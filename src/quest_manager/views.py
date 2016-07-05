import json
from django.conf import settings

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.urlresolvers import reverse_lazy, reverse

from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect, Http404
from django.template import RequestContext, loader
from django.utils.decorators import method_decorator
from django.views.generic.edit import CreateView, DeleteView, UpdateView


from badges.models import BadgeAssertion, Badge
from comments.models import Comment, Document
from comments.forms import CommentForm
from notifications.signals import notify
from prerequisites.models import Prereq

from .forms import QuestForm, SubmissionForm, SubmissionFormStaff, SubmissionQuickReplyForm
from .models import Quest, QuestSubmission, TaggedItem

class QuestDelete(DeleteView):
    model = Quest
    success_url = reverse_lazy('quests:quests')

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(QuestDelete, self).dispatch(*args, **kwargs)

class QuestUpdate(UpdateView):
    model = Quest
    form_class = QuestForm
    # template_name = ''

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(QuestUpdate, self).get_context_data(**kwargs)
        context['heading'] = "Update Quest"
        context['action_value']= ""
        context['submit_btn_value']= "Update"
        return context

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(QuestUpdate, self).dispatch(*args, **kwargs)

@login_required
def quest_list(request, quest_id=None, submission_id=None):

    available_quests = []
    in_progress_submissions = []
    completed_submissions = []
    past_submissions = []

    available_tab_active=False
    in_progress_tab_active=False
    completed_tab_active=False
    past_tab_active = False

    active_quest_id = 0
    active_submission_id=0

    # Figure out what tab we want.
    if quest_id is not None:
        # if a quest_id was provided, got to the Available tab
        active_quest_id = int(quest_id)
        available_tab_active=True
    elif submission_id is not None:
        # if sub_id was provided, figure out which tab and go there
        #this isn't active
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
    else:
        available_tab_active = True

    page = request.GET.get('page')

    #need these anyway to count them.  get_available is not a queryset, cant use .count()


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
    else:
        if request.user.is_staff:
            available_quests = Quest.objects.all()
            # num_available = available_quests.count()
        else:
            available_quests = Quest.objects.get_available(request.user)
            # num_available = len(available_quests)

    #paginate or no?
    # available_quests = paginate(available_quests, page)

    # num_inprogress = QuestSubmission.objects.all_not_completed(request.user).count()
    # num_completed = QuestSubmission.objects.all_completed(request.user).count()

    context = {
        "heading": "Quests",
        "available_quests": available_quests,
        # "num_available": num_available,
        "in_progress_submissions": in_progress_submissions,
        # "num_inprogress": num_inprogress,
        "completed_submissions": completed_submissions,
        "past_submissions": past_submissions,
        # "num_completed": num_completed,
        "active_q_id": active_quest_id,
        "active_id": active_submission_id,
        "available_tab_active": available_tab_active,
        "inprogress_tab_active": in_progress_tab_active,
        "completed_tab_active": completed_tab_active,
        "past_tab_active": past_tab_active,
    }
    return render(request, "quest_manager/quests.html" , context)

@login_required
def ajax_quest_info(request, quest_id = None):
    if request.is_ajax() and request.method == "POST":
        quest = get_object_or_404(Quest, pk=quest_id)
        context = {
            "q": quest,
        }
        return render(request,
                "quest_manager/preview_content_quests_avail.html",
                context)
    else:
        raise Http404

@login_required
def ajax_approval_info(request, submission_id = None):

    if request.is_ajax() and request.method == "POST":
        sub = get_object_or_404(QuestSubmission, pk=submission_id)
        context = {
            "s": sub,
        }
        return render(request,
                "quest_manager/preview_content_approvals.html",
                context)
    else:
        raise Http404

@login_required
def ajax_submission_info(request, submission_id = None):
    if request.is_ajax() and request.method == "POST":

        # past means previous semester that is now closed
        past = '/past/' in request.path_info
        completed = '/completed/' in request.path_info

        if past: #past subs are filtered out of default queryset, so need to get
            past_submissions = QuestSubmission.objects.all_completed_past(request.user)
            sub = get_object_or_404(past_submissions, pk=submission_id)
        else:
            sub = get_object_or_404(QuestSubmission, pk=submission_id)

        context = {
            "s": sub,
            "completed": completed,
            "past": past,
        }
        return render(request,
                "quest_manager/preview_content_submissions.html",
                context)
    else:
        raise Http404

@staff_member_required
def quest_create(request):
    form = QuestForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        form.save()
        return redirect('quests:quests')
    context = {
        "heading": "Create New Quest",
        "form": form,
        "submit_btn_value": "Create",
    }
    return render(request, "quest_manager/quest_form.html", context)

@staff_member_required
def quest_copy(request, quest_id):
    new_quest = get_object_or_404(Quest, pk=quest_id)
    new_quest.pk = None # autogen a new primary key (quest_id by default)
    new_quest.name = "Copy of " + new_quest.name
    # print(quest_to_copy)
    # print(new_quest)
    # new_quest.save()

    form =  QuestForm(request.POST or None, instance = new_quest)
    if form.is_valid():
        form.save()
        # make the copied quest a prerequisite for the new quest
        copied_quest = get_object_or_404(Quest, pk=quest_id)
        Prereq.objects.add_simple_prereq(new_quest, copied_quest)

        #add same campaigns/categories as copied quest
        new_quest.categories = copied_quest.categories.all()

        return redirect(new_quest)

    context = {
        "heading": "Copy a Quest",
        "form": form,
        "submit_btn_value": "Create",
    }
    return render(request, "quest_manager/quest_form.html", context)

@login_required
def detail(request, quest_id):
    #if there is an active submission, get it and display accordingly

    q = get_object_or_404(Quest, pk=quest_id)
    active_submission = QuestSubmission.objects.quest_is_available(request.user, q)

    context = {
        "heading": q.name,
        "q": q,
    }
    return render(request, 'quest_manager/detail.html', context)

########### Quest APPROVAL VIEWS #################################

@staff_member_required
def approve(request, submission_id):

    submission = get_object_or_404(QuestSubmission, pk=submission_id)
    origin_path = submission.get_absolute_url()

    if request.method == "POST":

        #currently only the big form has files.  Need a more robust way to determine...
        if request.FILES:
            form = SubmissionForm(request.POST, request.FILES)
        else:
            form = SubmissionQuickReplyForm(request.POST)

        if form.is_valid():
            #handle badge assertion
            comment_text_addition = ""
            badge = form.cleaned_data.get('award')
            if badge:
                #badge = get_object_or_404(Badge, pk=badge_id)
                new_assertion = BadgeAssertion.objects.create_assertion(submission.user, badge, request.user)
                messages.success(request, ("Badge " + str(new_assertion) + " granted to " + str(new_assertion.user)))
                comment_text_addition = "<p></br><i class='fa fa-certificate text-warning'></i> The <b>"+ \
                badge.name +"</b> badge was granted for this quest <i class='fa fa-certificate text-warning'></i></p>"

            # handle with quest comments
            blank_comment_text = ""
            if 'approve_button' in request.POST:
                note_verb="approved"
                icon="<span class='fa-stack'>" + \
                    "<i class='fa fa-check fa-stack-2x text-success'></i>" + \
                    "<i class='fa fa-shield fa-stack-1x'></i>" + \
                    "</span>"
                blank_comment_text="(approved without comment)"
                submission.mark_approved() ##############
            elif 'comment_button' in request.POST:
                note_verb="commented on"
                icon="<span class='fa-stack'>" + \
                    "<i class='fa fa-shield fa-stack-1x'></i>" + \
                    "<i class='fa fa-comment-o fa-stack-2x text-info'></i>" + \
                    "</span>"
                blank_comment_text="(no comment added)"
            elif 'return_button' in request.POST:
                note_verb="returned"
                icon="<span class='fa-stack'>" + \
                    "<i class='fa fa-shield fa-stack-1x'></i>" + \
                    "<i class='fa fa-ban fa-stack-2x text-danger'></i>" + \
                    "</span>"
                blank_comment_text="(returned without comment)"
                submission.mark_returned() ##############
            else:
                raise Http404("unrecognized submit button")


            comment_text_form = form.cleaned_data.get('comment_text')
            if not comment_text_form:
                comment_text = blank_comment_text
            else:
                comment_text = comment_text_form
            comment_new = Comment.objects.create_comment(
                user = request.user,
                path = origin_path,
                text = comment_text + comment_text_addition,
                target = submission
            )

            #handle files
            if request.FILES:
                file_list = request.FILES.getlist('files')
                for afile in file_list:
                    # print(afile)
                    newdoc = Document( docfile = afile, comment = comment_new)
                    newdoc.save()

            # don't say "with" in notification if no comment was entered
            if not comment_text_form:
                action = None
            else:
                action = comment_new

            affected_users = [submission.user,]
            notify.send(
                request.user,
                action=action,
                target= submission,
                recipient=submission.user,
                affected_users=affected_users,
                verb=note_verb,
                icon=icon,
            )

            message_string = "<a href='"+ origin_path +"'>Submission of " + \
                            submission.quest.name + "</a> " + note_verb + \
                            " for <a href='" + submission.user.profile.get_absolute_url() + "'>" + submission.user.username + "</a>"
            messages.success(request, message_string)


            return redirect("quests:approvals")
        else:
            # messages.error(request, "There was an error with your comment. Maybe you need to type something?")
            # return redirect(origin_path)

            #rendering here with the context allows validation errors to be displayed
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

def paginate(object_list, page, per_page = 30):
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

# Redundant - Use the approvals view below
# @staff_member_required
# def submissions(request, quest_id):
#
#     quest = get_object_or_404(Quest, id=quest_id)
#
#     submitted_submissions = []
#     approved_submissions = []
#     returned_submissions = []
#     skipped_submissions = []
#
#     submitted_tab_active=True
#     returned_tab_active=False
#     approved_tab_active=False
#     skipped_tab_active=False
#
#     page = request.GET.get('page')
#     # if '/submitted/' in request.path_info:
#     #     approval_submissions = QuestSubmission.objects.all_awaiting_approval()
#     if '/returned/' in request.path_info:
#         returned_submissions = QuestSubmission.objects.all_returned().get_quest(quest)
#         returned_tab_active = True
#         submitted_tab_active= False
#         returned_submissions = paginate(returned_submissions, page)
#     elif '/approved/' in request.path_info:
#         approved_submissions = QuestSubmission.objects.all_approved().get_quest(quest)
#         approved_tab_active = True
#         submitted_tab_active= False
#         approved_submissions = paginate(approved_submissions, page)
#     elif '/skipped/' in request.path_info:
#         skipped_submissions = QuestSubmission.objects.all_skipped().get_quest(quest)
#         skipped_tab_active = True
#         submitted_tab_active= False
#         skipped_submissions = paginate(skipped_submissions, page)
#     else:
#         submitted_submissions = QuestSubmission.objects.all_awaiting_approval().get_quest(quest)
#         submitted_submissions = paginate(submitted_submissions, page)
#         # approval_submissions = QuestSubmission.objects.all_awaiting_approval()
#         # approved_submissions = QuestSubmission.objects.all_approved()
#         # returned_submissions = QuestSubmission.objects.all_returned()
#
#     tab_list = [{   "name": "Submitted",
#                     "submissions": submitted_submissions,
#                     "active" : submitted_tab_active,
#                     "time_heading": "Submitted",
#                     "url": reverse('quests:submitted_for_quest', kwargs={'quest_id': quest_id}),
#                 },
#                 {   "name": "Returned",
#                     "submissions": returned_submissions,
#                     "active" : returned_tab_active,
#                     "time_heading": "Returned",
#                     "url": reverse('quests:returned_for_quest', kwargs={'quest_id': quest_id}),
#                 },
#                 {   "name": "Approved",
#                     "submissions": approved_submissions,
#                     "active" : approved_tab_active,
#                     "time_heading": "Approved",
#                     "url": reverse('quests:approved_for_quest', kwargs={'quest_id': quest_id}),
#                 },
#                 {   "name": "Skipped",
#                     "submissions": skipped_submissions,
#                     "active" : skipped_tab_active,
#                     "time_heading": "Transfered",
#                     "url": reverse('quests:skipped_for_quest', kwargs={'quest_id': quest_id}),
#                 },]
#
#     # main_comment_form = CommentForm(request.POST or None, wysiwyg=True, label="")
#     quick_reply_form = SubmissionQuickReplyForm(request.POST or None)
#     heading = "Submission Summary: " + quest.name
#
#     context = {
#         "heading": heading,
#         "tab_list": tab_list,
#         # "main_comment_form": main_comment_form,
#         "quick_reply_form": quick_reply_form,
#     }
#     return render(request, "quest_manager/quest_approval.html" , context)

@staff_member_required
def approvals(request, quest_id = None):
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

    if quest_id:
        quest = get_object_or_404(Quest, id=quest_id)
    else:
        quest = None

    submitted_submissions = []
    approved_submissions = []
    returned_submissions = []
    skipped_submissions = []

    submitted_tab_active=False
    returned_tab_active=False
    approved_tab_active=False
    skipped_tab_active=False

    page = request.GET.get('page')
    # if '/submitted/' in request.path_info:
    #     approval_submissions = QuestSubmission.objects.all_awaiting_approval()
    if '/returned/' in request.path_info:
        returned_submissions = QuestSubmission.objects.all_returned()
        returned_tab_active = True
        returned_submissions = paginate(returned_submissions, page)
    elif '/approved/' in request.path_info:
        approved_submissions = QuestSubmission.objects.all_approved(quest=quest)
        approved_tab_active = True
        approved_submissions = paginate(approved_submissions, page)
    elif '/skipped/' in request.path_info:
        skipped_submissions = QuestSubmission.objects.all_skipped()
        skipped_tab_active = True
        skipped_submissions = paginate(skipped_submissions, page)
    else: # default is /submitted/ (awaiting approval)
        submitted_tab_active= True
        submitted_submissions = QuestSubmission.objects.all_awaiting_approval()
        submitted_submissions = paginate(submitted_submissions, page)

    tab_list = [{   "name": "Submitted",
                    "submissions": submitted_submissions,
                    "active" : submitted_tab_active,
                    "time_heading": "Submitted",
                    "url": reverse('quests:submitted'),
                },
                {   "name": "Returned",
                    "submissions": returned_submissions,
                    "active" : returned_tab_active,
                    "time_heading": "Returned",
                    "url": reverse('quests:returned'),
                },
                {   "name": "Approved",
                    "submissions": approved_submissions,
                    "active" : approved_tab_active,
                    "time_heading": "Approved",
                    "url": reverse('quests:approved'),
                },
                {   "name": "Skipped",
                    "submissions": skipped_submissions,
                    "active" : skipped_tab_active,
                    "time_heading": "Transfered",
                    "url": reverse('quests:skipped'),
                },]

    quick_reply_form = SubmissionQuickReplyForm(request.POST or None)

    context = {
        "heading": "Quest Approval",
        "tab_list": tab_list,
        "quick_reply_form": quick_reply_form,
    }
    return render(request, "quest_manager/quest_approval.html" , context)


#########################################
#
#   QUEST SUBMISSION - STUDENT VIEWS
#
#########################################
@login_required
def complete(request, submission_id):
    submission = get_object_or_404(QuestSubmission, pk=submission_id)
    origin_path = submission.get_absolute_url()

    #http://stackoverflow.com/questions/22470637/django-show-validationerror-in-template
    if request.method == "POST":

        # form = CommentForm(request.POST or None, wysiwyg=True, label="")
        # form = SubmissionQuickReplyForm(request.POST)
        form = SubmissionForm(request.POST, request.FILES)

        if form.is_valid():
            comment_text = form.cleaned_data.get('comment_text')
            if not comment_text:
                if submission.quest.verification_required and not request.FILES:
                    messages.error(request, "Please read the Submission Instructions more carefully.  You are expected to submit something to complete this quest!")
                    return redirect(origin_path)
                else:
                    comment_text = "(submitted without comment)"
            comment_new = Comment.objects.create_comment(
                user = request.user,
                path = origin_path,
                text = comment_text,
                target = submission,
            )

            if request.FILES:
                file_list = request.FILES.getlist('files')
                for afile in file_list:
                    # print(afile)
                    newdoc = Document( docfile = afile, comment = comment_new)
                    newdoc.save()

            if 'complete' in request.POST:
                note_verb="completed"
                if submission.quest.verification_required:
                    note_verb += ", awaiting approval."
                else:
                    note_verb += " and automatically approved."

                icon="<i class='fa fa-shield fa-lg'></i>"
                affected_users = None
                submission.mark_completed() ###################
                if submission.quest.verification_required == False:
                    submission.mark_approved()

            elif 'comment' in request.POST:
                note_verb="commented on"
                icon="<span class='fa-stack'>" + \
                    "<i class='fa fa-shield fa-stack-1x'></i>" + \
                    "<i class='fa fa-comment-o fa-stack-2x text-info'></i>" + \
                    "</span>"
                if request.user.is_staff:
                    affected_users = [submission.user,]
                else:  # student comment
                    affected_users = User.objects.filter(is_staff=True)
            else:
                raise Http404("unrecognized submit button")

            notify.send(
                request.user,
                action=comment_new,
                target= submission,
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
    new_sub = QuestSubmission.objects.create_submission(request.user, quest)
    # if new_sub is None:
    #     print("This quest is not available, why is it showing up?")
    #     raise Http404 #shouldn't get here
    #should just do this, but the redirect is screwing up with the tour...
    #return redirect('quests:submission', submission_id = new_sub.id)

    if new_sub is None: #might be because quest was already started
        #so try to get the started Quest
        sub = QuestSubmission.objects.all_for_user_quest(request.user, quest).last()
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
def skip(request, submission_id):

    submission = get_object_or_404(QuestSubmission, pk=submission_id)
    # student can only do this if the button is turned on by a teacher
    # prevent students form skipping by guessing correct url
    # also make sure it's the student who owns the submission
    if (request.user.profile.game_lab_transfer_process_on and submission.user == request.user) or request.user.is_staff:

        #add default comment to submission
        origin_path = submission.get_absolute_url()
        comment_text = "(Quest skipped - no XP granted)"
        comment_new = Comment.objects.create_comment(
            user = request.user,
            path = origin_path,
            text = comment_text,
            target = submission,
        )

        #approve quest automatically, and mark as transfer.
        submission.mark_completed() ###################
        submission.mark_approved(transfer = True)

        messages.success(request,
            ("Transfer Successful.  No XP was granted for this quest."))
        if request.user.is_staff:
            return redirect("quests:approvals")
        return redirect("quests:quests")
    else:
        raise Http404

@login_required
def skipped(request, quest_id):
    '''A combination of the start and complete views, but automatically approved
    regardless, and game_lab_transfer = True
    '''
    quest = get_object_or_404(Quest, pk=quest_id)
    new_sub = QuestSubmission.objects.create_submission(request.user, quest)
    if new_sub is None: #might be because quest was already started
        #so try to get the started Quest
        submission = QuestSubmission.objects.all_for_user_quest(request.user, quest).last()
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
def drop(request, submission_id):
    sub = get_object_or_404(QuestSubmission, pk=submission_id)
    template_name = "quest_manager/questsubmission_confirm_delete.html"
    if sub.user != request.user:
        return redirect('quests:quests')
    if request.method=='POST':
        sub.delete()
        messages.error(request, ("Quest dropped."))
        return redirect('quests:quests')
    return render(request, template_name, {'submission':sub})


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
        main_comment_form = SubmissionForm(request.POST or None)
    #main_comment_form = CommentForm(request.POST or None, wysiwyg=True, label="")
    #reply_comment_form = CommentForm(request.POST or None, label="")
    # comments = Comment.objects.all_with_target_object(sub)

    context = {
        "heading": sub.quest.name,
        "submission": sub,
        # "comments": comments,
        "submission_form": main_comment_form,
        # "reply_comment_form": reply_comment_form,
    }
    return render(request, 'quest_manager/submission.html', context)

@login_required
def ajax(request):
    if request.is_ajax() and request.method == "POST":

        submission_count = QuestSubmission.objects.all_awaiting_approval().count()
        sub_data = {
            "count": submission_count,
        }
        json_data = json.dumps(sub_data)

        return HttpResponse(json_data, content_type='application/json' )
    else:
        raise Http404
