from django.contrib.auth import get_user_model
# from django.core import mail
from django.shortcuts import reverse
from django.templatetags.static import static

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name
from unittest.mock import patch

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
        """Home view for public tenant should permanent redirect (301) to the public flatpage called 'home'
        """
        self.assertRedirects(
            response=self.client.get(reverse('home')),
            status_code=301,
            target_status_code=404,  # the flatpage doesn't actually exist at this point in the test, but its creation is tested elsewhere
            expected_url='/pages/home'
        )

    # Contact Form removed
    # @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    # @patch('tenant.views.connection', schema_name=get_public_schema_name())
    # def test_home_public_contact_form(self, mock_connection1, mock_connection2):
    #     form_data = {
    #         'name': 'First Last',
    #         'email': 'test@example.com',
    #         'message': 'Test Message',
    #         'g-recaptcha-response': 'PASSED',
    #     }
    #     response = self.client.post(reverse('home'), data=form_data)
    #     # Form submission redirects to same home page
    #     self.assertEqual(response.status_code, 302)
    #     self.assertEqual(response.url, reverse('home'))
    #     # The view should be sent via email with form info if successfull
    #     self.assertEqual(len(mail.outbox), 1)

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

    def test_achievements_redirect_to_badges_views(self):
        # log in a teacher
        staff_user = User.objects.create_user(username="test_staff_user", password="password", is_staff=True)
        self.client.force_login(staff_user)

        # assert (most) relevant badge views are redirected to from old urls
        self.assertRedirects(self.client.get('/achievements/'), reverse('badges:list'))
        self.assertRedirects(self.client.get('/achievements/create/'), reverse('badges:badge_create'))
        self.assertRedirects(self.client.get('/achievements/1'), reverse('badges:badge_detail', args=[1]))
        self.assertRedirects(self.client.get('/achievements/1/edit/'), reverse('badges:badge_update', args=[1]))
        self.assertRedirects(self.client.get('/achievements/1/delete/'), reverse('badges:badge_delete', args=[1]))


class AccountOverridenVewsTest(ViewTestUtilsMixin, TenantTestCase):
    """Misc. tests for overriden (decorated) `allauth` views"""

    def setUp(self):
        # Every test needs access to the request factory.
        # https://docs.djangoproject.com/en/3.0/topics/testing/advanced/#the-request-factory
        # self.factory = RequestFactory()
        self.client = TenantClient(self.tenant)

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_sigunp_public_tenant(self, mock_connection1, mock_connection2):
        """
        Overriden (decorated) `account_signup` view should be non-public,
        ie. return 404 (not found) for general public.
        """
        self.assert404('account_signup')  # not found

    def test_signup_non_public_tenant(self):
        """
        Overriden (decorated) `account_signup` view should be non-public,
        ie. return 200 (ok) for non-public tenant.
        """
        self.assert200('account_signup')  # ok

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_login_public_tenant(self, mock_connection1, mock_connection2):
        """
        Overriden (decorated) `account_login` view should be non-public,
        ie. return 404 (not found) for general public.
        """
        self.assert404('account_login')  # not found

    def test_login_non_public_tenant(self):
        """
        Overriden (decorated) `account_login` view should be non-public,
        ie. return 200 (ok) for non-public tenant.
        """
        self.assert200('account_login')  # ok

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_logout_public_tenant(self, mock_connection1, mock_connection2):
        """
        Overriden (decorated) `account_logout` view should be non-public,
        ie. return 404 (not found) for general public.
        """
        self.assert404('account_logout')  # not found

    def test_logout_non_public_tenant(self):
        """
        Overriden (decorated) `account_logout` view should be non-public,
        ie. return 302 (redirect) for non-public tenant.
        """
        self.assert302('account_logout')  # redirect

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_change_password_public_tenant(self, mock_connection1, mock_connection2):
        """
        Overriden (decorated) `account_change_password` view should be non-public,
        ie. return 404 (not found) for general public.
        """
        self.assert404('account_change_password')  # not found

    def test_change_password_non_public_tenant(self):
        """
        Overriden (decorated) `account_change_password` view should be non-public,
        ie. return 302 (login required) for non-public tenant.
        """
        self.assert302('account_change_password')  # login required

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_set_password_public_tenant(self, mock_connection1, mock_connection2):
        """
        Overriden (decorated) `account_set_password` view should be non-public,
        ie. return 404 (not found) for general public.
        """
        self.assert404('account_set_password')  # not found

    def test_set_password_non_public_tenant(self):
        """
        Overriden (decorated) `account_set_password` view should be non-public,
        ie. return 302 (login required) for non-public tenant.
        """
        self.assert302('account_set_password')  # login required

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_inactive_public_tenant(self, mock_connection1, mock_connection2):
        """
        Overriden (decorated) `account_inactive` view should be non-public,
        ie. return 404 (not found) for general public.
        """
        self.assert404('account_inactive')  # not found

    def test_inactive_non_public_tenant(self):
        """
        Overriden (decorated) `account_inactive` view should be non-public,
        ie. return 200 (ok) for non-public tenant.
        """
        self.assert200('account_inactive')  # ok

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_email_public_tenant(self, mock_connection1, mock_connection2):
        """
        Overriden (decorated) `account_email` view should be non-public,
        ie. return 404 (not found) for general public.
        """
        self.assert404('account_email')  # not found

    def test_email_non_public_tenant(self):
        """
        Overriden (decorated) `account_email` view should be non-public,
        ie. return 302 (login required) for non-public tenant.
        """
        self.assert302('account_email')  # login required

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_email_verification_sent_public_tenant(self, mock_connection1, mock_connection2):
        """
        Overriden (decorated) `account_email_verification_sent` view should be non-public,
        ie. return 404 (not found) for general public.
        """
        self.assert404('account_email_verification_sent')  # not found

    def test_email_verification_sent_non_public_tenant(self):
        """
        Overriden (decorated) `account_email_verification_sent` view should be non-public,
        ie. return 200 (ok) for non-public tenant.
        """
        self.assert200('account_email_verification_sent')  # ok

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_confirm_email_public_tenant(self, mock_connection1, mock_connection2):
        """
        Overriden (decorated) `account_confirm_email` view should be non-public,
        ie. return 404 (not found) for general public.
        """
        self.assert404('account_confirm_email', kwargs={'key': '123'})  # not found

    def test_confirm_email_non_public_tenant(self):
        """
        Overriden (decorated) `account_confirm_email` view should be non-public,
        ie. return 200 (ok) for non-public tenant.
        """
        self.assert200('account_confirm_email', kwargs={'key': '123'})  # ok

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_reset_password_public_tenant(self, mock_connection1, mock_connection2):
        """
        Overriden (decorated) `account_reset_password` view should be non-public,
        ie. return 404 (not found) for general public.
        """
        self.assert404('account_reset_password')  # not found

    def test_reset_password_non_public_tenant(self):
        """
        Overriden (decorated) `account_reset_password` view should be non-public,
        ie. return 200 (ok) for non-public tenant.
        """
        self.assert200('account_reset_password')  # ok

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_reset_password_done_public_tenant(self, mock_connection1, mock_connection2):
        """
        Overriden (decorated) `account_reset_password_done` view should be non-public,
        ie. return 404 (not found) for general public.
        """
        self.assert404('account_reset_password_done')  # not found

    def test_reset_password_done_non_public_tenant(self):
        """
        Overriden (decorated) `account_reset_password_done` view should be non-public,
        ie. return 200 (ok) for non-public tenant.
        """
        self.assert200('account_reset_password_done')  # ok

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_reset_password_from_key_public_tenant(self, mock_connection1, mock_connection2):
        """
        Overriden (decorated) `account_reset_password_from_key` view should be non-public,
        ie. return 404 (not found) for general public.
        """
        self.assert404('account_reset_password_from_key', kwargs={'uidb36': '123', 'key': '123'})  # not found

    def test_reset_password_from_key_non_public_tenant(self):
        """
        Overriden (decorated) `account_reset_password_from_key` view should be non-public,
        ie. return 200 (ok) for non-public tenant.
        """
        self.assert200('account_reset_password_from_key', kwargs={'uidb36': '123', 'key': '123'})  # ok

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_reset_password_from_key_done_public_tenant(self, mock_connection1, mock_connection2):
        """
        Overriden (decorated) `account_reset_password_from_key_done` view should be non-public,
        ie. return 404 (not found) for general public.
        """
        self.assert404('account_reset_password_from_key_done')  # not found

    def test_reset_password_from_key_done_non_public_tenant(self):
        """
        Overriden (decorated) `account_reset_password_from_key_done` view should be non-public,
        ie. return 200 (ok) for non-public tenant.
        """
        self.assert200('account_reset_password_from_key_done')  # ok


class GoogleSigninViewTest(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)

    def test_enable_google_signin_is_False(self):
        """
        Test to verify that Google sign in button is not showing in the page when it is disabled
        """

        response = self.client.get(reverse('account_login'))
        self.assertNotIn("btn_google_signin_dark_normal_web", response.content.decode('utf-8'))

        response = self.client.get(reverse('account_signup'))
        self.assertNotIn("btn_google_signin_dark_normal_web", response.content.decode('utf-8'))

    def test_enable_google_signin_is_True(self):
        """
        Test to verify that Google sign in button is showing in the page when it is enabled
        """
        config = SiteConfig.get()
        config.enable_google_signin = True
        config.save()

        response = self.client.get(reverse('account_login'))
        self.assertIn("btn_google_signin_dark_normal_web", response.content.decode('utf-8'))

        response = self.client.get(reverse('account_signup'))
        self.assertIn("btn_google_signin_dark_normal_web", response.content.decode('utf-8'))
