import json
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest, QuestSubmission
from questions.forms import QuestionSubmissionFormsetFactory, SHORT_ANSWER_MAX_LENGTH
from questions.models import Question, QuestionSubmission
from questions.utils import save_draft_file_answers, sync_draft_question_submissions

User = get_user_model()


class QuestionSubmissionFlowTestBase(ByteDeckTenantTestCase):
    """Shared fixtures for the submission-flow integration tests: a quest with a required
    short answer + an optional long answer, and a student mid-submission."""

    @classmethod
    def setUpTestData(cls):
        """A teacher, a student, and a quest with two questions."""
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
        self.submission = baker.make(QuestSubmission, quest=self.quest, user=self.test_student)
        # visiting the submission page creates the draft comment and the draft answer
        # rows; do it through the view so tests exercise the real flow
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

    def file_field_name(self, question):
        """The formset field name of the given question's file input, found by the question's
        position among the submission's draft rows (the order the formset is built in)."""
        rows = list(sync_draft_question_submissions(self.submission))
        index = next(i for i, row in enumerate(rows) if row.question_id == question.id)
        return f"question_submissions-{index}-response_file"


class SubmissionPageFormsetTest(QuestionSubmissionFlowTestBase):
    """The submission page renders the answer formset in the right situations only."""

    def test_submission_page__student_sees_question_formset(self):
        """A student working a quest with questions sees one answer form per question,
        including each question's instructions."""
        response = self.assert200("quests:submission", args=[self.submission.id])
        formset = response.context["question_formset"]
        self.assertEqual(len(formset.forms), 2)
        self.assertContains(response, "What is your website URL?")
        self.assertContains(response, "Describe your process.")

    def test_submission_page__short_answer_tells_the_student_its_limit(self):
        """A short answer says how long it may be, where the student is typing it (#2401).

        The input itself enforces the limit silently, by refusing further keystrokes, so the
        sentence under it is the only thing that tells a student the rule before they hit it.
        """
        response = self.assert200("quests:submission", args=[self.submission.id])

        self.assertContains(response, f"Up to {SHORT_ANSWER_MAX_LENGTH} characters.")

    def test_submission_page__short_answer_hint_is_the_counter_hook(self):
        """The short answer's input and hint render as the pair the live counter joins (#2482).

        The counter script on the submission page finds each maxlength-carrying input's hint
        by looking up `hint_<input id>`, so this pins that exact association: the short
        answer's own input id, the maxlength on that same tag, and a hint whose id is the
        input's with the `hint_` prefix. If crispy's hint id or the widget's maxlength ever
        changes shape, the counter dies silently: this failure is the only thing that would
        say so.
        """
        response = self.assert200("quests:submission", args=[self.submission.id])
        content = response.content.decode()

        rows = list(sync_draft_question_submissions(self.submission))
        index = next(i for i, row in enumerate(rows) if row.question_id == self.short_question.id)
        input_id = f"id_question_submissions-{index}-response_text"

        input_tag = re.search(rf'<input[^>]*\bid="{input_id}"[^>]*>', content)
        self.assertIsNotNone(input_tag, f"no input with id {input_id} on the page")
        self.assertIn(f'maxlength="{SHORT_ANSWER_MAX_LENGTH}"', input_tag.group(0))
        self.assertContains(response, f'id="hint_{input_id}"')

    def test_submission_page__summernote_assets_load_once(self):
        """The answer editors ride on the assets the comment box already loads (#2169).

        Crispy renders a form's media alongside the form, so a long-answer question repeats the
        whole summernote asset set in the middle of the page on top of the copy in the head.
        """
        content = self.assert200("quests:submission", args=[self.submission.id]).content.decode()

        self.assertEqual(content.count("summernote.min.js"), 1)

    def test_submission_page__no_formset_without_questions(self):
        """A quest with no questions renders no formset."""
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
        response = self.assert200("quests:submission", args=[self.submission.id])
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

    def test_complete__uploaded_file_survives_a_failed_submit(self):
        """A file attached alongside a blank required answer is kept, not silently dropped (#2165).

        Browsers never repopulate a file input, so without saving the upload the student's file
        would vanish on the re-render with no notice: the required file error would reappear
        even though they did attach one, or an optional answer would publish as empty.
        """
        file_question = baker.make(
            Question, quest=self.quest, ordinal=3, type="file_upload", required=False,
            instructions="<p>Attach your work.</p>", allowed_file_type="image",
        )
        upload = SimpleUploadedFile("my-work.png", b"file_content", content_type="image/png")

        # short answer left blank, so the formset is invalid and the page re-renders
        data = {"complete": True, "comment_text": "<p>a comment</p>", **self.formset_data(short_text="")}
        data[self.file_field_name(file_question)] = upload
        response = self.client.post(self.complete_url(), data=data)

        self.assertEqual(response.status_code, 200)

        file_row = QuestionSubmission.objects.get(
            quest_submission=self.submission, question=file_question, comment__isnull=True)
        self.assertTrue(file_row.response_file, "the attached file was dropped on re-render")
        self.assertIn("my-work", file_row.response_file.name)
        # and the re-rendered page shows it, so the student can see it was kept
        self.assertContains(response, "my-work")

    def test_complete__rejected_file_is_not_saved(self):
        """A file rejected for its type is not kept, so its error still applies on the retry (#2165).

        Only uploads that pass the question's own file-type check are worth keeping; storing a
        rejected one would let the student submit again without fixing it.
        """
        file_question = baker.make(
            Question, quest=self.quest, ordinal=3, type="file_upload", required=False,
            instructions="<p>Attach an image.</p>", allowed_file_type="image",
        )
        not_an_image = SimpleUploadedFile("notes.txt", b"file_content", content_type="text/plain")

        data = {"complete": True, "comment_text": "<p>a comment</p>", **self.formset_data()}
        data[self.file_field_name(file_question)] = not_an_image
        response = self.client.post(self.complete_url(), data=data)

        self.assertEqual(response.status_code, 200)
        file_row = QuestionSubmission.objects.get(
            quest_submission=self.submission, question=file_question, comment__isnull=True)
        self.assertFalse(file_row.response_file)

    def test_complete__file_field_left_alone_keeps_the_saved_file(self):
        """Re-submitting without re-choosing a file keeps the one already saved (#2165).

        The student's second attempt only fixes the text answer, leaving the file input empty
        as browsers force them to; that must not wipe the file kept from the first attempt.
        """
        file_question = baker.make(
            Question, quest=self.quest, ordinal=3, type="file_upload", required=True,
            instructions="<p>Attach your work.</p>", allowed_file_type="image",
        )

        # first attempt: file attached, required text answer blank, so it bounces back
        first = {"complete": True, "comment_text": "<p>a comment</p>", **self.formset_data(short_text="")}
        first[self.file_field_name(file_question)] = SimpleUploadedFile(
            "my-work.png", b"file_content", content_type="image/png")
        self.client.post(self.complete_url(), data=first)

        file_row = QuestionSubmission.objects.get(
            quest_submission=self.submission, question=file_question, comment__isnull=True)
        kept_name = file_row.response_file.name
        self.assertTrue(kept_name)

        # second attempt: text answer fixed, file input left empty
        response = self.client.post(
            self.complete_url(),
            data={"complete": True, "comment_text": "<p>a comment</p>", **self.formset_data()})
        self.assertRedirects(response, reverse("quests:quests"))

        file_row.refresh_from_db()
        self.assertEqual(file_row.response_file.name, kept_name)
        # and it published with the completion, rather than as an empty answer
        self.assertIsNotNone(file_row.comment_id)

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

    def test_autosave__file_answer_rows_reject_text(self):
        """A crafted autosave can't stash text on a file-upload row: only short/long answer
        rows accept response_text. Otherwise a file question could be turned into free-text
        content, letting a student bypass the submission's 'attach or comment' requirement
        without uploading the required file."""
        file_question = baker.make(
            Question, quest=self.quest, ordinal=3, type="file_upload", required=False,
            instructions="<p>Upload a file.</p>")
        file_row = sync_draft_question_submissions(self.submission).get(question=file_question)
        self.autosave({
            "question_submissions-0-id": str(file_row.id),
            "question_submissions-0-response_text": "sneaky text answer",
        })
        file_row.refresh_from_db()
        self.assertEqual(file_row.response_text, "")

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

    def test_autosave__non_dict_answers_payload_ignored(self):
        """A valid-JSON but non-object answers payload (e.g. a list) is ignored, not a 500."""
        # json.loads("[1, 2, 3]") is a list, so answers.items() would blow up (500) without the
        # dict guard; status 200 is the regression assertion.
        response = self.autosave([1, 2, 3])
        self.assertEqual(response.status_code, 200)

    def test_autosave__non_integer_id_ignored(self):
        """A row whose client-supplied id isn't an integer is skipped, not a 500."""
        row = sync_draft_question_submissions(self.submission).get(question=self.short_question)
        # filter(pk="abc") would raise ValueError (500) without the int() guard; the row is
        # left untouched and the request succeeds.
        response = self.autosave({
            "question_submissions-0-id": "abc",
            "question_submissions-0-response_text": "draft answer",
        })
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.response_text, "")

    def test_autosave__irrelevant_and_incomplete_answer_keys_ignored(self):
        """Answer keys that don't match the formset naming, and rows sent without an id or
        without their text, are skipped without saving anything."""
        row = sync_draft_question_submissions(self.submission).get(question=self.short_question)
        response = self.autosave({
            "unrelated-key": "ignored",
            "question_submissions-0-id": str(row.id),  # id without response_text
            "question_submissions-1-response_text": "text without id",
        })
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.response_text, "")

    def test_autosave__unchanged_answer_not_resaved(self):
        """An answer identical to what's stored isn't rewritten (no needless save)."""
        row = sync_draft_question_submissions(self.submission).get(question=self.short_question)
        row.response_text = "already saved"
        row.save()
        row.refresh_from_db()
        last_edit = row.datetime_last_edit

        self.autosave({
            "question_submissions-0-id": str(row.id),
            "question_submissions-0-response_text": "already saved",
        })
        row.refresh_from_db()
        self.assertEqual(row.datetime_last_edit, last_edit)


class DraftFileSaveTest(QuestionSubmissionFlowTestBase):
    """Saving a draft stores the files chosen on the page, not only the text (#1459)."""

    def save_draft(self, extra=None):
        """POST an ajax draft save carrying the answer formset's fields, as the Save Draft
        button does now that it sends the whole form as FormData.

        Args:
            extra: a dict merged over the default payload, adding or overriding fields
                (how a test attaches its files).

        Returns:
            The view's response, whose JSON body is the draft-save contract.
        """
        data = {
            "comment": "<p>draft words</p>",
            "submission_id": self.submission.id,
            **self.formset_data(short_text="draft title"),
        }
        data.update(extra or {})
        return self.client.post(
            reverse("quests:ajax_save_draft"), data=data,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_save_draft__stores_a_file_answer(self):
        """A file chosen on a file-upload question is stored on its draft row by Save Draft,
        unpublished, and the response names it so the page can show it was kept."""
        file_question = baker.make(
            Question, quest=self.quest, ordinal=3, type="file_upload",
            required=False, allowed_file_type="all",
        )
        sync_draft_question_submissions(self.submission)
        field_name = self.file_field_name(file_question)

        response = self.save_draft(
            {field_name: SimpleUploadedFile("sketch.png", b"file_content", content_type="image/png")})

        payload = json.loads(response.content)
        self.assertEqual(payload["result"], "Draft saved")
        row = QuestionSubmission.objects.get(quest_submission=self.submission, question=file_question)
        self.assertIn("sketch", row.response_file.name)
        self.assertIsNone(row.comment_id, "a draft-saved answer must not be published")
        self.assertIn("sketch", payload["saved_answer_files"][field_name])

    def test_save_draft__stores_comment_attachments(self):
        """A file chosen in the comment's Attach files field is stored on the draft comment
        by Save Draft, where completing the quest publishes it from."""
        response = self.save_draft(
            {"attachments": SimpleUploadedFile("notes.pdf", b"file_content", content_type="application/pdf")})

        payload = json.loads(response.content)
        self.assertEqual(payload["result"], "Draft saved")
        documents = list(self.submission.draft_comment.document_set.all())
        self.assertEqual(len(documents), 1)
        self.assertIn("notes", documents[0].docfile.name)
        self.assertEqual(payload["saved_attachments"], ["notes.pdf"])

    def test_save_draft__rejects_a_file_the_question_does_not_accept(self):
        """A file whose type the question refuses is not stored, and the response carries
        the field's own error so the page can say why."""
        image_question = baker.make(
            Question, quest=self.quest, ordinal=3, type="file_upload",
            required=False, allowed_file_type="image",
        )
        sync_draft_question_submissions(self.submission)
        field_name = self.file_field_name(image_question)

        response = self.save_draft(
            {field_name: SimpleUploadedFile("notes.txt", b"file_content", content_type="text/plain")})

        payload = json.loads(response.content)
        row = QuestionSubmission.objects.get(quest_submission=self.submission, question=image_question)
        self.assertFalse(row.response_file, "a rejected file must not be stored")
        self.assertNotIn(field_name, payload["saved_answer_files"])
        self.assertIn("Filetype not supported", payload["file_errors"][field_name])

    def test_save_draft__rejected_replacement_reports_the_error_not_the_kept_file(self):
        """Rejecting a replacement upload reports the rejection, while the earlier file stays.

        The row keeps the file an earlier draft save stored, so the response must not
        present that kept file as this save's success: the student chose a new file and
        needs to hear why it was refused.
        """
        image_question = baker.make(
            Question, quest=self.quest, ordinal=3, type="file_upload",
            required=False, allowed_file_type="image",
        )
        sync_draft_question_submissions(self.submission)
        field_name = self.file_field_name(image_question)
        self.save_draft(
            {field_name: SimpleUploadedFile("first.png", b"file_content", content_type="image/png")})

        response = self.save_draft(
            {field_name: SimpleUploadedFile("replacement.txt", b"file_content", content_type="text/plain")})

        payload = json.loads(response.content)
        self.assertIn("Filetype not supported", payload["file_errors"][field_name])
        self.assertNotIn(field_name, payload["saved_answer_files"])
        row = QuestionSubmission.objects.get(quest_submission=self.submission, question=image_question)
        self.assertIn("first", row.response_file.name, "the earlier draft-saved file must survive")

    def test_save_draft__file_on_a_text_answer_row_is_ignored(self):
        """A file crafted onto a text question's row is ignored: the form for a text row
        has no file field, so nothing is stored and nothing is reported saved."""
        rows = list(sync_draft_question_submissions(self.submission))
        index = next(i for i, row in enumerate(rows) if row.question_id == self.short_question.id)
        field_name = f"question_submissions-{index}-response_file"

        response = self.save_draft(
            {field_name: SimpleUploadedFile("sneak.png", b"file_content", content_type="image/png")})

        payload = json.loads(response.content)
        short_row = QuestionSubmission.objects.get(
            quest_submission=self.submission, question=self.short_question)
        self.assertFalse(short_row.response_file)
        self.assertEqual(payload["saved_answer_files"], {})

    def test_save_draft__stores_comment_attachments_on_a_quest_without_questions(self):
        """A comment attachment draft-saves on a quest that asks no questions at all.

        The files leg only builds the answer formset when the quest has questions, so
        this pins the other side of that branch: with none, the attachment path still
        runs and stores the file on the draft comment.
        """
        plain_quest = baker.make(Quest, name="Plain Quest", verification_required=True)
        submission = baker.make(QuestSubmission, quest=plain_quest, user=self.test_student)
        self.client.get(reverse("quests:submission", args=[submission.id]))
        submission.refresh_from_db()

        response = self.client.post(
            reverse("quests:ajax_save_draft"),
            data={
                "comment": "<p>no questions here</p>",
                "submission_id": submission.id,
                "attachments": SimpleUploadedFile("notes.pdf", b"file_content", content_type="application/pdf"),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        payload = json.loads(response.content)
        self.assertEqual(payload["result"], "Draft saved")
        self.assertEqual(payload["saved_attachments"], ["notes.pdf"])
        documents = list(submission.draft_comment.document_set.all())
        self.assertEqual(len(documents), 1)
        self.assertIn("notes", documents[0].docfile.name)

    def test_save_draft__reports_a_rejected_comment_attachment(self):
        """An attachment the form refuses is not stored, and the response carries the
        field's own error so the page can say why.

        The attachments field caps each file at 16 MiB, so a file one byte over makes
        the form error; nothing may be stored and nothing reported saved.
        """
        oversized = SimpleUploadedFile(
            "huge.pdf", b"x" * (16777216 + 1), content_type="application/pdf")

        response = self.save_draft({"attachments": oversized})

        payload = json.loads(response.content)
        self.assertIn("Max filesize", payload["file_errors"]["attachments"])
        self.assertEqual(payload["saved_attachments"], [])
        self.assertEqual(self.submission.draft_comment.document_set.count(), 0)

    def test_save_draft__file_without_management_form_saves_text_only(self):
        """A hand-built POST that sends a file without the formset's management form does
        not error: the text answers and comment still save, the files leg reports nothing."""
        rows = list(sync_draft_question_submissions(self.submission))
        response = self.client.post(
            reverse("quests:ajax_save_draft"),
            data={
                "comment": "<p>still saves</p>",
                "submission_id": self.submission.id,
                "answers": json.dumps({
                    "question_submissions-0-id": str(rows[0].id),
                    "question_submissions-0-response_text": "still saves",
                }),
                "question_submissions-0-response_file":
                    SimpleUploadedFile("orphan.png", b"file_content", content_type="image/png"),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        payload = json.loads(response.content)
        self.assertEqual(payload["result"], "Draft saved")
        self.assertEqual(payload["saved_answer_files"], {})
        self.submission.draft_comment.refresh_from_db()
        self.assertEqual(self.submission.draft_comment.text, "<p>still saves</p>")


class DraftSaveRacesSubmitTest(QuestionSubmissionFlowTestBase):
    """A draft save that lands while the student's submit is publishing writes only the
    answer it carries, so it cannot revert a published answer to a draft (#2565).

    Both draft-save legs read their answer rows, then write them back a moment later. In
    between, the submit request can publish those rows by setting `comment`. Whether the
    page still shows the student's work therefore depends on the write touching only the
    column it came to change.
    """

    def publish_answers(self):
        """Publish this submission's draft answers, as completing the quest does.

        Returns:
            Comment: the comment the answers were published against.
        """
        comment = self.submission.draft_comment
        QuestionSubmission.objects.filter(
            quest_submission=self.submission, comment__isnull=True, question__isnull=False
        ).update(comment=comment)
        return comment

    def test_save_draft_file_answers__keeps_an_answer_published_when_a_submit_beats_it(self):
        """The file leg holds instances loaded before the submit, so its write is the one
        that lands last: the answer stays published, and gains the file the student chose."""
        file_question = baker.make(
            Question, quest=self.quest, ordinal=3, type="file_upload",
            required=False, allowed_file_type="all",
        )
        sync_draft_question_submissions(self.submission)
        field_name = self.file_field_name(file_question)
        upload = SimpleUploadedFile("sketch.png", b"file_content", content_type="image/png")

        # The autosave request reaches the point where it has read the rows and validated
        # the upload, which is where it takes its snapshot of `comment`.
        formset = QuestionSubmissionFormsetFactory(
            self.formset_data(), {field_name: upload},
            instance=self.submission, queryset=sync_draft_question_submissions(self.submission),
        )
        formset.is_valid()

        # The student's submit lands in that gap and publishes the answers.
        comment = self.publish_answers()

        save_draft_file_answers(formset, {field_name: upload})

        row = QuestionSubmission.objects.get(quest_submission=self.submission, question=file_question)
        self.assertEqual(row.comment_id, comment.id, "the published answer must stay published")
        self.assertIn("sketch", row.response_file.name)

    def test_ajax_save_draft__keeps_a_text_answer_published_when_a_submit_beats_it(self):
        """The text leg re-reads `comment` when it selects the row, which leaves a smaller
        gap before the write, not none: a submit publishing inside it must still stand.

        `full_clean` runs between the read and the write, so publishing from there puts the
        submit exactly in that gap without depending on real request timing.
        """
        row = sync_draft_question_submissions(self.submission).get(question=self.short_question)
        comment = self.submission.draft_comment

        def publish_between_the_read_and_the_write(instance, *args, **kwargs):
            QuestionSubmission.objects.filter(pk=instance.pk).update(comment=comment)

        with patch.object(QuestionSubmission, "full_clean", autospec=True,
                          side_effect=publish_between_the_read_and_the_write):
            self.client.post(
                reverse("quests:ajax_save_draft"),
                data={
                    "submission_id": self.submission.id,
                    "comment": "<p>draft words</p>",
                    "answers": json.dumps({
                        "question_submissions-0-id": str(row.id),
                        "question_submissions-0-response_text": "my website",
                    }),
                },
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        row.refresh_from_db()
        self.assertEqual(row.comment_id, comment.id, "the published answer must stay published")
        self.assertEqual(row.response_text, "my website")


class AnswerDisplayTest(QuestionSubmissionFlowTestBase):
    """Published answers display with their comment for students and markers."""

    def complete_with_answers(self):
        """Complete the submission with valid answers."""
        self.client.post(
            reverse("quests:complete", args=[self.submission.id]),
            data={"complete": True, "comment_text": "", **self.formset_data()})
        self.submission.refresh_from_db()

    def test_display__student_sees_published_answers(self):
        """After submitting, the student sees their answers under the submission comment, each
        numbered ("1.", "2.") ahead of its prompt in question (ordinal) order."""
        self.complete_with_answers()
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertContains(response, "Your answer")  # the answers table's student-facing column header
        self.assertContains(response, "My answer")
        # each answer is numbered inline, in question order: "1. What is your website URL?" then
        # "2. Describe your process." (short_question is ordinal 1, long_question ordinal 2)
        content = response.content.decode()
        self.assertLess(content.index("<strong>1.</strong>"), content.index("What is your website URL?"))
        self.assertLess(content.index("What is your website URL?"), content.index("<strong>2.</strong>"))
        self.assertLess(content.index("<strong>2.</strong>"), content.index("Describe your process."))
        # each answer carries its question-type icon (short answer = text cursor, long answer = paragraph)
        self.assertContains(response, "fa-i-cursor")
        self.assertContains(response, "fa-align-left")
        # the table opts into the wrapping styles so a long unbroken answer/URL can't overflow the cell
        self.assertContains(response, "question-answers")

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

    def test_display__multiparagraph_marker_notes_render_in_div(self):
        """Multi-paragraph marker notes keep their <p> tags (unwrap_p only strips a single
        wrapping one), so the label wrapper is a <div>, not a <p>: a <p> nested in a <p> is
        invalid and the browser would auto-close the outer one, breaking the label layout."""
        self.short_question.marker_notes = "<p>First note.</p><p>Second note.</p>"
        self.short_question.save()
        self.complete_with_answers()

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertContains(response, '<div class="text-muted"><small><b>Marker notes:</b>')
        # both paragraphs survive verbatim: unwrap_p only strips a single wrapping <p>, so
        # multi-paragraph notes keep their tags (rather than being flattened or escaped)
        self.assertContains(response, "<p>First note.</p><p>Second note.</p>")

    def publish_file_answer(self, file_name, content=b"pretend media"):
        """Give the submission a published file answer, as if the student had uploaded one.

        Args:
            file_name (str): the name to store the file under, whose extension decides how
                the page shows it.
            content (bytes): the file's contents, which nothing here reads.

        Returns:
            QuestionSubmission: the published answer, with the file attached.
        """
        file_question = baker.make(
            Question, quest=self.quest, ordinal=3, type="file_upload", required=False,
            instructions="<p>Upload your work.</p>",
        )
        self.complete_with_answers()
        answer = QuestionSubmission.objects.get(quest_submission=self.submission, question=file_question)
        answer.response_file = SimpleUploadedFile(file_name, content)
        answer.save()

        return answer

    def test_display__an_image_answer_is_shown_on_the_page(self):
        """A picture a student uploaded is displayed where it is read (#2172).

        A marker working through a set of answers reads the image itself; the link stays for
        opening or saving the original.
        """
        answer = self.publish_file_answer("my_drawing.png")
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))

        self.assertContains(response, '<img class="question-media"')
        self.assertContains(response, answer.response_file.url)

    def test_display__a_video_answer_gets_a_player(self):
        """A video answer is playable on the page, where the marker is reading it."""
        self.publish_file_answer("my_clip.mp4")
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))

        self.assertContains(response, '<video class="question-media" controls preload="metadata">')

    def test_display__an_audio_answer_gets_a_player(self):
        """An audio answer is playable on the page, the same as a video one."""
        self.publish_file_answer("my_reading.mp3")
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))

        self.assertContains(response, '<audio class="question-media" controls preload="metadata">')

    def test_display__any_other_answer_file_is_offered_as_a_link(self):
        """A file the page cannot embed is offered as a link to open or save."""
        answer = self.publish_file_answer("my_notes.pdf")
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))

        self.assertNotContains(response, '<img class="question-media"')
        self.assertContains(response, f'<a href="{answer.response_file.url}" target="_blank">')

    def test_display__a_solution_image_is_shown_to_staff(self):
        """The teacher's example answer is shown too, beside the answers it is compared with."""
        self.short_question.solution_file = SimpleUploadedFile("the_solution.png", b"pretend image")
        self.short_question.save()
        self.complete_with_answers()
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))

        self.short_question.refresh_from_db()
        self.assertContains(response, "<b>Solution file:</b>")
        self.assertContains(response, self.short_question.solution_file.url)
        self.assertContains(response, '<img class="question-media"')

    def test_display__student_does_not_see_marker_notes(self):
        """Solutions and marker notes stay staff-only in the answers display."""
        self.short_question.solution_text = "SECRET SOLUTION"
        self.short_question.save()
        self.complete_with_answers()
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertContains(response, "My answer")
        self.assertNotContains(response, "SECRET SOLUTION")


class QuestDetailEntryPointTest(QuestionSubmissionFlowTestBase):
    """The quest detail page links staff to question management."""

    def test_quest_detail__staff_see_manage_questions_button(self):
        """Staff get the Submission Questions panel with its Manage Questions link."""
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse("quests:quest_detail", args=[self.quest.id]))
        self.assertContains(response, "Manage Questions")
        self.assertContains(response, reverse("questions:list", args=[self.quest.id]))

    def test_quest_detail__student_sees_no_manage_button(self):
        """Students don't see the staff questions panel (checked on the submission page,
        which embeds the same quest detail content and renders for the owning student)."""
        response = self.assert200("quests:submission", args=[self.submission.id])
        self.assertNotContains(response, "Manage Questions")

    def test_quest_detail__tooltip_shows_the_characters_the_teacher_typed(self):
        """An ampersand in a question's instructions reads as one in the table and its tooltip.

        Summernote stores it as an entity; stripping tags alone leaves that entity in place, and
        escaping it again on the way out would show the reader "Tom &amp;amp; Jerry" (#2169).
        """
        self.short_question.instructions = "<p>Compare <b>Tom &amp; Jerry</b></p>"
        self.short_question.save()
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse("quests:quest_detail", args=[self.quest.id]))

        # the page source escapes it once, so the reader sees "Tom & Jerry"
        self.assertContains(response, "Tom &amp; Jerry")
        self.assertNotContains(response, "&amp;amp;")

    def test_quest_detail__marker_notes_popover_is_initialized(self):
        """The marker-notes popover in the question table is activated on this page (#2166).

        A bootstrap popover does nothing until something initializes it: without the site-wide
        initializer this icon offers only its native "Marker Notes" title, leaving the notes
        themselves unreadable on the page a teacher marks from.
        """
        self.short_question.marker_notes = "<p>Accept any working URL.</p>"
        self.short_question.save()
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse("quests:quest_detail", args=[self.quest.id]))

        self.assertContains(response, "Accept any working URL.")
        self.assertContains(response, 'data-toggle="popover"')
        self.assertContains(response, """$('[data-toggle="popover"]').popover();""")


class DraftRowHealingTest(QuestionSubmissionFlowTestBase):
    """sync_draft_question_submissions heals duplicate draft rows for the same question."""

    def test_sync__duplicate_draft_rows_healed_keeping_content(self):
        """When duplicate draft rows exist for one question (concurrency race, or a deleted
        published comment reverting answers into an active cycle), sync keeps the row with
        content and deletes the empty duplicates."""
        contentful = sync_draft_question_submissions(self.submission).get(question=self.short_question)
        contentful.response_text = "keep me"
        contentful.save()
        # simulate a duplicate empty draft row for the same question (bypassing sync)
        QuestionSubmission.objects.create(quest_submission=self.submission, question=self.short_question)

        rows = sync_draft_question_submissions(self.submission)
        short_rows = rows.filter(question=self.short_question)
        self.assertEqual(short_rows.count(), 1)
        self.assertEqual(short_rows.first().response_text, "keep me")

    def test_sync__duplicate_dropped_when_keeper_has_content(self):
        """When the most recently edited duplicate is the contentful one, the older empty
        duplicate is simply dropped."""
        # older empty duplicate first, then the contentful row (edited last = the keeper)
        QuestionSubmission.objects.create(quest_submission=self.submission, question=self.short_question)
        contentful = QuestionSubmission.objects.create(
            quest_submission=self.submission, question=self.short_question, response_text="newest wins")

        rows = sync_draft_question_submissions(self.submission)
        short_rows = rows.filter(question=self.short_question)
        self.assertEqual(short_rows.count(), 1)
        self.assertEqual(short_rows.first().id, contentful.id)


class CompleteSecurityTest(QuestionSubmissionFlowTestBase):
    """The complete flow can't be tricked into publishing unvalidated or unsanitized answers,
    nor into bypassing required questions (regression tests for the review round)."""

    def autosave(self, answers):
        """POST an ajax draft save (as the AJAX request the view demands) for self.submission."""
        return self.client.post(
            reverse("quests:ajax_save_draft"),
            data={"comment": "<p>x</p>", "submission_id": self.submission.id, "answers": json.dumps(answers)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_autosave__sanitizes_script_on_write(self):
        """A hostile draft answer is neutralized as it is stored, not just on the form path —
        the raw value would otherwise be published verbatim and rendered with |safe."""
        row = sync_draft_question_submissions(self.submission).get(question=self.short_question)
        self.autosave({
            "question_submissions-0-id": str(row.id),
            "question_submissions-0-response_text": '<img src=x onerror="alert(1)">answer',
        })
        row.refresh_from_db()
        self.assertNotIn("onerror", row.response_text)
        self.assertIn("answer", row.response_text)

    def test_complete__autosaved_script_not_published_raw(self):
        """Publishing an autosaved answer via completion can't smuggle raw script into the
        marking display, even when the completion POST re-sends the same value unchanged."""
        rows = list(sync_draft_question_submissions(self.submission))
        short_row = next(r for r in rows if r.question_id == self.short_question.id)
        self.autosave({
            "question_submissions-0-id": str(short_row.id),
            "question_submissions-0-response_text": '<img src=x onerror="alert(1)">',
        })
        short_row.refresh_from_db()
        # complete, re-sending the (already sanitized) stored value so the form is "unchanged"
        data = self.formset_data(short_text=short_row.response_text)
        response = self.client.post(
            reverse("quests:complete", args=[self.submission.id]),
            data={"complete": True, "comment_text": "", **data})
        self.assertRedirects(response, reverse("quests:quests"))
        short_row.refresh_from_db()
        self.assertTrue(short_row.is_published)
        self.assertNotIn("onerror", short_row.response_text)

    def test_complete__zero_forms_rejected_required_not_bypassed(self):
        """A tampered management form declaring zero answer forms can't complete a quest
        whose required question was never answered."""
        response = self.client.post(
            reverse("quests:complete", args=[self.submission.id]),
            data={
                "complete": True, "comment_text": "",
                "question_submissions-TOTAL_FORMS": "0",
                "question_submissions-INITIAL_FORMS": "0",
                "question_submissions-MIN_NUM_FORMS": "0",
                "question_submissions-MAX_NUM_FORMS": "1000",
            })
        self.assertRedirects(response, self.submission.get_absolute_url())
        self.submission.refresh_from_db()
        self.assertFalse(self.submission.is_completed)
        self.assertFalse(QuestionSubmission.objects.filter(
            quest_submission=self.submission, comment__isnull=False).exists())

    def test_complete__question_added_after_page_load_blocks_and_redirects(self):
        """If the quest gains a question after the student's page loaded, the stale POST
        (missing that answer form) is bounced back rather than completing silently."""
        # student's page has 2 questions; teacher adds a required 3rd
        stale_data = self.formset_data()
        baker.make(Question, quest=self.quest, ordinal=3, type="short_answer", required=True)
        response = self.client.post(
            reverse("quests:complete", args=[self.submission.id]),
            data={"complete": True, "comment_text": "", **stale_data})
        self.assertRedirects(response, self.submission.get_absolute_url())
        self.submission.refresh_from_db()
        self.assertFalse(self.submission.is_completed)

    def test_complete__questions_changed_keeps_comment_attachment(self):
        """The questions-changed bounce keeps an attachment that validates (#2428).

        The redirect rebuilds the page with an empty file input, so the upload survives on
        the draft comment instead: the same place the validation-failure path keeps it
        (#2427), and the place a successful completion publishes it from. The student is
        told it was kept.
        """
        stale_data = self.formset_data(short_text="my title")
        baker.make(Question, quest=self.quest, ordinal=3, type="short_answer", required=True)
        upload = SimpleUploadedFile("evidence.png", b"file_content", content_type="image/png")

        response = self.client.post(
            reverse("quests:complete", args=[self.submission.id]),
            data={"complete": True, "comment_text": "", "attachments": upload, **stale_data})

        self.assertRedirects(response, self.submission.get_absolute_url())
        self.submission.refresh_from_db()
        self.assertFalse(self.submission.is_completed)
        documents = list(self.submission.draft_comment.document_set.all())
        self.assertEqual(len(documents), 1, "the attachment was dropped on the redirect")
        self.assertIn("evidence", documents[0].docfile.name)
        self.assertIn(
            "Your attached file was saved, so you don't need to choose it again.",
            [str(message) for message in get_messages(response.wsgi_request)],
        )

    def test_complete__questions_changed_keeps_file_answer(self):
        """The questions-changed bounce keeps a file answer that validates (#2428).

        The answer stays on its own draft row, unpublished, the same place the
        validation-failure path keeps it (#2165), so the rebuilt page shows it as already
        attached and a later completion publishes it.
        """
        file_question = baker.make(
            Question, quest=self.quest, ordinal=3, type="file_upload",
            required=False, allowed_file_type="all",
        )
        rows = list(sync_draft_question_submissions(self.submission))
        stale_data = self.formset_data(short_text="my title")
        upload = SimpleUploadedFile("my-recording.png", b"file_content", content_type="image/png")
        stale_data[self.file_field_name(file_question)] = upload
        baker.make(Question, quest=self.quest, ordinal=4, type="short_answer", required=True)

        response = self.client.post(
            reverse("quests:complete", args=[self.submission.id]),
            data={"complete": True, "comment_text": "", **stale_data})

        self.assertRedirects(response, self.submission.get_absolute_url())
        row = QuestionSubmission.objects.get(quest_submission=self.submission, question=file_question)
        self.assertIn("my-recording", row.response_file.name, "the file answer was dropped on the redirect")
        self.assertIsNone(row.comment_id, "a kept draft answer must not be published")
        self.assertEqual(len(rows), 3)

    def test_complete__optional_blank_answers_still_require_comment_when_verification_required(self):
        """A verification-required quest whose only questions are optional and left blank
        still demands a comment or attachment — answers-that-aren't-answers aren't content."""
        # replace the fixture questions with a single optional one
        Question.objects.filter(quest=self.quest).delete()
        optional = baker.make(Question, quest=self.quest, ordinal=1, type="short_answer", required=False)
        # rebuild the draft rows for the new question set
        rows = list(sync_draft_question_submissions(self.submission))
        data = {
            "question_submissions-TOTAL_FORMS": "1",
            "question_submissions-INITIAL_FORMS": "1",
            "question_submissions-MIN_NUM_FORMS": "0",
            "question_submissions-MAX_NUM_FORMS": "1000",
            "question_submissions-0-id": str(rows[0].id),
            "question_submissions-0-response_text": "",
        }
        self.assertEqual(rows[0].question_id, optional.id)
        response = self.client.post(
            reverse("quests:complete", args=[self.submission.id]),
            data={"complete": True, "comment_text": "", **data})
        # bounced by the attach-or-comment rule, not completed
        self.assertRedirects(response, self.submission.get_absolute_url())
        self.submission.refresh_from_db()
        self.assertFalse(self.submission.is_completed)


class SkipDiscardsDraftAnswersTest(QuestionSubmissionFlowTestBase):
    """Skipping a submission clears the answers the student drafted but never submitted (#2164)."""

    def draft_some_answers(self):
        """Put content in the submission's draft answer rows, as autosaving a draft would.

        Returns:
            list: the draft rows, each now carrying answer text.
        """
        rows = list(sync_draft_question_submissions(self.submission))
        for row in rows:
            row.response_text = "drafted but never submitted"
            row.save()
        return rows

    def draft_rows(self):
        """The submission's unpublished draft answers.

        Returns:
            QuerySet: the submission's answer rows that have no comment, so the ones a skip
            should discard.
        """
        return QuestionSubmission.objects.filter(quest_submission=self.submission, comment__isnull=True)

    def test_skip__discards_the_students_draft_answers(self):
        """A student who is not earning XP skips their own in-progress submission, and their
        drafted answers go with it.

        Nothing renders unpublished answers, and a skipped submission is approved for good, so
        rows left behind here would be permanently invisible data.
        """
        self.draft_some_answers()
        self.assertEqual(self.draft_rows().count(), 2)
        profile = self.test_student.profile
        profile.not_earning_xp = True
        profile.save()

        response = self.client.post(reverse("quests:skip", args=[self.submission.id]))

        self.assertRedirects(response, reverse("quests:quests"), fetch_redirect_response=False)
        self.submission.refresh_from_db()
        self.assertTrue(self.submission.is_approved)
        self.assertFalse(self.draft_rows().exists())

    def test_skip__leaves_already_published_answers_alone(self):
        """A teacher skipping a submission the student did complete keeps the published answers.

        Those answers are part of the record of what was handed in, and they still display with
        their comment; only unpublished drafts are discarded.
        """
        self.client.post(
            reverse("quests:complete", args=[self.submission.id]),
            data={"complete": True, "comment_text": "", **self.formset_data()})
        published = QuestionSubmission.objects.filter(quest_submission=self.submission, comment__isnull=False)
        self.assertEqual(published.count(), 2)
        self.client.force_login(self.test_teacher)

        self.client.post(reverse("quests:skip", args=[self.submission.id]))

        self.submission.refresh_from_db()
        self.assertTrue(self.submission.do_not_grant_xp)
        self.assertEqual(published.count(), 2)

    def test_ApproveView__skip_button_discards_the_students_draft_answers(self):
        """A teacher skipping from the submission page discards the drafts too, so both skip
        paths leave the same state behind."""
        self.draft_some_answers()
        self.assertEqual(self.draft_rows().count(), 2)
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse("quests:approve", args=[self.submission.id]),
            data={"skip_button": True, "comment_text": ""})

        self.assertRedirects(response, reverse("quests:approvals"), fetch_redirect_response=False)
        self.submission.refresh_from_db()
        self.assertTrue(self.submission.do_not_grant_xp)
        self.assertFalse(self.draft_rows().exists())
