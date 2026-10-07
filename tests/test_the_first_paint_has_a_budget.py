"""The first visit has a byte budget, and the first screen is not left waiting.

Audit 2026-09-30, P1-11 / F-3 / O15 (roadmap #32). One 460 KB-gz script
plus a 152 KB-gz chart library loaded synchronously before the first paint;
the Home hero was `loading="lazy"`; fonts waited for the stylesheet; board
art and fonts carried no cache lifetime; 13 MB of unreferenced renders sat
under the web root; the venue art shipped as 150-510 KB JPEGs. Measured
2026-09-30 after this change: app.js trims to 453 KB gz and the boot path
(index + styles + visuals + app + teams) to ~580 KB, from ~730 KB.

Splitting the standalone views out of app.js — the rest of the audit's
<400 KB target — is the multi-day part of #32 and is not done here; this
budget is what stops the number growing back meanwhile.
"""

import gzip
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WEB = ROOT / "web"
HTML = (WEB / "index.html").read_text()

#: KB, gzip -9 of the TRIMMED copy (engine/shrink), i.e. what a phone gets.
#: app.js was raised 2026-10-03 from 470 by the NHL team page and the Edge
#: Hunter panel (~1 KB). The first visit came DOWN the same day, 603 -> 590:
#: index.html is served without its comments now (29 -> 11 KB gz), and the
#: budget keeps the saving rather than spending it.
#: 472 -> 476 on 2026-10-04 by the pick page's case section (pickCaseHTML:
#: the facts sorted for the bet, the corners he sees, the back-and-forth
#: script — ~2.5 KB), the change Ethan asked for that day.
#: 476 -> 477 on 2026-10-04 by Ethan's "do all of it" list: the research
#: box, the price-move alert, the why line on Most Likely rows and the
#: Record page's "This week" card (+0.6 KB gz together).
#: 477 -> 478 on 2026-10-06 by the Status page's Kalshi trader card
#: (kalshiCardHTML: mode, today's orders, record, the Pikkit link —
#: +0.37 KB gz; the file sat 0.14 KB under 477 before it).
#: 478 -> 479 on 2026-10-06 by the Verify page (renderVerify: the chain's
#: anchors with their OpenTimestamps proofs and each day's sealed picks —
#: +1.07 KB gz), Ethan's "do 2" the same evening.
#: 479 -> 480 on 2026-10-06 by Bet it and the Discord page (betItHTML on
#: the pick page, the Most Likely cards, the Edge rows and the Pick of the
#: Day; the site-posted channels and the latest #record posts). Told to Ethan.
#: 480 -> 485 on 2026-10-06 by the Feed (Ethan: "a social page where users
#: can make parlays and share them … a tail button … likes … comments … a
#: bio"): renderFeed, the post cards, the Tail box, comments and the
#: profile — +4.3 KB gz. Told to Ethan.
#: 485 -> 481 on 2026-10-07: the Feed moved out to js/social.js, loaded on
#: first use like the chart library (Ethan: "a full social feature …
#: profiles for users" — 13 KB gz that no first visit should carry). What
#: stays is the loader, the route and two icons. Told to Ethan.
#: 481 -> 483 on 2026-10-07 by the Bet it sheet (Ethan, from his phone, at
#: a black panel: "a box with … all the sportsbooks logos that we offer"):
#: the book table with each book's colours, the tile renderer and the
#: sheet that opens on its own layer — +1.35 KB gz. Told to Ethan.
#: 483 -> 484 on 2026-10-07 by the Watch button (Ethan: "link you to
#: whatever streaming service is hosting that game"): the table of where
#: each carrier streams and the button on the live card and the
#: play-by-play page — +1.2 KB gz. Told to Ethan.
#: 484 -> 485 on 2026-10-07 by the second Bet it/Watch pass (Ethan: "real
#: Sportsbook logos … whatever else u think to add"): the icon manifest
#: reader, the best-price and your-book tags, Watch before kickoff on the
#: game page — +0.3 KB gz. Told to Ethan.
#: 485 -> 486 on 2026-10-07 by Watch linking to the game itself (MLB.TV
#: and Gameday by gamePk, ESPN Gamecast by event id) and team search for
#: every league (Ethan: "all sports should be able to search teams") —
#: +0.3 KB gz. Told to Ethan.
APP_JS_BUDGET_KB = 486
#: 590 -> 591 on 2026-10-04 by the NHL play-by-play rows and the Live tab's
#: NHL chip fix (+0.17 KB gz; the boot path sat 43 bytes under 590).
#: 591 -> 592 on 2026-10-04 by the same four (+0.27 KB gz on the boot path).
#: 592 -> 594 on 2026-10-06 by the Verify page: its section in index.html
#: and renderVerify in app.js, +1.2 KB gz on the boot path together.
#: 594 -> 595 on 2026-10-06 by Bet it and the Discord page: the same
#: JavaScript as the app.js bump above plus their styles. Told to Ethan.
#: 595 -> 596 on 2026-10-06 by the Bet it box (every book that has the bet,
#: Ethan: "a box that shows all the different sports books"). Told to Ethan.
#: 596 -> 601 on 2026-10-06 by the Feed: the JavaScript in the app.js bump
#: above plus its styles and its section (+4.6 KB gz). Told to Ethan.
#: 601 -> 596 on 2026-10-07: its JavaScript and styles now load on first
#: use (js/social.js, css/social.css). Told to Ethan.
#: 596 -> 597 on 2026-10-07 by one profile for the whole site (Ethan: "it
#: should all be one main profile"): the top-bar chip in the profile's
#: colour, the Account page as the profile, the streak board's name. +0.3
#: KB gz after Social's own icons moved out of app.js to pay for most of
#: it; the boot path sat 0.03 KB under 596 before. Told to Ethan.
#: 597 -> 599 on 2026-10-07 by the Bet it sheet: the app.js bump above
#: plus the sheet's and the tiles' styles (+1.1 KB gz all told). Told to Ethan.
#: 599 -> 600 on 2026-10-07 by the Watch button: the app.js bump above
#: plus its styles. Told to Ethan.
#: 600 -> 601 on 2026-10-07 by the same pass. Told to Ethan.
#: 601 -> 602 on 2026-10-07 by the app.js bump above (Watch to the game,
#: team search in every league). Told to Ethan.
BOOT_BUDGET_KB = 602


def _gz_trimmed(rel: str) -> int:
    from engine import shrink
    text = (WEB / rel).read_text()
    if rel in shrink.FILES:
        text = shrink.trimmed(rel, text)
    return len(gzip.compress(text.encode(), 9))


def test_app_js_stays_inside_its_budget():
    kb = _gz_trimmed("js/app.js") / 1024
    assert kb <= APP_JS_BUDGET_KB, f"app.js is {kb:.0f} KB gz trimmed — over {APP_JS_BUDGET_KB}"


def test_the_boot_path_stays_inside_its_budget_and_carries_no_chart_library():
    scripts = re.findall(r'<script src="([^"]+)"', HTML)
    assert not any("apexcharts" in s or "echarts" in s for s in scripts), \
        "a chart library is back in the boot path"
    total = _gz_trimmed("index.html") + _gz_trimmed("css/styles.css")
    for s in scripts:
        rel = s.split("?")[0]
        total += _gz_trimmed(rel) if (WEB / rel).exists() else 0
    kb = total / 1024
    assert kb <= BOOT_BUDGET_KB, f"the first visit is {kb:.0f} KB gz — over {BOOT_BUDGET_KB}"


def test_apex_loads_on_first_use():
    vis = (WEB / "js" / "visuals.js").read_text()
    i = vis.index("function mountGlossCharts(")
    body = vis[i:vis.index("\n}\n", i)]
    assert "loadApex()" in body and 'querySelector("[data-gloss-curve]")' in body
    assert 's.src = "vendor/apexcharts.min.js"' in vis


def test_the_hero_is_eager_and_the_body_font_is_preloaded():
    app = (WEB / "js" / "app.js").read_text()
    for fn in ("potdBallArt", "potdVenueArt"):
        i = app.index(f"function {fn}(")
        body = app[i:app.index("\n}\n", i)]
        assert 'fetchpriority="high"' in body and 'loading="lazy"' not in body, fn
    assert '<link rel="preload" href="fonts/archivo-narrow.woff2" as="font"' in HTML
    assert HTML.index('rel="preload"') < HTML.index('rel="stylesheet"')


def test_art_and_fonts_are_cached_and_the_inbox_is_not_served():
    caddy = (ROOT / "deploy" / "Caddyfile").read_text()
    assert '@img path /img/*' in caddy and 'header @img Cache-Control "public, max-age=604800"' in caddy
    assert 'header @fonts Cache-Control "public, max-age=31536000, immutable"' in caddy
    assert "@incoming path /img/venues/incoming/*" in caddy and "respond @incoming 404" in caddy


def test_every_venue_variant_has_its_webp_and_the_page_asks_for_it():
    variants = WEB / "img" / "venues" / "variants"
    jpgs = sorted(variants.glob("*.jpg"))
    assert jpgs
    for j in jpgs:
        w = j.with_suffix(".webp")
        assert w.exists(), f"{w.name} missing — venueSrc serves it, so the card would break"
        assert w.stat().st_size < j.stat().st_size
    app = (WEB / "js" / "app.js").read_text()
    line = app[app.index("const venueSrc = "):]
    line = line[:line.index("\n")]
    assert '.jpg$/, "$1.webp")' in line
    assert "_webp(done, out)" in (ROOT / "tools" / "venues_ingest.py").read_text(), \
        "the ingest must write the webp it serves"


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
