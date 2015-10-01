from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User

from django.http import HttpResponse

from django.views.generic import TemplateView,ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView

from django.core.urlresolvers import reverse_lazy, reverse
from django.shortcuts import render, redirect, get_object_or_404

from notifications.signals import notify

from comments.forms import CommentForm
from comments.models import Comment

from .models import Suggestion
from .forms import SuggestionForm

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
                user = request.user,
                path = origin_path,
                text = comment_text,
                target = suggestion,
            )

            if 'comment_button' in request.POST:
                note_verb="commented on"
                # icon = "<i class='fa fa-lg fa-comment-o text-info'></i>"
                icon="<span class='fa-stack'>" + \
                    "<i class='fa fa-lightbulb-o fa-stack-1x'></i>" + \
                    "<i class='fa fa-comment-o fa-stack-2x text-info'></i>" + \
                    "</span>"
                if request.user.is_staff:
                    #get other commenters on this announcement
                    affected_users = None
                else:  # student comment
                    affected_users = User.objects.filter(is_staff=True)
            else:
                raise Http404("unrecognized submit button")

            notify.send(
                request.user,
                action=comment_new,
                target= suggestion,
                recipient=request.user,
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

@login_required
def suggestion_list(request, id=None):
    template_name='suggestions/suggestion_list.html'
    suggestions = Suggestion.objects.all()

    if id:
        active_id = int(id)
    else:
        active_id = None

    print("**********")
    print(active_id)

    comment_form = CommentForm(request.POST or None, label="")
    context = {
        'comment_form': comment_form,
        'object_list': suggestions,
        'active_id': active_id,
    }
    return render(request, template_name, context)

@login_required
def suggestion_create(request):
    template_name='suggestions/suggestion_form.html'
    form = SuggestionForm(request.POST or None)
    if form.is_valid():
        new_suggestion = form.save(commit=False)
        new_suggestion.user = request.user
        new_suggestion.save()
        return redirect('suggestions:list')
    return render(request, template_name, {'form':form})

@staff_member_required
def suggestion_update(request, pk):
    template_name='suggestions/suggestion_form.html'
    server = get_object_or_404(Suggestion, pk=pk)
    form = SuggestionForm(request.POST or None, instance=server)
    if form.is_valid():
        form.save()
        return redirect('suggestions:list')
    return render(request, template_name, {'form':form})

@staff_member_required
def suggestion_delete(request, pk):
    template_name='suggestions/suggestion_confirm_delete.html'
    suggestion = get_object_or_404(Suggestion, pk=pk)
    if request.method=='POST':
        suggestion.delete()
        return redirect('suggestions:list')
    return render(request, template_name, {'object':suggestion})


class SuggestionList(ListView):
    model = Suggestion

class SuggestionCreate(CreateView):
    model = Suggestion
    success_url = reverse_lazy('suggestions:list')
    fields = ['title', 'description', 'user']

class SuggestionUpdate(UpdateView):
    model = Suggestion
    success_url = reverse_lazy('suggestions:list')
    fields = ['title', 'description']

class SuggestionDelete(DeleteView):
    model = Suggestion
    success_url = reverse_lazy('suggestions:list')
