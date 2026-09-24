"""Headless render test: at a phone's width, a page is no wider than the screen (#2750).

On screens up to 480px wide the page container's side padding drops to 7px, half Bootstrap's
15px gutter, so the Bootstrap grid inside it has to be narrowed to match: a row's negative margin
reaches out exactly as far as the padding around it. Left at Bootstrap's -15px, every row sticks
out 8px past both edges of the screen, and every page can be dragged sideways on a phone.

The pages are rendered by the app itself, through the test client, then opened in headless
Chromium with the real vendored stylesheets. Static files are served from disk and every other
request, scripts included, is refused, so the test is hermetic and measures only what the
stylesheets do. It skips cleanly unless Playwright and a Chromium build are both available, like
the other render tests (e.g. djcytoscape/tests/test_map_layout_render.py).
"""

import glob
import os
from unittest import skipUnless
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.urls import reverse

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover (Playwright is in requirements; this guards an install without it)
    HAS_PLAYWRIGHT = False

User = get_user_model()

#: An ordinary phone held upright.
PHONE_WIDTH = 375

#: Where the rendered page pretends to live, so its root-relative /static/ links resolve.
PAGE_ORIGIN = "http://deck.test"


def _find_chromium():
    """Return the path to a pre-installed Chromium/headless-shell binary, or None if there is none.

    Playwright pins an exact build directory, so rather than let it download one (disabled in this
    environment) we resolve whatever build is already on disk under PLAYWRIGHT_BROWSERS_PATH.
    """
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    for pattern in ("chromium-*/chrome-linux/chrome", "chromium_headless_shell-*/chrome-linux/headless_shell"):
        hits = sorted(glob.glob(os.path.join(root, pattern)))
        if hits:
            return hits[-1]
    return None  # pragma: no cover (only on a machine with Playwright but no browser build)


_CHROMIUM = _find_chromium() if HAS_PLAYWRIGHT else None


@skipUnless(HAS_PLAYWRIGHT and _CHROMIUM, "Playwright and a Chromium build are required")
class PhoneWidthRenderTest(ByteDeckTenantTestCase):
    """Real pages fit a phone's screen, with their content still 7px from its edges (#2750)."""

    @classmethod
    def setUpTestData(cls):
        """A student and a teacher to view the pages as."""
        cls.student = User.objects.create_user('phone_student')
        cls.teacher = User.objects.create_user('phone_teacher', is_staff=True)

    def _render(self, url, user=None):
        """Render a page through the test client, as ``user`` or signed out.

        Args:
            url (str): the page's path.
            user (User): who views it, or None for a visitor who is not signed in.

        Returns:
            str: the page's HTML.
        """
        if user:
            self.client.force_login(user)
        else:
            self.client.logout()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        return response.content.decode()

    def _measure(self, pages):
        """Open each rendered page at a phone's width and measure it.

        Playwright's event loop is started here, after every page has been rendered, and stopped
        before returning, so no database work happens while it runs.

        Args:
            pages (dict): page name to its HTML.

        Returns:
            dict: page name to ``scroll_width`` (how wide the page is), ``inner_width`` (how wide
            the screen is) and ``heading_left`` (where the page's heading starts, from the left
            edge of the screen).
        """
        measured = {}
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=_CHROMIUM)
            for name, html in pages.items():
                page = browser.new_page(viewport={"width": PHONE_WIDTH, "height": 740})
                page.route("**/*", lambda route, request, html=html: self._serve(route, request, html))
                page.goto(f"{PAGE_ORIGIN}/page/")
                measured[name] = page.evaluate("""() => ({
                    scroll_width: document.documentElement.scrollWidth,
                    inner_width: window.innerWidth,
                    heading_left: document.querySelector('#main-container h1').getBoundingClientRect().left,
                })""")
                page.close()
            browser.close()
        return measured

    @staticmethod
    def _serve(route, request, html):
        """Answer the browser's requests: the page itself, stylesheets, fonts and images from disk.

        Everything else, scripts included, is refused, so the page's layout is the stylesheets'
        alone and nothing reaches out of the test.
        """
        path = urlparse(request.url).path
        if request.url == f"{PAGE_ORIGIN}/page/":
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            return
        if path.startswith(settings.STATIC_URL) and request.resource_type in ("stylesheet", "font", "image"):
            found = finders.find(path[len(settings.STATIC_URL):])
            if found:
                route.fulfill(path=found)
                return
        route.abort()

    def test_pages__are_no_wider_than_a_phone(self):
        """No page can be dragged sideways on a phone, and its content keeps a 7px margin.

        The three pages cover each way the grid meets the container: the sidebar layout's own row
        (the badge list, as a student, whose badges sit in a row inside a panel), a row of
        side-by-side columns straight inside the page (the semester form's three fields, as a
        teacher), and the layout without a sidebar (the public portfolios, signed out).
        """
        config = SiteConfig.get()
        pages = {
            'badges': self._render(reverse('badges:list'), self.student),
            'semester form': self._render(reverse('courses:semester_update', args=[config.active_semester.pk]), self.teacher),
            'public portfolios': self._render(reverse('portfolios:public_list')),
        }
        # Each page only tests its kind of row while it still has side-by-side columns to show.
        self.assertIn('col-xs-4 col-badge', pages['badges'])
        self.assertIn('col-xs-4', pages['semester form'])

        for name, measured in self._measure(pages).items():
            with self.subTest(page=name):
                self.assertEqual(measured['inner_width'], PHONE_WIDTH)
                self.assertLessEqual(measured['scroll_width'], measured['inner_width'])
                self.assertEqual(measured['heading_left'], 7)
