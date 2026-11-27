"""Tests for dropping the text and highlight colors that pasted content brings with it (#3008).

Copying text off a page carries the colors it was shown in: the browser writes the computed color
and background-color into the copied HTML as inline styles. A student who copied from their own
comment in the dark theme pasted dark text on dark blocks, which the light theme can barely show,
and text pasted from a document comes in black, which the dark theme can't show at all. The
paste-colors plugin (static/bytedeck_summernote/plugins/paste-colors/) takes those colors off what
a paste adds, and leaves the rest of the formatting and the colors already in the content.

The announcement form is rendered by the app itself, through the test client, and opened in
headless Chromium with the app's own static files, scripts and stylesheets included, so the
editor runs with the real SUMMERNOTE_CONFIG and plugins. Every other request is refused. The page
is served over https so the clipboard can be written, and the paste is a real Ctrl+V: the browser
inserts the clipboard's HTML itself, as it does for a writer. The tests skip cleanly unless
Playwright and a Chromium build are both available, like the other render tests (e.g.
test_image_align_render.py).
"""

import glob
import os
from unittest import skipUnless
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase
from django.urls import reverse

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover (Playwright is in requirements; this guards an install without it)
    HAS_PLAYWRIGHT = False

User = get_user_model()

#: Where the rendered page pretends to live: https, so the page may write to the clipboard.
PAGE_ORIGIN = "https://deck.test"

PASTE_COLORS_JS = os.path.join(settings.STATIC_URL, 'bytedeck_summernote/plugins/paste-colors/summernote-paste-colors.js')

#: Text copied from a comment shown in the dark theme, as the browser puts it on the clipboard:
#: each paragraph carries the theme's light text and dark background, and the bold its weight.
DARK_THEME_COPY = (
    '<p style="color: rgb(220, 220, 220); background-color: rgb(39, 43, 48);">Copied in the dark theme</p>'
    '<p style="color: rgb(220, 220, 220); background-color: rgb(39, 43, 48);">'
    '<b style="color: rgb(220, 220, 220);">Bold</b> and plain</p>'
)

#: Text from a document or an older page: a font's color attribute, and a table cell's bgcolor.
OLDER_MARKUP_COPY = (
    '<p><font color="#000000">Black text from a document</font></p>'
    '<table><tbody><tr><td bgcolor="#000000">A dark cell</td></tr></tbody></table>'
)


class PasteColorsConfigTest(SimpleTestCase):
    """Both kinds of editor drop the colors pasted content brings."""

    def test_summernote_config__loads_the_paste_colors_plugin(self):
        """Both the iframe widget and the inplace widget load the plugin."""
        self.assertIn(PASTE_COLORS_JS, settings.SUMMERNOTE_CONFIG['js'])
        self.assertIn(PASTE_COLORS_JS, settings.SUMMERNOTE_CONFIG['js_for_inplace'])
        self.assertIsNotNone(finders.find('bytedeck_summernote/plugins/paste-colors/summernote-paste-colors.js'))


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
class PasteColorsRenderTest(ByteDeckTenantTestCase):
    """Pasted content loses the colors it was copied with, and keeps everything else."""

    def setUp(self):
        """Render the announcement form as a teacher sees it, and open it in a headless browser
        that may read and write the page's clipboard.

        Playwright's sync API runs an event loop, and Django refuses database access while one
        is running, so the browser starts only once the page is rendered, and is stopped by a
        cleanup, which runs before the test's transaction is rolled back.
        """
        teacher = User.objects.create_user('paste_colors_teacher', is_staff=True)
        self.client.force_login(teacher)
        response = self.client.get(reverse('announcements:create'))
        self.assertEqual(response.status_code, 200)
        self.html = response.content.decode()

        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        browser = playwright.chromium.launch(executable_path=_CHROMIUM)
        self.addCleanup(browser.close)
        context = browser.new_context()
        context.grant_permissions(["clipboard-read", "clipboard-write"], origin=PAGE_ORIGIN)
        self.page = context.new_page()
        self.page.route("**/*", self._serve)
        self.page.goto(f"{PAGE_ORIGIN}/page/")
        self.page.wait_for_selector('.note-editable')

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

    def _paste(self, html, content='<p>Start</p>'):
        """Fill the editor with `content`, then paste `html` at its end with Ctrl+V.

        Args:
            html (str): the HTML put on the clipboard, as a copy from a page or document puts it.
            content (str): what the editor holds before the paste.

        Returns:
            str: the editor's content once the paste has settled, as the form will save it.
        """
        self.page.evaluate("content => $('#id_content').summernote('code', content)", content)
        self.page.evaluate(
            """async html => {
                const text = new DOMParser().parseFromString(html, 'text/html').body.textContent;
                await navigator.clipboard.write([new ClipboardItem({
                    'text/html': new Blob([html], {type: 'text/html'}),
                    'text/plain': new Blob([text], {type: 'text/plain'}),
                })]);
            }""",
            html,
        )
        self.page.locator('.note-editable p').last.click()
        self.page.keyboard.press('End')
        self.page.keyboard.press('Control+V')
        self.page.wait_for_timeout(300)
        return self.page.evaluate("() => $('#id_content').summernote('code')")

    def test_paste__drops_the_colors_copied_from_the_dark_theme(self):
        """Text copied in the dark theme pastes without its light text and dark background.

        Those are the colors a copy carries from the page it was copied off, and the light
        theme shows them as dark blocks of dark text.
        """
        saved = self._paste(DARK_THEME_COPY)

        self.assertIn('Copied in the dark theme', saved)
        self.assertNotIn('background-color', saved)
        self.assertNotIn('color:', saved)

    def test_paste__keeps_the_rest_of_the_pasted_formatting(self):
        """Only the colors go: the pasted bold is still bold."""
        saved = self._paste(DARK_THEME_COPY)

        bold = self.page.evaluate(
            """() => Array.from(document.querySelectorAll('.note-editable *'))
                .some(el => el.textContent === 'Bold' && getComputedStyle(el).fontWeight >= 600)"""
        )
        self.assertTrue(bold, saved)

    def test_paste__drops_older_markup_colors(self):
        """A font's color attribute and a table cell's bgcolor, as a document pastes them, go too."""
        saved = self._paste(OLDER_MARKUP_COPY)

        self.assertIn('Black text from a document', saved)
        self.assertIn('A dark cell', saved)
        self.assertNotIn('bgcolor', saved)
        self.assertNotIn('color=', saved)
        self.assertNotIn('color:', saved)

    def test_paste__keeps_colors_already_in_the_content(self):
        """Colors the content had before the paste stay: only what the paste adds is cleaned.

        A color already there was chosen with the toolbar's color button, or survived an earlier
        paste the writer then colored on purpose.
        """
        saved = self._paste(
            DARK_THEME_COPY,
            content='<p><span style="color: rgb(255, 0, 0);">Red on purpose</span></p><p>Start</p>',
        )

        self.assertIn('<span style="color: rgb(255, 0, 0);">Red on purpose</span>', saved)
        self.assertNotIn('background-color', saved)
