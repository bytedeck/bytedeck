import datetime

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction

from freezegun import freeze_time
from model_bakery import baker

from comments.models import Comment
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest, QuestSubmission
from questions.models import ALLOWED_FILE_TYPE_CHOICES, Question, QuestionSubmission
from utilities.fields import FILE_MIME_TYPES


class QuestionModelTest(ByteDeckTenantTestCase):
    """Tests for the Question model (a quest's additional submission fields)."""

    @classmethod
    def setUpTestData(cls):
        """Two quests, each usable for questions; two questions on the first quest."""
        cls.quest = baker.make(Quest, name="Test Quest")
        cls.quest2 = baker.make(Quest, name="Test Quest 2")

        cls.question = baker.make(
            Question,
            quest=cls.quest,
            ordinal=432,
            type="long_answer",
            instructions="test question instructions",
        )
        cls.question2 = baker.make(
            Question,
            quest=cls.quest,
            ordinal=433,
            type="file_upload",
            instructions="test question 2 instructions",
        )

    def test_creation__values_retrievable(self):
        """A created question keeps its relation to its quest and its field values."""
        self.assertEqual(self.question.quest.name, "Test Quest")
        self.assertEqual(self.question.instructions, "test question instructions")

    def test_str__ordinal_and_type(self):
        """__str__ returns "[ordinal] - [type]"."""
        self.assertEqual(str(self.question), "432 - long_answer")

    def test_fields__save_and_timestamps(self):
        """All editable fields round-trip through the database; datetime_created is fixed at
        creation while datetime_last_edit follows the latest save."""
        with freeze_time("2010-01-01"):
            question = baker.make(
                Question,
                quest=self.quest,
                ordinal=900,
                type="short_answer",
                instructions="Test Question",
                solution_text="Test Solution",
                marker_notes="Test Notes",
                required=False,
            )

        retrieved_question = Question.objects.get(id=question.id)
        self.assertEqual(retrieved_question.type, "short_answer")
        self.assertEqual(retrieved_question.instructions, "Test Question")
        self.assertEqual(retrieved_question.solution_text, "Test Solution")
        self.assertEqual(retrieved_question.marker_notes, "Test Notes")
        self.assertFalse(retrieved_question.required)
        self.assertEqual(
            retrieved_question.datetime_created,
            datetime.datetime(2010, 1, 1, tzinfo=datetime.timezone.utc),
        )
        self.assertEqual(
            retrieved_question.datetime_last_edit,
            datetime.datetime(2010, 1, 1, tzinfo=datetime.timezone.utc),
        )

        # move time forward and edit: created stays, last_edit follows
        with freeze_time("2010-01-02"):
            retrieved_question.instructions = "Updated instructions"
            retrieved_question.save()

        retrieved_question.refresh_from_db()
        self.assertEqual(retrieved_question.instructions, "Updated instructions")
        self.assertEqual(
            retrieved_question.datetime_created,
            datetime.datetime(2010, 1, 1, tzinfo=datetime.timezone.utc),
        )
        self.assertEqual(
            retrieved_question.datetime_last_edit,
            datetime.datetime(2010, 1, 2, tzinfo=datetime.timezone.utc),
        )

    def test_type__valid_choices_pass_full_clean(self):
        """Each supported question type validates, and display labels are generated."""
        for i, question_type in enumerate(["short_answer", "long_answer", "file_upload"]):
            question = baker.make(Question, quest=self.quest2, ordinal=100 + i, type=question_type)
            question.full_clean()
            self.assertEqual(question.type, question_type)
        self.assertEqual(question.get_type_display(), "File Upload")

    def test_type__invalid_choice_fails_full_clean(self):
        """An unknown question type is rejected by validation."""
        with self.assertRaises(ValidationError):
            question = baker.make(Question, quest=self.quest2, ordinal=110, type="bad_type")
            question.full_clean()

    def test_ordering__by_ordinal(self):
        """Questions are returned ordered by their ordinal, regardless of creation order."""
        # created after the setUpTestData questions but with a lower ordinal
        first = baker.make(Question, quest=self.quest, ordinal=100)
        ordinals = list(Question.objects.filter(quest=self.quest).values_list("ordinal", flat=True))
        self.assertEqual(ordinals, sorted(ordinals))
        self.assertEqual(Question.objects.filter(quest=self.quest).first(), first)

    def test_ordinal_constraint__unique_per_quest(self):
        """Two questions in the same quest cannot share an ordinal, but questions in
        different quests can."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                baker.make(Question, quest=self.quest, ordinal=232)
                baker.make(Question, quest=self.quest, ordinal=232)

        # same ordinal, different quest: fine
        question1 = baker.make(Question, quest=self.quest, ordinal=233)
        question2 = baker.make(Question, quest=self.quest2, ordinal=233)
        question2.full_clean()
        self.assertEqual(question1.ordinal, 233)
        self.assertEqual(question2.ordinal, 233)

    def test_ordinal__manual_set_and_default(self):
        """The ordinal can be set manually to any value; unset, it defaults to 1."""
        question1 = Question.objects.create(quest=self.quest2, ordinal=500, instructions="Test Question")
        question2 = Question.objects.create(quest=self.quest2, instructions="Test Question")
        self.assertEqual(question1.ordinal, 500)
        self.assertEqual(question2.ordinal, 1)

    def test_next_ordinal__per_quest(self):
        """next_ordinal() returns one above the quest's highest ordinal, independently
        per quest, and 1 for a quest with no questions yet."""
        baker.make(Question, quest=self.quest, ordinal=1000)
        baker.make(Question, quest=self.quest, ordinal=1)
        self.assertEqual(Question.next_ordinal(self.quest), 1001)

        # a higher ordinal in a different quest doesn't affect the first quest
        baker.make(Question, quest=self.quest2, ordinal=2000)
        self.assertEqual(Question.next_ordinal(self.quest), 1001)
        self.assertEqual(Question.next_ordinal(self.quest2), 2001)

        # no questions yet: next ordinal is 1
        quest3 = baker.make(Quest)
        self.assertEqual(Question.next_ordinal(quest3), 1)

    def test_allowed_file_type__choices_validated(self):
        """allowed_file_type accepts only the declared choices."""
        question = baker.make(Question, quest=self.quest2, ordinal=120, allowed_file_type="image")
        question.full_clean()
        self.assertEqual(question.allowed_file_type, "image")
        self.assertEqual(question.get_allowed_file_type_display(), "Image")

        with self.assertRaises(ValidationError):
            question = baker.make(Question, quest=self.quest2, ordinal=121, allowed_file_type="bad")
            question.full_clean()

    def test_allowed_file_type__choices_map_to_mime_types(self):
        """Every allowed_file_type choice has a matching FILE_MIME_TYPES entry, so
        allowed_mime_types() always resolves."""
        for key, _label in ALLOWED_FILE_TYPE_CHOICES:
            self.assertIn(key, FILE_MIME_TYPES)
        question = baker.make(Question, quest=self.quest2, ordinal=130, allowed_file_type="audio")
        self.assertEqual(question.allowed_mime_types(), FILE_MIME_TYPES["audio"])
        # the default 'all' resolves to the "accept anything" sentinel
        question = baker.make(Question, quest=self.quest2, ordinal=131)
        self.assertEqual(question.allowed_mime_types(), "All")

    def test_solution_file__saved_regardless_of_allowed_file_type(self):
        """Model-level saves don't enforce MIME restrictions (that's the form's job): a
        solution file of any type is stored and its content preserved."""
        video = SimpleUploadedFile("file.mp4", b"file_content", content_type="video/mp4")
        question = baker.make(
            Question, quest=self.quest2, ordinal=140, type="file_upload",
            solution_file=video, allowed_file_type="image",
        )
        question = Question.objects.get(id=question.id)
        self.assertTrue(question.solution_file.file.name.endswith(".mp4"))
        self.assertEqual(question.solution_file.read(), b"file_content")

    def test_quest_delete__cascades_to_questions(self):
        """Deleting a quest deletes its questions."""
        new_quest = baker.make(Quest, name="Quest about to be deleted")
        baker.make(Question, quest=new_quest, ordinal=1)
        baker.make(Question, quest=new_quest, ordinal=2)

        old_question_count = Question.objects.count()
        new_quest.delete()
        self.assertEqual(Question.objects.count(), old_question_count - 2)
        self.assertFalse(Question.objects.filter(quest_id=new_quest.id).exists())


class QuestionSubmissionModelTest(ByteDeckTenantTestCase):
    """Tests for QuestionSubmission (a student's answer to one question, owned by their
    QuestSubmission, optionally published with a Comment)."""

    @classmethod
    def setUpTestData(cls):
        """A quest with two questions, a student's quest submission, and one draft answer
        per question."""
        cls.quest = baker.make(Quest, name="Test Quest")
        cls.question = baker.make(
            Question, quest=cls.quest, instructions="Test question", ordinal=1, type="short_answer",
        )
        cls.question2 = baker.make(
            Question, quest=cls.quest, instructions="Test question 2", ordinal=2, type="long_answer",
        )
        cls.submission = baker.make(QuestSubmission, quest=cls.quest, ordinal=1)
        cls.question_submission = baker.make(
            QuestionSubmission, quest_submission=cls.submission, question=cls.question,
        )
        cls.question_submission2 = baker.make(
            QuestionSubmission, quest_submission=cls.submission, question=cls.question2,
        )

    def make_comment(self, **kwargs):
        """Create a Comment targeting this class's quest submission (the Comment model has a
        GenericForeignKey, so the target must always be passed explicitly)."""
        return baker.make(Comment, target_object=self.submission, **kwargs)

    def test_creation__values_retrievable(self):
        """A created answer is reachable from its quest submission and knows its question."""
        self.assertEqual(self.question_submission.question.instructions, "Test question")
        self.assertEqual(
            list(self.submission.question_submissions.all()),
            [self.question_submission, self.question_submission2],
        )

    def test_str__creation_time_and_ordinal(self):
        """__str__ returns "[creation datetime] - ([question ordinal])", with "(?)" when the
        question has been deleted."""
        with freeze_time("2010-01-01 13:00"):
            question_submission = baker.make(
                QuestionSubmission, quest_submission=self.submission, question=self.question,
            )
            orphan = baker.make(QuestionSubmission, quest_submission=self.submission, question=None)

        self.assertEqual(str(question_submission), "2010-01-01 1:00PM - (1)")
        self.assertEqual(str(orphan), "2010-01-01 1:00PM - (?)")

    def test_fields__save_and_retrieve(self):
        """The response text round-trips through the database."""
        self.question_submission.response_text = "Test Answer"
        self.question_submission.save()
        retrieved = QuestionSubmission.objects.get(id=self.question_submission.id)
        self.assertEqual(retrieved.response_text, "Test Answer")

    def test_is_published__follows_comment(self):
        """An answer with no comment is an unpublished draft; setting the comment publishes it."""
        self.assertFalse(self.question_submission.is_published)
        self.question_submission.comment = self.make_comment(text="Published!")
        self.question_submission.save()
        self.assertTrue(QuestionSubmission.objects.get(id=self.question_submission.id).is_published)

    def test_comment_foreignkey__answers_retrievable_from_comment(self):
        """Published answers can be retrieved through their comment's reverse relation."""
        comment = self.make_comment(text="Test comment")
        QuestionSubmission.objects.filter(quest_submission=self.submission).update(comment=comment)
        self.assertEqual(comment.question_submissions.count(), 2)
        self.assertEqual(comment.question_submissions.first().question, self.question)

    def test_ordering__by_question_ordinal(self):
        """Answers are returned in their question's ordinal order, regardless of creation order."""
        # this answer is created last but its question has the lowest ordinal, so it sorts first
        question3 = baker.make(Question, quest=self.quest, ordinal=0, type="short_answer")
        first = baker.make(QuestionSubmission, quest_submission=self.submission, question=question3)
        answers = list(QuestionSubmission.objects.filter(quest_submission=self.submission))
        ordinals = [a.question.ordinal for a in answers]
        self.assertEqual(ordinals, sorted(ordinals))
        self.assertEqual(answers[0], first)

    def test_response_file__content_preserved(self):
        """A file answer of any type is stored at model level with its content preserved
        (MIME enforcement is the form's job)."""
        video = SimpleUploadedFile("file.mp4", b"file_content", content_type="video/mp4")
        answer = baker.make(
            QuestionSubmission, quest_submission=self.submission, question=self.question,
            response_file=video,
        )
        answer = QuestionSubmission.objects.get(id=answer.id)
        self.assertTrue(answer.response_file.file.name.endswith(".mp4"))
        self.assertEqual(answer.response_file.read(), b"file_content")

    def test_question_delete__answers_survive_with_null_question(self):
        """Deleting a question keeps its answers (question set to NULL) so markers can still
        see what students submitted."""
        new_question = baker.make(Question, quest=self.quest, ordinal=541)
        answer1 = baker.make(
            QuestionSubmission, quest_submission=self.submission, question=new_question,
            response_text="Test Answer A",
        )
        answer2 = baker.make(
            QuestionSubmission, quest_submission=self.submission, question=new_question,
            response_text="Test Answer A",
        )

        old_count = QuestionSubmission.objects.count()
        new_question.delete()
        self.assertEqual(QuestionSubmission.objects.count(), old_count)
        answer1.refresh_from_db()
        answer2.refresh_from_db()
        self.assertIsNone(answer1.question)
        self.assertIsNone(answer2.question)

    def test_question_delete__response_file_still_accessible(self):
        """After a question is deleted, a student's uploaded file answer still exists and
        can be read."""
        new_question = baker.make(Question, quest=self.quest, ordinal=542)
        video = SimpleUploadedFile("file.mp4", b"file_content", content_type="video/mp4")
        answer = baker.make(
            QuestionSubmission, quest_submission=self.submission, question=new_question,
            response_file=video,
        )

        new_question.delete()
        answer = QuestionSubmission.objects.get(id=answer.id)
        self.assertTrue(answer.response_file.file.name.endswith(".mp4"))
        self.assertEqual(answer.response_file.read(), b"file_content")

    def test_comment_delete__answers_revert_to_draft(self):
        """Deleting a published comment keeps the answers but reverts them to unpublished
        (comment set to NULL) rather than destroying student work."""
        comment = self.make_comment(text="Comment about to be deleted")
        answer = baker.make(
            QuestionSubmission, quest_submission=self.submission, question=self.question,
            comment=comment, response_text="Survives",
        )

        comment.delete()
        answer.refresh_from_db()
        self.assertIsNone(answer.comment)
        self.assertFalse(answer.is_published)
        self.assertEqual(answer.response_text, "Survives")

    def test_quest_submission_delete__cascades_to_answers(self):
        """Deleting a student's quest submission deletes its answers: the submission is the
        answers' lifecycle anchor."""
        other_submission = baker.make(QuestSubmission, quest=self.quest, ordinal=2)
        baker.make(QuestionSubmission, quest_submission=other_submission, question=self.question)
        baker.make(QuestionSubmission, quest_submission=other_submission, question=self.question2)

        old_count = QuestionSubmission.objects.count()
        other_submission.delete()
        self.assertEqual(QuestionSubmission.objects.count(), old_count - 2)
        self.assertFalse(QuestionSubmission.objects.filter(quest_submission_id=other_submission.id).exists())
