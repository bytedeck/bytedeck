import json
import posixpath
import re
import uuid
from datetime import datetime, timezone as dt_timezone

from django.utils.html import format_html
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic.list import ListView

import numpy as np

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import (
    Case, DateTimeField, F, ExpressionWrapper, fields, BooleanField, Count, Exists, IntegerField, OuterRef, Q, Sum, Value, When,
)
from django.db.models.functions import Coalesce, Now
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import Http404, get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, View
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from hackerspace_online.decorators import staff_member_required, xml_http_request_required

from badges.models import BadgeAssertion
from comments.models import Comment, Document
from comments.sanitize import sanitize_comment_html
from comments.utils import accepted_attachments, save_draft_attachments
from questions.forms import QuestionSubmissionFormsetFactory
from questions.models import QuestionSubmission, QuestionType
from questions.utils import discard_draft_question_submissions, save_draft_file_answers, sync_draft_question_submissions
from courses.models import Block, CourseStudent
from utilities.sorting import apply_sort, resolve_sort

from .listing import QUEST_SORT_COLUMNS, search_quests
from library.utils import is_library_schema_requested, library_schema_if_requested
from notifications.signals import notify
from notifications.models import notify_rank_up
from prerequisites.views import ObjectPrereqsFormView
from siteconfig.models import SiteConfig
from tenant.views import NonPublicOnlyViewMixin, non_public_only_view
from djcytoscape.views import UpdateMapMessageMixin
from profile_manager.models import Profile
from collections import Counter

from .forms import (
    QuestForm,
    SubmissionForm,
    SubmissionFormCustomXP,
    SubmissionFormStaff,
    SubmissionQuickReplyForm,
    SubmissionQuickReplyFormStudent,
    TAQuestForm,
    CommonDataForm,
)
from .models import Quest, QuestSubmission, Category, CommonData
from djcytoscape.models import CytoScape

User = get_user_model()


def is_staff_or_TA(user):
    if user.is_staff:
        return True

    try:
        if user.profile.is_TA:
            return True
    except AttributeError:  # probably because the user is not logged in, so AnonymousUser and has no profile
        pass

    return False


@method_decorator(staff_member_required, name='dispatch')
class CategoryList(NonPublicOnlyViewMixin, LoginRequiredMixin, ListView):
    model = Category

    @property
    def inactive_tab_active(self):
        return '/inactive/' in self.request.path

    @property
    def available_tab_active(self):
        return self.request.path in [reverse('quest_manager:categories'), reverse('quest_manager:categories_available')]

    def get_queryset(self):
        queryset = super().get_queryset()

        if self.inactive_tab_active:
            queryset = queryset.filter(published=False)
        else:
            queryset = queryset.filter(published=True)

        # provide the per-campaign counts the template displays in a single query,
        # instead of a COUNT/SUM per campaign (see Category.quest_count / xp_sum);
        # the filter must match Category.current_quests(): published and not archived
        current_quest_filter = Q(quest__published=True) & ~Q(quest__archived=True)
        queryset = queryset.annotate(
            quest_count_annotated=Count('quest', filter=current_quest_filter),
            xp_sum_annotated=Sum('quest__xp', filter=current_quest_filter),
        )

        return queryset

    def get_context_data(self, *args, **kwargs):
        """Add the tab state and the campaign table's flags to the deck's campaign list.

        Args:
            *args: positional arguments passed through to `ListView.get_context_data`.
            **kwargs: keyword arguments passed through to `ListView.get_context_data`.

        Returns:
            dict: the template context, with
                - available_tab_active (bool): the Available tab is the one being shown.
                - inactive_tab_active (bool): the Inactive tab is the one being shown.
                - is_library_view (bool): False. The campaign table is shared with the
                    Library's campaign list, and this is the deck's own copy, so it shows
                    the local actions rather than the Library's import action.

        The export action's flag is not set here: the template asks the
        `can_export_to_library` tag itself.
        """
        context_data = super().get_context_data(*args, **kwargs)

        context_data['available_tab_active'] = self.available_tab_active
        context_data['inactive_tab_active'] = self.inactive_tab_active
        # these are the deck's own campaigns, so the shared campaign table shows the
        # local actions (edit, publish, export, delete) rather than the Library's import action
        context_data['is_library_view'] = False

        return context_data


class CategoryDetail(NonPublicOnlyViewMixin, LoginRequiredMixin, DetailView):
    """The only category view non-staff users should have access to

    A view that contains campaign information as well as a comprehensive list of
    quests in a given campaign that eschews the complexity and unreliability of maps,
    and changes dynamically based on the credentials of the user accessing it.
    """

    model = Category

    def get_context_data(self, **kwargs):
        """Sets context data passed to the Category Detail view template

        Currently only exists as a picker for which list of quests those who access the view will see:
        - Staff users will see a complete list of quests currently in the viewed campaign
        - Students or other non-staff users will only see active quests

        Returns:
            dict: Context info containing the appropriate quests for the user to view,
            including "category_displayed_quests".
        """
        if self.request.user.is_staff:
            quests = Quest.objects.filter(campaign=self.object)
        else:
            # students shouldn't be able to see inactive quests when they access this view
            quests = Quest.objects.get_active().filter(campaign=self.object)

        # The template reads each quest's icon (which falls back to the campaign
        # icon), tags, and calls quest.expired() (twice), so select_related the
        # campaign, prefetch tags and annotate is_expired to avoid a handful of
        # queries per quest. This mirrors the quest list view (see quest_list()).
        quests = quests.select_related("campaign").prefetch_related("tags")
        not_expired_subquery = quests.not_expired().values("id")
        quests = quests.annotate(
            is_expired=ExpressionWrapper(
                ~Exists(not_expired_subquery.filter(id=OuterRef("id"))),
                output_field=BooleanField(),
            )
        )

        kwargs['category_displayed_quests'] = quests

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name="dispatch")
class CategoryCreate(NonPublicOnlyViewMixin, CreateView):
    fields = ("title", "short_description", "icon", "published", "map_order")
    model = Category
    success_url = reverse_lazy("quests:categories")

    def get_context_data(self, **kwargs):
        """Add the campaign creation form context.

        Args:
            **kwargs: extra context passed through to the template.

        Returns:
            dict: template context including the form heading, submit button label,
            and `cancel_url` — the campaigns list, since a new campaign has no
            detail view to return to yet.
        """
        kwargs["heading"] = "Create New Campaign"
        kwargs["submit_btn_value"] = "Create"
        kwargs["cancel_url"] = reverse("quests:categories")

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name="dispatch")
class CategoryUpdate(NonPublicOnlyViewMixin, UpdateView):
    fields = ("title", "short_description", "icon", "published", "map_order")
    model = Category
    # no success_url: UpdateView falls back to the object's get_absolute_url(), returning
    # the user to the campaign detail view they started the edit from (issue #1931)

    def get_context_data(self, **kwargs):
        """Add the campaign update form context.

        Args:
            **kwargs: extra context passed through to the template.

        Returns:
            dict: template context including the form heading, submit button label,
            and `cancel_url` — the campaign's detail view, so cancelling returns
            to the page the edit was started from (issue #1931).
        """
        kwargs["heading"] = "Update Campaign"
        kwargs["submit_btn_value"] = "Update"
        kwargs["cancel_url"] = self.object.get_absolute_url()

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name="dispatch")
class CategoryDelete(NonPublicOnlyViewMixin, DeleteView):
    model = Category
    success_url = reverse_lazy("quests:categories")

    def post(self, request, *args, **kwargs):
        """
        Handle POST requests by delegating to the delete method to
        enforce custom deletion logic and validation.
        """
        return self.delete(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """
        Attempt to delete the Category object only if it has no published quests.
        If published quests exist, prevent deletion and display an error message.

        This logic protects against race conditions where the user loads the delete
        confirmation page while the campaign appears deletable (e.g., only has
        unpublished quests), but by the time they submit the form, one or more
        quests may have been published.
        https://github.com/bytedeck/bytedeck/pull/1837#discussion_r2232233693

        Returns:
            HttpResponseRedirect on successful deletion or redirect back with error.
        """
        self.object = self.get_object()

        # Use a fresh queryset directly from Quest.objects instead of self.object.quest_set
        # to avoid stale cached related objects and ensure we check the latest DB state.
        if Quest.objects.filter(campaign=self.object, published=True).exists():
            messages.error(
                request,
                "You can't delete this campaign because it contains published quests"
            )
            return redirect(self.success_url)

        return super().delete(request, *args, **kwargs)


@method_decorator(staff_member_required, name='dispatch')
class CategoryPublish(View):
    http_method_names = ['post']

    def post(self, request, pk):
        """
        Handle POST request to publish a campaign and all its associated quests.

        Retrieves the Category by primary key (pk). Attempts to publish the campaign along
        with all related quests using the model method `publish_with_quests()`. On success,
        adds a success message linking to the campaign detail. On failure, adds an error message.

        Finally, redirects the user back to the page the publish button was clicked on: the
        `next` POST parameter if it is a safe local URL (the campaigns list view provides it),
        otherwise the campaign's detail view (issue #1931).

        Args:
            request: The HTTP request object.
            pk: Primary key of the campaign to publish.

        Returns:
            HttpResponseRedirect to the `next` URL or the campaign detail page.
        """
        category = get_object_or_404(Category, pk=pk)
        category.publish_with_quests()
        messages.success(request, format_html(
            'Campaign "<a href="{}">{}</a>" and all quests published.',
            category.get_absolute_url(), category.title,
        ))

        # only follow `next` if it stays on this host (and keeps https when the
        # request came in over https), to prevent open redirects and downgrades
        next_url = request.POST.get('next')
        if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            return redirect(next_url)
        return redirect(category)


class QuestDelete(NonPublicOnlyViewMixin, UserPassesTestMixin, UpdateMapMessageMixin, DeleteView):
    def test_func(self):
        return self.get_object().is_editable(self.request.user)

    def get_queryset(self):
        """
        Include archived quests so that archived quests can be deleted using this views.
        """
        return Quest.objects.all_including_archived()

    model = Quest
    success_url = reverse_lazy("quests:quests")

    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class QuestFormViewMixin:
    """Data and methods common to QuestCreateView, QuestUpdateView, and QuestCopyView"""

    model = Quest

    def form_valid(self, form):
        # TA created quests should not be published.
        if self.request.user.profile.is_TA:
            form.instance.published = False
            form.instance.editor = self.request.user
        # When a teacher makes a form published, remove editor abilities.
        elif form.instance.published:
            form.instance.editor = None

        # Save the object so we can add prereqs to it
        super_response = super().form_valid(form)
        self.set_new_prereqs(form)
        return super_response

    def set_new_prereqs(self, form):
        # Set new prerequisites, if any:
        quest_prereq = form.cleaned_data["new_quest_prerequisite"]
        badge_prereq = form.cleaned_data["new_badge_prerequisite"]
        if quest_prereq or badge_prereq:
            self.object.clear_all_prereqs()
            self.object.add_simple_prereqs([quest_prereq, badge_prereq])

    def get_form_class(self):
        if self.request.user.profile.is_TA:
            return TAQuestForm
        else:
            return QuestForm


class QuestCreate(NonPublicOnlyViewMixin, UserPassesTestMixin, QuestFormViewMixin, CreateView):
    def test_func(self):
        return is_staff_or_TA(self.request.user)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super().get_context_data(**kwargs)
        context["heading"] = "Create New Quest"
        context["cancel_url"] = reverse("quests:quests")
        context["submit_btn_value"] = "Create"
        return context


class QuestUpdate(NonPublicOnlyViewMixin, UserPassesTestMixin, QuestFormViewMixin, UpdateMapMessageMixin, UpdateView):
    def test_func(self):
        # user self.get_object() because self.object doesn't exist yet
        # https://stackoverflow.com/questions/38544692/django-dry-principle-and-userpassestestmixin
        return self.get_object().is_editable(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["heading"] = "Update Quest"
        context["cancel_url"] = reverse("quests:quest_detail", args=[self.object.id])
        context["submit_btn_value"] = "Update"
        return context

    def get_success_url(self):
        if self.object.archived:
            return reverse("quests:quests")
        return self.object.get_absolute_url()  # this is default

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        qs = form.fields["new_quest_prerequisite"].queryset
        # Remove the object being edited as an option for a prerequisite
        form.fields["new_quest_prerequisite"].queryset = qs.exclude(id=self.object.id)
        return form


class QuestPrereqsUpdate(ObjectPrereqsFormView):
    model = Quest


class QuestCopy(QuestCreate):
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        # by default, set the quest this was copied from as the new_quest_prerequisite
        # If this is changed in the form it will be overwritten in form_valid() from QuestFormViewMixin
        copied_quest = get_object_or_404(Quest, pk=self.kwargs["quest_id"])
        # Set initial tags and prerequisite for the form
        kwargs["initial"]["tags"] = copied_quest.tags.all()
        kwargs["initial"]["new_quest_prerequisite"] = copied_quest

        # Create a new Quest instance based on the copied quest
        new_quest = get_object_or_404(Quest, pk=self.kwargs["quest_id"])
        new_quest.pk = None  # autogen a new primary key (quest_id by default)
        new_quest.import_id = uuid.uuid4()  # assign a new import ID
        new_quest.name = new_quest.name + " - COPY"  # indicate this is a copy

        kwargs["instance"] = new_quest
        return kwargs

    def form_valid(self, form):
        """Save the new (copied) quest and duplicate the source quest's submission questions
        onto it, so a copied quest keeps its questions (issue #2161).

        `form` is the validated QuestForm bound to the new (copied) quest instance. Returns the
        redirect response from the parent view. Quest creation, prerequisite setup and question
        duplication all run inside a single transaction, so a failure duplicating a question rolls
        back the whole copy rather than leaving an orphaned quest with no (or partial) questions.

        Student answers are not copied — those belong to submissions, not to the quest. The
        solution_file reference is shared with the source question, matching how the copied
        quest already shares its icon file.
        """
        from questions.models import Question

        with transaction.atomic():
            response = super().form_valid(form)  # saves self.object (the new quest) and sets prereqs

            source_quest = get_object_or_404(Quest, pk=self.kwargs["quest_id"])
            for question in Question.objects.filter(quest=source_quest):
                question.pk = None
                question.quest = self.object
                question.full_clean()
                question.save()
        return response


class QuestSubmissionSummary(UserPassesTestMixin, DetailView):
    model = Quest
    context_object_name = "quest"
    template_name = "quest_manager/summary.html"

    def test_func(self):
        return is_staff_or_TA(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        subs = self.object.questsubmission_set.exclude(time_approved=None)
        subs = QuestSubmission.objects.all_approved(quest=self.object, active_semester_only=False)
        if subs:
            latest_submission_time = subs.latest("time_approved").time_approved
        else:
            latest_submission_time = None
        count_total = subs.count()
        subs = subs.filter(time_returned=None)
        count_first_time = subs.count()
        if count_total > 0:
            percent_returned = int((count_total - count_first_time) / count_total * 100)
        else:
            percent_returned = None

        context["count_total"] = count_total
        context["count_first_time"] = count_first_time
        context["percent_returned"] = percent_returned
        context["latest_submission_time"] = latest_submission_time

        return context


@method_decorator([staff_member_required], name="dispatch")
class QuestArchive(NonPublicOnlyViewMixin, DetailView):
    model = Quest
    template_name = "quest_manager/quest_confirm_archive.html"

    def get_context_data(self, **kwargs):
        """
        Add prerequisite information to the context for the archive confirmation page.

        Includes a list of all objects that list this quest as a prerequisite, regardless of active status,
        under the 'prereq_of' key for use in the template.
        """
        context = super().get_context_data(**kwargs)
        quest = self.get_object()
        prereq_of = []
        for obj in quest.get_reliant_objects(active_only=False):
            # add an attribute 'model_name' for template use
            obj.model_name = obj.__class__.__name__
            prereq_of.append(obj)

        context['prereq_of'] = prereq_of
        return context

    def post(self, request, *args, **kwargs):
        """
        Archive a quest after confirmation, unless it is currently used as a prerequisite.

        If the quest is a prerequisite for any other quests, prevent archiving, display
        an error message, and redirect the user to the quest detail page.

        If archiving proceeds:
        - Set `archived=True` and validate/save the quest.
        - Delete all submissions associated with the quest.
        - Recalculate/invalidate XP for all users who previously submitted the quest.
        - Display a success message.
        - Redirect to the archived quests list.

        Returns:
            HttpResponseRedirect: Either to the quest detail page (if blocked) or the archived list (if successful).
        """
        quest = self.get_object()

        if quest.is_used_prereq():
            messages.error(
                request,
                "You cannot archive this quest while it is a prerequisite for other quests. "
                "Remove it as a prerequisite from all dependent quests before archiving."
            )
            return redirect("quests:quest_detail", quest.id)

        quest_link = format_html('<a href="{}">{}</a>', quest.get_absolute_url(), quest.name)

        # Archive the quest
        quest.archived = True
        quest.published = False
        quest.full_clean()
        quest.save()

        # Use the base manager to include all submissions (even if your default manager filters some out)
        base_qs = QuestSubmission._base_manager.filter(quest=quest)

        # Grab affected user IDs before deletion
        user_ids = list(base_qs.values_list('user_id', flat=True).distinct())

        # Delete all submissions in one go
        base_qs.delete()

        # Invalidate XP for each affected user
        for user_id in user_ids:
            try:
                profile = Profile.objects.get(user_id=user_id)
                profile.xp_invalidate_cache()
            except Profile.DoesNotExist:
                continue

        messages.success(
            request,
            format_html("Quest '{}' has been archived and all its submissions have been deleted.", quest_link),
        )
        return redirect("quests:archived")


class QuestBulkEditView(UserPassesTestMixin, View):
    """
    View to handle bulk editing operations on Quest objects.

    Allows staff users (and TAs for permission checks) to perform bulk actions
    such as publishing, unpublishing, deleting, and unarchiving multiple quests at once.

    GET requests redirect to the main quest list with bulk edit mode enabled.

    POST requests perform the specified bulk action on the selected quests and
    redirect back to the quest list with a success or error message.

    Permissions:
        Only users passing `is_staff_or_TA` check are allowed.

    Actions supported:
        - delete
        - publish
        - unpublish
        - unarchive
    """

    # Note: TAs pass this permission check, but bulk editing UI is currently restricted to staff only,
    # so TAs cannot perform bulk edits via the frontend yet.
    def test_func(self):
        return is_staff_or_TA(self.request.user)

    @staticmethod
    def bulk_update_quests(quests, field_updates: dict, extra_update_fields: list = None):
        """
        Apply field updates to each quest in the queryset and save them individually.

        Args:
            quests (QuerySet): A queryset of Quest instances.
            field_updates (dict): Field name -> new value.
            extra_update_fields (list): Any extra fields to save beyond those in field_updates.

        Returns:
            int: Number of quests updated.
        """
        count = 0
        update_fields = list(field_updates.keys())
        if extra_update_fields:
            update_fields.extend(extra_update_fields)

        seen = set()
        update_fields = [f for f in update_fields if not (f in seen or seen.add(f))]

        for quest in quests.iterator():
            for field, value in field_updates.items():
                setattr(quest, field, value)
            quest.full_clean()
            quest.save(update_fields=update_fields)
            count += 1
        return count

    def get(self, request, *args, **kwargs):
        bulk_edit_mode = request.user.is_staff and 'bulk_edit' in request.GET
        context = {
            'bulk_edit_mode': bulk_edit_mode,
        }
        return render(request, 'quest_manager/tab_quests_available.html', context)

    def post(self, request, *args, **kwargs):
        """
        Handle bulk editing operations on selected quests, including:
        - Deletion
        - Publishing
        - Unpublishing
        - Unarchiving

        Expects:
            - 'selected_quests[]': A list of quest IDs to act upon.
            - 'action': The bulk action to perform (e.g., "delete", "publish").

        Redirects to the quest list view with a success or warning message.

        Returns:
            HttpResponseRedirect: Redirect to the quest list page with feedback.
        """
        quest_ids = request.POST.getlist("selected_quests[]")
        action = request.POST.get("action")

        if not quest_ids:
            messages.warning(request, "No quests selected.")
            return redirect("quests:quests")
        if action in ["unarchive", "delete"]:
            # Include archived quests for delete and unarchive actions because
            # those target quests excluded from the default queryset.
            quests = Quest.objects.all_including_archived().filter(id__in=quest_ids)
        else:
            quests = Quest.objects.filter(id__in=quest_ids)

        if action == "delete":
            count = 0
            for quest in quests:
                quest.delete()
                count += 1
            messages.success(request, f"{count} quest(s) deleted.")
        elif action == "publish":
            count = self.bulk_update_quests(
                quests,
                field_updates={"published": True, "editor": None}
            )
            messages.success(request, f"{count} quest(s) published.")
        elif action == "unpublish":
            count = self.bulk_update_quests(
                quests,
                field_updates={"published": False}
            )
            messages.success(request, f"{count} quest(s) unpublished.")
        elif action == "unarchive":
            count = self.bulk_update_quests(
                quests,
                field_updates={"archived": False, "published": False}
            )
            messages.success(request, f"{count} quest(s) unarchived.")

        return redirect("quests:quests")


@method_decorator(staff_member_required, name="dispatch")
class CommonDataListView(ListView):
    model = CommonData
    template_name = "quest_manager/common_quest_info_list.html"


@method_decorator(staff_member_required, name="dispatch")
class CommonDataCreateView(CreateView):
    model = CommonData
    form_class = CommonDataForm
    template_name = "quest_manager/common_quest_info_form.html"
    success_url = reverse_lazy("quest_manager:commonquestinfo_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["heading"] = "Create Common Quest Info"
        context["submit_btn_value"] = "Create"
        return context


@method_decorator(staff_member_required, name="dispatch")
class CommonDataUpdateView(UpdateView):
    model = CommonData
    form_class = CommonDataForm
    template_name = "quest_manager/common_quest_info_form.html"
    success_url = reverse_lazy("quest_manager:commonquestinfo_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["heading"] = "Update Common Quest Info"
        context["submit_btn_value"] = "Update"
        return context

    def get_success_url(self):
        return self.request.GET.get("next", self.success_url)


@method_decorator(staff_member_required, name="dispatch")
class CommonDataDeleteView(DeleteView):
    model = CommonData
    template_name = "quest_manager/common_quest_info_delete.html"
    success_url = reverse_lazy("quest_manager:commonquestinfo_list")


@xml_http_request_required
@non_public_only_view
@login_required
def ajax_summary_histogram(request, pk):
    max_ = int(request.GET.get("max", 60))
    min_ = int(request.GET.get("min", 1))

    quest = get_object_or_404(Quest, pk=pk)

    minutes_list = get_minutes_to_complete_list(quest)

    np_data = np.array(minutes_list)
    # remove outliers
    np_data = np_data[(np_data >= min_) & (np_data < max_ + 1)]
    # sort values
    np_data = np.sort(np_data)

    histogram_values, histogram_labels = get_histogram(np_data, min_, max_)

    size = np_data.size
    mean = float(np.mean(np_data))
    data = {
        "histogram_values": histogram_values.tolist(),
        "histogram_labels": histogram_labels[:-1].tolist(),
        "count": size,
        "mean": mean,
        "percentile_50": int(np.median(np_data)) if size else None,
        "percentile_25": int(np_data[size // 4]) if size else None,
        "percentile_75": int(np_data[size * 3 // 4]) if size else None,
    }

    return JsonResponse(data)


def get_histogram(data_list, min, max):
    # step should be 1 until we reach 60, then got to step size 2 for every 60 in the range
    step = (max - min - 1) // 60 + 1

    # max +2:
    #  +1 because we don't want to cut off at the max, we want to include max as the last step
    #  +1 because the highest # is the right bin edge
    bins = range(min, max + 2, step)
    return np.histogram(data_list, bins=bins)


def get_minutes_to_complete_list(quest):
    # Only approved, never returned quests
    subs = (
        quest.questsubmission_set.filter(time_returned=None)
        .exclude(first_time_completed=None)
        .exclude(time_approved=None)
    )

    duration = ExpressionWrapper(
        F("first_time_completed") - F("timestamp"), output_field=fields.DurationField()
    )
    subs = subs.annotate(time_to_complete=duration)
    time_list = subs.values_list("time_to_complete", flat=True)
    minutes_list = [t.total_seconds() / 60 for t in time_list]

    return minutes_list


class QuestListViewTabTypes:
    """ enum for quest_list's tabs.
    Note: using enum.auto() will not work as django template tags cant properly define its value.
    """
    AVAILABLE = 0
    IN_PROGRESS = 1
    COMPLETED = 2
    PAST = 3
    DRAFT = 4
    ARCHIVED = 5


@non_public_only_view
@login_required
def quest_list(request, quest_id=None, template="quest_manager/quests.html"):
    available_quests = []
    in_progress_submissions = []
    completed_submissions = []
    past_submissions = []
    draft_quests = []
    archived_quests = []

    view_type = QuestListViewTabTypes.AVAILABLE
    remove_hidden = True

    active_quest_id = 0

    # Figure out what tab we want.
    if quest_id is not None:
        # if a quest_id was provided, got to the Available tab
        active_quest_id = int(quest_id)
        view_type = QuestListViewTabTypes.AVAILABLE
    # otherwise look at the path
    elif "/inprogress/" in request.path_info:
        view_type = QuestListViewTabTypes.IN_PROGRESS
    elif "/completed/" in request.path_info:
        view_type = QuestListViewTabTypes.COMPLETED
    elif "/past/" in request.path_info:
        view_type = QuestListViewTabTypes.PAST
    elif "/drafts/" in request.path_info:
        view_type = QuestListViewTabTypes.DRAFT
    elif "/archived/" in request.path_info:
        view_type = QuestListViewTabTypes.ARCHIVED
    else:
        view_type = QuestListViewTabTypes.AVAILABLE
        if "/all/" in request.path_info:
            remove_hidden = False

    page = request.GET.get("page")

    # Quest and Submission Querysets (in order of tabs =)
    if request.user.is_staff:
        available_quests = (
            Quest.objects.all()
            .published()
            .select_related("campaign", "editor__profile")
            .prefetch_related("tags")
        )
        # There was a looping call to quest.expired() which was causing a lot of queries.  Instead, annotate the value here
        not_expired_subquery = available_quests.not_expired().values("id")
        available_quests = available_quests.annotate(
            is_expired=ExpressionWrapper(
                ~Exists(not_expired_subquery.filter(id=OuterRef("id"))),
                output_field=BooleanField(),
            )
        )
    else:
        if request.user.profile.has_current_course:
            available_quests = Quest.objects.get_available(request.user, remove_hidden)
        else:
            available_quests = Quest.objects.get_available_without_course(request.user)

    # Repeatable quests the student completed that are still within their cooldown window: shown in
    # the Available tab as "available again soon" with a countdown, rather than being hidden (#57).
    cooldown_quests = []
    if not request.user.is_staff:
        cooldown_quests = list(Quest.objects.get_in_cooldown(request.user))
        for quest in cooldown_quests:
            quest.cooldown_available_at = quest.next_repeat_available(request.user)

    in_progress_submissions = QuestSubmission.objects.all_not_completed(
        request.user, blocking=True
    )
    completed_submissions = QuestSubmission.objects.all_completed(request.user)
    past_submissions = QuestSubmission.objects.all_completed_past(request.user)
    draft_quests = Quest.objects.all_drafts(request.user)
    archived_quests = Quest.objects.all_archived(request.user)

    # Counts
    in_progress_submissions_count = in_progress_submissions.count()
    completed_submissions_count = completed_submissions.count()
    past_submissions_count = past_submissions.count()
    drafts_count = draft_quests.count()
    archived_count = archived_quests.count()
    available_quests_count = (
        len(available_quests)
        if type(available_quests) is list
        else available_quests.count()
    )

    # The quest tabs show the campaign, and are the student's own submissions, so there is
    # no user column. The in-progress tab's Status cell carries no time, so it offers no
    # sort by it. The tabs that are not paginated offer nothing: their headings stay plain
    # until they are paginated too.
    sortable_columns = {}
    sort_column, sort_descending = '', False

    if view_type == QuestListViewTabTypes.IN_PROGRESS:
        sortable_columns = submission_sort_columns(campaign=True, status=False)
        in_progress_submissions, sort_column, sort_descending = sorted_submission_page(
            request, in_progress_submissions, sortable_columns, page,
        )
        # available_quests = []
    elif view_type == QuestListViewTabTypes.COMPLETED:
        # completed_submissions_count = completed_submissions.count()
        sortable_columns = submission_sort_columns(campaign=True)
        completed_submissions, sort_column, sort_descending = sorted_submission_page(
            request, completed_submissions, sortable_columns, page,
        )
        # available_quests = []
    elif view_type == QuestListViewTabTypes.PAST:
        sortable_columns = submission_sort_columns(campaign=True)
        past_submissions, sort_column, sort_descending = sorted_submission_page(
            request, past_submissions, sortable_columns, page,
        )
        # available_quests = []

    if view_type == QuestListViewTabTypes.DRAFT:
        quests = draft_quests
    elif view_type == QuestListViewTabTypes.ARCHIVED:
        quests = archived_quests
    else:
        quests = available_quests

    # The quest tabs are searched, ordered and paginated in the database, so all three
    # cover the whole tab rather than the page the browser is holding (#2379, #2410).
    # The counts above are taken first, so the tab badges keep reporting what the tab
    # holds rather than what the current search matched.
    search_term = request.GET.get('q', '').strip()
    quests = search_quests(quests, search_term)
    num_matching_quests = quests.count()

    quest_sort_column, quest_sort_descending = resolve_sort(request, QUEST_SORT_COLUMNS)
    quests = apply_sort(quests, QUEST_SORT_COLUMNS, quest_sort_column, quest_sort_descending, tie_break='name')
    quests = paginate(quests, page)

    # Used to explain why the "Available" tab is empty, if it is
    awaiting_approval = QuestSubmission.objects.filter(
        user=request.user, is_approved=False, is_completed=True
    ).exists()

    context = {
        "heading": "Quests",
        "quests": quests,
        "awaiting_approval": awaiting_approval,
        "available_quests": available_quests,
        "remove_hidden": remove_hidden,
        "num_available": available_quests_count,
        "in_progress_submissions": in_progress_submissions,
        "num_inprogress": in_progress_submissions_count,
        "completed_submissions": completed_submissions,
        "draft_quests": draft_quests,
        "num_drafts": drafts_count,
        "archived_quests": archived_quests,
        "num_archived": archived_count,
        "past_submissions": past_submissions,
        "num_past": past_submissions_count,
        "num_completed": completed_submissions_count,
        "cooldown_quests": cooldown_quests,
        "active_q_id": active_quest_id,
        "VIEW_TYPES": QuestListViewTabTypes,
        "view_type": view_type,
        "bulk_edit_mode": request.user.is_staff and 'bulk_edit' in request.GET,
        # Read by snippets/sortable_column_heading.html in the submission tabs' table
        "sortable_columns": sortable_columns,
        "sort_column": sort_column,
        "sort_descending": sort_descending,
        # The quest tabs (available, drafts, archived) carry their own search and order,
        # since they list quests rather than submissions
        "search_term": search_term,
        "num_matching_quests": num_matching_quests,
        "quest_sortable_columns": QUEST_SORT_COLUMNS,
        "quest_sort_column": quest_sort_column,
        "quest_sort_descending": quest_sort_descending,
    }
    return render(request, template, context)


@xml_http_request_required
@non_public_only_view
@login_required
def ajax_quest_info(request, quest_id=None):
    """Return the rendered preview panel for one quest, for the accordion tables.

    POST only, and XHR only (see the decorators). The accordion in
    bootstrap-table-accordion.js calls this when a row is expanded and drops the
    returned HTML into the row's detail area.

    On a Library page the accordion sets ``use_library_schema=1``, which serves
    the preview out of the shared Library schema instead of the caller's own
    deck. That flag is a boolean by design: the schema name is resolved server
    side from the library app's config, never taken from the request, so a
    caller cannot name the schema its request runs against (schema names are the
    decks' public subdomains, so accepting one would let any logged-in user read
    another deck's content).

    Args:
        request (HttpRequest): the current request. Reads ``use_library_schema``
            from POST; everything else comes from the URL and the session.
        quest_id (int | None): primary key of the quest to preview, in whichever
            schema the flag above selected. Staff may preview archived quests.

    Returns:
        JsonResponse: ``{"quest_info_html": "<rendered preview>"}``.

    Raises:
        Http404: if the request is not a POST, if no ``quest_id`` is given (the
            "every quest at once" response was an unbounded per-request memory
            hog with no staff gate, issue #2081), or if no matching quest is
            visible to this user.
    """
    if request.method == "POST":
        template = 'quest_manager/preview_content_quests_avail.html'

        with library_schema_if_requested(request):
            is_library_view = is_library_schema_requested(request)

            if quest_id:
                if request.user.is_staff:
                    quest = get_object_or_404(Quest.objects.all_including_archived(), pk=quest_id)
                else:
                    quest = get_object_or_404(Quest, pk=quest_id)

                # The export button's can_export_to_library tag runs during this render,
                # so it still answers for the schema selected above: on a Library preview
                # it sees the Library schema and offers no export button.
                quest_info_html = render_to_string(template,
                                                   {'q': quest, 'is_library_view': is_library_view},
                                                   request=request)

                data = {'quest_info_html': quest_info_html}

                return JsonResponse(data)

            else:
                # No quest_id: the accordion UI always requests one quest at a time by id, so there
                # is no legitimate caller for an "all quests" response. Rendering every quest's
                # preview HTML into a single JSON blob (held twice in memory -- the dict of rendered
                # strings and then the json.dumps of it) is an unbounded per-request memory hog that
                # any logged-in user could trigger by POSTing the bare URL, and it had no staff gate
                # (issue #2081). Reject it like the view's other invalid requests.
                raise Http404

    else:
        raise Http404


@xml_http_request_required
@non_public_only_view
@staff_member_required
def ajax_approval_info(request, submission_id=None):
    """Render one submission's row content for the teachers' approvals page.

    Staff-only: the template it renders includes the quest's Instructor Notes and the
    submitting student's details, and its only caller is the approvals page, which is
    itself staff-only.
    """
    if request.method == "POST":
        qs = QuestSubmission.objects.get_queryset(exclude_archived_quests=False, exclude_quests_not_published=False)

        sub = get_object_or_404(qs, pk=submission_id)
        template = 'quest_manager/preview_content_approvals.html'
        quest_info_html = render_to_string(template, {'s': sub}, request=request)

        return JsonResponse({'quest_info_html': quest_info_html})
    else:
        raise Http404


@xml_http_request_required
@non_public_only_view
@login_required
def ajax_submission_info(request, submission_id=None):
    """Render the preview panel for one submission, requested over AJAX from a submission tab.

    Three legs pick the queryset by URL: /past/ and /completed/ scope to the requester's own
    finished submissions, while the default (in-progress) leg previews any submission for staff
    and TAs (the copy-a-started-quest feature, #141) but only the requester's own for a regular
    student, so one student cannot read another's answers or comment thread (#2558). Only an
    AJAX POST is served; anything else is a 404.
    """
    if request.method == "POST":
        # past means previous semester that is now closed
        past = "/past/" in request.path_info
        completed = "/completed/" in request.path_info

        if past:  # past subs are filtered out of default queryset, so need to get
            qs = QuestSubmission.objects.all_completed_past(request.user)
        elif completed:
            qs = QuestSubmission.objects.all_completed(request.user)
        else:
            # The in-progress preview is unscoped for staff and TAs (a TA previews another
            # student's started quest to copy it, #141), but a regular student may only see
            # their own submission: otherwise any logged-in student could POST another
            # student's submission id and read their answers and comment thread.
            qs = QuestSubmission.objects.all()
            if not is_staff_or_TA(request.user):
                qs = qs.get_user(request.user)

        sub = get_object_or_404(qs, pk=submission_id)

        context = {
            "s": sub,
            "completed": completed,
            "past": past,
        }
        template = "quest_manager/preview_content_submissions.html"
        quest_info_html = render_to_string(template, context, request=request)

        return JsonResponse({"quest_info_html": quest_info_html})
    else:
        raise Http404


@non_public_only_view
@login_required
def detail(request, quest_id):
    """
    Display the quest if it is available to the user or if user is staff, otherwise check for a completed submission
    and display that.  If no submission, and not available, then display a restricted version.
    :param request:
    :param quest_id:
    :return:
    """

    q = get_object_or_404(Quest.objects.all_including_archived(), pk=quest_id)

    if q.is_available(request.user) or q.is_editable(request.user):
        available = True
    else:
        # Display submission if quest is not available
        submissions = QuestSubmission.objects.all_for_user_quest(
            request.user, q, active_semester_only=False
        )
        if submissions:
            sub = submissions.latest("time_approved")
            return redirect(sub)
        else:
            # No submission either, so display quest flagged as unavailable
            available = False

    context = {
        "heading": q.name,
        "q": q,
        "available": available,
        "maps": CytoScape.objects.get_related_maps(q),
    }

    return render(request, "quest_manager/detail.html", context)


@non_public_only_view
@staff_member_required
def quest_user_status(request, quest_id):
    """
    Display the status of all active students for a given quest.

    Retrieves all active student profiles and their latest submission for the specified quest.
    For each student, determines their submission status, including:
    - Not Started (no submission)
    - Approved (approved submission)
    - Returned (submission returned for revisions)
    - Awaiting Approval (submission pending review)
    - In Progress (submission in progress but not yet approved/returned)

    Passes the quest and a list of user statuses with their submissions to the template
    for rendering.

    Args:
        request (HttpRequest): The HTTP request object.
        quest_id (int): The primary key of the quest.

    Returns:
        HttpResponse: Rendered page showing the user status list for the quest.
    """
    quest = get_object_or_404(Quest.objects.all(), pk=quest_id)

    # Three student groups the page can show, as sets of user ids (issue #1973):
    #   active    — all active students (in a course or not); the superset
    #   current   — students registered in a course in a semester that is open
    #   my_blocks — students in a course block the current teacher teaches in one of those
    # The last two span every open semester, since a deck can run more than one at a time
    # (issue #2157 Phase 3): scoping them to the deck's default would count a student as
    # current and then leave them out of their own teacher's group.
    active_profiles = list(Profile.objects.all_active().students_only().select_related('user'))
    active_ids = {profile.user_id for profile in active_profiles}
    current_ids = set(
        CourseStudent.objects.all_users_in_open_semesters(students_only=True).values_list('id', flat=True)
    ) & active_ids
    my_block_ids = set(
        CourseStudent.objects.get_queryset().in_open_semesters().filter(
            block__current_teacher=request.user
        ).values_list('user_id', flat=True)
    ) & active_ids

    # Latest submission per user (over the active superset), newest attempt first.
    submissions = (
        QuestSubmission.objects.filter(quest=quest, user_id__in=active_ids)
        .select_related('user')
        .order_by('user_id', '-time_approved', '-id')
    )
    latest_sub_by_user = {}
    for sub in submissions:
        latest_sub_by_user.setdefault(sub.user_id, sub)

    def status_of(sub):
        """Map a user's latest submission (or None) to a display status."""
        if sub is None:
            return "Not Started"
        if sub.is_approved:
            return "Approved"
        if sub.is_returned():
            return "Returned"
        if sub.is_awaiting_approval():
            return "Awaiting Approval"
        return "In Progress"

    # One status entry per active student; a "completed" date only exists once approved.
    entries_by_id = {}
    for profile in active_profiles:
        sub = latest_sub_by_user.get(profile.user_id)
        entries_by_id[profile.user_id] = {
            "user": profile.user,
            "status": status_of(sub),
            "submission": sub,
            "completed": sub.time_approved if (sub and sub.is_approved) else None,
        }

    STATUS_ORDER = ["Approved", "Returned", "Awaiting Approval", "In Progress", "Not Started"]
    status_order_index = {status: i for i, status in enumerate(STATUS_ORDER)}

    # Which group the table shows; default to the teacher's own blocks, falling back to all active
    # students when they teach none so the page isn't empty.
    scopes = {"my_blocks": my_block_ids, "current": current_ids, "active": active_ids}
    scope = request.GET.get("scope", "my_blocks")
    if scope not in scopes:
        scope = "my_blocks"
    if scope == "my_blocks" and not my_block_ids:
        scope = "active"

    user_status_list = [entries_by_id[uid] for uid in scopes[scope]]
    user_status_list.sort(key=lambda e: (status_order_index.get(e["status"], 99), e["user"].username.lower()))

    # Status breakdown across all three groups, side by side.
    def counts_for(id_set):
        counts = Counter(entries_by_id[uid]["status"] for uid in id_set)
        total = len(id_set)
        return {
            status: {"count": counts.get(status, 0), "percent": f"{(counts.get(status, 0) / total * 100) if total else 0:.0f}%"}
            for status in STATUS_ORDER
        }

    breakdown_my_blocks = counts_for(my_block_ids)
    breakdown_current = counts_for(current_ids)
    breakdown_active = counts_for(active_ids)
    status_breakdown = [
        {
            "status": status,
            "my_blocks": breakdown_my_blocks[status],
            "current": breakdown_current[status],
            "active": breakdown_active[status],
        }
        for status in STATUS_ORDER
    ]

    context = {
        "q": quest,
        "maps": CytoScape.objects.get_related_maps(quest),
        "user_status_list": user_status_list,
        "status_breakdown": status_breakdown,
        "scope": scope,
        "has_my_blocks": bool(my_block_ids),
        "totals": {"my_blocks": len(my_block_ids), "current": len(current_ids), "active": len(active_ids)},
        "no_details": False,
        "is_library_view": False,
    }

    return render(request, "quest_manager/quest_user_status.html", context)


#######################################
#
#  Quest APPROVAL VIEWS
#
# #################################

class ApproveView(NonPublicOnlyViewMixin, View):
    """ When staff approves, returns, skips, or comments on a quest submission, this view is called.
    """

    def get_submission(self, submission_id):
        """ gets the main model of this view: QuestSubmission.
        functions like CRUD view's self.get_object()
        """
        return get_object_or_404(QuestSubmission, pk=submission_id)

    def get_form(self):
        """ Multiple forms because staff can either
        - use standard approve view
        - use quick reply view
        """
        # standard view
        if self.request.FILES or self.request.POST.get("awards"):
            return SubmissionFormStaff(self.request.POST, self.request.FILES)

        # quick reply
        return SubmissionQuickReplyForm(self.request.POST)

    def form_valid(self):
        """ handles response when form is valid
        - returns HttpResponse if standard
        - returns JsonResponse if ajax
        """
        if not self.is_ajax:
            return redirect("quests:approvals")

        # for ajax call. Need to replicate standard view's procedure where
        # - quest submission container disappears  (handled client side)
        # - message box container shows (handled here)
        template_name = 'messages-snippet.html'
        context = {
            'messages': list(messages.get_messages(self.request))
        }
        html = render_to_string(template_name, context)
        return JsonResponse(data={'messages_html': html})

    def form_invalid(self):
        """ handles response when form is invalid
        - returns HttpResponse if standard
        - returns JsonResponse if ajax
        """
        # need to return a failing status code for ajax request
        # without this should return a response with 200 status code
        if self.is_ajax:
            return JsonResponse({'error': 'Bad Request'}, status=400)

        # messages.error(request, "There was an error with your comment. Maybe you need to type something?")
        # return redirect(origin_path)

        # rendering here with the context allows validation errors to be displayed
        context = {
            "heading": self.submission.quest.name,
            "submission": self.submission,
            # "comments": comments,
            "submission_form": self.form,
            "anchor": "submission-form-" + str(self.submission.quest.id),
            # "reply_comment_form": reply_comment_form,
        }
        return render(self.request, "quest_manager/submission.html", context)

    # button handling
    def handle_form_button(self, notification_kwargs):
        """ handles any of the form buttons
        "approve_button", "comment_button", "return_button", "skip_button"
        in request

        takes in notification_kwargs and updates 'verb' and 'icon' keys
        returns default text incase staff submits without any comments
        """
        blank_comment_text = ""
        if "approve_button" in self.request.POST:
            note_verb = "approved"
            icon = (
                "<span class='fa-stack'>"
                + "<i class='fa fa-check fa-stack-2x text-success'></i>"
                + "<i class='fa fa-shield fa-stack-1x'></i>"
                + "</span>"
            )
            blank_comment_text = f"<p>{SiteConfig.get().blank_approval_text}</p>"
            self.submission.mark_approved()
        elif "comment_button" in self.request.POST:
            note_verb = "commented on"
            icon = (
                "<span class='fa-stack'>"
                + "<i class='fa fa-shield fa-stack-1x'></i>"
                + "<i class='fa fa-comment-o fa-stack-2x text-info'></i>"
                + "</span>"
            )
            blank_comment_text = "<p>(no comment added)</p>"
        elif "return_button" in self.request.POST:
            note_verb = "returned"
            icon = (
                "<span class='fa-stack'>"
                + "<i class='fa fa-shield fa-stack-1x'></i>"
                + "<i class='fa fa-ban fa-stack-2x text-danger'></i>"
                + "</span>"
            )
            blank_comment_text = f"<p>{SiteConfig.get().blank_return_text}</p>"
            self.submission.mark_returned()
        # dispatch() raises Http404 unless post_has_valid_button() is true, so one of the four
        # buttons is always present by the time this runs; this elif always matches when the
        # earlier ones did not, making the no-match fall-through unreachable.
        elif "skip_button" in self.request.POST:  # pragma: no branch
            note_verb = "skipped"
            icon = (
                "<span class='fa-stack text-muted'>"
                + "<i class='fa fa-shield fa-stack-1x'></i>"
                + "</span>"
            )
            blank_comment_text = (
                "<p>(Skipped - You were not granted XP for this quest)</p>"
            )
            # Matches the skip view: waiving the quest drops the answers the student drafted but
            # never submitted, so they don't linger as rows nothing will ever show (#2164). The
            # answers of any cycle they did submit stay published with their own comment. Both
            # steps share a transaction so a failure in the approval (which also grants badges
            # and recalculates XP) takes the deletion back with it.
            with transaction.atomic():
                discard_draft_question_submissions(self.submission)
                self.submission.mark_approved(transfer=True)

        notification_kwargs.update({
            'verb': note_verb,
            'icon': icon,
        })

        return blank_comment_text

    def post_has_valid_button(self):
        """ quick helper function to check if any of the valid buttons exist in POST request """
        valid_buttons = ["approve_button", "comment_button", "return_button", "skip_button"]
        return any(btype in self.request.POST for btype in valid_buttons)

    # misc.
    def get_notification_kwargs(self):
        """ gets the kwargs for notifications. every key should be empty unless
        there is something we want to put before hand.
        similar to get_context_data """
        kwargs = dict.fromkeys(["action", "target", "recipient", "affected_users", "verb", "icon"], None)

        # add default values here
        kwargs["target"] = self.submission
        kwargs["recipient"] = self.submission.user
        kwargs["affected_users"] = [self.submission.user]

        # if the staff member approving/commenting/returning the submission isn't
        # one of the student's teachers then notify the student's teachers too
        # If they have no teachers (e.g. this quest is available outside of a course
        # and the student is not in a course) then nothing will be appended anyway
        teachers_list = list(self.submission.user.profile.current_teachers())
        if self.request.user not in teachers_list:
            kwargs["affected_users"].extend(teachers_list)

        return kwargs

    def handle_rank_up_notification(self):
        """ handles the conditions to trigger "rank up" notification.
        - if staff pressed "approve"
        - if quest grants xp
        - notify_rank_up conditions (ie. xp is enough to achieve new rank)
        """
        # if approving a sumbission and granting an xp.
        if "approve_button" in self.request.POST and not self.submission.do_not_grant_xp:
            xp = self.submission.xp_requested or self.submission.quest.xp
            notify_rank_up(
                self.submission.user,
                # xp_cached is updated we have to subtract to get old xp
                self.submission.user.profile.xp_cached - xp,
                self.submission.user.profile.xp_cached,
            )

    def save_uploaded_files(self, comment):
        """ saves request files to comment object """
        if self.request.FILES:
            for afile in self.request.FILES.getlist("attachments"):
                newdoc = Document(docfile=afile, comment=comment)
                newdoc.save()

    def handle_award(self):
        """ for each badge in award/awards:
        - create new assertion for student
        - create new message for each assertion for staff
        - add to comment text for each assertion

        """
        # handle badge assertion
        comment_text_addition = ""

        # get list of badges
        badge = self.form.cleaned_data.get("award")
        badges = [badge] if badge else self.form.cleaned_data.get("awards", [])

        for badge in badges:
            # a badge granted alongside a quest counts toward whichever course the student put
            # that quest against, so the badge and the work it recognises land together (#2440)
            new_assertion = BadgeAssertion.objects.create_assertion(
                self.submission.user, badge, self.request.user, course=self.submission.course
            )
            messages.success(
                self.request,
                (
                    "Badge "
                    + str(new_assertion)
                    + " granted to "
                    + str(new_assertion.user)
                ),
            )
            rarity_icon = badge.get_rarity_icon()
            comment_text_addition += (
                "<p></br>"
                + rarity_icon
                + "The <b>"
                + badge.name
                + "</b> badge was granted for this quest "
                + rarity_icon
                + "</p>"
            )

        return comment_text_addition

    # django built-in methods

    @method_decorator(staff_member_required)
    def dispatch(self, request, *args, **kwargs):
        """ requests are only allowed if:
        - POST method
        - optionally POST AJAX method
        """
        # this is a POST only view
        if request.method != "POST":
            raise Http404

        if not self.post_has_valid_button():
            raise Http404("unrecognized submit button")

        self.is_ajax = request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'

        return super().dispatch(request, *args, **kwargs)

    def post(self, request, submission_id, *args, **kwargs):
        self.submission = self.get_submission(submission_id)
        self.form = self.get_form()

        if self.form.is_valid():
            notification_kwargs = self.get_notification_kwargs()

            #
            blank_comment_text = self.handle_form_button(notification_kwargs)
            comment_text_addition = self.handle_award()

            # handle comment text
            # if staff didnt write any text for comment use blank_comment_text
            comment_text = self.form.cleaned_data.get("comment_text")
            if not comment_text or comment_text == "<p><br></p>":
                comment_text = blank_comment_text

            comment_new = Comment.objects.create_comment(
                user=self.request.user,
                path=self.submission.get_absolute_url(),
                text=comment_text + comment_text_addition,
                target=self.submission,
            )

            self.save_uploaded_files(comment_new)

            #
            notify.send(
                self.request.user,
                **notification_kwargs
            )
            self.handle_rank_up_notification()

            messages.success(self.request, format_html(
                "<a href='{}'>Submission of {}</a> {} for <a href='{}'>{}</a>",
                self.submission.get_absolute_url(),
                self.submission.quest.name,
                notification_kwargs["verb"],
                self.submission.user.profile.get_absolute_url(),
                self.submission.user.username,
            ))

            return self.form_valid()
        return self.form_invalid()


#: A returned submission whose `time_returned` was never recorded is treated as very old,
#: so it sorts alongside the oldest rather than jumping to the front of a list ordered by
#: Status. `snippets/submitted_status.html` calls the same case "Unknown time ago".
RETURNED_LONG_AGO = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)


def submission_status_time():
    """The time the Status column shows, as something the database can order by.

    That column shows a different time depending on how far the submission got, following
    the same chain as `quest_manager/snippets/submitted_status.html`: approved shows when
    it was approved, awaiting approval shows when it was handed in, returned shows when it
    was returned, and one still in progress has no time of its own.

    A sort has to read the value the reader is looking at, so this mirrors that chain
    rather than picking a single column and hoping the tab only holds one kind of row.

    Returns:
        Case: the timestamp for each submission, for `order_by`.
    """
    return Case(
        When(is_approved=True, then=F('time_approved')),
        # Reached only when not approved, so this is "awaiting approval"
        When(is_completed=True, then=F('time_completed')),
        # Reached only when not completed, so a time_completed here means it was returned
        When(time_completed__isnull=False, then=Coalesce(F('time_returned'), Value(RETURNED_LONG_AGO))),
        default=Now(),
        output_field=DateTimeField(),
    )


def submission_displayed_xp():
    """The XP the table shows, as something the database can order by.

    The cell shows a different number depending on the submission, following the same
    chain as the two tab templates: a skipped submission grants nothing and shows 0, a
    quest whose XP the student enters shows the amount they asked for, and everything else
    shows the quest's own XP.

    Ordering by `quest__xp` alone would sort by a number that is not on screen for either
    of the first two, which is the same trap the Status column has.

    Returns:
        Case: the XP for each submission, for `order_by`.
    """
    return Case(
        When(do_not_grant_xp=True, then=Value(0)),
        When(quest__xp_can_be_entered_by_students=True, then=F('xp_requested')),
        default=F('quest__xp'),
        output_field=IntegerField(),
    )


def submission_sort_columns(*, campaign=False, user=False, status=True):
    """The columns a submission tab offers, mapped to what the database orders on.

    Two columns are never offered, for the same reason the Library's quests tab does not
    offer its tags (#2410): a submission's {group} blocks and its quest's tags are both
    many-valued, so there is no one value to order a row by, and neither column can keep
    the promise a sort control makes.

    Args:
        campaign (bool): whether this tab shows the quest's campaign.
        user (bool): whether this tab shows whose submission it is.
        status (bool): whether the Status column carries a time. The in-progress tabs show
            no time there, so ordering by it would move nothing and still look like a sort.

    Returns:
        dict: the offered columns, keyed by the key the headings use.
    """
    columns = {
        'name': 'quest__name',
        'xp': submission_displayed_xp(),
    }
    if campaign:
        columns['campaign'] = 'quest__campaign__title'
    if user:
        columns['user'] = 'user__username'
    if status:
        columns['status'] = submission_status_time()

    return columns


def sorted_submission_page(request, submissions, sort_columns, page):
    """Order a tab's submissions by the chosen column, then cut the requested page out.

    Ordering before paginating is the whole point: the browser only ever holds one page,
    so a sort applied there answers a question about the page rather than about the tab
    (#2582). `id` settles submissions that tie, so paging through shows each exactly once.

    Args:
        request (HttpRequest): the current request, for the `sort` parameter.
        submissions (QuerySet[QuestSubmission]): the tab's submissions.
        sort_columns (dict): the columns this tab offers.
        page: the requested page.

    Returns:
        tuple[Page, str, bool]: the page, the column key applied ('' for none), and
        whether it was reversed.
    """
    column, descending = resolve_sort(request, sort_columns)
    submissions = apply_sort(submissions, sort_columns, column, descending, tie_break='id')

    return paginate(submissions, page), column, descending


def paginate(object_list, page, per_page=30):
    paginator = Paginator(object_list, per_page)
    try:
        object_list = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        object_list = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        object_list = paginator.page(paginator.num_pages)
    return object_list


class ApprovalsViewTabTypes:
    """ enum for approvals's tabs.
    Note: using enum.auto() will not work as django template tags cant properly define its value.
    """
    SUBMITTED = 0
    APPROVED = 1
    INPROGRESS = 2
    FLAGGED = 3


@non_public_only_view
@staff_member_required
def approvals(request, quest_id=None, template="quest_manager/quest_approval.html"):
    """A view for Teachers' Quest Approvals section.

    If a quest_id is provided, then filter the queryset to only include
    submissions for that quest.

    Different querysets are generated based on the url. Each with its own tab.
    Currently:
        In progress
        Submitted (i.e. awaiting approval)
        Approved
        Flagged

    """

    # If we are looking up past approvals of a specific quest
    if quest_id:
        quest = get_object_or_404(Quest, id=quest_id)
        if "/all/" in request.path_info:
            active_sem_only = False
            past_approvals_all = True
        else:
            active_sem_only = True
            past_approvals_all = (
                False  # If we are looking at previous approvals of a specific quest
            )
    else:
        quest = None
        past_approvals_all = None
        active_sem_only = True

    if "/all/" in request.path_info:
        current_teacher_only = False
    else:
        current_teacher_only = True

    submitted_submissions = []
    approved_submissions = []
    in_progress_submissions = []
    flagged_submissions = []

    view_type = ApprovalsViewTabTypes.SUBMITTED

    page = request.GET.get("page")
    # The approvals tabs show whose submission it is, and no campaign column. The
    # in-progress tab's Status cell carries no time, so it offers no sort by it.
    sortable_columns = submission_sort_columns(user=True)
    # if '/submitted/' in request.path_info:
    #     approval_submissions = QuestSubmission.objects.all_awaiting_approval()
    if "/in-progress/" in request.path_info:
        view_type = ApprovalsViewTabTypes.INPROGRESS
        sortable_columns = submission_sort_columns(user=True, status=False)
        in_progress_submissions = QuestSubmission.objects.all_not_completed().order_by(F("time_completed").desc(nulls_last=True))
        in_progress_submissions, sort_column, sort_descending = sorted_submission_page(
            request, in_progress_submissions, sortable_columns, page,
        )
    elif "/approved/" in request.path_info:
        view_type = ApprovalsViewTabTypes.APPROVED
        approved_submissions = QuestSubmission.objects.all_approved(
            quest=quest, active_semester_only=active_sem_only
        )
        approved_submissions, sort_column, sort_descending = sorted_submission_page(
            request, approved_submissions, sortable_columns, page,
        )
    elif "/flagged/" in request.path_info:
        view_type = ApprovalsViewTabTypes.FLAGGED
        flagged_submissions = QuestSubmission.objects.flagged(user=request.user)
        flagged_submissions, sort_column, sort_descending = sorted_submission_page(
            request, flagged_submissions, sortable_columns, page,
        )
    else:  # default is /submitted/ (awaiting approval)
        view_type = ApprovalsViewTabTypes.SUBMITTED
        if current_teacher_only:
            teacher = request.user
        else:
            teacher = None
        submitted_submissions = QuestSubmission.objects.all_awaiting_approval(
            teacher=teacher
        )
        submitted_submissions, sort_column, sort_descending = sorted_submission_page(
            request, submitted_submissions, sortable_columns, page,
        )

    tab_list = [
        {
            "name": "In Progress",
            "submissions": in_progress_submissions,
            "active": view_type == ApprovalsViewTabTypes.INPROGRESS,
            "time_heading": "inprogress",
            "url": reverse("quests:in_progress"),
        },
        {
            "name": "Submitted",
            "submissions": submitted_submissions,
            "active": view_type == ApprovalsViewTabTypes.SUBMITTED,
            "time_heading": "Submitted",
            "url": reverse("quests:submitted"),
        },
        {
            "name": "Approved",
            "submissions": approved_submissions,
            "active": view_type == ApprovalsViewTabTypes.APPROVED,
            "time_heading": "Approved",
            "url": reverse("quests:approved"),
        },
        {
            "name": "Flagged",
            "submissions": flagged_submissions,
            "active": view_type == ApprovalsViewTabTypes.FLAGGED,
            "time_heading": "Transferred",
            "url": reverse("quests:flagged"),
        },
    ]

    quick_reply_form = SubmissionQuickReplyForm(request.POST or None)

    # Header button that toggles displaying all quest approvals or only those from groups assigned to the current user
    show_all_blocks_button = True

    grouped_blocks = Block.objects.grouped_teachers_blocks()
    teachers = grouped_blocks.keys()
    # If there is only one user with assigned blocks AND that user is the current user, the header button is redundant and isn't displayed
    if len(teachers) == 1 and list(teachers)[0] == request.user.id:
        show_all_blocks_button = False

    context = {
        "heading": "Quest Approval",
        "tab_list": tab_list,
        "quick_reply_form": quick_reply_form,
        "VIEW_TYPES": ApprovalsViewTabTypes,
        "view_type": view_type,
        "current_teacher_only": current_teacher_only,
        "past_approvals_all": past_approvals_all,
        "quest": quest,
        "quick_reply_text": SiteConfig.get().submission_quick_text,
        "show_all_blocks_button": show_all_blocks_button,
        # Read by snippets/sortable_column_heading.html in the tab's table
        "sortable_columns": sortable_columns,
        "sort_column": sort_column,
        "sort_descending": sort_descending,
    }
    return render(request, template, context)


@non_public_only_view
@staff_member_required
@require_POST
def unarchive(request, quest_id):
    """
    Unarchive a quest by setting `archived=False` and ensure it is unpublished
    so it appears in the Drafts tab.

    This also triggers a recalculation of XP for any users who previously submitted
    this quest, to account for its status change.

    Only staff members can perform this action.

    Args:
        request: The HTTP request object.
        quest_id: The ID of the quest to unarchive.

    Returns:
        HttpResponseRedirect: Redirects to the Drafts tab with a success message.
    """
    # Use get_object_or_404 (not QuerySet.get) so a manually entered/stale quest id
    # returns a clean 404 instead of raising Quest.DoesNotExist as an unhandled 500
    # (issue #1856). all_including_archived() is required because the default manager
    # excludes archived quests -- the only ones this view acts on.
    quest = get_object_or_404(Quest.objects.all_including_archived(), id=quest_id)

    # Make the link that leads to the quests detail page to include in the message
    quest_link = format_html('<a href="{}">{}</a>', quest.get_absolute_url(), quest.name)

    quest.archived = False
    # Make sure the quest goes to the Drafts tab
    quest.published = False
    quest.full_clean()
    quest.save()

    messages.success(request, format_html("Quest '{}' has been unarchived and moved to the Drafts tab.", quest_link))
    # Since the quest is sent to the Drafts tab redirect them there
    return redirect("quests:drafts")


#########################################
#
#   QUEST SUBMISSION - STUDENT VIEWS
#
#########################################
def _keep_posted_uploads(request, form, question_formset, submission, followup=""):
    """Save the POST's uploads that pass their own validation, and tell the student.

    A browser never repopulates a file input, so any response that sends the student back to
    the submission page (the re-render with validation errors, or the questions-changed
    redirect) arrives with every file input empty: without this their uploads are gone with
    nothing to say so (#2165, #2427, #2428). Comment attachments are kept on the draft
    comment and file answers on their draft rows, the same places a successful completion
    publishes them from.

    Validation is run here, because the questions-changed guard calls this before the view
    has validated anything (`is_valid` caches, so it costs nothing where it already ran),
    and only uploads that pass are kept: a file rejected for type or size is dropped so its
    error still applies on the retry.

    Args:
        request: the request, for its FILES and as the messages target.
        form: the bound submission form. Forms without an attachments field keep nothing.
        question_formset: the bound answer formset, or None when the POST involves none.
        submission: the QuestSubmission whose draft comment holds kept attachments.
        followup: an extra sentence for the notice. The re-render path points at its
            inline errors with it; the redirect path passes nothing, since its own error
            message already says what to do next.

    Returns:
        int: how many files were kept.
    """
    form.is_valid()
    kept_files = save_draft_attachments(form, submission.draft_comment)
    if question_formset is not None:
        question_formset.is_valid()
        kept_files += save_draft_file_answers(question_formset, request.FILES)
    if kept_files:
        noun, verb, pronoun = ("file", "was", "it") if kept_files == 1 else ("files", "were", "them")
        messages.info(
            request,
            f"Your attached {noun} {verb} saved, so you don't need to choose {pronoun} again.{followup}",
        )
    return kept_files


@non_public_only_view
@login_required
def complete(request, submission_id):
    """
    When a student has completed a quest, or is commenting on an already completed quest, this view is called
    - The submission is marked as completed (by the student)
    - If the quest is automatically approved, then the submission is also marked as approved
    """
    submission = get_object_or_404(QuestSubmission, pk=submission_id)
    origin_path = submission.get_absolute_url()

    # EARLY EXIT CONDITIONS: ####################

    # Completing publishes the submission's comment and question answers under the owner's name
    # and marks their quest done, so only the owner may do it. Staff act on other students'
    # submissions through the approve view, not this one. Matches submission() and drop().
    if submission.user != request.user and not request.user.is_staff:
        raise Http404("You can only submit your own quests.")

    # This view should only be access when a student submits a submission comment form
    if request.method != "POST":
        raise Http404

    # for some reason Summernote is submitting the form in the background when an image is added or
    # dropped into the widget We need to ignore that submission
    # https://github.com/summernote/django-summernote/issues/362
    if "complete" not in request.POST and "comment" not in request.POST:
        raise Http404("unrecognized submit button")

    # if no comment and not completed, quest did not come from submission view
    if not submission.is_completed and not submission.draft_comment:
        raise Http404("no comment found")

    # There's a bug where somehow is_approved = True but the POST request contains xp_requested data.
    # Not sure how this happens, but need to throw an error when it does so we don't accidentally overwright the
    # approved XP value for this submission.
    if submission.is_approved and request.POST.get("xp_requested"):
        return HttpResponseForbidden(
            "This quest has already been approved. Cannot modify XP on an already approved submission. \n\n"
            "To modify the XP granted by this submission the teacher must return it to the student, then the student"
            "can resubmit it with different amount of XP requested."
        )

    # END EARLY EXIT CONDITIONS ####################

    # Figure out what Form we are using

    student_can_enter_xp = submission.quest.xp_can_be_entered_by_students and not submission.is_approved

    # the student's own courses, so the form can ask which one this counts toward (#2440)
    if student_can_enter_xp:
        form = SubmissionFormCustomXP(request.POST, request.FILES, student=submission.user)
    elif request.FILES:  # if there are files, we need to use the full form
        form = SubmissionForm(request.POST, request.FILES, student=submission.user)
    else:
        form = SubmissionQuickReplyFormStudent(request.POST, student=submission.user)

    # The quest's questions, bound to this POST as an answer formset over the submission's
    # draft rows. Only the "complete" action on a not-yet-completed submission involves the
    # formset: commenting ("comment" button) never does, and a duplicate "complete" POST
    # (browser back button) must not spawn fresh draft rows on a completed submission.
    question_formset = None
    if "complete" in request.POST and not submission.is_completed and submission.quest.question_set.exists():
        draft_rows = sync_draft_question_submissions(submission)
        question_formset = QuestionSubmissionFormsetFactory(
            request.POST, request.FILES,
            instance=submission, queryset=draft_rows,
        )

        # The management form is client-controlled: a tampered TOTAL_FORMS/INITIAL_FORMS (or a
        # stale page from before the quest's questions changed) can present fewer answer forms
        # than the quest has questions. Without this guard those omitted questions are never
        # validated yet still published (the blanket publish below), so required questions
        # could be bypassed — completing/auto-approving a quest with nothing answered. Require
        # the POST to cover exactly the quest's current questions; otherwise bounce back to a
        # freshly-built page that shows them all.
        expected_ids = set(draft_rows.values_list("pk", flat=True))
        posted_ids = {f.instance.pk for f in question_formset.forms if f.instance.pk}
        if posted_ids != expected_ids:
            messages.error(
                request,
                "This quest's questions have changed since you opened this page. "
                "Please review and answer them, then submit again.",
            )
            # The redirect rebuilds the page with empty file inputs, so keep the uploads
            # that validate, just as the validation-failure path below does (#2428).
            _keep_posted_uploads(request, form, question_formset, submission)
            return redirect(origin_path)

    if not form.is_valid() or (question_formset and not question_formset.is_valid()):
        # The main form path should only occur if a student tries to use the quick reply form
        # on a quest that has `xp_can_be_entered_by_student`; re-rendering shows the full form
        # so they can enter XP. The formset path re-renders with each question's errors visible.

        # Keep the uploads that did validate, both the comment's attachments and the file
        # answers, since the re-rendered file inputs come back empty and the student would
        # otherwise lose them with no warning (#2165, #2427).
        _keep_posted_uploads(
            request, form, question_formset, submission,
            followup=" Fix the problems below and submit the quest again.",
        )

        context = {
            "heading": submission.quest.name,
            "submission": submission,
            "q": submission.quest,  # allows for common data to be displayed on sidebar more easily...
            "submission_form": form,
            "question_formset": question_formset,
            "anchor": "submission-form-" + str(submission.quest.id),
        }
        return render(request, "quest_manager/submission.html", context)

    # else form (and answer formset, if any) is valid:

    comment_text = form.cleaned_data.get("comment_text")

    # Whether the student actually answered at least one question (a BaseFormSet is always
    # truthy, so `if question_formset:` alone would treat a set of only-blank optional
    # answers as content and wrongly bypass the verification-required check below).
    answered_a_question = bool(question_formset) and any(
        f.cleaned_data.get("response_text") or f.cleaned_data.get("response_file")
        for f in question_formset.forms
    )

    # If the student didn't leave a comment (or the default html from summernote <p><br></p>)
    # then need to check if we should bother handling this form submission
    if not comment_text or comment_text == "<p><br></p>":

        # If the student answered at least one question, those answers are the submission's
        # content, so don't demand an additional comment or attachment on top of them.
        if answered_a_question:
            comment_text = "(submitted without comment)"
        # If the `verification_required` flag is set, then the teacher is expecting either
        # a comment or a file (something to check).  We already know there isn't a comment
        # so check for files.
        elif submission.quest.verification_required and not request.FILES:
            messages.error(
                request,
                "Please read the Submission Instructions more carefully.  "
                "You are expected to attach something or comment to complete this quest!",
            )
            return redirect(origin_path)
        # If this form is being used to add a comment to an already completed quest, then
        # we need to make sure the student atually left a comment
        elif "comment" in request.POST and not request.FILES:
            messages.error(request, "Please leave a comment.")
            return redirect(origin_path)
        # else none of these are true, then add some default text to the blank comment
        # this could happen for example, if he quest is automatically approved, or if they added a file
        # instead of commenting.
        else:
            comment_text = "(submitted without comment)"

    xp_requested = 0
    # If custom XP, then we need to get the XP value and append it to the comment.
    if isinstance(form, SubmissionFormCustomXP):
        xp_requested = form.cleaned_data.get("xp_requested")
        comment_text += f"<ul><li><b>XP requested: {xp_requested}</b></li></ul>"

    # The submission's draft_comment property (a Comment object) is used to save a new comment
    # at the end of this view when `mark_completed` is called on the submission,
    # so make sure the draft comment is set properly with the form's latest comment text.
    draft_comment = submission.draft_comment
    draft_text = f"<p>{comment_text}</p>"
    if draft_comment:
        # update all comment fields
        draft_comment.text = draft_text
        draft_comment.target_object_id = submission.id
        draft_comment.target_object = submission
        # reset timestamp needed otherwise it will use the draft comment's timestamp from when the submission was started
        draft_comment.timestamp = timezone.now()
        draft_comment.full_clean()
        draft_comment.save()

    # this is for quick_reply comments
    # if draft comment was removed. make a new comment object for submission
    else:
        draft_comment = Comment.objects.create_comment(
            user=request.user,
            path=submission.get_absolute_url(),
            text=draft_text,
            target=submission,
        )

    # Create Document objects and connect them to the comment for uploaded files
    if request.FILES:
        for afile in request.FILES.getlist("attachments"):
            newdoc = Document(docfile=afile, comment=draft_comment)
            newdoc.full_clean()
            newdoc.save()

    affected_users = []

    # Two possibilities, the student is either completing the quest ("complete" button) or commenting on an already
    # completed quest ("comment" button).
    if "complete" in request.POST:
        if question_formset:
            # Persist the answers, then publish them with the completion comment. Rows whose
            # question was deleted stay unpublished (and invisible) rather than blocking.
            question_formset.save()
            QuestionSubmission.objects.filter(
                quest_submission=submission, comment__isnull=True, question__isnull=False
            ).update(comment=draft_comment)

        note_verb = "completed"
        msg_text = "Quest completed"

        if submission.quest.verification_required:
            msg_text += ", awaiting approval."
        else:
            note_verb += " (auto-approved quest)"
            msg_text += " and automatically approved."
            msg_text += " Please give me a moment to calculate what new quests this should make available to you."
            # format_html so the break renders: everything appended above is plain text, which
            # a message escapes, and the deck AI's name is escaped as an argument.
            msg_text = format_html(
                "{} Try refreshing your browser in a few moments. Thanks! <br>{}",
                msg_text, SiteConfig.get().deck_ai,
            )

        icon = "<i class='fa fa-shield fa-lg'></i>"

        # Send notification to current teachers when a comment is left on an auto-approved quest
        # since these quests don't appear in the approvals tab, teacher would never know about the comment.
        if (
            form.cleaned_data.get("comment_text")
            and not submission.quest.verification_required
        ):
            affected_users.extend(request.user.profile.current_teachers())

        # Record which course the student said this counts toward, before the XP is granted so
        # an auto-approved quest lands in the right course straight away (issue #2440).
        # Assigned whatever they picked, "split evenly" (None) included: a submission a teacher
        # returned carries its earlier choice, and redoing it has to be able to change that
        # choice back. The form is seeded with the current course, so this writes back what the
        # student was actually shown.
        submission.course = form.cleaned_data.get('course')

        submission.mark_completed(xp_requested)
        if not submission.quest.verification_required:
            submission.mark_approved()

            # mark_approved() just set do_not_grant_xp to False (its transfer arg defaults to
            # False), so this is always true on the auto-approve path; the skip-notify branch
            # is unreachable here.
            if not submission.do_not_grant_xp:  # pragma: no branch
                # if not requesting xp, xp_requested will default to 0
                # 0 or xp = xp
                xp = xp_requested or submission.quest.xp
                notify_rank_up(
                    submission.user,
                    # subtract from cache as mark_approved updates xp
                    submission.user.profile.xp_cached - xp,
                    submission.user.profile.xp_cached,
                )

    # The early-exit guard above raises Http404 unless "complete" or "comment" is in POST, so
    # when the "complete" branch is not taken this elif always matches; the no-match
    # fall-through (the redundant else noted below) is unreachable.
    elif "comment" in request.POST:  # pragma: no branch
        note_verb = "commented on"
        msg_text = "Quest commented on."
        icon = (
            "<span class='fa-stack'>"
            + "<i class='fa fa-shield fa-stack-1x'></i>"
            + "<i class='fa fa-comment-o fa-stack-2x text-info'></i>"
            + "</span>"
        )
        affected_users = []
        if request.user.is_staff:
            affected_users = [
                submission.user,
            ]
        else:  # student comment
            # student's teachers
            affected_users.extend(
                request.user.profile.current_teachers()
            )  # User.objects.filter(is_staff=True)
            # add quest's teacher if necessary
            if submission.quest.specific_teacher_to_notify:
                affected_users.append(
                    submission.quest.specific_teacher_to_notify
                )

            # if commenting after approval we have to remove draft_comment
            # else drafts get "stuck" to same comment
            submission.draft_comment = None
            submission.save()

    # else:  # this case is already covered at the top of the view and thus redundant
    #     raise Http404("unrecognized submit button")

    notify.send(
        request.user,
        action=draft_comment,
        target=submission,
        recipient=submission.user,
        affected_users=set(affected_users),  # remove doubles/flatten
        verb=note_verb,
        icon=icon,
    )
    messages.success(request, msg_text)
    return redirect("quests:quests")


@non_public_only_view
@login_required
def start(request, quest_id):
    quest = get_object_or_404(Quest, pk=quest_id)

    if not quest.is_available(request.user):
        # check if it's not available because they already have a submission in progress
        sub = (
            QuestSubmission.objects.all_not_completed(request.user)
            .filter(quest_id=quest_id)
            .first()
        )
        if not sub:
            # They're trying to start a quest they don't have access too. This
            # could happen if they manually enter a different quest.id in the start url
            raise Http404
        else:
            # We found an in-progress/not completed submission for the quest, so send them to it
            # instead of starting a new one, and let them know why (issue #57).
            messages.info(
                request,
                format_html(
                    "You already have <strong>{}</strong> in progress: "
                    "finish this one before starting it again.",
                    quest.name,
                ),
            )
            return redirect(sub)
    else:
        new_sub = QuestSubmission.objects.create_submission(request.user, quest)
        return redirect(new_sub)


@non_public_only_view
@login_required
def hide(request, quest_id):
    quest = get_object_or_404(Quest, pk=quest_id)
    request.user.profile.hide_quest(quest_id)

    messages.warning(
        request,
        format_html("<strong>{}</strong> has been added to your list of hidden quests.", quest.name),
    )

    return redirect("quests:quests")


@non_public_only_view
@login_required
def unhide(request, quest_id):
    quest = get_object_or_404(Quest, pk=quest_id)
    request.user.profile.unhide_quest(quest_id)

    messages.success(
        request,
        format_html("<strong>{}</strong> has been removed from your list of hidden quests.", quest.name),
    )

    return redirect("quests:available_all")


@login_required
@require_POST
def skip(request, submission_id):
    """Approve a submission as a transfer: complete and approved, but worth no XP.

    Limited to staff and to a student marked as not earning XP acting on their own
    submission, so a student cannot skip a quest by guessing the url. POST-only, because it
    approves the quest outright (#2383).

    Args:
        request: the HttpRequest; must be a POST.
        submission_id: the id of the QuestSubmission to transfer.

    Returns:
        An HttpResponseRedirect to the approvals queue for staff, or to the student's quests.

    Raises:
        Http404: when the requester may not skip this submission.
    """
    submission = get_object_or_404(QuestSubmission, pk=submission_id)
    # student can only do this if the button is turned on by a teacher
    # prevent students form skipping by guessing correct url
    # also make sure it's the student who owns the submission
    if (
        request.user.profile.not_earning_xp and submission.user == request.user
    ) or request.user.is_staff:
        # add default comment to submission
        # origin_path = submission.get_absolute_url()
        # comment_text = "(Quest skipped - no XP granted)"
        # comment_new = Comment.objects.create_comment(
        #     user=request.user,
        #     path=origin_path,
        #     text=comment_text,
        #     target=submission,
        # )

        # The quest is being waived, so any answers the student drafted will never be submitted
        # and nothing renders them; drop them rather than leave invisible rows behind (#2164).
        # In one transaction with the approval that justifies it, so a failure part way through
        # (marking approved also grants badges and recalculates XP) cannot leave the answers
        # deleted on a submission that was never transferred.
        with transaction.atomic():
            discard_draft_question_submissions(submission)

            draft_comment = submission.draft_comment

            # approve quest automatically, and mark as transfer.
            submission.mark_completed()
            submission.mark_approved(transfer=True)

            # mark_completed() clears the draft comment because completing publishes it first.
            # Skipping publishes nothing, so hand it back: a transferred quest can still be
            # commented on, and the student keeps whatever they had typed (with anything attached
            # to it) ready to post. This is how the staff skip button already leaves it (#2431).
            if draft_comment:
                submission.draft_comment = draft_comment
                submission.save()

        messages.success(
            request, ("Transfer Successful.  No XP was granted for this quest.")
        )
        if request.user.is_staff:
            return redirect("quests:approvals")
        return redirect("quests:quests")
    else:
        raise Http404


@non_public_only_view
@login_required
@require_POST
def skipped(request, quest_id):
    """Skip a quest the student never started: start it, then transfer it.

    A combination of the start and complete views, but automatically approved regardless,
    and do_not_grant_xp = True. POST-only, since it both creates a submission and approves
    it (#2383).

    Args:
        request: the HttpRequest; must be a POST.
        quest_id: the id of the Quest to start and transfer.

    Returns:
        The HttpResponseRedirect from :func:`skip`, which handles the approval.
    """
    quest = get_object_or_404(Quest, pk=quest_id)
    # create_submission always returns a submission: a new in-progress one, or the
    # existing in-progress submission when the quest was already started (issue #1345).
    submission = QuestSubmission.objects.create_submission(request.user, quest)
    return skip(request, submission.id)


@xml_http_request_required
@non_public_only_view
@login_required
def ajax_save_draft(request):
    """Autosave the requesting student's own draft comment, answers, and chosen files.

    Scoped to the submission's owner: a draft is the student's own work in progress, and
    the draft form is only ever rendered for them (staff get the marking form instead), so
    any other user's submission id is a 404.

    The POST carries `submission_id`, the comment HTML as `comment`, text answers as an
    `answers` JSON object of the formset's field names, and, when files were chosen, the
    formset's own fields (management form, row ids, files) plus the comment's
    `attachments`, as the page sends the whole form as FormData (#1459).

    Returns a JSON object: `result` ("Draft saved" or "No changes"), and, when the POST
    carried files, `saved_answer_files` (file field name to the stored file's bare name),
    `saved_attachments` (the accepted upload names), and `file_errors` (field name to the
    validation message for a rejected file).
    """
    if request.POST:
        response_data = {
            "result": "No changes",
        }

        submission_comment = request.POST.get("comment")
        # the id is client-supplied: a missing or non-numeric one would raise ValueError
        # in the pk lookup below (a 500), so turn it away as a 404 first.
        try:
            submission_id = int(request.POST.get("submission_id", ""))
        except (TypeError, ValueError):
            raise Http404("No valid submission id provided.")
        # xp_requested = request.POST.get('xp_requested')

        sub = get_object_or_404(QuestSubmission, pk=submission_id, user=request.user)
        # if there is no draft comment, then the quest is not in progress
        if not sub.draft_comment:
            raise Http404("No draft comment found. The quest is not in progress.")

        draft_comment = sub.draft_comment

        if submission_comment is not None and draft_comment.text != submission_comment:
            draft_comment.text = submission_comment
            # sub.xp_requested = xp_requested
            response_data["result"] = "Draft saved"
            draft_comment.save()

        # Autosave draft answers to the quest's questions. Text answers arrive as a JSON
        # object of the formset's field names, pairing each row's hidden id with its
        # response_text; file answers arrive in request.FILES and are handled below.
        answers_json = request.POST.get("answers")
        if answers_json and sub.quest.question_set.exists():
            try:
                answers = json.loads(answers_json)
            except ValueError:
                answers = {}
            # the payload is client-controlled: a valid-JSON scalar/list (e.g. "5" or [])
            # would blow up on .items() below, so coerce anything but an object to empty.
            if not isinstance(answers, dict):
                answers = {}

            rows = {}  # formset index -> {'id': ..., 'response_text': ...}
            for key, value in answers.items():
                match = re.match(r"^question_submissions-(\d+)-(id|response_text)$", key)
                if match:
                    rows.setdefault(match.group(1), {})[match.group(2)] = value

            for row_data in rows.values():
                text = row_data.get("response_text")
                if text is None:
                    continue
                # the id is also client-supplied; a non-integer would make the pk lookup
                # below raise ValueError (a 500), so skip rows without a usable integer id.
                try:
                    row_id = int(row_data["id"])
                except (KeyError, TypeError, ValueError):
                    continue
                # only this submission's own unpublished rows can be draft-saved.
                # Sanitize on write: this raw draft is published verbatim on completion
                # (the blanket publish below doesn't re-clean unchanged rows) and rendered
                # with |safe in the marking display, so an unsanitized draft would be
                # stored XSS against the marker (issues #1343 / #2113).
                text = sanitize_comment_html(text)
                # Only text-answer rows autosave: a crafted request could otherwise stash
                # response_text on a file-upload row, which completion would then count as
                # submission content, letting a student bypass the "attach or comment" gate
                # without actually uploading the required file.
                row = QuestionSubmission.objects.filter(
                    pk=row_id, quest_submission=sub, comment__isnull=True,
                    question__type__in=(QuestionType.SHORT_ANSWER, QuestionType.LONG_ANSWER),
                ).first()
                if row and row.response_text != text:
                    row.response_text = text
                    row.full_clean()
                    row.save()
                    response_data["result"] = "Draft saved"

        # Draft-save any files in the POST (#1459). The Save Draft button posts the whole
        # form as FormData, so a chosen comment attachment or file answer arrives here just
        # as it would on submit, is validated by the same forms, and is stored by the same
        # helpers in the same places (the draft comment, the draft rows): a draft-saved
        # file and one kept from a failed submit are indistinguishable, and both publish
        # with the completion. The response names what was saved and what was rejected, so
        # the page can clear those inputs and show the outcome without a reload.
        if request.FILES:
            saved_answer_files = {}
            saved_attachments = []
            file_errors = {}

            if sub.quest.question_set.exists():
                question_formset = QuestionSubmissionFormsetFactory(
                    request.POST, request.FILES,
                    instance=sub, queryset=sync_draft_question_submissions(sub),
                )
                # Validate so the per-form errors below are populated. A hand-built POST
                # that omits the management form does not raise here: Django records a
                # non-form error and the formset has no forms, so the loop below does
                # nothing and the text answers (above) still save.
                question_formset.is_valid()
                save_draft_file_answers(question_formset, request.FILES)
                for answer_form in question_formset.forms:
                    field_name = answer_form.add_prefix("response_file")
                    if field_name not in request.FILES:
                        continue
                    # errors first: a row that already holds a file from an earlier save
                    # keeps it when a replacement is rejected, and reporting that stored
                    # file as "saved" would present the rejection as a success
                    if answer_form.errors.get("response_file"):
                        file_errors[field_name] = " ".join(answer_form.errors["response_file"])
                    elif answer_form.instance.pk and answer_form.instance.response_file:
                        # the bare file name: the stored value is a whole media path
                        saved_answer_files[field_name] = posixpath.basename(str(answer_form.instance.response_file))

            if request.FILES.getlist("attachments"):
                # the same form the submit builds, so the same size and count rules apply
                form = SubmissionForm(request.POST, request.FILES, student=request.user)
                form.is_valid()
                saved_attachments = [upload.name for upload in accepted_attachments(form)]
                save_draft_attachments(form, draft_comment)
                if form.errors.get("attachments"):
                    file_errors["attachments"] = " ".join(form.errors["attachments"])

            if saved_answer_files or saved_attachments:
                response_data["result"] = "Draft saved"
            response_data["saved_answer_files"] = saved_answer_files
            response_data["saved_attachments"] = saved_attachments
            response_data["file_errors"] = file_errors

        return HttpResponse(json.dumps(response_data), content_type="application/json")

    else:
        raise Http404


@non_public_only_view
@login_required
def drop(request, submission_id):
    # Submission should only be droppable when quest is still not approved
    try:
        sub = QuestSubmission.objects.get(pk=submission_id, is_approved=False)
    except QuestSubmission.DoesNotExist:
        sub = get_object_or_404(
            QuestSubmission.objects.all_completed(request.user).filter(
                is_approved=False
            ),
            pk=submission_id,
        )

    template_name = "quest_manager/questsubmission_confirm_delete.html"
    if sub.user != request.user and not request.user.is_staff:
        return redirect("quests:quests")
    if request.method == "POST":
        if sub.draft_comment:
            sub.draft_comment.delete()
        sub.delete()
        messages.error(request, ("Quest dropped."))
        return redirect("quests:quests")
    return render(request, template_name, {"submission": sub})


@non_public_only_view
@login_required
def submission(request, submission_id=None, quest_id=None):
    try:
        sub = QuestSubmission.objects.get(pk=submission_id)
    except QuestSubmission.DoesNotExist:
        # Student might have completed the submission and suddenly quest became unavailable
        # So, we'll take a look at their completed quests instead
        sub = get_object_or_404(
            QuestSubmission.objects.all_completed(request.user), pk=submission_id
        )

    if sub.user != request.user and not request.user.is_staff:
        return redirect("quests:quests")

    question_formset = None

    if request.user.is_staff:
        # Staff form has additional fields such as award granting.
        main_comment_form = SubmissionFormStaff()

    else:
        draft_comment = sub.draft_comment
        # if there is no draft comment, create one.
        if not draft_comment:
            text = ""
            draft_comment = Comment.objects.create_comment(
                user=request.user,
                path=sub.get_absolute_url(),
                text=text,
                target=None
            )
            sub.draft_comment = draft_comment
            sub.save()

        # show the course this already counts toward, so a student returning to the page sees
        # their earlier choice rather than the form offering to reset it (issue #2440)
        initial = {"comment_text": sub.draft_comment.text, "course": sub.course}
        if sub.quest.xp_can_be_entered_by_students and not sub.is_approved:
            # Use the xp requested from the submission. Default to quest xp
            initial["xp_requested"] = sub.xp_requested or sub.quest.xp
            main_comment_form = SubmissionFormCustomXP(initial=initial,
                                                       minimum_xp=sub.quest.xp,
                                                       student=request.user)
        else:
            main_comment_form = SubmissionForm(initial=initial, student=request.user)

        # The quest's questions, as an answer formset over this submission's draft rows.
        # Only while the submission can still be worked on; answers on completed/approved
        # submissions are published and shown with their comment instead.
        if not sub.is_completed and not sub.is_approved and sub.quest.question_set.exists():
            question_formset = QuestionSubmissionFormsetFactory(
                instance=sub, queryset=sync_draft_question_submissions(sub)
            )

    context = {
        "heading": sub.quest_name(),
        "submission": sub,
        "q": sub.quest,  # allows for common data to be displayed on sidebar more easily...
        "submission_form": main_comment_form,
        "question_formset": question_formset,
        # "reply_comment_form": reply_comment_form,
        "quick_reply_text": SiteConfig.get().submission_quick_text,
        # A quest can become unpublished (drafted) after a student has already submitted it.
        # The student can still open the submission to review their past work, but the submission
        # form is useless (it has no submit button) and confusing (issue #798), so the template
        # hides the form and shows a "no longer available" notice instead. Staff keep the form so
        # they can still manage the submission. (Archived quests are already unreachable here -- the
        # QuestSubmission manager excludes them from this view entirely, so they 404, which matches
        # the "no longer viewable" fallback the issue accepts for the archived case.)
        "quest_no_longer_available": not sub.quest.published,
    }
    return render(request, "quest_manager/submission.html", context)


@xml_http_request_required
@non_public_only_view
@login_required
def ajax_submission_count(request):
    """Returns the number of submissions awaiting approval for the current user
    This is used to update the number beside the "Approvals" button in the navbar"""
    if request.method == "POST":
        submission_count = QuestSubmission.objects.all_awaiting_approval(
            teacher=request.user
        ).count()

        return JsonResponse(data={"count": submission_count})
    else:
        raise Http404


########################
#
# FLAGGED SUBMISSIONS
#
########################


@non_public_only_view
@staff_member_required
def flag(request, submission_id):
    sub = get_object_or_404(QuestSubmission, pk=submission_id)

    # record who raised the flag, so it is attributable on a deck with several teachers
    sub.flagged_by = request.user
    sub.save()

    messages.success(request, "Submission flagged for future follow up.")

    return redirect("quests:approvals")


@xml_http_request_required
@non_public_only_view
@staff_member_required
def ajax_flag(request):
    if request.method == "POST":
        submission_id = request.POST.get("submission_id", None)
        sub = QuestSubmission.objects.get(id=submission_id)
        sub.flagged_by = request.user
        sub.save()
        return JsonResponse(data={})
    else:
        raise Http404


@non_public_only_view
@staff_member_required
def unflag(request, submission_id):
    sub = get_object_or_404(QuestSubmission, pk=submission_id)

    sub.flagged_by = None
    sub.save()

    messages.success(
        request,
        format_html(
            "Submission <a href='{}'>{} by {}</a> has been unflagged.",
            sub.get_absolute_url(), sub.quest_name(), sub.user,
        ),
    )

    return redirect("quests:approvals")
