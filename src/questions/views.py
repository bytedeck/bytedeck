from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from hackerspace_online.decorators import StaffMemberRequiredMixin
from siteconfig.models import SiteConfig
from tenant.views import NonPublicOnlyViewMixin
from quest_manager.models import Quest

from .forms import QuestionForm
from .models import Question, QuestionType


class SubmissionQuestionsEnabledMixin:
    """404 unless the deck has opted into submission questions via
    SiteConfig.enable_submission_questions (a deck-level feature flag, default off).

    Sits after NonPublicOnlyViewMixin (SiteConfig is a tenant-schema singleton, so the
    tenant check must run first) and before StaffMemberRequiredMixin, so on a deck with
    the feature off these URLs don't exist for anyone — no login redirect breadcrumbs.
    """

    def dispatch(self, request, *args, **kwargs):
        """404 the request when the feature flag is off."""
        if not SiteConfig.get().enable_submission_questions:
            raise Http404("Submission questions are not enabled on this deck.")
        return super().dispatch(request, *args, **kwargs)


class QuestionListView(NonPublicOnlyViewMixin, SubmissionQuestionsEnabledMixin, StaffMemberRequiredMixin, ListView):
    """Staff-only list of a quest's questions, with buttons to create each question type."""

    model = Question
    template_name = 'questions/question_list.html'
    context_object_name = 'questions'

    def get_queryset(self):
        """Only this quest's questions, in ordinal order (model Meta)."""
        return Question.objects.filter(quest_id=self.kwargs['quest_id'])

    def get_context_data(self, **kwargs):
        """Add the quest and the creatable question types."""
        context_data = super().get_context_data(**kwargs)
        context_data['quest'] = get_object_or_404(Quest, pk=self.kwargs['quest_id'])
        context_data['type_choices'] = QuestionType.choices
        return context_data


class QuestionFormViewMixin:
    """Shared bits of the create and update views: both render QuestionForm for a
    question type that must be validated before the form is built."""

    template_name = 'questions/question_form.html'
    form_class = QuestionForm

    def get_question_type(self):
        """Return the validated question type this view operates on. Subclasses override."""
        raise NotImplementedError

    def get_form_kwargs(self):
        """Pass the question type through to QuestionForm."""
        kwargs = super().get_form_kwargs()
        kwargs['question_type'] = self.get_question_type()
        return kwargs


class QuestionCreateView(NonPublicOnlyViewMixin, SubmissionQuestionsEnabledMixin, StaffMemberRequiredMixin, QuestionFormViewMixin, CreateView):
    """Staff-only creation of a question of the type named in the URL."""

    model = Question

    def get_question_type(self):
        """Return the type from the URL, or 404 if it isn't a supported question type."""
        question_type = self.kwargs['question_type']
        if question_type not in QuestionType.values:
            raise Http404(f"Question of type {question_type} not supported.")
        return question_type

    def get_context_data(self, **kwargs):
        """Add the quest, heading and submit-button label."""
        question_type_label = QuestionType(self.get_question_type()).label
        kwargs['heading'] = f'Create "{question_type_label}" Question'
        kwargs['quest'] = get_object_or_404(Quest, pk=self.kwargs['quest_id'])
        kwargs['submit_btn_value'] = 'Create'
        return super().get_context_data(**kwargs)

    def form_valid(self, form):
        """Attach the new question to the URL's quest, at the next ordinal."""
        quest = get_object_or_404(Quest, pk=self.kwargs['quest_id'])
        form.instance.quest = quest
        form.instance.ordinal = Question.next_ordinal(quest)
        return super().form_valid(form)

    def get_success_url(self):
        """Back to the quest's question list."""
        return reverse('questions:list', kwargs={'quest_id': self.kwargs['quest_id']})


class QuestionQuestScopedMixin:
    """Scope single-object views to the quest named in the URL, so a question can only be
    addressed through its own quest's URLs."""

    def get_queryset(self):
        """Only questions of the URL's quest."""
        return Question.objects.filter(quest_id=self.kwargs['quest_id'])


class QuestionUpdateView(
    NonPublicOnlyViewMixin, SubmissionQuestionsEnabledMixin, StaffMemberRequiredMixin,
    QuestionQuestScopedMixin, QuestionFormViewMixin, UpdateView,
):
    """Staff-only editing of an existing question (its type is fixed at creation)."""

    model = Question

    def get_question_type(self):
        """The existing question's type (not user-supplied). self.object is already set by
        UpdateView.get()/post() before the form is built."""
        return self.object.type

    def get_context_data(self, **kwargs):
        """Add the quest, heading and submit-button label."""
        kwargs['heading'] = f'Update "{self.object.get_type_display()}" Question'
        kwargs['update_view'] = True
        kwargs['quest'] = self.object.quest
        kwargs['submit_btn_value'] = 'Update'
        return super().get_context_data(**kwargs)

    def get_success_url(self):
        """Back to the quest's question list."""
        return self.object.get_list_url()


class QuestionDeleteView(NonPublicOnlyViewMixin, SubmissionQuestionsEnabledMixin, StaffMemberRequiredMixin, QuestionQuestScopedMixin, DeleteView):
    """Staff-only deletion of a question, with confirmation page.

    Students' existing answers survive (QuestionSubmission.question is SET_NULL) so markers
    can still see what was submitted before the question was removed.
    """

    model = Question
    template_name = 'questions/question_confirm_delete.html'

    def get_success_url(self):
        """Back to the quest's question list."""
        return reverse('questions:list', kwargs={'quest_id': self.kwargs['quest_id']})
