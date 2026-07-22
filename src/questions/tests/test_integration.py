import json

from django.contrib.auth import get_user_model
from django.urls import reverse

from django_tenants.test.client import TenantClient
from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase, ViewTestUtilsMixin
from quest_manager.models import Quest, QuestSubmission
from questions.models import Question, QuestionSubmission
from questions.utils import sync_draft_question_submissions
from siteconfig.models import SiteConfig

User = get_user_model()


class QuestionSubmissionFlowTestBase(ViewTestUtilsMixin, ByteDeckTenantTestCase):
    """Shared fixtures for the submission-flow integration tests: an opted-in deck, a quest
    with a required short answer + an optional long answer, and a student mid-submission."""

    @classmethod
    def setUpTestData(cls):
        """Enable the feature; teacher, student, quest with two questions."""
        config = SiteConfig.get()
        config.enable_submission_questions = True
        config.save()

        cls.test_teacher = User.objects.create_user("test_teacher", password="password", is_staff=True)
        cls.test_student = User.objects.create_user("test_student", password="password")

        cls.quest = baker.make(Quest, name="Questful Quest", verification_required=True)
        cls.short_question = baker.make(
            Question, quest=cls.quest, ordinal=1, type="short_answer", required=True,
            instructions="<p>What is your website URL?</p>",
        )
        cls.long_question = baker.make(
            Question, quest=cls.quest, ordinal=2, type="long_answer", required=False,
            instructions="<p>Describe your process.</p>",
        )

    def setUp(self):
        """Tenant client, and a fresh in-progress submission with its draft comment (created
        the same way the submission view does)."""
        self.client = TenantClient(self.tenant)
        self.submission = baker.make(QuestSubmission, quest=self.quest, user=self.test_student)
        # visiting the submission page creates the draft comment and (with the feature on)
        # the draft answer rows; do it through the view so tests exercise the real flow
        self.client.force_login(self.test_student)
        self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.submission.refresh_from_db()

    def formset_data(self, short_text="My answer", long_text=""):
        """Valid POST data for the two-question answer formset of self.submission."""
        rows = list(sync_draft_question_submissions(self.submission))
        data = {
            "question_submissions-TOTAL_FORMS": str(len(rows)),
            "question_submissions-INITIAL_FORMS": str(len(rows)),
            "question_submissions-MIN_NUM_FORMS": "0",
            "question_submissions-MAX_NUM_FORMS": "1000",
        }
        texts = {self.short_question.id: short_text, self.long_question.id: long_text}
        for i, row in enumerate(rows):
            data[f"question_submissions-{i}-id"] = str(row.id)
            data[f"question_submissions-{i}-response_text"] = texts.get(row.question_id, "")
        return data


class SubmissionPageFormsetTest(QuestionSubmissionFlowTestBase):
    """The submission page renders the answer formset in the right situations only."""

    def test_submission_page__student_sees_question_formset(self):
        """A student working a quest with questions sees one answer form per question,
        including each question's instructions."""
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertEqual(response.status_code, 200)
        formset = response.context["question_formset"]
        self.assertEqual(len(formset.forms), 2)
        self.assertContains(response, "What is your website URL?")
        self.assertContains(response, "Describe your process.")

    def test_submission_page__no_formset_when_flag_off(self):
        """With the deck's flag off, the submission page has no answer formset."""
        config = SiteConfig.get()
        config.enable_submission_questions = False
        config.save()
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertIsNone(response.context["question_formset"])

    def test_submission_page__no_formset_without_questions(self):
        """A quest with no questions renders no formset even with the flag on."""
        plain_quest = baker.make(Quest)
        plain_sub = baker.make(QuestSubmission, quest=plain_quest, user=self.test_student)
        response = self.client.get(reverse("quests:submission", args=[plain_sub.id]))
        self.assertIsNone(response.context["question_formset"])

    def test_submission_page__no_formset_for_staff(self):
        """Staff viewing a student's submission see the marking form, not the answer formset."""
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertIsNone(response.context["question_formset"])

    def test_submission_page__no_formset_when_awaiting_approval(self):
        """Answers can't be edited while the submission awaits approval."""
        self.submission.mark_completed()
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertIsNone(response.context["question_formset"])

    def test_submission_page__question_added_mid_draft_appears(self):
        """A question the teacher adds after the student started shows up on next render."""
        baker.make(Question, quest=self.quest, ordinal=3, type="short_answer", required=True)
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertEqual(len(response.context["question_formset"].forms), 3)

    def test_submission_page__question_deleted_mid_draft_excluded(self):
        """Deleting a question mid-draft removes its form without crashing the page."""
        self.short_question.delete()
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertEqual(response.status_code, 200)
        formset = response.context["question_formset"]
        self.assertEqual(len(formset.forms), 1)
        self.assertEqual(formset.forms[0].question, self.long_question)


class CompleteWithQuestionsTest(QuestionSubmissionFlowTestBase):
    """Completing a quest validates, saves, and publishes the question answers."""

    def complete_url(self):
        """The submission's complete URL."""
        return reverse("quests:complete", args=[self.submission.id])

    def test_complete__valid_answers_no_comment_succeeds(self):
        """Answered questions count as submission content: no additional comment or
        attachment is demanded, and the answers publish with the completion comment."""
        response = self.client.post(
            self.complete_url(), data={"complete": True, "comment_text": "", **self.formset_data()})
        self.assertRedirects(response, reverse("quests:quests"))

        self.submission.refresh_from_db()
        self.assertTrue(self.submission.is_completed)

        published = QuestionSubmission.objects.filter(
            quest_submission=self.submission, comment__isnull=False)
        self.assertEqual(published.count(), 2)
        answer = published.get(question=self.short_question)
        self.assertEqual(answer.response_text, "My answer")
        # published with the completion comment, which targets the submission
        self.assertEqual(answer.comment.target_object, self.submission)

    def test_complete__missing_required_answer_rerenders_with_errors(self):
        """A blank required answer blocks completion and re-renders the page with the
        formset's errors visible; nothing is published or lost."""
        response = self.client.post(
            self.complete_url(),
            data={"complete": True, "comment_text": "<p>a comment</p>", **self.formset_data(short_text="")})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You must provide a text response")

        self.submission.refresh_from_db()
        self.assertFalse(self.submission.is_completed)
        self.assertFalse(QuestionSubmission.objects.filter(
            quest_submission=self.submission, comment__isnull=False).exists())

    def test_complete__flag_off_ignores_formset(self):
        """With the deck's flag off, completion behaves exactly as before questions existed:
        a comment (or file) is still demanded and no answers are touched."""
        config = SiteConfig.get()
        config.enable_submission_questions = False
        config.save()

        response = self.client.post(
            self.complete_url(), data={"complete": True, "comment_text": ""})
        # blocked by the attach-something-or-comment rule (verification_required quest)
        self.assertRedirects(response, self.submission.get_absolute_url())
        self.submission.refresh_from_db()
        self.assertFalse(self.submission.is_completed)

    def test_complete__quest_without_questions_unchanged(self):
        """A quest with no questions completes exactly as before when a comment is left."""
        plain_quest = baker.make(Quest, verification_required=True)
        plain_sub = baker.make(QuestSubmission, quest=plain_quest, user=self.test_student)
        self.client.get(reverse("quests:submission", args=[plain_sub.id]))  # create draft
        response = self.client.post(
            reverse("quests:complete", args=[plain_sub.id]),
            data={"complete": True, "comment_text": "<p>done!</p>"})
        self.assertRedirects(response, reverse("quests:quests"))
        plain_sub.refresh_from_db()
        self.assertTrue(plain_sub.is_completed)

    def test_complete__resubmission_gets_fresh_draft_rows(self):
        """After a return, the next cycle gets fresh draft rows while the previous cycle's
        published answers stay attached to their comment."""
        self.client.post(
            self.complete_url(), data={"complete": True, "comment_text": "", **self.formset_data()})
        self.submission.refresh_from_db()
        first_cycle = set(QuestionSubmission.objects.filter(
            quest_submission=self.submission, comment__isnull=False).values_list("id", flat=True))
        self.assertEqual(len(first_cycle), 2)

        self.submission.mark_returned()
        # student revisits the page: fresh cycle
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        formset = response.context["question_formset"]
        self.assertEqual(len(formset.forms), 2)
        new_ids = {form.instance.id for form in formset.forms}
        self.assertTrue(new_ids.isdisjoint(first_cycle))
        # the published first-cycle answers are untouched
        self.assertEqual(QuestionSubmission.objects.filter(
            quest_submission=self.submission, comment__isnull=False).count(), 2)


class AnswerAutosaveTest(QuestionSubmissionFlowTestBase):
    """ajax_save_draft persists draft text answers alongside the draft comment."""

    def autosave(self, answers, submission=None):
        """POST an autosave (as the AJAX request the view demands); returns the response."""
        submission = submission or self.submission
        return self.client.post(
            reverse("quests:ajax_save_draft"),
            data={
                "comment": "<p>draft</p>",
                "submission_id": submission.id,
                "answers": json.dumps(answers),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_autosave__saves_changed_answer_text(self):
        """A changed draft answer is saved and reported as 'Draft saved'."""
        row = sync_draft_question_submissions(self.submission).get(question=self.short_question)
        response = self.autosave({
            "question_submissions-0-id": str(row.id),
            "question_submissions-0-response_text": "draft answer",
        })
        self.assertEqual(json.loads(response.content)["result"], "Draft saved")
        row.refresh_from_db()
        self.assertEqual(row.response_text, "draft answer")

    def test_autosave__cannot_touch_other_users_rows(self):
        """An answer row belonging to another student's submission can't be draft-saved
        through someone else's submission id."""
        other_student = User.objects.create_user("other_student", password="password")
        other_sub = baker.make(QuestSubmission, quest=self.quest, user=other_student)
        other_row = baker.make(
            QuestionSubmission, quest_submission=other_sub, question=self.short_question)

        self.autosave({
            "question_submissions-0-id": str(other_row.id),
            "question_submissions-0-response_text": "tampered",
        })
        other_row.refresh_from_db()
        self.assertEqual(other_row.response_text, "")

    def test_autosave__published_rows_untouched(self):
        """Published answers (already attached to a comment) can't be altered by autosave."""
        self.client.post(
            reverse("quests:complete", args=[self.submission.id]),
            data={"complete": True, "comment_text": "", **self.formset_data()})
        published = QuestionSubmission.objects.filter(
            quest_submission=self.submission, comment__isnull=False).get(question=self.short_question)

        self.autosave({
            "question_submissions-0-id": str(published.id),
            "question_submissions-0-response_text": "revisionism",
        })
        published.refresh_from_db()
        self.assertEqual(published.response_text, "My answer")

    def test_autosave__malformed_answers_ignored(self):
        """Malformed answers JSON is ignored rather than crashing the autosave."""
        response = self.client.post(
            reverse("quests:ajax_save_draft"),
            data={"comment": "<p>draft</p>", "submission_id": self.submission.id, "answers": "{not json"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)


class AnswerDisplayTest(QuestionSubmissionFlowTestBase):
    """Published answers display with their comment for students and markers."""

    def complete_with_answers(self):
        """Complete the submission with valid answers."""
        self.client.post(
            reverse("quests:complete", args=[self.submission.id]),
            data={"complete": True, "comment_text": "", **self.formset_data()})
        self.submission.refresh_from_db()

    def test_display__student_sees_published_answers(self):
        """After submitting, the student sees their answers under the submission comment."""
        self.complete_with_answers()
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertContains(response, "Question Answers:")
        self.assertContains(response, "My answer")

    def test_display__staff_see_answers_with_marker_notes(self):
        """Markers see the answers plus the question's solution and marker notes."""
        self.short_question.solution_text = "An URL like https://example.com"
        self.short_question.marker_notes = "<p>Check it loads.</p>"
        self.short_question.save()
        self.complete_with_answers()

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertContains(response, "My answer")
        self.assertContains(response, "An URL like https://example.com")
        self.assertContains(response, "Check it loads.")

    def test_display__student_does_not_see_marker_notes(self):
        """Solutions and marker notes stay staff-only in the answers display."""
        self.short_question.solution_text = "SECRET SOLUTION"
        self.short_question.save()
        self.complete_with_answers()
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertContains(response, "My answer")
        self.assertNotContains(response, "SECRET SOLUTION")

    def test_display__nothing_when_flag_off(self):
        """Turning the flag off hides the answers display (data is kept, nothing renders)."""
        self.complete_with_answers()
        config = SiteConfig.get()
        config.enable_submission_questions = False
        config.save()
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertNotContains(response, "Question Answers:")
        # the data survives for re-enabling
        self.assertEqual(QuestionSubmission.objects.filter(
            quest_submission=self.submission, comment__isnull=False).count(), 2)


class QuestDetailEntryPointTest(QuestionSubmissionFlowTestBase):
    """The quest detail page links staff to question management when the feature is on."""

    def test_quest_detail__staff_see_manage_questions_button(self):
        """Staff get the Submission Questions panel with its Manage Questions link."""
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse("quests:quest_detail", args=[self.quest.id]))
        self.assertContains(response, "Manage Questions")
        self.assertContains(response, reverse("questions:list", args=[self.quest.id]))

    def test_quest_detail__student_sees_no_manage_button(self):
        """Students don't see the staff questions panel (checked on the submission page,
        which embeds the same quest detail content and renders for the owning student)."""
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Manage Questions")

    def test_quest_detail__staff_no_panel_when_flag_off(self):
        """With the flag off the staff panel disappears."""
        config = SiteConfig.get()
        config.enable_submission_questions = False
        config.save()
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse("quests:quest_detail", args=[self.quest.id]))
        self.assertNotContains(response, "Manage Questions")
