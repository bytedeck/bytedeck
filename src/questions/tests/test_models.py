import datetime
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models import Q
from django_tenants.test.cases import TenantTestCase
from freezegun import freeze_time
from model_bakery import baker

from quest_manager.models import Quest, QuestSubmission
from comments.models import Comment
from questions.models import Question, QuestionSubmission


@freeze_time("2010-01-01")
class QuestionTestModel(TenantTestCase):
    def setUp(self):
        self.quest = baker.make(Quest, name="Test Quest")
        self.quest2 = baker.make(Quest, name="Test Quest 2")

        self.question = baker.make(
            Question,
            quest=self.quest,
            ordinal=432,
            type="long_answer",
            instructions="test question instructions",
        )

        self.question2 = baker.make(
            Question,
            quest=self.quest,
            ordinal=433,
            type="file_upload",
            instructions="test question 2 instructions",
        )

        self.image = SimpleUploadedFile(
            "file.jpg", b"file_content", content_type="image/jpg"
        )
        self.video = SimpleUploadedFile(
            "file.mp4", b"file_content", content_type="video/mp4"
        )

    def test_creation(self):
        "Ensure questions can be created. Do this by checking that a value can be retrieved."
        self.assertEqual(self.question.quest.name, "Test Quest")

    def test_str(self):
        "Ensure the string representation of a question is correct"
        self.assertEqual(str(self.question), "432 - long_answer")

    def test_fields(self):
        "Ensure all fields have values that can be retrieved as expected"
        question_id = self.question.id
        self.question.quest = self.quest
        self.question.type = "short_answer"
        self.question.instructions = "Test Question"
        self.question.solution_text = "Test Solution"
        self.question.marker_notes = "Test Notes"
        self.question.required = False
        self.question.save()
        try:
            retrieved_question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            self.fail("Question was not saved correctly")

        self.assertEqual(retrieved_question.id, question_id)
        self.assertEqual(retrieved_question.type, "short_answer")

        self.assertEqual(retrieved_question.instructions, "Test Question")
        self.assertEqual(retrieved_question.solution_text, "Test Solution")
        self.assertEqual(retrieved_question.marker_notes, "Test Notes")
        self.assertEqual(retrieved_question.required, False)

        # Check that the times were correctly recorded
        self.assertEqual(
            retrieved_question.datetime_created,
            datetime.datetime(2010, 1, 1, tzinfo=datetime.timezone.utc),
        )
        self.assertEqual(
            retrieved_question.datetime_last_edit,
            datetime.datetime(2010, 1, 1, tzinfo=datetime.timezone.utc),
        )

        # Now let's move time forward and make an edit
        with freeze_time("2010-01-02"):
            retrieved_question.instructions = "Updated instructions"
            retrieved_question.save()

            # Reload the object from the database
            retrieved_question.refresh_from_db()

            self.assertEqual(retrieved_question.instructions, "Updated instructions")
            # Check that datetime_created didn't change
            self.assertEqual(
                retrieved_question.datetime_created,
                datetime.datetime(2010, 1, 1, tzinfo=datetime.timezone.utc),
            )
            # Check that datetime_last_edit updated
            self.assertEqual(
                retrieved_question.datetime_last_edit,
                datetime.datetime(2010, 1, 2, tzinfo=datetime.timezone.utc),
            )

    def test_correct_types(self):
        "Ensure that the correct types can be used as expected"
        question = baker.make(Question, type="short_answer")
        question.full_clean()
        self.assertEqual(question.type, "short_answer")

        question = baker.make(Question, type="long_answer")
        question.full_clean()
        self.assertEqual(question.type, "long_answer")

        question = baker.make(Question, type="file_upload")
        question.full_clean()
        self.assertEqual(question.type, "file_upload")
        self.assertEqual(question.get_type_display(), "File Upload")

    def test_incorrect_type(self):
        "Ensure that an error is raised when an incorrect type is used"
        with self.assertRaises(ValidationError):
            question = baker.make(Question, type="bad_type")
            # full_clean() triggers the validation process
            question.full_clean()

    def test_ordering(self):
        "When questions are retrieved from the database, they should be ordered by their ordinal field"
        questions = Question.objects.all()

        # loop through, ensuring each question has an ordinal higher than the previous
        previous_ordinal = questions[0].ordinal
        for question in questions[1:]:
            self.assertGreater(question.ordinal, previous_ordinal)
            previous_ordinal = question.ordinal

        # create a new question with a higher ordinal and ensure it comes at the end of the list
        baker.make(Question, quest=self.quest, ordinal=100)
        questions = Question.objects.all()
        # get the last two questions

        self.assertGreater(
            questions[questions.count() - 1].ordinal,
            questions[questions.count() - 2].ordinal,
        )

    def test_ordinal_constraint(self):
        "Ensure that two questions in the same quest cannot have the same ordinal"
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                question1 = baker.make(Question, quest=self.quest, ordinal=232)
                question2 = baker.make(Question, quest=self.quest, ordinal=232)
                question2.full_clean()

        # Ensure that two questions in different quests can have the same ordinal
        question1 = baker.make(Question, quest=self.quest, ordinal=233)
        question2 = baker.make(Question, quest=self.quest2, ordinal=233)  # different quest
        question2.full_clean()

        self.assertEqual(question1.ordinal, 233)
        self.assertEqual(question2.ordinal, 233)

    def test_ordinal_manual_set(self):
        "Ensure that the ordinal value can be manually set to any value"
        # on a sidenote, we should also be able to manually set the ordinal value
        # and the default value should be 1
        question1 = Question.objects.create(quest=self.quest, ordinal=500, instructions="Test Question")
        self.assertEqual(question1.ordinal, 500)
        question2 = Question.objects.create(quest=self.quest, instructions="Test Question")
        question1.full_clean()
        question2.full_clean()
        self.assertEqual(question1.ordinal, 500)
        self.assertEqual(question2.ordinal, 1)

        # if we manually set the ordinal lower, it should also be respected
        question3 = Question.objects.create(quest=self.quest, ordinal=1000, instructions="Test Question")
        self.assertEqual(question3.ordinal, 1000)
        question4 = Question.objects.create(quest=self.quest, ordinal=999, instructions="Test Question")
        self.assertEqual(question4.ordinal, 999)
        question3.full_clean()
        question4.full_clean()

    def test_next_ordinal_func(self):
        """Ensure the next_ordinal(self, quest) method for the Question
        model correctly returns the next ordinal
        """
        # create a question with a high ordinal
        baker.make(Question, quest=self.quest, ordinal=1000).full_clean()
        # create a question with a lower ordinal
        baker.make(Question, quest=self.quest, ordinal=1).full_clean()

        # get the next ordinal
        next_ordinal = Question.next_ordinal(self.quest)
        self.assertEqual(next_ordinal, 1001)

        # create a question with a higher ordinal, but in a different quest.
        # the next ordinal should still be 1001 for the first quest.
        baker.make(Question, quest=self.quest2, ordinal=2000).full_clean()
        next_ordinal = Question.next_ordinal(self.quest)
        self.assertEqual(next_ordinal, 1001)
        # the next ordinal for the second quest should be 2001
        next_ordinal = Question.next_ordinal(self.quest2)

        # create a quest with no questions, and ensure the next ordinal is 1
        quest3 = baker.make(Quest)
        next_ordinal = Question.next_ordinal(quest3)
        self.assertEqual(next_ordinal, 1)

    def test_allowed_file_type(self):
        """Ensure that we can specify allowed file types for questions, and that only specified
        allowed types can be specified
        """
        question = baker.make(Question, allowed_file_type="image")
        question.full_clean()

        self.assertEqual(question.allowed_file_type, "image")
        self.assertEqual(question.get_allowed_file_type_display(), "Image")

        with self.assertRaises(ValidationError):
            question = baker.make(Question, allowed_file_type="bad")
            question.full_clean()

    def test_correct_upload_type(self):
        # test that we can save a question with an image to the database
        image_question = baker.make(
            Question,
            quest=self.quest,
            solution_file=self.image,
            ordinal=111,
            type="file_upload",
        )
        question_id = image_question.id
        image_question.save()
        image_question = Question.objects.get(id=question_id)
        # ensure file was saved as a jpg as expected. Maybe there is a better way to test this?
        self.assertTrue(image_question.solution_file.file.name.endswith(".jpg"))

        # test that we can save a question with a video to the database
        video_question = baker.make(
            Question, quest=self.quest, solution_file=self.video
        )
        question_id = video_question.id
        video_question.save()
        video_question = Question.objects.get(id=question_id)
        # ensure file was saved as an mp4 as expected.
        self.assertTrue(video_question.solution_file.file.name.endswith(".mp4"))

    def test_incorrect_upload_type(self):
        """Since there is no check in place to stop us from uploading files of the wrong type,
        this test ensures that this occurs as expected.
        This may seem like a strange test, but it is important to acknowledge the expected behavior.
        """
        # patch the solution_file content types and the allowed_file_type to only allow images
        with patch(
            "questions.models.Question.solution_file.field.content_types",
            ["image/jpeg"],
        ):
            question = baker.make(Question, solution_file=self.video)
            with patch.object(question, "allowed_file_type", "image"):
                self.assertEqual(question.allowed_file_type, "image")
                self.assertListEqual(
                    question.solution_file.field.content_types, ["image/jpeg"]
                )
                question.full_clean()
                file_content = question.solution_file.read()
                self.assertEqual(file_content, b"file_content")

    def test_parent_quest_delete(self):
        """Ensure that when a parent quest is deleted, all of its questions are deleted as well"""
        new_quest = baker.make(Quest, name="Quest about to be deleted")
        baker.make(
            Question,
            quest=new_quest,
            ordinal=1,
            instructions="Question about to be deleted A",
        )
        baker.make(
            Question,
            quest=new_quest,
            ordinal=2,
            instructions="Question about to be deleted B",
        )

        old_question_count = Question.objects.count()
        new_quest.delete()
        self.assertEqual(Question.objects.count(), old_question_count - 2)
        deleted_questions = Question.objects.filter(
            Q(instructions="Question about to be deleted A")
            | Q(instructions="Question about to be deleted B")
        )
        self.assertEqual(deleted_questions.count(), 0)


@freeze_time("2010-01-01")
class QuestionSubmissionTestModel(TenantTestCase):
    def setUp(self):
        self.quest = baker.make(Quest, name="Test Quest")
        self.question = baker.make(
            Question,
            quest=self.quest,
            instructions="Test question",
            ordinal=1,
            type="short_answer",
        )
        self.question2 = baker.make(
            Question,
            quest=self.quest,
            instructions="Test question 2",
            ordinal=2,
            type="long_answer",
        )
        self.draft_comment = baker.make(
            Comment, text="Test comment"
        )
        self.submission = baker.make(
            QuestSubmission, quest=self.quest, ordinal=1, draft_comment=self.draft_comment
        )
        self.question_submission = baker.make(
            QuestionSubmission, comment=self.draft_comment, question=self.question
        )
        self.question_submission2 = baker.make(
            QuestionSubmission, comment=self.draft_comment, question=self.question2
        )
        self.image = SimpleUploadedFile(
            "file.jpg", b"file_content", content_type="image/jpg"
        )
        self.video = SimpleUploadedFile(
            "file.mp4", b"file_content", content_type="video/mp4"
        )

        self.bad_file = SimpleUploadedFile(
            "file.txt", b"file_content", content_type="bad"
        )

    def test_creation(self):
        """Ensure question submissions can be created. Do this by checking that
        some simple values can be retrieved.
        """
        self.assertEqual(
            self.question_submission.comment.text, "Test comment"
        )
        self.assertEqual(self.draft_comment.questionsubmission_set.all()[0].question.instructions, "Test question")
        self.assertEqual(
            self.question_submission.question.instructions, "Test question"
        )

    def test_str(self):
        """Ensure the string representation of a question submission is correct.
        The format should be "[Quest Submission __str__] - (Question Ordinal)".
        If the submission doesn't have a question, a question mark "(?)" should be used instead.
        """
        comment_time = self.draft_comment.timestamp.strftime("%Y-%m-%d %-I:%M%p")
        self.assertEqual(
            str(self.question_submission),
            f"{comment_time} - (1)",
        )

        baker.make(QuestionSubmission, comment=self.draft_comment, question=None)
        self.assertEqual(
            str(QuestionSubmission.objects.get(question=None)),
            f"{comment_time} - (?)",
        )

    def test_fields(self):
        "Ensure all fields have values that can be retrieved as expected"

        question_submission_id = self.question_submission.id
        self.question_submission.response_text = "Test Answer"
        self.question_submission.save()
        try:
            retrieved_question_submission = QuestionSubmission.objects.get(
                id=question_submission_id
            )
        except QuestionSubmission.DoesNotExist:
            self.fail("QuestionSubmission was not saved correctly")

        self.assertEqual(retrieved_question_submission.id, question_submission_id)
        self.assertEqual(retrieved_question_submission.response_text, "Test Answer")

    def test_comment_foreignkey(self):
        """Ensure that a set of question submissions can be retrieved through their comment"""
        question_submissions = QuestionSubmission.objects.filter(comment=self.draft_comment)
        self.assertEqual(question_submissions.count(), 2)
        question_submissions = self.draft_comment.questionsubmission_set.all()
        self.assertEqual(question_submissions.count(), 2)
        self.assertEqual(question_submissions[0].question, self.question)

    def test_ordering(self):
        """When question submissions are retrieved from the database,
        they should be ordered by the ordinal of the question they are for
        """
        question_submissions = QuestionSubmission.objects.all()

        # loop through, ensuring each question submission has an ordinal higher than the previous
        previous_ordinal = question_submissions[0].question.ordinal
        for question_submission in question_submissions[1:]:
            self.assertGreater(question_submission.question.ordinal, previous_ordinal)
            previous_ordinal = question_submission.question.ordinal

        # create a new question submission with a higher ordinal and ensure it comes at the end of the list
        baker.make(
            QuestionSubmission,
            comment=self.draft_comment,
            question=self.question,
            question__ordinal=100,
        )
        question_submissions = QuestionSubmission.objects.all()
        # get the last two question submissions
        self.assertGreater(
            question_submissions[question_submissions.count() - 1].question.ordinal,
            question_submissions[question_submissions.count() - 2].question.ordinal,
        )

    def test_correct_upload_type(self):
        # test that we can save a question with an image to the database
        image_question_submission = baker.make(
            QuestionSubmission, response_file=self.image
        )
        question_submission_id = image_question_submission.id
        image_question_submission.save()
        image_question_submission = QuestionSubmission.objects.get(
            id=question_submission_id
        )
        # ensure file was saved as an mp4 as expected.
        self.assertTrue(
            image_question_submission.response_file.file.name.endswith(".jpg")
        )

        # test that we can save a question with a video to the database
        video_question_submission = baker.make(
            QuestionSubmission, response_file=self.video
        )
        question_submission_id = video_question_submission.id
        video_question_submission.save()
        video_question_submission = QuestionSubmission.objects.get(
            id=question_submission_id
        )
        # ensure file was saved as an mp4 as expected.
        self.assertTrue(
            video_question_submission.response_file.file.name.endswith(".mp4")
        )
        # ensure file has the content that we expect
        self.assertEqual(
            video_question_submission.response_file.file.read(), b"file_content"
        )

    def test_incorrect_upload_type(self):
        """Since there is no check in place to stop us from uploading files of the wrong type,
        this test ensures that this occurs as expected.
        This may seem like a strange test, but it is important to acknowledge the expected behavior.
        """
        # patch the solution_file content types and the allowed_file_type to only allow images
        with patch(
            "questions.models.QuestionSubmission.response_file.field.content_types",
            ["image/jpeg"],
        ):
            question_sub = baker.make(
                QuestionSubmission,
                question=self.question,
                comment=self.draft_comment,
                response_file=self.video,
            )
            self.assertEqual(
                question_sub.response_file.field.content_types, ["image/jpeg"]
            )
            question_sub.full_clean()
            file_content = question_sub.response_file.read()
            self.assertEqual(file_content, b"file_content")

    def test_parent_question_delete(self):
        """Ensure that when a parent question is deleted, the question submissions are not deleted"""
        new_question = baker.make(
            Question,
            quest=self.quest,
            instructions="Question about to be deleted",
            ordinal=541,
        )
        baker.make(
            QuestionSubmission,
            comment=self.draft_comment,
            question=new_question,
            response_text="Test Answer A",
        )
        baker.make(
            QuestionSubmission,
            comment=self.draft_comment,
            question=new_question,
            response_text="Test Answer A",
        )

        old_question_submission_count = QuestionSubmission.objects.count()
        new_question.delete()
        self.assertEqual(
            QuestionSubmission.objects.count(), old_question_submission_count
        )
        deleted_question_submissions = QuestionSubmission.objects.filter(
            response_text="Test Answer A"
        )
        self.assertEqual(deleted_question_submissions.count(), 2)
        self.assertIsNone(deleted_question_submissions[0].question)
        self.assertIsNone(deleted_question_submissions[1].question)

    def test_question_deleted_files_still_exist(self):
        """Ensure that if we delete a QuestionSubmission's parent question, the student's file submissions
        still exist and can be accessed. This is important for the case where a student uploads a file,
        then the question is deleted. We still want to be able to access the file.
        """
        new_question = baker.make(
            Question,
            quest=self.quest,
            instructions="Question about to be deleted",
            ordinal=541,
        )
        question_submission = baker.make(
            QuestionSubmission,
            comment=self.draft_comment,
            question=new_question,
            response_file=self.video,
        )
        question_submission_id = question_submission.id
        question_submission.save()
        question_submission = QuestionSubmission.objects.get(
            id=question_submission_id
        )
        # ensure file was saved as an mp4 as expected.
        self.assertTrue(
            question_submission.response_file.file.name.endswith(".mp4")
        )
        # ensure file has the content that we expect
        self.assertEqual(
            question_submission.response_file.file.read(), b"file_content"
        )
        new_question.delete()
        question_submission = QuestionSubmission.objects.get(
            id=question_submission_id
        )
        # ensure file was saved as an mp4 as expected.
        self.assertTrue(
            question_submission.response_file.file.name.endswith(".mp4")
        )
        # ensure file has the content that we expect
        self.assertEqual(
            question_submission.response_file.file.read(), b"file_content"
        )

    def test_parent_comment_delete(self):
        """Ensure that when a comment is deleted, the question submissions are deleted"""
        new_submission = baker.make(
            QuestSubmission,
            quest=self.quest,
            ordinal=541,
        )
        new_comment = baker.make(
            Comment, target_object=new_submission, text="Comment about to be deleted"
        )
        baker.make(
            QuestionSubmission,
            comment=new_comment,
            question=self.question,
            response_text="Test Answer A",
        )
        baker.make(
            QuestionSubmission,
            comment=new_comment,
            question=self.question,
            response_text="Test Answer A",
        )

        old_question_submission_count = QuestionSubmission.objects.count()
        new_comment.delete()
        self.assertEqual(
            QuestionSubmission.objects.count(), old_question_submission_count - 2
        )
        deleted_question_submissions = QuestionSubmission.objects.filter(
            response_text="Test Answer A"
        )
        self.assertEqual(deleted_question_submissions.count(), 0)
