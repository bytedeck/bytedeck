"""Headless render tests for the tick boxes on quest lists (js/tickable-lists.js, #1074).

A student working through a long list of steps in a quest can tick each one off: the items of a
list with the "tickable" class, in a quest's Quest Details and Submission Instructions, get a tick
box. These run the real script and the real stylesheet rules in headless Chromium, on a page laid
out like those two sections.

Hermetic (no Django server, no DB, no tenant routing), and they skip cleanly unless Playwright and
a Chromium build are both available, so a normal suite run (or CI without a browser) is
unaffected.
"""

import glob
import os
import tempfile
from unittest import skipUnless

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


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
    return None


_CHROMIUM = _find_chromium() if HAS_PLAYWRIGHT else None

# Two sections laid out like a quest's (quest_detail_content.html): one with only the lists a teacher
# marked tickable, one with the deck's "every list" option on. The script is loaded twice, as a page
# that includes the quest's sections twice would, so a second run must not add a second box.
_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="file://{bootstrap_css}">
<link rel="stylesheet" href="file://{common_css}">
</head><body>
<div id="marked" class="panel-body tickable-scope">
  <ul id="bullets" class="tickable"><li>Open the file</li>
    <li>
      <p>Save it with your name</p>
    </li>
  </ul>
  <ol id="numbers" class="tickable"><li>Hand it in</li></ol>
  <ul id="plain"><li>Not marked</li></ul>
</div>
<div id="every" class="panel-body tickable-scope" data-tickable-all>
  <ul id="every-bullets"><li>One</li><li>Two</li></ul>
  <ol id="every-numbers"><li>Three</li></ol>
</div>
<ul id="outside" class="tickable"><li>Not in a quest section</li></ul>
<script src="file://{tickable_js}"></script>
<script src="file://{tickable_js}"></script>
</body></html>"""


@skipUnless(HAS_PLAYWRIGHT and _CHROMIUM, "Playwright and a Chromium build are required")
class TickableListsRenderTest(SimpleTestCase):
    """The items of a tickable list in a quest get a tick box each, and nothing else does (#1074)."""

    @classmethod
    def setUpClass(cls):
        """Start one headless browser and build the page for the class."""
        super().setUpClass()
        cls._pw = sync_playwright().start()
        cls._browser = cls._pw.chromium.launch(executable_path=_CHROMIUM)
        html = _PAGE.format(
            bootstrap_css=finders.find('css/bootstrap-3.4.1.min.css'),
            common_css=finders.find('css/custom_common.css'),
            tickable_js=finders.find('js/tickable-lists.js'),
        )
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as fh:
            fh.write(html)
            cls._html_path = fh.name

    @classmethod
    def tearDownClass(cls):
        """Close the browser, stop Playwright and drop the page."""
        cls._browser.close()
        cls._pw.stop()
        os.unlink(cls._html_path)
        super().tearDownClass()

    def setUp(self):
        """Open the page."""
        self.page = self._browser.new_page(viewport={"width": 900, "height": 600})
        self.addCleanup(self.page.close)
        self.page.goto("file://" + self._html_path)

    def _boxes(self, selector):
        """How many tick boxes each item of the list `selector` holds, in order.

        Args:
            selector (str): CSS selector for one list.

        Returns:
            list: the number of tick boxes in each of the list's items.
        """
        return self.page.eval_on_selector(
            selector, "list => [...list.children].map(item => item.querySelectorAll('.tickable-box').length)")

    def _style(self, selector, prop):
        """The computed value of CSS property `prop` on the element `selector`."""
        return self.page.eval_on_selector(selector, f"el => getComputedStyle(el).getPropertyValue('{prop}')")

    def test_tickable_lists__bulleted_list_gets_a_box_in_place_of_each_bullet(self):
        """Each item of a tickable bulleted list gets one box, sitting in the list's indent where the
        bullet was. An item whose text is in a paragraph gets its box inside that paragraph, on the
        text's line."""
        self.assertEqual(self._boxes("#bullets"), [1, 1])
        self.assertEqual(self._style("#bullets", "list-style-type"), "none")

        item = self.page.locator("#bullets > li").first.bounding_box()
        box = self.page.locator("#bullets > li > .tickable-box").bounding_box()
        self.assertLess(box["x"] + box["width"], item["x"])  # in the indent, left of the item's text

        paragraph = self.page.locator("#bullets > li > p").bounding_box()
        boxed = self.page.locator("#bullets > li > p > .tickable-box").bounding_box()
        self.assertLess(boxed["y"], paragraph["y"] + paragraph["height"])  # on the paragraph's line, not above it

    def test_tickable_lists__numbered_list_keeps_its_numbers_with_a_box_beside_each(self):
        """A tickable numbered list keeps its numbers, and each item's box starts its text."""
        self.assertEqual(self._boxes("#numbers"), [1])
        self.assertEqual(self._style("#numbers", "list-style-type"), "decimal")
        self.assertTrue(self.page.eval_on_selector(
            "#numbers > li", "item => item.firstChild.classList.contains('tickable-box')"))

    def test_tickable_lists__a_list_without_the_class_gets_no_boxes(self):
        """In a section without the deck's every-list option, only the lists marked tickable change."""
        self.assertEqual(self._boxes("#plain"), [0])
        self.assertEqual(self._style("#plain", "list-style-type"), "disc")

    def test_tickable_lists__every_list_option_ticks_every_list_in_its_section(self):
        """With the deck's every-list option on, every list in the section gets boxes, unmarked or not."""
        self.assertEqual(self._boxes("#every-bullets"), [1, 1])
        self.assertEqual(self._boxes("#every-numbers"), [1])

    def test_tickable_lists__a_list_outside_the_quest_sections_is_left_alone(self):
        """Only Quest Details and Submission Instructions get boxes, even for a list marked tickable."""
        self.assertEqual(self._boxes("#outside"), [0])

    def test_tickable_lists__a_box_can_be_ticked(self):
        """Clicking a box ticks it."""
        box = self.page.locator("#numbers .tickable-box")
        box.click()
        self.assertTrue(box.is_checked())
