"""Headless render tests: a formula from the editor's Insert Math button shows without its LaTeX source.

The button (summernote-math.js) inserts the formula KaTeX draws, followed by a span holding the
LaTeX it was drawn from, so the formula can be opened and edited again. The plugin hides that span
with an inline display: none, but the HTML sanitizer that comments and submissions go through
doesn't allow "display", so the style was gone by the time the text was shown, and the source sat
beside the formula: in a comment, and in the editor when a draft was opened again (#2874). The
shared stylesheet hides it now.

Each page is rendered by the app itself, through the test client, and opened in headless Chromium
with the app's own static files, scripts and stylesheets included. Every other request is refused.
The tests skip cleanly unless Playwright and a Chromium build are both available, like the other
render tests (e.g. test_image_shapes_render.py).
"""

import glob
import os
from unittest import skipUnless
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders

from model_bakery import baker

from comments.models import Comment
from comments.sanitize import sanitize_comment_html
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

#: The LaTeX a teacher typed into the Insert Math dialog.
LATEX = r"A = \frac{1}{2}bh"

#: What the Insert Math button puts in the editor for it: KaTeX's drawing of the formula (cut down
#: to one symbol here), then the source, hidden by an inline style the sanitizer doesn't keep.
FORMULA = (
    'The area is <span class="note-math"><span class="katex"><span class="katex-html" aria-hidden="true">'
    '<span class="mord mathnormal">A</span></span></span>'
    f'<span class="note-latex" style="display: none;">{LATEX}</span></span>'
)


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
class MathRenderTest(ByteDeckTenantTestCase):
    """A formula shows without its LaTeX source, in a comment and in the editor."""

    def setUp(self):
        """Give a student two submissions: one handed in, with a teacher's comment holding a
        formula, and one in progress, with a draft holding one. Render both pages, the first as
        the teacher sees it and the second as the student does.

        Playwright's sync API runs an event loop, and Django refuses database access while one
        is running, so the browser starts only once the pages are rendered, and is stopped by a
        cleanup, which runs before the test's transaction is rolled back.
        """
        semester = SiteConfig.get().active_semester
        teacher = User.objects.create_user('math_teacher', is_staff=True)
        student = User.objects.create_user('math_student')

        # what the comment and the draft are stored as: both are sent through the reply form, which
        # sanitizes its text (SubmissionForm.clean_comment_text), so neither keeps the inline style
        stored = sanitize_comment_html(FORMULA)

        handed_in = baker.make(
            QuestSubmission, user=student, quest=baker.make(Quest, name="Triangles", published=True),
            semester=semester, is_completed=True,
        )
        Comment.objects.create_comment(
            user=teacher, text=stored, path=handed_in.get_absolute_url(), target=handed_in,
        )

        in_progress = baker.make(
            QuestSubmission, user=student, quest=baker.make(Quest, name="Circles", published=True),
            semester=semester,
        )
        in_progress.draft_comment = Comment.objects.create_comment(
            user=student, text=stored, path=in_progress.get_absolute_url(), target=in_progress,
        )
        in_progress.save()

        self.pages = {}
        for name, user, submission in (('comment', teacher, handed_in), ('draft', student, in_progress)):
            self.client.force_login(user)
            response = self.client.get(submission.get_absolute_url())
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

    def test_comment__shows_the_formula_without_its_latex_source(self):
        """A teacher's comment shows the formula, and not the LaTeX it was drawn from beside it."""
        self.page.goto(f"{PAGE_ORIGIN}/comment/")
        comment = self.page.locator('.comment-content', has=self.page.locator('.note-math'))

        self.assertTrue(comment.locator('.katex').is_visible())
        self.assertFalse(comment.locator('.note-latex').is_visible())
        self.assertNotIn(LATEX, comment.inner_text())

    def test_draft__shows_the_formula_without_its_latex_source_in_the_editor(self):
        """A draft opened again shows the formula in the editor without its source, which is still
        there for the Insert Math dialog to edit."""
        self.page.goto(f"{PAGE_ORIGIN}/draft/")
        editor = self.page.locator('div.note-editable', has=self.page.locator('.note-math'))
        editor.wait_for()

        self.assertTrue(editor.locator('.katex').is_visible())
        self.assertFalse(editor.locator('.note-latex').is_visible())
        self.assertEqual(editor.locator('.note-latex').text_content(), LATEX)
        self.assertNotIn(LATEX, editor.inner_text())
