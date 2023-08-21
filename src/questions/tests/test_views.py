from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from model_bakery import baker

from quest_manager.models import Quest
from questions.models import Question


class QuestionCRUDLViewTest(TenantTestCase):
    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_teacher = User.objects.create_user(
            "test_teacher", password="password", is_staff=True
        )
        self.test_student = User.objects.create_user(
            "test_student", password="password"
        )

        self.quest = baker.make(Quest, xp=5)
        self.question1 = baker.make(
            Question, quest=self.quest, ordinal=1, instructions="Test instructions 1"
        )
        self.question2 = baker.make(
            Question, quest=self.quest, ordinal=2, instructions="Test instructions 2"
        )
        self.question_form_data1 = {
            "quest": self.quest.id,
            "ordinal": 3,
            "type": "short_answer",
            "instructions": "Test instructions",
            "solution_text": "Test solution text",
            "required": True,
        }
        self.file_upload1 = SimpleUploadedFile(
            "file.mp4", b"file_content", content_type="video/mp4"
        )
        self.long_question1 = baker.make(
            Question,
            quest=self.quest,
            ordinal=4,
            type="long_answer",
            instructions="Test instructions",
            solution_text="Test solution text",
        )
        self.file_question1 = baker.make(
            Question,
            quest=self.quest,
            ordinal=5,
            type="file_upload",
            instructions="Test instructions",
            solution_file=self.file_upload1,
        )
        self.question_form_file_data1 = {
            "quest": self.quest.id,
            "ordinal": 6,
            "type": "file_upload",
            "instructions": "Test instructions",
            "solution_text": "Test solution text",
            "required": True,
            "file": self.file_upload1,
            "allowed_file_type": "video",
        }

    def test_question_list_student_access_denied(self):
        # log in the student
        self.client.force_login(self.test_student)
        response = self.client.get(
            reverse("questions:list", kwargs={"quest_id": self.quest.id})
        )
        self.assertEqual(response.status_code, 403)

    def test_question_list_teacher_access_granted(self):
        self.client.force_login(self.test_teacher)
        response = self.client.get(
            reverse("questions:list", kwargs={"quest_id": self.quest.id})
        )
        self.assertEqual(response.status_code, 200)

    def test_question_list_teacher_invalid_quest_id(self):
        """If the teacher tries to access a quest that doesn't exist, they should get a 404"""
        self.client.force_login(self.test_teacher)
        response = self.client.get(
            reverse("questions:list", kwargs={"quest_id": 999})
        )
        self.assertEqual(response.status_code, 404)

    def test_question_list_content_is_displayed(self):
        self.client.force_login(self.test_teacher)
        response = self.client.get(
            reverse("questions:list", kwargs={"quest_id": self.quest.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "questions/question_list.html")
        # NOTE: Question instructions are truncated at 20 characters,
        # so we can't test for instructions larger than that
        self.assertContains(response, self.question1.instructions)
        self.assertContains(response, self.question2.instructions)

    def test_question_create_teacher_access_granted(self):
        self.client.force_login(self.test_teacher)
        response = self.client.get(
            reverse(
                "questions:create",
                kwargs={"quest_id": self.quest.id, "question_type": "short_answer"},
            )
        )
        self.assertEqual(response.status_code, 200)

    def test_question_create_teacher_with_invalid_type(self):
        """If the teacher tries to create a question with an invalid question type, they should get a 404"""
        self.client.force_login(self.test_teacher)
        response = self.client.get(
            reverse(
                "questions:create",
                kwargs={
                    "quest_id": self.quest.id,
                    "question_type": "invalid_question_type",
                },
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_question_create_student(self):
        """Students should not be able to create questions"""
        self.client.force_login(self.test_student)

        question_count_before = Question.objects.count()

        response = self.client.post(
            reverse(
                "questions:create",
                kwargs={"quest_id": self.quest.id, "question_type": "short_answer"},
            ),
            data=self.question_form_data1,
        )
        self.assertEqual(response.status_code, 403)
        # make sure the question wasn't created
        self.assertEqual(Question.objects.count(), question_count_before)

    def test_question_create_teacher(self):
        """Teachers should be able to create questions"""
        self.client.force_login(self.test_teacher)

        question_count_before = Question.objects.count()

        response = self.client.post(
            reverse(
                "questions:create",
                kwargs={"quest_id": self.quest.id, "question_type": "short_answer"},
            ),
            data=self.question_form_data1,
        )
        # there should be no form errors
        if response.context and "form" in response.context:
            form_errors = response.context["form"].errors
        else:
            form_errors = {}
        self.assertIsNone(response.context, f"Form errors: {form_errors}")
        self.assertEqual(response.status_code, 302)
        # make sure the question was created
        self.assertEqual(Question.objects.count(), question_count_before + 1)

    def test_question_create_file_upload(self):
        """Teachers should be able to create file upload questions"""
        self.client.force_login(self.test_teacher)

        question_count_before = Question.objects.count()

        response = self.client.post(
            reverse(
                "questions:create",
                kwargs={"quest_id": self.quest.id, "question_type": "file_upload"},
            ),
            data=self.question_form_file_data1,
        )
        # there should be no form errors
        if response.context and "form" in response.context:
            form_errors = response.context["form"].errors
        else:
            form_errors = {}
        self.assertIsNone(response.context, f"Form errors: {form_errors}")
        self.assertEqual(response.status_code, 302)
        # make sure the question was created
        self.assertEqual(Question.objects.count(), question_count_before + 1)

    def test_question_update_student_access_denied(self):
        # log in the student
        self.client.force_login(self.test_student)
        response = self.client.get(
            reverse(
                "questions:update",
                kwargs={"quest_id": self.quest.id, "pk": self.question1.id},
            )
        )
        self.assertEqual(response.status_code, 403)

    def test_question_update_teacher_access_granted(self):
        self.client.force_login(self.test_teacher)
        response = self.client.get(
            reverse(
                "questions:update",
                kwargs={"quest_id": self.quest.id, "pk": self.question1.id},
            )
        )
        self.assertEqual(response.status_code, 200)

    def test_question_update_previous_content_short_answer(self):
        """The question's previous content (instructions, etc) should be displayed on the page when the teacher
        is updating it."""
        self.client.force_login(self.test_teacher)
        response = self.client.get(
            reverse(
                "questions:update",
                kwargs={"quest_id": self.quest.id, "pk": self.question2.id},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.question2.instructions)

    def test_question_update_previous_content_long_answer(self):
        """When a teacher is updating a long answer question, the previous question's content should be displayed in
        the form fields."""
        self.client.force_login(self.test_teacher)
        response = self.client.get(
            reverse(
                "questions:update",
                kwargs={"quest_id": self.quest.id, "pk": self.long_question1.id},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.long_question1.instructions)
        self.assertContains(response, self.long_question1.solution_text)

    def test_question_update_previous_content_file_upload(self):
        """The previous question's content should be displayed on the page"""
        self.client.force_login(self.test_teacher)
        response = self.client.get(
            reverse(
                "questions:update",
                kwargs={"quest_id": self.quest.id, "pk": self.file_question1.id},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.file_question1.instructions)
        question_file = response.context["question"].solution_file
        # self.assertEqual(question_file, self.file_upload1)
        # ensure file has same content
        self.assertEqual(question_file.read(), b'file_content')

    def test_question_update_short_answer(self):
        """Teachers should be able to update short answer questions"""
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse(
                "questions:update",
                kwargs={"quest_id": self.quest.id, "pk": self.question1.id},
            ),
            data=self.question_form_data1,
        )
        # there should be no form errors
        if response.context and "form" in response.context:
            form_errors = response.context["form"].errors
        else:
            form_errors = {}
        self.assertIsNone(response.context, f"Form errors: {form_errors}")
        self.assertEqual(response.status_code, 302)
        # make sure the question was updated
        self.assertEqual(Question.objects.get(id=self.question1.id).instructions, "Test instructions")

    def test_question_update_file_upload(self):
        """Teachers should be able to update file upload questions"""
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse(
                "questions:update",
                kwargs={"quest_id": self.quest.id, "pk": self.file_question1.id},
            ),
            data=self.question_form_file_data1,
        )
        # there should be no form errors
        if response.context and "form" in response.context:
            form_errors = response.context["form"].errors
        else:
            form_errors = {}
        self.assertIsNone(response.context, f"Form errors: {form_errors}")
        self.assertEqual(response.status_code, 302)
        # make sure the question was updated
        self.assertEqual(Question.objects.get(id=self.file_question1.id).instructions, "Test instructions")
        self.assertEqual(Question.objects.get(id=self.file_question1.id).solution_file.read(), b'file_content')

    def test_question_delete_student_access_denied(self):
        # log in the student
        self.client.force_login(self.test_student)
        response = self.client.get(
            reverse(
                "questions:delete",
                kwargs={"quest_id": self.quest.id, "pk": self.question1.id},
            )
        )
        self.assertEqual(response.status_code, 403)

    def test_question_delete_teacher_access_granted(self):
        self.client.force_login(self.test_teacher)
        response = self.client.get(
            reverse(
                "questions:delete",
                kwargs={"quest_id": self.quest.id, "pk": self.question1.id},
            )
        )
        self.assertEqual(response.status_code, 200)

    def test_teacher_delete_question(self):
        """Teachers should be able to delete questions. Ensure that it is actually deleted."""
        self.client.force_login(self.test_teacher)

        previous_question_count = Question.objects.count()
        response = self.client.post(
            reverse(
                "questions:delete",
                kwargs={"quest_id": self.quest.id, "pk": self.question1.id},
            )
        )
        self.assertEqual(response.status_code, 302)
        # make sure the question was deleted
        self.assertFalse(Question.objects.filter(id=self.question1.id).exists())
        # make sure the other question was not deleted
        self.assertTrue(Question.objects.filter(id=self.question2.id).exists())
        # make sure only one question was deleted
        self.assertEqual(Question.objects.count(), previous_question_count - 1)
