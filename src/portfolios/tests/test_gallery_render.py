"""Headless render test: an artwork's caption reaches the portfolio lightbox as text, not markup (#2518).

The public portfolio page opens each artwork in lightGallery, which injects the artwork's caption
into the page with jQuery's ``.html()``. A caption kept in the gallery link's ``data-sub-html``
attribute is decoded on the way out of the attribute, so the escaping Django applied is gone
by the time it is injected, and a student's title or description runs as HTML for anyone who
opens their artwork, signed in or not.

The page is rendered by the app through the test client and opened in headless Chromium with the
real vendored jQuery, lightGallery and justifiedGallery. Static files and the artwork's upload are
served from disk and every other request is refused, so the test is hermetic. It skips cleanly
unless Playwright and a Chromium build are both available, like the other render tests (e.g.
djcytoscape/tests/test_map_layout_render.py).
"""

import glob
import os
import shutil
import tempfile
from unittest import skipUnless
from urllib.parse import unquote, urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import override_settings
from django.urls import reverse
from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from portfolios.models import Artwork
from portfolios.tests.test_views import generate_test_png_file

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover (Playwright is in requirements; this guards an install without it)
    HAS_PLAYWRIGHT = False

User = get_user_model()

#: Where the rendered page pretends to live, so its root-relative links resolve.
PAGE_ORIGIN = "http://deck.test"

#: Markup that marks the page if it runs: a broken image whose error handler sets a flag.
TITLE_PAYLOAD = '<img src=x onerror="document.body.dataset.t=1">'
DESCRIPTION_PAYLOAD = '<img src=y onerror="document.body.dataset.d=1">'


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
class PortfolioGalleryCaptionRenderTest(ByteDeckTenantTestCase):
    """What the lightbox shows for an artwork whose title and description hold markup (#2518)."""

    @classmethod
    def setUpClass(cls):
        """Keep the artwork's upload in a throwaway MEDIA_ROOT, out of the project's own."""
        cls._temp_media = tempfile.mkdtemp(prefix='test-media-portfolio-gallery-')
        cls._media_override = override_settings(MEDIA_ROOT=cls._temp_media)
        cls._media_override.enable()
        cls.addClassCleanup(cls._media_override.disable)
        cls.addClassCleanup(shutil.rmtree, cls._temp_media, ignore_errors=True)
        super().setUpClass()

    def _serve(self, route, request, html, page_url):
        """Answer the browser's requests: the page, static files, and uploads from disk.

        Everything else is refused, so nothing reaches out of the test.
        """
        path = unquote(urlparse(request.url).path)
        found = None
        if request.url == page_url:
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            return
        if path.startswith(settings.STATIC_URL):
            found = finders.find(path[len(settings.STATIC_URL):])
        elif path.startswith(settings.MEDIA_URL):
            candidate = os.path.join(settings.MEDIA_ROOT, path[len(settings.MEDIA_URL):])
            found = candidate if os.path.isfile(candidate) else None
        if found:
            route.fulfill(path=found)
        else:
            route.abort()

    def test_public__the_lightbox_shows_an_artworks_caption_as_text(self):
        """Opening an artwork on the public page runs none of its title or description, and the
        caption shows them as the student typed them."""
        portfolio = baker.make('portfolios.Portfolio', user=baker.make(User))
        baker.make(
            Artwork, portfolio=portfolio, title=TITLE_PAYLOAD, description=DESCRIPTION_PAYLOAD,
            image_file=generate_test_png_file(),
        )
        path = reverse('portfolios:public', args=[portfolio.uuid])
        html = self.client.get(path).content.decode()
        page_url = PAGE_ORIGIN + path

        # Playwright runs only after the page is rendered, so no database work happens inside it.
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=_CHROMIUM)
            page = browser.new_page()
            page.route("**/*", lambda route, request: self._serve(route, request, html, page_url))
            page.goto(page_url)
            # the gallery is laid out first, and the lightbox attached once that completes
            page.wait_for_function("() => !!$('#gallery').data('lightGallery')", timeout=15000)
            # clicked from script: the test's one-pixel image leaves too small a thumbnail for a
            # pointer click to land on, and lightGallery only listens for the click itself
            page.evaluate("() => document.querySelector('#gallery > a').click()")
            page.wait_for_selector('.lg-sub-html h4', state='attached', timeout=15000)
            page.wait_for_timeout(300)  # time for an injected image to fail and fire its handler
            result = page.evaluate("""() => ({
                ran: [document.body.dataset.t, document.body.dataset.d],
                title: document.querySelector('.lg-sub-html h4').textContent,
                description: document.querySelector('.lg-sub-html p').textContent,
            })""")
            browser.close()

        self.assertEqual(result['ran'], [None, None])
        self.assertEqual(result['title'], TITLE_PAYLOAD)
        self.assertEqual(result['description'], DESCRIPTION_PAYLOAD)
