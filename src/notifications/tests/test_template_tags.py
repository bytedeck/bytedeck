from django.contrib.auth import get_user_model

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from notifications.models import Notification, new_notification
from notifications.templatetags.notification_tags import notification_unread, notification_url

User = get_user_model()


class NotificationTemplateTagsTest(ByteDeckTenantTestCase):
    """Tests for the notification_unread and notification_url template filters."""

    @classmethod
    def setUpTestData(cls):
        """A teacher, a student, and an announcement to hang notifications off of."""
        cls.teacher = User.objects.create_user('tt_teacher', is_staff=True)
        cls.student = User.objects.create_user('tt_student')
        cls.target = baker.make('announcements.Announcement')

    def _make_notification(self):
        """Create (or recreate) a single notification to the student about the target."""
        Notification.objects.filter(recipient=self.student).delete()
        new_notification(self.teacher, recipient=self.student, target=self.target, verb='posted')
        return Notification.objects.get_user_target(self.student, self.target)

    def test_notification_unread__returns_unread_state(self):
        """The filter reports True while the notification is unread and False once read."""
        note = self._make_notification()
        self.assertTrue(notification_unread(self.target, self.student))
        note.mark_read()
        self.assertFalse(notification_unread(self.target, self.student))

    def test_notification_unread__none_when_missing_args(self):
        """A missing target or user makes the filter return None rather than querying."""
        self.assertIsNone(notification_unread(None, self.student))
        self.assertIsNone(notification_unread(self.target, None))

    def test_notification_url__returns_target_url(self):
        """The filter returns the notification's own get_url()."""
        note = self._make_notification()
        self.assertEqual(notification_url(self.target, self.student), note.get_url())

    def test_notification_url__none_when_missing_args(self):
        """A missing target or user makes the filter return None."""
        self.assertIsNone(notification_url(None, self.student))
        self.assertIsNone(notification_url(self.target, None))
