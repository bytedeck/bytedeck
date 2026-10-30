"""Headless render tests: a flagged submission's Flag buttons turn into Unflag buttons (#824).

Flagging a submission is an Ajax request, so the page isn't reloaded: before #824 the button showed
a tick and went back to Flag, though the submission was flagged and a reload would offer Unflag.
Now its Flag buttons turn into the same Unflag button a reload would draw, all of them (a
submission's own page draws two). A flag that fails leaves the Flag button as it was.

The submission page is rendered by the app itself, through the test client, and opened in headless
Chromium with the app's own static files, scripts included. The test answers the flag request
itself and refuses every other request. It skips cleanly unless Playwright and a Chromium build
are both available, like the other render tests (e.g. test_submit_while_attaching_render.py).
"""

import glob
import os
from unittest import skipUnless
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.urls import reverse

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover (Playwright is in requirements; this guards an install without it)
    HAS_PLAYWRIGHT = False

User = get_user_model()

#: Where the rendered page pretends to live, so its root-relative links resolve.
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
class FlagSubmissionRenderTest(ByteDeckTenantTestCase):
    """Flagging a submission turns its Flag buttons into Unflag buttons, without a reload (#824)."""

    def setUp(self):
        """Render a student's submitted quest as their teacher sees it, and open it in a headless
        browser.

        Playwright's sync API runs an event loop, and Django refuses database access while one
        is running, so the browser starts only once the page is rendered, and is stopped by a
        cleanup, which runs before the test's transaction is rolled back.
        """
        teacher = User.objects.create_user('flag_teacher', is_staff=True)
        student = User.objects.create_user('flag_student')
        quest = baker.make(Quest, name="Flag Quest", xp=5, published=True)
        submission = baker.make(
            QuestSubmission, user=student, quest=quest,
            semester=SiteConfig.get().active_semester, is_completed=True,
        )

        self.client.force_login(teacher)
        response = self.client.get(submission.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.html = response.content.decode()
        self.flag_path = reverse('quests:ajax_flag')
        self.unflag_path = reverse('quests:unflag', args=[submission.id])
        self.submission_id = submission.id

        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        browser = playwright.chromium.launch(executable_path=_CHROMIUM)
        self.addCleanup(browser.close)
        self.page = browser.new_page()
        self.flag_status = 200  # how the test answers the flag request
        self.flags = []  # the body of each flag request
        self.dialogs = []  # the text of any alert the page raised
        self.page.on("dialog", lambda dialog: (self.dialogs.append(dialog.message), dialog.dismiss()))
        self.page.route("**/*", self._serve)
        self.page.goto(f"{PAGE_ORIGIN}/page/")

    def _serve(self, route, request):
        """Answer the page's requests: the page itself and its static files from disk, and the flag
        request with `flag_status`. Anything else is refused.

        Args:
            route (playwright.sync_api.Route): the intercepted request's route, answered here.
            request (playwright.sync_api.Request): the request it intercepted.
        """
        path = urlparse(request.url).path
        if path == "/page/":
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        elif path.startswith(settings.STATIC_URL) and finders.find(path[len(settings.STATIC_URL):]):
            route.fulfill(path=finders.find(path[len(settings.STATIC_URL):]))
        elif path == self.flag_path:
            self.flags.append(request.post_data)
            route.fulfill(status=self.flag_status, content_type="application/json", body="{}")
        else:
            route.abort()

    def _flag(self):
        """Press the first Flag button on the page."""
        self.page.locator('.btn-flag-submission').first.click()

    def test_flag__the_flag_buttons_become_unflag_buttons(self):
        """Once the flag goes through, every Flag button for the submission (its page draws two)
        becomes the Unflag button, linked to unflag it, as a reload would show them."""
        self.assertEqual(self.page.locator('.btn-flag-submission').count(), 2)

        self._flag()

        self.page.wait_for_selector('.btn-unflag-submission', timeout=10000)
        self.page.wait_for_function("document.querySelectorAll('.btn-unflag-submission').length === 2", timeout=10000)
        self.assertEqual(self.page.locator('.btn-flag-submission').count(), 0)
        for href in self.page.locator('.btn-unflag-submission').evaluate_all("buttons => buttons.map(b => b.getAttribute('href'))"):
            self.assertEqual(href, self.unflag_path)
        self.assertEqual(len(self.flags), 1)
        self.assertIn(f"submission_id={self.submission_id}", self.flags[0])
        self.assertEqual(self.dialogs, [])

    def test_flag__both_buttons_pressed_at_once_send_one_flag(self):
        """Pressing the submission's two Flag buttons before the first flag is answered sends one
        flag, not two: a second still on its way after the buttons became Unflag could flag the
        submission again after the teacher unflagged it."""
        self.page.evaluate("document.querySelectorAll('.btn-flag-submission').forEach(button => button.click())")

        self.page.wait_for_function("document.querySelectorAll('.btn-unflag-submission').length === 2", timeout=10000)
        self.assertEqual(len(self.flags), 1)

    def test_flag__a_failed_flag_leaves_the_flag_button(self):
        """A flag the server refuses says so, and leaves the Flag button as it was, so it can be
        pressed again."""
        self.flag_status = 500

        self._flag()

        self.page.wait_for_function("document.querySelector('.btn-flag-submission .fa-spinner') === null", timeout=10000)
        self.assertEqual(len(self.dialogs), 1)
        self.assertIn("wasn't flagged", self.dialogs[0])
        self.assertEqual(self.page.locator('.btn-unflag-submission').count(), 0)
        first = self.page.locator('.btn-flag-submission').first
        self.assertTrue(first.locator('.fa-flag-o').is_visible())
        self.assertEqual(first.locator('.fa-spinner, .fa-check').count(), 0)

        self.flag_status = 200
        self._flag()
        self.page.wait_for_selector('.btn-unflag-submission', timeout=10000)
        self.assertEqual(len(self.flags), 2)
