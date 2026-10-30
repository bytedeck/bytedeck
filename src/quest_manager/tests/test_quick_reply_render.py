"""Headless render tests: a quick reply's HTML arrives in the reply as HTML.

A teacher can give a quest its own Quick Reply Text, and the deck a site-wide one, and insert
either into a reply with a button. Teachers write links into them, such as a link to a moment in a
video. On a submission's page the reply box is the rich-text editor, and the text arrived in it
escaped, so the link showed as its HTML source. The buttons now carry their text sanitized on the
server, and the submission page inserts it as HTML; on Quest Approvals, whose reply box is plain
text, it goes in as its source, which the comment renders once sent.

Each page is rendered by the app itself, through the test client, and opened in headless Chromium
with the app's own static files, scripts included. Every other request is refused. The tests skip
cleanly unless Playwright and a Chromium build are both available, like the other render tests
(e.g. test_flag_submission_render.py).
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

#: The quest's quick reply, as a teacher wrote one: a link to a moment in a video.
QUEST_QUICK_REPLY = (
    'Please take a look at <a href="https://youtu.be/J8MH-k0Fa6Y?si=dq9GB2UH_iQWd-Ro&t=360">6:00</a> '
    'of the video for a quick reference for the timing and squash and stretch.'
)
VIDEO_URL = "https://youtu.be/J8MH-k0Fa6Y?si=dq9GB2UH_iQWd-Ro&t=360"

#: The deck's site-wide quick reply, with a link of its own.
SITE_QUICK_TEXT = 'Read the <a href="https://example.com/rubric">rubric</a> first.'


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
class QuickReplyRenderTest(ByteDeckTenantTestCase):
    """The quick reply buttons insert their text's HTML, on a submission's page and on Quest Approvals."""

    def setUp(self):
        """Give a student a submitted quest with a quick reply, and the deck a site-wide one, and
        render the submission's page and Quest Approvals as their teacher sees them.

        Playwright's sync API runs an event loop, and Django refuses database access while one
        is running, so the browser starts only once the pages are rendered, and is stopped by a
        cleanup, which runs before the test's transaction is rolled back.
        """
        config = SiteConfig.get()
        config.submission_quick_text = SITE_QUICK_TEXT
        config.save()
        teacher = User.objects.create_user('quick_reply_teacher', is_staff=True)
        student = User.objects.create_user('quick_reply_student')
        quest = baker.make(Quest, name="Bouncing Ball", xp=5, published=True, quick_reply=QUEST_QUICK_REPLY)
        submission = baker.make(
            QuestSubmission, user=student, quest=quest,
            semester=config.active_semester, is_completed=True,
        )
        self.submission_id = submission.id

        self.client.force_login(teacher)
        self.pages = {}
        for name, url in (('submission', submission.get_absolute_url()), ('approvals', reverse('quests:submitted_all'))):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.pages[f'/{name}/'] = response.content.decode()

        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        browser = playwright.chromium.launch(executable_path=_CHROMIUM)
        self.addCleanup(browser.close)
        self.page = browser.new_page()
        self.page.route("**/*", self._serve)

    def _serve(self, route, request):
        """Answer the page's requests: the rendered pages and their static files from disk. Anything
        else is refused.

        Args:
            route (playwright.sync_api.Route): the intercepted request's route, answered here.
            request (playwright.sync_api.Request): the request it intercepted.
        """
        path = urlparse(request.url).path
        if path in self.pages:
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.pages[path])
        elif path.startswith(settings.STATIC_URL) and finders.find(path[len(settings.STATIC_URL):]):
            route.fulfill(path=finders.find(path[len(settings.STATIC_URL):]))
        else:
            route.abort()

    def _press(self, button_id):
        """Press a quick reply button, by its id, wherever it sits on the page."""
        self.page.evaluate("id => document.getElementById(id).click()", button_id)

    def _open_submission(self):
        """Open the submission's page, once its editor is up.

        Returns:
            playwright.sync_api.Locator: the editing area of the reply's editor.
        """
        self.page.goto(f"{PAGE_ORIGIN}/submission/")
        editor = self.page.locator('#main-comment-form div.note-editable')
        editor.wait_for()
        return editor

    def test_submission_page__quest_quick_reply_inserts_its_link(self):
        """On a submission's page, the quest's quick reply lands in the editor with its link as a
        link, not as the link's HTML source."""
        editor = self._open_submission()

        self._press(f'btn_quest_quick_text{self.submission_id}')

        link = editor.locator('a')
        self.assertEqual(link.count(), 1)
        self.assertEqual(link.get_attribute('href'), VIDEO_URL)
        self.assertEqual(link.inner_text(), '6:00')
        self.assertIn('Please take a look at 6:00 of the video', editor.inner_text())
        self.assertNotIn('<a', editor.inner_text())

    def test_submission_page__site_wide_quick_reply_inserts_its_link(self):
        """On a submission's page, the site-wide quick reply lands in the editor with its link as a
        link."""
        editor = self._open_submission()

        self._press(f'btn_quick_text{self.submission_id}')

        self.assertEqual(editor.locator('a').get_attribute('href'), 'https://example.com/rubric')
        self.assertIn('Read the rubric first.', editor.inner_text())

    def test_approvals__quest_quick_reply_inserts_its_html(self):
        """On Quest Approvals, the plain-text reply box receives the quest's quick reply as its
        HTML source, link included, which the comment renders once sent."""
        self.page.goto(f"{PAGE_ORIGIN}/approvals/")
        box = self.page.locator(f'#quick_reply{self.submission_id} textarea')

        self._press(f'btn_quest_quick_text{self.submission_id}')
        self._press(f'btn_quick_text{self.submission_id}')

        text = box.input_value()
        self.assertIn('Please take a look at <a href="https://youtu.be/J8MH-k0Fa6Y?si=dq9GB2UH_iQWd-Ro&amp;t=360">6:00</a>', text)
        self.assertIn('Read the <a href="https://example.com/rubric">rubric</a> first.', text)
