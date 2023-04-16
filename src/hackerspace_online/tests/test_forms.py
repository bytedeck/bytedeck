from allauth.account.adapter import get_adapter
from django.conf import settings
from django.core import mail
from django.test.utils import override_settings
from datetime import timedelta
from unittest.mock import patch
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialLogin
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.shortcuts import reverse
from django.utils import timezone
from hackerspace_online.tests.utils import generate_form_data
from profile_manager.forms import ProfileForm
from profile_manager.models import email_confirmed_handler

from siteconfig.models import SiteConfig

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name, schema_context

from hackerspace_online.forms import CustomSignupForm, CustomSocialAccountSignupForm, PublicContactForm, CustomLoginForm

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

    def test_sign_up_via_post_with_email(self):

        self.client = TenantClient(self.tenant)
        form_data = {
            'email': 'email@example.com',
            'username': "username",
            'first_name': "firsttest",
            'last_name': "Lasttest",
            'access_code': "314159",
            'password1': "password",
            'password2': "password"
        }

        with patch("django.contrib.messages.add_message") as mock_add_message:
            response = self.client.post(reverse('account_signup'), form_data, follow=True,)
            self.assertEqual(mock_add_message.call_count, 2)
            confirmation_email_sent_msg = mock_add_message.call_args_list[0][0][2]
            successfully_signed_in_msg = mock_add_message.call_args_list[1][0][2]

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(confirmation_email_sent_msg, f'Confirmation e-mail sent to {form_data["email"]}.')
        self.assertEqual(successfully_signed_in_msg, f'Successfully signed in as {form_data["username"]}.')

        self.assertRedirects(response, reverse('quests:quests'))
        user = User.objects.get(username="username")
        self.assertEqual(user.first_name, "firsttest")

        # Signals don't seem to populate the request attribute during tests.. but it actually gets called
        # self.assertTrue(getattr(response.wsgi_request, 'recently_signed_up_with_email', None))


class CustomSocialAccountSignUpFormTest(TenantTestCase):

    def setUp(self):
        pass

    def get_social_login(self):
        extra_data = {
            "email": "user@example.com",
        }
        return SocialLogin(
            user=User(email="user@example.com", first_name="firsttest", last_name="lasttest"),
            account=SocialAccount(provider="google", extra_data=extra_data),
            email_addresses=[
                EmailAddress(
                    email="user@example.com",
                    verified=True,
                    primary=True
                ),
            ]
        )

    def setup_social_app(self):
        with schema_context(get_public_schema_name()):
            app = SocialApp.objects.create(
                provider='google',
                name='Test Google App',
                client_id='test_client_id',
                secret='test_secret',
            )
            app.sites.add(Site.objects.get_current())

        config = SiteConfig.get()
        config._propagate_google_provider()

    def test_init(self):
        CustomSocialAccountSignupForm(sociallogin=self.get_social_login())

    def test_complete_fields(self):
        """
        Test in case there are changes from CustomSignupForm
        """
        form = CustomSocialAccountSignupForm(sociallogin=self.get_social_login())

        social_signup_form_fields = [
            'first_name',
            'last_name',
            'access_code',
            'username',
            'email',
        ]

        self.assertEqual(len(form.fields), len(social_signup_form_fields))
        self.assertListEqual(sorted(social_signup_form_fields), sorted(form.fields.keys()))

    def test_valid_data(self):
        form = CustomSocialAccountSignupForm(
            sociallogin=self.get_social_login(),
            data={
                'username': 'sample.username',
                'access_code': '314159',
            }
        )

        form.data = {**form.initial, **form.data}

        self.assertTrue(form.is_valid())

    def test_bad_access_codecoverage(self):
        """ Test that a social sign up form with the wrong access code doesn't validate """
        form = CustomSocialAccountSignupForm(
            sociallogin=self.get_social_login(),
            data={
                'username': "username",
                'access_code': "wrongcode",
            }
        )
        form.data = {**form.initial, **form.data}

        self.assertFalse(form.is_valid())

        with self.assertRaisesMessage(forms.ValidationError, "Access code unrecognized."):
            form.clean()

    def test_sign_up_via_post(self):
        self.client = TenantClient(self.tenant)
        session = self.client.session
        form_data = {
            'username': "username",
            'access_code': "314159",
        }

        # Fake the session object to have the `socialaccount_sociallogin` since that's what it looks for
        # when a user chooses a google account to sign up
        sociallogin = self.get_social_login()
        session["socialaccount_sociallogin"] = sociallogin.serialize()
        session.save()

        # email should be pre-populated
        resp = self.client.get(reverse("socialaccount_signup"))
        form = resp.context["form"]

        self.assertEqual(form["email"].value(), "user@example.com")

        form_data = {**form.initial, **form_data}
        response = self.client.post(reverse('socialaccount_signup'), data=form_data, follow=True)

        self.assertRedirects(response, reverse('quests:quests'))

        user = User.objects.get(username="username")
        self.assertEqual(user.first_name, "firsttest")

    @patch('allauth.socialaccount.providers.oauth2.client.OAuth2Client.get_access_token')
    @patch('allauth.socialaccount.providers.google.views.GoogleOAuth2Adapter.complete_login')
    @patch('allauth.socialaccount.models.SocialLogin.verify_and_unstash_state')
    def test_signin_via_post_connect_existing_account_automatically(
        self,
        mock_verify_and_unstash_state,
        mock_complete_login,
        mock_get_access_token
    ):
        """
        When a user tries to login via OAuth and the email they used in an OAuth signin matches their current email
        but that email is verified, automatically merge their social account with their local account
        """

        test_student = User.objects.create_user(
            username='test_student',
            password="password",
            email='test_student@example.com',
        )
        # Add a verified email to the student
        test_student.emailaddress_set.create(
            email=test_student.email,
            verified=True,
        )

        self.setup_social_app()
        self.client = TenantClient(self.tenant)

        social_login = self.get_social_login()
        social_login.user.email = test_student.email
        social_login.email_addresses[0].email = test_student.email

        mock_get_access_token.return_value = {
            'access_token': 'test_access_token',
            'expires_in': 3599,
            'scope': 'openid https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email',
            'token_type': 'Bearer',
            'id_token': 'test_id_token'
        }
        mock_complete_login.return_value = social_login
        mock_verify_and_unstash_state.return_value = {'process': 'login', 'scope': '', 'auth_params': ''}

        # Simulate a student clicking the Google Sign in button
        url = reverse('google_login')
        response = self.client.post(url)

        # Check that they get redirected to the google accounts sign in page
        authorize_url = response.headers['Location']
        self.assertIn('accounts.google.com', authorize_url)
        self.assertIn('response_type=code', authorize_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('client_id=test_client_id', authorize_url)

        # There should be no SocialAccount associated to a student at this point
        self.assertFalse(SocialAccount.objects.filter(user=test_student, provider='google').exists())

        # Simulate a student entering the correct details or choosing a google account to sign in with
        response = self.client.get(reverse('google_callback'), data={'code': 'testcode', 'state': 'randomstate'}, follow=True)
        self.assertRedirects(response, reverse('quests:quests'))

        mock_get_access_token.assert_called_once()
        mock_complete_login.assert_called_once()

        # Since there is a match with Google email used during login, that account should now be
        # associated to that student who logged in
        self.assertTrue(SocialAccount.objects.filter(user=test_student, provider='google').exists())

    @patch('allauth.socialaccount.providers.oauth2.client.OAuth2Client.get_access_token')
    @patch('allauth.socialaccount.providers.google.views.GoogleOAuth2Adapter.complete_login')
    @patch('allauth.socialaccount.models.SocialLogin.verify_and_unstash_state')
    def test_signin_via_post_connect_existing_account_manually__merge_yes(
        self,
        mock_verify_and_unstash_state,
        mock_complete_login,
        mock_get_access_token
    ):
        """
        When a user tries to login via OAuth and the email they used in an OAuth signin matches their current email
        but that email is not verified, the user gets redirected to the Oauth merge page, clicks yes and then it will
        merge their social account with their local account
        """

        test_student = User.objects.create_user(
            username='test_student',
            password="password",
            email='test_student@example.com',
        )

        self.setup_social_app()
        self.client = TenantClient(self.tenant)

        social_login = self.get_social_login()
        social_login.user.email = test_student.email
        social_login.email_addresses[0].email = test_student.email

        mock_get_access_token.return_value = {
            'access_token': 'test_access_token',
            'expires_in': 3599,
            'scope': 'openid https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email',
            'token_type': 'Bearer',
            'id_token': 'test_id_token'
        }
        mock_complete_login.return_value = social_login
        mock_verify_and_unstash_state.return_value = {'process': 'login', 'scope': '', 'auth_params': ''}

        # Simulate a student clicking the Google Sign in button
        url = reverse('google_login')
        response = self.client.post(url)

        # Check that they get redirected to the google accounts sign in page
        authorize_url = response.headers['Location']
        self.assertIn('accounts.google.com', authorize_url)
        self.assertIn('response_type=code', authorize_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('client_id=test_client_id', authorize_url)

        # There should be no SocialAccount associated to a student at this point
        self.assertFalse(SocialAccount.objects.filter(user=test_student, provider='google').exists())

        # Simulate a student entering the correct details or choosing a google account to sign in with
        response = self.client.get(reverse('google_callback'), data={'code': 'testcode', 'state': 'randomstate'}, follow=True)

        # Since there is no verified email but User.email is the same with the Social Login email they used
        # then they should be redirected to the oauth account merge page
        self.assertRedirects(response, reverse('profiles:oauth_merge_account'))
        self.assertIn('merge_with_user_id', response.wsgi_request.session)

        # Clicking No should redirect them to the socialaccount sign up page
        # response = self.client.post(reverse('profiles:oauth_merge_account'), data={'submit': 'no'}, follow=True)
        # test_student.refresh_from_db()
        # self.assertEqual(test_student.email, '')

        # Clicking Yes should merge the accounts and redirect them to the login page
        response = self.client.post(reverse('profiles:oauth_merge_account'), data={'submit': 'yes'}, follow=True)

        mock_get_access_token.assert_called_once()
        mock_complete_login.assert_called_once()

        # Since there is a match with Google email used during login, that account should now be
        # associated to that student who logged in
        self.assertTrue(SocialAccount.objects.filter(user=test_student, provider='google').exists())

        # test_student should now have a verified email
        test_student.refresh_from_db()
        self.assertTrue(test_student.emailaddress_set.filter(email=test_student.email, verified=True).exists())

    @patch('allauth.socialaccount.providers.oauth2.client.OAuth2Client.get_access_token')
    @patch('allauth.socialaccount.providers.google.views.GoogleOAuth2Adapter.complete_login')
    @patch('allauth.socialaccount.models.SocialLogin.verify_and_unstash_state')
    def test_signin_via_post_connect_existing_account_manually__merge_no(
        self,
        mock_verify_and_unstash_state,
        mock_complete_login,
        mock_get_access_token
    ):
        """
        When a user tries to login via OAuth and the email they used in an OAuth signin matches their current email
        but that email is not verified, the user gets redirected to the Oauth merge page, clicks No;

        They should be redirected to the signup page and the email associated with that user should be removed
        """

        test_student = User.objects.create_user(
            username='test_student',
            password="password",
            email='test_student@example.com',
        )

        self.setup_social_app()
        self.client = TenantClient(self.tenant)

        social_login = self.get_social_login()
        social_login.user.email = test_student.email
        social_login.email_addresses[0].email = test_student.email

        mock_get_access_token.return_value = {
            'access_token': 'test_access_token',
            'expires_in': 3599,
            'scope': 'openid https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email',
            'token_type': 'Bearer',
            'id_token': 'test_id_token'
        }
        mock_complete_login.return_value = social_login
        mock_verify_and_unstash_state.return_value = {'process': 'login', 'scope': '', 'auth_params': ''}

        # Simulate a student clicking the Google Sign in button
        url = reverse('google_login')
        response = self.client.post(url)

        # Check that they get redirected to the google accounts sign in page
        authorize_url = response.headers['Location']
        self.assertIn('accounts.google.com', authorize_url)
        self.assertIn('response_type=code', authorize_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('client_id=test_client_id', authorize_url)

        # There should be no SocialAccount associated to a student at this point
        self.assertFalse(SocialAccount.objects.filter(user=test_student, provider='google').exists())

        # Simulate a student entering the correct details or choosing a google account to sign in with
        response = self.client.get(reverse('google_callback'), data={'code': 'testcode', 'state': 'randomstate'}, follow=True)

        # Since there is no verified email but User.email is the same with the Social Login email they used
        # then they should be redirected to the oauth account merge page
        self.assertRedirects(response, reverse('profiles:oauth_merge_account'))
        self.assertIn('merge_with_user_id', response.wsgi_request.session)

        # Clicking No should redirect them to the socialaccount sign up page
        response = self.client.post(reverse('profiles:oauth_merge_account'), data={'submit': 'no'}, follow=True)

        # The email should not be assosicated with that user anymore
        test_student.refresh_from_db()
        self.assertEqual(test_student.email, '')

        mock_get_access_token.assert_called_once()
        mock_complete_login.assert_called_once()

        response_form = response.context['form'].initial

        # Perform the signup process as a different user
        form_data = {
            **response_form,
            'username': 'new_student',
            'access_code': '314159',
        }
        response = self.client.post(reverse('socialaccount_signup'), data=form_data, follow=True)
        self.assertRedirects(response, reverse('quests:quests'))

        registered_student = User.objects.get(username='new_student')

        self.assertNotEqual(registered_student, test_student)

        # No account should be created for the test_student because we just registered for a new account
        self.assertFalse(SocialAccount.objects.filter(user=test_student, provider='google').exists())

        # There should now be a social account under the newly registered user
        self.assertTrue(SocialAccount.objects.filter(user=registered_student, provider='google').exists())

    @patch('allauth.socialaccount.providers.oauth2.client.OAuth2Client.get_access_token')
    @patch('allauth.socialaccount.providers.google.views.GoogleOAuth2Adapter.complete_login')
    @patch('allauth.socialaccount.models.SocialLogin.verify_and_unstash_state')
    def test_signin_via_post_google_signin_redirects_to_signup_page_on_new_account(
        self,
        mock_verify_and_unstash_state,
        mock_complete_login,
        mock_get_access_token
    ):
        """
        When a student tries to login via OAuth and they have not yet created an account in ByteDeck,
        they should simple be redirected to the signup page
        """

        self.setup_social_app()
        self.client = TenantClient(self.tenant)

        social_email = "user@example.com"
        social_login = self.get_social_login()
        social_login.user.email = social_email
        social_login.email_addresses[0].email = social_email

        mock_get_access_token.return_value = {
            'access_token': 'test_access_token',
            'expires_in': 3599,
            'scope': 'openid https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email',
            'token_type': 'Bearer',
            'id_token': 'test_id_token'
        }
        mock_complete_login.return_value = social_login
        mock_verify_and_unstash_state.return_value = {'process': 'login', 'scope': '', 'auth_params': ''}

        # Simulate a student clicking the Google Sign in button
        url = reverse('google_login')
        response = self.client.post(url)

        # Check that they get redirected to the google accounts sign in page
        authorize_url = response.headers['Location']
        self.assertIn('accounts.google.com', authorize_url)
        self.assertIn('response_type=code', authorize_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('client_id=test_client_id', authorize_url)

        # Simulate a student entering the correct details or choosing a google account to sign in with
        response = self.client.get(reverse('google_callback'), data={'code': 'testcode', 'state': 'randomstate'}, follow=True)

        # Student should now be redirected to the social sign up page
        self.assertRedirects(response, reverse('socialaccount_signup'))
        mock_get_access_token.assert_called_once()
        mock_complete_login.assert_called_once()

    @patch('allauth.socialaccount.providers.oauth2.client.OAuth2Client.get_access_token')
    @patch('allauth.socialaccount.providers.google.views.GoogleOAuth2Adapter.complete_login')
    @patch('allauth.socialaccount.models.SocialLogin.verify_and_unstash_state')
    def test_signup_via_post_google_signin_change_email_and_revert_back_to_google_email(
        self,
        mock_verify_and_unstash_state,
        mock_complete_login,
        mock_get_access_token
    ):
        """
        When a student performs a signup via google, completes the signup process, and then changes their email and verifies

        When a student performs a signup via google and does the following:
            - Completes the signup process
            - Changes their email address
            - Verifies the new email address
            - Reverts back to the email they used via google login

        They should not be required to verify their email address and a confirmation email should not be sent
        """

        self.setup_social_app()
        self.client = TenantClient(self.tenant)

        social_email = "user@example.com"
        social_login = self.get_social_login()
        social_login.user.email = social_email
        social_login.email_addresses[0].email = social_email

        mock_get_access_token.return_value = {
            'access_token': 'test_access_token',
            'expires_in': 3599,
            'scope': 'openid https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email',
            'token_type': 'Bearer',
            'id_token': 'test_id_token'
        }
        mock_complete_login.return_value = social_login
        mock_verify_and_unstash_state.return_value = {'process': 'login', 'scope': '', 'auth_params': ''}

        # Simulate a student clicking the Google Sign in button
        url = reverse('google_login')
        response = self.client.post(url)

        # Simulate a student entering the correct details or choosing a google account to sign in with
        response = self.client.get(reverse('google_callback'), data={'code': 'testcode', 'state': 'randomstate'}, follow=True)

        # Student should now be redirected to the social sign up page
        self.assertRedirects(response, reverse('socialaccount_signup'))
        mock_get_access_token.assert_called_once()
        mock_complete_login.assert_called_once()

        response_form = response.context['form'].initial

        # Student completes the signup process
        form_data = {
            **response_form,
            'username': 'newusername',
            'access_code': '314159',
        }
        response = self.client.post(reverse('socialaccount_signup'), data=form_data, follow=True)

        # User should now be registered
        user = User.objects.get(username=form_data["username"])
        self.assertIsNotNone(user)

        self.assertTrue(user.socialaccount_set.exists())

        # Change email and then verify
        form_data = generate_form_data(model_form=ProfileForm, grad_year=timezone.now().date().year + 2)
        old_email = user.email
        new_email = "my_new_email@example.com"
        form_data.update({
            "email": new_email,
        })
        self.assertEqual(len(mail.outbox), 0)
        self.client.post(reverse("profiles:profile_update", args=[user.profile.pk]), data=form_data)
        self.assertEqual(len(mail.outbox), 1)  # email should be sent

        user.refresh_from_db()

        self.assertEqual(user.email, new_email)
        email_address_obj = user.emailaddress_set.get(email=new_email)

        # Manually verify email
        get_adapter(response.wsgi_request).confirm_email(response.wsgi_request, email_address_obj)
        email_confirmed_handler(email_address=email_address_obj)

        email_address_obj.refresh_from_db()

        self.assertTrue(email_address_obj.verified)
        self.assertTrue(email_address_obj.primary)

        # There should be now 1 primary and 2 verified
        self.assertEqual(user.emailaddress_set.filter(primary=True).count(), 1)
        self.assertEqual(user.emailaddress_set.filter(verified=True).count(), 2)

        mail.outbox.clear()

        # Revert back to old email
        form_data.update({
            "email": old_email
        })
        self.client.post(reverse("profiles:profile_update", args=[user.profile.pk]), data=form_data)

        # There should be no emails sent at this point since emails are only sent if the email address is not verified
        self.assertEqual(len(mail.outbox), 0)

        user.refresh_from_db()
        self.assertEqual(user.email, old_email)

        # Email should still be verified
        primary_email_obj = EmailAddress.objects.get_primary(user)
        self.assertTrue(primary_email_obj.verified)
        self.assertTrue(primary_email_obj.primary)


class CustomLoginFormTest(TenantTestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testuser')

    def test_init(self):
        CustomLoginForm()

    def test_valid_data(self):

        # django-allauth forms require `request` to be passed when instantiating the form
        # normally, forms are used from within a django view and the view passes the request object to the form
        # but in this case, we are just performing a test to the form itself so we need to have access to
        # a WSGIRqeuest object, hence a small http call is performed
        # See issue: https://github.com/pennersr/django-allauth/issues/3002
        client = TenantClient(self.tenant)
        wsgi_request = client.get(reverse('account_login')).wsgi_request

        form = CustomLoginForm(
            {
                'login': 'testuser',
                'password': 'testuser',
            },
            request=wsgi_request,
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
