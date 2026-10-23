import re
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.shortcuts import reverse

from django_tenants.utils import get_public_schema_name

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

User = get_user_model()


class NonPublicOnlyAuthViewTests(ByteDeckTenantTestCase):
    """
    Custom `non_public_only_view` decorator was applied on every `allauth` views.
    """

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_public_tenant__allauth_views_return_404(self, mock_connection1, mock_connection2):
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

    def test_non_public_tenant__allauth_views_accessible(self):
        """
        Overriden (decorated) `allauth` view should be accessible for non-public tenant schemas only,
        ie. return anything except 404 (not found) for non-public tenant.
        """
        self.assert200('account_signup')  # ok
        self.assert200('account_login')  # ok
        # logging out lands on ACCOUNT_LOGOUT_REDIRECT_URL, which this project points at the login page
        self.assertRedirects(self.client.get(reverse('account_logout')), reverse(settings.LOGIN_URL))
        self.assertRedirectsLogin('account_change_password')  # login required
        self.assertRedirectsLogin('account_set_password')  # login required
        self.assert200('account_inactive')  # ok
        self.assertRedirectsLogin('account_email')  # login required
        self.assert200('account_email_verification_sent')  # ok
        self.assert200('account_confirm_email', kwargs={'key': '123'})  # ok
        self.assert200('account_reset_password')  # ok
        self.assert200('account_reset_password_done')  # ok
        self.assert200('account_reset_password_from_key', kwargs={'uidb36': '123', 'key': '123'})  # ok
        self.assert200('account_reset_password_from_key_done')  # ok


class SignOutNavbarTests(ByteDeckTenantTestCase):
    """The navbar's Sign Out control logs a user out in a single click by POSTing to
    the logout view.

    allauth logs a user out only on POST (``ACCOUNT_LOGOUT_ON_GET`` is left at its
    default ``False``), so the navbar carries a hidden POST form that a small JS
    handler submits on click. The visible link keeps its ``href`` as a no-JS
    fallback: with JS off it GETs allauth's confirmation page, whose button POSTs
    the same view. Because sign-out is a POST, it can't be triggered by a GET
    (a prefetch, an ``<img>``, or a cross-site link)."""

    def setUp(self):
        """Log in a student so the authenticated navbar (which holds Sign Out) renders."""
        self.student = User.objects.create_user(username='test_student', password='password')
        self.client.force_login(self.student)

    def test_navbar__sign_out_posts_to_logout(self):
        """The authenticated navbar renders a POST form (carrying a CSRF token) that
        targets the logout view, plus the visible link as a no-JS GET fallback."""
        logout_url = reverse('account_logout')
        response = self.client.get(reverse('quest_manager:quests'))
        self.assertEqual(response.status_code, 200)
        # A hidden POST form targets the logout view and carries a CSRF token, so one
        # click signs out and the request can't be forged by a GET.
        self.assertContains(response, f'<form method="post" action="{logout_url}" class="js-signout-form hidden">')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        # The visible link is the no-JS fallback (GET -> allauth's confirmation page).
        self.assertContains(response, f'<a href="{logout_url}" class="js-signout" role="button">Sign Out</a>')

    def test_logout__post_clears_the_session(self):
        """POSTing the logout view actually signs the user out: the auth session is
        cleared and the request redirects to the login page. This is the behavior the
        navbar's one-click sign-out (and its no-JS confirmation button) relies on."""
        self.assertIn('_auth_user_id', self.client.session)  # signed in from setUp
        response = self.client.post(reverse('account_logout'))
        self.assertRedirects(response, reverse(settings.LOGIN_URL))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout__get_does_not_sign_out(self):
        """A GET to the logout view does NOT sign the user out: it renders allauth's
        confirmation page while the auth session stays intact. This is what keeps
        sign-out from being triggered by a GET (a prefetch, an <img>, or a cross-site
        link), and is the no-JS page the navbar link degrades to."""
        response = self.client.get(reverse('account_logout'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Are you sure you want to sign out?')
        self.assertIn('_auth_user_id', self.client.session)  # still signed in


class SuspendedDeckSignupTests(ByteDeckTenantTestCase):
    """Sign-up is closed on a suspended deck (#1734 redesign): a suspended deck is
    owner-only, so brand-new accounts must not be able to register and land in a
    signed-in session."""

    def setUp(self):
        """Use a tenant-aware client and start from an unsuspended
        (far-future-trial) deck with a clean deck cache."""
        from django.core.cache import cache

        from tenant.models import Tenant
        from tenant.utils import deck_cache_key

        cache.delete(deck_cache_key(self.tenant.schema_name))
        self.set_deck = lambda **fields: (
            Tenant.objects.filter(pk=self.tenant.pk).update(**fields),
            cache.delete(deck_cache_key(self.tenant.schema_name)),
        )

    def suspend_deck(self):
        """Lapse the deck's trial far past the grace window."""
        from datetime import date

        self.set_deck(trial_end_date=date(2020, 1, 1), paid_until=None)

    def test_signup__closed_on_suspended_deck(self):
        """On a suspended deck the sign-up page renders the closed notice (with the
        owner-only explanation) instead of the form, and a POST creates no user."""
        self.suspend_deck()

        response = self.client.get(reverse('account_signup'))
        self.assertTemplateUsed(response, 'account/signup_closed.html')
        self.assertContains(response, 'Sign-up is currently closed')
        self.assertContains(response, 'only the deck owner can sign in')

        form_data = {
            'username': "sneakysignup",
            'first_name': "Sneaky",
            'last_name': "Signup",
            'access_code': "314159",
            'password1': "password",
            'password2': "password",
        }
        response = self.client.post(reverse('account_signup'), form_data)
        # the guard, not form validation, must be what blocked the valid payload:
        # the closed notice renders and no account exists
        self.assertContains(response, 'Sign-up is currently closed')
        self.assertContains(response, 'only the deck owner can sign in')
        self.assertFalse(User.objects.filter(username='sneakysignup').exists())

    def test_signup__adapter_defers_to_default_outside_deck_schemas(self):
        """Where there is no current deck (the public and shared-library schemas),
        the adapter leaves sign-up governed by the default allauth behavior."""
        from unittest.mock import patch as mock_patch

        from hackerspace_online.adapter import CustomAccountAdapter

        with mock_patch('hackerspace_online.adapter.get_current_deck', return_value=None):
            self.assertTrue(CustomAccountAdapter().is_open_for_signup(request=None))

    def test_signup__open_on_unsuspended_deck(self):
        """An unsuspended deck's sign-up page still renders the normal form."""
        response = self.client.get(reverse('account_signup'))
        self.assertTemplateUsed(response, 'account/signup.html')
        self.assertNotContains(response, 'Sign-up is currently closed')


class ResetPasswordViewTests(ByteDeckTenantTestCase):
    """Tests the password-reset request flow, including requests for unassigned email addresses."""

    @classmethod
    def setUpTestData(cls):
        """Create a student with a known email for password-reset scenarios."""
        cls.test_email = 'test_email@bytedeck.com'
        cls.test_password = 'password'
        cls.test_student1 = User.objects.create_user('test_student', email=cls.test_email, password=cls.test_password)

    def test_request_password_reset__fails_for_unassigned_email(self):
        """ User should not be able to request a password reset for an email address no account uses """
        data = {
            'email': 'nonexistentemail@gmail.com'
        }
        response = self.client.post(reverse('account_reset_password'), data=data)
        self.assertContains(response, 'error_1_id_email')  # invalid with error message
        self.assertContains(response, 'This e-mail address is not assigned')

    def test_reset_password__email_sent_to_requesting_user(self):
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
