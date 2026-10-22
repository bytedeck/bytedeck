"""Tests for the editor's Edit image button, which changes the picture an image shows (#2907) and
its description (#2911).

The button sits in the menu over a clicked image (js/summernote-image-source.js). Its dialog shows
the image's URL to edit, or takes a new file, which goes up through the editor's own image upload
(uploadImages in bytedeck_summernote/widget_common.html), and shows its description (alt text) to
edit. Only the image's src and alt change, so its size, float, shapes and other attributes stay. A
height left by dragging the image's corner goes with a new picture, so a picture of a different
shape keeps its proportions.

The announcement form is rendered by the app itself, through the test client, and opened in
headless Chromium with the app's own static files, scripts included, so the editor runs with the
real SUMMERNOTE_CONFIG and plugins. An image upload is answered the way each test sets, as the
upload view would answer it, and every other request is refused. The tests skip cleanly unless
Playwright and a Chromium build are both available, like the other render tests (e.g.
test_image_shapes_render.py).
"""

import glob
import json
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

#: The image's URL before it is changed, and the one it is changed to.
OLD_URL = "/static/img/banner.png"
NEW_URL = "/static/img/icon.png"

IMAGE_SOURCE_JS = os.path.join(settings.STATIC_URL, 'js/summernote-image-source.js')


class ImageSourceConfigTest(SimpleTestCase):
    """The Edit image button is in the image's menu in both kinds of editor."""

    def test_summernote_config__loads_the_image_source_plugin(self):
        """Both the iframe widget and the inplace widget load the plugin."""
        self.assertIn(IMAGE_SOURCE_JS, settings.SUMMERNOTE_CONFIG['js'])
        self.assertIn(IMAGE_SOURCE_JS, settings.SUMMERNOTE_CONFIG['js_for_inplace'])
        self.assertIsNotNone(finders.find('js/summernote-image-source.js'))

    def test_summernote_config__image_menu_has_the_edit_image_button(self):
        """The image's menu shows the button, beside Image Shapes."""
        groups = dict(settings.SUMMERNOTE_CONFIG['summernote']['popover']['image'])
        self.assertEqual(groups['custom'], ['imageShapes', 'imageSource'])


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
class ImageSourceRenderTest(ByteDeckTenantTestCase):
    """The Edit image button changes the picture an image shows and its description, and nothing else about it."""

    def setUp(self):
        """Render the announcement form as a teacher sees it, and open it in a headless browser.

        Playwright's sync API runs an event loop, and Django refuses database access while one
        is running, so the browser starts only once the page is rendered, and is stopped by a
        cleanup, which runs before the test's transaction is rolled back.
        """
        teacher = User.objects.create_user('image_source_teacher', is_staff=True)
        self.client.force_login(teacher)
        response = self.client.get(reverse('announcements:create'))
        self.assertEqual(response.status_code, 200)
        self.html = response.content.decode()
        self.upload_path = reverse('bytedeck_summernote-upload_attachment')
        self.upload_reply = (200, {"files": [{"url": NEW_URL}]})
        self.uploads = 0
        # a list here holds the uploads unanswered, for a test to answer when it chooses
        self.held_uploads = None

        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        browser = playwright.chromium.launch(executable_path=_CHROMIUM)
        self.addCleanup(browser.close)
        self.page = browser.new_page()
        self.alerts = []
        self.page.on('dialog', self._alert)
        self.page.route("**/*", self._serve)
        self.page.goto(f"{PAGE_ORIGIN}/page/")
        self.page.wait_for_selector('.note-editable')

    def _serve(self, route, request):
        """Answer the page's requests: the page, an image upload with upload_reply, and the static
        files from disk. Anything else is refused.

        Args:
            route (playwright.sync_api.Route): the intercepted request's route, answered here.
            request (playwright.sync_api.Request): the request it intercepted.
        """
        path = urlparse(request.url).path
        if path == "/page/":
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        elif path == self.upload_path and request.method == 'POST':
            self.uploads += 1
            if self.held_uploads is not None:
                self.held_uploads.append(route)
                return
            status, body = self.upload_reply
            route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
        elif path.startswith(settings.STATIC_URL) and finders.find(path[len(settings.STATIC_URL):]):
            route.fulfill(path=finders.find(path[len(settings.STATIC_URL):]))
        else:
            route.abort()

    def _alert(self, dialog):
        """Note the text of an alert the page shows, and close it."""
        self.alerts.append(dialog.message)
        dialog.accept()

    def _write(self, image):
        """Fill the editor with a paragraph, `image`, and another paragraph.

        Args:
            image (str): the image's HTML.
        """
        self.page.evaluate(
            "image => $('#id_content').summernote('code', '<p>Before</p><p>' + image + '</p><p>After</p>')",
            image,
        )

    def _image(self, name):
        """Return one of the editor's image's attributes, or a property of its inline style.

        Args:
            name (str): an attribute, e.g. 'src', or 'style.<property>'.

        Returns:
            str: its value, None for an attribute it doesn't have.
        """
        image = self.page.locator('.note-editable img')
        if name.startswith('style.'):
            return image.evaluate("(img, property) => img.style[property]", name[len('style.'):])
        return image.get_attribute(name)

    def _open_dialog(self):
        """Click the image and press Edit image in its menu, then wait for the dialog to be shown.

        A click on the last paragraph first closes an image menu left open by an earlier click.
        The dialog fills its URL field and puts the focus there once it has finished opening, so
        that is what is waited for.

        Returns:
            playwright.sync_api.Locator: the dialog's URL field.
        """
        self.page.locator('.note-editable p').last.click()
        self.page.locator('.note-editable img').click()
        self.page.locator('.note-image-popover button[aria-label="Edit image"]').click()
        self.page.wait_for_function("() => document.activeElement.classList.contains('note-image-source-url')")
        return self.page.locator('.note-image-source-url')

    def _dialog_is_open(self):
        """Whether the Edit Image dialog is showing."""
        return self.page.locator('.modal:has(.note-image-source-url)').is_visible()

    def test_image_source__dialog_shows_the_images_url(self):
        """The dialog opens on the URL the image has now, ready to edit."""
        self._write(f'<img src="{OLD_URL}" style="width: 200px;">')

        self.assertEqual(self._open_dialog().input_value(), OLD_URL)

    def test_image_source__changes_the_src_and_keeps_the_rest(self):
        """A new URL changes the image's src, and its classes, alt text, size and float stay as they
        were, in the editor and in the form's field."""
        self._write(f'<img class="img-responsive img-rounded" src="{OLD_URL}" alt="The map" style="width: 200px; float: left;">')

        self._open_dialog().fill(NEW_URL)
        self.page.locator('.note-image-source-btn').click()

        self.assertEqual(self._image('src'), NEW_URL)
        self.assertEqual(self._image('class'), 'img-responsive img-rounded')
        self.assertEqual(self._image('alt'), 'The map')
        self.assertEqual(self._image('style.width'), '200px')
        self.assertEqual(self._image('style.float'), 'left')
        self.page.wait_for_function("() => !$('.modal:has(.note-image-source-url)').is(':visible')")
        self.assertIn(NEW_URL, self.page.locator('#id_content').input_value())

    def test_image_source__enter_changes_the_image(self):
        """Pressing Enter in the URL field changes the image, as the button does."""
        self._write(f'<img src="{OLD_URL}">')

        self._open_dialog().fill(NEW_URL)
        self.page.keyboard.press('Enter')

        self.assertEqual(self._image('src'), NEW_URL)

    def test_image_source__new_picture_keeps_its_proportions(self):
        """A height left by dragging the image's corner goes, so the new picture keeps its own
        proportions at the image's width."""
        self._write(f'<img src="{OLD_URL}" style="width: 200px; height: 50px;">')

        self._open_dialog().fill(NEW_URL)
        self.page.locator('.note-image-source-btn').click()

        self.assertEqual(self._image('style.width'), '200px')
        self.assertEqual(self._image('style.height'), '')

    def test_image_source__an_empty_url_cannot_be_set(self):
        """With the URL field emptied, the Save button is disabled."""
        self._write(f'<img src="{OLD_URL}">')

        self._open_dialog().fill('')

        self.assertTrue(self.page.locator('.note-image-source-btn').is_disabled())

    def test_image_source__uploads_a_new_picture(self):
        """A file chosen in the dialog is uploaded through the editor's own upload, and the image
        shows the uploaded picture, keeping the rest of itself."""
        self._write(f'<img class="img-thumbnail" src="{OLD_URL}" style="width: 200px;">')

        self._open_dialog()
        self.page.locator('.note-image-source-file').set_input_files(finders.find('img/icon.png'))

        self.page.wait_for_function(f"() => $('.note-editable img').attr('src') === '{NEW_URL}'")
        self.assertEqual(self.uploads, 1)
        self.assertEqual(self._image('class'), 'img-thumbnail')
        self.assertEqual(self._image('style.width'), '200px')
        self.page.wait_for_function("() => !$('.modal:has(.note-image-source-url)').is(':visible')")
        self.assertEqual(self.page.locator('.note-image-source-file').input_value(), '')

    def test_image_source__a_failed_upload_leaves_the_image_as_it_was(self):
        """When the upload fails, the writer is told why, the image keeps its picture, and the
        dialog stays open to try again, with the file input emptied so that choosing the same file
        again counts as a new choice."""
        self.upload_reply = (400, {"message": "That file is too large."})
        self._write(f'<img src="{OLD_URL}">')

        self._open_dialog()
        with self.page.expect_event('dialog'):
            self.page.locator('.note-image-source-file').set_input_files(finders.find('img/icon.png'))

        self.assertEqual(self.alerts, ["That file is too large."])
        self.assertEqual(self._image('src'), OLD_URL)
        self.assertTrue(self._dialog_is_open())
        self.assertEqual(self.page.locator('.note-image-source-file').input_value(), '')

    def test_image_source__an_upload_given_up_on_changes_nothing(self):
        """An upload still going when the dialog is closed was given up on: when it finishes, the
        image keeps its picture, and the dialog opened again since stays open."""
        self.held_uploads = []
        self._write(f'<img src="{OLD_URL}">')
        self._open_dialog()
        self.page.locator('.note-image-source-file').set_input_files(finders.find('img/icon.png'))
        for _ in range(100):
            if self.held_uploads:
                break
            self.page.wait_for_timeout(50)
        self.assertTrue(self.held_uploads, "The upload never reached the test's server.")

        self.page.locator('.modal:has(.note-image-source-url) .close').click()
        self.page.wait_for_function("() => !$('.modal:has(.note-image-source-url)').is(':visible')")
        self._open_dialog()
        status, body = self.upload_reply
        self.held_uploads[0].fulfill(status=status, content_type="application/json", body=json.dumps(body))
        self.page.wait_for_timeout(500)

        self.assertEqual(self._image('src'), OLD_URL)
        self.assertTrue(self._dialog_is_open())

    def test_image_source__undo_brings_the_old_picture_back(self):
        """Changing the picture is one step the editor can undo."""
        self._write(f'<img src="{OLD_URL}">')
        self._open_dialog().fill(NEW_URL)
        self.page.locator('.note-image-source-btn').click()

        self.page.evaluate("() => $('#id_content').summernote('undo')")

        self.assertEqual(self._image('src'), OLD_URL)

    def test_image_source__dialog_shows_the_images_description(self):
        """The dialog shows the description (alt text) the image has now."""
        self._write(f'<img src="{OLD_URL}" alt="A map of the quests">')

        self._open_dialog()

        self.assertEqual(self.page.locator('.note-image-source-alt').input_value(), 'A map of the quests')

    def test_image_source__sets_the_description_and_keeps_the_picture(self):
        """A description typed in the dialog becomes the image's alt text, and with the URL left as
        it was, the picture and a dragged height stay."""
        self._write(f'<img src="{OLD_URL}" style="width: 200px; height: 50px;">')

        self._open_dialog()
        self.page.locator('.note-image-source-alt').fill('  A map of the quests  ')
        self.page.locator('.note-image-source-btn').click()

        self.assertEqual(self._image('alt'), 'A map of the quests')
        self.assertEqual(self._image('src'), OLD_URL)
        self.assertEqual(self._image('style.height'), '50px')
        self.assertIn('alt="A map of the quests"', self.page.locator('#id_content').input_value())

    def test_image_source__an_emptied_description_leaves_no_alt(self):
        """Emptying the description takes the image's alt off, rather than leaving alt="", which
        would tell a screen reader to skip the image as decoration."""
        self._write(f'<img src="{OLD_URL}" alt="A map of the quests">')

        self._open_dialog()
        self.page.locator('.note-image-source-alt').fill('')
        self.page.keyboard.press('Enter')

        self.assertIsNone(self._image('alt'))

    def test_image_source__an_uploaded_picture_gets_the_description(self):
        """A description typed before choosing a file is given to the uploaded picture."""
        self._write(f'<img src="{OLD_URL}">')

        self._open_dialog()
        self.page.locator('.note-image-source-alt').fill('The new map')
        self.page.locator('.note-image-source-file').set_input_files(finders.find('img/icon.png'))

        self.page.wait_for_function(f"() => $('.note-editable img').attr('src') === '{NEW_URL}'")
        self.assertEqual(self._image('alt'), 'The new map')
