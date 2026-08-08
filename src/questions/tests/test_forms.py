from django.core.files.uploadedfile import SimpleUploadedFile

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest, QuestSubmission
from questions.forms import QuestionForm, QuestionSubmissionForm, QuestionSubmissionFormsetFactory
from questions.models import Question, QuestionSubmission


class QuestionFormTest(ByteDeckTenantTestCase):
    """Tests for QuestionForm (the teacher-facing create/edit form)."""

    def test_init__short_and_long_answer_hide_file_fields(self):
        """Text question types show solution_text and hide the file-related fields."""
        for question_type in ("short_answer", "long_answer"):
            form = QuestionForm(question_type=question_type)
            self.assertIn("solution_text", form.fields)
            self.assertNotIn("solution_file", form.fields)
            self.assertNotIn("allowed_file_type", form.fields)
            self.assertEqual(form.fields["type"].initial, question_type)

    def test_init__file_upload_hides_solution_text(self):
        """The file_upload type shows the file fields and hides solution_text."""
        form = QuestionForm(question_type="file_upload")
        self.assertNotIn("solution_text", form.fields)
        self.assertIn("solution_file", form.fields)
        self.assertIn("allowed_file_type", form.fields)

    def test_init__invalid_type_raises_value_error(self):
        """An unsupported question type is a programming error (views must validate first),
        so the form refuses to build."""
        with self.assertRaises(ValueError):
            QuestionForm(question_type="not_a_type")
        with self.assertRaises(ValueError):
            QuestionForm()  # question_type kwarg missing entirely

    def test_valid_data__creates_question(self):
        """The form validates and saves a well-formed short_answer question."""
        quest = baker.make(Quest)
        form = QuestionForm(
            data={
                "type": "short_answer",
                "instructions": "What did you learn?",
                "solution_text": "Something",
                "required": True,
            },
            question_type="short_answer",
        )
        self.assertTrue(form.is_valid(), form.errors)
        question = form.save(commit=False)
        question.quest = quest
        question.ordinal = Question.next_ordinal(quest)
        question.full_clean()
        question.save()
        self.assertEqual(Question.objects.get(id=question.id).instructions, "What did you learn?")


class QuestionSubmissionFormTest(ByteDeckTenantTestCase):
    """Tests for QuestionSubmissionForm and its formset (the student-facing answer forms)."""

    @classmethod
    def setUpTestData(cls):
        """A quest with one question of each type, and a student submission with a draft
        answer row per question."""
        cls.quest = baker.make(Quest)
        cls.short_question = baker.make(
            Question, quest=cls.quest, ordinal=1, type="short_answer", required=True,
        )
        cls.long_question = baker.make(
            Question, quest=cls.quest, ordinal=2, type="long_answer", required=True,
        )
        cls.file_question = baker.make(
            Question, quest=cls.quest, ordinal=3, type="file_upload", required=True,
            allowed_file_type="video",
        )
        cls.submission = baker.make(QuestSubmission, quest=cls.quest)
        cls.short_answer = baker.make(
            QuestionSubmission, quest_submission=cls.submission, question=cls.short_question,
        )
        cls.long_answer = baker.make(
            QuestionSubmission, quest_submission=cls.submission, question=cls.long_question,
        )
        cls.file_answer = baker.make(
            QuestionSubmission, quest_submission=cls.submission, question=cls.file_question,
        )

    def test_init__short_answer_field(self):
        """Short answer forms get a 200-char text field and no file field."""
        form = QuestionSubmissionForm(instance=self.short_answer)
        self.assertIn("response_text", form.fields)
        self.assertNotIn("response_file", form.fields)
        self.assertEqual(form.fields["response_text"].max_length, 200)
        self.assertTrue(form.fields["response_text"].required)

    def test_init__long_answer_field(self):
        """Long answer forms get an unbounded rich-text field and no file field."""
        form = QuestionSubmissionForm(instance=self.long_answer)
        self.assertIn("response_text", form.fields)
        self.assertNotIn("response_file", form.fields)
        self.assertIsNone(form.fields["response_text"].max_length)

    def test_init__file_upload_field(self):
        """File upload forms get a restricted file field with the question's MIME types,
        and no text field."""
        form = QuestionSubmissionForm(instance=self.file_answer)
        self.assertIn("response_file", form.fields)
        self.assertNotIn("response_text", form.fields)
        self.assertEqual(form.fields["response_file"].content_types, self.file_question.allowed_mime_types())

    def test_init__optional_question_not_required(self):
        """Answers to non-required questions aren't required fields."""
        optional_question = baker.make(
            Question, quest=self.quest, ordinal=4, type="short_answer", required=False,
        )
        answer = baker.make(
            QuestionSubmission, quest_submission=self.submission, question=optional_question,
        )
        form = QuestionSubmissionForm(instance=answer)
        self.assertFalse(form.fields["response_text"].required)

    def test_clean__required_text_missing_is_invalid(self):
        """A required text question rejects an empty response with a friendly error, and
        accepts a filled one."""
        form = QuestionSubmissionForm(data={"response_text": ""}, instance=self.short_answer)
        self.assertFalse(form.is_valid())

        form = QuestionSubmissionForm(data={"response_text": "An answer"}, instance=self.short_answer)
        self.assertTrue(form.is_valid(), form.errors)

    def test_clean__short_answer_over_200_chars_is_invalid(self):
        """The 200-character short answer limit is enforced server-side, not just by the widget."""
        form = QuestionSubmissionForm(data={"response_text": "x" * 201}, instance=self.short_answer)
        self.assertFalse(form.is_valid())

    def test_clean__required_file_missing_is_invalid(self):
        """A required file question rejects a POST with no file, and accepts an allowed one."""
        form = QuestionSubmissionForm(data={}, files={}, instance=self.file_answer)
        self.assertFalse(form.is_valid())

        video = SimpleUploadedFile("file.mp4", b"file_content", content_type="video/mp4")
        form = QuestionSubmissionForm(data={}, files={"response_file": video}, instance=self.file_answer)
        self.assertTrue(form.is_valid(), form.errors)

    def test_clean__wrong_file_type_is_invalid(self):
        """A file whose MIME type isn't allowed for the question is rejected."""
        image = SimpleUploadedFile("file.jpg", b"file_content", content_type="image/jpeg")
        form = QuestionSubmissionForm(data={}, files={"response_file": image}, instance=self.file_answer)
        self.assertFalse(form.is_valid())

    def test_clean__all_file_type_accepts_anything(self):
        """A question with the default 'all' file type accepts any MIME type."""
        any_question = baker.make(
            Question, quest=self.quest, ordinal=5, type="file_upload", required=True,
        )
        answer = baker.make(
            QuestionSubmission, quest_submission=self.submission, question=any_question,
        )
        anything = SimpleUploadedFile("file.bin", b"file_content", content_type="application/octet-stream")
        form = QuestionSubmissionForm(data={}, files={"response_file": anything}, instance=answer)
        self.assertTrue(form.is_valid(), form.errors)

    def test_deleted_question__form_fails_validation_instead_of_crashing(self):
        """An answer whose question was deleted (question=None) builds a degraded stub form
        that fails validation with a message, rather than raising an exception."""
        orphan = baker.make(QuestionSubmission, quest_submission=self.submission, question=None)
        form = QuestionSubmissionForm(data={}, instance=orphan)  # must not raise
        self.assertNotIn("response_text", form.fields)
        self.assertNotIn("response_file", form.fields)
        self.assertFalse(form.is_valid())
        self.assertIn("no longer matches", str(form.errors))

    def test_formset__valid_answers_save(self):
        """The inline formset binds one form per existing answer row (extra=0), validates a
        complete POST and saves the responses onto the student's answers."""
        # only this class's text questions, to keep POST data simple
        queryset = QuestionSubmission.objects.filter(
            quest_submission=self.submission, question__type__in=["short_answer", "long_answer"],
        )
        data = {
            "question_submissions-TOTAL_FORMS": "2",
            "question_submissions-INITIAL_FORMS": "2",
            "question_submissions-MIN_NUM_FORMS": "0",
            "question_submissions-MAX_NUM_FORMS": "1000",
            "question_submissions-0-id": str(self.short_answer.id),
            "question_submissions-0-response_text": "Short answer",
            "question_submissions-1-id": str(self.long_answer.id),
            "question_submissions-1-response_text": "<p>Long answer</p>",
        }
        formset = QuestionSubmissionFormsetFactory(data, instance=self.submission, queryset=queryset)
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()

        self.short_answer.refresh_from_db()
        self.long_answer.refresh_from_db()
        self.assertEqual(self.short_answer.response_text, "Short answer")
        self.assertEqual(self.long_answer.response_text, "<p>Long answer</p>")

    def test_formset__missing_required_answer_is_invalid(self):
        """The formset reports errors when a required answer is left blank."""
        queryset = QuestionSubmission.objects.filter(id=self.short_answer.id)
        data = {
            "question_submissions-TOTAL_FORMS": "1",
            "question_submissions-INITIAL_FORMS": "1",
            "question_submissions-MIN_NUM_FORMS": "0",
            "question_submissions-MAX_NUM_FORMS": "1000",
            "question_submissions-0-id": str(self.short_answer.id),
            "question_submissions-0-response_text": "",
        }
        formset = QuestionSubmissionFormsetFactory(data, instance=self.submission, queryset=queryset)
        self.assertFalse(formset.is_valid())
