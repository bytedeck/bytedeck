from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required

from django.http import HttpResponse

from django.views.generic import TemplateView,ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView

from django.core.urlresolvers import reverse_lazy
from django.shortcuts import render, redirect, get_object_or_404

from .models import Suggestion
from .forms import SuggestionForm

@login_required
def suggestion_list(request):
    template_name='suggestions/suggestion_list.html'
    suggestions = Suggestion.objects.all()
    context = {}
    context['object_list'] = suggestions
    return render(request, template_name, context)

@login_required
def suggestion_create(request):
    template_name='suggestions/suggestion_form.html'
    form = SuggestionForm(request.POST or None)
    if form.is_valid():
        form.save()
        return redirect('suggestions:list')
    return render(request, template_name, {'form':form})

@login_required
def suggestion_update(request, pk):
    template_name='suggestions/suggestion_form.html'
    server = get_object_or_404(Suggestion, pk=pk)
    form = SuggestionForm(request.POST or None, instance=server)
    if form.is_valid():
        form.save()
        return redirect('suggestions:list')
    return render(request, template_name, {'form':form})

@login_required
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
