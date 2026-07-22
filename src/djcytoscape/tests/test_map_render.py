"""Headless browser tests for the quest-map front-end (``djcytoscape/js/maps.js``).

These are the first browser-driven tests in the project. Rather than stand up a
full Selenium/live-server stack, they load the *real* vendored map assets
(``cytoscape``, ``dagre``, ``cytoscape-dagre`` and ``maps.js``) into headless
Chromium via Playwright, feed a hand-built ``elements`` fixture, run the actual
dagre layout, and read the resulting node positions back out. That exercises the
one piece of front-end logic unit/view tests structurally can't reach — the
map's client-side layout — while staying hermetic (no network, no Django live
server, no tenant routing).

Locally the test is skipped unless Playwright *and* a pre-installed Chromium are
available, so it never breaks a dev suite run that lacks the browser. In CI --
where the browser is provisioned into the image on purpose -- the test step sets
``REQUIRE_BROWSER_TESTS=1`` so a missing browser fails loudly (at collection)
instead of silently skipping this coverage. To run it: ``pip install playwright``
and ensure a Chromium build is present (``playwright install chromium`` locally,
or the browser image in CI).
"""

import glob
import json
import math
import os
import unittest

from django.test import SimpleTestCase

# Directory holding the production JS the quest_map template loads.
_JS_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "djcytoscape", "js")

# maps.js is written against jQuery (for DOM/event glue) and assumes a global
# ``cy`` already exists. jQuery isn't the code under test, so instead of vendoring
# it we stub the handful of calls maps.js makes. ``ready`` must DEFER (like real
# jQuery) so the ``var updateBounds`` defined lower in maps.js exists before the
# document-ready callback runs. After that callback finishes (it runs the dagre
# layout), the shim flips ``window.__mapsReady`` so the test can wait on a real
# signal instead of a fixed sleep. maps.js makes a single ``$(document).ready``
# call, so the flag is set exactly once, after layout.
_JQUERY_SHIM = (
    "window.$=window.jQuery=function(){return{"
    "ready:function(f){if(f)setTimeout(function(){f();window.__mapsReady=true;},0);return this;},"
    "resize:function(){return this;},click:function(){return this;},"
    "css:function(){return this;},toggleClass:function(){return this;}};};"
)


def _chromium_executable():
    """Return the path to a pre-installed Chromium binary, or None if absent.

    Playwright's bundled-browser lookup pins an exact build number that may not
    match the image's pre-installed Chromium, so tests launch with an explicit
    executable_path resolved here instead.
    """
    matches = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    return matches[0] if matches else None


def _playwright_available():
    """True when Playwright is importable and a Chromium binary is present."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return _chromium_executable() is not None


def _require_browser():
    """True when the environment demands these tests actually run (i.e. CI).

    CI bakes Chromium into the web image on purpose (INSTALL_TEST_BROWSERS), so a
    missing browser there is a provisioning regression we want to fail loudly on
    rather than silently skip past. The CI test step sets REQUIRE_BROWSER_TESTS=1.
    """
    return os.environ.get("REQUIRE_BROWSER_TESTS") == "1"


# Guard against silently losing this coverage: if CI demands the browser but it
# isn't available, fail at collection instead of skipping. Locally (flag unset)
# the tests still skip cleanly when no browser is present.
if _require_browser() and not _playwright_available():
    raise RuntimeError(
        "REQUIRE_BROWSER_TESTS=1 but Playwright/Chromium is unavailable, so the quest-map "
        "browser tests would silently skip. Check the image's Chromium provisioning "
        "(INSTALL_TEST_BROWSERS in the Dockerfile / docker-compose.override.yml)."
    )


def _read_js(name):
    """Return the contents of a vendored map JS asset by file name."""
    with open(os.path.join(_JS_DIR, name), encoding="utf-8") as f:
        return f.read()


def _harness_html(elements, style="[]"):
    """Build a standalone HTML page that renders ``elements`` exactly as production does.

    It inlines the real cytoscape/dagre/cytoscape-dagre/maps.js and initialises
    ``cy`` with the same options as ``djcytoscape/templates/djcytoscape/quest_map.html``.

    Args:
        elements: the cytoscape ``elements`` fixture (a list of ``{"data": {...}}``
            node/edge dicts), JSON-serialised into the ``cy`` init.
        style: the cytoscape ``style`` value as a JSON string (a stylesheet array,
            e.g. ``"[]"`` for none), inlined verbatim into the ``cy`` init.

    Returns:
        str: a complete HTML document that, when loaded in a browser, builds the
        map and exposes the live cytoscape instance as ``window.cy``.
    """
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
<div id="cy" style="width:1200px;height:1200px;"></div>
<script>{_JQUERY_SHIM}</script>
<script>{_read_js('cytoscape.min.js')}</script>
<script>{_read_js('dagre.min.js')}</script>
<script>{_read_js('cytoscape-dagre.js')}</script>
<script>
window.__errors = [];
window.__mapsReady = false;
window.addEventListener('error', function (e) {{ window.__errors.push(String(e.message || e)); }});
var mapContainer = document.getElementById('cy');
var cy = cytoscape({{
  container: mapContainer,
  minZoom: 0.5, maxZoom: 3, zoom: 3, wheelSensitivity: 0.1,
  zoomingEnabled: true, userZoomingEnabled: false,
  autoungrabify: true, autounselectify: true,
  elements: {json.dumps(elements)},
  style: {style},
}});
</script>
<script>{_read_js('maps.js')}</script>
</body></html>"""


@unittest.skipUnless(_playwright_available(), "requires playwright + a pre-installed chromium")
class QuestMapRenderTest(SimpleTestCase):
    """Drives the real quest-map JS in headless Chromium and asserts on the layout."""

    def _render(self, elements, style="[]"):
        """Render ``elements`` through maps.js headless and read the resulting layout back.

        Args:
            elements: the cytoscape ``elements`` fixture (node/edge dicts) to lay out.
            style: the cytoscape ``style`` JSON string, forwarded unchanged to
                ``_harness_html`` (defaults to ``"[]"`` — no custom styling, since
                these tests assert on geometry, not appearance).

        Returns:
            tuple[dict, list]: ``(positions, errors)`` where ``positions`` maps each
            childless (leaf/quest) node id to ``{"id", "x", "y"}`` — compound campaign
            parents are excluded — and ``errors`` is the list of any uncaught page
            errors and console errors collected during the render (empty when clean).
        """
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=_chromium_executable())
            try:
                page = browser.new_page()
                errors = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

                page.set_content(_harness_html(elements, style), wait_until="load")
                # dagre runs synchronously in maps.js, but wait for cy to exist first.
                page.wait_for_function("() => window.cy && cy.nodes().length > 0")
                # Wait for the deferred jQuery-ready callback (which runs the dagre
                # layout) to finish, rather than sleeping a fixed interval -- the shim
                # sets window.__mapsReady once it completes.
                page.wait_for_function("() => window.__mapsReady === true")

                positions = page.evaluate(
                    "() => cy.nodes(':childless').map(n => "
                    "({id: n.id(), x: n.position('x'), y: n.position('y')}))"
                )
                errors += page.evaluate("() => window.__errors")
            finally:
                browser.close()
        return {p["id"]: p for p in positions}, errors

    def test_map_render__nodes_are_laid_out_without_js_errors(self):
        """A simple quest chain renders: every node gets a finite position and no JS error is raised."""
        elements = [
            {"data": {"id": "a", "label": "a"}},
            {"data": {"id": "b", "label": "b"}},
            {"data": {"id": "c", "label": "c"}},
            {"data": {"source": "a", "target": "b"}},
            {"data": {"source": "b", "target": "c"}},
        ]
        pos, errors = self._render(elements)

        self.assertEqual(errors, [], f"unexpected JS errors while rendering the map: {errors}")
        self.assertEqual(set(pos), {"a", "b", "c"})
        for node_id, p in pos.items():
            self.assertTrue(
                all(isinstance(v, (int, float)) and math.isfinite(v) for v in (p["x"], p["y"])),
                f"{node_id} has a non-finite position",
            )
        # dagre ranks the chain top-to-bottom, so the three nodes sit at distinct heights...
        self.assertEqual(len({round(p["y"]) for p in pos.values()}), 3)
        # ...and in the a->b->c edge direction (y grows downward), not reversed.
        self.assertLess(pos["a"]["y"], pos["b"]["y"])
        self.assertLess(pos["b"]["y"], pos["c"]["y"])

    def test_campaign_layout__in_campaign_successor_stays_vertically_stacked(self):
        """Regression guard for #1787/#2023: a campaign's quests stay vertically stacked
        even when one is also a prerequisite for a quest outside the campaign.

        Chain q1->q2->q3 all live in campaign C; q2 also branches to ``out`` (no
        campaign). q3 must remain directly below q2 (same x), while ``out`` — on the
        same rank as q3 — is pushed off to the side.
        """
        elements = [
            {"data": {"id": "C", "label": "Campaign"}},
            {"data": {"id": "q1", "label": "q1", "parent": "C"}},
            {"data": {"id": "q2", "label": "q2", "parent": "C"}},
            {"data": {"id": "q3", "label": "q3", "parent": "C"}},
            {"data": {"id": "out", "label": "out"}},
            {"data": {"source": "q1", "target": "q2"}},
            {"data": {"source": "q2", "target": "q3"}},
            {"data": {"source": "q2", "target": "out"}},
        ]
        pos, errors = self._render(elements)

        self.assertEqual(errors, [], f"unexpected JS errors while rendering the map: {errors}")

        # The in-campaign chain is vertically aligned (same x, within a small tolerance)...
        self.assertAlmostEqual(pos["q1"]["x"], pos["q2"]["x"], delta=5)
        self.assertAlmostEqual(pos["q2"]["x"], pos["q3"]["x"], delta=5)
        # ...and stacked top-to-bottom in q1->q2->q3 order (y grows downward).
        self.assertLess(pos["q1"]["y"], pos["q2"]["y"])
        self.assertLess(pos["q2"]["y"], pos["q3"]["y"])
        # q3 and the out-of-campaign branch share a rank (same y)...
        self.assertAlmostEqual(pos["q3"]["y"], pos["out"]["y"], delta=5)
        # ...but the branch is pushed clearly to the side instead of dragging q3 with it.
        self.assertGreater(abs(pos["out"]["x"] - pos["q2"]["x"]), 40)
