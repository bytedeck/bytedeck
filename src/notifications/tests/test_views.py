from django.contrib.auth import get_user_model
from django.shortcuts import reverse

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from model_bakery import baker

from hackerspace_online.tests.utils import ViewTestUtilsMixin

User = get_user_model()


class NotificationViewTests(ViewTestUtilsMixin, TenantTestCase):

    # includes some basic model data
    # fixtures = ['initial_data.json']

    def setUp(self):
        self.client = TenantClient(self.tenant)

        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)
        self.test_student2 = baker.make(User)

    def test_all_notification_page_status_codes_for_anonymous(self):
        ''' If not logged in then all views should redirect to home page '''

        self.assertRedirectsLogin('notifications:list')
        self.assertRedirectsLogin('notifications:list_unread')
        self.assertRedirectsLogin('notifications:read', kwargs={'id': 1})
        self.assertRedirectsLogin('notifications:read_all')

        self.assertRedirectsLogin('notifications:ajax')  # this doesn't make sense.  Should 404
        self.assertRedirectsLogin('notifications:ajax_mark_read')  # this doesn't make sense.  Should 404

    def test_all_notification_page_status_codes_for_students(self):
        # log in student1
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        # Accessible views:
        self.assertEqual(self.client.get(reverse('notifications:list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('notifications:list_unread')).status_code, 200)

        self.assertRedirects(
            response=self.client.get(reverse('notifications:read_all')),
            expected_url=reverse('notifications:list'),
        )

        # Inaccessible views:
        self.assertEqual(self.client.get(reverse('notifications:ajax_mark_read')).status_code, 404)  # requires AJAX
        self.assertEqual(self.client.get(reverse('notifications:ajax')).status_code, 404)  # requires POST

    def test_all_notification_page_status_codes_for_teachers(self):
        # log in student1
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        # Accessible views:
        self.assertEqual(self.client.get(reverse('notifications:list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('notifications:list_unread')).status_code, 200)

        self.assertRedirects(
            response=self.client.get(reverse('notifications:read_all')),
            expected_url=reverse('notifications:list'),
        )

        # Inaccessible views:
        self.assertEqual(self.client.get(reverse('notifications:ajax_mark_read')).status_code, 404)  # requires POST
        self.assertEqual(self.client.get(reverse('notifications:ajax')).status_code, 404)  # requires POST

    def test_ajax_mark_read(self):
        """ Marks a Notification as read via Ajax (by setting unread = FALSE)
        """
        # log in student1
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        notification = baker.make('notifications.Notification', recipient=self.test_student1)
        # make sure it is unread
        self.assertTrue(notification.unread)

        # mark it as read via the view being tested
        ajax_data = {
            'id': notification.id,
        }
        response = self.client.post(
            reverse('notifications:ajax_mark_read'),
            data=ajax_data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)

    def test_ajax(self):
        # log in student1
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        response = self.client.post(
            reverse('notifications:ajax'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
