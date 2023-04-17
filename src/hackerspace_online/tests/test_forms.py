from django.conf import settings
from django.test.utils import override_settings
from datetime import timedelta
from django import forms
from django.contrib.auth import get_user_model
from django.shortcuts import reverse

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from hackerspace_online.forms import CustomSignupForm, PublicContactForm, CustomLoginForm

User = get_user_model()


class CustomSignUpFormTest(TenantTestCase):

    def setUp(self):
        pass

    def test_init(self):
        CustomSignupForm()

    def test_valid_data(self):
        form = CustomSignupForm(
            {
                'username': "username",
                'first_name': "firsttest",
                'last_name': "Lasttest",
                'access_code': "314159",
                'password1': "password",
                'password2': "password"
            }
        )
        self.assertTrue(form.is_valid())

    def test_bad_access_codecoverage(self):
        """ Test that a sign up form with the wrong access code doesn't validate """
        form = CustomSignupForm(
            {
                'username': "username",
                'first_name': "firsttest",
                'last_name': "Lasttest",
                'access_code': "wrongcode",
                'password1': "password",
                'password2': "password"
            }
        )
        self.assertFalse(form.is_valid())

        with self.assertRaisesMessage(forms.ValidationError, "Access code unrecognized."):
            form.clean()

    def test_sign_up_via_post(self):
        self.client = TenantClient(self.tenant)
        form_data = {
            'username': "username",
            'first_name': "firsttest",
            'last_name': "Lasttest",
            'access_code': "314159",
            'password1': "password",
            'password2': "password"
        }
        response = self.client.post(reverse('account_signup'), form_data, follow=True,)
        self.assertRedirects(response, reverse('quests:quests'))
        user = User.objects.get(username="username")
        self.assertEqual(user.first_name, "firsttest")

    def test_sign_up_via_post_upcase_username(self):
        self.client = TenantClient(self.tenant)
        form_data = {
            'username': "TestUser",
            'first_name': "firsttest",
            'last_name': "Lasttest",
            'access_code': "314159",
            'password1': "password",
            'password2': "password"
        }
        response = self.client.post(reverse('account_signup'), form_data, follow=True,)
        self.assertRedirects(response, reverse('quests:quests'))

        with self.assertRaises(User.DoesNotExist):
            User.objects.get(username=form_data['username'])

        user = User.objects.get(username=form_data['username'].lower())

        self.assertIsNotNone(user)


class CustomLoginFormTest(TenantTestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testuser')

    def test_init(self):
        CustomLoginForm()

    def test_valid_data(self):
        form = CustomLoginForm(
            {
                'login': 'testuser',
                'password': 'testuser',
            }
        )
        self.assertTrue(form.is_valid())

    def test_login_with_upcase_username(self):
        """
        User should still be able to login regardless of the username case
        """
        self.client = TenantClient(self.tenant)
        form_data = {
            'login': 'TestUser',
            'password': 'testuser'
        }
        response = self.client.post(reverse('account_login'), form_data, follow=True)
        self.assertRedirects(response, reverse('quests:quests'))

    @override_settings(SESSION_COOKIE_AGE=60 * 60 * 24)
    def test_session_expires_based_on_SESSION_COOKIE_AGE(self):
        """
        Test that whatever the value of SESSION_COOKIE_AGE expires correctly
        """

        self.client = TenantClient(self.tenant)
        form_data = {
            'login': 'TestUser',
            'password': 'testuser'
        }

        response = self.client.post(reverse('account_login'), form_data, follow=True)
        self.assertRedirects(response, reverse('quests:quests'))

        session = response.wsgi_request.session
        self.user.refresh_from_db()

        # NOTE: We are only testing the date here since there are some discrepancies on when the a the session object is created
        # probably after a couple of seconds after the `last_login` is set
        self.assertEqual((self.user.last_login + timedelta(seconds=settings.SESSION_COOKIE_AGE)).date(), session.get_expiry_date().date())

    def test_remember_me_session_expires_on_browser_close(self):
        """
        Test to see that disabling `Remember me` expires on browser close
        """

        self.client = TenantClient(self.tenant)
        form_data = {
            'login': 'TestUser',
            'password': 'testuser'
        }

        response = self.client.post(reverse('account_login'), form_data, follow=True)
        self.assertRedirects(response, reverse('quests:quests'))
        session = response.wsgi_request.session
        self.assertTrue(session.get_expire_at_browser_close())

    def test_remember_me_session_does_not_expire_on_browser_close(self):
        """
        Test to see that enabling `Remember me` does not expire immediately even when the browser is closed
        """

        self.client = TenantClient(self.tenant)
        form_data = {
            'login': 'TestUser',
            'password': 'testuser',
            'remember': True
        }

        response = self.client.post(reverse('account_login'), form_data, follow=True)
        self.assertRedirects(response, reverse('quests:quests'))
        session = response.wsgi_request.session
        self.assertFalse(session.get_expire_at_browser_close())

    def tearDown(self) -> None:
        self.user.delete()


class PublicContactFormTest(TenantTestCase):

    def setUp(self):
        pass

    def test_init(self):
        PublicContactForm()

    def test_valid_data(self):
        form = PublicContactForm(
            data={
                'name': 'First Last',
                'email': 'test@example.com',
                'message': 'Test Message',
                'g-recaptcha-response': 'PASSED',
            }
        )
        self.assertTrue(form.is_valid())
