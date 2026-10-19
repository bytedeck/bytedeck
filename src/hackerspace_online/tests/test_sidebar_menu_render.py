"""Headless render tests: the sidebar's ⋮ menu is part of its row, not a button of its own (#1133).

Quests and Badges each have a "more" menu, the ⋮ at the right of their row in the sidebar. It was
a separate button beside the row: white while the row beside it was the current page's colour, a
grey box of its own when pointed at, and greyed again while its menu was open. The row is now one
element that its link and its ⋮ fill between them, so the ⋮ always shows the row's colour.

A page is rendered by the app itself, through the test client, and opened in headless Chromium
with the app's own static files, scripts included, since Bootstrap's script opens the menu.
Every other request is refused. The tests skip cleanly unless Playwright and a Chromium build are
both available, like the other render tests (e.g. test_phone_width_render.py).
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

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover (Playwright is in requirements; this guards an install without it)
    HAS_PLAYWRIGHT = False

User = get_user_model()

#: Where the rendered pages pretend to live, so their root-relative links resolve.
PAGE_ORIGIN = "http://deck.test"

#: The colour an element shows: its own background, or the nearest one behind it.
SHOWN_BACKGROUND = """el => {
    for (let e = el; e; e = e.parentElement) {
        const colour = getComputedStyle(e).backgroundColor;
        if (colour !== 'rgba(0, 0, 0, 0)' && colour !== 'transparent') return colour;
    }
    return null;
}"""


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
class SidebarMenuRenderTest(ByteDeckTenantTestCase):
    """The ⋮ beside Quests and Badges shows the same colour as the rest of its row."""

    def setUp(self):
        """Render the quest list, where Quests is the current page, and the announcements, where
        neither row is, as a teacher sees them.

        Playwright's sync API runs an event loop, and Django refuses database access while one
        is running, so the browser starts only once the pages are rendered, and is stopped by a
        cleanup, which runs before the test's transaction is rolled back.
        """
        self.client.force_login(User.objects.create_user('sidebar_teacher', is_staff=True))
        self.pages = {}
        for name, url in (('quests', reverse('quests:quests')), ('announcements', reverse('announcements:list'))):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.pages[f'/{name}/'] = response.content.decode()

        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        browser = playwright.chromium.launch(executable_path=_CHROMIUM)
        self.addCleanup(browser.close)
        self.page = browser.new_page(viewport={'width': 1280, 'height': 900})
        self.page.route("**/*", self._serve)

    def _serve(self, route, request):
        """Answer the page's requests: the rendered pages and their static files from disk. Anything
        else is refused.

        Args:
            route (playwright.sync_api.Route): the intercepted request's route, answered here.
            request (playwright.sync_api.Request): the request it intercepted.
        """
        path = urlparse(request.url).path
        if path in self.pages:
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.pages[path])
        elif path.startswith(settings.STATIC_URL) and finders.find(path[len(settings.STATIC_URL):]):
            route.fulfill(path=finders.find(path[len(settings.STATIC_URL):]))
        else:
            route.abort()

    def _shown(self, selector):
        """The background colour an element shows, its own or the nearest behind it."""
        return self.page.locator(selector).evaluate(SHOWN_BACKGROUND)

    def test_current_page__the_menu_shows_its_rows_colour(self):
        """With Quests the current page, its ⋮ is the row's colour too, not a white button
        beside it, and there's no line between the two."""
        self.page.goto(f"{PAGE_ORIGIN}/quests/")

        self.assertEqual(self._shown('#quests-menu-dropdown'), self._shown('#quests-menu'))
        self.assertEqual(self._shown('#quests-menu'), 'rgb(51, 122, 183)')  # the current page's blue
        self.assertEqual(self.page.locator('#quests-menu').evaluate("el => getComputedStyle(el).borderRightWidth"), '0px')

    def test_pointing_at_the_menu__highlights_its_row_not_a_box_of_its_own(self):
        """Pointing at Badges' ⋮ highlights the Badges row as a whole, the way pointing at any
        other row does."""
        self.page.goto(f"{PAGE_ORIGIN}/announcements/")
        resting = self._shown('#badges-menu')

        self.page.locator('#badges-menu-dropdown').hover()

        self.assertEqual(self._shown('#badges-menu-dropdown'), self._shown('#badges-menu'))
        self.assertNotEqual(self._shown('#badges-menu'), resting)

    def test_open_menu__the_row_keeps_its_colour(self):
        """While Quests' menu is open, its row stays the current page's colour, the ⋮ included."""
        self.page.goto(f"{PAGE_ORIGIN}/quests/")

        self.page.locator('#quests-menu-dropdown').click()
        self.page.mouse.move(0, 0)

        self.assertTrue(self.page.locator('#lg-menu-main .dropdown-menu').first.is_visible())
        self.assertEqual(self._shown('#quests-menu-dropdown'), 'rgb(51, 122, 183)')
        self.assertEqual(self._shown('#quests-menu'), 'rgb(51, 122, 183)')
