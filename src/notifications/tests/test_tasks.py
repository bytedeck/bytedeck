from datetime import timedelta
from model_bakery import baker
from unittest.mock import patch

from django_tenants.test.cases import TenantTestCase

from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from notifications import tasks
from notifications.models import Notification
from notifications.tasks import generate_notification_email, get_notification_emails, delete_old_notifications
from siteconfig.models import SiteConfig

User = get_user_model()


class NotificationTasksTests(TenantTestCase):
    """ Run tasks asyncronously with apply() """

    def setUp(self):

        config = SiteConfig.get()
        self.sem = config.active_semester
        config.site_name_short = "Deck"
        config.save()
        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', email="student@email.com")
        self.test_student2 = baker.make(User, email="student2@email.com")

        self.ai_user, _ = User.objects.get_or_create(
            pk=SiteConfig.get().deck_ai.pk,
            defaults={
                'username': "Autogenerated AI",
            },
        )

        baker.make('courses.CourseStudent', user=self.test_student1, semester=self.sem)
        baker.make('courses.CourseStudent', user=self.test_student2, semester=self.sem)

    def test_get_notification_emails(self):
        """ Test that the correct list of notification emails are generated"""
        root_url = f'https://{self.get_test_tenant_domain()}'

        # 0 notifications to start
        emails = get_notification_emails(root_url)
        self.assertEqual(type(emails), list)
        self.assertEqual(len(emails), 0)

        course = baker.make('courses.Course')
        semester = SiteConfig.get().active_semester

        # Create a notification for student 1, but they have emails turned off by default
        notification1 = baker.make(Notification, recipient=self.test_student1)
        emails = get_notification_emails(root_url)
        self.assertEqual(len(emails), 0)

        # Turn on notification emails for student1, now it should appear and add them to the list of emails
        from allauth.account.models import EmailAddress

        EmailAddress.objects.create(user=self.test_student1, email=self.test_student1.email, verified=True, primary=True)
        baker.make('courses.CourseStudent', user=self.test_student1, course=course, semester=semester)
        self.test_student1.profile.get_notifications_by_email = True
        self.test_student1.profile.save()

        emails = get_notification_emails(root_url)

        self.assertEqual(len(emails), 1)
        self.assertEqual(emails[0].to, [self.test_student1.email])

        # Turn on notification emails for student2, should still only be 1 (from the test_student1)
        EmailAddress.objects.create(user=self.test_student2, email=self.test_student2.email, verified=True, primary=True)
        baker.make('courses.CourseStudent', user=self.test_student2, course=course, semester=semester)
        self.test_student2.profile.get_notifications_by_email = True
        self.test_student2.profile.save()

        emails = get_notification_emails(root_url)
        self.assertEqual(len(emails), 1)
        self.assertEqual(emails[0].to, [self.test_student1.email])

        # Make a bunch of notifications for student2, so now we should have 2 emails
        baker.make(Notification, recipient=self.test_student2, _quantity=10)
        emails = get_notification_emails(root_url)

        self.assertEqual(len(emails), 2)
        self.assertEqual(emails[0].to, [self.test_student1.email])
        self.assertEqual(emails[1].to, [self.test_student2.email])

        # mark the original notification as read, so only student2 email now
        notification1.unread = False
        notification1.save()
        emails = get_notification_emails(root_url)
        self.assertEqual(len(emails), 1)
        self.assertEqual(emails[0].to, [self.test_student2.email])

    def test_email_notifications_to_users_on_all_schemas(self):
        task_result = tasks.email_notification_to_users_on_all_schemas.apply()
        self.assertTrue(task_result.successful())

    def test_email_notifications_to_users(self):
        task_result = tasks.email_notifications_to_users_on_schema.apply(
            kwargs={
                "root_url": "https://test.com",
            }
        )
        self.assertTrue(task_result.successful())

    def test_generate_notification_email__student(self):
        """ Test that the content of a notification email is correct """
        notifications = baker.make(Notification, recipient=self.test_student1, _quantity=2)

        root_url = 'https://test.com'
        email = generate_notification_email(self.test_student1, root_url)

        self.assertEqual(type(email), EmailMultiAlternatives)
        self.assertEqual(email.to, [self.test_student1.email])
        # Default deck short name is "Deck"
        self.assertEqual(email.subject, "Deck Notifications")

        # https://stackoverflow.com/questions/62958111/how-to-display-html-content-of-an-emailmultialternatives-mail-object
        html_content = email.alternatives[0][0]

        self.assertNotIn("Quest submissions awaiting your approval", html_content)  # Teachers only

        self.assertIn("Unread notifications:", html_content)
        self.assertIn(str(notifications[0]), html_content)  # Links to notifications
        self.assertIn(str(notifications[1]), html_content)  # Links to notifications

    def test_generate_notification_email__staff(self):
        """ Test that staff notification emails include quests awaiting approval """
        notification = baker.make(Notification, recipient=self.test_teacher)
        root_url = 'https://test.com'
        sub = baker.make('quest_manager.questsubmission')

        # fake the call to `QuestSubmission.objects.all_awaiting_approval` made within
        # `generate_notification_email` so that it return a submission
        with patch('notifications.tasks.QuestSubmission.objects.all_awaiting_approval', return_value=[sub]):
            email = generate_notification_email(self.test_teacher, root_url)

        self.assertEqual(type(email), EmailMultiAlternatives)
        self.assertEqual(email.to, [self.test_teacher.email])

        # https://stackoverflow.com/questions/62958111/how-to-display-html-content-of-an-emailmultialternatives-mail-object
        html_content = email.alternatives[0][0]
        self.assertIn("Quest submissions awaiting your approval", html_content)  # Teachers only
        self.assertIn(str(sub), html_content)

        self.assertIn("Unread notifications:", html_content)
        self.assertIn(str(notification), html_content)  # Links to notifications

    def test_does_not_generate_email_for_inactive_students(self):
        root_url = 'https://test.com'

        # 0 notifications to start
        emails = get_notification_emails(root_url)
        self.assertEqual(type(emails), list)
        self.assertEqual(len(emails), 0)

        # Create a noficiation for 1 student that has no course but have emails turned on
        inactive_student = baker.make(User)
        baker.make(Notification, recipient=inactive_student)

        inactive_student.profile.get_notifications_by_email = True
        inactive_student.profile.save()

        # Should not get email because they are not enrolled in any courses
        emails = get_notification_emails(root_url)
        self.assertEqual(len(emails), 0)


class DeleteOldNotificationsTestCase(TenantTestCase):
    def setUp(self):
        super().setUp()

        self.old_notification = baker.make(
            Notification,
            timestamp=timezone.now() - timedelta(days=90)  # Older than 3 months
        )

        self.recent_notification = baker.make(
            Notification,
            timestamp=timezone.now() - timedelta(days=89)  # Within 3 months
        )

        self.notification_count = Notification.objects.count()

    def test_task_deletes_old_notifications(self):
        """Ensure old notifications >90 days are deleted but recent ones remain."""
        delete_old_notifications()

        with self.assertRaises(Notification.DoesNotExist):
            self.old_notification.refresh_from_db()  # Should be deleted

        self.recent_notification.refresh_from_db()  # Should still exist

    @patch('notifications.tasks.delete_old_notifications.delay')
    def test_task_is_called_properly(self, mock_task):
        """Ensure the task can be scheduled via Celery."""
        delete_old_notifications.delay()
        mock_task.assert_called_once()
