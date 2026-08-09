from allauth.socialaccount.models import SocialApp
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
# from django.core import mail
from django.shortcuts import reverse
from django.templatetags.static import static

from django_tenants.utils import get_public_schema_name, schema_context
from unittest.mock import patch

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig

User = get_user_model()


class ViewsTest(ByteDeckTenantTestCase):
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


class GoogleSigninViewTest(ByteDeckTenantTestCase):

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


class MessagesSnippetIconTest(ByteDeckTenantTestCase):
    """Rendering tests pinning django messages (messages-snippet.html) icon-free:
    the level-icon request from staging live testing was scoped to the
    subscription-status banner only (#2140 review)."""

    class FakeMessage:
        """Stand-in for a django.contrib.messages Message: the snippet only reads
        .tags and renders str(message)."""

        def __init__(self, tags, text):
            self.tags = tags
            self.text = text

        def __str__(self):
            return self.text

    def render_messages(self, tags):
        """Render the snippet with one fake message of the given tags."""
        from django.template.loader import render_to_string
        return render_to_string('messages-snippet.html', {'messages': [self.FakeMessage(tags, 'the message text')]})

    def test_messages_snippet__messages_have_no_level_icon(self):
        """Django messages render icon-free at every level: the maintainer scoped the
        icon request to the subscription-status banner only, so no fa- icon may leak
        into the shared messages snippet."""
        for tags in ('error', 'warning', 'info', 'success'):
            html = self.render_messages(tags)
            self.assertNotIn('fa-ban', html)
            self.assertNotIn('fa-exclamation-triangle', html)
            self.assertNotIn('fa-info-circle', html)
