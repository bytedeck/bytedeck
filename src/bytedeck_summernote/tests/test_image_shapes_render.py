"""Headless render tests for the editor's Image Shapes menu, the shapes button over a clicked image.

The menu ticks the shapes the image has, like the toolbar's own menus, and each shape turns on or
off, so an image can have several; None takes them all off. A shape is chosen after Bootstrap has
moved the focus to the menu's button, and Summernote forgets the image it had selected when the
editor loses the focus, so the menu keeps the image it opened for: before that, a shape chosen
after typing in the editor did nothing.

The announcement form is rendered by the app itself, through the test client, and opened in
headless Chromium with the app's own static files, scripts included, so the editor runs with the
real SUMMERNOTE_CONFIG and plugins. Every other request is refused. The tests skip cleanly unless
Playwright and a Chromium build are both available, like the other render tests (e.g.
quest_manager/tests/test_flag_submission_render.py).
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

#: Where the rendered page pretends to live, so its root-relative links resolve.
PAGE_ORIGIN = "http://deck.test"

#: The menu's items, top to bottom.
LABELS = ["Responsive", "Rounded", "Circle", "Thumbnail", "None"]


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
class ImageShapesRenderTest(ByteDeckTenantTestCase):
    """The Image Shapes menu shows and changes the shapes of the image it opened for."""

    def setUp(self):
        """Render the announcement form as a teacher sees it, and open it in a headless browser.

        Playwright's sync API runs an event loop, and Django refuses database access while one
        is running, so the browser starts only once the page is rendered, and is stopped by a
        cleanup, which runs before the test's transaction is rolled back.
        """
        teacher = User.objects.create_user('shapes_teacher', is_staff=True)
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

    def _write(self, image_classes=""):
        """Fill the editor with a paragraph, an image with `image_classes`, and another paragraph."""
        self.page.evaluate(
            """classes => $('#id_content').summernote('code',
                '<p>Before</p><p><img class="' + classes + '" src="/static/img/banner.png" style="width: 200px;"></p><p>After</p>')""",
            image_classes,
        )

    def _image_classes(self):
        """The image's classes, sorted, as a list."""
        return sorted(self.page.locator('.note-editable img').evaluate("img => img.className").split())

    def _open_menu(self):
        """Click the image and open the Image Shapes menu over it.

        A click on the last paragraph first closes an image menu left open by an earlier click:
        Summernote opens it where the mouse was, so its arrow would cover the image.

        Returns:
            list: the labels of the items the menu ticks.
        """
        self.page.locator('.note-editable p').last.click()
        self.page.locator('.note-editable img').click()
        group = self.page.locator('.note-image-popover .note-btn-group:has(.dropdown-shape)')
        group.locator('.dropdown-toggle').click()
        self.page.wait_for_selector('.note-image-popover .dropdown-shape', state='visible')
        return [item.inner_text().strip() for item in group.locator('.dropdown-shape a.checked').all()]

    def _choose(self, label):
        """Open the Image Shapes menu over the image and choose `label`."""
        self._open_menu()
        self.page.locator('.note-image-popover .dropdown-shape a', has_text=label).click()

    def test_image_shapes__menu_lists_the_shapes(self):
        """The menu offers the four shapes and None, in that order."""
        self._write()
        self._open_menu()
        items = self.page.locator('.note-image-popover .dropdown-shape a')
        self.assertEqual([item.inner_text().strip() for item in items.all()], LABELS)

    def test_image_shapes__menu_ticks_the_shapes_the_image_has(self):
        """Every shape the image has is ticked, and only those."""
        self._write("img-rounded img-thumbnail")
        self.assertEqual(self._open_menu(), ["Rounded", "Thumbnail"])

    def test_image_shapes__menu_ticks_none_for_an_image_without_a_shape(self):
        """An image with no shape has None ticked, and nothing else."""
        self._write()
        self.assertEqual(self._open_menu(), ["None"])

    def test_image_shapes__a_shape_turns_on_and_off(self):
        """Choosing a shape adds it beside the ones the image has; choosing it again takes it off,
        and the menu's ticks follow."""
        self._write("img-thumbnail")

        self._choose("Circle")
        self.assertEqual(self._image_classes(), ["img-circle", "img-thumbnail"])
        self.assertEqual(self._open_menu(), ["Circle", "Thumbnail"])
        self.page.keyboard.press("Escape")

        self._choose("Circle")
        self.assertEqual(self._image_classes(), ["img-thumbnail"])

    def test_image_shapes__none_takes_every_shape_off(self):
        """None takes off every shape the image has, and leaves its other classes alone."""
        self._write("img-responsive img-rounded img-circle img-thumbnail note-float-left")

        self._choose("None")

        self.assertEqual(self._image_classes(), ["note-float-left"])

    def test_image_shapes__works_after_typing_in_the_editor(self):
        """A shape chosen after typing in the editor applies. Opening the menu takes the focus
        from the editor, which then forgets its selected image, so before the menu kept the image
        it opened for, nothing happened."""
        self._write("img-rounded")
        self.page.locator('.note-editable p').first.click()
        self.page.keyboard.type(" typed")

        self._choose("None")
        self.assertEqual(self._image_classes(), [])

        self.page.locator('.note-editable p').first.click()
        self._choose("Responsive")
        self.assertEqual(self._image_classes(), ["img-responsive"])
