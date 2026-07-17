from allauth.socialaccount.models import SocialApp
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
# from django.core import mail
from django.shortcuts import reverse
from django.templatetags.static import static

from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name, schema_context
from unittest.mock import patch

from hackerspace_online.tests.utils import ByteDeckTenantTestCase, ViewTestUtilsMixin
from siteconfig.models import SiteConfig

User = get_user_model()


class ViewsTest(ViewTestUtilsMixin, ByteDeckTenantTestCase):
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
        self.assertRedirects(self.client.get('/achievements/1/'), reverse('badges:badge_detail', args=[1]))
        self.assertRedirects(self.client.get('/achievements/1/edit/'), reverse('badges:badge_update', args=[1]))
        self.assertRedirects(self.client.get('/achievements/1/delete/'), reverse('badges:badge_delete', args=[1]))


class GoogleSigninViewTest(ViewTestUtilsMixin, ByteDeckTenantTestCase):

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
        # django-allauth 65's {% get_providers %} only lists providers that are
        # actually configured with a SocialApp, so set one up the way
        # production decks get one (public app propagated to the tenant).
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
        config.enable_google_signin = True
        config.save()

        response = self.client.get(reverse('account_login'))
        self.assertIn("btn_google_signin_dark_normal_web", response.content.decode('utf-8'))

        response = self.client.get(reverse('account_signup'))
        self.assertIn("btn_google_signin_dark_normal_web", response.content.decode('utf-8'))
