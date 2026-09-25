"""Headless render tests for the summernote classes plugin: each editor restyles its own content (#2735).

The plugin lists the classes an element can take in its editor's status bar, and a click on one
toggles it on the element last pressed in that editor. A page can hold several editors (the
quest form has three), and the plugin's handlers must stay inside the one they belong to: a
click on a class in one editor restyled the element last pressed in every other editor too, and
a table cell pressed in one editor turned off the table button in all of them.

These drive the *real* vendored summernote build and the *real* classes plugin in headless
Chromium, with two editors on one page. Hermetic (no Django server, no DB, no tenant routing), and
they skip cleanly unless Playwright and a Chromium build are both available, like the caret tests
beside them (test_keep_caret.py).
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
except ImportError:  # pragma: no cover (Playwright is in requirements; this guards an install without it)
    HAS_PLAYWRIGHT = False

CLASSES_JS = os.path.join(settings.STATIC_URL, 'js/summernote-classes.js')

# Each editor holds a line and a table cell, told apart by which editor they are in.
CONTENT = '<p>{which} line</p><table class="table"><tbody><tr><td>{which} cell</td></tr></tbody></table>'


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


def _asset(static_url):
    """Absolute path on disk of a static file, named the way SUMMERNOTE_CONFIG names one.

    Args:
        static_url (str): a STATIC_URL-prefixed path, e.g. ``/static/js/summernote-classes.js``.

    Returns:
        str: the absolute path the static finders resolve it to.
    """
    return finders.find(static_url[len(settings.STATIC_URL):])


# Two editors on one page, over the same vendored jQuery and Bootstrap the site runs on, with the
# classes plugin taken from SUMMERNOTE_CONFIG's path. disableTableNesting is on, so pressing a table
# cell exercises the plugin's table button as well as its class list.
_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="file://{bootstrap_css}">
<link rel="stylesheet" href="file://{summernote_css}">
<style>body {{ margin: 0; font: 14px/1.4 sans-serif; }}</style>
</head><body>
<textarea id="first">{first}</textarea>
<textarea id="second">{second}</textarea>
<script src="file://{jquery}"></script>
<script src="file://{bootstrap_js}"></script>
<script src="file://{summernote_js}"></script>
<script src="file://{classes_js}"></script>
<script>
window.editorsReady = 0;
$(function () {{
    $('#first, #second').summernote({{
        height: 120,
        disableTableNesting: true,
        toolbar: [['table', ['table']]],
        callbacks: {{ onInit: function () {{ window.editorsReady += 1; }} }}
    }});
}});
</script>
</body></html>"""


class SummernoteClassesConfigTest(SimpleTestCase):
    """The classes plugin is loaded by the inplace widget, which every multi-editor form uses."""

    def test_summernote_config__loads_the_classes_plugin(self):
        """The inplace widget loads the plugin, from a path that is a real static file."""
        self.assertIn(CLASSES_JS, settings.SUMMERNOTE_CONFIG['js_for_inplace'])
        self.assertIsNotNone(_asset(CLASSES_JS))


@skipUnless(HAS_PLAYWRIGHT and _CHROMIUM, "Playwright and a Chromium build are required")
class SummernoteClassesRenderTest(SimpleTestCase):
    """A class clicked in one editor's status bar restyles that editor's element only (#2735)."""

    @classmethod
    def setUpClass(cls):
        """Start one headless browser and build the two-editor page for the class."""
        super().setUpClass()
        cls._pw = sync_playwright().start()
        cls._browser = cls._pw.chromium.launch(executable_path=_CHROMIUM)
        html = _PAGE.format(
            bootstrap_css=_asset(os.path.join(settings.STATIC_URL, 'css/bootstrap-3.4.1.min.css')),
            summernote_css=finders.find('summernote/summernote.min.css'),
            jquery=_asset(os.path.join(settings.STATIC_URL, 'js/jquery-2.2.4.min.js')),
            bootstrap_js=_asset(os.path.join(settings.STATIC_URL, 'js/bootstrap-3.4.1.min.js')),
            summernote_js=finders.find('summernote/summernote.min.js'),
            classes_js=_asset(CLASSES_JS),
            first=CONTENT.format(which='First'),
            second=CONTENT.format(which='Second'),
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
        """Open the page once both editors are ready."""
        self.page = self._browser.new_page(viewport={"width": 900, "height": 700})
        self.addCleanup(self.page.close)
        self.page.goto("file://" + self._html_path)
        self.page.wait_for_function("() => window.editorsReady === 2", timeout=20000)

    def _press(self, selector, editor):
        """Press an element inside one editor with real mouse events, as a writer's click would.

        Args:
            selector (str): CSS selector for the element, looked up inside that editor.
            editor (int): 0 for the first editor on the page, 1 for the second.
        """
        box = self.page.locator('.note-editor').nth(editor).locator(selector).first.bounding_box()
        self.assertIsNotNone(box, f"{selector} is not in editor {editor}")
        self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        self.page.mouse.down()
        self.page.mouse.up()
        self.page.wait_for_timeout(100)

    def test_class_label__restyles_only_its_own_editors_element(self):
        """With a line pressed in each editor, clicking a class in the first one's status bar puts
        it on the first editor's line alone, and marks that label as active."""
        self._press('.note-editable p', editor=0)
        self._press('.note-editable p', editor=1)
        self._press('.note-status-output [data-class="text-center"]', editor=0)

        result = self.page.evaluate("""() => ({
            lines: $('.note-editable p').map(function () { return this.className; }).get(),
            label_active: $('.note-editor').eq(0)
                .find('.note-status-output [data-class="text-center"]').hasClass('note-classes-active'),
        })""")

        self.assertEqual(result['lines'], ['text-center', ''])
        self.assertTrue(result['label_active'])

    def test_table_cell__turns_off_its_own_editors_table_button_only(self):
        """Pressing a table cell in the first editor turns off that editor's table button, so no
        table goes inside the table, and leaves the second editor's alone."""
        self._press('.note-editable td', editor=0)

        disabled = self.page.evaluate(
            """() => $('.note-editor').map(function () {
                return $(this).find('.note-toolbar [aria-label="Table"]').prop('disabled');
            }).get()"""
        )

        self.assertEqual(disabled, [True, False])
