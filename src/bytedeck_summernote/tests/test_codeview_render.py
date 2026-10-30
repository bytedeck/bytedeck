"""Tests that the editor's code view shows what was just written in the editor (#2902).

The code view is CodeMirror 5, which Summernote builds over its own textarea each time the code
view opens (CodeMirror.fromTextArea) and takes down each time it closes (toTextArea). An instance
keeps its own copy of the text, and its save() writes that copy into the textarea, even after the
instance has been taken down. Summernote keeps the last instance it built, and its code getter,
summernote('code'), saves that instance into the textarea while the code view is open.

The widget's onBlur copied summernote('code') into the form's field. The keep-caret plugin
(static/bytedeck_summernote/plugins/keep-caret/) keeps the focus in the editing area while the
toolbar is pressed (#2734), so the editing area loses it only once the code view, opening, takes
the focus itself. At that moment the code view counts as open but CodeMirror is not built yet. On
the first opening there is no instance yet, and saving it raised a TypeError. On any later opening
the instance left over from the last one saved the old text over the new, so the code view opened
on the content as it was when it last closed, and closing it put that content back into the editor.

The page is the quest form, rendered by the app through the test client, so the widget template
under test is the real one. Headless Chromium opens it with the app's own static files. CodeMirror
comes from cdnjs, which a test can't reach, so CODEMIRROR stands in for it: it keeps
CodeMirror 5's fromTextArea contract, which is the part this depends on
(https://github.com/codemirror/codemirror5/blob/5.63.3/src/edit/fromTextArea.js). Every other
request is refused. The tests skip cleanly unless Playwright and a Chromium build are both
available, like the other render tests (e.g. test_stored_math_render.py).
"""

import glob
import os
from unittest import skipUnless
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.urls import reverse

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover (Playwright is in requirements; this guards an install without it)
    HAS_PLAYWRIGHT = False

User = get_user_model()

#: Where the rendered page pretends to live, so its root-relative links resolve.
PAGE_ORIGIN = "http://deck.test"

#: The quest's instructions as the teacher opens them; the test deletes " Delete this." from the end.
INSTRUCTIONS = "<p>Keep this sentence. Delete this.</p>"
DELETED = " Delete this."

#: A stand-in for CodeMirror 5 holding to the fromTextArea contract: each instance keeps its own
#: copy of the text, save() writes that copy into the textarea, and toTextArea() saves and puts the
#: textarea back. save() still works once the instance has been taken down, as CodeMirror's does.
CODEMIRROR = """
window.CodeMirror = {
    fromTextArea: function (textarea) {
        var text = textarea.value, handlers = {};
        var wrapper = document.createElement('div');
        wrapper.className = 'CodeMirror';
        textarea.style.display = 'none';
        textarea.parentNode.insertBefore(wrapper, textarea.nextSibling);
        var cm = {
            getValue: function () { return text; },
            setValue: function (value) { text = value; },
            getDoc: function () { return cm; },
            save: function () { textarea.value = text; },
            toTextArea: function () {
                cm.save();
                wrapper.parentNode.removeChild(wrapper);
                textarea.style.display = '';
            },
            on: function (name, handler) { (handlers[name] = handlers[name] || []).push(handler); },
            setSize: function () {},
            getWrapperElement: function () { return wrapper; }
        };
        return cm;
    }
};
"""


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
class CodeviewRenderTest(ByteDeckTenantTestCase):
    """The code view opens on what is in the editor, and closing it keeps the editor's content."""

    def setUp(self):
        """Render the edit form of a quest with INSTRUCTIONS as a teacher sees it, and open it in
        headless Chromium.

        Playwright's sync API runs an event loop, and Django refuses database access while one
        is running, so the browser starts only once the page is rendered, and is stopped by a
        cleanup, which runs before the test's transaction is rolled back.
        """
        teacher = User.objects.create_user('codeview_teacher', is_staff=True)
        quest = baker.make(Quest, name="Code view", instructions=INSTRUCTIONS)

        self.client.force_login(teacher)
        response = self.client.get(reverse('quests:quest_update', args=[quest.pk]))
        self.assertEqual(response.status_code, 200)
        self.html = response.content.decode()

        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        browser = playwright.chromium.launch(executable_path=_CHROMIUM)
        self.addCleanup(browser.close)
        self.page = browser.new_page()
        self.page_errors = []
        self.page.on('pageerror', lambda error: self.page_errors.append(str(error)))
        self.page.route("**/*", self._serve)

        self.page.goto(f"{PAGE_ORIGIN}/edit/")
        self.editor = self.page.locator('#id_instructions + div .note-editor')
        self.editable = self.editor.locator('.note-editable')
        self.editable.wait_for(timeout=5000)

    def _serve(self, route, request):
        """Answer the page's requests: the rendered page, CODEMIRROR for CodeMirror's script, and
        the app's static files from disk. Anything else is refused.

        Args:
            route (playwright.sync_api.Route): the intercepted request's route, answered here.
            request (playwright.sync_api.Request): the request it intercepted.
        """
        url = urlparse(request.url)
        if url.path == '/edit/':
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        elif url.hostname == 'cdnjs.cloudflare.com' and url.path.endswith('/codemirror.min.js'):
            route.fulfill(status=200, content_type="text/javascript", body=CODEMIRROR)
        elif url.path.startswith(settings.STATIC_URL) and finders.find(url.path[len(settings.STATIC_URL):]):
            route.fulfill(path=finders.find(url.path[len(settings.STATIC_URL):]))
        else:
            route.abort()

    def _toggle_codeview(self):
        """Press the toolbar's code view button, as a mouse does."""
        self.editor.locator('.btn-codeview').click()

    def _codeview_text(self):
        """Return the text the open code view shows.

        Returns:
            str: the text of the CodeMirror instance the code view is showing.
        """
        return self.editor.locator('.note-codable').evaluate("codable => $(codable).data('cmEditor').getValue()")

    def _delete_the_last_sentence(self):
        """Put the caret at the end of the instructions and delete DELETED with Backspace."""
        self.editable.click()
        self.page.keyboard.press('Control+End')
        for _ in DELETED:
            self.page.keyboard.press('Backspace')
        self.assertEqual(self.editable.inner_text().strip(), 'Keep this sentence.')

    def _assert_codeview_follows_the_edit(self):
        """Open the code view and close it again, asserting the edit survives both ways."""
        self._toggle_codeview()
        self.assertIn('Keep this sentence.', self._codeview_text())
        self.assertNotIn('Delete this', self._codeview_text())

        self._toggle_codeview()
        self.assertEqual(self.editable.inner_text().strip(), 'Keep this sentence.')
        self.assertNotIn('Delete this', self.page.locator('#id_instructions').input_value())
        self.assertEqual(self.page_errors, [])

    def test_codeview__shows_an_edit_made_before_it_was_first_opened(self):
        """The first time the code view opens after an edit, it shows the edit, without an error."""
        self._delete_the_last_sentence()

        self._assert_codeview_follows_the_edit()

    def test_codeview__shows_an_edit_made_after_it_was_last_closed(self):
        """Once the code view has been opened and closed, an edit made in the editor afterwards is
        what it shows the next time it opens, and closing it again keeps the edit."""
        self._toggle_codeview()
        self._toggle_codeview()

        self._delete_the_last_sentence()

        self._assert_codeview_follows_the_edit()
