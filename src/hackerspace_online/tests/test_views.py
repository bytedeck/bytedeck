from mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.shortcuts import reverse
from django.templatetags.static import static

from tenant_schemas.test.cases import TenantTestCase
from tenant_schemas.test.client import TenantClient
from tenant_schemas.utils import get_public_schema_name

from hackerspace_online.tests.utils import ViewTestUtilsMixin
from siteconfig.models import SiteConfig

User = get_user_model()


class ViewsTest(ViewTestUtilsMixin, TenantTestCase):
    def setUp(self):
        # Every test needs access to the request factory.
        # https://docs.djangoproject.com/en/3.0/topics/testing/advanced/#the-request-factory
        # self.factory = RequestFactory()
        self.client = TenantClient(self.tenant)

    def test_secret_view(self):
        self.assert200('simple')

    def test_home_view_staff(self):
        staff_user = User.objects.create_user(username="test_staff_user", password="password", is_staff=True)
        self.client.force_login(staff_user)
        response = self.client.get(reverse('home'))
        self.assertRedirects(
            response,
            reverse('quests:approvals')
        )

    def test_home_view_authenticated(self):
        user = User.objects.create_user(username="test_user", password="password")
        self.client.force_login(user)
        self.assertRedirectsQuests('home')

    def test_home_view_anonymous(self):
        response = self.client.get(reverse('home'))
        self.assertRedirects(
            response,
            reverse('account_login')
        )

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_home_public_tenant(self, mock_connection1, mock_connection2):
        """Home view for public tenant should render the public landing page directly"""
        self.assert200('home')

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_home_public_contact_form(self, mock_connection1, mock_connection2):
        form_data = {
            'name': 'First Last',
            'email': 'test@example.com',
            'message': 'Test Message',
            'g-recaptcha-response': 'PASSED',
        }
        response = self.client.post(reverse('home'), data=form_data)
        # Form submission redirects to same home page
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home'))
        # The view should be sent via email with form info if successfull
        self.assertEqual(len(mail.outbox), 1)

    def test_favicon(self):
        """ Requests for /favicon.ico made by browsers is redirected to the site's favicon """
        response = self.client.get('/favicon.ico')
        self.assertEqual(response.status_code, 301)  # permanent redirect
        self.assertEqual(response.url, SiteConfig.get().get_favicon_url())

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_favicon_public_tenant(self, mock_connection1, mock_connection2):
        """ Requests for /favicon.ico made by browsers is redirected to the site's favicon """
        response = self.client.get('/favicon.ico')
        self.assertEqual(response.status_code, 301)  # permanent redirect
        self.assertEqual(response.url, static('icon/favicon.ico'))

    def test_password_reset_view(self):
        self.assert200('account_reset_password')


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
        data = {
            'password1': 'samplepassword',
            'password2': 'samplepassword'
        }
        action_url = response.context_data.get('action_url')
        response = self.client.post(action_url, data=data)
        self.assertRedirects(response, reverse('account_login'))

        # After changing the password student should be able to login using the new password
        success = self.client.login(username=self.test_student1.username, password=data['password1'])
        self.assertTrue(success)
