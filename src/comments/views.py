from django.shortcuts import render, HttpResponseRedirect

from django.contrib import messages
from django.contrib.auth.decorators import login_required

# Create your views here.
from notifications.signals import notify
from quest_manager.models import Quest

from .models import Comment
from .forms import CommentForm


@login_required
def comment_thread(request, id):
    comment = Comment.objects.get(id=id)
    form = CommentForm()
    context = {
        "comment": comment,
        "heading": "Comment Thread",
        "form": form,
    }
    return render(request, "comments/comment_thread.html", context)


def comment_create(request):
    if request.method == "POST" and request.user.is_authenticated():
        parent_id = request.POST.get('parent_id')
        quest_id = request.POST.get('quest_id')
        origin_path = request.POST.get('origin_path')

        try:
            quest = Quest.objects.get(id = quest_id)

        except:
            quest = None

        parent_comment = None
        if parent_id is not None:
            try:
                parent_comment = Comment.objects.get(id=parent_id)
            except:
                parent_comment = None

            if parent_comment is not None and parent_comment.quest is not None:
                quest = parent_comment.quest
        form = CommentForm(request.POST)
        if form.is_valid():
            comment_text = form.cleaned_data['new_comment']
            if parent_comment is not None:
                comment_new = Comment.objects.create_comment(
                    user = request.user,
                    path = parent_comment.get_origin,
                    text = comment_text,
                    quest = quest,
                    parent=parent_comment
                    )
                notify.send(request.user, recipient='somernadomuser', action='Responded to user')
                messages.success(request, "Thanks for your reply! <a class='alert-link' href='http://google.com'>Google!</a>", extra_tags='safe')
                return HttpResponseRedirect(parent_comment.get_absolute_url())
            else:
                comment_new = Comment.objects.create_comment(
                    user = request.user,
                    path = origin_path,
                    text = comment_text,
                    quest = quest
                    )
                notify.send(request.user, recipient=None, action='New comment added')
                messages.success(request, "Thanks for commenting!")
                return HttpResponseRedirect(comment_new.get_absolute_url())
        else:
            messages.error(request, "There was an error with your comment.")
            return HttpResponseRedirect(origin_path)

    else:
        raise Http404
