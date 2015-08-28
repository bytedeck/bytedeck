from django.conf import settings

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType

from django.core.mail import send_mail
from django.core.urlresolvers import reverse_lazy

from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect, Http404
from django.template import RequestContext, loader
from django.utils.decorators import method_decorator
from django.views.generic.edit import CreateView, DeleteView, UpdateView


from comments.models import Comment
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
        print(context)
        return context

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(QuestUpdate, self).dispatch(*args, **kwargs)

@login_required
def quest_list(request):
    available_quests = Quest.objects.get_available(request.user)
    in_progress_submissions = QuestSubmission.objects.all_not_completed(request.user)
    completed_submissions = QuestSubmission.objects.all_completed(request.user)
    # in_progress_quests = [s.quest for s in in_progress_submissions]
    # completed_quests = [s.quest for s in completed_submissions]
    context = {
        "heading": "Quests",
        "available_quests": available_quests,
        "in_progress_submissions": in_progress_submissions,
        "completed_submissions": completed_submissions,
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

# @staff_member_required
# def quest_update(request, quest_id):
#     quest_to_update = get_object_or_404(Quest, pk=quest_id)
#     form = QuestForm(request.POST or None, request.FILES or None)
#     if form.is_valid():
#         form.save()
#         return redirect('quests:quests')
#     context = {
#         "heading": "Update Quest",
#         "form": form,
#         "submit_btn_value": "Update",
#     }
#     return render(request, "quest_manager/quest_form.html", context)

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
            messages.error(request, "There was an error with your comment.")
            return redirect(origin_path)
    else:
        raise Http404

@staff_member_required
def approvals(request):

    approval_submissions = QuestSubmission.objects.all_awaiting_approval()
    approved_submissions = QuestSubmission.objects.all_approved()
    returned_submissions = QuestSubmission.objects.all_returned()

    tab_list = [{"name": "Awaiting Approval", "submissions": approval_submissions,},
                { "name": "Returned", "submissions": returned_submissions,},
                { "name": "Approved", "submissions": approved_submissions,},]

    main_comment_form = CommentForm(request.POST or None, wysiwyg=True, label="")
    quick_reply_form = SubmissionQuickReplyForm(request.POST or None)

    context = {
        "heading": "Quest Approval",
        "tab_list": tab_list,
        "main_comment_form": main_comment_form,
        "quick_reply_form": quick_reply_form,
    }
    return render(request, "quest_manager/quest_approval.html" , context)


########### QUEST SUBMISSION VIEWS ###############################
@login_required
def complete(request, submission_id):
    submission = get_object_or_404(QuestSubmission, pk=submission_id)
    origin_path = submission.get_absolute_url()

    if request.method == "POST":

        form = CommentForm(request.POST or None, wysiwyg=True, label="")
        # form = SubmissionQuickReplyForm(request.POST)

        if form.is_valid():
            comment_text = form.cleaned_data.get('comment_text')
            if not comment_text:
                comment_text = ""
            comment_new = Comment.objects.create_comment(
                user = request.user,
                path = origin_path,
                text = comment_text,
                target = submission,
            )

            if 'complete' in request.POST:
                note_verb="completed"
                icon="<i class='fa fa-shield fa-lg'></i>"
                submission.mark_completed() ###################
                affected_users = None
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
            messages.error(request, "There was an error with your comment.")
            return redirect(origin_path)
    else:
        raise Http404

@login_required
def start(request, quest_id):

    quest = get_object_or_404(Quest, pk=quest_id)
    new_sub = QuestSubmission.objects.create_submission(request.user, quest)
    if new_sub is None:
        print("This quest is not available, why is it showing up?")
        raise Http404 #shouldn't get here
    return redirect('quests:submission', submission_id = new_sub.id)

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
def submission(request, submission_id):
    # sub = QuestSubmission.objects.get(id = submission_id)
    sub = get_object_or_404(QuestSubmission, pk=submission_id)
    if sub.user != request.user and not request.user.is_staff:
        return redirect('quests:quests')

    # comment_form = SubmissionForm(request.POST or None)
    main_comment_form = CommentForm(request.POST or None, wysiwyg=True, label="")
    reply_comment_form = CommentForm(request.POST or None, label="")
    # comments = Comment.objects.all_with_target_object(sub)

    context = {
        "heading": sub.quest.name,
        "submission": sub,
        # "comments": comments,
        "submission_form": main_comment_form,
        # "reply_comment_form": reply_comment_form,
    }
    return render(request, 'quest_manager/submission.html', context)




## Demo of sending email
# @login_required
# def email_demo(request):
#     subject = "Test email from Hackerspace Online"
#     from_email = ("Timberline's Digital Hackerspace <" +
#         settings.EMAIL_HOST_USER +
#         ">")
#     to_emails = [from_email]
#     email_message = "from %s: %s via %s" %(
#         "Dear Bloggins", "sup", from_email)
#
#     html_email_message = "<h1> if this is showing you received an HTML messaage</h1>"
#
#     send_mail(subject,
#         email_message,
#         from_email,
#         to_emails,
#         html_message = html_email_message,
#         fail_silently=False)
#
#     context = {
#         "email_to" : to_emails,
#         "email_from": from_email,
#         "email_message":email_message,
#         "html_email_message": html_email_message
#
#     }
#
#     return render(request, "email_demo.html", context)


##
