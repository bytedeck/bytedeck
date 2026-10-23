"""Headless render tests for marking a submission's question answers (#2923, #2927).

A question's marker notes open from their info button in a popover that shows them as written,
images, links and tables included, and that stays open until the button, a click elsewhere or
Escape closes it. The answers sit in three columns, Question, Answer provided and Solution, on a
wide screen, and stack in that order on a narrow one.

The submission page is rendered by the app itself, through the test client, and opened in
headless Chromium with the app's own static files, scripts and stylesheets included. Every other
request is refused. The tests skip cleanly unless Playwright and a Chromium build are both
available, like the other render tests (e.g. quest_manager/tests/test_flag_submission_render.py).
"""

import glob
import os
from unittest import skipUnless
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.staticfiles import finders
from django.urls import reverse

from questions.tests.test_integration import QuestionSubmissionFlowTestBase

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover (Playwright is in requirements; this guards an install without it)
    HAS_PLAYWRIGHT = False

#: Where the rendered page pretends to live, so its root-relative links resolve.
PAGE_ORIGIN = "http://deck.test"

#: Marker notes holding what a plain-text popover would lose: formatting, an image, a link and a table.
NOTES = (
    '<p>Look for a <b>working</b> link.</p>'
    '<p><img class="notes-image" src="/static/img/banner.png" style="width: 900px;"></p>'
    '<p><a class="notes-link" href="https://example.com/rubric">The rubric</a></p>'
    '<table class="table notes-table"><tbody><tr><td>Full marks</td><td>Loads and is styled</td></tr></tbody></table>'
)

#: The answers' marker notes button: the quest's own question table, above, has one too.
BUTTON = ".question-answers .marker-notes-popover"


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
class MarkingAnswersRenderTest(QuestionSubmissionFlowTestBase):
    """A teacher marking a submission's answers, in a browser."""

    def setUp(self):
        """Have the student submit their answers, render the submission as their teacher sees it,
        and open it in a headless browser.

        Playwright's sync API runs an event loop, and Django refuses database access while one
        is running, so the browser starts only once the page is rendered, and is stopped by a
        cleanup, which runs before the test's transaction is rolled back.
        """
        super().setUp()
        self.short_question.solution_text = "Any URL that loads"
        self.short_question.marker_notes = NOTES
        self.short_question.save()
        self.client.post(
            reverse("quests:complete", args=[self.submission.id]),
            data={"complete": True, "comment_text": "", **self.formset_data()})

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="table table-condensed question-answers"')
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

    def _open_notes(self):
        """Press the answers' marker notes button and wait for the popover to finish opening."""
        self.page.locator(BUTTON).first.click()
        self.page.wait_for_selector(".marker-notes-tip.in", timeout=10000)

    def _wait_closed(self):
        """Wait for the marker notes popover to finish closing."""
        self.page.wait_for_selector(".marker-notes-tip", state="detached", timeout=10000)

    def _box(self, selector):
        """The bounding box of the first element the selector finds.

        Args:
            selector (str): a CSS selector.

        Returns:
            dict: the element's x, y, width and height, in CSS pixels.
        """
        return self.page.locator(selector).first.bounding_box()

    def test_marker_notes__open_showing_the_notes_as_written(self):
        """The popover shows the notes' HTML, formatting, image, link and table included, the image
        held to the popover's width."""
        self._open_notes()

        tip = self.page.locator(".marker-notes-tip")
        self.assertEqual(tip.locator(".popover-title").inner_text(), "Marker Notes")
        self.assertEqual(tip.locator(".popover-content b").inner_text(), "working")
        self.assertEqual(tip.locator(".notes-link").get_attribute("href"), "https://example.com/rubric")
        self.assertTrue(tip.locator(".notes-table").is_visible())
        image = tip.locator(".notes-image")
        self.page.wait_for_function("document.querySelector('.marker-notes-tip .notes-image').naturalWidth > 0", timeout=10000)
        self.assertLessEqual(image.bounding_box()["width"], tip.bounding_box()["width"])

    def test_marker_notes__stay_open_until_closed(self):
        """The notes stay open to be read, and close from a click elsewhere, Escape, or their
        button, which opens them again with a single click each time."""
        self._open_notes()
        self.page.mouse.move(5, 5)
        self.page.wait_for_timeout(300)
        self.page.locator(".marker-notes-tip .notes-table").click()
        self.assertEqual(self.page.locator(".marker-notes-tip.in").count(), 1, "a click inside keeps the notes open")

        self.page.mouse.click(5, 300)
        self._wait_closed()

        self._open_notes()
        self.page.keyboard.press("Escape")
        self._wait_closed()

        self._open_notes()
        self.page.locator(BUTTON).first.click()
        self._wait_closed()

    def test_layout__three_columns_on_a_wide_screen(self):
        """On a wide screen each answer is a row: its question, the answer and the solution side
        by side, under the header row naming them."""
        cells = [self._box(f".question-answers tbody tr:first-child td:nth-child({n})") for n in (1, 2, 3)]

        self.assertTrue(self.page.locator(".question-answers thead").is_visible())
        self.assertEqual({round(cell["y"]) for cell in cells}, {round(cells[0]["y"])})
        self.assertLess(cells[0]["x"], cells[1]["x"])
        self.assertLess(cells[1]["x"], cells[2]["x"])
        self.assertFalse(self.page.locator(".question-answers-label").first.is_visible())

    def test_layout__stacked_on_a_narrow_screen(self):
        """Below Bootstrap's sm breakpoint the question comes first, then the answer, then the
        solution, one under another, each under a label of its own in place of the header row."""
        self.page.set_viewport_size({"width": 600, "height": 900})

        cells = [self._box(f".question-answers tbody tr:first-child td:nth-child({n})") for n in (1, 2, 3)]

        self.assertFalse(self.page.locator(".question-answers thead").is_visible())
        self.assertEqual({round(cell["x"]) for cell in cells}, {round(cells[0]["x"])})
        self.assertGreaterEqual(cells[1]["y"], cells[0]["y"] + cells[0]["height"] - 1)
        self.assertGreaterEqual(cells[2]["y"], cells[1]["y"] + cells[1]["height"] - 1)
        labels = self.page.locator(".question-answers tbody tr:first-child .question-answers-label")
        self.assertEqual(labels.all_inner_texts(), ["Answer provided", "Solution"])
        self.assertTrue(labels.first.is_visible())
