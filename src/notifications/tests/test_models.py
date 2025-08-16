from django.contrib.auth import get_user_model

from django_tenants.test.cases import TenantTestCase
from django.contrib.contenttypes.models import ContentType
from unittest import TestCase
from model_bakery import baker
from model_bakery.recipe import Recipe

from notifications.models import Notification, new_notification


class NotificationModelTest(TenantTestCase):

    def setUp(self):
        User = get_user_model()
        self.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        self.student = baker.make(User)
        # self.assertion = baker.make(BadgeAssertion)
        # self.badge = Recipe(Badge, xp=20).make()
        # self.badge_assertion_recipe = Recipe(BadgeAssertion, user=self.student, badge=self.badge)

    def test_notification_creation(self):
        notification = Notification.objects.create(
            recipient=self.student,
            sender_content_type=ContentType.objects.get_for_model(self.teacher),
            sender_object_id=self.teacher.id,
            verb="sent you a notification"
        )
        notification.full_clean()
        notification.save()
        self.assertIsInstance(notification, Notification)
        self.assertIsNotNone(str(notification))

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
            action (any Model): Used alongside "verb" to create syntax of notification ie. "<user> <verb> with <action>"
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

    def test_url_correct_comment_hash(self):
        """ Checks if instances where an url is given. There is a corresponding comment hash with it
        ie. url...#comment-id.

        So far the only functions that use target_object.get_absolute_url are:
        - __str__
        - get_url()
        """
        # create notification with comment as an action and corresponding verb
        comment = baker.make('comments.Comment')
        new_notification(
            self.student,
            action=comment,
            target=baker.make('announcements.Announcement'),
            recipient=self.student,
            affected_users=[self.teacher],
            verb="commented on",
        )
        # since new_notification does not return anything, have to get it from query
        notification = Notification.objects.order_by('id').last()
        self.assertEqual(notification.verb, "commented on")
        self.assertEqual(notification.action_object_id, comment.id)

        # Base case: check if notification without comment does not have hash
        base_notification = Notification.objects.create(
            recipient=self.student,
            sender_content_type=ContentType.objects.get_for_model(self.teacher),
            sender_object_id=self.teacher.id,
            verb="sent you a notification"
        )
        base_notification.full_clean()
        base_notification.save()

        self.assertFalse('#comment-' in base_notification.get_url())
        self.assertFalse('#comment-' in str(base_notification))

        # check if notification with comment has a hash
        comment_hash = f'#comment-{comment.id}'
        self.assertTrue(comment_hash in notification.get_url())
        self.assertTrue(comment_hash in str(notification))


class NotificationModel_html_strip_Test(TestCase):
    """
        This test class is specialized on testing the html_strip() method of Notification model
    """

    def setUp(self):
        pass

    def test_notification_html_strip__check_with_no_html(self):
        """
            Base case test to see if html_strip() wont strip normal text
        """
        test_case = "TEST CASE 1 NO STRIPPED TAGS"
        expected_case = "TEST CASE 1 NO STRIPPED TAGS"

        self.assertEqual(
            Notification.html_strip(test_case),
            expected_case
        )

    def test_notification_html_strip__check_with_html(self):
        """
            Test that html_strip() strips out any html tags (excluding img).
            <img> tags are not tested here.
        """
        test_case = "<p>TEST CASE 2</p> WITH <h1>HTML</h1> TAGS"
        expected_case = "TEST CASE 2 WITH HTML TAGS"

        self.assertEqual(
            Notification.html_strip(test_case),
            expected_case
        )

    def test_notification_html_strip__check_with_img_tag(self):
        """
            Test that html_strip() wont strip out any img tags.
        """
        test_case = 'TEST CASE 3 WITH IMG <img src="SOURCE" style="should be empty"></img> TAG'
        expected_case = 'TEST CASE 3 WITH IMG <img height="20px" src="SOURCE" style="" width="auto"/> TAG'

        self.assertEqual(
            Notification.html_strip(test_case),
            expected_case
        )

    def test_notification_html_strip__check_with_html_and_img_tag(self):
        """
            Test that html_strip() strips out any html tags and excludes img tags.
        """
        test_case = '<h1>TEST CASE 4</h1> <p>HTML</p> AND IMG <img src="SOURCE" style="should be empty"></img> TAGS'
        expected_case = 'TEST CASE 4 HTML AND IMG <img height="20px" src="SOURCE" style="" width="auto"/> TAGS'

        self.assertEqual(
            Notification.html_strip(test_case),
            expected_case
        )
