"""Headless render tests for the summernote caret: toolbar commands land where the writer is (#2734).

Summernote rebuilds the range it works from out of the live document selection every time the
editing area takes focus, and every toolbar command focuses the editing area on its way in. A
press moves the selection out of the editing area first, so by the time the command runs the only
selection left is the one the browser makes on focus: the very start of the content. Tables were
inserted at the top of the editor on every attempt, and a list press with the selection elsewhere
put the list at the top and scrolled the editor up to it.

These drive the *real* vendored summernote build and the *real* keep-caret plugin in headless
Chromium, over the two flows that show it: inserting a table with the caret near the bottom, and
pressing the list button after the writer has moved on to another field.

Hermetic (no Django server, no DB, no tenant routing), and they skip cleanly unless Playwright and
a Chromium build are both available, so a normal suite run (or CI without a browser) is
unaffected. They run for real once a Chromium build is present (see the front-end-testing setup in
#2053/#503).
"""

import glob
import os
import tempfile
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

KEEP_CARET_JS = os.path.join(settings.STATIC_URL, 'js/summernote-keep-caret.js')

# Enough paragraphs that the editor has to scroll, so a command landing at the top is unmistakable.
PARAGRAPH_COUNT = 20
CONTENT = "".join(f"<p>Line {number}, written by the teacher.</p>" for number in range(1, PARAGRAPH_COUNT + 1))


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


def _asset(static_url):
    """Absolute path on disk of a static file, named the way SUMMERNOTE_CONFIG names one.

    Args:
        static_url (str): a STATIC_URL-prefixed path, e.g. ``/static/js/summernote-keep-caret.js``.

    Returns:
        str: the absolute path the static finders resolve it to.
    """
    return finders.find(static_url[len(settings.STATIC_URL):])


# The page is the editor on its own: summernote and the plugins the inplace widget loads, over the
# same vendored jQuery and Bootstrap the site runs on. Only the keep-caret plugin is loaded, and it
# is taken from SUMMERNOTE_CONFIG so that dropping it from the settings fails these too. The other
# plugins are left out because they pull in assets (KaTeX, icon lists) the editor does not need to
# place a caret.
_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="file://{bootstrap_css}">
<link rel="stylesheet" href="file://{summernote_css}">
<style>body {{ margin: 0; font: 14px/1.4 sans-serif; }} #another-field {{ display: block; margin: 4px; }}</style>
</head><body>
<input id="another-field" type="text" value="the quest name">
<textarea id="editor">{content}</textarea>
<script src="file://{jquery}"></script>
<script src="file://{bootstrap_js}"></script>
<script src="file://{summernote_js}"></script>
<script src="file://{keep_caret_js}"></script>
<script>
window.editorReady = false;
$(function () {{
    $('#editor').summernote({{
        height: 150,
        toolbar: [['para', ['ul', 'ol']], ['table', ['table']]],
        callbacks: {{ onInit: function () {{ window.editorReady = true; }} }}
    }});
}});
</script>
</body></html>"""


class SummernoteKeepCaretConfigTest(SimpleTestCase):
    """The keep-caret plugin is loaded by both summernote widget flavours (#2734)."""

    def test_summernote_config__loads_the_keep_caret_plugin(self):
        """Both the iframe widget and the inplace widget load the plugin, so every editor keeps its caret."""
        self.assertIn(KEEP_CARET_JS, settings.SUMMERNOTE_CONFIG['js'])
        self.assertIn(KEEP_CARET_JS, settings.SUMMERNOTE_CONFIG['js_for_inplace'])

    def test_summernote_config__keep_caret_plugin_is_on_disk(self):
        """The path the settings name resolves to a real static file, so the editors can load it."""
        self.assertIsNotNone(_asset(KEEP_CARET_JS))


@skipUnless(HAS_PLAYWRIGHT and _CHROMIUM, "Playwright and a Chromium build are required")
class SummernoteKeepCaretRenderTest(SimpleTestCase):
    """Toolbar commands act where the writer put the caret, not at the top of the editor (#2734)."""

    @classmethod
    def setUpClass(cls):
        """Start one headless browser and build the editor page for the class."""
        super().setUpClass()
        cls._pw = sync_playwright().start()
        cls._browser = cls._pw.chromium.launch(executable_path=_CHROMIUM)
        html = _PAGE.format(
            bootstrap_css=_asset(os.path.join(settings.STATIC_URL, 'css/bootstrap-3.4.1.min.css')),
            summernote_css=finders.find('summernote/summernote.min.css'),
            jquery=_asset(os.path.join(settings.STATIC_URL, 'js/jquery-2.2.4.min.js')),
            bootstrap_js=_asset(os.path.join(settings.STATIC_URL, 'js/bootstrap-3.4.1.min.js')),
            summernote_js=finders.find('summernote/summernote.min.js'),
            keep_caret_js=_asset(KEEP_CARET_JS),
            content=CONTENT,
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
        """Open the editor, scroll it to its last line and leave the caret unset."""
        self.page = self._browser.new_page(viewport={"width": 900, "height": 600})
        self.addCleanup(self.page.close)
        self.page.goto("file://" + self._html_path)
        self.page.wait_for_function("() => window.editorReady === true", timeout=20000)
        self.page.evaluate("() => { var e = document.querySelector('.note-editable'); e.scrollTop = e.scrollHeight; }")
        self.page.wait_for_timeout(200)

    def _press(self, selector, index=0, dx=None, dy=None):
        """Press a page element with real mouse events, so the browser moves focus as it really would.

        Playwright's own click scrolls its target into view first, which moves the very scroll
        position these tests measure, so the press is driven from the element's box instead.

        Args:
            selector (str): CSS selector for the element to press.
            index (int): which match to press, when the selector matches several.
            dx (float): x offset into the element's box, or None for its centre.
            dy (float): y offset into the element's box, or None for its centre.
        """
        box = self.page.locator(selector).nth(index).bounding_box()
        self.assertIsNotNone(box, f"{selector} is not on the page")
        self.page.mouse.move(box["x"] + (box["width"] / 2 if dx is None else dx),
                             box["y"] + (box["height"] / 2 if dy is None else dy))
        self.page.wait_for_timeout(100)
        self.page.mouse.down()
        self.page.wait_for_timeout(60)
        self.page.mouse.up()

    def _content(self):
        """Report what the editor holds and where it is scrolled to.

        Returns:
            dict: ``children`` (each top-level element's tag and text), ``table`` and ``list``
            (the index of the first table and the first list among them, or -1), and
            ``scroll_top``.
        """
        return self.page.evaluate("""() => {
            var editable = document.querySelector('.note-editable');
            function indexOf(node) {
                if (!node) return -1;
                while (node && node.parentNode !== editable) node = node.parentNode;
                return node ? Array.prototype.indexOf.call(editable.children, node) : -1;
            }
            return {
                children: Array.prototype.map.call(editable.children, function (child) {
                    return {tag: child.tagName, text: (child.textContent || '').trim().slice(0, 30)};
                }),
                table: indexOf(editable.querySelector('table')),
                list: indexOf(editable.querySelector('ul')),
                scroll_top: Math.round(editable.scrollTop)
            };
        }""")

    def test_insert_table__lands_at_the_caret(self):
        """A table goes in beside the line the caret is on, leaving the lines above it alone."""
        self._press(".note-editable p", index=PARAGRAPH_COUNT - 1, dx=30)
        self._press('.note-btn[aria-label="Table"]')
        self.page.wait_for_timeout(300)
        self._press(".note-dimension-picker-mousecatcher", dx=30, dy=30)
        self.page.wait_for_timeout(400)

        content = self._content()
        self.assertNotEqual(content["table"], -1, "no table was inserted")
        self.assertGreater(
            content["table"], PARAGRAPH_COUNT - 3,
            f"the table went in near the top instead of at the caret: {content['children'][:4]}")
        self.assertTrue(content["children"][0]["text"].startswith("Line 1,"),
                        "the first line of the editor was pushed aside by the table")

    def test_insert_table__does_not_scroll_the_editor_to_the_top(self):
        """The editor stays on the line being worked on rather than jumping back to line one."""
        self._press(".note-editable p", index=PARAGRAPH_COUNT - 1, dx=30)
        self._press('.note-btn[aria-label="Table"]')
        self.page.wait_for_timeout(300)
        self._press(".note-dimension-picker-mousecatcher", dx=30, dy=30)
        self.page.wait_for_timeout(400)

        self.assertGreater(self._content()["scroll_top"], 0, "the editor scrolled back to its first line")

    def test_insert_list__uses_the_caret_after_the_writer_leaves_the_editor(self):
        """A list started after typing in another field still goes on the line the caret was left on."""
        self._press(".note-editable p", index=PARAGRAPH_COUNT - 1, dx=30)
        self._press("#another-field")
        self.page.wait_for_timeout(150)
        self._press('.note-btn[aria-label^="Unordered list"]')
        self.page.wait_for_timeout(400)

        content = self._content()
        self.assertEqual(
            content["list"], PARAGRAPH_COUNT - 1,
            f"the list went in near the top instead of at the caret: {content['children'][:4]}")
        self.assertGreater(content["scroll_top"], 0, "the editor scrolled back to its first line")
