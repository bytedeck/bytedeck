from django.conf import settings
from django.core.paginator import Paginator
from django.template import Template, Context
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig
from utilities.templatetags.utility_tags import checkcross, elided_page_range, favicon_url, public_email_logo_url


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


def _page(number, num_pages, per_page=15):
    """Return page `number` of a list that fills `num_pages` pages of `per_page` rows."""
    return Paginator(range(num_pages * per_page), per_page).page(number)


class ElidedPageRangeFilterTest(SimpleTestCase):
    """The page numbers a pagination control links, for one page of a list (#2448)."""

    def test_elided_page_range__links_a_window_around_the_current_page(self):
        """Two pages either side of the current one, the first and last, and a gap marker between.

        Page 14 of 34 is the example from the issue: 7 numbers instead of 34.
        """
        gap = Paginator.ELLIPSIS
        self.assertEqual(list(elided_page_range(_page(14, 34))), [1, gap, 12, 13, 14, 15, 16, gap, 34])

    def test_elided_page_range__near_an_end_has_one_gap(self):
        """At either end of the list there is only the one gap, on the far side."""
        gap = Paginator.ELLIPSIS
        self.assertEqual(list(elided_page_range(_page(1, 34))), [1, 2, 3, gap, 34])
        self.assertEqual(list(elided_page_range(_page(34, 34))), [1, gap, 32, 33, 34])

    def test_elided_page_range__a_short_list_links_every_page(self):
        """A list short enough that a gap would hide almost nothing keeps every page."""
        self.assertEqual(list(elided_page_range(_page(3, 6))), [1, 2, 3, 4, 5, 6])


class PaginationControlsTest(SimpleTestCase):
    """The shared page links under a long list (`quest_manager/pagination_controls.html`, #2448)."""

    def render(self, page, path="/quests/approvals/?q=robot"):
        """Render the control for `page`, as a request to `path` would."""
        return render_to_string(
            "quest_manager/pagination_controls.html", {"items": page}, request=RequestFactory().get(path))

    def test_pagination_controls__links_only_the_window_and_the_ends(self):
        """Page 14 of 34 links 1, 12 to 16 and 34, marks both gaps, and nothing else in the middle."""
        html = self.render(_page(14, 34))

        for linked in (1, 12, 13, 14, 15, 16, 34):
            with self.subTest(linked=linked):
                self.assertIn(f'href="?q=robot&amp;page={linked}"', html)
        for left_out in (2, 11, 17, 33):
            with self.subTest(left_out=left_out):
                self.assertNotIn(f'>{left_out}</a>', html)
        self.assertEqual(html.count('<li class="disabled"><span>\u2026</span></li>'), 2)
        self.assertInHTML('<li class="active"><a href="?q=robot&amp;page=14">14</a></li>', html)

    def test_pagination_controls__keeps_the_ends_and_the_steps(self):
        """The first, previous, next and last links are there as before, keeping the query string."""
        html = self.render(_page(14, 34))

        self.assertInHTML('<li><a href="?q=robot&amp;page=1">&lt;&lt;</a></li>', html)
        self.assertInHTML('<li><a href="?q=robot&amp;page=13">&lt;</a></li>', html)
        self.assertInHTML('<li><a href="?q=robot&amp;page=15">&gt;</a></li>', html)
        self.assertInHTML('<li><a href="?q=robot&amp;page=34">&gt;&gt;</a></li>', html)

    def test_pagination_controls__a_single_page_has_no_control(self):
        """One page of results needs no page links at all."""
        self.assertNotIn("pagination", self.render(_page(1, 1)))
