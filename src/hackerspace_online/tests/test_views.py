import re
from pathlib import Path

from allauth.socialaccount.models import SocialApp
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
# from django.core import mail
from django.contrib.messages import constants as messages_constants
from django.contrib.messages.storage.base import Message
from django.shortcuts import reverse
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.utils.html import format_html

from django_tenants.utils import get_public_schema_name, schema_context
from unittest.mock import patch

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig

User = get_user_model()


class ViewsTest(ByteDeckTenantTestCase):
    """Tests the project-level views: the home-page redirects per role, the favicon, and the secret page."""

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
    """Tests that the login page shows or hides the Google sign-in button per the siteconfig setting."""

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


def render_messages_snippet(text, level=messages_constants.WARNING, extra_tags=None):
    """Render messages-snippet.html with one real message in it.

    A real `Message` rather than a stand-in, because the snippet reads three different
    things off it (`tags` for the alert colour, `extra_tags` for the safe escape hatch,
    and `message` for the text) and a stand-in drifts out of step with that.

    Args:
        text (str): the message text, plain or already safe.
        level (int): a django.contrib.messages constant, deciding the alert colour.
        extra_tags (str | None): the message's extra tags, space separated.

    Returns:
        str: the rendered HTML.
    """
    message = Message(level, text, extra_tags=extra_tags)
    return render_to_string('messages-snippet.html', {'messages': [message]})


class MessagesSnippetIconTest(ByteDeckTenantTestCase):
    """Rendering tests pinning django messages (messages-snippet.html) icon-free:
    the level-icon request from staging live testing was scoped to the
    subscription-status banner only (#2140 review)."""

    def render_messages(self, tags):
        """Render the snippet with one message at the level named by `tags`."""
        levels = {
            'error': messages_constants.ERROR,
            'warning': messages_constants.WARNING,
            'info': messages_constants.INFO,
            'success': messages_constants.SUCCESS,
        }
        return render_messages_snippet('the message text', level=levels[tags])

    def test_messages_snippet__messages_have_no_level_icon(self):
        """Django messages render icon-free at every level: the maintainer scoped the
        icon request to the subscription-status banner only, so no fa- icon may leak
        into the shared messages snippet."""
        for tags in ('error', 'warning', 'info', 'success'):
            html = self.render_messages(tags)
            self.assertNotIn('fa-ban', html)
            self.assertNotIn('fa-exclamation-triangle', html)
            self.assertNotIn('fa-info-circle', html)


class MessagesSnippetEscapingTest(ByteDeckTenantTestCase):
    """Rendering tests pinning what messages-snippet.html treats as markup (#2498).

    Messages are escaped by default, so a name interpolated into one arrives as text.
    A message that means its markup builds it with `format_html`, and a plain string
    meant to carry markup opts in with `extra_tags='safe'`.
    """

    def test_messages_snippet__escapes_a_plain_message(self):
        """Markup in a plain string message reaches the page as text."""
        html = render_messages_snippet('Quest <script>alert(1)</script> was hidden.')

        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)

    def test_messages_snippet__renders_markup_built_with_format_html(self):
        """A message built with format_html keeps its own markup and escapes its arguments."""
        html = render_messages_snippet(
            format_html('<strong>{}</strong> was hidden.', 'Quest <script>alert(1)</script>')
        )

        self.assertIn('<strong>', html)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)

    def test_messages_snippet__safe_extra_tag_renders_a_plain_string_as_markup(self):
        """The `safe` extra tag is the deliberate escape hatch, so its markup renders."""
        html = render_messages_snippet('<a href="/verify/">Verify your email</a>', extra_tags='safe')

        self.assertIn('<a href="/verify/">Verify your email</a>', html)

    def test_messages_snippet__a_tag_merely_containing_safe_does_not_disable_escaping(self):
        """Only the exact `safe` tag opts out of escaping.

        The tags are matched as a list: `message.tags` joins every tag into one string, so
        matching a substring of it would let `extra_tags='unsafe'` (or any tag with "safe"
        inside it) silently turn escaping off for that message.
        """
        for extra_tags in ('unsafe', 'safety-notice', 'not-safe-at-all'):
            with self.subTest(extra_tags=extra_tags):
                html = render_messages_snippet('<script>alert(1)</script>', extra_tags=extra_tags)

                self.assertNotIn('<script>alert(1)</script>', html)
                self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)

    def test_messages_snippet__safe_still_works_beside_other_extra_tags(self):
        """A message can carry `safe` alongside other tags and still render its markup."""
        html = render_messages_snippet('<strong>Done</strong>', extra_tags='safe dismissible')

        self.assertIn('<strong>Done</strong>', html)

    def test_public_base__escapes_a_plain_message_too(self):
        """The public tenant shows messages from its own base template, on the same terms.

        It is a separate renderer from messages-snippet.html, so it shares the decision
        rather than repeating it: every message it shows today is a hardcoded literal, but
        an escaping default that only half the site honours is not a default (#2498).
        """
        html = render_to_string(
            'public/base.html',
            {'messages': [Message(messages_constants.WARNING, '<script>alert(1)</script>')]},
        )

        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)

    def test_public_base__renders_markup_built_with_format_html(self):
        """A safely-built message keeps its markup on the public tenant as well."""
        html = render_to_string(
            'public/base.html',
            {'messages': [Message(messages_constants.SUCCESS, format_html('<strong>{}</strong>', 'Deck created'))]},
        )

        self.assertIn('<strong>Deck created</strong>', html)

    def test_message_templates__all_render_a_message_through_the_shared_include(self):
        """No template may render a message body on its own terms.

        Both renderers include `_message_body.html`, which is what makes escape-by-default a
        default rather than a local choice. A third renderer that inlines `{{ message }}` or
        `{{ message|safe }}` would silently opt out of it, so this catches that at the source.
        """
        templates_root = Path(settings.BASE_DIR) / 'templates'
        shared_include = templates_root / '_message_body.html'
        offenders = []

        for path in Path(settings.BASE_DIR).rglob('*.html'):
            if path == shared_include:
                continue
            for number, line in enumerate(path.read_text().splitlines(), start=1):
                if re.search(r'{{\s*message(\.message)?\s*(\|[^}]*)?}}', line):
                    offenders.append(f'{path.relative_to(settings.BASE_DIR)}:{number}')

        self.assertEqual(
            offenders, [],
            'these templates render a message themselves instead of including _message_body.html: '
            + ', '.join(offenders),
        )
