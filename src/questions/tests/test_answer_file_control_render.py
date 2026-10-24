"""Headless render tests for a file question's answer control on the submission page (#2925).

The control works as the submission's own attachments do, for one file: choosing a file saves the
draft straight away, the saved file then appears in the list above the button with its Delete
button, and Delete empties the list again.

The submission page is rendered by the app itself, through the test client, and opened in headless
Chromium with the app's own static files, scripts included. The test answers the draft save and the
delete itself, and refuses every other request. It skips cleanly unless Playwright and a Chromium
build are both available, like the other render tests (e.g.
quest_manager/tests/test_submit_while_attaching_render.py).
"""

import glob
import json
import os
from unittest import skipUnless
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from model_bakery import baker

from questions.models import Question, QuestionSubmission
from questions.tests.test_integration import QuestionSubmissionFlowTestBase
from questions.utils import render_answer_file

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover (Playwright is in requirements; this guards an install without it)
    HAS_PLAYWRIGHT = False

#: Where the rendered page pretends to live, so its root-relative links resolve.
PAGE_ORIGIN = "http://deck.test"


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
class AnswerFileControlRenderTest(QuestionSubmissionFlowTestBase):
    """Choosing a file for a file question lists it with its Delete button, and Delete removes it."""

    def setUp(self):
        """Add a file question to the student's quest, render their submission page, and open it in
        a headless browser.

        Playwright's sync API runs an event loop, and Django refuses database access while one
        is running, so the browser starts only once the page and the endpoints' answers are
        rendered, and is stopped by a cleanup, which runs before the test's transaction is
        rolled back.
        """
        self.file_question = baker.make(
            Question, quest=self.quest, ordinal=3, type="file_upload", required=False,
            instructions="<p>Upload your logo.</p>", allowed_file_type="image",
        )
        super().setUp()
        self.field_name = self.file_field_name(self.file_question)
        response = self.client.get(reverse("quests:submission", args=[self.submission.id]))
        self.assertEqual(response.status_code, 200)
        self.html = response.content.decode()
        self.save_draft_path = reverse("quests:ajax_save_draft")

        # What the draft save hands back once the file is stored, rendered from the row holding
        # it, after the page above was rendered without it.
        row = QuestionSubmission.objects.get(quest_submission=self.submission, question=self.file_question)
        self.delete_path = reverse("questions:ajax_delete_draft_answer_file", args=[row.id])
        row.response_file = SimpleUploadedFile("logo.png", b"png-bytes", content_type="image/png")
        row.save()
        self.addCleanup(row.response_file.storage.delete, row.response_file.name)
        self.saved_html = render_answer_file(row)

        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        browser = playwright.chromium.launch(executable_path=_CHROMIUM)
        self.addCleanup(browser.close)
        self.page = browser.new_page()
        self.draft_bodies = []  # what each draft save sent
        self.deletes = []  # the path of each delete
        self.dialogs = []  # the text of any alert the page raised
        self.page.on("dialog", lambda dialog: (self.dialogs.append(dialog.message), dialog.dismiss()))
        self.page.route("**/*", self._serve)
        self.page.goto(f"{PAGE_ORIGIN}/page/")

    def _serve(self, route, request):
        """Answer the page's requests: the page itself and its static files from disk, the draft
        save as the server answers one that stored the file, and the delete as the server answers
        one that removed it. Anything else is refused.

        Args:
            route (playwright.sync_api.Route): the intercepted request's route, answered here.
            request (playwright.sync_api.Request): the request it intercepted.
        """
        path = urlparse(request.url).path
        if path == "/page/":
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        elif path.startswith(settings.STATIC_URL) and finders.find(path[len(settings.STATIC_URL):]):
            route.fulfill(path=finders.find(path[len(settings.STATIC_URL):]))
        elif path == self.save_draft_path:
            self.draft_bodies.append(request.post_data_buffer or b"")
            body = {
                "result": "Draft saved", "saved_answer_files": {self.field_name: "logo.png"},
                "answer_files_html": {self.field_name: self.saved_html}, "saved_attachments": [], "file_errors": {},
            }
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
        elif path == self.delete_path and request.method == "POST":
            self.deletes.append(path)
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"answer_file_html": ""}))
        else:
            route.abort()

    def test_choose_file__the_saved_file_is_listed_and_deletable(self):
        """A chosen file goes up with a draft save, then shows in the list with its Delete button,
        its input emptied, and Delete takes it off the list again."""
        saved = self.page.locator(f'.answer-file-saved[data-for="{self.field_name}"]')
        self.assertEqual(saved.locator("li").count(), 0)

        self.page.set_input_files(
            f'input[name="{self.field_name}"]',
            files=[{"name": "logo.png", "mimeType": "image/png", "buffer": b"png-bytes"}],
        )

        self.page.wait_for_selector(f'.answer-file-saved[data-for="{self.field_name}"] .answer-file-delete', timeout=10000)
        self.assertIn(self.field_name.encode(), self.draft_bodies[0])
        self.assertIn("logo.png", saved.inner_text())
        self.assertEqual(self.page.eval_on_selector(f'input[name="{self.field_name}"]', "input => input.files.length"), 0)
        self.assertEqual(self.page.locator(".draft-file-note").count(), 0, "the list says it, so no note says it again")

        saved.locator(".answer-file-delete").click()

        self.page.wait_for_function(
            f"document.querySelectorAll('.answer-file-saved[data-for=\"{self.field_name}\"] li').length === 0", timeout=10000)
        self.assertEqual(self.deletes, [self.delete_path])
        self.assertEqual(self.dialogs, [])
