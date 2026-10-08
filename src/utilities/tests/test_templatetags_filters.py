from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.template import Template, Context

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig
from utilities.templatetags.utility_tags import (
    checkcross, favicon_url, max_upload_request_size, public_email_logo_url, user_guide_url,
)


class CheckcrossFilterTest(SimpleTestCase):
    """Tests for the checkcross filter's non-boolean fall-through."""

    def test_checkcross__non_boolean_returns_none(self):
        """A value that is neither True nor False maps to no icon (None)."""
        self.assertIsNone(checkcross(None))


class FaviconUrlTagTest(ByteDeckTenantTestCase):
    """Tests for the favicon_url tag on a (non-public) tenant."""

    def test_favicon_url__returns_siteconfig_favicon(self):
        """On a tenant, favicon_url returns the deck's configured favicon URL.

        A known favicon is configured first, then the tag is asserted against that exact URL
        (computed independently of get_favicon_url) so the test can't pass on an empty fixture
        where both sides would collapse to the same default.
        """
        config = SiteConfig.get()
        config.favicon = 'favicon/known_test_favicon.png'
        config.save()  # invalidates the SiteConfig cache via invalidate_siteconfig_cache_signal
        self.assertEqual(favicon_url(), f"{settings.MEDIA_URL}favicon/known_test_favicon.png")


class MaxUploadRequestSizeTagTest(SimpleTestCase):
    """The max_upload_request_size tag hands the browser's upload size check its limit (#783)."""

    @override_settings(MAX_UPLOAD_REQUEST_SIZE=1234)
    def test_max_upload_request_size__is_the_setting(self):
        """The tag gives settings.MAX_UPLOAD_REQUEST_SIZE, so the limit can be set per deployment."""
        self.assertEqual(max_upload_request_size(), 1234)


class PossessiveFilterTest(TestCase):
    def test_add_possessive__various_name_endings(self):
        """Filter appends the correct possessive suffix for names ending in s, 's, 's, and other letters."""
        template = Template("{% load filters %}{{ name|add_possessive }}")

        # Test a name that ends with "s"
        context = Context({"name": "James"})
        output = template.render(context)
        self.assertEqual(output, "James&#x27;")

        # Test a name that ends with "'s"
        context = Context({"name": "John's"})
        output = template.render(context)
        self.assertEqual(output, "John&#x27;s")

        # Test a name that ends with "’s"
        context = Context({"name": "Andrés’s"})
        output = template.render(context)
        self.assertEqual(output, "Andrés’s")

        # Test a name that doesn't end with "s", "'s", or "’s"
        context = Context({"name": "Mary"})
        output = template.render(context)
        self.assertEqual(output, "Mary&#x27;s")


class PublicEmailLogoUrlTagTest(SimpleTestCase):
    """Tests for the platform wordmark tag used in ByteDeck's own emails."""

    def test_public_email_logo_url__returns_the_configured_wordmark(self):
        """The tag serves settings.PUBLIC_EMAIL_LOGO_URL verbatim: an absolute
        URL (mail clients cannot resolve relative static paths) read from
        settings rather than SiteConfig, so it also works on the public schema,
        which has no SiteConfig."""
        with self.settings(PUBLIC_EMAIL_LOGO_URL='https://cdn.example.com/wordmark.png'):
            self.assertEqual(public_email_logo_url(), 'https://cdn.example.com/wordmark.png')


class UserGuideUrlTagTest(SimpleTestCase):
    """Tests for the user_guide_url tag, the address the app's help links use (#2109)."""

    @override_settings(USER_GUIDE_URL='https://guide.example/')
    def test_user_guide_url__the_guide_or_one_of_its_pages(self):
        """Without a page it's the guide's home page; with one, that page within the guide."""
        self.assertEqual(user_guide_url(), 'https://guide.example/')
        self.assertEqual(user_guide_url('quests/shared-library/'), 'https://guide.example/quests/shared-library/')
