from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from django_tenants.test.client import TenantClient
from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase, ViewTestUtilsMixin
from quest_manager.models import Quest
from questions.models import Question
from siteconfig.models import SiteConfig

User = get_user_model()


class QuestionCRUDViewTest(ViewTestUtilsMixin, ByteDeckTenantTestCase):
    """Tests for the staff-only question CRUD views (list/create/update/delete), on a deck
    that has opted into the feature via SiteConfig.enable_submission_questions."""

    @classmethod
    def setUpTestData(cls):
        """Enable submission questions for the deck, plus a teacher, a student, and a quest
        with one question of each type."""
        config = SiteConfig.get()
        config.enable_submission_questions = True
        config.save()

        cls.test_teacher = User.objects.create_user("test_teacher", password="password", is_staff=True)
        cls.test_student = User.objects.create_user("test_student", password="password")

        cls.quest = baker.make(Quest, xp=5)
        cls.other_quest = baker.make(Quest)
        cls.question1 = baker.make(
            Question, quest=cls.quest, ordinal=1, instructions="Test instructions 1",
        )
        cls.question2 = baker.make(
            Question, quest=cls.quest, ordinal=2, instructions="Test instructions 2",
        )
        cls.long_question1 = baker.make(
            Question, quest=cls.quest, ordinal=4, type="long_answer",
            instructions="Test instructions", solution_text="Test solution text",
        )

    def setUp(self):
        """Set up a tenant test client, per-test form data, and a file_upload question
        (per-test because its uploaded file is consumed when read)."""
        self.client = TenantClient(self.tenant)
        self.question_form_data = {
            "type": "short_answer",
            "instructions": "Test instructions",
            "solution_text": "Test solution text",
            "required": True,
        }
        self.file_upload = SimpleUploadedFile("file.mp4", b"file_content", content_type="video/mp4")
        self.file_question1 = baker.make(
            Question, quest=self.quest, ordinal=5, type="file_upload",
            instructions="Test instructions", solution_file=self.file_upload,
        )
        self.question_form_file_data = {
            "type": "file_upload",
            "instructions": "Test instructions",
            "required": True,
            "solution_file": SimpleUploadedFile("file2.mp4", b"file_content", content_type="video/mp4"),
            "allowed_file_type": "video",
        }

    def assertNoFormErrors(self, response):
        """Fail with the form's errors if the response re-rendered the form instead of redirecting."""
        if response.context and "form" in response.context:
            self.fail(f"Form errors: {response.context['form'].errors}")
        self.assertEqual(response.status_code, 302)

    def test_all_question_page_status_codes__anonymous(self):
        """If not logged in then all question views should redirect to the login page."""
        self.assertRedirectsLogin("questions:list", kwargs={"quest_id": self.quest.id})
        self.assertRedirectsLogin(
            "questions:create", kwargs={"quest_id": self.quest.id, "question_type": "short_answer"})
        self.assertRedirectsLogin(
            "questions:update", kwargs={"quest_id": self.quest.id, "pk": self.question1.id})
        self.assertRedirectsLogin(
            "questions:delete", kwargs={"quest_id": self.quest.id, "pk": self.question1.id})

    def test_all_question_page_status_codes__student(self):
        """Students get a 403 from every question view: question CRUD is staff-only."""
        self.client.force_login(self.test_student)
        self.assert403("questions:list", kwargs={"quest_id": self.quest.id})
        self.assert403(
            "questions:create", kwargs={"quest_id": self.quest.id, "question_type": "short_answer"})
        self.assert403(
            "questions:update", kwargs={"quest_id": self.quest.id, "pk": self.question1.id})
        self.assert403(
            "questions:delete", kwargs={"quest_id": self.quest.id, "pk": self.question1.id})

    def test_list__teacher_sees_questions(self):
        """Teachers can view a quest's question list, which displays each question's
        (truncated) instructions."""
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse("questions:list", kwargs={"quest_id": self.quest.id}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "questions/question_list.html")
        # NOTE: instructions are truncated at 20 characters in the table, so these
        # fixture instructions must be shorter than that to assert on them
        self.assertContains(response, self.question1.instructions)
        self.assertContains(response, self.question2.instructions)

    def test_list__invalid_quest_404(self):
        """The question list for a nonexistent quest is a 404."""
        self.client.force_login(self.test_teacher)
        self.assert404("questions:list", kwargs={"quest_id": 99999999})

    def test_create__teacher_get(self):
        """Teachers can open the create form for a supported question type."""
        self.client.force_login(self.test_teacher)
        self.assert200(
            "questions:create", kwargs={"quest_id": self.quest.id, "question_type": "short_answer"})

    def test_create__invalid_type_404(self):
        """Creating a question with an unsupported type in the URL is a 404 (not a crash)."""
        self.client.force_login(self.test_teacher)
        self.assert404(
            "questions:create",
            kwargs={"quest_id": self.quest.id, "question_type": "invalid_question_type"})

    def test_create__student_denied_nothing_created(self):
        """A student POSTing to the create view gets a 403 and no question is created."""
        self.client.force_login(self.test_student)
        question_count_before = Question.objects.count()
        response = self.client.post(
            reverse("questions:create",
                    kwargs={"quest_id": self.quest.id, "question_type": "short_answer"}),
            data=self.question_form_data,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Question.objects.count(), question_count_before)

    def test_create__teacher_short_answer(self):
        """A teacher can create a short answer question; it lands on the quest at the next
        ordinal and redirects back to the question list."""
        self.client.force_login(self.test_teacher)
        question_count_before = Question.objects.count()
        response = self.client.post(
            reverse("questions:create",
                    kwargs={"quest_id": self.quest.id, "question_type": "short_answer"}),
            data=self.question_form_data,
        )
        self.assertNoFormErrors(response)
        self.assertRedirects(response, reverse("questions:list", kwargs={"quest_id": self.quest.id}))
        self.assertEqual(Question.objects.count(), question_count_before + 1)
        new_question = Question.objects.filter(quest=self.quest).order_by("ordinal").last()
        self.assertEqual(new_question.instructions, "Test instructions")
        self.assertEqual(new_question.ordinal, 6)  # next_ordinal: after the setUp file question's ordinal 5

    def test_create__teacher_file_upload(self):
        """A teacher can create a file upload question, including its solution file."""
        self.client.force_login(self.test_teacher)
        question_count_before = Question.objects.count()
        response = self.client.post(
            reverse("questions:create",
                    kwargs={"quest_id": self.quest.id, "question_type": "file_upload"}),
            data=self.question_form_file_data,
        )
        self.assertNoFormErrors(response)
        self.assertEqual(Question.objects.count(), question_count_before + 1)
        new_question = Question.objects.filter(quest=self.quest, type="file_upload").order_by("ordinal").last()
        self.assertEqual(new_question.allowed_file_type, "video")
        self.assertEqual(new_question.solution_file.read(), b"file_content")

    def test_update__teacher_get_short_answer(self):
        """The update form shows the question's existing content."""
        self.client.force_login(self.test_teacher)
        response = self.client.get(
            reverse("questions:update",
                    kwargs={"quest_id": self.quest.id, "pk": self.question2.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.question2.instructions)

    def test_update__teacher_get_long_answer(self):
        """The update form for a long answer question shows its instructions and solution text."""
        self.client.force_login(self.test_teacher)
        response = self.client.get(
            reverse("questions:update",
                    kwargs={"quest_id": self.quest.id, "pk": self.long_question1.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.long_question1.instructions)
        self.assertContains(response, self.long_question1.solution_text)

    def test_update__teacher_get_file_upload(self):
        """The update form for a file upload question shows its instructions and keeps the
        existing solution file."""
        self.client.force_login(self.test_teacher)
        response = self.client.get(
            reverse("questions:update",
                    kwargs={"quest_id": self.quest.id, "pk": self.file_question1.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.file_question1.instructions)
        self.assertEqual(response.context["question"].solution_file.read(), b"file_content")

    def test_update__teacher_post(self):
        """A teacher can update a question; the changes persist."""
        self.client.force_login(self.test_teacher)
        self.question_form_data["instructions"] = "Updated instructions"
        response = self.client.post(
            reverse("questions:update",
                    kwargs={"quest_id": self.quest.id, "pk": self.question1.id}),
            data=self.question_form_data,
        )
        self.assertNoFormErrors(response)
        self.question1.refresh_from_db()
        self.assertEqual(self.question1.instructions, "Updated instructions")

    def test_update__wrong_quest_404(self):
        """A question can't be addressed through another quest's URL: the update view 404s
        when the quest_id doesn't match the question's quest."""
        self.client.force_login(self.test_teacher)
        self.assert404(
            "questions:update",
            kwargs={"quest_id": self.other_quest.id, "pk": self.question1.id})

    def test_delete__teacher_get_confirmation(self):
        """The delete view shows a confirmation page."""
        self.client.force_login(self.test_teacher)
        self.assert200(
            "questions:delete", kwargs={"quest_id": self.quest.id, "pk": self.question1.id})

    def test_delete__teacher_post(self):
        """A teacher can delete a question; only that question is removed, and the view
        redirects back to the question list."""
        self.client.force_login(self.test_teacher)
        previous_question_count = Question.objects.count()
        response = self.client.post(
            reverse("questions:delete",
                    kwargs={"quest_id": self.quest.id, "pk": self.question1.id}))
        self.assertRedirects(response, reverse("questions:list", kwargs={"quest_id": self.quest.id}))
        self.assertFalse(Question.objects.filter(id=self.question1.id).exists())
        self.assertTrue(Question.objects.filter(id=self.question2.id).exists())
        self.assertEqual(Question.objects.count(), previous_question_count - 1)

    def test_delete__wrong_quest_404(self):
        """A question can't be deleted through another quest's URL."""
        self.client.force_login(self.test_teacher)
        self.assert404(
            "questions:delete",
            kwargs={"quest_id": self.other_quest.id, "pk": self.question1.id})
        self.assertTrue(Question.objects.filter(id=self.question1.id).exists())


class QuestionViewsFeatureDisabledTest(ViewTestUtilsMixin, ByteDeckTenantTestCase):
    """With SiteConfig.enable_submission_questions left at its default (False), the question
    URLs must not exist for anyone — the deck has not opted into the feature."""

    @classmethod
    def setUpTestData(cls):
        """A teacher and a quest with one question; the feature flag stays at its default (off)."""
        cls.test_teacher = User.objects.create_user("test_teacher", password="password", is_staff=True)
        cls.quest = baker.make(Quest)
        cls.question = baker.make(Question, quest=cls.quest, ordinal=1)

    def setUp(self):
        """Set up a tenant test client for each test."""
        self.client = TenantClient(self.tenant)

    def test_flag_default__disabled(self):
        """The feature flag defaults to off so existing decks are unaffected by the upgrade."""
        self.assertFalse(SiteConfig.get().enable_submission_questions)

    def test_all_question_pages__404_for_staff_when_disabled(self):
        """Even staff get a 404 from every question view while the deck hasn't enabled the feature."""
        self.client.force_login(self.test_teacher)
        self.assert404("questions:list", kwargs={"quest_id": self.quest.id})
        self.assert404(
            "questions:create", kwargs={"quest_id": self.quest.id, "question_type": "short_answer"})
        self.assert404(
            "questions:update", kwargs={"quest_id": self.quest.id, "pk": self.question.id})
        self.assert404(
            "questions:delete", kwargs={"quest_id": self.quest.id, "pk": self.question.id})

    def test_all_question_pages__404_for_anonymous_when_disabled(self):
        """Anonymous users get a 404 (not a login redirect) while the feature is off — the
        URLs shouldn't reveal their existence on a deck that hasn't opted in."""
        self.assert404("questions:list", kwargs={"quest_id": self.quest.id})
        self.assert404(
            "questions:create", kwargs={"quest_id": self.quest.id, "question_type": "short_answer"})
