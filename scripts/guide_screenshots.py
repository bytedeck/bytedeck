"""Annotated, cropped screenshots of the running app, for the user guide (docs/).

The guide's screenshots all come from this helper, so they share one look: a red box around the
part a sentence talks about and, where a numbered list in the text goes with the picture, a
numbered red badge with an arrow pointing at it. The callouts are drawn as an SVG overlay in the
page itself, so they land exactly on the element, and the picture is clipped to the region that
matters rather than the whole page. CLAUDE.md ("User guide") has the conventions.

Write a short script per guide page that drives the app with Playwright and calls `shot`:

    import sys
    sys.path.insert(0, "scripts")
    from guide_screenshots import C, browser, go, login, shot, sync_playwright

    with sync_playwright() as p:
        page = login(browser(p), "http://hackerspace.localhost:8000", "owner")
        go(page, "http://hackerspace.localhost:8000/config/")
        label = lambda f: page.locator(f"label[for=id_{f}]")
        shot(page, "docs/images/quick-start/site-settings.png",
             region=[page.locator("h1").first, page.locator("#div_id_access_code")],
             callouts=[C(label("site_name"), 1), C(label("site_name_short"), 2), C(label("access_code"), 3)])

Needs Playwright and a Chromium (`pip install playwright && playwright install chromium`); set
GUIDE_CHROMIUM to use a Chromium already on the machine instead.
"""
import os
from dataclasses import dataclass

from playwright.sync_api import sync_playwright

RED = "#e0262d"
# Django's debug toolbar would sit over the picture
HIDE_CSS = "#djDebugRoot { display: none !important; }"

DRAW_JS = r"""
(spec) => {
  const NS = 'http://www.w3.org/2000/svg';
  const R = 13, PAD = 3, GAP = 3;
  const doc = document.documentElement;
  const W = Math.max(doc.scrollWidth, document.body.scrollWidth);
  const H = Math.max(doc.scrollHeight, document.body.scrollHeight);
  const svg = document.createElementNS(NS, 'svg');
  svg.id = 'guide-annotations';
  svg.setAttribute('width', W); svg.setAttribute('height', H);
  svg.style.cssText = 'position:absolute;left:0;top:0;pointer-events:none;z-index:2147483647;overflow:visible';
  svg.innerHTML = `<defs>
    <marker id="ga-head" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4.2" markerHeight="4.2" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="${spec.color}"/></marker>
    <filter id="ga-shadow" x="-50%" y="-50%" width="200%" height="200%">
      <feDropShadow dx="0" dy="1" stdDeviation="1.2" flood-opacity="0.35"/></filter></defs>`;
  const b = {x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity};
  const grow = (x0, y0, x1, y1) => { b.x0 = Math.min(b.x0, x0); b.y0 = Math.min(b.y0, y0); b.x1 = Math.max(b.x1, x1); b.y1 = Math.max(b.y1, y1); };
  const el = (tag, attrs) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    svg.appendChild(e);
    return e;
  };
  for (const c of spec.callouts) {
    const x = c.rect.x - PAD, y = c.rect.y - PAD, w = c.rect.w + 2 * PAD, h = c.rect.h + 2 * PAD;
    if (c.box) {
      el('rect', {x, y, width: w, height: h, rx: 4, fill: 'none', stroke: spec.color, 'stroke-width': 2.5});
      grow(x - 2, y - 2, x + w + 2, y + h + 2);
    }
    if (c.n === null) continue;
    // the point on the box's edge the arrow ends at, and the direction away from it
    const [ex, ey, dx, dy] = {
      right: [x + w, y + h * c.along, 1, 0], left: [x, y + h * c.along, -1, 0],
      top: [x + w * c.along, y, 0, -1], bottom: [x + w * c.along, y + h, 0, 1],
    }[c.side];
    // inside: the badge sits just within a large box, by the given side, with no arrow
    const off = c.inside ? -(R + 8) : c.dist + R;
    const cx = ex + dx * off + c.dx, cy = ey + dy * off + c.dy;
    const len = Math.hypot(ex - cx, ey - cy);
    if (!c.inside && len > R + GAP + 6) {
      const ux = (ex - cx) / len, uy = (ey - cy) / len;
      el('line', {x1: cx + ux * (R + 1), y1: cy + uy * (R + 1), x2: ex - ux * GAP, y2: ey - uy * GAP,
                  stroke: spec.color, 'stroke-width': 3, 'stroke-linecap': 'round', 'marker-end': 'url(#ga-head)'});
    }
    el('circle', {cx, cy, r: R, fill: spec.color, stroke: '#fff', 'stroke-width': 2, filter: 'url(#ga-shadow)'});
    const t = el('text', {x: cx, y: cy + 0.5, fill: '#fff', 'font-size': 15, 'font-weight': 700, 'text-anchor': 'middle',
                          'dominant-baseline': 'central', 'font-family': 'Helvetica Neue, Helvetica, Arial, sans-serif'});
    t.textContent = c.n;
    grow(cx - R - 3, cy - R - 3, cx + R + 3, cy + R + 4);
  }
  doc.appendChild(svg);
  return {bounds: isFinite(b.x0) ? b : null, W, H};
}
"""


@dataclass
class C:
    """One callout on `target`: a Playwright locator, or a rect dict (x, y, w, h) in document coordinates.

    `n` is the badge's number, matching the numbered list that follows the picture; None draws only
    the box. `side` is where the badge sits (right, left, top or bottom), `dist` the arrow's length,
    `along` where on that side the arrow lands (0 to 1), and `dx`/`dy` nudge the badge. `inside` puts
    the badge just within a large box, with no arrow. `box` False leaves out the box, for buttons that
    touch each other, whose boxes would overlap.
    """
    target: object
    n: object = None
    side: str = "right"
    dist: int = 26
    along: float = 0.5
    dx: int = 0
    dy: int = 0
    box: bool = True
    inside: bool = False


def rect(page, target):
    """`target`'s rect in document coordinates (a rect dict is returned as it is)."""
    if isinstance(target, dict):
        return target
    target.scroll_into_view_if_needed()
    box = target.bounding_box()
    sx, sy = page.evaluate("[window.scrollX, window.scrollY]")
    return {"x": box["x"] + sx, "y": box["y"] + sy, "w": box["width"], "h": box["height"]}


def union(rects):
    """The smallest rect holding every rect in `rects`, to box several elements as one."""
    x0 = min(r["x"] for r in rects)
    y0 = min(r["y"] for r in rects)
    x1 = max(r["x"] + r["w"] for r in rects)
    y1 = max(r["y"] + r["h"] for r in rects)
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def shot(page, path, region, callouts=(), pad=10, trim=None):
    """Draw `callouts`, then save the part of the page covering `region` and the callouts to `path`.

    `region` is a locator or rect, or a list of them: the picture is the smallest rectangle holding
    them all, plus `pad` pixels. `trim` (a dict of left/top/right/bottom pixels) cuts that back, for
    an element whose margin would bring a sliver of its neighbour into the picture.
    """
    regions = [rect(page, r) for r in (region if isinstance(region, (list, tuple)) else [region])]
    specs = [{"rect": rect(page, c.target), "n": None if c.n is None else str(c.n), "side": c.side, "dist": c.dist,
              "along": c.along, "dx": c.dx, "dy": c.dy, "box": c.box, "inside": c.inside} for c in callouts]
    page.evaluate("() => document.getElementById('guide-annotations')?.remove()")
    drawn = page.evaluate(DRAW_JS, {"callouts": specs, "color": RED})
    r = union(regions)
    x0, y0, x1, y1 = r["x"] - pad, r["y"] - pad, r["x"] + r["w"] + pad, r["y"] + r["h"] + pad
    trim = trim or {}
    x0, y0 = x0 + trim.get("left", 0), y0 + trim.get("top", 0)
    x1, y1 = x1 - trim.get("right", 0), y1 - trim.get("bottom", 0)
    if drawn["bounds"]:
        bb = drawn["bounds"]
        x0, y0, x1, y1 = min(x0, bb["x0"] - 4), min(y0, bb["y0"] - 4), max(x1, bb["x1"] + 4), max(y1, bb["y1"] + 4)
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(drawn["W"], int(x1 + 0.999)), min(drawn["H"], int(y1 + 0.999))
    page.screenshot(path=path, clip={"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}, full_page=True)
    page.evaluate("() => document.getElementById('guide-annotations')?.remove()")
    print(f"saved {path} {x1 - x0}x{y1 - y0}")


def browser(p):
    """A headless Chromium: GUIDE_CHROMIUM's, or Playwright's own."""
    return p.chromium.launch(executable_path=os.environ.get("GUIDE_CHROMIUM") or None,
                             args=["--no-proxy-server", "--disable-background-networking"])


def login(browser, base, username, password="password", width=1100, height=1400):
    """A page on deck `base`, signed in as `username` (None stays signed out), the debug toolbar hidden.

    1100 pixels wide is the guide's standard: the app's desktop layout, at a width the guide's
    column shows without shrinking text much. The tall viewport keeps most crops on one screen.
    """
    ctx = browser.new_context(viewport={"width": width, "height": height})
    ctx.add_init_script(f"""document.addEventListener('DOMContentLoaded', () => {{
        const s = document.createElement('style'); s.textContent = `{HIDE_CSS}`; document.head.appendChild(s); }});""")
    page = ctx.new_page()
    page.on("dialog", lambda d: d.accept())
    if username:
        page.goto(base + "/accounts/login/")
        page.fill("input[name=login]", username)
        page.fill("input[name=password]", password)
        page.click("button[type=submit], input[type=submit]")
        page.wait_for_load_state("networkidle")
    return page


def go(page, url, wait=400):
    """Open `url` and let it settle."""
    page.goto(url)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(wait)


def readable_message(page):
    """The page's flash message, the window first narrowed so the message wraps to a width the guide shows legibly."""
    page.set_viewport_size({"width": 760, "height": 1400})
    page.wait_for_timeout(400)
    return page.locator(".alert.alert-dismissible:visible").first


__all__ = ["C", "browser", "go", "login", "readable_message", "rect", "shot", "sync_playwright", "union"]
