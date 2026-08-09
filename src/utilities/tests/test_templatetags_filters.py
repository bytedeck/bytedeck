from django.test import SimpleTestCase, TestCase
from django.template import Template, Context

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig
from utilities.templatetags.utility_tags import checkcross, favicon_url


class CheckcrossFilterTest(SimpleTestCase):
    """Tests for the checkcross filter's non-boolean fall-through."""

    def test_checkcross__non_boolean_returns_none(self):
        """A value that is neither True nor False maps to no icon (None)."""
        self.assertIsNone(checkcross(None))


class FaviconUrlTagTest(ByteDeckTenantTestCase):
    """Tests for the favicon_url tag on a (non-public) tenant."""

    def test_favicon_url__returns_siteconfig_favicon(self):
        """On a tenant, favicon_url returns the deck's configured favicon URL."""
        self.assertEqual(favicon_url(), SiteConfig.get().get_favicon_url())


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
