"""Headless render tests for the competency levels on a submission's approval form (#2952).

Each competency is a row: its name, then its level buttons. A name too long for one line wraps in
a column of its own, and the buttons keep a column of their own beside it, rather than dropping
under the name. Below Bootstrap's sm breakpoint there isn't room for both side by side, so there the
buttons go under the name, as the marking table's columns stack on a narrow screen.

The submission page is rendered by the app itself, through the test client, and opened in headless
Chromium with the app's own static files, so the layout is the stylesheets' own. It skips cleanly
unless Playwright and a Chromium build are both available, like the other render tests (e.g.
questions/tests/test_marker_notes_render.py).
"""

import glob
import os
from unittest import skipUnless
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.staticfiles import finders
from django.urls import reverse

from competencies.tests.test_approval import ApprovalTestMixin, set_competencies_flag
from hackerspace_online.tests.utils import ByteDeckTenantTestCase

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover (Playwright is in requirements; this guards an install without it)
    HAS_PLAYWRIGHT = False

#: Where the rendered page pretends to live, so its root-relative links resolve.
PAGE_ORIGIN = "http://deck.test"

#: A competency name too long for one line beside the level buttons, as BC's curricular
#: competencies often are.
LONG_NAME = (
    "Identify and apply strategies to evaluate the credibility and accuracy of information "
    "and sources, and explain how they shaped the design"
)


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
class ApprovalLevelsRenderTest(ApprovalTestMixin, ByteDeckTenantTestCase):
    """The approval form's competency rows, laid out in a browser."""

    def setUp(self):
        """Give one competency a long name, render the submission as the teacher sees it, and open
        it in a headless browser.

        Playwright's sync API runs an event loop, and Django refuses database access while one is
        running, so the browser starts only once the page is rendered, and is stopped by a cleanup.
        """
        set_competencies_flag(True)
        self.thinking.name = LONG_NAME
        self.thinking.save()
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("quests:submission", args=[self.make_submission().pk]))
        self.assertContains(response, 'class="competency-approval-levels"')
        self.html = response.content.decode()

        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        browser = playwright.chromium.launch(executable_path=_CHROMIUM)
        self.addCleanup(browser.close)
        self.page = browser.new_page(viewport={"width": 1200, "height": 900})
        self.page.route("**/*", self._serve)
        self.page.goto(f"{PAGE_ORIGIN}/page/")

    def _serve(self, route, request):
        """Answer the page's requests: the page itself and its static files from disk. Anything
        else is refused.

        Args:
            route (playwright.sync_api.Route): the intercepted request's route, answered here.
            request (playwright.sync_api.Request): the request it intercepted.
        """
        path = urlparse(request.url).path
        if path == "/page/":
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        elif path.startswith(settings.STATIC_URL) and finders.find(path[len(settings.STATIC_URL):]):
            route.fulfill(path=finders.find(path[len(settings.STATIC_URL):]))
        else:
            route.abort()

    def _long_row(self):
        """The boxes of the long-named competency's name and its level buttons.

        Returns:
            tuple: the name's and the button group's bounding boxes, in CSS pixels.
        """
        row = self.page.locator(".competency-approval-row", has_text="Identify and apply")
        return row.locator(".competency-approval-name").bounding_box(), row.locator(".btn-group").bounding_box()

    def test_layout__a_long_name_wraps_beside_its_buttons(self):
        """A name too long for one line wraps in its own column, and its level buttons stay beside
        it, level with the name, rather than dropping onto a line of their own (#2952)."""
        name, buttons = self._long_row()

        self.assertGreater(name["height"], 30, "the long name wraps onto more than one line")
        self.assertGreaterEqual(buttons["x"], name["x"] + name["width"] - 1, "the buttons are right of the name")
        self.assertLess(buttons["y"], name["y"] + name["height"], "the buttons are beside the name, not under it")

    def test_layout__buttons_go_under_the_name_on_a_narrow_screen(self):
        """Below Bootstrap's sm breakpoint the buttons take a line of their own under a long name,
        since there is no room for it to read beside them, and stay at the right, in line with the
        buttons of a row whose name fits beside them."""
        self.page.set_viewport_size({"width": 600, "height": 900})

        name, buttons = self._long_row()
        short_buttons = self.page.locator(".competency-approval-row", has_text="Communicating").locator(".btn-group").bounding_box()

        self.assertGreaterEqual(buttons["y"], name["y"] + name["height"] - 1)
        self.assertAlmostEqual(buttons["x"] + buttons["width"], short_buttons["x"] + short_buttons["width"], delta=1)
