"""Headless render tests for a list table's search box finding text as it's written (#3007).

bootstrap-table searched a table built from markup by escaping the query, ' and " included, and
comparing it with each cell's HTML, where the browser leaves ' and " as they are, so a search
holding either found nothing. js/bootstrap-table-search.js has it escape the query as the browser
escapes cell text instead.

A list page is rendered by the app itself, through the test client, and opened in headless
Chromium with the app's own static files, and its search box is typed into. Two pages, since
bootstrap-table reaches a page two ways: through snippets/bootstrap_table.html (the tag list) and
from quest_manager/base.html (the Common Quest Info list). It skips cleanly unless Playwright and a
Chromium build are both available, like the other render tests (e.g.
competencies/tests/test_approval_levels_render.py).
"""

import glob
import os
from unittest import skipUnless
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.urls import reverse
from taggit.models import Tag

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import CommonData

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover (Playwright is in requirements; this guards an install without it)
    HAS_PLAYWRIGHT = False

User = get_user_model()

#: Where the rendered page pretends to live, so its root-relative links resolve.
PAGE_ORIGIN = "http://deck.test"

#: The rows' names: one with an apostrophe, one with double quotes, one with the characters the
#: browser does escape in a cell's HTML, and one that matches none of the searches.
NAMES = ("Children's learning", 'Say "hi" first', "R&D <lab>", "Other things")


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


class TableSearchRenderMixin:
    """Search a list page's table in a browser. A subclass names the page and makes its rows."""

    def make_rows(self):
        """Create one row of the page's list for each of NAMES."""
        raise NotImplementedError

    def list_url(self):
        """The list page's URL."""
        raise NotImplementedError

    def setUp(self):
        """Render the list page, as a teacher, with a row for each of NAMES, and open it in a
        headless browser.

        Playwright's sync API runs an event loop, and Django refuses database access while one is
        running, so the browser starts only once the page is rendered, and is stopped by a cleanup.
        """
        self.make_rows()
        self.client.force_login(User.objects.create_user("search_teacher", is_staff=True))
        response = self.client.get(self.list_url())
        self.assertContains(response, "js/bootstrap-table-search.js")
        self.html = response.content.decode()

        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        browser = playwright.chromium.launch(executable_path=_CHROMIUM)
        self.addCleanup(browser.close)
        self.page = browser.new_page(viewport={"width": 1200, "height": 900})
        self.page.route("**/*", self._serve)
        self.page.goto(f"{PAGE_ORIGIN}/page/")
        self.page.wait_for_selector(".bootstrap-table .search input")

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

    def _search(self, text):
        """Type into the table's search box and return the names left in the table.

        bootstrap-table searches on a key's release, a moment after the last one, so the text is
        typed key by key. It announces each search, with its query, in its `search.bs.table`
        event, and this waits for the one carrying the whole text before reading the rows: a slow
        typist's pause could start a search on part of it, and "Children" matches the row that
        "Children's" has to.

        Args:
            text (str): what to type.

        Returns:
            list[str]: the first cell's text of each row the search leaves.
        """
        self.page.evaluate(
            "window.searchedText = null;"
            "$('[data-toggle=\"table\"]').on('search.bs.table', function (event, query) { window.searchedText = query; })"
        )
        self.page.locator(".bootstrap-table .search input").press_sequentially(text)
        self.page.wait_for_function("text => window.searchedText === text", arg=text, timeout=10000)
        return self.page.eval_on_selector_all(
            ".bootstrap-table tbody tr:not(.no-records-found) td:first-child",
            "cells => cells.map(cell => cell.textContent.trim())",
        )

    def test_search__finds_text_with_an_apostrophe(self):
        """Searching for "Children's" finds the row named "Children's learning" (#3007)."""
        self.assertEqual(self._search("Children's"), ["Children's learning"])

    def test_search__finds_text_with_double_quotes(self):
        """Searching for '"hi"' finds the row named 'Say "hi" first' (#3007)."""
        self.assertEqual(self._search('"hi"'), ['Say "hi" first'])

    def test_search__still_finds_an_ampersand_and_angle_brackets(self):
        """&, < and > are the characters the browser escapes in a cell's HTML, and a search for
        them still finds them: "R&D <lab>" finds its row."""
        self.assertEqual(self._search("R&D <lab>"), ["R&D <lab>"])


@skipUnless(HAS_PLAYWRIGHT and _CHROMIUM, "Playwright and a Chromium build are required")
class TagListSearchRenderTest(TableSearchRenderMixin, ByteDeckTenantTestCase):
    """The tag list, which loads bootstrap-table through snippets/bootstrap_table.html."""

    def make_rows(self):
        """Create a tag named for each of NAMES."""
        for name in NAMES:
            Tag.objects.create(name=name)

    def list_url(self):
        """The tag list's URL."""
        return reverse("tags:list")


@skipUnless(HAS_PLAYWRIGHT and _CHROMIUM, "Playwright and a Chromium build are required")
class CommonQuestInfoListSearchRenderTest(TableSearchRenderMixin, ByteDeckTenantTestCase):
    """The Common Quest Info list, whose bootstrap-table comes from quest_manager/base.html."""

    def make_rows(self):
        """Create a Common Quest Info titled for each of NAMES."""
        for name in NAMES:
            CommonData.objects.create(title=name, instructions="Instructions")

    def list_url(self):
        """The Common Quest Info list's URL."""
        return reverse("quest_manager:commonquestinfo_list")
