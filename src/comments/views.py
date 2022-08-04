from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.http import Http404
from django.shortcuts import (HttpResponseRedirect, get_object_or_404,
                              redirect, render)

from hackerspace_online.decorators import staff_member_required

from notifications.signals import notify
from tenant.views import non_public_only_view

from .forms import CommentForm
from .models import Comment


@non_public_only_view
@staff_member_required
def unflag(request, id):
    comment = get_object_or_404(Comment, pk=id)
    comment.unflag()
    return redirect(comment.path)


@non_public_only_view
@staff_member_required
def delete(request, id, template_name='comments/confirm_delete.html'):
    comment = get_object_or_404(Comment, pk=id)
    path = comment.path
    if request.method == 'POST':
        comment.delete()
        return redirect(path)
    return render(request, template_name, {'object': comment})


@non_public_only_view
@staff_member_required
def flag(request, id):
    comment = get_object_or_404(Comment, pk=id)
    comment.flag()

    icon = "<span class='fa-stack'>" + \
           "<i class='fa fa-comment-o fa-flip-horizontal fa-stack-1x'></i>" + \
           "<i class='fa fa-ban fa-stack-2x text-danger'></i>" + \
           "</span>"

    notify.send(
        request.user,
        target=comment,
        recipient=comment.user,
        affected_users=[comment.user, ],
        verb='flagged',
        icon=icon,
    )

    return redirect(comment.path)


@non_public_only_view
@login_required
def comment_thread(request, id):
    comment = get_object_or_404(Comment, id=id)
    form = CommentForm(label="Reply")
    context = {
        "comment": comment,
        "heading": "Comment Thread",
        "form": form,
    }
    return render(request, "comments/comment_thread.html", context)


@non_public_only_view
@login_required
def comment_create(request):
    if request.method == "POST" and request.user.is_authenticated:
        parent_id = request.POST.get('parent_id')
        # quest_id = request.POST.get('quest_id')
        target_content_type_id = request.POST.get('target_content_type_id')
        target_object_id = request.POST.get('target_id')
        origin_path = request.POST.get('origin_path')
        success_url = request.POST.get('success_url')
        success_message = request.POST.get('success_message', "Thanks for your comment!")

        try:
            # quest = Quest.objects.get(id = quest_id)
            content_type = ContentType.objects.get_for_id(target_content_type_id)
            target = content_type.get_object_for_this_type(id=target_object_id)
        except:  # noqa
            # TODO deal with this
            target = None

        parent_comment = None
        if parent_id is not None:
            try:
                parent_comment = Comment.objects.get(id=parent_id)
            except:  # noqa
                # TODO deal with this
                parent_comment = None

            if parent_comment is not None:
                target = parent_comment.get_target_object()
                if success_url is None:
                    success_url = parent_comment.get_absolute_url()

        icon = "<i class='fa fa-lg fa-comment-o text-info'></i>"

        form = CommentForm(request.POST)
        if form.is_valid():
            comment_text = form.cleaned_data.get('comment_text')
            if parent_comment is not None:
                comment_new = Comment.objects.create_comment(
                    user=request.user,
                    path=parent_comment.get_origin(),
                    text=comment_text,
                    # quest = quest,
                    target=target,
                    parent=parent_comment,
                )
                affected_users = parent_comment.get_affected_users()
                notify.send(
                    request.user,
                    action=comment_new,
                    target=parent_comment,
                    recipient=parent_comment.user,
                    affected_users=affected_users,
                    verb='replied to',
                    icon=icon,
                )
                # messages.success(request, "Thanks for your reply! <a class='alert-link' href='http://google.com'>Google!</a>", extra_tags='safe') # noqa
                messages.success(request, success_message)
                return HttpResponseRedirect(success_url)
            else:
                comment_new = Comment.objects.create_comment(
                    user=request.user,
                    path=origin_path,
                    text=comment_text,
                    # quest = quest
                    target=target,
                )
                # Fix this to send to all staff
                affected_users = affected_users = User.objects.filter(is_staff=True)
                notify.send(
                    request.user,
                    action=comment_new,
                    target=target,
                    recipient=request.user,
                    affected_users=affected_users,
                    verb='commented on',
                    icon=icon,
                )
                messages.success(request, success_message)

                if success_url is None:
                    success_url = comment_new.get_absolute_url()

                return HttpResponseRedirect(success_url)
        else:
            messages.error(request, "There was an error with your comment. Did you type anything in the box?")
            if origin_path is None:
                return HttpResponseRedirect(parent_comment.get_absolute_url())
            return HttpResponseRedirect(origin_path)

    else:
        raise Http404
