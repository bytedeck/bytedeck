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
    {{ data: {{ id: '22', parent: '20', label: 'B2', campaignOrder: {order_b} }} }}{extra_nodes}
  ],
  edges: [
    {{ data: {{ id: '101', source: '11', target: '12' }} }},
    {{ data: {{ id: '102', source: '21', target: '22' }} }}{extra_edges}
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

    def _positions(self, order_a, order_b, connected=False, intro=False):
        """Render the two-campaign map and return ``{'a': meanX_A, 'b': meanX_B, 'intro': x|None}``.

        ``connected`` adds a cross-campaign prerequisite edge from A's first quest to B's first quest,
        so campaign B branches off the side of campaign A (A1 continues to A2 AND to B1) — the case
        that used to merge the two campaigns into a single un-orderable column (issue #1977).

        ``intro`` adds a campaign-less node that leads into campaign A (intro -> A1); its rendered x is
        returned so a test can check the intro node follows campaign A when the columns are reordered.
        """
        extra_nodes = ",\n    { data: { id: '1', label: 'Intro' } }" if intro else ""
        extra_edges = ""
        if connected:
            extra_edges += ",\n    { data: { id: '201', source: '11', target: '21' } }"
        if intro:
            extra_edges += ",\n    { data: { id: '301', source: '1', target: '11' } }"
        html = _PAGE_TEMPLATE.format(
            jquery_stub=_JQUERY_STUB, js_dir=self.js_dir, order_a=order_a, order_b=order_b,
            extra_nodes=extra_nodes, extra_edges=extra_edges,
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
            result = {
                "a": page.evaluate(mean_x, ["11", "12"]),
                "b": page.evaluate(mean_x, ["21", "22"]),
                "intro": page.evaluate(mean_x, ["1"]) if intro else None,
            }
        finally:
            page.close()
            os.unlink(html_path)
        return result

    def _campaign_mean_x(self, order_a, order_b, connected=False):
        """Render the two-campaign map with the given map_orders; return (meanX_A, meanX_B)."""
        p = self._positions(order_a, order_b, connected=connected)
        return p["a"], p["b"]

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

    def test_map_order__connected_campaigns_still_ordered_by_map_order(self):
        """A campaign that branches off another must still obey map_order (reopened #1977).

        When B's first quest is a prerequisite continuation of A (a cross-campaign edge), the
        previous connected-component grouping merged A and B into one column, so map_order between
        them did nothing. B has the lower map_order here and must render to the left of A even
        though it hangs off A.
        """
        ax, bx = self._campaign_mean_x(order_a=1000, order_b=0, connected=True)
        self.assertLess(bx, ax, "connected campaign B (lower map_order) should still be left of A")

        # Mirror it — swapping the values swaps the columns, so the fix isn't direction-dependent
        # for the connected case either.
        ax, bx = self._campaign_mean_x(order_a=0, order_b=1000, connected=True)
        self.assertLess(ax, bx, "connected campaign A (lower map_order) should be left of B")

    def test_map_order__intro_node_follows_its_reordered_campaign(self):
        """A campaign-less intro node that leads into a campaign follows that campaign after the
        columns are reordered, instead of being stranded over the campaign's old slot (#1977).

        The intro leads into campaign A; B has the lower map_order (so B goes left, A right). The
        intro must sit over A's column, not stay stranded on the left where A used to be. Checked
        both ways so it isn't direction-dependent.
        """
        p = self._positions(order_a=1000, order_b=0, connected=True, intro=True)
        self.assertLess(
            abs(p["intro"] - p["a"]), abs(p["intro"] - p["b"]),
            "intro node should sit over campaign A (which it leads into), not the reordered-away B",
        )
        p = self._positions(order_a=0, order_b=1000, connected=True, intro=True)
        self.assertLess(
            abs(p["intro"] - p["a"]), abs(p["intro"] - p["b"]),
            "intro node should still sit over campaign A after swapping the order",
        )


# A campaign of two quests feeding two campaigns of three, which is the shape of a map whose intro
# campaign leads into parallel paths. The intro campaign sits in its own vertical band above the
# other two, so its x-slot has room on either side that a side-by-side campaign's slot does not.
_STACKED_PAGE_TEMPLATE = """<!doctype html><html><head>
<style>#cy {{ width: 1400px; height: 1200px; position: absolute; top: 0; left: 0; }}</style>
</head><body><div id="cy"></div>
<script>{jquery_stub}</script>
<script src="file://{js_dir}/cytoscape.min.js"></script>
<script src="file://{js_dir}/dagre.min.js"></script>
<script src="file://{js_dir}/cytoscape-dagre.js"></script>
<script>
var elements = {{
  nodes: [
    {{ data: {{ id: '10', label: 'Intro Campaign', campaignOrder: {order_i} }} }},
    {{ data: {{ id: '100', parent: '10', label: 'I0', campaignOrder: {order_i} }} }},
    {{ data: {{ id: '101', parent: '10', label: 'I1', campaignOrder: {order_i} }} }},
    {{ data: {{ id: '20', label: 'Path A', campaignOrder: {order_a} }} }},
    {{ data: {{ id: '200', parent: '20', label: 'A0', campaignOrder: {order_a} }} }},
    {{ data: {{ id: '201', parent: '20', label: 'A1', campaignOrder: {order_a} }} }},
    {{ data: {{ id: '202', parent: '20', label: 'A2', campaignOrder: {order_a} }} }},
    {{ data: {{ id: '30', label: 'Path B', campaignOrder: {order_b} }} }},
    {{ data: {{ id: '300', parent: '30', label: 'B0', campaignOrder: {order_b} }} }},
    {{ data: {{ id: '301', parent: '30', label: 'B1', campaignOrder: {order_b} }} }},
    {{ data: {{ id: '302', parent: '30', label: 'B2', campaignOrder: {order_b} }} }}
  ],
  edges: [
    {{ data: {{ id: 'i1', source: '100', target: '101' }} }},
    {{ data: {{ id: 'a1', source: '200', target: '201' }} }},
    {{ data: {{ id: 'a2', source: '201', target: '202' }} }},
    {{ data: {{ id: 'b1', source: '300', target: '301' }} }},
    {{ data: {{ id: 'b2', source: '301', target: '302' }} }},
    {{ data: {{ id: 'ia', source: '101', target: '200' }} }},
    {{ data: {{ id: 'ib', source: '101', target: '300' }} }}
  ]
}};
var cy = cytoscape({{ container: document.getElementById('cy'), elements: elements, style: [] }});
</script>
<script src="file://{js_dir}/maps.js"></script>
</body></html>"""


@skipUnless(HAS_PLAYWRIGHT and _CHROMIUM, "Playwright and a Chromium build are required")
class CampaignColumnOverlapRenderTest(SimpleTestCase):
    """Campaign columns never sit on top of each other, whatever their map_order (#2627).

    An x-slot is only as wide as dagre made it, and dagre widens a slot for whatever competes with
    it at the same ranks. A campaign in a vertical band of its own has room on either side that a
    campaign standing beside another does not, so the two kinds of slot are not interchangeable:
    moving a side-by-side campaign into a solitary campaign's slot puts it closer to its neighbour
    than a node is wide, and the two campaigns are drawn over each other for their whole height.
    """

    @classmethod
    def setUpClass(cls):
        """Start one headless browser and locate the vendored cytoscape assets for the class."""
        super().setUpClass()
        cls.js_dir = os.path.join(apps.get_app_config("djcytoscape").path, "static", "djcytoscape", "js")
        cls._pw = sync_playwright().start()
        cls._browser = cls._pw.chromium.launch(executable_path=_CHROMIUM)

    @classmethod
    def tearDownClass(cls):
        """Close the browser and stop Playwright."""
        cls._browser.close()
        cls._pw.stop()
        super().tearDownClass()

    def _campaign_boxes(self, order_i=0, order_a=0, order_b=0):
        """Render the stacked map and return each campaign's rendered box.

        Args:
            order_i (int): map_order of the intro campaign, which sits above the other two.
            order_a (int): map_order of Path A.
            order_b (int): map_order of Path B.

        Returns:
            list[dict]: one ``{'label', 'x1', 'x2', 'y1', 'y2'}`` per campaign.
        """
        html = _STACKED_PAGE_TEMPLATE.format(
            jquery_stub=_JQUERY_STUB, js_dir=self.js_dir,
            order_i=order_i, order_a=order_a, order_b=order_b,
        )
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as fh:
            fh.write(html)
            html_path = fh.name
        page = self._browser.new_page()
        try:
            page.goto("file://" + html_path)
            page.wait_for_timeout(300)
            return page.evaluate(
                "() => cy.nodes().filter(n => n.isParent()).map(function (c) {"
                "  var b = c.boundingBox();"
                "  return { label: c.data('label'), x1: b.x1, x2: b.x2, y1: b.y1, y2: b.y2 }; })"
            )
        finally:
            page.close()
            os.unlink(html_path)

    def _overlaps(self, boxes):
        """Return a readable description of each pair of campaign boxes that intersect.

        Args:
            boxes (list[dict]): campaign boxes from `_campaign_boxes`.

        Returns:
            list[str]: one entry per overlapping pair, empty when the columns are clear of
            each other. Touching edges do not count; only a positive area in both axes does.
        """
        found = []
        for i, first in enumerate(boxes):
            for second in boxes[i + 1:]:
                across = min(first["x2"], second["x2"]) - max(first["x1"], second["x1"])
                down = min(first["y2"], second["y2"]) - max(first["y1"], second["y1"])
                if across > 0 and down > 0:
                    found.append(
                        f"{first['label']} and {second['label']} overlap by "
                        f"{round(across)}x{round(down)} px"
                    )
        return found

    def test_campaign_columns__do_not_overlap_at_the_default_map_order(self):
        """A map nobody has ordered comes out with its columns clear of each other.

        Every campaign at map_order 0 falls back to the smallest quest id, so a default map is
        reordered too rather than left alone: this is what a deck that has never touched campaign
        ordering gets. The intro campaign is a row of one, so it keeps the x dagre gave it, and
        the two paths share a row and may trade places within it.
        """
        overlaps = self._overlaps(self._campaign_boxes())
        self.assertEqual(overlaps, [], "campaign columns overlap: " + "; ".join(overlaps))

    def test_campaign_columns__do_not_overlap_when_map_order_reorders_them(self):
        """Setting a map_order on each campaign must not stack them either, in either direction."""
        for orders in ((1, 2, 3), (3, 2, 1), (2, 3, 1), (1, 3, 2)):
            with self.subTest(orders=orders):
                overlaps = self._overlaps(self._campaign_boxes(*orders))
                self.assertEqual(overlaps, [], "campaign columns overlap: " + "; ".join(overlaps))

    def test_campaign_columns__map_order_still_swaps_the_two_side_by_side_paths(self):
        """The two paths still obey map_order between themselves, which is what #1977 asked for.

        Only campaigns that stand beside each other trade places now, so this is the swap that has
        to keep working: the intro campaign above them is not part of their row.
        """
        by_label = {b["label"]: b for b in self._campaign_boxes(order_i=0, order_a=1, order_b=2)}
        self.assertLess(by_label["Path A"]["x1"], by_label["Path B"]["x1"])

        by_label = {b["label"]: b for b in self._campaign_boxes(order_i=0, order_a=2, order_b=1)}
        self.assertLess(by_label["Path B"]["x1"], by_label["Path A"]["x1"])
