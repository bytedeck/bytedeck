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
        cls.teacher = User.objects.create_user('tt_teacher', is_staff=True)
        cls.student = User.objects.create_user('tt_student')
        cls.target = baker.make('announcements.Announcement')

    def _make_notification(self):
        Notification.objects.filter(recipient=self.student).delete()
        new_notification(self.teacher, recipient=self.student, target=self.target, verb='posted')
        return Notification.objects.get_user_target(self.student, self.target)

    def test_notification_unread__returns_unread_state(self):
        note = self._make_notification()
        self.assertTrue(notification_unread(self.target, self.student))
        note.mark_read()
        self.assertFalse(notification_unread(self.target, self.student))

    def test_notification_unread__none_when_missing_args(self):
        self.assertIsNone(notification_unread(None, self.student))
        self.assertIsNone(notification_unread(self.target, None))

    def test_notification_url__returns_target_url(self):
        note = self._make_notification()
        self.assertEqual(notification_url(self.target, self.student), note.get_url())

    def test_notification_url__none_when_missing_args(self):
        self.assertIsNone(notification_url(None, self.student))
        self.assertIsNone(notification_url(self.target, None))
