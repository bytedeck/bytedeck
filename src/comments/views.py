import os

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from hackerspace_online.decorators import staff_member_required

from notifications.signals import notify
from tenant.views import non_public_only_view

from .models import Comment, Document


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


# @non_public_only_view
# @login_required
# def comment_thread(request, id):
#     comment = get_object_or_404(Comment, id=id)
#     form = CommentForm(label="Reply")
#     context = {
#         "comment": comment,
#         "heading": "Comment Thread",
#         "form": form,
#     }
#     return render(request, "comments/comment_thread.html", context)


# @non_public_only_view
# @login_required
# def comment_create(request):
#     if request.method == "POST" and request.user.is_authenticated:
#         parent_id = request.POST.get('parent_id')
#         # quest_id = request.POST.get('quest_id')
#         target_content_type_id = request.POST.get('target_content_type_id')
#         target_object_id = request.POST.get('target_id')
#         origin_path = request.POST.get('origin_path')
#         success_url = request.POST.get('success_url')
#         success_message = request.POST.get('success_message', "Thanks for your comment!")

#         try:
#             # quest = Quest.objects.get(id = quest_id)
#             content_type = ContentType.objects.get_for_id(target_content_type_id)
#             target = content_type.get_object_for_this_type(id=target_object_id)
#         except:  # noqa
#             # TODO deal with this
#             target = None

#         parent_comment = None
#         if parent_id is not None:
#             try:
#                 parent_comment = Comment.objects.get(id=parent_id)
#             except:  # noqa
#                 # TODO deal with this
#                 parent_comment = None

#             if parent_comment is not None:
#                 target = parent_comment.get_target_object()
#                 if success_url is None:
#                     success_url = parent_comment.get_absolute_url()

#         icon = "<i class='fa fa-lg fa-comment-o text-info'></i>"

#         form = CommentForm(request.POST)
#         if form.is_valid():
#             comment_text = form.cleaned_data.get('comment_text')
#             if parent_comment is not None:
#                 comment_new = Comment.objects.create_comment(
#                     user=request.user,
#                     path=parent_comment.get_origin(),
#                     text=comment_text,
#                     # quest = quest,
#                     target=target,
#                     parent=parent_comment,
#                 )
#                 affected_users = parent_comment.get_affected_users()
#                 notify.send(
#                     request.user,
#                     action=comment_new,
#                     target=parent_comment,
#                     recipient=parent_comment.user,
#                     affected_users=affected_users,
#                     verb='replied to',
#                     icon=icon,
#                 )
#                 # messages.success(request, "Thanks for your reply! <a class='alert-link' href='http://google.com'>Google!</a>", extra_tags='safe') # noqa
#                 messages.success(request, success_message)
#                 return HttpResponseRedirect(success_url)
#             else:
#                 comment_new = Comment.objects.create_comment(
#                     user=request.user,
#                     path=origin_path,
#                     text=comment_text,
#                     # quest = quest
#                     target=target,
#                 )
#                 # Fix this to send to all staff
#                 affected_users = affected_users = User.objects.filter(is_staff=True)
#                 notify.send(
#                     request.user,
#                     action=comment_new,
#                     target=target,
#                     recipient=request.user,
#                     affected_users=affected_users,
#                     verb='commented on',
#                     icon=icon,
#                 )
#                 messages.success(request, success_message)

#                 if success_url is None:
#                     success_url = comment_new.get_absolute_url()

#                 return HttpResponseRedirect(success_url)
#         else:
#             messages.error(request, "There was an error with your comment. Did you type anything in the box?")
#             if origin_path is None:
#                 return HttpResponseRedirect(parent_comment.get_absolute_url())
#             return HttpResponseRedirect(origin_path)

#     else:
#         raise Http404


def _may_download(user, comment):
    """Whether this user may fetch an attachment on this comment.

    Args:
        user (User): the signed-in viewer.
        comment (Comment): the comment the attachment hangs off, or None for an attachment on
            no comment at all, which belongs to nobody and is nobody's to fetch.

    Returns:
        bool: True if they can already see the thread the attachment is part of.
    """
    from announcements.models import Announcement  # locally: announcements imports this app

    if comment is None:
        return False
    if user.is_staff or comment.user_id == user.id:
        return True
    target = comment.target_object
    # a submission belongs to one student, and every attachment on their own thread is theirs
    # to open, including one their teacher attached
    if getattr(target, "user_id", None) == user.id:
        return True
    # An announcement's thread is the whole deck's, so its attachments are everyone's, as long
    # as the announcement is one they can actually see. A draft, an unreleased, an archived or
    # an expired one is not on their announcements page, and this url carries a guessable id,
    # so it must not be the way to reach what that page withholds.
    return (
        isinstance(target, Announcement)
        and Announcement.objects.get_for_students().filter(pk=target.pk).exists()
    )


@non_public_only_view
@login_required
def document_download(request, id):
    """Hand a script-capable attachment to the viewer as a download instead of opening it.

    The submission comment's "Attach files" box takes web files, because whole cohorts of
    quests ask students to hand in a page or a vector drawing through it. Served inline from
    the app's own origin, such a file runs whatever script it carries in the session of
    whoever follows the link, normally the teacher marking the work. Everything the app links
    that could do that goes through here instead, and this responds with
    ``Content-Disposition: attachment``, so following the link saves the file (#2726).

    Who may follow it is everyone who can see the thread it hangs off: staff, whoever wrote the
    comment, the student whose submission it is (so a teacher's attached example is still theirs
    to open), and anyone at all when the thread is that of an announcement they can see, which
    is the whole deck's.
    A url carrying a row id is guessable in a way a storage path is not, so this is checked
    rather than left open, even though the stored file itself is reachable by anyone holding
    its storage url.

    Args:
        request (HttpRequest): the request.
        id (int): id of the Document to serve.

    Returns:
        FileResponse: the stored file, as an attachment.

    Raises:
        Http404: if the attachment is not one of the files served this way (an image is linked
            at its storage url and must keep opening in a tab rather than downloading), or the
            viewer is not one of the people above.
    """
    document = get_object_or_404(Document, pk=id)
    if not document.is_script_capable:
        raise Http404("That attachment is not served as a download.")
    if not _may_download(request.user, document.comment):
        raise Http404("I don't think you're supposed to be here....")

    return FileResponse(
        document.docfile.open("rb"),
        as_attachment=True,
        filename=os.path.basename(document.docfile.name),
    )
