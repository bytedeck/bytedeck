"""Headless render tests: a submit pressed while a chosen file is still attaching waits for it (#2834).

Choosing a file on a submission page saves the draft straight away, uploading the file (#2749). A
submit pressed while that upload is still on its way would send the same file again with the form,
and wait on both uploads. The page holds the submit until the draft save lands instead, saying so
beside the button, and then sends the form without the file the save stored.

The submission page is rendered by the app itself, through the test client, and opened in headless
Chromium with the app's own static files, scripts included. The test answers the draft save and the
submit itself, holding the draft save until it chooses to answer it, and refuses every other
request. It skips cleanly unless Playwright and a Chromium build are both available, like the other
render tests (e.g. hackerspace_online/tests/test_phone_width_render.py).
"""

import glob
import json
import os
from unittest import skipUnless
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.urls import reverse

from model_bakery import baker

from comments.models import Comment
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover (Playwright is in requirements; this guards an install without it)
    HAS_PLAYWRIGHT = False

User = get_user_model()

#: Where the rendered page pretends to live, so its root-relative links resolve.
PAGE_ORIGIN = "http://deck.test"

#: The chosen file's bytes: distinctive, so a request can be searched for them.
FILE_CONTENT = b"attaching-2834-" * 64


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
class SubmitWhileAttachingRenderTest(ByteDeckTenantTestCase):
    """A submit pressed while a chosen file is still uploading with the draft waits for it (#2834)."""

    def setUp(self):
        """Give a student an in-progress submission with a draft comment, render its page, and
        open it in a headless browser.

        Playwright's sync API runs an event loop, and Django refuses database access while one
        is running, so the browser starts only once the page is rendered, and is stopped by a
        cleanup, which runs before the test's transaction is rolled back.
        """
        student = User.objects.create_user('attaching_student')
        quest = baker.make(Quest, name="Attaching Quest", xp=5, published=True)
        submission = baker.make(
            QuestSubmission, user=student, quest=quest,
            semester=SiteConfig.get().active_semester, is_completed=False,
        )
        submission.draft_comment = Comment.objects.create_comment(
            user=student, path=submission.get_absolute_url(), text="", target=None)
        submission.save()

        self.client.force_login(student)
        response = self.client.get(submission.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.html = response.content.decode()
        self.save_draft_path = reverse('quests:ajax_save_draft')
        self.complete_path = reverse('quests:complete', args=[submission.id])

        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        browser = playwright.chromium.launch(executable_path=_CHROMIUM)
        self.addCleanup(browser.close)
        self.page = browser.new_page()
        self.held_saves = []  # draft saves the test has yet to answer
        self.draft_bodies = []  # what each draft save sent
        self.submits = []  # what each submit sent
        self.dialogs = []  # the text of any alert the page raised
        self.page.on("dialog", lambda dialog: (self.dialogs.append(dialog.message), dialog.dismiss()))
        self.page.route("**/*", self._serve)
        self.page.goto(f"{PAGE_ORIGIN}/page/")

    def _serve(self, route, request):
        """Answer the page's requests: the page itself and its static files from disk, the draft
        save held for the test to answer, and the submit recorded. Anything else is refused.

        Args:
            route (playwright.sync_api.Route): the intercepted request's route, which is answered
                (or kept, for a draft save) here.
            request (playwright.sync_api.Request): the request it intercepted.
        """
        path = urlparse(request.url).path
        if path == "/page/":
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        elif path.startswith(settings.STATIC_URL) and finders.find(path[len(settings.STATIC_URL):]):
            route.fulfill(path=finders.find(path[len(settings.STATIC_URL):]))
        elif path == self.save_draft_path:
            self.draft_bodies.append(request.post_data_buffer or b"")
            self.held_saves.append(route)
        elif path == self.complete_path and request.method == "POST":
            self.submits.append(request.post_data_buffer or b"")
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body="<p id='sent'>Submitted</p>")
        else:
            route.abort()

    def _choose_file(self):
        """Choose a file in the comment's Attach files input, which starts a draft save carrying it."""
        self.page.set_input_files(
            '#submission-main-form input[name="attachments"]',
            files=[{"name": "recording.txt", "mimeType": "text/plain", "buffer": FILE_CONTENT}],
        )
        self.page.wait_for_function("document.querySelector('.draft-file-note-pending') !== null")
        self._wait_until(lambda: self.held_saves, "the draft save carrying the file")

    def _wait_until(self, condition, what, timeout_ms=5000):
        """Let the page run until `condition()` holds, failing the test if it never does.

        Args:
            condition (callable): checked after each short wait, which is when Playwright hands
                the page's requests to `_serve`.
            what (str): what is being waited for, for the failure message.
            timeout_ms (int): how long to wait in all.
        """
        for _ in range(timeout_ms // 50):
            if condition():
                return
            self.page.wait_for_timeout(50)
        self.fail(f"Timed out waiting for {what}")

    def _answer_save(self, status=200, file_errors=None):
        """Answer the held draft save, as the server would.

        Args:
            status (int): the response's status code: 200 for a save, anything else for a failure.
            file_errors (dict or None): the files the server refused, by input name, with why.
                The server sends the re-rendered attachments list only when it stored one, so a
                refusal comes without it.
        """
        if file_errors:
            body = {"saved_answer_files": {}, "saved_attachments": [], "file_errors": file_errors}
        else:
            body = {
                "result": "Draft saved", "saved_answer_files": {}, "saved_attachments": ["recording.txt"],
                "file_errors": {}, "draft_attachments_html": "<ul id='saved-list'></ul>",
            }
        self.held_saves.pop(0).fulfill(status=status, content_type="application/json", body=json.dumps(body))

    def _waiting_shown(self):
        """Whether the note beside the button saying the submit waits for the file is showing."""
        return self.page.is_visible('#submit-waiting')

    def test_submit__waits_for_the_file_attaching_and_sends_it_once(self):
        """A submit pressed while the draft save is uploading the chosen file waits for it, saying
        so, and then goes without the file: it was uploaded once, by the draft save. Pressing
        Submit again while it waits changes nothing."""
        self._choose_file()

        self.page.click('#tour-submit-quest')
        self.page.wait_for_timeout(300)
        self.assertEqual(self.submits, [])
        self.assertTrue(self._waiting_shown())
        self.page.click('#tour-submit-quest')
        self.page.wait_for_timeout(300)

        self._answer_save()
        self._wait_until(lambda: self.submits, "the submit")
        self.page.wait_for_timeout(300)

        self.assertEqual(len(self.submits), 1)
        self.assertIn(b'name="complete"', self.submits[0])
        self.assertNotIn(FILE_CONTENT, self.submits[0])
        self.assertEqual([FILE_CONTENT in body for body in self.draft_bodies], [True])
        self.assertEqual(self.dialogs, [])

    def test_submit__sends_the_file_itself_when_the_draft_save_fails(self):
        """When the draft save it waited for fails, the file was never stored, so the submit
        carries it as it always did."""
        self._choose_file()
        self.page.click('#tour-submit-quest')
        self.page.wait_for_timeout(300)

        self._answer_save(status=500)
        self._wait_until(lambda: self.submits, "the submit")

        self.assertIn(FILE_CONTENT, self.submits[0])

    def test_submit__stops_when_the_file_is_refused(self):
        """When the server refuses the file, the submit stops so the reason can be read under
        the input, and the student can submit again from there."""
        self._choose_file()
        self.page.click('#tour-submit-quest')
        self.page.wait_for_timeout(300)

        self._answer_save(file_errors={"attachments": "That kind of file can't be attached."})
        self.page.wait_for_timeout(500)

        self.assertEqual(self.submits, [])
        self.assertFalse(self._waiting_shown())
        self.assertIn("can't be attached", self.page.inner_text('#main-comment-form'))

        self.page.click('#tour-submit-quest')
        self._wait_until(lambda: self.submits, "the submit pressed again")

    def test_submit__goes_straight_through_with_no_file_on_its_way(self):
        """With nothing uploading, a submit goes at once, as it always has."""
        self.page.click('#tour-submit-quest')
        self._wait_until(lambda: self.submits, "the submit")

        self.assertEqual(self.held_saves, [])
