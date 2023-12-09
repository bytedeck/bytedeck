import json
import uuid

from django.utils.decorators import method_decorator
from django.views.generic.list import ListView

import numpy as np

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import F, ExpressionWrapper, fields
from django.db.models import BooleanField, Exists, OuterRef
from django.http import HttpResponse, JsonResponse
from django.shortcuts import Http404, get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.views.generic import DetailView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from hackerspace_online.decorators import staff_member_required

from badges.models import BadgeAssertion
from comments.models import Comment, Document
from courses.models import Block
from notifications.signals import notify
from prerequisites.views import ObjectPrereqsFormView
from siteconfig.models import SiteConfig
from tenant.views import NonPublicOnlyViewMixin, non_public_only_view

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

User = get_user_model()


def is_staff_or_TA(user):
    if user.is_staff:
        return True

    try:
        if user.profile.is_TA:
            return True
    except (
        AttributeError
    ):  # probably because the user is not logged in, so AnonymousUser and has no profile
        pass

    return False


@method_decorator(staff_member_required, name="dispatch")
class CategoryList(NonPublicOnlyViewMixin, LoginRequiredMixin, ListView):
    model = Category


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

        Returns a dictionary containing default context info as well as a queryset that contains the
        appropriate quests a user will see; "category_displayed_quests".
        """
        if self.request.user.is_staff:
            kwargs["category_displayed_quests"] = Quest.objects.filter(
                campaign=self.object
            )
        else:
            # students shouldn't be able to see inactive quests when they access this view
            # filtering before calling get_active, while likely less costly, changes the object
            # from type QuestManager to a QuestQueryset, which doesn't have the get_active method
            kwargs["category_displayed_quests"] = Quest.objects.get_active().filter(
                campaign=self.object
            )

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name="dispatch")
class CategoryCreate(NonPublicOnlyViewMixin, CreateView):
    fields = ("title", "icon", "active")
    model = Category
    success_url = reverse_lazy("quests:categories")

    def get_context_data(self, **kwargs):
        kwargs["heading"] = "Create New Campaign"
        kwargs["submit_btn_value"] = "Create"

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name="dispatch")
class CategoryUpdate(NonPublicOnlyViewMixin, UpdateView):
    fields = ("title", "icon", "active")
    model = Category
    success_url = reverse_lazy("quests:categories")

    def get_context_data(self, **kwargs):
        kwargs["heading"] = "Update Campaign"
        kwargs["submit_btn_value"] = "Update"

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name="dispatch")
class CategoryDelete(NonPublicOnlyViewMixin, DeleteView):
    model = Category
    success_url = reverse_lazy("quests:categories")


class QuestDelete(NonPublicOnlyViewMixin, UserPassesTestMixin, DeleteView):
    def test_func(self):
        return self.get_object().is_editable(self.request.user)

    model = Quest
    success_url = reverse_lazy("quests:quests")

    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class QuestFormViewMixin:
    """Data and methods common to QuestCreateView, QuestUpdateView, and QuestCopyView"""

    model = Quest

    def form_valid(self, form):
        # TA created quests should not be visible to students.
        if self.request.user.profile.is_TA:
            form.instance.visible_to_students = False
            form.instance.editor = self.request.user
        # When a teacher makes a form visible, remove editor abilities.
        elif form.instance.visible_to_students:
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


class QuestCreate(
    NonPublicOnlyViewMixin, UserPassesTestMixin, QuestFormViewMixin, CreateView
):
    def test_func(self):
        return is_staff_or_TA(self.request.user)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super().get_context_data(**kwargs)
        context["heading"] = "Create New Quest"
        context["cancel_url"] = reverse("quests:quests")
        context["submit_btn_value"] = "Create"
        return context


class QuestUpdate(
    NonPublicOnlyViewMixin, UserPassesTestMixin, QuestFormViewMixin, UpdateView
):
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
        kwargs["initial"]["tags"] = copied_quest.tags.all()
        kwargs["initial"]["new_quest_prerequisite"] = copied_quest

        new_quest = get_object_or_404(Quest, pk=self.kwargs["quest_id"])
        new_quest.pk = None  # autogen a new primary key (quest_id by default)
        new_quest.import_id = uuid.uuid4()
        new_quest.name = new_quest.name + " - COPY"

        kwargs["instance"] = new_quest
        return kwargs


class QuestSubmissionSummary(DetailView, UserPassesTestMixin):
    model = Quest
    context_object_name = "quest"
    template_name = "quest_manager/summary.html"

    def test_func(self):
        return is_staff_or_TA(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        subs = self.object.questsubmission_set.exclude(time_approved=None)
        latest_submission_time = subs.latest("time_approved").time_approved
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


@non_public_only_view
@login_required
def ajax_summary_histogram(request, pk):
    if request.is_ajax():
        max = int(request.GET.get("max", 60))
        min = int(request.GET.get("min", 1))

        quest = get_object_or_404(Quest, pk=pk)

        minutes_list = get_minutes_to_complete_list(quest)

        np_data = np.array(minutes_list)
        # remove outliers
        np_data = np_data[(np_data >= min) & (np_data < max + 1)]
        # sort values
        np_data = np.sort(np_data)

        histogram_values, histogram_labels = get_histogram(np_data, min, max)

        size = np_data.size
        mean = float(np.mean(np_data))
        data = {
            "histogram_values": histogram_values.tolist(),
            "histogram_labels": histogram_labels[:-1].tolist(),
            "count": size,
            "mean": mean,
            "percentile_50": int(np.median(np_data)),
            "percentile_25": int(np_data[size // 4]) if size else None,
            "percentile_75": int(np_data[size * 3 // 4]) if size else None,
        }

        return JsonResponse(data)

    else:
        raise Http404


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


@non_public_only_view
@login_required
def quest_list(request, quest_id=None, template="quest_manager/quests.html"):
    available_quests = []
    in_progress_submissions = []
    completed_submissions = []
    past_submissions = []
    draft_quests = []

    available_tab_active = False
    in_progress_tab_active = False
    completed_tab_active = False
    past_tab_active = False
    drafts_tab_active = False
    remove_hidden = True

    active_quest_id = 0

    # Figure out what tab we want.
    if quest_id is not None:
        # if a quest_id was provided, got to the Available tab
        active_quest_id = int(quest_id)
        available_tab_active = True
    # otherwise look at the path
    elif "/inprogress/" in request.path_info:
        in_progress_tab_active = True
    elif "/completed/" in request.path_info:
        completed_tab_active = True
    elif "/past/" in request.path_info:
        past_tab_active = True
    elif "/drafts/" in request.path_info:
        drafts_tab_active = True
    else:
        available_tab_active = True
        if "/all/" in request.path_info:
            remove_hidden = False

    page = request.GET.get("page")

    # Quest and Submission Querysets (in order of tabs =)
    if request.user.is_staff:
        available_quests = (
            Quest.objects.all()
            .visible()
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

    in_progress_submissions = QuestSubmission.objects.all_not_completed(
        request.user, blocking=True
    )
    completed_submissions = QuestSubmission.objects.all_completed(request.user)
    past_submissions = QuestSubmission.objects.all_completed_past(request.user)
    draft_quests = Quest.objects.all_drafts(request.user)

    # Counts
    in_progress_submissions_count = in_progress_submissions.count()
    completed_submissions_count = completed_submissions.count()
    past_submissions_count = past_submissions.count()
    drafts_count = draft_quests.count()
    available_quests_count = (
        len(available_quests)
        if type(available_quests) is list
        else available_quests.count()
    )

    quick_reply_form = SubmissionQuickReplyFormStudent(request.POST or None)

    if in_progress_tab_active:
        in_progress_submissions = paginate(in_progress_submissions, page)
        # available_quests = []
    elif completed_tab_active:
        # completed_submissions_count = completed_submissions.count()
        completed_submissions = paginate(completed_submissions, page)
        # available_quests = []
    elif past_tab_active:
        past_submissions = paginate(past_submissions, page)
        # available_quests = []

    # Used to explain why the "Available" tab is empty, if it is
    awaiting_approval = QuestSubmission.objects.filter(
        user=request.user, is_approved=False, is_completed=True
    ).exists()

    context = {
        "heading": "Quests",
        "awaiting_approval": awaiting_approval,
        "available_quests": available_quests,
        "remove_hidden": remove_hidden,
        "num_available": available_quests_count,
        "in_progress_submissions": in_progress_submissions,
        "num_inprogress": in_progress_submissions_count,
        "completed_submissions": completed_submissions,
        "draft_quests": draft_quests,
        "num_drafts": drafts_count,
        "past_submissions": past_submissions,
        "num_past": past_submissions_count,
        "num_completed": completed_submissions_count,
        "active_q_id": active_quest_id,
        "available_tab_active": available_tab_active,
        "inprogress_tab_active": in_progress_tab_active,
        "completed_tab_active": completed_tab_active,
        "past_tab_active": past_tab_active,
        "drafts_tab_active": drafts_tab_active,
        "quick_reply_form": quick_reply_form,
    }
    return render(request, template, context)


@non_public_only_view
@login_required
def ajax_quest_info(request, quest_id=None):
    if request.is_ajax() and request.method == "POST":
        template = "quest_manager/preview_content_quests_avail.html"

        if quest_id:
            quest = get_object_or_404(Quest, pk=quest_id)

            template = "quest_manager/preview_content_quests_avail.html"
            quest_info_html = render_to_string(template, {"q": quest}, request=request)

            data = {
                "quest_info_html": quest_info_html
            }

            # JsonResponse new in Django 1.7 is equivalent to:
            # return HttpResponse(json.dumps(data), content_type='application/json')
            return JsonResponse(data)

        else:  # all quests, used for staff only.
            quests = Quest.objects.all()
            all_quest_info_html = {}

            for q in quests:
                all_quest_info_html[q.id] = render_to_string(
                    template, {"q": q}, request=request
                )

            data = json.dumps(all_quest_info_html)
            return JsonResponse(data, safe=False)

    else:
        raise Http404


@non_public_only_view
@login_required
def ajax_approval_info(request, submission_id=None):
    if request.is_ajax() and request.method == "POST":
        qs = QuestSubmission.objects.get_queryset(
            exclude_archived_quests=False, exclude_quests_not_visible_to_students=False
        )

        sub = get_object_or_404(qs, pk=submission_id)
        template = "quest_manager/preview_content_approvals.html"
        quest_info_html = render_to_string(template, {"s": sub}, request=request)

        return JsonResponse({"quest_info_html": quest_info_html})
    else:
        raise Http404


@non_public_only_view
@login_required
def ajax_submission_info(request, submission_id=None):
    if request.is_ajax() and request.method == "POST":
        # past means previous semester that is now closed
        past = "/past/" in request.path_info
        completed = "/completed/" in request.path_info

        if past:  # past subs are filtered out of default queryset, so need to get
            qs = QuestSubmission.objects.all_completed_past(request.user)
        elif completed:
            qs = QuestSubmission.objects.all_completed(request.user)
        else:
            qs = QuestSubmission.objects.all()

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

    q = get_object_or_404(Quest, pk=quest_id)

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
    }

    return render(request, "quest_manager/detail.html", context)


#######################################
#
#  Quest APPROVAL VIEWS
#
# #################################


@non_public_only_view
@staff_member_required
def approve(request, submission_id):
    submission = get_object_or_404(QuestSubmission, pk=submission_id)
    origin_path = submission.get_absolute_url()

    if request.method == "POST":
        # currently only the big form has files.  Need a more robust way to determine...
        if request.FILES or request.POST.get("awards"):
            if request.user.is_staff:
                form = SubmissionFormStaff(request.POST, request.FILES)
            else:
                form = SubmissionForm(request.POST, request.FILES)
        else:
            form = SubmissionQuickReplyForm(request.POST)

        if form.is_valid():
            # handle badge assertion
            comment_text_addition = ""

            badge = form.cleaned_data.get("award")

            if badge:
                badges = [badge]
            else:
                badges = form.cleaned_data.get("awards")
            if badges:
                for badge in badges:
                    # badge = get_object_or_404(Badge, pk=badge_id)
                    new_assertion = BadgeAssertion.objects.create_assertion(
                        submission.user, badge, request.user
                    )
                    messages.success(
                        request,
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

            # handle with quest comments
            blank_comment_text = ""
            if "approve_button" in request.POST:
                note_verb = "approved"
                icon = (
                    "<span class='fa-stack'>"
                    + "<i class='fa fa-check fa-stack-2x text-success'></i>"
                    + "<i class='fa fa-shield fa-stack-1x'></i>"
                    + "</span>"
                )
                blank_comment_text = SiteConfig.get().blank_approval_text
                submission.mark_approved()
            elif "comment_button" in request.POST:
                note_verb = "commented on"
                icon = (
                    "<span class='fa-stack'>"
                    + "<i class='fa fa-shield fa-stack-1x'></i>"
                    + "<i class='fa fa-comment-o fa-stack-2x text-info'></i>"
                    + "</span>"
                )
                blank_comment_text = "(no comment added)"
            elif "return_button" in request.POST:
                note_verb = "returned"
                icon = (
                    "<span class='fa-stack'>"
                    + "<i class='fa fa-shield fa-stack-1x'></i>"
                    + "<i class='fa fa-ban fa-stack-2x text-danger'></i>"
                    + "</span>"
                )
                blank_comment_text = SiteConfig.get().blank_return_text
                submission.mark_returned()
            elif "skip_button" in request.POST:
                note_verb = "skipped"
                icon = (
                    "<span class='fa-stack text-muted'>"
                    + "<i class='fa fa-shield fa-stack-1x'></i>"
                    + "</span>"
                )
                blank_comment_text = (
                    "(Skipped - You were not granted XP for this quest)"
                )
                submission.mark_approved(transfer=True)
            else:
                raise Http404("unrecognized submit button")

            comment_text_form = form.cleaned_data.get("comment_text")
            if not comment_text_form:
                comment_text = blank_comment_text
            else:
                comment_text = comment_text_form
            comment_new = Comment.objects.create_comment(
                user=request.user,
                path=origin_path,
                # wrap comment text in <p> tag so default submission replies and quick replies are formatted correctly
                text=f"<p>{comment_text}</p>{comment_text_addition}",
                target=submission,
            )

            # handle files
            if request.FILES:
                for afile in request.FILES.getlist("attachments"):
                    newdoc = Document(docfile=afile, comment=comment_new)
                    newdoc.save()

            # don't say "with" in notification if no comment was entered
            if not comment_text_form:
                action = None
            else:
                action = comment_new

            affected_users = [
                submission.user,
            ]

            # if the staff member approving/commenting/retruning the submission isn't
            # one of the student's teachers then notify the student's teachers too
            # If they have no teachers (e.g. this quest is available outside of a course
            # and the student is not in a course) then nothign will be appended anyway
            teachers_list = list(submission.user.profile.current_teachers())
            if request.user not in teachers_list:
                affected_users.extend(teachers_list)

            notify.send(
                request.user,
                action=action,
                target=submission,
                recipient=submission.user,
                affected_users=affected_users,
                verb=note_verb,
                icon=icon,
            )

            message_string = (
                "<a href='"
                + origin_path
                + "'>Submission of "
                + submission.quest.name
                + "</a> "
                + note_verb
                + " for <a href='"
                + submission.user.profile.get_absolute_url()
                + "'>"
                + submission.user.username
                + "</a>"
            )
            messages.success(request, message_string)

            return redirect("quests:approvals")
        else:
            # messages.error(request, "There was an error with your comment. Maybe you need to type something?")
            # return redirect(origin_path)

            # rendering here with the context allows validation errors to be displayed
            context = {
                "heading": submission.quest.name,
                "submission": submission,
                # "comments": comments,
                "submission_form": form,
                "anchor": "submission-form-" + str(submission.quest.id),
                # "reply_comment_form": reply_comment_form,
            }
            return render(request, "quest_manager/submission.html", context)
    else:
        raise Http404


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


@non_public_only_view
@staff_member_required
def approvals(request, quest_id=None, template="quest_manager/quest_approval.html"):
    """A view for Teachers' Quest Approvals section.

    If a quest_id is provided, then filter the queryset to only include
    submissions for that quest.

    Different querysets are generated based on the url. Each with its own tab.
    Currently:
        Submitted (i.e. awaiting approval)
        Returned
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
    returned_submissions = []
    flagged_submissions = []

    submitted_tab_active = False
    returned_tab_active = False
    approved_tab_active = False
    flagged_tab_active = False

    page = request.GET.get("page")
    # if '/submitted/' in request.path_info:
    #     approval_submissions = QuestSubmission.objects.all_awaiting_approval()
    if "/returned/" in request.path_info:
        returned_submissions = QuestSubmission.objects.all_returned()
        returned_tab_active = True
        returned_submissions = paginate(returned_submissions, page)
    elif "/approved/" in request.path_info:
        approved_submissions = QuestSubmission.objects.all_approved(
            quest=quest, active_semester_only=active_sem_only
        )
        approved_tab_active = True
        approved_submissions = paginate(approved_submissions, page)
    elif "/flagged/" in request.path_info:
        flagged_submissions = QuestSubmission.objects.flagged(user=request.user)
        flagged_tab_active = True
        flagged_submissions = paginate(flagged_submissions, page)
    else:  # default is /submitted/ (awaiting approval)
        submitted_tab_active = True
        if current_teacher_only:
            teacher = request.user
        else:
            teacher = None
        submitted_submissions = QuestSubmission.objects.all_awaiting_approval(
            teacher=teacher
        )
        submitted_submissions = paginate(submitted_submissions, page)

    tab_list = [
        {
            "name": "Submitted",
            "submissions": submitted_submissions,
            "active": submitted_tab_active,
            "time_heading": "Submitted",
            "url": reverse("quests:submitted"),
        },
        {
            "name": "Returned",
            "submissions": returned_submissions,
            "active": returned_tab_active,
            "time_heading": "Returned",
            "url": reverse("quests:returned"),
        },
        {
            "name": "Approved",
            "submissions": approved_submissions,
            "active": approved_tab_active,
            "time_heading": "Approved",
            "url": reverse("quests:approved"),
        },
        {
            "name": "Flagged",
            "submissions": flagged_submissions,
            "active": flagged_tab_active,
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
        "submitted_tab_active": submitted_tab_active,
        "current_teacher_only": current_teacher_only,
        "past_approvals_all": past_approvals_all,
        "quest": quest,
        "quick_reply_text": SiteConfig.get().submission_quick_text,
        "show_all_blocks_button": show_all_blocks_button,
    }
    return render(request, template, context)


#########################################
#
#   QUEST SUBMISSION - STUDENT VIEWS
#
#########################################
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

    # http://stackoverflow.com/questions/22470637/django-show-validationerror-in-template
    if request.method == "POST":
        # for some reason Summernote is submitting the form in the background when an image is added or
        # dropped into the widget We need to ignore that submission
        # https://github.com/summernote/django-summernote/issues/362
        if "complete" not in request.POST and "comment" not in request.POST:
            raise Http404("unrecognized submit button")

        if (
            submission.quest.xp_can_be_entered_by_students
            and not submission.is_approved
        ):
            form = SubmissionFormCustomXP(request.POST, request.FILES)
        elif request.FILES:
            form = SubmissionForm(request.POST, request.FILES)
        else:
            form = SubmissionQuickReplyFormStudent(request.POST)

        if form.is_valid():
            comment_text = form.cleaned_data.get("comment_text")
            if not comment_text:
                if submission.quest.verification_required and not request.FILES:
                    messages.error(
                        request,
                        "Please read the Submission Instructions more carefully.  "
                        "You are expected to attach something or comment to complete this quest!",
                    )
                    return redirect(origin_path)
                elif "comment" in request.POST and not request.FILES:
                    messages.error(request, "Please leave a comment.")
                    return redirect(origin_path)
                else:
                    comment_text = "(submitted without comment)"

            if (
                submission.quest.xp_can_be_entered_by_students
                and not submission.is_approved
            ):
                xp_requested = form.cleaned_data.get("xp_requested")
                comment_text += f"<ul><li><b>XP requested: {xp_requested}</b></li></ul>"

            comment_new = Comment.objects.create_comment(
                user=request.user,
                path=origin_path,
                text=comment_text,
                target=submission,
            )

            if request.FILES:
                for afile in request.FILES.getlist("attachments"):
                    newdoc = Document(docfile=afile, comment=comment_new)
                    newdoc.save()

            if "complete" in request.POST:
                note_verb = "completed"
                msg_text = "Quest completed"
                affected_users = []

                if submission.quest.verification_required:
                    msg_text += ", awaiting approval."
                else:
                    note_verb += " (auto-approved quest)"
                    msg_text += " and automatically approved."
                    msg_text += " Please give me a moment to calculate what new quests this should make available to you."
                    msg_text += " Try refreshing your browser in a few moments. Thanks! <br>&mdash;{deck_ai}"
                    msg_text = msg_text.format(deck_ai=SiteConfig.get().deck_ai)

                icon = "<i class='fa fa-shield fa-lg'></i>"

                # Notify teacher if they are specific to quest but are not the student's current teacher
                # current teacher doesn't need the notification because they'll see it in their approvals tabs already
                if (
                    submission.quest.specific_teacher_to_notify
                    and submission.quest.specific_teacher_to_notify
                    not in request.user.profile.current_teachers()
                ):
                    affected_users.append(submission.quest.specific_teacher_to_notify)

                # Send notification to current teachers when a comment is left on an auto-approved quest
                # since these quests don't appear in the approvals tab, teacher would never know about the comment.
                if (
                    form.cleaned_data.get("comment_text")
                    and not submission.quest.verification_required
                ):
                    affected_users.extend(request.user.profile.current_teachers())

                xp_requested = (
                    form.cleaned_data.get("xp_requested")
                    if submission.quest.xp_can_be_entered_by_students
                    else 0
                )
                submission.mark_completed(xp_requested)
                if not submission.quest.verification_required:
                    submission.mark_approved()

            elif "comment" in request.POST:
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
                    # remove doubles/flatten
                    affected_users = set(affected_users)
            else:
                raise Http404("unrecognized submit button")

            notify.send(
                request.user,
                action=comment_new,
                target=submission,
                recipient=submission.user,
                affected_users=affected_users,
                verb=note_verb,
                icon=icon,
            )
            messages.success(request, msg_text)
            return redirect("quests:quests")
        else:
            context = {
                "heading": submission.quest.name,
                "submission": submission,
                # "comments": comments,
                "submission_form": form,
                "anchor": "submission-form-" + str(submission.quest.id),
                # "reply_comment_form": reply_comment_form,
            }
            return render(request, "quest_manager/submission.html", context)
    else:
        raise Http404


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
            # We found an in-progress/not completed submission for the quest,
            # so send them to it instead of starting a new one
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
        "<strong>"
        + quest.name
        + "</strong> has been added to your list of hidden quests.",
    )

    return redirect("quests:quests")


@non_public_only_view
@login_required
def unhide(request, quest_id):
    quest = get_object_or_404(Quest, pk=quest_id)
    request.user.profile.unhide_quest(quest_id)

    messages.success(
        request,
        "<strong>"
        + quest.name
        + "</strong> has been removed from your list of hidden quests.",
    )

    return redirect("quests:available_all")


@login_required
def skip(request, submission_id):
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

        # approve quest automatically, and mark as transfer.
        submission.mark_completed()
        submission.mark_approved(transfer=True)

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
def skipped(request, quest_id):
    """A combination of the start and complete views, but automatically approved
    regardless, and do_not_grant_xp = True
    """
    quest = get_object_or_404(Quest, pk=quest_id)
    new_sub = QuestSubmission.objects.create_submission(request.user, quest)
    if new_sub is None:  # might be because quest was already started
        # so try to get the started Quest
        submission = QuestSubmission.objects.all_for_user_quest(
            request.user, quest, True
        ).last()
        if submission is None:
            raise Http404
    else:
        submission = new_sub

    return skip(request, submission.id)


@non_public_only_view
@login_required
def ajax_save_draft(request):
    if request.is_ajax() and request.POST:
        response_data = {
            "result": "No changes",
        }

        submission_comment = request.POST.get("comment")
        submission_id = request.POST.get("submission_id")
        # xp_requested = request.POST.get('xp_requested')

        sub = get_object_or_404(QuestSubmission, pk=submission_id)

        if sub.draft_text != submission_comment:
            sub.draft_text = submission_comment
            # sub.xp_requested = xp_requested
            response_data["result"] = "Draft saved"
            sub.save()

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
        sub.delete()
        messages.error(request, ("Quest dropped."))
        return redirect("quests:quests")
    return render(request, template_name, {"submission": sub})


@non_public_only_view
@login_required
def submission(request, submission_id=None, quest_id=None):
    # sub = QuestSubmission.objects.get(id = submission_id)
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

    if request.user.is_staff:
        # Staff form has additional fields such as award granting.
        main_comment_form = SubmissionFormStaff(request.POST or None)
    else:
        initial = {"comment_text": sub.draft_text}
        if sub.quest.xp_can_be_entered_by_students and not sub.is_approved:
            # Use the xp requested from the submission. Default to quest xp
            initial["xp_requested"] = sub.xp_requested or sub.quest.xp
            main_comment_form = SubmissionFormCustomXP(
                request.POST or None, initial=initial, minimum_xp=sub.quest.xp
            )
        else:
            main_comment_form = SubmissionForm(request.POST or None, initial=initial)

    # main_comment_form = CommentForm(request.POST or None, wysiwyg=True, label="")
    # reply_comment_form = CommentForm(request.POST or None, label="")
    # comments = Comment.objects.all_with_target_object(sub)

    context = {
        "heading": sub.quest_name(),
        "submission": sub,
        "q": sub.quest,  # allows for common data to be displayed on sidebar more easily...
        # "comments": comments,
        "submission_form": main_comment_form,
        # "reply_comment_form": reply_comment_form,
        "quick_reply_text": SiteConfig.get().submission_quick_text,
    }
    return render(request, "quest_manager/submission.html", context)


@non_public_only_view
@login_required
def ajax_submission_count(request):
    """Returns the number of submissions awaiting approval for the current user
    This is used to update the number beside the "Approvals" button in the navbar"""
    if request.is_ajax() and request.method == "POST":
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

    # approve quest automatically, and mark as transfer.
    sub.flagged_by = request.user
    sub.save()

    messages.success(request, "Submission flagged for future follow up.")

    return redirect("quests:approvals")


@non_public_only_view
@staff_member_required
def ajax_flag(request):
    if request.is_ajax() and request.method == "POST":
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

    # approve quest automatically, and mark as transfer.
    sub.flagged_by = None
    sub.save()

    messages.success(
        request,
        "Submission <a href='%s'>%s by %s</a> has been unflagged."
        % (sub.get_absolute_url(), sub.quest_name(), sub.user),
    )

    return redirect("quests:approvals")
