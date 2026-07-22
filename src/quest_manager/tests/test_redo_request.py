"""Tests for the "redo a past-completed quest" request/approval flow (issue #56)."""

from django.contrib.auth import get_user_model
from django.urls import reverse

from django_tenants.test.client import TenantClient
from model_bakery import baker

from courses.models import Block, CourseStudent, Semester
from hackerspace_online.tests.utils import ByteDeckTenantTestCase, ViewTestUtilsMixin
from notifications.models import Notification
from quest_manager.models import Quest, QuestSubmission, RedoRequest
from siteconfig.models import SiteConfig

User = get_user_model()


class RedoRequestTestMixin:
    """Shared setup: a teacher, a student, and a quest the student completed in a *past* semester."""

    @classmethod
    def setUpTestData(cls):
        """Complete a quest in the active semester, then open a new one so the completion is 'past'."""
        # a teacher must exist before students are created (profile signal notifies staff)
        cls.test_teacher = User.objects.create_user('test_teacher', is_staff=True)
        cls.test_student = User.objects.create_user('test_student')

        cls.quest = baker.make(Quest, name="Redoable Quest", xp=5)

        # complete the quest in the currently-active semester...
        cls.past_semester = SiteConfig.get().active_semester
        cls.past_submission = baker.make(
            QuestSubmission,
            user=cls.test_student,
            quest=cls.quest,
            semester=cls.past_semester,
            is_completed=True,
            is_approved=True,
        )

        # ...then open a new semester, so the completed submission is now "past".
        cls.current_semester = baker.make(Semester)
        SiteConfig.get().set_active_semester(cls.current_semester.id)

    def setUp(self):
        """Set up a tenant-aware test client."""
        self.client = TenantClient(self.tenant)


class RedoRequestModelTests(RedoRequestTestMixin, ByteDeckTenantTestCase):

    def test_has_pending__true_only_while_unanswered(self):
        """has_pending is True while a request is unanswered and False once approved/denied."""
        rr = RedoRequest.objects.create(user=self.test_student, quest=self.quest, semester=self.current_semester)
        self.assertTrue(RedoRequest.objects.has_pending(self.test_student, self.quest))
        self.assertTrue(rr.is_pending)

        rr.is_approved = True
        rr.save()
        self.assertFalse(RedoRequest.objects.has_pending(self.test_student, self.quest))
        self.assertFalse(rr.is_pending)

    def test_pending_manager__excludes_answered_requests(self):
        """The pending() manager returns unanswered requests and excludes answered ones."""
        approved = RedoRequest.objects.create(
            user=self.test_student, quest=self.quest, semester=self.current_semester, is_approved=True)
        pending = RedoRequest.objects.create(
            user=self.test_student, quest=baker.make(Quest), semester=self.current_semester)
        pending_qs = RedoRequest.objects.pending()
        self.assertIn(pending, pending_qs)
        self.assertNotIn(approved, pending_qs)

    def test_str__names_student_and_quest(self):
        """The string representation identifies the requesting student and the quest."""
        rr = RedoRequest.objects.create(user=self.test_student, quest=self.quest, semester=self.current_semester)
        self.assertEqual(str(rr), f"Redo request from {self.test_student} for {self.quest}")


class RedoRequestCreateViewTests(RedoRequestTestMixin, ViewTestUtilsMixin, ByteDeckTenantTestCase):

    def test_redo_request__get_is_404(self):
        """The request endpoint only accepts POST, not GET."""
        self.client.force_login(self.test_student)
        response = self.client.get(reverse('quests:redo_request', args=[self.past_submission.id]))
        self.assertEqual(response.status_code, 404)

    def test_redo_request__anonymous_redirected_to_login(self):
        """An anonymous user is redirected to login rather than creating a request."""
        self.assertRedirectsLogin('quests:redo_request', args=[self.past_submission.id])

    def test_redo_request__creates_request_and_notifies_teacher(self):
        """A student POST creates a pending request and notifies staff (no current teacher)."""
        self.client.force_login(self.test_student)
        teacher_notifications_before = Notification.objects.all_for_user(self.test_teacher).count()

        response = self.client.post(reverse('quests:redo_request', args=[self.past_submission.id]))

        self.assertRedirects(response, reverse('quests:past'))
        self.assertTrue(RedoRequest.objects.has_pending(self.test_student, self.quest))
        # falls back to notifying staff since the student has no current teacher/course
        self.assertEqual(
            Notification.objects.all_for_user(self.test_teacher).count(),
            teacher_notifications_before + 1,
        )

    def test_redo_request__cannot_request_another_students_submission(self):
        """A student can't request a redo of a submission that isn't theirs (404)."""
        other_student = User.objects.create_user('other_student')
        self.client.force_login(other_student)
        response = self.client.post(reverse('quests:redo_request', args=[self.past_submission.id]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(RedoRequest.objects.filter(user=other_student).exists())

    def test_redo_request__duplicate_request_is_blocked(self):
        """A second request for the same quest doesn't create a second pending record."""
        self.client.force_login(self.test_student)
        self.client.post(reverse('quests:redo_request', args=[self.past_submission.id]))
        self.client.post(reverse('quests:redo_request', args=[self.past_submission.id]))
        self.assertEqual(RedoRequest.objects.filter(user=self.test_student, quest=self.quest).count(), 1)

    def test_redo_request__no_open_semester_blocks_request(self):
        """If the active semester is closed, no redo request is created."""
        self.current_semester.closed = True
        self.current_semester.save()
        self.client.force_login(self.test_student)
        response = self.client.post(reverse('quests:redo_request', args=[self.past_submission.id]))
        self.assertRedirects(response, reverse('quests:past'))
        self.assertFalse(RedoRequest.objects.filter(user=self.test_student).exists())

    def test_redo_request__blocked_when_quest_already_in_progress_this_semester(self):
        """No request is created if the student already has the quest going this semester."""
        # a current-semester submission for the same quest already exists
        QuestSubmission.objects.create_submission(self.test_student, self.quest)
        self.client.force_login(self.test_student)
        response = self.client.post(reverse('quests:redo_request', args=[self.past_submission.id]))
        self.assertRedirects(response, reverse('quests:past'))
        self.assertFalse(RedoRequest.objects.filter(user=self.test_student, quest=self.quest).exists())

    def test_redo_request__notifies_students_current_teacher(self):
        """When the student is in a course, their block's teacher (not all staff) is notified."""
        block = baker.make(Block, current_teacher=self.test_teacher)
        baker.make(CourseStudent, user=self.test_student, block=block, semester=self.current_semester)
        self.client.force_login(self.test_student)
        teacher_notifications_before = Notification.objects.all_for_user(self.test_teacher).count()

        response = self.client.post(reverse('quests:redo_request', args=[self.past_submission.id]))

        self.assertRedirects(response, reverse('quests:past'))
        self.assertTrue(RedoRequest.objects.has_pending(self.test_student, self.quest))
        self.assertEqual(
            Notification.objects.all_for_user(self.test_teacher).count(),
            teacher_notifications_before + 1,
        )


class RedoRequestButtonRenderTests(RedoRequestTestMixin, ViewTestUtilsMixin, ByteDeckTenantTestCase):

    def _past_preview_html(self):
        """POST the past-submission AJAX preview and return its rendered HTML fragment."""
        response = self.client.post(
            reverse('quests:ajax_info_past', args=[self.past_submission.id]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        return response.json()['quest_info_html']

    def test_past_preview__shows_request_redo_button(self):
        """A past completion with no pending request shows the Request Redo button."""
        self.client.force_login(self.test_student)
        self.assertIn('Request Redo', self._past_preview_html())

    def test_past_preview__hides_button_when_request_pending(self):
        """The Request Redo button is hidden once a request is already pending for the quest."""
        RedoRequest.objects.create(user=self.test_student, quest=self.quest, semester=self.current_semester)
        self.client.force_login(self.test_student)
        self.assertNotIn('Request Redo', self._past_preview_html())

    def test_past_preview__hides_button_when_no_open_semester(self):
        """The Request Redo button is hidden when the active semester is closed."""
        self.current_semester.closed = True
        self.current_semester.save()
        self.client.force_login(self.test_student)
        self.assertNotIn('Request Redo', self._past_preview_html())

    def test_past_preview__hides_button_when_quest_in_progress_this_semester(self):
        """The Request Redo button is hidden when the quest is already on the go this semester."""
        QuestSubmission.objects.create_submission(self.test_student, self.quest)
        self.client.force_login(self.test_student)
        self.assertNotIn('Request Redo', self._past_preview_html())


class RedoRequestRespondViewTests(RedoRequestTestMixin, ViewTestUtilsMixin, ByteDeckTenantTestCase):

    def setUp(self):
        """Add a pending redo request for the teacher-response tests."""
        super().setUp()
        self.redo_request = RedoRequest.objects.create(
            user=self.test_student, quest=self.quest, semester=self.current_semester)

    def test_redo_requests_list__is_staff_only(self):
        """The redo-requests list page is 403 for students, 200 for staff, login-redirect for anon."""
        self.assertRedirectsLogin('quests:redo_requests')
        self.client.force_login(self.test_student)
        self.assert403('quests:redo_requests')
        self.client.force_login(self.test_teacher)
        self.assert200('quests:redo_requests')

    def test_redo_request_respond__is_staff_only(self):
        """Approve/deny endpoints are forbidden to students."""
        self.client.force_login(self.test_student)
        self.assertEqual(
            self.client.post(reverse('quests:redo_request_approve', args=[self.redo_request.id])).status_code, 403)
        self.assertEqual(
            self.client.post(reverse('quests:redo_request_deny', args=[self.redo_request.id])).status_code, 403)

    def test_redo_request_respond__requires_post(self):
        """A GET to either approve or deny endpoint is 404 (POST only)."""
        self.client.force_login(self.test_teacher)
        self.assertEqual(
            self.client.get(reverse('quests:redo_request_approve', args=[self.redo_request.id])).status_code, 404)
        self.assertEqual(
            self.client.get(reverse('quests:redo_request_deny', args=[self.redo_request.id])).status_code, 404)

    def test_redo_request_approve__creates_inprogress_submission_and_notifies_student(self):
        """Approving marks the request approved, creates a current-semester in-progress submission, notifies the student."""
        self.client.force_login(self.test_teacher)
        student_notifications_before = Notification.objects.all_for_user(self.test_student).count()

        response = self.client.post(reverse('quests:redo_request_approve', args=[self.redo_request.id]))

        self.assertRedirects(response, reverse('quests:redo_requests'))
        self.redo_request.refresh_from_db()
        self.assertTrue(self.redo_request.is_approved)
        self.assertEqual(self.redo_request.responded_by, self.test_teacher)
        self.assertIsNotNone(self.redo_request.datetime_responded)

        # a fresh in-progress submission now exists for the student in the current semester
        new_sub = QuestSubmission.objects.all_not_completed(user=self.test_student).get(quest=self.quest)
        self.assertEqual(new_sub.semester, self.current_semester)

        self.assertEqual(
            Notification.objects.all_for_user(self.test_student).count(),
            student_notifications_before + 1,
        )

    def test_redo_request_deny__marks_denied_and_creates_no_submission(self):
        """Denying marks the request denied and creates no in-progress submission."""
        self.client.force_login(self.test_teacher)
        response = self.client.post(reverse('quests:redo_request_deny', args=[self.redo_request.id]))

        self.assertRedirects(response, reverse('quests:redo_requests'))
        self.redo_request.refresh_from_db()
        self.assertTrue(self.redo_request.is_denied)
        self.assertEqual(self.redo_request.responded_by, self.test_teacher)
        # no new in-progress submission was created
        self.assertFalse(
            QuestSubmission.objects.all_not_completed(user=self.test_student).filter(quest=self.quest).exists())

    def test_redo_request_deny__already_answered_is_404(self):
        """Denying an already-answered request is 404 (it's no longer pending)."""
        self.redo_request.is_approved = True
        self.redo_request.save()
        self.client.force_login(self.test_teacher)
        self.assertEqual(
            self.client.post(reverse('quests:redo_request_deny', args=[self.redo_request.id])).status_code, 404)

    def test_redo_request_approve__already_answered_is_404(self):
        """Approving an already-answered request is 404 (it's no longer pending)."""
        self.redo_request.is_denied = True
        self.redo_request.save()
        self.client.force_login(self.test_teacher)
        self.assertEqual(
            self.client.post(reverse('quests:redo_request_approve', args=[self.redo_request.id])).status_code, 404)
