from django.contrib.auth import get_user_model

from django_tenants.test.cases import TenantTestCase
from model_bakery import baker
from model_bakery.recipe import Recipe

from notifications.models import Notification, new_notification


class NotificationModelTest(TenantTestCase):

    def setUp(self):
        User = get_user_model()
        self.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        self.student = baker.make(User)
        self.notification = baker.make(Notification)
        # self.assertion = baker.make(BadgeAssertion)
        # self.badge = Recipe(Badge, xp=20).make()
        # self.badge_assertion_recipe = Recipe(BadgeAssertion, user=self.student, badge=self.badge)

    def test_notification_creation(self):
        self.assertIsInstance(self.notification, Notification)
        self.assertIsNotNone(str(self.notification))

    def test_mark_read(self):
        notification = baker.make(Notification)
        self.assertTrue(notification.unread)
        notification.mark_read()
        self.assertFalse(notification.unread)

    def test_new_notification(self):
        """
        def new_notification(sender, **kwargs):
        Creates notification when a signal is sent with notify.send(sender, **kwargs)
        :param sender: the object (any Model) initiating/causing the notification
        :param kwargs:
            target (any Model): The object being notified about (Submission, Comment, BadgeAssertion, etc.)
            action (any Model): Not sure... not used I assume.
            recipient (User): The receiving User, required (but not used if affected_users are provided ...?)
            affected_users (list of Users): everyone who should receive the notification
            verb (string): sender 'verb' [target] [action]. E.g MrC 'commented on' SomeAnnouncement
            icon (html string): e.g.:
                "<span class='fa-stack'>" + \
                "<i class='fa fa-comment-o fa-flip-horizontal fa-stack-1x'></i>" + \
                "<i class='fa fa-ban fa-stack-2x text-danger'></i>" + \
                "</span>"
        :return:
        """

        # make sure the student doesn't have any notifications yet
        notes_before = self.student.notifications.all()
        self.assertEqual(notes_before.count(), 0)

        kwargs = {
            'recipient': self.student,
            'verb': 'tested'
        }
        new_notification(self.teacher, **kwargs)

        # now the student should have one if it worked.
        notes_after = self.student.notifications.all()
        self.assertEqual(notes_after.count(), 1)

        notes_unread = Notification.objects.all_unread(self.student)
        self.assertEqual(notes_unread.count(), 1)
