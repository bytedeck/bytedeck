"""Tests for linking an image in the editor, the link wrapping the image itself (#2909).

Summernote's Insert Link dialog builds its link from the selected text, so with an image selected the
link used to come out as new text beside the image. js/summernote-image-link.js links the selected
image instead, from the toolbar's Link button and from Link in the image's menu, and opens the same
dialog on the image's own link to edit. The image's menu shows a linked image's URL and has Unlink.

The announcement form is rendered by the app itself, through the test client, and opened in
headless Chromium with the app's own static files, scripts included, so the editor runs with the
real SUMMERNOTE_CONFIG and plugins. Every other request is refused. The tests skip cleanly unless
Playwright and a Chromium build are both available, like the other render tests (e.g.
test_image_source_render.py).
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

#: Where the rendered page pretends to live, so its root-relative links resolve.
PAGE_ORIGIN = "http://deck.test"

#: The image the tests link.
IMAGE = '<img src="/static/img/banner.png" style="width: 200px;">'

IMAGE_LINK_JS = os.path.join(settings.STATIC_URL, 'js/summernote-image-link.js')


class ImageLinkConfigTest(SimpleTestCase):
    """The image's Link and Unlink buttons are in its menu in both kinds of editor."""

    def test_summernote_config__loads_the_image_link_plugin(self):
        """Both the iframe widget and the inplace widget load the plugin."""
        self.assertIn(IMAGE_LINK_JS, settings.SUMMERNOTE_CONFIG['js'])
        self.assertIn(IMAGE_LINK_JS, settings.SUMMERNOTE_CONFIG['js_for_inplace'])
        self.assertIsNotNone(finders.find('js/summernote-image-link.js'))

    def test_summernote_config__image_menu_has_link_and_unlink(self):
        """The image's menu has Link and Unlink."""
        groups = dict(settings.SUMMERNOTE_CONFIG['summernote']['popover']['image'])
        self.assertEqual(groups['imagelink'], ['imageLink', 'imageUnlink'])


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
class ImageLinkRenderTest(ByteDeckTenantTestCase):
    """An image is linked with the link wrapping it, from the toolbar or from the image's menu."""

    def setUp(self):
        """Render the announcement form as a teacher sees it, and open it in a headless browser.

        Playwright's sync API runs an event loop, and Django refuses database access while one
        is running, so the browser starts only once the page is rendered, and is stopped by a
        cleanup, which runs before the test's transaction is rolled back.
        """
        teacher = User.objects.create_user('image_link_teacher', is_staff=True)
        self.client.force_login(teacher)
        response = self.client.get(reverse('announcements:create'))
        self.assertEqual(response.status_code, 200)
        self.html = response.content.decode()

        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        browser = playwright.chromium.launch(executable_path=_CHROMIUM)
        self.addCleanup(browser.close)
        self.page = browser.new_page()
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

    def _write(self, middle):
        """Fill the editor with a paragraph, `middle` in a paragraph of its own, and another paragraph.

        Args:
            middle (str): the HTML in the middle paragraph.
        """
        self.page.evaluate(
            "middle => $('#id_content').summernote('code', '<p>Before</p><p>' + middle + '</p><p>After</p>')",
            middle,
        )

    def _select_image(self):
        """Click the image, so the editor selects it and opens its menu.

        A click on the last paragraph first closes an image menu left open by an earlier click.
        """
        self.page.locator('.note-editable p').last.click()
        self.page.locator('.note-editable img').click()
        self.page.locator('.note-image-popover').wait_for(state='visible')

    def _menu_button(self, label):
        """The button in the image's menu with the label `label`."""
        return self.page.locator(f'.note-image-popover button[aria-label="{label}"]')

    def _wait_for_link_dialog(self):
        """Wait for the Insert Link dialog to finish opening, when it puts the focus in its URL field.

        Returns:
            playwright.sync_api.Locator: the dialog's URL field.
        """
        self.page.wait_for_function("() => document.activeElement.classList.contains('note-link-url')")
        return self.page.locator('.note-link-url')

    def _editor_html(self):
        """The editor's content, as the form's field holds it."""
        return self.page.locator('#id_content').input_value()

    def test_image_link__toolbar_link_wraps_the_selected_image(self):
        """With an image selected, the toolbar's Link button links the image: the link wraps it,
        no text is added, and "Text to display" isn't asked for. The URL starts out empty, not as
        the image's own file, and a URL without a protocol gets the default one, as a text link's
        does."""
        self._write(IMAGE)
        self._select_image()

        self.page.locator('.note-toolbar button:has(.note-icon-link)').click()
        url = self._wait_for_link_dialog()
        self.assertFalse(self.page.locator('.note-link-text').is_visible())
        self.assertEqual(url.input_value(), '')
        url.fill('example.com/map')
        self.page.locator('.note-link-btn').click()

        link = self.page.locator('.note-editable a:has(img)')
        self.assertEqual(link.get_attribute('href'), 'http://example.com/map')
        self.assertEqual(link.inner_text().strip(), '')
        self.assertEqual(self.page.locator('.note-editable').inner_text().split(), ['Before', 'After'])
        self.assertIn('<a href="http://example.com/map"', self._editor_html())

    def test_image_link__menu_link_wraps_the_image(self):
        """Link in the image's menu links the image the same way."""
        self._write(IMAGE)
        self._select_image()

        self._menu_button('Link').click()
        self._wait_for_link_dialog().fill('https://example.com/map')
        self.page.locator('.note-link-btn').click()

        self.assertEqual(self.page.locator('.note-editable a:has(img)').get_attribute('href'), 'https://example.com/map')

    def test_image_link__edits_the_link_the_image_is_in(self):
        """On a linked image, the image's menu shows the link, and the dialog opens on its URL and
        "Open in new window" to edit; the image keeps the one link."""
        self._write(f'<a href="https://old.example.com/" target="_blank">{IMAGE}</a>')
        self._select_image()
        self.assertEqual(self.page.locator('.note-image-popover .note-image-link a').inner_text(), 'https://old.example.com/')

        self._menu_button('Link').click()
        url = self._wait_for_link_dialog()
        self.assertEqual(url.input_value(), 'https://old.example.com/')
        self.assertTrue(self.page.locator('.sn-checkbox-open-in-new-window input').is_checked())
        self.page.locator('.sn-checkbox-open-in-new-window input').uncheck()
        url.fill('https://new.example.com/')
        self.page.locator('.note-link-btn').click()

        self.assertEqual(self.page.locator('.note-editable a').count(), 1)
        link = self.page.locator('.note-editable a:has(img)')
        self.assertEqual(link.get_attribute('href'), 'https://new.example.com/')
        self.assertIsNone(link.get_attribute('target'))

    def test_image_link__script_links_are_not_made(self):
        """A javascript: or data: URL doesn't link the image, so neither the content nor the image's
        menu holds a link that runs script."""
        for url in ('javascript:alert(1)', 'DATA:text/html,<script>alert(1)</script>'):
            with self.subTest(url=url):
                self._write(IMAGE)
                self._select_image()
                self._menu_button('Link').click()
                self._wait_for_link_dialog().fill(url)
                self.page.locator('.note-link-btn').click()

                self.assertEqual(self.page.locator('.note-editable a').count(), 0)

    def test_image_link__unlink_takes_the_image_out_of_its_link(self):
        """Unlink in the image's menu takes the image out of its link and keeps the image."""
        self._write(f'<a href="https://example.com/">{IMAGE}</a>')
        self._select_image()

        self._menu_button('Unlink').click()

        self.assertEqual(self.page.locator('.note-editable a').count(), 0)
        self.assertEqual(self.page.locator('.note-editable img').count(), 1)
        self.assertNotIn('<a', self._editor_html())

    def test_image_link__unlink_is_off_and_no_link_shows_for_an_unlinked_image(self):
        """An image with no link shows no link in its menu, and its Unlink is disabled."""
        self._write(IMAGE)
        self._select_image()

        self.assertFalse(self.page.locator('.note-image-popover .note-image-link').is_visible())
        self.assertTrue(self._menu_button('Unlink').is_disabled())

    def test_image_link__link_popover_stays_away_from_the_image_menu(self):
        """Summernote's own link popover, open for a text link the caret is in, closes as an image
        is selected, so the image's menu is the one menu showing."""
        self._write(f'<a href="https://example.com/">{IMAGE}</a> <a href="https://text.example.com/">words</a>')
        self.page.locator('.note-editable a', has_text='words').click()
        self.page.locator('.note-link-popover').wait_for(state='visible')

        self.page.locator('.note-editable img').click()
        self.page.locator('.note-image-popover').wait_for(state='visible')
        self.page.wait_for_timeout(200)

        self.assertFalse(self.page.locator('.note-link-popover').is_visible())

    def test_image_link__text_links_are_made_as_before(self):
        """With text selected rather than an image, the toolbar's Link button is Summernote's own:
        it asks for the text to display, and links the text."""
        self._write('<span id="words">some words</span>')
        self.page.locator('.note-editable p').first.click()
        # The editor keeps its own copy of the selection, taken on a key or mouse release, so a
        # keyup follows the selection set here, as it would follow one made with the keyboard.
        self.page.evaluate("""() => {
            const range = document.createRange();
            range.selectNodeContents(document.getElementById('words'));
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
            $('.note-editable').trigger('keyup');
        }""")

        self.page.locator('.note-toolbar button:has(.note-icon-link)').click()
        self._wait_for_link_dialog().fill('https://example.com/')
        self.assertTrue(self.page.locator('.note-link-text').is_visible())
        self.assertEqual(self.page.locator('.note-link-text').input_value(), 'some words')
        self.page.locator('.note-link-btn').click()

        self.assertEqual(self.page.locator('.note-editable a').inner_text(), 'some words')
