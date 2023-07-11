import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.shortcuts import reverse

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name

from hackerspace_online.tests.utils import ViewTestUtilsMixin

User = get_user_model()


class NonPublicOnlyAuthViewTests(ViewTestUtilsMixin, TenantTestCase):
    """
    Custom `non_public_only_view` decorator was applied on every `allauth` views.
    """

    def setUp(self):
        self.client = TenantClient(self.tenant)

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_public_tenant(self, mock_connection1, mock_connection2):
        """
        Overriden (decorated) `allauth` view should not be accessible for public tenant schemas,
        ie. return 404 (not found) for general public.
        """
        self.assert404('account_signup')  # not found
        self.assert404('account_login')  # not found
        self.assert404('account_logout')  # not found
        self.assert404('account_change_password')  # not found
        self.assert404('account_set_password')  # not found
        self.assert404('account_inactive')  # not found
        self.assert404('account_email')  # not found
        self.assert404('account_email_verification_sent')  # not found
        self.assert404('account_confirm_email', kwargs={'key': '123'})  # not found
        self.assert404('account_reset_password')  # not found
        self.assert404('account_reset_password_done')  # not found
        self.assert404('account_reset_password_from_key', kwargs={'uidb36': '123', 'key': '123'})  # not found
        self.assert404('account_reset_password_from_key_done')  # not found

    def test_non_public_tenant(self):
        """
        Overriden (decorated) `allauth` view should be accessible for non-public tenant schemas only,
        ie. return anything except 404 (not found) for non-public tenant.
        """
        self.assert200('account_signup')  # ok
        self.assert200('account_login')  # ok
        self.assert302('account_logout')  # redirect
        self.assert302('account_change_password')  # login required
        self.assert302('account_set_password')  # login required
        self.assert200('account_inactive')  # ok
        self.assert302('account_email')  # login required
        self.assert200('account_email_verification_sent')  # ok
        self.assert200('account_confirm_email', kwargs={'key': '123'})  # ok
        self.assert200('account_reset_password')  # ok
        self.assert200('account_reset_password_done')  # ok
        self.assert200('account_reset_password_from_key', kwargs={'uidb36': '123', 'key': '123'})  # ok
        self.assert200('account_reset_password_from_key_done')  # ok


class ResetPasswordViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)

        self.test_email = 'test_email@bytedeck.com'
        self.test_password = 'password'
        self.test_student1 = User.objects.create_user('test_student', email=self.test_email, password=self.test_password)

    def test_user_cannot_request_password_reset(self):
        """ User should not be able to request password reset if they registered without an email """
        data = {
            'email': 'nonexistentemail@gmail.com'
        }
        response = self.client.post(reverse('account_reset_password'), data=data)
        self.assertContains(response, 'error_1_id_email')  # invalid with error message
        self.assertContains(response, 'This e-mail address is not assigned')

    def test_email_sent_to_requesting_user(self):
        """ Email should be sent to the requesting user containing the password verification link """
        data = {
            'email': self.test_email
        }
        response = self.client.post(reverse('account_reset_password'), data=data)
        self.assertRedirects(
            response=response,
            expected_url=reverse('account_reset_password_done'),
        )

        # There should be one item in the outbox
        self.assertEqual(len(mail.outbox), 1)
        sent_mail = mail.outbox[0]

        # Email sent should be equal to the email used for resetting
        self.assertEqual(sent_mail.to[0], self.test_email)

        # Extract password reset link
        password_reset_link = re.search(r'(?P<url>https?://[^\s]+)', sent_mail.body).group('url')
        response = self.client.get(password_reset_link, follow=True)
        self.assertEqual(response.status_code, 200)

        # User should be able to change password
        new_password = 'newpassword'
        new_password_again = 'newpassword'
        data = {
            'password1': new_password,
            'password2': new_password_again
        }

        # Get the form action url from the previous response where we can send a post
        # request to change the user's password
        action_url = response.context_data.get('action_url')
        response = self.client.post(action_url, data=data)
        self.assertRedirects(response, reverse('account_login'))

        # After changing the password student should be able to login using the new password
        success = self.client.login(username=self.test_student1.username, password=new_password)
        self.assertTrue(success)
