"""Tests that a formula is drawn by the page's own KaTeX, whichever KaTeX version stored it.

The editor's Insert Math button (summernote-math.js) stores a formula as the HTML KaTeX built when
it was typed, followed by the LaTeX it was built from in a hidden span. That HTML only lays out
under the stylesheet of the KaTeX version that built it, and KaTeX renames the classes its layout
hangs on between versions: a formula stored by KaTeX 0.9.0 and shown under 0.18.1's stylesheet
draws a vector's arrow under the letter and overlaps a fraction with itself (#2884). The pages now
draw each formula again from its LaTeX (js/note-math.js), and the editor loads the same KaTeX the
pages do.

The browser tests render each page with the app itself, through the test client, and open it in
headless Chromium with the app's own static files, scripts and stylesheets included. Every other
request is refused. They skip cleanly unless Playwright and a Chromium build are both available,
like the other render tests (e.g. test_image_shapes_render.py).
"""

import glob
import os
import re
from unittest import skipUnless
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.template.loader import get_template
from django.test import SimpleTestCase
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

#: The LaTeX a teacher typed into the Insert Math dialog.
LATEX = r"\vec{w}"

#: What the Insert Math button stored for it while the editor loaded KaTeX 0.9.0: that version's
#: drawing of the formula (the arrow's path data left out, its box kept), then the hidden source.
STORED_BY_KATEX_0_9_0 = (
    '<span class="note-math"><span class="katex"><span class="katex-mathml"><math><semantics><mrow>'
    '<mover accent="true"><mrow><mi>w</mi></mrow><mo>⃗</mo></mover></mrow>'
    f'<annotation encoding="application/x-tex">{LATEX}</annotation></semantics></math></span>'
    '<span class="katex-html" aria-hidden="true"><span class="strut" style="height:0.714em;"></span>'
    '<span class="strut bottom" style="height:0.714em;vertical-align:0em;"></span><span class="base">'
    '<span class="mord accent"><span class="vlist-t"><span class="vlist-r"><span class="vlist" style="height:0.714em;">'
    '<span style="top:-3em;"><span class="pstrut" style="height:3em;"></span><span class="mord">'
    '<span class="mord mathit" style="margin-right:0.02691em;">w</span></span></span>'
    '<span style="top:-3em;"><span class="pstrut" style="height:3em;"></span>'
    '<span class="accent-body" style="left:-0.15216em;"><span class="overlay" style="height:0.714em;width:0.471em;">'
    "<svg width='0.471em' height='0.714em' style='width:0.471em' viewBox='0 0 471 714' preserveAspectRatio='xMinYMin'>"
    '</svg></span></span></span></span></span></span></span></span></span></span>'
    f'<span class="note-latex" style="display: none;">{LATEX}</span></span>'
)

#: A formula whose LaTeX KaTeX can't parse, after the drawing it was stored with.
UNPARSEABLE = (
    '<span class="note-math" id="unparseable"><span class="katex">as stored</span>'
    r'<span class="note-latex" style="display: none;">\frac{</span></span>'
)


class SummernoteKatexConfigTest(SimpleTestCase):
    """The editor builds a formula with the same KaTeX the pages draw it with."""

    def _template_katex(self):
        """Return the vendored KaTeX files the base templates load, as static paths.

        Returns:
            set: e.g. {'katex/katex-0.18.1.min.css', 'katex/katex-0.18.1.min.js'}.
        """
        source = ''.join(get_template(name).template.source for name in ('head_css.html', 'javascript.html'))
        return set(re.findall(r"""{% static '(katex/[^']+)' %}""", source))

    def test_summernote_config__editor_loads_the_katex_the_pages_load(self):
        """Every KaTeX file the editor's asset lists load is one the base templates load, so a formula
        typed in the editor is built by the version the pages style it with."""
        pages = self._template_katex()
        self.assertEqual(len(pages), 2)

        for key in ('css', 'js', 'css_for_inplace', 'js_for_inplace'):
            for asset in settings.SUMMERNOTE_CONFIG[key]:
                if 'katex' in asset.lower():
                    with self.subTest(key=key, asset=asset):
                        self.assertTrue(asset.startswith(settings.STATIC_URL))
                        self.assertIn(asset[len(settings.STATIC_URL):], pages)

    def test_summernote_config__iframe_editor_loads_katex_and_draws_stored_formulas(self):
        """The iframe editor's page has none of the base templates, so its own lists load KaTeX's
        stylesheet and script, and the script that draws stored formulas again, after KaTeX."""
        css = [asset[len(settings.STATIC_URL):] for asset in settings.SUMMERNOTE_CONFIG['css']]
        js = [asset[len(settings.STATIC_URL):] for asset in settings.SUMMERNOTE_CONFIG['js']]
        pages = self._template_katex()

        katex_css = [asset for asset in css if asset in pages and asset.endswith('.css')]
        katex_js = [asset for asset in js if asset in pages and asset.endswith('.js')]
        self.assertEqual(len(katex_css), 1)
        self.assertEqual(len(katex_js), 1)
        self.assertLess(js.index(katex_js[0]), js.index('js/note-math.js'))


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
class StoredMathRenderTest(ByteDeckTenantTestCase):
    """A formula stored by an older KaTeX is drawn by the page's own, on the page and in the editor."""

    def setUp(self):
        """Give a quest instructions holding a formula stored by KaTeX 0.9.0 and one KaTeX can't
        parse, then render its page and its edit form as a teacher sees them.

        Playwright's sync API runs an event loop, and Django refuses database access while one
        is running, so the browser starts only once the pages are rendered, and is stopped by a
        cleanup, which runs before the test's transaction is rolled back.
        """
        teacher = User.objects.create_user('math_teacher', is_staff=True)
        quest = baker.make(
            Quest, name="Unit vectors", published=True,
            instructions=f'<p>Is {STORED_BY_KATEX_0_9_0} a unit vector? {UNPARSEABLE}</p>',
        )

        self.client.force_login(teacher)
        self.pages = {}
        for name, url in (('quest', quest.get_absolute_url()), ('edit', reverse('quests:quest_update', args=[quest.pk]))):
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

    def _assert_drawn_by_the_pages_katex(self, formula):
        """Assert a formula is the page's KaTeX's drawing of LATEX, with its arrow over the letter.

        Args:
            formula (playwright.sync_api.Locator): the formula's span.note-math.
        """
        formula.locator('.katex-accent').wait_for(timeout=5000)
        self.assertEqual(formula.locator('.accent').count(), 0)
        self.assertEqual(formula.locator('.note-latex').text_content(), LATEX)

        arrow = formula.locator('svg').bounding_box()
        letter = formula.locator('.mathnormal').bounding_box()
        self.assertLess(arrow['y'] + arrow['height'], letter['y'] + letter['height'])

    def test_quest__draws_a_formula_stored_by_an_older_katex_with_the_pages_own(self):
        """A formula KaTeX 0.9.0 stored in a quest's instructions is drawn again by the page's KaTeX,
        with the vector's arrow above the letter."""
        self.page.goto(f"{PAGE_ORIGIN}/quest/")

        self._assert_drawn_by_the_pages_katex(self.page.locator('.note-math').first)

    def test_quest__keeps_a_formula_katex_cannot_parse_as_it_was_stored(self):
        """A formula whose LaTeX KaTeX can't parse keeps the drawing it was stored with."""
        self.page.goto(f"{PAGE_ORIGIN}/quest/")
        self.page.locator('.note-math .katex-accent').first.wait_for(timeout=5000)

        self.assertEqual(self.page.locator('#unparseable .katex').inner_text(), 'as stored')

    def test_quest__draws_a_formula_added_after_the_page_loads(self):
        """A formula added to the page once it has loaded, as the quest list's AJAX previews are,
        is drawn by the page's KaTeX too."""
        self.page.goto(f"{PAGE_ORIGIN}/quest/")
        self.page.evaluate(
            "html => document.body.insertAdjacentHTML('beforeend', '<div id=\"later\">' + html + '</div>')",
            STORED_BY_KATEX_0_9_0,
        )

        self._assert_drawn_by_the_pages_katex(self.page.locator('#later .note-math'))

    def test_editor__draws_a_stored_formula_with_the_pages_katex(self):
        """Opening the quest to edit shows the formula drawn by the page's KaTeX in the editor, with
        its source still beside it for the Insert Math dialog."""
        self.page.goto(f"{PAGE_ORIGIN}/edit/")
        editor = self.page.locator('div.note-editable', has=self.page.locator('.note-math')).first
        editor.wait_for(timeout=5000)

        self._assert_drawn_by_the_pages_katex(editor.locator('.note-math').first)
