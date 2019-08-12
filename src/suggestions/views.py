from badges.models import Badge, BadgeAssertion
from badges.views import grant_badge
from comments.forms import CommentForm
from comments.models import Comment
from courses.models import Semester
from djconfig import config
from notifications.signals import notify

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404, Http404
from django.utils import timezone
from .forms import SuggestionForm
from .models import Suggestion, Vote


@login_required
def comment(request, id):
    suggestion = get_object_or_404(Suggestion, pk=id)
    origin_path = suggestion.get_absolute_url()

    if request.method == "POST":
        form = CommentForm(request.POST)
        if form.is_valid():
            comment_text = form.cleaned_data.get('comment_text')
            # if not comment_text:
            #     comment_text = ""
            comment_new = Comment.objects.create_comment(
                user=request.user,
                path=origin_path,
                text=comment_text,
                target=suggestion,
            )

            if 'comment_button' in request.POST:
                note_verb = "commented on"
                # icon = "<i class='fa fa-lg fa-comment-o text-info'></i>"
                icon = "<span class='fa-stack'>" + \
                       "<i class='fa fa-lightbulb-o fa-stack-1x'></i>" + \
                       "<i class='fa fa-comment-o fa-stack-2x text-info'></i>" + \
                       "</span>"
                if request.user.is_staff:
                    # get other commenters on this announcement
                    affected_users = None
                else:  # student comment
                    affected_users = User.objects.filter(is_staff=True)
                    # should student comments also be sent to original suggester?
            else:
                raise Http404("unrecognized submit button")

            notify.send(
                request.user,
                action=comment_new,
                target=suggestion,
                recipient=suggestion.user,
                affected_users=affected_users,
                verb=note_verb,
                icon=icon,
            )
            messages.success(request, ("Suggestion " + note_verb))
            return redirect(origin_path)
        else:
            messages.error(request, "There was an error with your comment.")
            return redirect(origin_path)
    else:
        raise Http404


def suggestion_list_beta(request, id=None, completed=False):
    return suggestion_list(request, id, completed, beta=True)


@login_required
def suggestion_list(request, id=None, completed=False):
    template_name = 'suggestions/suggestion_list.html'

    # Are we within the dates of the active semester?
    semester = get_object_or_404(Semester, pk=config.hs_active_semester)

    if completed:
        suggestions = Suggestion.objects.all_completed()
    else:
        if request.user.is_staff:
            suggestions = Suggestion.objects.all().exclude(status=Suggestion.COMPLETED)
        else:
            suggestions = Suggestion.objects.all_for_student(request.user).exclude(status=Suggestion.COMPLETED)

    if id:
        active_id = int(id)
    else:
        active_id = None

    votes_total = request.user.vote_set.all().count()
    votes_this_semester = Vote.objects.all_this_semester(request.user).count()

    vote_badge = get_object_or_404(Badge, pk=config.hs_voting_badge)
    suggestion_badge = get_object_or_404(Badge, pk=config.hs_suggestion_badge)

    comment_form = CommentForm(request.POST or None, label="")
    context = {
        'comment_form': comment_form,
        'object_list': suggestions,
        'active_id': active_id,
        'completed_list': completed,
        'votes_total': votes_total,
        'suggestion_badge': suggestion_badge,
        'vote_badge': vote_badge,
        'num_votes': config.hs_num_votes,
        'votes_this_semester': votes_this_semester,
        'semester': semester,
    }
    return render(request, template_name, context)


def suggestion_list_completed(request, id=None):
    return suggestion_list(request, id, completed=True)


@login_required
def suggestion_create(request):
    template_name = 'suggestions/suggestion_form.html'
    form = SuggestionForm(request.POST or None)
    if form.is_valid():
        new_suggestion = form.save(commit=False)
        new_suggestion.user = request.user
        new_suggestion.status_timestamp = timezone.now()
        new_suggestion.save()

        icon = "<i class='fa fa-lg fa-fw fa-lightbulb-o'></i>"

        notify.send(
            request.user,
            # action=profile.user,
            target=new_suggestion,
            recipient=request.user,
            affected_users=User.objects.filter(is_staff=True),
            verb='suggested:',
            icon=icon,
        )

        messages.success(request, "Thank you for your suggestion! Mr C \
            has to it review before it will be publicly visible.")

        return redirect(new_suggestion.get_absolute_url())

    return render(request, template_name, {'form': form})


@staff_member_required
def suggestion_update(request, pk):
    template_name = 'suggestions/suggestion_form.html'
    suggestion = get_object_or_404(Suggestion, pk=pk)
    form = SuggestionForm(request.POST or None, instance=suggestion)
    if form.is_valid():
        form.save()
        return redirect(suggestion.get_absolute_url())
    return render(request, template_name, {'form': form})


@staff_member_required
def suggestion_delete(request, pk):
    template_name = 'suggestions/suggestion_confirm_delete.html'
    suggestion = get_object_or_404(Suggestion, pk=pk)
    if request.method == 'POST':
        suggestion.delete()
        return redirect('suggestions:list')
    return render(request, template_name, {'object': suggestion})


@staff_member_required
def suggestion_approve(request, id):
    suggestion = get_object_or_404(Suggestion, id=id)
    # Todo move this into the model, not view!
    suggestion.status = Suggestion.APPROVED
    suggestion.status_timestamp = timezone.now()
    suggestion.save()

    icon = "<span class='fa-stack'>" + \
           "<i class='fa fa-lightbulb-o fa-stack-1x'></i>" + \
           "<i class='fa fa-check fa-stack-2x text-success'></i>" + \
           "</span>"

    # TODO don't hardcode this, put it in the settings!
    suggestion_badge = get_object_or_404(Badge, pk=config.hs_suggestion_badge)
    grant_badge(request, suggestion_badge.id, suggestion.user.id)

    notify.send(
        request.user,
        # action=profile.user,
        target=suggestion,
        recipient=suggestion.user,
        affected_users=[suggestion.user, ],
        verb='approved',
        icon=icon,
    )
    messages.success(request, "Suggestion by " + str(suggestion.user) + " approved.")

    return redirect(suggestion.get_absolute_url())


@staff_member_required
def suggestion_complete(request, pk):
    suggestion = get_object_or_404(Suggestion, pk=pk)
    suggestion.status = Suggestion.COMPLETED
    suggestion.status_timestamp = timezone.now()
    suggestion.save()

    icon = "<span class='fa-stack'>" + \
           "<i class='fa fa-lightbulb-o fa-stack-1x'></i>" + \
           "<i class='fa fa-star-o fa-stack-2x text-success'></i>" + \
           "</span>"

    notify.send(
        request.user,
        # action=profile.user,
        target=suggestion,
        recipient=suggestion.user,
        affected_users=[suggestion.user, ],
        verb='completed',
        icon=icon,
    )
    messages.success(request, "Suggestion by " + str(suggestion.user) + " was completed!")

    return redirect(suggestion.get_absolute_url())


@staff_member_required
def suggestion_reject(request, pk):
    suggestion = get_object_or_404(Suggestion, pk=pk)
    suggestion.status = Suggestion.NOT_APPROVED
    suggestion.status_timestamp = timezone.now()
    suggestion.save()

    icon = "<span class='fa-stack'>" + \
           "<i class='fa fa-lightbulb-o fa-stack-1x'></i>" + \
           "<i class='fa fa-ban fa-stack-2x text-danger'></i>" + \
           "</span>"

    notify.send(
        request.user,
        # action=profile.user,
        target=suggestion,
        recipient=suggestion.user,
        affected_users=[suggestion.user, ],
        verb='rejected',
        icon=icon,
    )
    messages.error(request, "Suggestion by " + str(suggestion.user) + " was rejected.")

    return redirect(suggestion.get_absolute_url())


@login_required
def up_vote(request, id):
    return vote(request, id, 1)


@login_required
def down_vote(request, id):
    return vote(request, id, -1)


@login_required
def vote(request, id, vote_score):
    if not config.hs_suggestions_on:
        raise Http404

    suggestion = get_object_or_404(Suggestion, id=id)

    if vote_score == 1:
        str_vote = "+1"
    elif vote_score == -1:
        str_vote = "-1"
    else:
        raise Http404("There was an error with your attempt to vote.")

    success = Vote.objects.record_vote(suggestion, request.user, vote_score)
    check_votes_and_grant_badge(request, request.user)

    if not success:
        messages.error(request, "You already voted today!")
    else:
        messages.success(request, "You voted " + str_vote + " for " + str(suggestion))
        check_votes_and_grant_badge(request, request.user)

    return redirect("suggestions:list")


def check_votes_and_grant_badge(request, user):
    user_votes_this_sem = Vote.objects.all_this_semester(user).count()
    vote_badge = get_object_or_404(Badge, pk=config.hs_voting_badge)
    user_num_votes_badge = BadgeAssertion.objects.num_assertions(user, vote_badge, active_semester_only=True)
    votes_per_badge = config.hs_num_votes

    vote_badges_earned = int(user_votes_this_sem / votes_per_badge)

    if vote_badges_earned > user_num_votes_badge:
        grant_badge(request, vote_badge.id, user.id)
        return True
    else:
        return False
