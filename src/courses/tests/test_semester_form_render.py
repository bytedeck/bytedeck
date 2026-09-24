"""Headless render test: a row added to the semester form's excluded dates starts no picker itself (#2654).

django-bootstrap-datepicker-plus attaches a date picker to every date input added to the page,
from a MutationObserver, on the input's ``.dbdp`` wrapper. A second picker started on the input
by the form's own ``AddForm()`` opens on top of the widget's: pressing the new row's calendar
icon shows two calendars, one over the other.

The form is rendered by the app through the test client and opened in headless Chromium with
the real vendored jQuery. The picker's plugin comes from a CDN, which the test refuses like every
other outside request, so ``$.fn.datetimepicker`` is replaced with a spy that records whatever it
is started on. It skips cleanly unless Playwright and a Chromium build are both available, like
the other render tests (e.g. djcytoscape/tests/test_map_layout_render.py).
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
from siteconfig.models import SiteConfig

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover (Playwright is in requirements; this guards an install without it)
    HAS_PLAYWRIGHT = False

User = get_user_model()

#: Where the rendered page pretends to live, so its root-relative /static/ links resolve.
PAGE_URL = "http://deck.test/page/"


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


def _serve(route, request, html):
    """Answer the browser's requests: the page itself, and static files from disk.

    Everything else, the date picker's CDN included, is refused, so nothing reaches out of the
    test.
    """
    path = urlparse(request.url).path
    if request.url == PAGE_URL:
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
        return
    if path.startswith(settings.STATIC_URL):
        found = finders.find(path[len(settings.STATIC_URL):])
        if found:
            route.fulfill(path=found)
            return
    route.abort()


@skipUnless(HAS_PLAYWRIGHT and _CHROMIUM, "Playwright and a Chromium build are required")
class SemesterFormAddRowRenderTest(ByteDeckTenantTestCase):
    """What pressing "+" on the semester form's excluded dates does in a browser (#2654)."""

    def test_add_form__leaves_the_new_rows_picker_to_the_widget(self):
        """AddForm() adds a row with a date input and starts no date picker of its own.

        The widget's observer already gives the new input its picker; one started here as well
        opens a second calendar over the first.
        """
        teacher = User.objects.create_user('picker_teacher', is_staff=True)
        self.client.force_login(teacher)
        response = self.client.get(reverse('courses:semester_update', args=[SiteConfig.get().active_semester.pk]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        # Playwright runs only after the page is rendered, so no database work happens inside it.
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=_CHROMIUM)
            page = browser.new_page()
            page.route("**/*", lambda route, request: _serve(route, request, html))
            page.goto(PAGE_URL)
            result = page.evaluate("""() => {
                window.pickerStartedOn = [];
                $.fn.datetimepicker = function () {
                    window.pickerStartedOn.push(this.attr('id') || this.attr('class'));
                    return this;
                };
                const before = document.querySelectorAll('input[data-dbdp-config][id^="id_form-"]').length;
                AddForm();
                const inputs = document.querySelectorAll('input[data-dbdp-config][id^="id_form-"]');
                return {added: inputs.length - before, newInput: inputs[inputs.length - 1].id,
                        pickerStartedOn: window.pickerStartedOn};
            }""")
            browser.close()

        # the row really was added, so the empty list below is about AddForm and not a no-op
        self.assertEqual(result['added'], 1)
        self.assertRegex(result['newInput'], r'^id_form-\d+-date$')
        self.assertEqual(result['pickerStartedOn'], [])
