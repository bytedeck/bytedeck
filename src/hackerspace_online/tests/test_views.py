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
        """Use a tenant-aware client for each test."""
        # Every test needs access to the request factory.
        # https://docs.djangoproject.com/en/3.0/topics/testing/advanced/#the-request-factory
        # self.factory = RequestFactory()
        self.client = TenantClient(self.tenant)

    def test_secret_view__returns_200(self):
        """The 'simple' secret view responds with 200."""
        self.assert200('simple')

    def test_home_view__staff_redirected_to_approvals(self):
        """A logged-in staff user hitting home is redirected to the approvals page."""
        staff_user = User.objects.create_user(username="test_staff_user", password="password", is_staff=True)
        self.client.force_login(staff_user)
        response = self.client.get(reverse('home'))
        self.assertRedirects(
            response,
            reverse('quests:approvals')
        )

    def test_home_view__authenticated_redirected_to_quests(self):
        """A logged-in student hitting home is redirected to the quests page."""
        user = User.objects.create_user(username="test_user", password="password")
        self.client.force_login(user)
        self.assertRedirectsQuests('home')

    def test_home_view__anonymous_redirected_to_login(self):
        """An anonymous visitor hitting home is redirected to the login page."""
        response = self.client.get(reverse('home'))
        self.assertRedirects(
            response,
            reverse('account_login')
        )

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_home_view__public_tenant_redirects_to_flatpage(self, mock_connection1, mock_connection2):
        """Home view for public tenant should permanent redirect (301) to the public flatpage called 'home'
        """
        self.assertRedirects(
            response=self.client.get(reverse('home')),
            status_code=301,
            target_status_code=404,  # the flatpage doesn't actually exist at this point in the test, but its creation is tested elsewhere
            expected_url='/pages/home'
        )

    # Contact Form removed

    def test_favicon__redirects_to_site_favicon(self):
        """ Requests for /favicon.ico made by browsers is redirected to the site's favicon """
        response = self.client.get('/favicon.ico')
        self.assertEqual(response.status_code, 301)  # permanent redirect
        self.assertEqual(response.url, SiteConfig.get().get_favicon_url())

    @patch('hackerspace_online.views.connection', schema_name=get_public_schema_name())
    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_favicon__public_tenant_redirects_to_static_favicon(self, mock_connection1, mock_connection2):
        """ Requests for /favicon.ico made by browsers is redirected to the site's favicon """
        response = self.client.get('/favicon.ico')
        self.assertEqual(response.status_code, 301)  # permanent redirect
        self.assertEqual(response.url, static('icon/favicon.ico'))

    def test_achievements__redirect_to_badges_views(self):
        """Legacy /achievements/ URLs redirect to their corresponding badges views."""
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
        """Use a tenant-aware client for each test."""
        self.client = TenantClient(self.tenant)

    def test_enable_google_signin__False_hides_button(self):
        """
        Test to verify that Google sign in button is not showing in the page when it is disabled
        """

        response = self.client.get(reverse('account_login'))
        self.assertNotIn("btn_google_signin_dark_normal_web", response.content.decode('utf-8'))

        response = self.client.get(reverse('account_signup'))
        self.assertNotIn("btn_google_signin_dark_normal_web", response.content.decode('utf-8'))

    def test_enable_google_signin__True_shows_button(self):
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
