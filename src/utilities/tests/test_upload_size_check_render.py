"""Headless render tests for the browser's check of a file's size before it is uploaded
(js/upload-size-check.js, #783).

A file over its input's own limit, or files that take one upload past what nginx lets through,
are taken back out of their input as they are chosen, with a note saying why, so nothing is sent
to be turned away. These run the real script in headless Chromium, on a page with the inputs it
handles, and choose files of exact sizes.

Hermetic (no Django server, no DB, no tenant routing), and they skip cleanly unless Playwright and
a Chromium build are both available, like the other render tests (e.g.
hackerspace_online/tests/test_phone_width_render.py).
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
except ImportError:  # pragma: no cover (Playwright is in requirements; this guards an install without it)
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
    return None  # pragma: no cover (only on a machine with Playwright but no browser build)


_CHROMIUM = _find_chromium() if HAS_PLAYWRIGHT else None

# A form like an upload page's: an input with a limit of its own, one taking several files with
# one, one taking several with none, and one more. One upload may carry 250 bytes in all. The
# page's own change handler is a stand-in for a submission's draft save, which uploads a file the
# moment it is chosen. The script is loaded twice, as a page with two editors loads it.
_PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<form id="form" enctype="multipart/form-data"
      onsubmit="window.submitted = (window.submitted || 0) + 1; return false;">
  <div class="form-group"><input id="limited" type="file" data-max-size="100"></div>
  <div class="form-group"><input id="limited-several" type="file" multiple data-max-size="100"></div>
  <div class="form-group"><input id="several" type="file" multiple></div>
  <div class="form-group"><input id="other" type="file"></div>
  <button id="send" type="submit">Send</button>
</form>
<script>
  window.handledByPage = [];
  document.addEventListener("change", function (event) { window.handledByPage.push(event.target.id); });
</script>
<script src="file://{script}" data-max-request-size="250"></script>
<script src="file://{script}" data-max-request-size="250"></script>
</body></html>"""


@skipUnless(HAS_PLAYWRIGHT and _CHROMIUM, "Playwright and a Chromium build are required")
class UploadSizeCheckRenderTest(SimpleTestCase):
    """A file too large to upload is refused as it is chosen, before anything is sent (#783)."""

    @classmethod
    def setUpClass(cls):
        """Start one headless browser and write the page for the class."""
        super().setUpClass()
        cls._pw = sync_playwright().start()
        cls._browser = cls._pw.chromium.launch(executable_path=_CHROMIUM)
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as fh:
            fh.write(_PAGE.replace("{script}", finders.find("js/upload-size-check.js")))
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
        self.page = self._browser.new_page()
        self.addCleanup(self.page.close)
        self.page.goto("file://" + self._html_path)

    def _choose(self, selector, *sizes):
        """Choose files of the given sizes in the input `selector`, as a person picking them would.

        Args:
            selector (str): CSS selector for one file input.
            *sizes (int): each file's size in bytes; the files are named file1.bin, file2.bin, ...
        """
        self.page.set_input_files(selector, files=[
            {"name": f"file{number}.bin", "mimeType": "application/octet-stream", "buffer": b"x" * size}
            for number, size in enumerate(sizes, start=1)
        ])

    def _chosen(self, selector):
        """How many files the input `selector` holds."""
        return self.page.eval_on_selector(selector, "input => input.files.length")

    def _notes(self, selector):
        """The text of each size note in the form group of the input `selector`."""
        return self.page.eval_on_selector(
            selector, "input => [...input.closest('.form-group').querySelectorAll('.upload-size-note')].map(n => n.textContent)")

    def _handled_by_page(self):
        """The ids of the inputs whose change reached the page's own handler."""
        return self.page.evaluate("window.handledByPage")

    def test_upload_size_check__a_file_over_its_inputs_limit_is_taken_back_out(self):
        """A file over the input's own limit is taken out of it, with one note saying so, and the
        page's own handler (a draft save) never hears of it."""
        self._choose("#limited", 200)

        self.assertEqual(self._chosen("#limited"), 0)
        self.assertEqual(self._notes("#limited"), [
            "“file1.bin” is 200 bytes, over the 100 bytes limit for a file here. Choose a smaller file.",
        ])
        self.assertEqual(self._handled_by_page(), [])

    def test_upload_size_check__a_file_within_its_limit_is_kept(self):
        """A file within the limit stays chosen and reaches the page's handler, and it clears the
        note an earlier, larger one left."""
        self._choose("#limited", 200)
        self._choose("#limited", 50)

        self.assertEqual(self._chosen("#limited"), 1)
        self.assertEqual(self._notes("#limited"), [])
        self.assertEqual(self._handled_by_page(), ["limited"])

    def test_upload_size_check__several_files_over_the_limit_are_counted(self):
        """When more than one chosen file is over the limit, the note says how many."""
        self._choose("#limited-several", 200, 50, 300)

        self.assertEqual(self._chosen("#limited-several"), 0)
        self.assertEqual(self._notes("#limited-several"), [
            "2 of these files are over the 100 bytes limit for a file here. Choose smaller files.",
        ])

    def test_upload_size_check__files_adding_up_past_one_upload_are_refused(self):
        """Files that are each fine but together more than one upload can carry are refused."""
        self._choose("#several", 100, 100, 100)

        self.assertEqual(self._chosen("#several"), 0)
        self.assertEqual(self._notes("#several"), [
            "These files come to 300 bytes, over the 250 bytes that can be uploaded at once. Choose fewer or smaller files.",
        ])

    def test_upload_size_check__counts_the_files_chosen_elsewhere_in_the_form(self):
        """The files chosen in a form's other inputs go up with these, so they count too. Only
        the file that tipped it over is taken out."""
        self._choose("#other", 200)
        self._choose("#several", 100)

        self.assertEqual(self._chosen("#other"), 1)
        self.assertEqual(self._chosen("#several"), 0)
        self.assertEqual(self._notes("#several"), [
            "With the other files chosen here, that comes to 300 bytes, over the 250 bytes that can be uploaded at "
            "once. Choose fewer or smaller files.",
        ])

    def test_upload_size_check__a_form_is_checked_as_it_is_sent(self):
        """Files that got into the form without a change the script saw are checked on submit: a
        form carrying too much isn't sent, and one within the limits is."""
        self.page.eval_on_selector("#several", """input => {
            const files = new DataTransfer();
            for (const size of [200, 200]) {
                files.items.add(new File([new Uint8Array(size)], "quiet.bin"));
            }
            input.files = files.files;
        }""")

        self.page.click("#send")

        self.assertIsNone(self.page.evaluate("window.submitted"))
        self.assertEqual(self._chosen("#several"), 0)
        self.assertEqual(len(self._notes("#several")), 1)

        self._choose("#several", 100)
        self.page.click("#send")

        self.assertEqual(self.page.evaluate("window.submitted"), 1)

    def test_upload_size_check__sizes_are_written_the_way_the_app_writes_them(self):
        """Sizes read the way Django's filesizeformat writes them in the app's own messages."""
        sizes = self.page.evaluate("[1, 512, 512000, 16777216, 21286092].map(window.uploadSizeCheck.formatSize)")

        self.assertEqual(sizes, ["1 byte", "512 bytes", "500.0 KB", "16.0 MB", "20.3 MB"])
