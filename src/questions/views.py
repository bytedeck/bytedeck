import os

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Max
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, View

from hackerspace_online.decorators import StaffMemberRequiredMixin
from tenant.views import NonPublicOnlyViewMixin, non_public_only_view
from quest_manager.models import Quest

from .forms import QuestionForm
from .models import Question, QuestionSubmission, QuestionType


class QuestionListView(NonPublicOnlyViewMixin, StaffMemberRequiredMixin, ListView):
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


class QuestionCreateView(NonPublicOnlyViewMixin, StaffMemberRequiredMixin, QuestionFormViewMixin, CreateView):
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


class QuestionUpdateView(NonPublicOnlyViewMixin, StaffMemberRequiredMixin, QuestionQuestScopedMixin, QuestionFormViewMixin, UpdateView):
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


class QuestionDeleteView(NonPublicOnlyViewMixin, StaffMemberRequiredMixin, QuestionQuestScopedMixin, DeleteView):
    """Staff-only deletion of a question, with confirmation page.

    Students' existing answers survive (QuestionSubmission.question is SET_NULL) so markers
    can still see what was submitted before the question was removed.
    """

    model = Question
    template_name = 'questions/question_confirm_delete.html'

    def get_success_url(self):
        """Back to the quest's question list."""
        return reverse('questions:list', kwargs={'quest_id': self.kwargs['quest_id']})


class QuestionMoveView(
    NonPublicOnlyViewMixin, StaffMemberRequiredMixin, QuestionQuestScopedMixin, View,
):
    """Staff-only POST endpoint that moves a question up or down within its quest's ordering.

    Students see a quest's questions in ascending ``ordinal`` order, so reordering is just
    swapping ordinals. The question swaps with the nearest question in the requested direction;
    ordinals aren't necessarily contiguous (deleting a question leaves a gap), so the neighbour is
    found by ordering rather than by ``ordinal ± 1``. Moving the first question up or the last
    question down is a no-op.

    There are two ways to ask for a move. The question list posts one in the background and
    swaps the answer into the page, which keeps the teacher's place in a long list across the
    several clicks a reorder takes (#2216): that request gets the re-rendered table as JSON. A
    plain form post gets a redirect to the list, which is the path a browser running no
    JavaScript takes.
    """

    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        """Swap the question's ordinal with its up/down neighbour (if any), then show the list.

        Args:
            request (HttpRequest): the move request. An ``X-Requested-With`` header of
                ``XMLHttpRequest`` asks for the table back instead of a redirect.
            *args: unused, passed through from the URL resolver.
            **kwargs: URL keywords; ``pk`` names the question and ``direction`` (which must be
                'up' or 'down') the way to move it.

        Returns:
            JsonResponse | HttpResponseRedirect: the re-rendered question table under
            ``question_table_html`` for an AJAX caller, otherwise a redirect to the list.

        Raises:
            Http404: if ``direction`` is neither 'up' nor 'down', or the question is not one of
                this quest's.
        """
        direction = self.kwargs['direction']
        if direction not in ('up', 'down'):
            raise Http404(f"Cannot move a question '{direction}'.")

        # get_queryset() (QuestionQuestScopedMixin) scopes to the URL's quest, so a question
        # can only be moved through its own quest's URL.
        question = get_object_or_404(self.get_queryset(), pk=self.kwargs['pk'])
        siblings = Question.objects.filter(quest_id=question.quest_id)
        if direction == 'up':
            neighbour = siblings.filter(ordinal__lt=question.ordinal).order_by('-ordinal').first()
        else:
            neighbour = siblings.filter(ordinal__gt=question.ordinal).order_by('ordinal').first()

        if neighbour is not None:
            self._swap_ordinals(question, neighbour)

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'question_table_html': self._render_table(request, question.quest)})

        return redirect('questions:list', quest_id=question.quest_id)

    @staticmethod
    def _render_table(request, quest):
        """Render the quest's questions as the list page shows them.

        The server re-renders the snippet the page was built from, so the order and which
        arrows are disabled at the ends of the list stay decided in one place. Working that
        out in JavaScript instead would be a second copy of the same rule, free to drift.

        Args:
            request (HttpRequest): the current request, so the template renders with the same
                context processors the page uses.
            quest (Quest): the quest whose questions to render.

        Returns:
            str: the rendered table.
        """
        return render_to_string(
            'questions/snippets/question_table.html',
            {
                'quest': quest,
                'questions': Question.objects.filter(quest_id=quest.id),
                # This table replaces the one on the question list, which is the page that
                # binds the move handler, so it needs the arrows the snippet otherwise
                # withholds. Without this a reorder would work once and then hand back a
                # table with nothing left to click (#2568).
                'can_reorder_questions': True,
            },
            request=request,
        )

    @staticmethod
    def _swap_ordinals(question, neighbour):
        """Swap two questions' ordinals inside a transaction, parking one at a temporary
        out-of-range ordinal first so the (quest, ordinal) unique constraint is never violated
        mid-swap (Postgres enforces it per statement, not just at commit)."""
        question_ordinal, neighbour_ordinal = question.ordinal, neighbour.ordinal
        # a value guaranteed not to collide with any existing ordinal in this quest
        temp_ordinal = Question.objects.filter(quest_id=question.quest_id).aggregate(Max('ordinal'))['ordinal__max'] + 1
        with transaction.atomic():
            question.ordinal = temp_ordinal
            question.full_clean()
            question.save()
            neighbour.ordinal = question_ordinal
            neighbour.full_clean()
            neighbour.save()
            question.ordinal = neighbour_ordinal
            question.full_clean()
            question.save()


@non_public_only_view
@login_required
def answer_file_download(request, pk):
    """Hand a web-file answer to the viewer as a download instead of opening it in the site.

    A question set to the "web" file type accepts HTML and SVG, which a browser will happily
    run scripts from if it navigates to them, in whatever origin serves them. Linking such an
    answer straight at its storage URL is how a student's file ends up executing in their
    marker's session. Everything the app links goes through here instead, and this responds
    with ``Content-Disposition: attachment``, so following the link saves the file rather than
    rendering it (#2559).

    Args:
        request (HttpRequest): the request.
        pk (int): id of the ``QuestionSubmission`` whose ``response_file`` to serve.

    Returns:
        FileResponse: the stored file, as an attachment.

    Raises:
        Http404: if the answer has no file, or the viewer is neither its owner nor staff.
    """
    answer = get_object_or_404(QuestionSubmission, pk=pk)
    if not answer.response_file:
        raise Http404("That answer doesn't have a file.")
    if not (request.user.is_staff or answer.quest_submission.user == request.user):
        raise Http404("I don't think you're supposed to be here....")

    return FileResponse(
        answer.response_file.open("rb"),
        as_attachment=True,
        filename=os.path.basename(answer.response_file.name),
    )
