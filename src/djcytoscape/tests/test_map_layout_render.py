"""Headless render tests for quest-map layout: map nodes never sit on top of each other (#2675).

Campaign columns used to be repositioned after dagre had laid the map out, so that a campaign's
``Category.map_order`` decided its place left to right (#1977). Nothing did that safely. dagre
sizes each column for what it put there and spaces every node it places, so moving nodes
afterwards reintroduces exactly the collisions dagre had avoided, and each fix only covered the
collision in front of it: #2627 stopped a solitary campaign's roomy slot being handed to a
side-by-side one, #2677 stopped a wide campaign landing in a narrow one's space, and campaign-less
nodes went on stacking because they were re-centred over their neighbours with no check at all.
The repositioning is gone and dagre's own layout stands, which is what these tests hold it to.

They drive the *real* vendored cytoscape/dagre assets and the *real* maps.js in headless Chromium,
over the three shapes that each produced an overlap.

Each fixture still carries a ``campaignOrder`` on its campaign nodes, which the server no longer
emits, and deliberately so: that value is what any future attempt at ordering would reach for, and
feeding it in means these fail the moment something starts consuming it to move nodes again.

Only the shared-neighbour case fails against the previous maps.js; the other two are the shapes
#2627 and #2677 had already each fixed in turn, kept here because this change subsumes both and
should not quietly lose their cover.

Hermetic (no Django server, no DB, no tenant routing), and they skip cleanly unless Playwright
and a Chromium build are both available, so a normal suite run (or CI without a browser) is
unaffected. They run for real once a Chromium build is present (see the front-end-testing setup in
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

_PAGE = """<!doctype html><html><head>
<style>#cy {{ width: 1600px; height: 1200px; position: absolute; top: 0; left: 0; }}</style>
</head><body><div id="cy"></div>
<script>{jquery_stub}</script>
<script src="file://{js_dir}/cytoscape.min.js"></script>
<script src="file://{js_dir}/dagre.min.js"></script>
<script src="file://{js_dir}/cytoscape-dagre.js"></script>
<script>
var elements = {elements};
var cy = cytoscape({{ container: document.getElementById('cy'), elements: elements, style: [] }});
</script>
<script src="file://{js_dir}/maps.js"></script>
</body></html>"""


def _node(node_id, label, parent=None, campaign_order=None):
    """One cytoscape node definition, optionally inside a compound campaign node.

    Args:
        node_id (str): the node's id.
        label (str): the label the map draws.
        parent (str): id of the campaign node this belongs to, or None for a campaign-less node.
        campaign_order (int): a ``campaignOrder`` to put in the node's data.

    Returns:
        dict: the node, shaped as elements_dict() emits it.
    """
    data = {"id": node_id, "label": label}
    if parent is not None:
        data["parent"] = parent
    if campaign_order is not None:
        data["campaignOrder"] = campaign_order
    return {"data": data}


def _edge(edge_id, source, target):
    """One cytoscape edge definition.

    Args:
        edge_id (str): the edge's id.
        source (str): id of the node the edge leaves.
        target (str): id of the node the edge enters.

    Returns:
        dict: the edge, shaped as elements_dict() emits it.
    """
    return {"data": {"id": edge_id, "source": source, "target": target}}


# An intro campaign feeding two parallel paths: the intro sits in a vertical band of its own, so
# its column has room on either side that a side-by-side campaign's column does not (#2627).
_STACKED = {
    "nodes": [
        _node("10", "Intro Campaign", campaign_order=0), _node("100", "I0", "10"), _node("101", "I1", "10"),
        _node("20", "Path A", campaign_order=2), _node("200", "A0", "20"), _node("201", "A1", "20"), _node("202", "A2", "20"),
        _node("30", "Path B", campaign_order=1), _node("300", "B0", "30"), _node("301", "B1", "30"), _node("302", "B2", "30"),
    ],
    "edges": [
        _edge("i1", "100", "101"),
        _edge("a1", "200", "201"), _edge("a2", "201", "202"),
        _edge("b1", "300", "301"), _edge("b2", "301", "302"),
        _edge("ia", "101", "200"), _edge("ib", "101", "300"),
    ],
}

# Campaigns of widely different widths side by side: "Wide" branches into three quests and is
# several across, the other two are chains one across (#2675, first report).
_UNEVEN_WIDTH = {
    "nodes": [
        _node("1", "Intro"),
        _node("10", "Wide", campaign_order=3), _node("100", "W0", "10"), _node("101", "W1", "10"),
        _node("102", "W2", "10"), _node("103", "W3", "10"),
        _node("20", "Narrow One", campaign_order=1), _node("200", "P0", "20"), _node("201", "P1", "20"),
        _node("30", "Narrow Two", campaign_order=2), _node("300", "Q0", "30"), _node("301", "Q1", "30"),
    ],
    "edges": [
        _edge("w1", "100", "101"), _edge("w2", "100", "102"), _edge("w3", "100", "103"),
        _edge("p1", "200", "201"), _edge("q1", "300", "301"),
        _edge("iw", "1", "100"), _edge("ip", "1", "200"), _edge("iq", "1", "300"),
    ],
}

# Two campaign-less badges hanging off the SAME quest, so they share a neighbour set (#2675,
# reopened). Re-centring each campaign-less node over the mean x of its neighbours gave both the
# same x and drew them on top of each other; dagre spaces them apart.
_SHARED_NEIGHBOURS = {
    "nodes": [
        _node("1", "Intro"),
        _node("10", "Wide", campaign_order=2), _node("100", "W0", "10"), _node("101", "W1", "10"), _node("102", "W2", "10"),
        _node("20", "Narrow", campaign_order=1), _node("200", "N0", "20"), _node("201", "N1", "20"),
        _node("30", "Badge A"), _node("31", "Badge B"),
    ],
    "edges": [
        _edge("w1", "100", "101"), _edge("w2", "100", "102"),
        _edge("n1", "200", "201"),
        _edge("iw", "1", "100"), _edge("in", "1", "200"),
        _edge("ba", "101", "30"), _edge("bb", "101", "31"),
    ],
}


@skipUnless(HAS_PLAYWRIGHT and _CHROMIUM, "Playwright and a Chromium build are required")
class MapLayoutOverlapRenderTest(SimpleTestCase):
    """No two nodes on a rendered map occupy the same space, whatever shape the map is (#2675).

    dagre spaces everything it places, so this holds as long as nothing moves nodes after it runs.
    The three shapes here are the three that each produced an overlap while something did.
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

    def _render(self, elements):
        """Render a map and return the box of every node on it.

        Campaign boxes are measured from their quests' own extent rather than the compound node's,
        because the compound adds padding that reports neighbouring campaigns as touching when the
        quests themselves are clear.

        Args:
            elements (dict): the nodes and edges to draw.

        Returns:
            list[dict]: one ``{'label', 'x1', 'x2', 'y1', 'y2'}`` per node, campaigns included.
        """
        import json
        html = _PAGE.format(jquery_stub=_JQUERY_STUB, js_dir=self.js_dir, elements=json.dumps(elements))
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as fh:
            fh.write(html)
            html_path = fh.name
        page = self._browser.new_page()
        try:
            page.goto("file://" + html_path)
            page.wait_for_timeout(300)
            return page.evaluate(
                "() => cy.nodes().map(function (n) {"
                "  var b = n.isParent() ? n.children().boundingBox() : n.boundingBox();"
                "  var p = n.parent();"
                "  return { label: n.data('label'), id: n.id(), parent: p.nonempty() ? p.id() : null,"
                "           x1: b.x1, x2: b.x2, y1: b.y1, y2: b.y2 }; })"
            )
        finally:
            page.close()
            os.unlink(html_path)

    def _overlaps(self, boxes):
        """Return a readable description of each pair of boxes that intersect.

        A campaign's box is its quests' extent, so a quest necessarily sits inside its own
        campaign's box. That one pairing is skipped by the compound PARENT relationship rather
        than by geometry: a campaign holding a single quest has exactly that quest's box, so a
        geometric "one contains the other" rule would have to treat identical boxes as nested,
        and identical boxes are the worst collision there is, not an exemption from the check.

        Args:
            boxes (list[dict]): node boxes from `_render`, each carrying its id and parent id.

        Returns:
            list[str]: one entry per overlapping pair, empty when the map is clear. Touching
            edges do not count; only a positive area in both axes does.
        """
        found = []
        for i, first in enumerate(boxes):
            for second in boxes[i + 1:]:
                if first["parent"] == second["id"] or second["parent"] == first["id"]:
                    continue  # a quest inside its own campaign
                across = min(first["x2"], second["x2"]) - max(first["x1"], second["x1"])
                down = min(first["y2"], second["y2"]) - max(first["y1"], second["y1"])
                if across > 0 and down > 0:
                    found.append(
                        f"{first['label']} and {second['label']} overlap by "
                        f"{round(across)}x{round(down)} px"
                    )
        return found

    def test_map_layout__a_campaign_above_others_does_not_collide(self):
        """An intro campaign stacked above two parallel paths leaves every column clear (#2627)."""
        overlaps = self._overlaps(self._render(_STACKED))
        self.assertEqual(overlaps, [], "map nodes overlap: " + "; ".join(overlaps))

    def test_map_layout__campaigns_of_different_widths_do_not_collide(self):
        """A branching campaign beside two chains leaves every column clear (#2675, first report).

        The widths differ by several node-widths here, which is what used to let one campaign
        reach past the gap on either side of another.
        """
        overlaps = self._overlaps(self._render(_UNEVEN_WIDTH))
        self.assertEqual(overlaps, [], "map nodes overlap: " + "; ".join(overlaps))

    def test_map_layout__campaign_less_nodes_sharing_a_neighbour_do_not_collide(self):
        """Two badges hanging off the same quest are drawn apart (#2675, reopened).

        They have identical neighbour sets, so re-centring each over the mean x of its neighbours
        put both at the same x and drew them exactly on top of each other. This is the shape that
        was still overlapping after the earlier fixes, and the one that settled it: nothing moves
        a node after dagre has placed it.
        """
        boxes = self._render(_SHARED_NEIGHBOURS)
        overlaps = self._overlaps(boxes)
        self.assertEqual(overlaps, [], "map nodes overlap: " + "; ".join(overlaps))

        # and specifically: the two badges are not in the same place
        badges = sorted((b for b in boxes if b["label"].startswith("Badge")), key=lambda b: b["x1"])
        self.assertEqual(len(badges), 2)
        self.assertLess(badges[0]["x2"], badges[1]["x1"], "the two badges are not side by side")
