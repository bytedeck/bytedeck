from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from django.contrib.contenttypes.models import ContentType
from unittest import TestCase
from model_bakery import baker
from model_bakery.recipe import Recipe

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from notifications.models import Notification, new_notification

User = get_user_model()


class NotificationModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        cls.student = baker.make(User)
        # cls.assertion = baker.make(BadgeAssertion)
        # cls.badge = Recipe(Badge, xp=20).make()
        # cls.badge_assertion_recipe = Recipe(BadgeAssertion, user=cls.student, badge=cls.badge)

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

    def test_new_notification__bulk_creates_one_insert_for_many_recipients(self):
        """new_notification writes every recipient's notification in a single bulk
        INSERT instead of one save() per recipient."""
        recipients = baker.make(User, _quantity=5)

        with CaptureQueriesContext(connection) as ctx:
            new_notification(
                self.teacher,
                recipient=self.student,  # required kwarg, unused when affected_users given
                affected_users=recipients,
                verb="tested",
            )

        # a single bulk INSERT covers all recipients (was one INSERT per recipient)
        inserts = [q for q in ctx.captured_queries if 'insert into "notifications_notification"' in q['sql'].lower()]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(Notification.objects.filter(recipient__in=recipients).count(), 5)

    def test_new_notification__skips_sender(self):
        """A user does not get notified about their own action, even when listed
        in affected_users (regression guard for the bulk_create refactor)."""
        # clear notifications created as a side effect of user creation in setUp
        Notification.objects.all().delete()

        new_notification(
            self.teacher,
            recipient=self.student,
            affected_users=[self.teacher, self.student],
            verb="tested",
        )
        # only the student (not the sender/teacher) should have a notification
        self.assertEqual(Notification.objects.filter(recipient=self.teacher).count(), 0)
        self.assertEqual(Notification.objects.filter(recipient=self.student).count(), 1)

    def test_mark_all_read__single_update_sets_unread_and_time_read(self):
        """mark_all_read marks every unread notification read and stamps time_read
        in one UPDATE (the previous two-update version left time_read unset)."""
        baker.make(Notification, recipient=self.student, unread=True, time_read=None, _quantity=3)
        self.assertEqual(Notification.objects.all_unread(self.student).count(), 3)

        with CaptureQueriesContext(connection) as ctx:
            Notification.objects.all().mark_all_read(self.student)

        updates = [q for q in ctx.captured_queries if q['sql'].lstrip().upper().startswith('UPDATE')]
        self.assertEqual(len(updates), 1)

        self.assertEqual(Notification.objects.all_unread(self.student).count(), 0)
        # time_read must actually be set now, not left None
        for note in Notification.objects.filter(recipient=self.student):
            self.assertIsNotNone(note.time_read)

    def test_mark_all_unread__single_update_sets_unread_and_clears_time_read(self):
        """mark_all_unread marks read notifications unread and clears time_read in
        one UPDATE (the previous two-update version left time_read set)."""
        baker.make(
            Notification, recipient=self.student, unread=False, time_read=timezone.now(), _quantity=3,
        )
        self.assertEqual(Notification.objects.all_read(self.student).count(), 3)

        with CaptureQueriesContext(connection) as ctx:
            Notification.objects.all().mark_all_unread(self.student)

        updates = [q for q in ctx.captured_queries if q['sql'].lstrip().upper().startswith('UPDATE')]
        self.assertEqual(len(updates), 1)

        self.assertEqual(Notification.objects.all_read(self.student).count(), 0)
        for note in Notification.objects.filter(recipient=self.student):
            self.assertTrue(note.unread)
            self.assertIsNone(note.time_read)

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
