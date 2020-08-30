import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.shortcuts import reverse

from tenant_schemas.test.cases import TenantTestCase
from tenant_schemas.test.client import TenantClient

from hackerspace_online.tests.utils import ViewTestUtilsMixin

User = get_user_model()


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
        self.assertContains(response, 'The e-mail address is not assigned to any user account. '
                                      'Please contact your teacher to have it reset.')

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
