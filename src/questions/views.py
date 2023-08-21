# Create your views here.
from typing import Any, Dict

from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from hackerspace_online.decorators import StaffMemberRequiredMixin
from tenant.views import NonPublicOnlyViewMixin
from quest_manager.models import Quest
from .models import QuestionType, Question
from .forms import QuestionForm


class QuestionListView(NonPublicOnlyViewMixin, StaffMemberRequiredMixin, ListView):
    model = Question
    template_name = 'questions/question_list.html'
    context_object_name = 'questions'

    def get_queryset(self):
        quest_id = self.kwargs.get('quest_id')
        return Question.objects.filter(quest__id=quest_id)

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context_data = super().get_context_data(**kwargs)
        context_data['quest'] = get_object_or_404(Quest, pk=self.kwargs.get('quest_id'))
        context_data['type_choices'] = QuestionType.choices
        return context_data


class QuestionCreateView(NonPublicOnlyViewMixin, StaffMemberRequiredMixin, CreateView):
    template_name = 'questions/question_form.html'
    form_class = QuestionForm
    model = Question

    def get_form_kwargs(self) -> Dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs['question_type'] = self.kwargs.get('question_type')
        return kwargs

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        kwargs['heading'] = f"Create \"{self.kwargs.get('question_type').capitalize().replace('_', ' ')}\" Question"
        quest_id = self.kwargs.get('quest_id')
        kwargs['quest'] = get_object_or_404(Quest, pk=quest_id)
        kwargs['submit_btn_value'] = 'Create'
        return super().get_context_data(**kwargs)

    def form_valid(self, form):
        quest = get_object_or_404(Quest, pk=self.kwargs.get('quest_id'))
        form.instance.quest = quest
        form.instance.ordinal = Question.next_ordinal(quest)
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse_lazy('questions:list', kwargs={'quest_id': self.kwargs.get('quest_id')})


class QuestionUpdateView(NonPublicOnlyViewMixin, StaffMemberRequiredMixin, UpdateView):
    form_class = QuestionForm

    def get_queryset(self, *args, **kwargs):
        return Question.objects.filter(pk=self.kwargs.get('pk'))

    def get_form_kwargs(self) -> Dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs['question_type'] = self.get_object().type
        return kwargs

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        kwargs['heading'] = f'Update \"{self.get_object().get_type_display()}\" Question'
        kwargs['update_view'] = True
        kwargs['quest'] = self.get_object().quest
        kwargs['submit_btn_value'] = 'Update'
        return super().get_context_data(**kwargs)

    def get_success_url(self) -> str:
        return self.get_object().get_list_url()


class QuestionDeleteView(NonPublicOnlyViewMixin, StaffMemberRequiredMixin, DeleteView):
    model = Question
    template_name = 'questions/question_confirm_delete.html'

    def get_queryset(self, *args, **kwargs):
        return Question.objects.filter(pk=self.kwargs.get('pk'))

    def get_success_url(self) -> str:
        return reverse_lazy('questions:list',
                            kwargs={'quest_id': self.get_object().quest.id})
