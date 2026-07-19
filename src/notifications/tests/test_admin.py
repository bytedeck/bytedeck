from datetime import timedelta

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase, request_with_messages
from notifications.admin import NotificationAdmin
from notifications.models import Notification

User = get_user_model()


def _make_note(sender, recipient):
    """Build a Notification with an explicit sender GFK (avoids model_bakery's random GFK)."""
    return baker.make(
        Notification,
        sender_content_type=ContentType.objects.get_for_model(sender),
        sender_object_id=sender.id,
        recipient=recipient,
    )


class NotificationAdminTest(ByteDeckTenantTestCase):
    """Tests for the NotificationAdmin custom admin action."""

    def setUp(self):
        """Build a NotificationAdmin and a message-enabled request for the action."""
        self.admin = NotificationAdmin(model=Notification, admin_site=AdminSite())
        self.request = request_with_messages()

    def test_delete_old_notifications_action__deletes_old_and_messages(self):
        """The admin action deletes notifications older than 90 days and reports the result via message_user."""
        sender = baker.make(User)
        recipient = baker.make(User)
        # An old notification (older than the 90 day cutoff) and a fresh one. (User
        # creation itself emits some notifications, so assert on these two by pk
        # rather than on the total count.)
        old = _make_note(sender, recipient)
        Notification.objects.filter(pk=old.pk).update(timestamp=timezone.now() - timedelta(days=100))
        fresh = _make_note(sender, recipient)

        self.admin.delete_old_notifications_action(self.request, Notification.objects.all())

        # The old notification is deleted; the fresh one survives.
        self.assertFalse(Notification.objects.filter(pk=old.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=fresh.pk).exists())
        messages = list(self.request._messages)
        self.assertEqual(len(messages), 1)
