from django.http import HttpResponse
from django.views.generic import TemplateView,ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.core.urlresolvers import reverse_lazy

from suggestions.models import Suggestion

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
