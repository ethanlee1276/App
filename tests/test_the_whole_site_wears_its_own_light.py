"""The whole site wears its own light: a soft gold behind every page, a club's colour behind a club's (SITEBG1).

Ethan, 2026-11-16: "also how i had you do with the player page and live page
with the team colors in the backround to make the page look nicer. we should do
that for the whole site. we can add a subtle gold gradient or something like
that in the backround to match the site. we can get creative with it and make
the site look nicer and start matching other stuff."

One fixed layer under every page (index.html .ambient, styles.css "THE SITE'S
OWN LIGHT"): the brand's gold from the top of the screen, an amber ember low in
the far corner, a breath of gold on the near side. A player's or a team's page
lays its club's colour over it (.amb-club, drawn inside the page's header), and
the team page's header wears the player page's band in its club's colours. The
game page's wash covers both.
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from _app import styles_css  # noqa: E402

HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
CSS = styles_css()


def _rule(css, selector):
    i = css.index("\n" + selector + " {") + 1
    return css[i:css.index("}", i)]


def test_one_layer_sits_under_every_page():
    body = HTML[HTML.index("<body>"):]
    assert body.index('<div class="ambient" aria-hidden="true"></div>') < body.index('<header class="topbar">'), \
        "the first thing in the body, so every page and the club's light paint over it"
    assert HTML.count('class="ambient"') == 1
    layer = _rule(STYLES, ".ambient, .amb-club")
    for want in ("position: fixed", "inset: 0", "z-index: -1", "pointer-events: none"):
        assert want in layer, want
    assert "background: var(--amb-top), var(--amb-low), var(--amb-side)" in _rule(STYLES, ".ambient")
    assert "body.gp-on .ambient { display: none; }" in STYLES, "the game page's wash is its own"


def test_the_light_is_the_brand_s_gold_in_both_themes_and_never_moves():
    dark = STYLES[STYLES.index("\n:root {"):STYLES.index(':root[data-theme="light"] {')]
    assert "--amb-1: var(--gold);" in dark, "the site's own gold, which the light theme deepens"
    light = STYLES[STYLES.index(':root[data-theme="light"] .ambient {'):]
    light = light[:light.index("}")]
    assert "--amb-top:" in light and "--amb-low:" in light, "paper takes its own strength, on the layer"
    theme = STYLES[STYLES.index(':root[data-theme="light"] {'):]
    assert "--amb-" not in theme[:theme.index("\n}")], "none in the theme's tokens, which the game page resets"
    section = STYLES[STYLES.index("THE SITE'S OWN LIGHT (SITEBG1"):]
    assert ':root[data-theme="light"] .amb-club {\n  --amb-club-top:' in section, "and a club's light on paper too"
    rules = section.split("========================================================================== */", 1)[1]
    for no in ("animation", "transition", "backdrop-filter", "filter: blur"):
        assert no not in rules, no
    # Each glow faint: the gold's strongest stop a fifth of the colour, at most.
    tops = [int(x) for x in re.findall(r"--amb-1\) (\d+)%", dark + light)]
    assert tops and max(tops) <= 20, tops


def test_a_club_s_page_lays_its_colour_over_the_gold():
    club = _rule(STYLES, ".amb-club")
    assert "var(--amb-club-top), var(--amb-club-low), var(--bg)" in club, "the club's light covers the gold under it"
    # Defined ON the layer: a gradient defined on :root is worked out there, where no club's colour is
    # set, and every club page wore the gold (the first cut did).
    assert "--amb-club-top: radial-gradient(" in club and "color-mix(in oklab, var(--amb-c) 34%, transparent)" in club
    root = STYLES[STYLES.index("\n:root {"):STYLES.index(':root[data-theme="light"] {')]
    assert "--amb-c" not in root and "--amb-c: var(--amb-1);" in club, "its own default, on the layer"
    pp = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")
    hero = pp[pp.index("function plrHeroHTML("):pp.index("function plrTabsHTML(")]
    assert '<div class="amb-club" style="--amb-c:${escapeAttr(club.color)}" aria-hidden="true"></div>' in hero, \
        "inside the header: a redrawn header (host.outerHTML) brings its own and leaves none behind"
    assert "raw[0] === \"#\" ? raw : `#${raw}`" in pp, "a colour a feed wrote without its hash still reads"
    more = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")
    head = more[more.index("function teamHeaderHTML("):more.index("function teamGameWho(")]
    assert 'class="tm-head${c ? " tm-band" : ""}"' in head and '<div class="amb-club" style="--amb-c:' in head
    band = CSS[CSS.index(".tm-head.tm-band {"):]
    band = band[:band.index("}")]
    assert "--tm-band: linear-gradient(118deg, color-mix(in oklab, var(--tm-c) 78%, var(--night-3))" in band, \
        "the player page's band, in the team's colour"
    assert "color: var(--night-text)" in band


def test_a_print_drops_the_light():
    assert "@media print { .ambient, .amb-club { display: none; } }" in STYLES


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
