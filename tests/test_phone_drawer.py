"""The phone menu opened, then vanished under its own scrim.

Ethan filmed it on 2026-08-19 (12:28:56Z). Frame by frame, at 20fps, the
recording says something more specific than "the menu is broken":

    t+0.40s   the drawer is fully open and correct, page at full brightness
    t+0.55s   the drawer is GONE and the page is dimmed

The drawer arrived. Then the dim arrived, about nine frames later, and
took the drawer with it. That gap is the tell: the scrim carried
`backdrop-filter: blur(2px)`, a blurred layer gets promoted to the
compositor, and a promoted layer can paint over a transformed sibling
that outranks it on z-index. So the drawer was genuinely on screen and
genuinely painted over — which is why it reproduced on no desktop engine
and why, on paper, the ordering was already right.

The blur is gone (that is `test_the_scrim_carries_no_backdrop_filter`).
But removing one property is a fix aimed at one mechanism, and iOS
promotes `position: fixed` layers on its own schedule for reasons of its
own. So the drawer is now promoted too: two composited layers ARE ordered
by z-index, and 50 beats 45 on every engine. Source order is the third
guard — last painted wins among equals.

THE ONLY INSTRUMENT THAT COULD HAVE CAUGHT THIS IS A PICTURE. Every DOM
fact was correct while the bug was happening: the class was on, the
transform was `translateX(0)`, the rect was at left 0, hit-testing
reached the drawer. `test_the_drawer_actually_paints_where_it_says_it_is`
therefore screenshots the drawer's own rectangle, decodes it in the page,
and asks what colour is actually there. The drawer's panel is
`rgb(10, 10, 19)`; the page behind a 62%-black scrim is darker than the
page, which is darker still. A scrim cannot brighten the page into the
drawer's colour, so the modal pixel tells the two apart.

BROWSER HALVES ARE OPT-IN (`QB_BROWSER_TESTS=1`), for the reason
test_proseflow.py records: Chromium-driving tests inside the full suite
crashed the browser on a busy container, and a flaky test is worse than
no test.

    QB_BROWSER_TESTS=1 python3 tests/test_phone_drawer.py

Run directly: `python3 tests/test_phone_drawer.py`
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()

#: app.js with its comments removed.
#:
#: The comments in this file quote the bug, name the events and explain
#: which approaches were rejected — so a search of the raw source finds
#: the EXPLANATION and reports it as the code. That shape has cost this
#: suite four false failures today, one of them while writing the test
#: below that exists to check for it.
APP_CODE = re.sub(r"(?m)^\s*//.*$", "",
                  re.sub(r"/\*.*?\*/", " ", APP, flags=re.S))

#: The drawer's rule lives in the ≤900px block; `.sidebar` also has a
#: desktop rule, so the phone one is found by the property that only it
#: sets. Anchoring on the text rather than on a line number because the
#: stylesheet moves under this constantly.
def _rule(opener: str) -> str:
    """The declaration block a selector opens. A renamed selector fails
    HERE, by name, rather than as a ValueError from `index` at import
    time with nothing to say about which rule moved."""
    assert opener in CSS, (
        f"the rule this test is about is gone: {opener!r}. It was renamed or "
        "restructured — re-anchor the test rather than deleting it.")
    block = CSS[CSS.index(opener):]
    return block[:block.index("}")]


_DRAWER = _rule(".sidebar { position: fixed; top: var(--topbar-h)")
_SCRIM = _rule("body.menu-open #scrim {")
_TABBAR = _rule(".tabbar { position: fixed; left: 0; right: 0; bottom: 0;")


def _z(block: str) -> int:
    m = re.search(r"z-index:\s*(\d+)", block)
    assert m, "no z-index in:\n" + block
    return int(m.group(1))


def test_the_scrim_carries_no_backdrop_filter():
    """The mechanism itself. A blurred scrim is a promoted scrim, and a
    promoted scrim outranks the drawer on the compositor no matter what
    z-index says."""
    assert "backdrop-filter" not in _SCRIM, \
        "the scrim is a promoted layer again — it will paint over the drawer"


def test_the_tab_bar_carries_no_backdrop_filter_either():
    """THE SAME MECHANISM, THIRD TIME. Ethan filmed it again on
    2026-08-22: mid-scroll the bottom bar paints as an opaque band across
    the MIDDLE of the page, content running on above and below it — a
    promoted layer drawn at a scroll offset the page has already left.

    A blurred layer is a layer with a cached backdrop snapshot, iOS
    promotes position:fixed on its own schedule, and momentum scrolling
    is where the two disagree. The scrim lost its blur for this; the tab
    bar kept one for three more days because nobody thought to look at
    the other fixed element on the page."""
    assert "backdrop-filter" not in _TABBAR, \
        "the tab bar is a promoted layer again — it will smear mid-scroll"


def test_the_tab_bar_is_opaque_without_the_blur():
    """--topbar-bg is 82% opaque and was relying on the blur to stay
    legible over moving text. Removing the blur and keeping a translucent
    background would trade a smear for text showing through the bar."""
    assert "--topbar-bg" not in _TABBAR, \
        "the bar is translucent again with nothing blurring behind it"
    assert "background: color-mix(" in _TABBAR, _TABBAR
    # Built from tokens, so it tracks the light theme too rather than
    # being a dark-mode hex that goes invisible at noon.
    assert "var(--panel)" in _TABBAR and "var(--bg)" in _TABBAR


# --- zoom ---------------------------------------------------------------------
def test_the_page_cannot_be_pinched_or_double_tapped_larger():
    """Ethan, 2026-08-22, with a recording of the fantasy page at four
    scales: "you should not be able too zoom in or out like in this
    video."

    THREE MECHANISMS, AND ALL THREE ARE NEEDED. The meta attribute covers
    Android and the installed home-screen app; iOS Safari in a tab has
    ignored it deliberately since iOS 10, so the gesture events cover
    that; and neither of them stops a double tap, which is what
    `touch-action` is for. Any one alone leaves a way in, which is why
    they are asserted together rather than in three files."""
    vp = HTML[HTML.index('name="viewport"'):]
    vp = vp[:vp.index(">")]
    assert "user-scalable=no" in vp, "the meta tag allows zooming again"
    assert "maximum-scale=1" in vp, vp
    # viewport-fit=cover is what makes the safe-area insets real. Losing
    # it while editing this line puts the tab bar back under the home
    # indicator, which is a different bug with the same one-line cause.
    assert "viewport-fit=cover" in vp, "the notch insets went with it"

    assert "gesturestart" in APP_CODE and "gesturechange" in APP_CODE, \
        "iOS Safari ignores the meta tag — the gesture events are the fix"
    i = APP_CODE.index("gesturestart")
    block = APP_CODE[i:i + 300]
    assert "preventDefault" in block and "passive: false" in block, \
        "a passive listener cannot cancel the gesture"

    body = _rule("body {")
    assert "touch-action: manipulation" in body, \
        "double-tap zoom is back"


def test_the_zoom_block_does_not_cost_scrolling():
    """Cancelling multi-touch through `touchmove` would need a
    non-passive listener on every scroll, which turns off the browser's
    scroll fast path for the whole document — paying for smooth scrolling
    to prevent a zoom. The gesture events cost nothing until a pinch
    actually begins."""
    i = APP_CODE.index("gesturestart")
    block = APP_CODE[max(0, i - 200):i + 400]
    assert "touchmove" not in block, \
        "a non-passive touchmove listener is back on the document"
    # `none` would kill panning as well as zooming.
    assert "touch-action: none" not in _rule("body {")


def test_the_drawer_outranks_the_scrim():
    """On paper this was always true, and on paper is not where the bug
    lived. It still has to stay true: it is the ordering the promotion
    below makes binding."""
    assert _z(_DRAWER) > _z(_SCRIM), \
        f"drawer z-index {_z(_DRAWER)} is not above scrim {_z(_SCRIM)}"


def test_the_drawer_is_promoted_to_its_own_layer():
    """Two composited layers are ordered by z-index. One composited layer
    and one ordinary one are ordered by whatever the compositor decides —
    which is the whole finding."""
    assert "will-change: transform" in _DRAWER, \
        "the phone drawer is no longer promoted; z-index stops being binding"


def test_the_scrim_is_painted_before_the_drawer():
    """Belt to that brace: among equals, last painted wins. `#scrim` must
    come first in the document and `#sidebar` after it."""
    assert HTML.index('id="scrim"') < HTML.index('id="sidebar"'), \
        "the scrim now comes after the drawer in the DOM"


def test_the_phone_opens_the_drawer_from_the_hamburger():
    """THIS USED TO SAY THE OPPOSITE. At ≤760px the hamburger was
    `display: none !important` and the tab bar's Menu reached the drawer
    by clicking that hidden button — a control nobody could see driving
    the one they could.

    Ethan reversed it on 2026-08-22, and for a concrete reason: the top
    bar's icon row had grown past its space and was clipping its own
    earliest icons, so the search button silently stopped existing. "Maybe
    we put it on the bottom bar where the menu button is, then move the
    menu button too be like three bars on the top left." The drawer has
    room up there and the tab bar's fifth slot became a destination, which
    is what a tab bar is for.

    What this file still guards is unchanged: the phone must have exactly
    one way in and it must not be hidden."""
    # EVERY ≤760px block, joined. There are a dozen in this sheet and the
    # browser applies all of them; taking the first found one about
    # something else entirely and concluded the hamburger was unstyled.
    import re as _re
    parts, at = [], 0
    while True:
        i = CSS.find("@media (max-width: 760px)", at)
        if i < 0:
            break
        depth, seen, end = 0, False, None
        for j in range(CSS.index("{", i), len(CSS)):
            if CSS[j] == "{":
                depth += 1
                seen = True
            elif CSS[j] == "}":
                depth -= 1
                if seen and depth == 0:
                    end = j + 1
                    break
        assert end, "a ≤760px block never closes"
        parts.append(CSS[i:end])
        at = end
    assert parts, "no ≤760px block"
    block = "\n".join(parts)
    rules = _re.findall(r"\.menu-toggle[^{]*\{([^}]*)\}", block)
    assert rules, "the phone block says nothing about the hamburger"
    assert any("display: grid" in r for r in rules), (
        "the hamburger is hidden on phones again, and the tab bar no "
        "longer has a Menu button to fall back on — the phone would have "
        "no way into the drawer at all")

    # And nothing clicks a hidden button on its behalf any more.
    assert 'getElementById("tb-menu")' not in APP, (
        "the tab bar still proxies to the toggle; that slot is Search now")
    assert 'id="tb-search"' in HTML


# --------------------------------------------------------------------------
# The browser half: what is actually painted where the drawer says it is.
# --------------------------------------------------------------------------

_PROBE = r"""
import { chromium } from 'playwright';
const PORT = process.argv[2];
// Container flags, for the reason rendercheck.py records: without
// --disable-dev-shm-usage Chromium dies with "Page crashed" on the first
// navigation once /dev/shm fills.
const ARGS = ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'];
let b = null, lastErr = null;
for (const path of [process.env.CHROMIUM_PATH, '/opt/pw-browsers/chromium',
                    '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', undefined]) {
  if (path === null) continue;
  try { b = await chromium.launch({ executablePath: path || undefined, args: ARGS }); break; }
  catch (e) { lastErr = e; }
}
if (!b) throw lastErr;
const p = await b.newPage({ viewport: { width: 390, height: 844 },
                            hasTouch: true, isMobile: true });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0, 140)));
await p.goto(`http://127.0.0.1:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(2500);

// WHAT COLOUR IS ACTUALLY THERE. Screenshot the rectangle, hand it back
// to the page as a data: URL (which does not taint a canvas), and tally
// the pixels. The modal colour is the panel's own background when the
// drawer painted, and a darkened page when something painted over it.
async function faceOf(rect) {
  const buf = await p.screenshot({ clip: rect });
  return await p.evaluate(async (b64) => {
    const img = new Image();
    img.src = 'data:image/png;base64,' + b64;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = img.width; c.height = img.height;
    const g = c.getContext('2d');
    g.drawImage(img, 0, 0);
    const d = g.getImageData(0, 0, c.width, c.height).data;
    const tally = new Map();
    for (let i = 0; i < d.length; i += 4) {
      const k = (d[i] << 16) | (d[i + 1] << 8) | d[i + 2];
      tally.set(k, (tally.get(k) || 0) + 1);
    }
    let best = 0, bestK = 0;
    for (const [k, n] of tally) if (n > best) { best = n; bestK = k; }
    return { modal: [bestK >> 16, (bestK >> 8) & 255, bestK & 255],
             share: best / (d.length / 4) };
  }, buf.toString('base64'));
}

const out = { errs };
// SIBLINGS, AND NOTHING BETWEEN THEM AND THE ROOT THAT ISOLATES. A
// z-index only compares two elements inside the SAME stacking context;
// give their shared parent a transform or an opacity and the drawer's 50
// stops being a promise about the scrim's 45. Both live in `.shell`,
// which is a plain grid container and creates no context — but that is a
// fact about today's stylesheet, so it is measured rather than assumed.
out.ordering = await p.evaluate(() => {
  const isolates = (el) => {
    const cs = getComputedStyle(el);
    if (cs.position !== 'static' && cs.zIndex !== 'auto') return 'z-index';
    if (parseFloat(cs.opacity) < 1) return 'opacity';
    for (const k of ['transform', 'filter', 'backdropFilter', 'perspective',
                     'mask', 'clipPath'])
      if (cs[k] && cs[k] !== 'none') return k;
    if (cs.mixBlendMode !== 'normal') return 'mix-blend-mode';
    if (cs.isolation === 'isolate') return 'isolation';
    if (/paint|layout|strict|content/.test(cs.contain || '')) return 'contain';
    if (/transform|opacity|filter/.test(cs.willChange || '')) return 'will-change';
    if (cs.position === 'fixed' || cs.position === 'sticky') return 'position';
    return '';
  };
  const a = document.getElementById('scrim'), b = document.getElementById('sidebar');
  const walls = [];
  for (let el = a.parentElement; el && el !== document.documentElement;
       el = el.parentElement) {
    const why = isolates(el);
    if (why) walls.push((el.id || el.className || el.tagName) + ': ' + why);
  }
  return { siblings: a.parentElement === b.parentElement,
           parent: (a.parentElement.id || a.parentElement.className || ''),
           order: a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? 'scrim-first' : 'drawer-first',
           walls };
});

// `#menu-toggle`, NOT `#tb-menu`. This probe tapped the tab bar's Menu
// button, which was removed when that slot became Search — and the
// static half of this very file asserts it is gone
// (`getElementById("tb-menu") not in APP`). So the two halves disagreed
// and the browser half timed out for thirty seconds waiting for a
// control the other half requires to be absent. The hamburger is what
// opens the drawer on a phone now, and the test above this one already
// says it must be visible there.
await p.locator('#menu-toggle').tap();
await p.waitForTimeout(900);                   // past the slide

const r = await p.locator('#sidebar').boundingBox();
out.rect = r;
out.open = await p.evaluate(() => {
  const sb = document.getElementById('sidebar');
  return { cls: document.body.classList.contains('menu-open'),
           bg: getComputedStyle(sb).backgroundColor,
           scrim: getComputedStyle(document.getElementById('scrim')).display,
           aria: document.getElementById('menu-toggle').getAttribute('aria-expanded') };
});
// Inset, so the panel's own border and the page beyond it are excluded.
out.face = await faceOf({ x: r.x + 6, y: r.y + 24,
                          width: Math.max(40, r.width - 14),
                          height: Math.min(460, r.height - 48) });
// The browser's own hit-test, which is the finger's question: can a nav
// row in there actually be tapped, or does something intercept it?
try {
  await p.locator('#sidebar .sport-btn').first().click({ trial: true, timeout: 4000 });
  out.reachable = true;
} catch (e) { out.reachable = String(e).slice(0, 160); }

await p.locator('#menu-toggle').tap();
await p.waitForTimeout(900);
out.closed = await p.evaluate(() => ({
  cls: document.body.classList.contains('menu-open'),
  scrim: getComputedStyle(document.getElementById('scrim')).display,
  left: Math.round(document.getElementById('sidebar').getBoundingClientRect().right),
  aria: document.getElementById('menu-toggle').getAttribute('aria-expanded') }));
console.log(JSON.stringify(out));
await b.close();
"""


def _have_node() -> bool:
    try:
        r = subprocess.run(
            ["node", "-e", "import('playwright').then(()=>0,()=>process.exit(1))"],
            capture_output=True, cwd=ROOT, timeout=30)
        return r.returncode == 0
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False


def _run_probe():
    """Serve the real handler and drive one phone-sized page."""
    import rendercheck
    srv, port = rendercheck._serve()
    script = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False,
                                         dir=ROOT) as fh:
            fh.write(_PROBE)
            script = fh.name
        proc = subprocess.run(["node", script, str(port)], cwd=ROOT,
                              capture_output=True, text=True, timeout=180)
    finally:
        if script:
            os.unlink(script)
        srv.shutdown()
    assert proc.returncode == 0, proc.stderr[-1500:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_the_drawer_actually_paints_where_it_says_it_is():
    """The assertion the DOM could not make. Every DOM fact was correct
    while Ethan's recording was failing — class on, transform at zero,
    rect at left 0 — and the drawer was still invisible."""
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    if not _have_node():
        print("      (skipped: no Node/Playwright — install to enable)")
        return
    out = _run_probe()

    o = out["ordering"]
    assert o["siblings"], \
        "the scrim and the drawer are no longer siblings — z-index stops comparing them"
    assert o["order"] == "scrim-first", \
        "the drawer now comes BEFORE the scrim; among equals the scrim would win"
    assert not o["walls"], (
        "something between the drawer and the root builds a stacking context, "
        f"so its z-index no longer outranks the scrim's: {o['walls']}")
    assert out["open"]["cls"], "tapping the tab bar's Menu did not open the drawer"
    assert out["open"]["scrim"] == "block", "no scrim while open"
    assert out["open"]["aria"] == "true", "aria-expanded did not follow the drawer"
    assert round(out["rect"]["x"]) == 0, \
        f"the drawer is not at the left edge: x={out['rect']['x']}"

    want = [int(n) for n in re.findall(r"\d+", out["open"]["bg"])[:3]]
    got = out["face"]["modal"]
    assert got == want, (
        "THE DRAWER IS OPEN AND SOMETHING ELSE IS PAINTED OVER IT.\n"
        f"  the panel's background is rgb{tuple(want)}\n"
        f"  the pixels in its own rectangle are mostly rgb{tuple(got)}\n"
        "  This is Ethan's 2026-08-19 recording. Check that nothing new "
        "promotes the scrim (backdrop-filter, filter, opacity, transform) "
        "and that the drawer still carries will-change: transform.")
    assert out["face"]["share"] > 0.25, \
        (f"only {out['face']['share']:.0%} of the drawer's rectangle is its own "
         "background — it is mostly covered by something")

    assert out["reachable"] is True, \
        f"a nav row inside the open drawer cannot be tapped: {out['reachable']}"

    assert not out["closed"]["cls"], "a second tap on Menu did not close the drawer"
    assert out["closed"]["scrim"] == "none", \
        "THE SCRIM OUTLIVED THE DRAWER — this is the stuck-blurred-screen half"
    assert out["closed"]["left"] <= 0, \
        f"the drawer did not slide back off screen: right edge {out['closed']['left']}"
    assert not out["errs"], f"page errors: {out['errs']}"


def test_no_element_anywhere_carries_backdrop_filter():
    """THE FOURTH TIME WAS A PHONE REBOOT. The scrim, the phone topbar
    and the menu toggle each lost their blur to milder versions of this
    failure — and the sticky topbar kept a blur(16px) that
    body.menu-open flips to position:fixed. Ethan, 2026-08-25, iPhone:
    "anytime I try to click any menu … my whole phone will black screen
    … a little gear spinning … then it'll send me to my lock screen."
    That is an iOS respring: WebKit's GPU process dying under a
    full-width blurred fixed layer re-composited over a transformed
    drawer and stadium photography.

    So the rule stops being per-element: NO live backdrop-filter
    declaration anywhere in the stylesheet. Comments may say the word;
    a declaration may not. The near-opaque --topbar-bg tokens carry the
    frosted look for free."""
    decl = re.compile(r"^[^/*\n]*backdrop-filter\s*:", re.M)
    hits = [m.group(0).strip() for m in decl.finditer(CSS)]
    assert not hits, f"live backdrop-filter declarations: {hits}"


def test_the_stadium_cards_stay_off_the_compositor_on_phones():
    """The respring's SECOND half (2026-08-26 — the blur removal alone
    did not stop it; Ethan: "I clicked on the nfl page then click on
    long shots, my whole iPhone went black"). Two permanent GPU costs
    lived on the stadium strip:

      * `.tilt { will-change: transform }` promoted EVERY card into its
        own compositor layer, each holding a decoded venue photo —
        sixteen textures on an NFL slate, paid by phones that cannot
        hover. Promotion now rides `.tilting`, which only enableTilt
        applies, and enableTilt refuses coarse pointers outright.
      * The SVG stadium scene — two feGaussianBlur filters per card —
        rasterized under every photo, and painted ALONE on every
        off-screen card while its lazy photo had not arrived: filter
        churn exactly during momentum scrolling. `:has(.venue-photo)`
        turns the drawing off whenever the photo ELEMENT exists, and
        vpFall removing the img on total failure brings it back with
        no JavaScript involved."""
    m = re.search(r"/\* pointer tilt on stadium cards \*/.*?\n\.tilt \{[^}]*\}", CSS, re.S)
    assert m and "will-change" not in m.group(0).split(".tilt {")[-1], \
        "will-change is back on the base .tilt class — a layer per card"
    assert ".tilt.tilting { transition: none; will-change: transform; }" in CSS
    assert '!window.matchMedia("(pointer: fine)").matches) return;' in APP, \
        "enableTilt binds on touch screens again"
    m2 = re.search(r"\.stadium-wrap:has\(\.venue-photo\) \.stadium,\s*"
                   r"\.gp-art:has\(\.venue-photo\) \.stadium "
                   r"\{ visibility: hidden; \}", CSS)
    assert m2, "the blurred SVG scene paints under every photo again"
    # visibility, NOT display: the drawing is the card art's SIZING
    # element (the photo is absolute over its box), so display:none
    # collapsed every card and the stadiums vanished (2026-08-26, the
    # day the first cut of this fix shipped).
    assert ":has(.venue-photo) .stadium { display: none" not in CSS, (
        "display:none is back - the photos have no box to fill")


def test_no_view_transitions_on_touch_screens():
    """RESPRING FIX, PART THREE — the part that matches the symptom. A
    view transition snapshots the entire <main> into GPU textures twice
    per navigation, at device resolution, on a page tens of thousands
    of pixels tall. It is the only cost in the site that scales with
    EVERY tap regardless of destination, which is what "anytime I try
    to click any menu or anything" was telling us. Ethan's iPhone
    respring survived the blur removal and the layer diet because
    neither touched this. Both halves are pinned: switchView must
    decline to start one on a coarse pointer, and the stylesheet must
    strip the transition name so a transition started by anything else
    still has nothing to snapshot."""
    i = APP.index("function switchView(name")
    body = APP[i:i + 1600]
    assert 'matchMedia("(pointer: coarse)").matches' in body, \
        "switchView starts full-page snapshots on phones again"
    m = re.search(r"@media \(pointer: coarse\) \{\s*"
                  r"main \{ view-transition-name: none; \}", CSS)
    assert m, "the coarse-pointer view-transition kill switch left the sheet"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    # run_tests.py counts a file's tests by reading "N tests passed" off
    # this line. "all good" matches nothing, so this file scored zero and
    # was still drawn green — say the number instead.
    print(f"\n{ran} tests passed." if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
