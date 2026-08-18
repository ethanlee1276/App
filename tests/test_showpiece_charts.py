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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
