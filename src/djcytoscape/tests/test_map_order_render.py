"""Headless render test for issue #1977 — campaign map_order actually reorders the columns.

The bug this guards against: PR #2016 tried to order campaigns by re-sorting the elements JSON,
assuming dagre honours input order. It doesn't (dagre orders same-rank nodes by crossing
minimization), so setting a campaign's map_order had no visible effect. The real fix repositions
the campaign columns in ``maps.js`` after dagre runs. That behaviour lives entirely in the
browser, so this test drives the *real* vendored cytoscape/dagre assets and the *real* maps.js in
headless Chromium and asserts the rendered left-to-right order follows map_order.

It is hermetic — no Django server, no DB, no tenant routing — and skips cleanly unless Playwright
and a Chromium build are both available, so a normal suite run (or CI without a browser) is
unaffected. Runs for real once a Chromium build is present (see the front-end-testing setup in
#2053/#503).
"""

import glob
import os
import tempfile
from unittest import skipUnless

from django.apps import apps
from django.test import SimpleTestCase

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
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
    return None


_CHROMIUM = _find_chromium() if HAS_PLAYWRIGHT else None

# A minimal jQuery stand-in so maps.js (which only uses $ for document-ready, resize, and a few
# .css()/.click() calls that never fire in a headless load) runs to completion. Ready callbacks are
# deferred like real jQuery so maps.js's later `var updateBounds` exists by the time they run.
_JQUERY_STUB = """
window.$ = window.jQuery = function () {
    var api = {
        ready: function (fn) { setTimeout(fn, 0); return api; },
        resize: function () { return api; },
        click: function () { return api; },
        css: function () { return api; },
        toggleClass: function () { return api; },
    };
    return api;
};
"""

_PAGE_TEMPLATE = """<!doctype html><html><head>
<style>#cy {{ width: 1200px; height: 800px; position: absolute; top: 0; left: 0; }}</style>
</head><body><div id="cy"></div>
<script>{jquery_stub}</script>
<script src="file://{js_dir}/cytoscape.min.js"></script>
<script src="file://{js_dir}/dagre.min.js"></script>
<script src="file://{js_dir}/cytoscape-dagre.js"></script>
<script>
var elements = {{
  nodes: [
    {{ data: {{ id: '10', label: 'Campaign A', campaignOrder: {order_a} }} }},
    {{ data: {{ id: '20', label: 'Campaign B', campaignOrder: {order_b} }} }},
    {{ data: {{ id: '11', parent: '10', label: 'A1', campaignOrder: {order_a} }} }},
    {{ data: {{ id: '12', parent: '10', label: 'A2', campaignOrder: {order_a} }} }},
    {{ data: {{ id: '21', parent: '20', label: 'B1', campaignOrder: {order_b} }} }},
    {{ data: {{ id: '22', parent: '20', label: 'B2', campaignOrder: {order_b} }} }}
  ],
  edges: [
    {{ data: {{ id: '101', source: '11', target: '12' }} }},
    {{ data: {{ id: '102', source: '21', target: '22' }} }}
  ]
}};
var cy = cytoscape({{ container: document.getElementById('cy'), elements: elements, style: [] }});
</script>
<script src="file://{js_dir}/maps.js"></script>
</body></html>"""


@skipUnless(HAS_PLAYWRIGHT and _CHROMIUM, "Playwright and a Chromium build are required")
class CampaignMapOrderRenderTest(SimpleTestCase):
    """Drive the real maps.js in headless Chromium and check map_order controls campaign order.

    Campaign A always has the smaller node id (10 < 20), so if the layout were ordered by id (the
    pre-fix behaviour) A would always be on the left. Driving the order via campaignOrder proves the
    fix: the campaign with the lower map_order wins regardless of id.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.js_dir = os.path.join(apps.get_app_config("djcytoscape").path, "static", "djcytoscape", "js")
        cls._pw = sync_playwright().start()
        cls._browser = cls._pw.chromium.launch(executable_path=_CHROMIUM)

    @classmethod
    def tearDownClass(cls):
        cls._browser.close()
        cls._pw.stop()
        super().tearDownClass()

    def _campaign_mean_x(self, order_a, order_b):
        """Render the two-campaign map with the given map_orders; return (meanX_A, meanX_B)."""
        html = _PAGE_TEMPLATE.format(
            jquery_stub=_JQUERY_STUB, js_dir=self.js_dir, order_a=order_a, order_b=order_b,
        )
        # Load from a real file so the browser will fetch the file:// asset <script>s (it refuses
        # to load file:// sub-resources for an in-memory set_content document).
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as fh:
            fh.write(html)
            html_path = fh.name
        page = self._browser.new_page()
        try:
            page.goto("file://" + html_path)
            # maps.js repositions synchronously right after layout.run(); give the page a beat to settle.
            page.wait_for_timeout(300)
            mean_x = "(ids) => ids.reduce((s, id) => s + cy.getElementById(id).position('x'), 0) / ids.length"
            ax = page.evaluate(mean_x, ["11", "12"])
            bx = page.evaluate(mean_x, ["21", "22"])
        finally:
            page.close()
            os.unlink(html_path)
        return ax, bx

    def test_map_order__lower_map_order_campaign_renders_on_the_left(self):
        """Campaign B (larger id) with a lower map_order than A must render to the left of A."""
        ax, bx = self._campaign_mean_x(order_a=1000, order_b=0)
        self.assertLess(bx, ax, "campaign B (lower map_order) should be left of A")

    def test_map_order__swapping_map_order_swaps_the_columns(self):
        """Giving A the lower map_order flips it back to the left — the order tracks the value."""
        ax, bx = self._campaign_mean_x(order_a=0, order_b=1000)
        self.assertLess(ax, bx, "campaign A (lower map_order) should be left of B")

    def test_map_order__equal_map_order_falls_back_to_node_id(self):
        """With equal map_order, the smaller-id campaign (A) stays left — the deterministic #2012
        tie-break, so maps where nobody set an order look exactly as before.
        """
        ax, bx = self._campaign_mean_x(order_a=0, order_b=0)
        self.assertLess(ax, bx, "with equal map_order, smaller-id campaign A should be left")
