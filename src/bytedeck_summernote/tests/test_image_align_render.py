"""Tests for aligning an image in the editor on a line of its own, at the left, center or right (#2910).

The float buttons in the image's menu let text wrap around an image. The paragraph's own alignment
can't move a Responsive image, which Bootstrap's img-responsive makes a block, so the image-align
plugin (static/bytedeck_summernote/plugins/image-align/) adds Align left, Align center and Align
right to the image's menu, as classes on the image: Bootstrap's center-block, and img-align-right
from css/custom_common.css.
An image is either aligned or floated, never both. On a phone, a floated image stops floating
and sits on a line of its own, as a floated figure does (#2918).

The announcement form is rendered by the app itself, through the test client, and opened in
headless Chromium with the app's own static files, scripts and stylesheets included, so the
editor runs with the real SUMMERNOTE_CONFIG and plugins. Every other request is refused. The tests
skip cleanly unless Playwright and a Chromium build are both available, like the other render
tests (e.g. test_image_link_render.py).
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

#: A Responsive image, as the editor inserts one, narrower than the editor.
IMAGE = '<img class="img-responsive" src="/static/img/banner.png" style="width: 200px;">'

IMAGE_ALIGN_JS = os.path.join(settings.STATIC_URL, 'bytedeck_summernote/plugins/image-align/summernote-image-align.js')


class ImageAlignConfigTest(SimpleTestCase):
    """The image's alignment buttons are in its menu in both kinds of editor."""

    def test_summernote_config__loads_the_image_align_plugin(self):
        """Both the iframe widget and the inplace widget load the plugin."""
        self.assertIn(IMAGE_ALIGN_JS, settings.SUMMERNOTE_CONFIG['js'])
        self.assertIn(IMAGE_ALIGN_JS, settings.SUMMERNOTE_CONFIG['js_for_inplace'])
        self.assertIsNotNone(finders.find('bytedeck_summernote/plugins/image-align/summernote-image-align.js'))

    def test_summernote_config__image_menu_has_the_alignments(self):
        """The image's menu has Align left, Align center and Align right, after the float buttons."""
        groups = settings.SUMMERNOTE_CONFIG['summernote']['popover']['image']
        names = [name for name, _ in groups]
        self.assertEqual(dict(groups)['imagealign'], ['imageAlignLeft', 'imageAlignCenter', 'imageAlignRight'])
        self.assertEqual(names.index('imagealign'), names.index('float') + 1)


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
class ImageAlignRenderTest(ByteDeckTenantTestCase):
    """An image is placed at the left, center or right of a line of its own, or floated, not both."""

    def setUp(self):
        """Render the announcement form as a teacher sees it, and open it in a headless browser.

        Playwright's sync API runs an event loop, and Django refuses database access while one
        is running, so the browser starts only once the page is rendered, and is stopped by a
        cleanup, which runs before the test's transaction is rolled back.
        """
        teacher = User.objects.create_user('image_align_teacher', is_staff=True)
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

    def _write(self, image):
        """Fill the editor with a paragraph, the image in a paragraph of its own, and another paragraph.

        Args:
            image (str): the image's HTML.
        """
        self.page.evaluate(
            "image => $('#id_content').summernote('code', '<p>Before</p><p>' + image + '</p><p>After</p>')",
            image,
        )

    def _select_image(self):
        """Click the image, so the editor selects it and opens its menu.

        A click on the last paragraph first closes an image menu left open by an earlier click.
        """
        self.page.locator('.note-editable p').last.click()
        self.page.locator('.note-editable img').click()
        self.page.locator('.note-image-popover').wait_for(state='visible')

    def _press(self, label):
        """Press the button in the image's menu with the label `label`."""
        self.page.locator(f'.note-image-popover button[aria-label="{label}"]').click()

    def _image(self):
        """The image's class, its float, and where it sits in its paragraph.

        Returns:
            dict: `classes` (a set), `float` (its inline float, '' for none), and `left` and
            `right`, the space between the image and its paragraph's edges, in pixels.
        """
        return self.page.evaluate("""() => {
            const img = document.querySelector('.note-editable img');
            const box = img.getBoundingClientRect(), line = img.parentElement.getBoundingClientRect();
            return {
                classes: img.className.split(/\\s+/).filter(Boolean),
                float: img.style.float,
                left: Math.round(box.left - line.left),
                right: Math.round(line.right - box.right),
            };
        }""")

    def _editor_html(self):
        """The editor's content, as the form's field holds it."""
        return self.page.locator('#id_content').input_value()

    def test_image_align__center_centers_a_responsive_image(self):
        """Align center centers a Responsive image on its line, with Bootstrap's center-block,
        in the editor and in the form's field."""
        self._write(IMAGE)
        self._select_image()

        self._press('Align center')

        image = self._image()
        self.assertIn('center-block', image['classes'])
        self.assertIn('img-responsive', image['classes'])
        self.assertGreater(image['left'], 0)
        self.assertLessEqual(abs(image['left'] - image['right']), 1)
        self.assertIn('center-block', self._editor_html())

    def test_image_align__right_puts_a_responsive_image_at_the_right(self):
        """Align right puts a Responsive image at the right of its line, with img-align-right."""
        self._write(IMAGE)
        self._select_image()

        self._press('Align right')

        image = self._image()
        self.assertIn('img-align-right', image['classes'])
        self.assertGreater(image['left'], 0)
        self.assertEqual(image['right'], 0)

    def test_image_align__left_takes_the_alignment_off(self):
        """Align left takes a center or right alignment off, so the image is back at the left."""
        self._write(IMAGE.replace('img-responsive', 'img-responsive center-block'))
        self._select_image()

        self._press('Align left')

        image = self._image()
        self.assertEqual(image['classes'], ['img-responsive'])
        self.assertEqual(image['left'], 0)

    def test_image_align__alignment_takes_the_float_off(self):
        """Aligning a floated image takes its float off, and the alignment replaces another."""
        self._write(IMAGE.replace('img-responsive', 'img-responsive img-align-right note-float-left').replace(
            'width: 200px;', 'width: 200px; float: left;'))
        self._select_image()

        self._press('Align center')

        image = self._image()
        self.assertEqual(sorted(image['classes']), ['center-block', 'img-responsive'])
        self.assertEqual(image['float'], '')

    def test_image_align__float_takes_the_alignment_off(self):
        """Floating an aligned image takes its alignment off, so it floats as Summernote's own
        float buttons float it."""
        self._write(IMAGE.replace('img-responsive', 'img-responsive center-block'))
        self._select_image()

        self._press('Float Right')

        image = self._image()
        self.assertEqual(sorted(image['classes']), ['img-responsive', 'note-float-right'])
        self.assertEqual(image['float'], 'right')
        self.assertEqual(image['right'], 0)

    def test_image_align__remove_float_leaves_the_alignment(self):
        """Remove float takes a float off and leaves an alignment as it is."""
        self._write(IMAGE.replace('img-responsive', 'img-responsive center-block'))
        self._select_image()

        self._press('Remove float')

        image = self._image()
        self.assertEqual(sorted(image['classes']), ['center-block', 'img-responsive'])
        self.assertEqual(image['float'], '')

    def test_image_align__undo_brings_the_float_back(self):
        """An alignment is one step the editor can undo, back to the image as it was."""
        self._write(IMAGE.replace('img-responsive', 'img-responsive note-float-left').replace(
            'width: 200px;', 'width: 200px; float: left;'))
        self._select_image()
        self._press('Align right')

        self.page.evaluate("() => $('#id_content').summernote('undo')")

        image = self._image()
        self.assertEqual(sorted(image['classes']), ['img-responsive', 'note-float-left'])
        self.assertEqual(image['float'], 'left')

    def _float_layout(self):
        """Where a floated image and the text after it sit, once the image has loaded.

        Returns:
            dict: `float`, the image's float as the page's stylesheets leave it, and `beside`,
            whether the text's first line starts beside the image rather than below it.
        """
        self.page.wait_for_function("() => document.querySelector('.note-editable img').complete")
        return self.page.evaluate("""() => {
            const img = document.querySelector('.note-editable img').getBoundingClientRect();
            const words = document.getElementById('words').getClientRects()[0];
            return {float: getComputedStyle(document.querySelector('.note-editable img')).float,
                    beside: words.top < img.bottom - 1};
        }""")

    def test_image_float__phones_put_a_floated_image_on_its_own_line(self):
        """On a phone, a floated image stops floating and the text goes below it, rather than into
        a column too narrow to read beside it; on a wider screen it floats with the text beside it
        (#2918). Bootstrap's pull-left and pull-right, which older content has, are treated the same."""
        words = 'The quest map shows every campaign as a column. ' * 6
        for classes, side in (('note-float-right', 'right'), ('note-float-left', 'left'),
                              ('pull-right', 'right'), ('pull-left', 'left')):
            image = f'<img class="img-responsive {classes}" src="/static/img/banner.png" style="width: 150px; float: {side};">'
            for width, floats in ((1000, True), (390, False)):
                with self.subTest(classes=classes, width=width):
                    self.page.set_viewport_size({'width': width, 'height': 900})
                    self.page.evaluate("html => $('#id_content').summernote('code', html)",
                                       f'<p>{image}<span id="words">{words}</span></p>')

                    layout = self._float_layout()

                    self.assertEqual(layout['float'], side if floats else 'none')
                    self.assertEqual(layout['beside'], floats)
