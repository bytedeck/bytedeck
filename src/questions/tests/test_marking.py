"""Marking a submission's question answers right or wrong (#2933).

A teacher marks answers wrong with the X beside each one in the marking table, saved at once.
Returning or approving the quest turns the marks into a check or an X the student sees, and on a
return only the questions marked wrong come back for the student to answer again.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse

from model_bakery import baker

from quest_manager.models import QuestSubmission
from questions.forms import QuestionSubmissionFormsetFactory
from questions.models import Question, QuestionSubmission
from questions.tests.test_integration import QuestionSubmissionFlowTestBase
from questions.utils import finalize_answer_marks, questions_to_answer, sync_draft_question_submissions

User = get_user_model()


class AnswerMarkingTest(QuestionSubmissionFlowTestBase):
    """A teacher marks answers wrong; returning or approving sets the marks the student sees."""

    def hand_in(self, short_text="My answer", long_text="<p>My process.</p>", comment_text=""):
        """Hand the quest in as the student, answering what the page asks.

        Args:
            short_text (str): the short answer, if the page asks it.
            long_text (str): the long answer, if the page asks it.
            comment_text (str): the submission comment.

        Returns:
            HttpResponse: the completion's response.
        """
        self.client.force_login(self.test_student)
        # the page first, as a student opens it to hand the quest in: that is what gives a
        # returned submission its draft comment again
        self.client.get(reverse("quests:submission", args=[self.submission.id]))
        rows = list(sync_draft_question_submissions(self.submission))
        data = {
            "complete": True, "comment_text": comment_text,
            "question_submissions-TOTAL_FORMS": str(len(rows)),
            "question_submissions-INITIAL_FORMS": str(len(rows)),
            "question_submissions-MIN_NUM_FORMS": "0",
            "question_submissions-MAX_NUM_FORMS": "1000",
        }
        texts = {self.short_question.id: short_text, self.long_question.id: long_text}
        for i, row in enumerate(rows):
            data[f"question_submissions-{i}-id"] = str(row.id)
            data[f"question_submissions-{i}-response_text"] = texts.get(row.question_id, "")
        response = self.client.post(reverse("quests:complete", args=[self.submission.id]), data=data)
        self.submission.refresh_from_db()
        return response

    def answer(self, question):
        """The question's most recently handed-in answer."""
        return QuestionSubmission.objects.filter(
            quest_submission=self.submission, question=question, comment__isnull=False,
        ).latest("comment_id")

    def mark(self, answer, wrong=True):
        """Press the X beside an answer, as a teacher.

        Args:
            answer (QuestionSubmission): the answer to mark.
            wrong (bool): mark it wrong, or take the mark back.

        Returns:
            HttpResponse: the endpoint's response.
        """
        self.client.force_login(self.test_teacher)
        return self.client.post(
            reverse("questions:ajax_mark_answer", args=[answer.id]),
            data={"wrong": "true" if wrong else "false"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def review(self, button):
        """Return or approve the submission as a teacher.

        Args:
            button (str): "return_button" or "approve_button".
        """
        self.client.force_login(self.test_teacher)
        self.client.post(
            reverse("quests:approve", args=[self.submission.id]),
            data={"comment_text": "<p>Have a look at your answers.</p>", button: True},
        )
        self.submission.refresh_from_db()

    def student_page(self):
        """The student's submission page."""
        self.client.force_login(self.test_student)
        return self.client.get(reverse("quests:submission", args=[self.submission.id]))

    # the X

    def test_mark__staff_mark_an_answer_wrong_and_take_it_back(self):
        """The X saves at once, both ways, and says what the answer's mark now is."""
        self.hand_in()
        answer = self.answer(self.short_question)

        response = self.mark(answer)

        self.assertEqual(response.json(), {"marked_wrong": True})
        answer.refresh_from_db()
        self.assertTrue(answer.marked_wrong)
        self.assertIsNone(answer.is_correct, "the mark stays with staff until a return or approval")

        self.assertEqual(self.mark(answer, wrong=False).json(), {"marked_wrong": False})
        answer.refresh_from_db()
        self.assertFalse(answer.marked_wrong)

    def test_mark__a_student_cannot_mark(self):
        """Marking is for staff: a student's request is refused and changes nothing."""
        self.hand_in()
        answer = self.answer(self.short_question)

        response = self.client.post(
            reverse("questions:ajax_mark_answer", args=[answer.id]), data={"wrong": "true"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 403)
        answer.refresh_from_db()
        self.assertFalse(answer.marked_wrong)

    def test_mark__post_only(self):
        """A GET marks nothing."""
        self.hand_in()
        answer = self.answer(self.short_question)
        self.client.force_login(self.test_teacher)

        response = self.client.get(
            reverse("questions:ajax_mark_answer", args=[answer.id]), HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.assertEqual(response.status_code, 405)

    def test_mark__a_draft_answer_is_404(self):
        """An answer still being written, not yet handed in, has nothing to mark."""
        draft = sync_draft_question_submissions(self.submission).get(question=self.short_question)

        self.assertEqual(self.mark(draft).status_code, 404)

    def test_mark__an_answer_already_marked_is_404(self):
        """Once the quest is returned the marks are set, and the X can't change them."""
        self.hand_in()
        answer = self.answer(self.short_question)
        self.review("return_button")

        self.assertEqual(self.mark(answer).status_code, 404)

    def test_mark__an_earlier_hand_in_is_404(self):
        """Only the latest hand-in is being reviewed, so an earlier one's answers can't be marked,
        even ones that were never marked (handed in before marking existed)."""
        self.hand_in()
        earlier = self.answer(self.short_question)
        self.submission.mark_returned()  # a return that set no marks
        self.hand_in(short_text="Better answer")

        self.assertEqual(self.mark(earlier).status_code, 404)
        self.assertEqual(self.mark(self.answer(self.short_question)).status_code, 200)

    # returning and approving

    def test_return__sets_each_answer_right_or_wrong(self):
        """A return turns the X into a mark: the answer marked wrong is wrong, the rest right."""
        self.hand_in()
        self.mark(self.answer(self.short_question))

        self.review("return_button")

        self.assertIs(self.answer(self.short_question).is_correct, False)
        self.assertIs(self.answer(self.long_question).is_correct, True)

    def test_return__only_the_questions_marked_wrong_come_back(self):
        """After a return the student answers only what was marked wrong, under its own number,
        starting from what they wrote before."""
        self.hand_in(long_text="<p>First try.</p>")
        self.mark(self.answer(self.long_question))
        self.review("return_button")

        response = self.student_page()

        formset = response.context["question_formset"]
        self.assertEqual([form.question for form in formset.forms], [self.long_question])
        self.assertEqual(formset.forms[0].instance.response_text, "<p>First try.</p>")
        self.assertContains(response, "<strong>Question 2 <small>(optional)</small>:</strong>", html=True)
        self.assertNotContains(response, "<strong>Question 1:</strong>", html=True)

    def test_return__nothing_marked_wrong_brings_back_no_questions(self):
        """A quest returned with nothing marked wrong asks no questions again: the student only
        gets the comment box, and hands the quest back in with a comment."""
        self.hand_in()
        self.review("return_button")

        response = self.student_page()

        self.assertEqual(len(response.context["question_formset"].forms), 0)
        self.assertNotContains(response, "question-submission-list")
        self.assertNotContains(response, "Additional Submission Comments")
        self.assertContains(response, 'name="question_submissions-TOTAL_FORMS"')

        self.hand_in(comment_text="<p>Fixed, see my comment.</p>")
        self.assertTrue(self.submission.is_completed)

    def test_return__the_new_hand_in_has_only_the_redone_answers(self):
        """The answers handed in again are published with the new comment, ready to be marked,
        while the right ones stay with the earlier comment, marked right."""
        self.hand_in()
        self.mark(self.answer(self.short_question))
        self.review("return_button")

        self.hand_in(short_text="A better answer")

        latest = QuestionSubmission.objects.filter(quest_submission=self.submission).latest("comment_id")
        latest_cycle = QuestionSubmission.objects.filter(quest_submission=self.submission, comment_id=latest.comment_id)
        self.assertEqual([answer.question for answer in latest_cycle], [self.short_question])
        self.assertEqual(latest_cycle.get().response_text, "A better answer")
        self.assertTrue(latest_cycle.get().awaiting_mark)
        self.assertIs(self.answer(self.long_question).is_correct, True)

        self.review("approve_button")
        self.assertIs(self.answer(self.short_question).is_correct, True)

    def test_return__a_question_added_since_comes_back(self):
        """A question added after the hand-in has no answer to judge, so it comes back even when
        nothing was marked wrong."""
        self.hand_in()
        self.review("return_button")
        added = baker.make(Question, quest=self.quest, ordinal=3, type="short_answer", instructions="<p>New?</p>")

        self.assertEqual(questions_to_answer(self.submission), [added])

    def test_return__answers_never_marked_all_come_back(self):
        """A hand-in returned without its answers being marked (as returns were before marking
        existed) brings every question back."""
        self.hand_in()
        self.submission.mark_returned()

        self.assertEqual(questions_to_answer(self.submission), [self.short_question, self.long_question])

    def test_return__an_approved_hand_in_never_marked_brings_every_question_back(self):
        """Returning a quest approved before answers were marked leaves its answers unmarked and
        brings every question back, rather than counting each of them right."""
        self.hand_in()
        self.submission.mark_approved()  # approved without its answers being marked
        self.review("return_button")

        self.assertIsNone(self.answer(self.short_question).is_correct)
        self.assertIsNone(self.answer(self.long_question).is_correct)
        self.assertEqual(questions_to_answer(self.submission), [self.short_question, self.long_question])

    def test_return__an_approved_quest_brings_back_what_approval_marked_wrong(self):
        """Returning a quest approved with an answer marked wrong brings that question back: the
        marks approval set stand."""
        self.hand_in()
        self.mark(self.answer(self.long_question))
        self.review("approve_button")
        self.review("return_button")

        self.assertFalse(self.submission.is_approved)
        self.assertEqual(questions_to_answer(self.submission), [self.long_question])

    def test_approve__marks_show_to_the_student_once_approved(self):
        """A teacher can mark an answer wrong and still approve: the student then sees a check on
        the right answer and an X on the wrong one, and saw neither while the quest awaited
        review."""
        self.hand_in()
        self.mark(self.answer(self.short_question))

        pending = self.student_page()
        self.assertNotContains(pending, 'class="answer-mark')
        self.assertNotContains(pending, "data-mark-url")

        self.review("approve_button")
        approved = self.student_page()

        self.assertContains(approved, '<span class="sr-only">Correct</span>', count=1)
        self.assertContains(approved, '<span class="sr-only">Marked wrong</span>', count=1)

    def test_marking_table__staff_get_the_x_until_the_marks_are_set(self):
        """While the quest awaits review, staff see the X beside each answer, pressed for the one
        marked wrong; once approved they see the marks instead."""
        self.hand_in()
        self.mark(self.answer(self.short_question))

        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))

        self.assertContains(response, 'aria-pressed="true"', count=1)
        self.assertContains(response, 'aria-pressed="false"', count=1)
        self.assertContains(response, reverse("questions:ajax_mark_answer", args=[self.answer(self.short_question).id]))

        self.review("approve_button")
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertNotContains(response, "data-mark-url")
        self.assertContains(response, '<span class="sr-only">Marked wrong</span>', count=1)

    # the helpers

    def test_finalize_answer_marks__only_the_latest_hand_in(self):
        """Marks are set on the hand-in under review, and an earlier one keeps whatever it has,
        marks or none."""
        self.hand_in()
        earlier = self.answer(self.short_question)
        self.submission.mark_returned()
        self.hand_in(short_text="Again")

        self.assertEqual(finalize_answer_marks(self.submission), 2)

        earlier.refresh_from_db()
        self.assertIsNone(earlier.is_correct)
        self.assertEqual(finalize_answer_marks(self.submission), 0, "marks already set stay as they are")

    def test_finalize_answer_marks__not_for_a_submission_back_with_the_student(self):
        """A returned submission has no hand-in under review: approving it from there leaves its
        latest answers as they are, even ones never marked."""
        self.hand_in()
        self.submission.mark_returned()  # a return that set no marks

        self.assertEqual(finalize_answer_marks(self.submission), 0)
        self.assertIsNone(self.answer(self.short_question).is_correct)

    def test_mark__refused_once_the_marks_are_set_meanwhile(self):
        """A mark that arrives after a return or approval has set the marks (from another tab, or
        another teacher) changes nothing and says so, rather than leaving the X out of step with
        the mark the student sees."""
        self.hand_in()
        answer = self.answer(self.short_question)
        finalize_answer_marks(self.submission)  # the marks are set between the check and the write

        with patch.object(QuestionSubmission, "awaiting_mark", new=property(lambda answer: True)):
            response = self.mark(answer)

        self.assertEqual(response.status_code, 404)
        answer.refresh_from_db()
        self.assertFalse(answer.marked_wrong)
        self.assertIs(answer.is_correct, True)

    def test_finalize_answer_marks__nothing_handed_in(self):
        """A submission with no published answers has nothing to mark."""
        self.assertEqual(finalize_answer_marks(self.submission), 0)

    def test_sync__a_file_answer_comes_back_empty(self):
        """A file answer marked wrong comes back as an empty answer: a file input can't start
        with the earlier file, which still shows with the earlier comment."""
        file_question = baker.make(Question, quest=self.quest, ordinal=3, type="file_upload", required=False)
        self.hand_in()
        answer = self.answer(file_question)
        QuestionSubmission.objects.filter(pk=answer.pk).update(response_text="", marked_wrong=True)
        self.review("return_button")

        drafts = sync_draft_question_submissions(self.submission)

        self.assertEqual([draft.question for draft in drafts], [file_question])
        self.assertFalse(drafts.get().response_file)
        self.assertEqual(drafts.get().response_text, "")

    def test_sync__a_short_answer_comes_back_as_typed(self):
        """A short answer is stored HTML-escaped, but comes back in its text input as the student
        typed it, rather than showing the escaped entities."""
        self.hand_in(short_text="R&D <3")
        answer = self.answer(self.short_question)
        self.assertEqual(answer.response_text, "R&amp;D &lt;3")  # as it is stored
        self.mark(answer)
        self.review("return_button")

        response = self.student_page()

        formset = response.context["question_formset"]
        self.assertEqual(formset.forms[0].instance.response_text, "R&D <3")
        self.assertContains(response, 'value="R&amp;D &lt;3"')


class QuestionNumberTest(QuestionSubmissionFlowTestBase):
    """A question's number is its place in the quest, whatever its ordinal."""

    def test_number__counts_questions_in_ordinal_order(self):
        """Ordinals can have gaps; the numbers don't."""
        third = baker.make(Question, quest=self.quest, ordinal=40, type="short_answer")

        self.assertEqual([self.short_question.number, self.long_question.number, third.number], [1, 2, 3])

    def test_answer_fields__labelled_with_their_question_number(self):
        """An answer field's aria-label carries its question's number, also when only some
        questions are being answered (#2933)."""
        rows = QuestionSubmission.objects.filter(question=self.long_question, quest_submission=self.submission)
        formset = QuestionSubmissionFormsetFactory(instance=self.submission, queryset=rows)

        self.assertIn("Response to question 2", str(formset.forms[0]["response_text"]))


class AwaitingMarkTest(QuestionSubmissionFlowTestBase):
    """Which answers a teacher can still mark."""

    def test_awaiting_mark__not_once_the_submission_is_approved(self):
        """An approved submission's answers are past marking, even ones never marked."""
        answer = baker.make(QuestionSubmission, quest_submission=self.submission, question=self.short_question,
                            comment=self.submission.draft_comment)
        QuestSubmission.objects.filter(pk=self.submission.pk).update(is_completed=True, is_approved=True)

        self.assertFalse(QuestionSubmission.objects.get(pk=answer.pk).awaiting_mark)
