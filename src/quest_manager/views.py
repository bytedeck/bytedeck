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


from badges.models import BadgeAssertion
from comments.models import Comment, Document
from comments.forms import CommentForm
from notifications.signals import notify

from .forms import QuestForm, SubmissionForm, SubmissionQuickReplyForm
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
    if request.user.is_staff:
        available_quests = Quest.objects.all()
    else:
        available_quests = Quest.objects.get_available(request.user)

    in_progress_submissions = QuestSubmission.objects.all_not_completed(request.user)
    completed_submissions = QuestSubmission.objects.all_completed(request.user)

    active_quest_id = 0
    active_submission_id=0

    available_tab_active=True
    inprogress_tab_active=False
    completed_tab_active=False

    if quest_id is not None:
        active_quest_id = int(quest_id)
    elif submission_id is not None:
        active_submission_id = int(submission_id)
        active_sub = get_object_or_404(QuestSubmission, pk=submission_id)
        if active_sub in in_progress_submissions:
            inprogress_tab_active = True
            available_tab_active= False
        elif active_sub in completed_submissions:
            completed_tab_active = True
            available_tab_active= False
    elif '/inprogress/' in request.path_info:
        inprogress_tab_active = True
        available_tab_active= False
    elif '/completed/' in request.path_info:
        completed_tab_active = True
        available_tab_active= False

    context = {
        "heading": "Quests",
        "available_quests": available_quests,
        "in_progress_submissions": in_progress_submissions,
        "completed_submissions": completed_submissions,
        "active_q_id": active_quest_id,
        "active_id": active_submission_id,
        "available_tab_active": available_tab_active,
        "inprogress_tab_active": inprogress_tab_active,
        "completed_tab_active": completed_tab_active,

        # "in_progress_quests": in_progress_quests,
        # "completed_quests": completed_quests,
    }
    return render(request, "quest_manager/quests.html" , context)

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
        return redirect('quests:quests')
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

        form = SubmissionQuickReplyForm(request.POST)

        if form.is_valid():
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
                text = comment_text,
                target = submission
            )

            # don't say "with" if no comment was entered
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
            messages.success(request, ("Quest " + note_verb))
            return redirect("quests:approvals")
        else:
            messages.error(request, "There was an error with your comment. Maybe you need to type something?")
            return redirect(origin_path)
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

@staff_member_required
def approvals(request):

    submitted_submissions = []
    approved_submissions = []
    returned_submissions = []
    gamelab_submissions = []

    submitted_tab_active=True
    returned_tab_active=False
    approved_tab_active=False
    gamelab_tab_active=False

    page = request.GET.get('page')
    # if '/submitted/' in request.path_info:
    #     approval_submissions = QuestSubmission.objects.all_awaiting_approval()
    if '/returned/' in request.path_info:
        returned_submissions = QuestSubmission.objects.all_returned()
        returned_tab_active = True
        submitted_tab_active= False
        returned_submissions = paginate(returned_submissions, page)
    elif '/approved/' in request.path_info:
        approved_submissions = QuestSubmission.objects.all_approved()
        approved_tab_active = True
        submitted_tab_active= False
        approved_submissions = paginate(approved_submissions, page)
    elif '/gamelab/' in request.path_info:
        gamelab_submissions = QuestSubmission.objects.all_gamelab()
        gamelab_tab_active = True
        submitted_tab_active= False
        gamelab_submissions = paginate(gamelab_submissions, page)
    else:
        submitted_submissions = QuestSubmission.objects.all_awaiting_approval()
        submitted_submissions = paginate(submitted_submissions, page)
        # approval_submissions = QuestSubmission.objects.all_awaiting_approval()
        # approved_submissions = QuestSubmission.objects.all_approved()
        # returned_submissions = QuestSubmission.objects.all_returned()

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
                {   "name": "GameLab",
                    "submissions": gamelab_submissions,
                    "active" : gamelab_tab_active,
                    "time_heading": "Transfered",
                    "url": reverse('quests:gamelab'),
                },]

    # main_comment_form = CommentForm(request.POST or None, wysiwyg=True, label="")
    quick_reply_form = SubmissionQuickReplyForm(request.POST or None)

    context = {
        "heading": "Quest Approval",
        "tab_list": tab_list,
        # "main_comment_form": main_comment_form,
        "quick_reply_form": quick_reply_form,
    }
    return render(request, "quest_manager/quest_approval.html" , context)


########### QUEST SUBMISSION VIEWS ###############################
@login_required
def complete(request, submission_id):
    submission = get_object_or_404(QuestSubmission, pk=submission_id)
    origin_path = submission.get_absolute_url()

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
                newdoc = Document( docfile = request.FILES['docfile'],
                                   comment = comment_new)
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
            messages.error(request, "There was an error with your comment.  Maybe your image or attachment was too big? 16MB max!")
            return redirect(origin_path)
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

    # comment_form = SubmissionForm(request.POST or None)
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
def gamelabtransfer(request, quest_id):
    '''A combination of the start and complete views, but automatically approved
    regardless, and game_lab_transfer = True'''
    quest = get_object_or_404(Quest, pk=quest_id)
    new_sub = QuestSubmission.objects.create_submission(request.user, quest)
    if new_sub is None: #might be because quest was already started
        #so try to get the started Quest
        submission = QuestSubmission.objects.all_for_user_quest(request.user, quest).last()
        if submission is None:
            raise Http404
    else:
        submission = new_sub

    #make sure another user isn't hacking in with urls
    if submission.user != request.user and not request.user.is_staff:
        return redirect('quests:quests')

    #add default comment to submission
    origin_path = submission.get_absolute_url()
    comment_text = "(GameLab transfer)"
    comment_new = Comment.objects.create_comment(
        user = request.user,
        path = origin_path,
        text = comment_text,
        target = submission,
    )

    #approve quest automatically, and mark as transfer.
    submission.mark_completed() ###################
    submission.mark_approved(transfer = True)

    messages.success(request, ("Transfer Successful"))
    return redirect("quests:quests")


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
