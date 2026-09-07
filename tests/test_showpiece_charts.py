"""The vendored chart engines and the rules that keep them honest.

Ethan, 2026-08-18: "is there any plugins or softwares…" and then
"start on the Echarts and work down." Two engines are vendored into
web/vendor (our own server serves them — no CDN, the LAN works
offline), and both follow one contract, defended here:

  * ENHANCEMENT, NEVER DEPENDENCY. The hand-drawn markup ships in the
    page and stays there; the library only upgrades it in place. A
    missing vendor file must leave the site exactly as it was.
  * THE BOOT PATH STAYS LIGHT. ApexCharts (~560KB) rides the shell;
    ECharts is a full megabyte and is lazy-injected by the first panel
    that needs it — it must appear in NO script tag and NO shell cache.
  * TOKENS, NOT LIBRARY DEFAULTS. Colors are read live from the theme
    custom properties at mount time, so the charts flip with the theme.

Run directly: `python3 tests/test_showpiece_charts.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def test_both_engines_are_vendored_not_linked_from_a_cdn():
    for f in ("apexcharts.min.js", "echarts.min.js"):
        path = os.path.join(ROOT, "web", "vendor", f)
        assert os.path.getsize(path) > 100_000, f
    html = _read("web", "index.html")
    assert "cdn.jsdelivr" not in html and "unpkg.com" not in html
    assert "cdnjs" not in html


def test_apex_rides_the_shell_and_echarts_stays_out_of_the_boot_path():
    html = _read("web", "index.html")
    assert 'src="vendor/apexcharts.min.js"' in html
    i = html.index("vendor/apexcharts.min.js")
    assert i < html.index('src="js/visuals.js"'), \
        "the mount helpers read window.ApexCharts — the engine loads first"
    assert "echarts.min.js" not in html, \
        "a megabyte does not belong in the boot path; loadECharts lazies it"
    sw = _read("web", "sw.js")
    assert "/vendor/apexcharts.min.js" in sw
    assert "echarts" not in sw, "and it stays out of the shell cache too"


def test_a_missing_vendor_file_leaves_the_fallbacks_standing():
    vis = _read("web", "js", "visuals.js")
    i = vis.index("function mountGlossCharts(")
    assert "if (!window.ApexCharts) return;" in vis[i:i + 400]
    j = vis.index("function loadECharts(")
    block = vis[j:j + 700]
    assert 's.onerror = () => resolve(null);' in block, \
        "a failed script load must resolve null, not hang or throw"
    k = vis.index("async function mountEChartsPanels(")
    assert "if (!ec) return;" in vis[k:vis.index("for (const el of nodes)", k)]


def test_the_money_charts_wrap_their_svg_fallbacks():
    app = _read("web", "js", "app.js")
    assert app.count("data-gloss-curve=") >= 3, \
        "home perf, My Bets and Bankroll each carry an upgradeable curve"
    assert app.count("mountGlossCharts(host)") >= 3
    # Each wrapper still contains a hand-drawn chart to fall back on.
    for anchor in ("perf-spark", "bk-curve-net"):
        i = app.index(anchor)
        seg = app[i - 1200:i + 1200]
        assert "data-gloss-curve" in seg, anchor


def test_the_replay_panel_upgrades_and_keeps_its_bars():
    app = _read("web", "js", "app.js")
    i = app.index("The replay")
    seg = app[i - 400:i + 2600]
    assert "data-echart-gauge" in seg and "data-echart-hist" in seg
    # The div-bar histogram LIVES INSIDE the upgradeable container, so a
    # machine that never loads the engine sees the panel it always saw.
    hist = seg[seg.index("data-echart-hist"):]
    assert "gp-sim-bar" in hist[:900]
    assert "mountEChartsPanels(host)" in app
    css = _read("web", "css", "styles.css")
    assert ".gp-sim-gauge:not([data-echarted]) { display: none; }" in css, \
        "an unmounted gauge must take no space — the fallback panel owns it"


def test_the_charts_wear_the_theme_tokens_not_library_defaults():
    vis = _read("web", "js", "visuals.js")
    for fn in ("mountGlossCharts", "mountEChartsPanels"):
        i = vis.index(f"function {fn}" if fn == "mountGlossCharts"
                      else f"async function {fn}")
        seg = vis[i:i + 4600]
        assert "getComputedStyle(document.documentElement)" in seg, fn
    # ECharts panels: no hardcoded hex colors — every color is a token
    # read (the gradient alpha suffix rides on a token, not a literal).
    i = vis.index("async function mountEChartsPanels(")
    seg = vis[i:]
    import re
    assert not re.search(r'"#[0-9A-Fa-f]{3,8}"', seg), \
        "a hardcoded color in the showpiece layer bypasses the theme"


# --- a finger is not a cursor -------------------------------------------------
def _place_fn():
    vis = _read("web", "js", "visuals.js")
    i = vis.index("function place(e) {")
    return vis[i:vis.index("\n  }", i) + 4]


def test_the_value_label_is_not_placed_under_the_finger():
    """Ethan, 2026-08-22, on the popup's bar chart: "when you hold your
    finger on the graph too see the number, my finger is in the way and i
    cant see the number."

    The label went 14px right and 30px above the pointer. That is right
    for a MOUSE — a cursor is a few pixels of arrow and the hand is
    nowhere near the screen. A fingertip covers roughly 45px and the hand
    behind it covers everything below and to the right of the contact
    point, which is precisely where those two offsets put the answer."""
    fn = _place_fn()
    assert "pointerType" in fn, "touch and mouse are still placed the same"
    assert "FINGER" in fn, "no allowance for what a fingertip hides"
    vis = _read("web", "js", "visuals.js")
    i = vis.index("const FINGER =")
    px = int(vis[i:i + 40].split("=")[1].split(";")[0])
    assert px >= 40, f"{px}px does not clear a fingertip"


def test_a_chart_near_the_top_puts_the_label_beside_the_finger():
    """Below is under the same finger. Falling back downward would be
    the original bug wearing a different offset."""
    fn = _place_fn()
    above = fn.index("e.clientY - h - FINGER")
    fallback = fn[above:]
    assert "e.clientX + FINGER" in fallback, \
        "the no-room-above case does not move sideways"
    assert "e.clientY + " not in fallback.split("} else {")[0], \
        "it falls back to BELOW the finger, which the finger also covers"


def test_the_mouse_placement_is_left_alone():
    """Nothing was wrong with it, and a cursor gains nothing from a 46px
    gap it has to travel to read."""
    fn = _place_fn()
    mouse = fn[fn.index("} else {"):]
    assert "e.clientX + 14" in mouse and "e.clientY - 30" in mouse


def test_the_label_never_leaves_the_screen():
    fn = _place_fn()
    assert "window.innerWidth" in fn and "Math.max(8" in fn


def test_the_line_chart_scrubber_measures_from_the_finger_too():
    """Ethan, after the bar-chart fix: "it also does that for to the line
    graph for the record page and the record line graph we show on the
    reccomended page."

    Same complaint, different code path — and the reason both existed is
    that neither measured from the thing in the way. The scrubber placed
    its label ten pixels above the SVG's TOP EDGE, which is plenty of
    room on the tall record chart and nowhere near enough on a
    sparkline: at 40px tall, a finger in the middle of it leaves a 30px
    gap and a fingertip covers 46. Measured in Chromium — tall chart
    120px of clearance, sparkline 30px before this and 46px after."""
    vis = _read("web", "js", "visuals.js")
    i = vis.index("function show(svg,")
    fn = vis[i:vis.index("\n  }", i) + 4]
    assert "clientY" in vis[i:i + 60], \
        "show() still only knows where the finger is horizontally"
    assert "clientY - th - FINGER" in fn, \
        "the label is placed from the chart edge, not from the finger"
    assert "rect.top - th - 10" in fn, \
        "the chart-relative placement is gone — a mouse gains nothing " \
        "from a 46px gap it has to travel to read"


def test_both_tooltips_agree_on_what_a_finger_hides():
    """Two numbers for the same finger would mean one of them is wrong."""
    vis = _read("web", "js", "visuals.js")
    assert vis.count("const FINGER =") == 1, \
        "the clearance is declared twice — they will drift"
    # Each function's OWN body, brace-matched to its closing "\n  }".
    # A fixed-width window would pass or fail on how long the comments
    # inside happen to be, which is the trap this suite keeps falling
    # into — including in the first draft of this very test, where 1400
    # characters fell 102 short.
    for marker in ("function place(e) {", "function show(svg,"):
        j = vis.index(marker)
        body = vis[j:vis.index("\n  }", j) + 4]
        assert "FINGER" in body, f"{marker} does not use the shared clearance"


def test_the_scrubber_also_moves_aside_near_the_top():
    vis = _read("web", "js", "visuals.js")
    i = vis.index("function show(svg,")
    fn = vis[i:vis.index("\n  }", i) + 4]
    assert "snapX + FINGER" in fn, "no sideways fallback"
    assert "snapX - tw - FINGER" in fn, "it can only move one way"


def test_a_touch_that_becomes_a_scroll_does_not_strand_the_label():
    """`pointercancel` fires and `pointerout` does not, which left the
    number sitting over whatever scrolled underneath it."""
    vis = _read("web", "js", "visuals.js")
    i = vis.index("function place(e) {")
    block = vis[i:i + 3000]
    assert "pointercancel" in block, "a cancelled touch leaves it on screen"
    assert '"scroll"' in block, "scrolling leaves it on screen"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
