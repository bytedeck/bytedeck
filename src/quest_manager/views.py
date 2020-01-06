import json
import uuid

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect, Http404
from django.template.loader import render_to_string
from django.urls import reverse_lazy, reverse
from django.views.generic.edit import DeleteView, UpdateView, CreateView

from djconfig import config

from badges.models import BadgeAssertion
from comments.models import Comment, Document
from notifications.signals import notify
from prerequisites.models import Prereq
from prerequisites.tasks import update_quest_conditions_for_user
from .forms import QuestForm, SubmissionForm, SubmissionFormStaff, SubmissionQuickReplyForm
from .models import Quest, QuestSubmission


def is_staff_or_TA(user):
    return user.is_staff or user.profile.is_TA


class QuestDelete(UserPassesTestMixin, DeleteView):
    def test_func(self):
        return self.get_object().is_editable(self.request.user)

    model = Quest
    success_url = reverse_lazy('quests:quests')

    def dispatch(self, *args, **kwargs):
        return super(QuestDelete, self).dispatch(*args, **kwargs)


class QuestCreate(UserPassesTestMixin, CreateView):
    def test_func(self):
        return is_staff_or_TA(self.request.user)

    model = Quest
    form_class = QuestForm

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(QuestCreate, self).get_context_data(**kwargs)
        context['heading'] = "Create New Quest"
        context['action_value'] = ""
        context['submit_btn_value'] = "Create"
        return context

    # The quest form needs the request object to see what user is trying to use it (teacher vs TA)
    # https://stackoverflow.com/questions/31204710/change-form-fields-based-on-request
    def get_form_kwargs(self):
        # grab the current set of form #kwargs
        kwargs = super(QuestCreate, self).get_form_kwargs()
        # Update the kwargs with the user_id
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        # TA created quests should not be visible to students.
        if self.request.user.profile.is_TA:
            form.instance.visible_to_students = False
            form.instance.editor = self.request.user
        return super(QuestCreate, self).form_valid(form)

    # @user_passes_test(test_func)
    # def dispatch(self, *args, **kwargs):
    #     return super(QuestCreate, self).dispatch(*args, **kwargs)


class QuestUpdate(UserPassesTestMixin, UpdateView):
    def test_func(self):
        # user self.get_object() because self.object doesn't exist yet
        # https://stackoverflow.com/questions/38544692/django-dry-principle-and-userpassestestmixin
        return self.get_object().is_editable(self.request.user)

    model = Quest
    form_class = QuestForm

    # template_name = ''

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(QuestUpdate, self).get_context_data(**kwargs)
        context['heading'] = "Update Quest"
        context['action_value'] = ""
        context['submit_btn_value'] = "Update"
        return context

    def get_success_url(self):
        if self.object.archived:
            return reverse("quests:quests")
        return self.object.get_absolute_url()

    # The quest form needs the request object to see what user is trying to use it (teacher vs TA)
    # https://stackoverflow.com/questions/31204710/change-form-fields-based-on-request
    def get_form_kwargs(self):
        # grab the current set of form #kwargs
        kwargs = super(QuestUpdate, self).get_form_kwargs()
        # Update the kwargs with the user_id
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        # TA created quests should not be visible to students.
        if self.request.user.profile.is_TA:
            form.instance.visible_to_students = False
            form.instance.editor = self.request.user
        elif form.instance.visible_to_students:
            form.instance.editor = None

        return super(QuestUpdate, self).form_valid(form)


@login_required
def quest_list2(request, quest_id=None, submission_id=None):
    return quest_list(request, quest_id, submission_id, template="quest_manager/quests2.html")


@login_required
def quest_list(request, quest_id=None, submission_id=None, template="quest_manager/quests.html"):
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
    active_submission_id = 0

    # Figure out what tab we want.
    if quest_id is not None:
        # if a quest_id was provided, got to the Available tab
        active_quest_id = int(quest_id)
        available_tab_active = True
    elif submission_id is not None:
        # if sub_id was provided, figure out which tab and go there
        # this isn't active
        active_submission_id = int(submission_id)
        active_sub = get_object_or_404(QuestSubmission, pk=submission_id)
        if active_sub in in_progress_submissions:
            in_progress_tab_active = True
        elif active_sub in completed_submissions:
            completed_tab_active = True
        else:
            raise Http404("Couldn't find this Submission. Sorry!")
    # otherwise look at the path
    elif '/inprogress/' in request.path_info:
        in_progress_tab_active = True
    elif '/completed/' in request.path_info:
        completed_tab_active = True
    elif '/past/' in request.path_info:
        past_tab_active = True
    elif '/drafts/' in request.path_info:
        drafts_tab_active = True
    else:
        available_tab_active = True
        if '/all/' in request.path_info:
            remove_hidden = False

    page = request.GET.get('page')

    # need these anyway to count them.
    # get_available is not a queryset, cant use .count()

    if in_progress_tab_active:
        in_progress_submissions = QuestSubmission.objects.all_not_completed(request.user)
        in_progress_submissions = paginate(in_progress_submissions, page)
        # available_quests = []
    elif completed_tab_active:
        completed_submissions = QuestSubmission.objects.all_completed(request.user)
        completed_submissions = paginate(completed_submissions, page)
        # available_quests = []
    elif past_tab_active:
        past_submissions = QuestSubmission.objects.all_completed_past(request.user)
        past_submissions = paginate(past_submissions, page)
        # available_quests = []
    elif drafts_tab_active:
        draft_quests = Quest.objects.all_drafts(request.user)
    else:
        if request.user.is_staff:
            available_quests = Quest.objects.all().visible().select_related('campaign', 'editor__profile')
            # num_available = available_quests.count()
        else:
            if request.user.profile.has_current_course:
                available_quests = Quest.objects.get_available(request.user, remove_hidden)
            # num_available = len(available_quests)
            else:
                available_quests = Quest.objects.get_available_without_course(request.user)

    # paginate or no?
    # available_quests = paginate(available_quests, page)

    # num_inprogress = QuestSubmission.objects.all_not_completed(request.user).count()
    # num_completed = QuestSubmission.objects.all_completed(request.user).count()

    context = {
        "heading": "Quests",
        "available_quests": available_quests,
        "remove_hidden": remove_hidden,
        # "num_available": num_available,
        "in_progress_submissions": in_progress_submissions,
        # "num_inprogress": num_inprogress,
        "completed_submissions": completed_submissions,
        "draft_quests": draft_quests,
        "past_submissions": past_submissions,
        # "num_completed": num_completed,
        "active_q_id": active_quest_id,
        "active_id": active_submission_id,
        "available_tab_active": available_tab_active,
        "inprogress_tab_active": in_progress_tab_active,
        "completed_tab_active": completed_tab_active,
        "past_tab_active": past_tab_active,
        "drafts_tab_active": drafts_tab_active,
    }
    return render(request, template, context)


@login_required
def ajax_quest_info(request, quest_id=None):

    if request.is_ajax() and request.method == "POST":

        template = "quest_manager/preview_content_quests_avail.html"

        if quest_id:
            quest = get_object_or_404(Quest, pk=quest_id)
            is_hidden = request.user.profile.is_quest_hidden(quest)
            is_repeatable = quest.is_repeatable()
            is_prerequisite = quest.is_used_prereq()

            template = "quest_manager/preview_content_quests_avail.html"
            quest_info_html = render_to_string(template, {"q": quest}, request=request)

            data = {
                "quest_info_html": quest_info_html,
                "is_hidden": is_hidden,
                "is_repeatable": is_repeatable,
                "is_prerequisite": is_prerequisite,
            }

            # JsonResponse new in Django 1.7 is equivalent to:
            # return HttpResponse(json.dumps(data), content_type='application/json')
            return JsonResponse(data)

        else:  # all quests, used for staff only.
            quests = Quest.objects.all()
            all_quest_info_html = {}

            for q in quests:
                all_quest_info_html[q.id] = render_to_string(template, {"q": q}, request=request)

            data = json.dumps(all_quest_info_html)
            return JsonResponse(data, safe=False)

    else:
        raise Http404


@login_required
def ajax_approval_info(request, submission_id=None):
    if request.is_ajax() and request.method == "POST":

        qs = QuestSubmission.objects.get_queryset(exclude_archived_quests=False,
                                                  exclude_quests_not_visible_to_students=False)

        sub = get_object_or_404(qs, pk=submission_id)
        template = "quest_manager/preview_content_approvals.html"
        quest_info_html = render_to_string(template, {"s": sub}, request=request)

        return JsonResponse({"quest_info_html": quest_info_html})
    else:
        raise Http404


@login_required
def ajax_submission_info(request, submission_id=None):
    if request.is_ajax() and request.method == "POST":

        # past means previous semester that is now closed
        past = '/past/' in request.path_info
        completed = '/completed/' in request.path_info

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


@user_passes_test(is_staff_or_TA)
def quest_copy(request, quest_id):
    new_quest = get_object_or_404(Quest, pk=quest_id)
    new_quest.pk = None  # autogen a new primary key (quest_id by default)
    new_quest.import_id = uuid.uuid4()
    new_quest.name = new_quest.name + " - COPY"
    # print(quest_to_copy)
    # print(new_quest)
    # new_quest.save()

    form = QuestForm(request.POST or None, instance=new_quest, user=request.user)

    if form.is_valid():
        if request.user.profile.is_TA:
            form.instance.visible_to_students = False
            form.instance.editor = request.user

        form.save()
        # make the copied quest a prerequisite for the new quest
        copied_quest = get_object_or_404(Quest, pk=quest_id)
        Prereq.add_simple_prereq(new_quest, copied_quest)

        # add same campaigns/categories as copied quest
        # new_quest.categories = copied_quest.categories.all()

        return redirect(new_quest)

    context = {
        "heading": "Copy a Quest",
        "form": form,
        "submit_btn_value": "Create",
    }
    return render(request, "quest_manager/quest_form.html", context)


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
        submissions = QuestSubmission.objects.all_for_user_quest(request.user, q, active_semester_only=False)
        if submissions:
            sub = submissions.latest('time_approved')
            return submission(request, sub.id)
        else:
            # No submission either, so display quest flagged as unavailable
            available = False

    context = {
        "heading": q.name,
        "q": q,
        "available": available,
    }

    return render(request, 'quest_manager/detail.html', context)


#######################################
#
#  Quest APPROVAL VIEWS
#
# #################################


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

            badge = form.cleaned_data.get('award')

            if badge:
                badges = [badge]
            else:
                badges = form.cleaned_data.get('awards')
            if badges:
                for badge in badges:
                    # badge = get_object_or_404(Badge, pk=badge_id)
                    new_assertion = BadgeAssertion.objects.create_assertion(submission.user, badge, request.user)
                    messages.success(
                        request,
                        ("Badge " + str(new_assertion) + " granted to " + str(new_assertion.user))
                    )
                    comment_text_addition += "<p></br><i class='fa fa-certificate text-warning'></i> The <b>" + \
                                             badge.name + "</b> badge was granted for this quest " + \
                                             "<i class='fa fa-certificate text-warning'></i></p>"

            # handle with quest comments
            blank_comment_text = ""
            if 'approve_button' in request.POST:
                note_verb = "approved"
                icon = "<span class='fa-stack'>" + \
                       "<i class='fa fa-check fa-stack-2x text-success'></i>" + \
                       "<i class='fa fa-shield fa-stack-1x'></i>" + \
                       "</span>"
                blank_comment_text = config.hs_blank_approval_text
                submission.mark_approved()
            elif 'comment_button' in request.POST:
                note_verb = "commented on"
                icon = "<span class='fa-stack'>" + \
                       "<i class='fa fa-shield fa-stack-1x'></i>" + \
                       "<i class='fa fa-comment-o fa-stack-2x text-info'></i>" + \
                       "</span>"
                blank_comment_text = "(no comment added)"
            elif 'return_button' in request.POST:
                note_verb = "returned"
                icon = "<span class='fa-stack'>" + \
                       "<i class='fa fa-shield fa-stack-1x'></i>" + \
                       "<i class='fa fa-ban fa-stack-2x text-danger'></i>" + \
                       "</span>"
                blank_comment_text = config.hs_blank_return_text
                submission.mark_returned()
            else:
                raise Http404("unrecognized submit button")

            comment_text_form = form.cleaned_data.get('comment_text')
            if not comment_text_form:
                comment_text = blank_comment_text
            else:
                comment_text = comment_text_form
            comment_new = Comment.objects.create_comment(
                user=request.user,
                path=origin_path,
                text=comment_text + comment_text_addition,
                target=submission
            )

            # handle files
            if request.FILES:
                for afile in request.FILES.getlist('attachments'):
                    newdoc = Document(docfile=afile, comment=comment_new)
                    newdoc.save()

            # don't say "with" in notification if no comment was entered
            if not comment_text_form:
                action = None
            else:
                action = comment_new

            affected_users = [submission.user, ]
            notify.send(
                request.user,
                action=action,
                target=submission,
                recipient=submission.user,
                affected_users=affected_users,
                verb=note_verb,
                icon=icon,
            )

            message_string = "<a href='" + origin_path + "'>Submission of " + \
                             submission.quest.name + "</a> " + note_verb + \
                             " for <a href='" + submission.user.profile.get_absolute_url() + "'>" + \
                             submission.user.username + "</a>"
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
            return render(request, 'quest_manager/submission.html', context)
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


@staff_member_required
def approvals(request, quest_id=None):
    """A view for Teachers' Quest Approvals section.

    If a quest_id is provided, then filter the queryset to only include
    submissions for that quest.

    Different querysets are generated based on the url. Each with its own tab.
    Currently:
        Submitted (i.e. awaiting approval)
        Returned
        Approved
        Skipped

    """

    # If we are looking up past approvals of a specific quest
    if quest_id:
        quest = get_object_or_404(Quest, id=quest_id)
        if '/all/' in request.path_info:
            active_sem_only = False
            past_approvals_all = True
        else:
            active_sem_only = True
            past_approvals_all = False  # If we are looking at previous approvals of a specific quest
    else:
        quest = None
        past_approvals_all = None
        active_sem_only = True

    if '/all/' in request.path_info:
        current_teacher_only = False
    else:
        current_teacher_only = True

    submitted_submissions = []
    approved_submissions = []
    returned_submissions = []
    skipped_submissions = []

    submitted_tab_active = False
    returned_tab_active = False
    approved_tab_active = False
    skipped_tab_active = False

    page = request.GET.get('page')
    # if '/submitted/' in request.path_info:
    #     approval_submissions = QuestSubmission.objects.all_awaiting_approval()
    if '/returned/' in request.path_info:
        returned_submissions = QuestSubmission.objects.all_returned()
        returned_tab_active = True
        returned_submissions = paginate(returned_submissions, page)
    elif '/approved/' in request.path_info:
        approved_submissions = QuestSubmission.objects.all_approved(quest=quest, active_semester_only=active_sem_only)
        approved_tab_active = True
        approved_submissions = paginate(approved_submissions, page)
    elif '/skipped/' in request.path_info:
        skipped_submissions = QuestSubmission.objects.all_skipped()
        skipped_tab_active = True
        skipped_submissions = paginate(skipped_submissions, page)
    else:  # default is /submitted/ (awaiting approval)
        submitted_tab_active = True
        if current_teacher_only:
            teacher = request.user
        else:
            teacher = None
        submitted_submissions = QuestSubmission.objects.all_awaiting_approval(teacher=teacher)
        submitted_submissions = paginate(submitted_submissions, page)

    tab_list = [{"name": "Submitted",
                 "submissions": submitted_submissions,
                 "active": submitted_tab_active,
                 "time_heading": "Submitted",
                 "url": reverse('quests:submitted'),
                 },
                {"name": "Returned",
                 "submissions": returned_submissions,
                 "active": returned_tab_active,
                 "time_heading": "Returned",
                 "url": reverse('quests:returned'),
                 },
                {"name": "Approved",
                 "submissions": approved_submissions,
                 "active": approved_tab_active,
                 "time_heading": "Approved",
                 "url": reverse('quests:approved'),
                 },
                {"name": "Skipped",
                 "submissions": skipped_submissions,
                 "active": skipped_tab_active,
                 "time_heading": "Transferred",
                 "url": reverse('quests:skipped'),
                 }, ]

    quick_reply_form = SubmissionQuickReplyForm(request.POST or None)

    context = {
        "heading": "Quest Approval",
        "tab_list": tab_list,
        "quick_reply_form": quick_reply_form,
        "submitted_tab_active": submitted_tab_active,
        "current_teacher_only": current_teacher_only,
        "past_approvals_all": past_approvals_all,
        "quest": quest,
        "quick_reply_text": config.hs_submission_quick_text
    }
    return render(request, "quest_manager/quest_approval.html", context)


#########################################
#
#   QUEST SUBMISSION - STUDENT VIEWS
#
#########################################
@login_required
def complete(request, submission_id):
    """
    When a student has completed a quest, or is commenting on an already completed quest, this view is called
    - The submission is marked as completed (by the student)
    - If the quest is automatically approved, then the submission is also marked as approved, and available quests are 
         recalculated directly/synchromously, so that their available quest list is up to date
    """
    submission = get_object_or_404(QuestSubmission, pk=submission_id)
    origin_path = submission.get_absolute_url()

    # http://stackoverflow.com/questions/22470637/django-show-validationerror-in-template
    if request.method == "POST":

        # for some reason Summernote is submitting the form in the background when an image is added or
        # dropped into the widget We need to ignore that submission
        # https://github.com/summernote/django-summernote/issues/362
        if 'complete' not in request.POST and 'comment' not in request.POST:
            raise Http404("unrecognized submit button")

        # form = CommentForm(request.POST or None, wysiwyg=True, label="")
        # form = SubmissionQuickReplyForm(request.POST)
        form = SubmissionForm(request.POST, request.FILES)

        if form.is_valid():
            comment_text = form.cleaned_data.get('comment_text')
            if not comment_text:
                if submission.quest.verification_required and not request.FILES:
                    messages.error(request,
                                   "Please read the Submission Instructions more carefully.  "
                                   "You are expected to attach something or comment to complete this quest!")
                    return redirect(origin_path)
                else:
                    comment_text = "(submitted without comment)"
            comment_new = Comment.objects.create_comment(
                user=request.user,
                path=origin_path,
                text=comment_text,
                target=submission,
            )

            if request.FILES:
                for afile in request.FILES.getlist('attachments'):
                    newdoc = Document(docfile=afile, comment=comment_new)
                    newdoc.save()

            if 'complete' in request.POST:
                note_verb = "completed"
                if submission.quest.verification_required:
                    note_verb += ", awaiting approval."
                else:
                    note_verb += " and automatically approved."

                icon = "<i class='fa fa-shield fa-lg'></i>"

                # Notify teacher if they are specific to quest but are not the student's teacher
                if submission.quest.specific_teacher_to_notify \
                        and submission.quest.specific_teacher_to_notify not in request.user.profile.current_teachers():
                    affected_users = [submission.quest.specific_teacher_to_notify, ]
                else:
                    affected_users = None
                submission.mark_completed()
                if not submission.quest.verification_required:
                    submission.mark_approved()
                    # Immediate/synchronous recalculation of available quests:
                    update_quest_conditions_for_user.apply(args=[request.user.id])

            elif 'comment' in request.POST:
                note_verb = "commented on"
                icon = "<span class='fa-stack'>" + \
                       "<i class='fa fa-shield fa-stack-1x'></i>" + \
                       "<i class='fa fa-comment-o fa-stack-2x text-info'></i>" + \
                       "</span>"
                affected_users = []
                if request.user.is_staff:
                    affected_users = [submission.user, ]
                else:  # student comment
                    # student's teachers
                    affected_users.extend(request.user.profile.current_teachers())  # User.objects.filter(is_staff=True)
                    # add quest's teacher if necessary
                    if submission.quest.specific_teacher_to_notify:
                        affected_users.append(submission.quest.specific_teacher_to_notify)
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
            messages.success(request, ("Quest " + note_verb))
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
            return render(request, 'quest_manager/submission.html', context)
    else:
        raise Http404


@login_required
def start(request, quest_id):
    quest = get_object_or_404(Quest, pk=quest_id)

    if not quest.is_available(request.user):
        raise Http404

    new_sub = QuestSubmission.objects.create_submission(request.user, quest)
    # if new_sub is None:
    #     print("This quest is not available, why is it showing up?")
    #     raise Http404 #shouldn't get here
    # should just do this, but the redirect is screwing up with the tour...
    # return redirect('quests:submission', submission_id = new_sub.id)

    if new_sub is None:  # might be because quest was already started
        # so try to get the started Quest
        sub = QuestSubmission.objects.all_for_user_quest(request.user, quest, True).last()
        if sub is None:
            raise Http404
    else:
        sub = new_sub

    if sub.user != request.user and not request.user.is_staff:
        return redirect('quests:quests')

    # Ideally do this!
    return redirect(sub)

    # # comment_form = SubmissionForm(request.POST or None)
    # main_comment_form = SubmissionForm(request.POST or None)
    # #main_comment_form = CommentForm(request.POST or None, wysiwyg=True, label="")
    # #reply_comment_form = CommentForm(request.POST or None, label="")
    # # comments = Comment.objects.all_with_target_object(sub)

    # Migth need this for the tour to work!
    # context = {
    #     "heading": sub.quest.name,
    #     "submission": sub,
    #     # "comments": comments,
    #     "submission_form": main_comment_form,
    #     # "reply_comment_form": reply_comment_form,
    # }
    # return render(request, 'quest_manager/submission.html', context)


@login_required
def hide(request, quest_id):
    quest = get_object_or_404(Quest, pk=quest_id)
    request.user.profile.hide_quest(quest_id)

    messages.warning(request, "<strong>" + quest.name + "</strong> has been added to your list of hidden quests.")

    return redirect("quests:quests")


@login_required
def unhide(request, quest_id):
    quest = get_object_or_404(Quest, pk=quest_id)
    request.user.profile.unhide_quest(quest_id)

    messages.success(request, "<strong>" + quest.name + "</strong> has been removed from your list of hidden quests.")

    return redirect("quests:available_all")


@login_required
def skip(request, submission_id):
    submission = get_object_or_404(QuestSubmission, pk=submission_id)
    # student can only do this if the button is turned on by a teacher
    # prevent students form skipping by guessing correct url
    # also make sure it's the student who owns the submission
    if (request.user.profile.game_lab_transfer_process_on and submission.user == request.user) or request.user.is_staff:

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

        messages.success(request,
                         ("Transfer Successful.  No XP was granted for this quest."))
        if request.user.is_staff:
            return redirect("quests:approvals")
        return redirect("quests:quests")
    else:
        raise Http404


@login_required
def skipped(request, quest_id):
    """A combination of the start and complete views, but automatically approved
    regardless, and game_lab_transfer = True
    """
    quest = get_object_or_404(Quest, pk=quest_id)
    new_sub = QuestSubmission.objects.create_submission(request.user, quest)
    if new_sub is None:  # might be because quest was already started
        # so try to get the started Quest
        submission = QuestSubmission.objects.all_for_user_quest(request.user, quest, True).last()
        if submission is None:
            raise Http404
    else:
        submission = new_sub

    return skip(request, submission.id)

    # #make sure another user isn't hacking in with urls
    # if submission.user != request.user and not request.user.is_staff:
    #     return redirect('quests:quests')
    #
    # #add default comment to submission
    # origin_path = submission.get_absolute_url()
    # comment_text = "(GameLab transfer - no XP for this quest)"
    # comment_new = Comment.objects.create_comment(
    #     user = request.user,
    #     path = origin_path,
    #     text = comment_text,
    #     target = submission,
    # )
    #
    # #approve quest automatically, and mark as transfer.
    # submission.mark_completed() ###################
    # submission.mark_approved(transfer = True)
    #
    # messages.success(request, ("Transfer Successful. No XP was granted for this quest."))
    # return redirect("quests:quests")


@login_required
def ajax_save_draft(request):
    if request.is_ajax() and request.POST:

        submission_comment = request.POST.get('comment')
        submission_id = request.POST.get('submission_id')

        sub = get_object_or_404(QuestSubmission, pk=submission_id)
        sub.draft_text = submission_comment
        sub.save()

        response_data = {}
        response_data['result'] = 'Draft saved'

        return HttpResponse(
            json.dumps(response_data),
            content_type="application/json"
        )

    else:
        raise Http404


@login_required
def drop(request, submission_id):
    sub = get_object_or_404(QuestSubmission, pk=submission_id)
    template_name = "quest_manager/questsubmission_confirm_delete.html"
    if sub.user != request.user and not request.user.is_staff:
        return redirect('quests:quests')
    if request.method == 'POST':
        sub.delete()
        messages.error(request, ("Quest dropped."))
        return redirect('quests:quests')
    return render(request, template_name, {'submission': sub})


@login_required
def submission(request, submission_id=None, quest_id=None):
    # sub = QuestSubmission.objects.get(id = submission_id)
    sub = get_object_or_404(QuestSubmission, pk=submission_id)
    if sub.user != request.user and not request.user.is_staff:
        return redirect('quests:quests')

    if request.user.is_staff:
        # Staff form has additional fields such as award granting.
        main_comment_form = SubmissionFormStaff(request.POST or None)
    else:
        initial = {'comment_text': sub.draft_text}
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
        "quick_reply_text": config.hs_submission_quick_text,
    }
    return render(request, 'quest_manager/submission.html', context)


@login_required
def ajax(request):
    if request.is_ajax() and request.method == "POST":

        submission_count = QuestSubmission.objects.all_awaiting_approval(teacher=request.user).count()
        sub_data = {
            "count": submission_count,
        }
        json_data = json.dumps(sub_data)

        return HttpResponse(json_data, content_type='application/json')
    else:
        raise Http404


########################
#
# FLAGGED SUBMISSIONS
#
########################

@staff_member_required
def flagged_submissions(request):
    flagged_subs = QuestSubmission.objects.flagged(user=request.user)

    quick_reply_form = SubmissionQuickReplyForm(request.POST or None)

    context = {
        "submissions": flagged_subs,
        "quick_reply_form": quick_reply_form,
        "active_id": None,
    }
    return render(request, "quest_manager/flagged.html", context)


@staff_member_required
def flag(request, submission_id):
    sub = get_object_or_404(QuestSubmission, pk=submission_id)

    # approve quest automatically, and mark as transfer.
    sub.flagged_by = request.user
    sub.save()

    messages.success(request, "Submission flagged for future follow up.")

    return redirect("quests:approvals")


@staff_member_required
def ajax_flag(request):
    if request.is_ajax() and request.method == "POST":

        submission_id = request.POST.get('submission_id', None)
        sub = QuestSubmission.objects.get(id=submission_id)
        sub.flagged_by = request.user
        sub.save()
        return JsonResponse(data={})
    else:
        raise Http404


@staff_member_required
def unflag(request, submission_id):
    sub = get_object_or_404(QuestSubmission, pk=submission_id)

    # approve quest automatically, and mark as transfer.
    sub.flagged_by = None
    sub.save()

    messages.success(request, "Submission <a href='%s'>%s by %s</a> has been unflagged." %
                     (sub.get_absolute_url(), sub.quest_name(), sub.user))

    return redirect("quests:approvals")
