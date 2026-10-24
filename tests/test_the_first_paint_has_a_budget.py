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
#: 486 -> 487 on 2026-10-08 by the Gamecast's door (Ethan, with ESPN's
#: app on a live game: "I want the page to look like ESPN's app"): the
#: tab set, the loader and the hero's record and carrier — the rooms
#: themselves load on first use (js/gamecast.js, css/gamecast.css), so a
#: first visit carries none of them. +0.4 KB gz. Told to Ethan.
#: 487 -> 489 on 2026-10-09 by the lag fixes (Ethan: "the site feel super
#: laggy and not feeling snappy or quick", then "switching pages will also
#: take a couple seconds"): one settle pass per frame instead of four
#: whole-page observers, the league memory that redraws a sport at once,
#: the off-screen pages drawn when opened, the remembered date formatters
#: and the phone-sized renders' chooser — +2.0 KB gz of code that makes
#: every page cheaper to run. Told to Ethan.
#: 489 -> 490 on 2026-10-09 by the first-visit pass (Ethan: "now make the
#: first visit to a sport faster too … everything needs to be faster"):
#: the other leagues' light copies fetched while idle, the whole board
#: asked for alongside the light one, paid files shared and never asked
#: for twice — +1.0 KB gz. The dead-code sweep that would have paid for
#: it found 0.6 KB in three functions, two of them pinned. Told to Ethan.
#: 490 -> 492 on 2026-10-11 by the password work (Ethan: "put in your
#: password twice ... add an option for forget a password"): the second
#: password box and its match check, Enter-to-submit, the Forgot password
#: links, and the reset page's three states — +1.86 KB gz (489.61 ->
#: 491.47). Told to Ethan.
#: 492 -> 493 on 2026-10-12 by Ask's parlay grader (Ethan: "users can upload
#: a screenshot of there parlay and it will rank it"): the attach sheet's
#: upload row, the loader and the graded turn — +0.41 KB gz (491.996 ->
#: 492.407). The upload and the card load on first use (js/slip.js,
#: css/slip.css). Told to Ethan.
#: 493 -> 494 on 2026-10-13 by the profit calendar opening on this month
#: (Ethan: "the mlb profit calander isn't updating, it's stuck on
#: September"): the month we are in drawn even with nothing settled, and
#: the line saying whether its bets are waiting on results or none was
#: placed — +0.28 KB gz (492.892 -> 493.175). Told to Ethan.
#: 494 -> 495 on 2026-10-13 by the UFC card's line read (Ethan: "ufc is
#: missing stuff"): one line on the pick and pass cards saying where the
#: bout's line opened and where it is now, from the snapshots stored since
#: 2026-08-10 — +0.05 KB gz (493.983 -> 494.032), the file
#: having sat 17 bytes under 494. Told to Ethan.
#: 495 -> 496 on 2026-10-15 by the Toolbox and the report card (Ethan, of
#: sixteen ideas: "do every one for every sport"): the loader, the page's
#: door and the report card's slot in My Bets. The tools themselves load on
#: first use (js/extras.js, css/extras.css) — +0.31 KB gz (494.883 ->
#: 495.197). Told to Ethan.
#: 496 -> 497 on 2026-10-19 by the game report (Ethan: "I want a full layed
#: out detailed explanation for every nfl game just like how the report
#: is"): the loader, the stand-in line, the fallback to the old page when
#: it fails, and the game page stepping the scan and the plan's narrative
#: aside for it — +0.61 KB gz (495.502 -> 496.109). The report itself, 3 KB
#: gz with its styles, loads on first use (js/report.js, css/report.css);
#: drawn here it was +1.18. Told to Ethan.
#: 497 -> 498 on 2026-10-22 by fantasy reading the NFL board (Ethan: "make
#: sure we wrap that into it how it should be"): the loader, the week on
#: each lineup row, the dossier's hook and the full profile keeping its
#: "This week" block, which it used to drop — +0.64 KB gz (496.483 ->
#: 497.122). The room, the pickups and the notes load on first use
#: (js/fantasyweek.js, 5.6 KB gz); drawn here they were +3.5. Told to Ethan.
#: 498 -> 499 on 2026-10-23 by the iPhone Duo (Ethan: "Make app work
#: seamlessly with iPhone duo ... The big screen we can do a desktop sort of
#: view"): the open screen's shape, shared by the header, the phone test and
#: the drawer, and the block at the top of the screen kept in place across a
#: fold — +0.97 KB gz (497.965 -> 498.938). Told to Ethan.
#: 499 -> 500 on 2026-10-24 by every fold and flip (Ethan: "make it unique
#: for that phone"): the list beside its pick on a wide open screen, the
#: Fold's near-square inner screen as an open shape, and the split dropped
#: when the screen folds — +0.30 KB gz (498.938 -> 499.24). Told to Ethan.
#: 500 -> 460 on 2026-10-24 — DOWN, and kept down. Ethan's "build
#: everything" (docs/IDEAS.md, "split app.js further"): the Fantasy room
#: (draft kit, mock draft, cheat sheet, waivers, the calendar, the league
#: desks — 186 declarations, chosen by TypeScript's own reading of which
#: ones nothing outside Fantasy calls) moved to js/fantasy.js, loaded on
#: first use, as Rocket Radar did to js/memes.js. 493.6 -> 450.5 KB gz.
#: 460 -> 290 on 2026-10-24 — DOWN again, and kept down. Ethan's "keep going
#: and finish everything": the Record page (js/record.js), the game, pick
#: and play-by-play pages (js/detail.js), the account pages (js/account.js)
#: and the rest of the More menu (js/more.js) load on first use, each
#: chosen the same way and checked to run on top of app.js
#: (tests/test_app_loads.py). 450.5 -> 284.2 KB gz.
APP_JS_BUDGET_KB = 290
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
#: 602 -> 603 on 2026-10-08 by the Gamecast's door: the app.js bump above
#: and the hero's two rules (the record, the carrier). The rooms' own
#: styles load with the module (css/gamecast.css). Told to Ethan.
#: 603 -> 605 on 2026-10-09 by the lag fixes: the app.js bump above
#: (+2.0 KB gz) and the head's connection hints for the picture hosts.
#: Told to Ethan.
#: 605 -> 606 on 2026-10-09 by the first-visit pass: the app.js bump
#: above. Told to Ethan.
#: 606 -> 608 on 2026-10-11 by the password work: the app.js bump above
#: plus the reset page's section and styles (605.87 -> 607.89 KB gz).
#: Told to Ethan.
#: 608 -> 609 on 2026-10-11 by the spots and the incentive tracker (Ethan:
#: "all of it"): the card's Spot, Milestone and Incentive lines with the
#: report's link, and the Milestone watch list (607.88 -> 608.20 KB gz).
#: Told to Ethan.
#: 609 -> 610 on 2026-10-12 by the lapse lock (Ethan: a failed payment or
#: a cancellation "should lock them too the paywall screen"): the open
#: tab's wall recheck and the paywall's lapse banner, after its sentence
#: moved to the server to pay for part of it (608.80 -> 609.18 KB gz).
#: Told to Ethan.
#: 610 -> 611 on 2026-10-13 by the profit calendars (Ethan: "the mlb profit
#: calander isn't updating, it's stuck on September", then "There should
#: be a profit calendar for both edge bets and most likely bets for all
#: sports"): this month drawn with its empty line, then the Edge bets |
#: Most Likely switch and its styles (609.37 -> 610.10 KB gz; app.js
#: 492.89 -> 493.60, inside its 494). Told to Ethan.
#: 611 -> 612 on 2026-10-14 by the fight card's Pick of the Day (Ethan, "do
#: 1-11", to "A Pick of the Day for the UFC card?": yes): the card drawn
#: under the UFC banner on a BET day, after two of the UFC page's empty
#: comment slots were folded away to pay for most of it (610.998 -> 611.007
#: KB gz, the boot path having sat 2 bytes under 611; app.js 494.489 ->
#: 494.498, inside its 495). Told to Ethan.
#: 612 -> 613 on 2026-10-15 by the Toolbox: the app.js bump above plus its
#: sidebar row and page section (611.803 -> 612.246 KB gz). Told to Ethan.
#: 613 -> 614 on 2026-10-19 by the game report: the app.js bump above
#: (612.551 -> 613.158 KB gz); its styles load with it (css/report.css).
#: Told to Ethan.
#: 614 -> 615 on 2026-10-22 by fantasy reading the NFL board: the app.js
#: bump above and the week's eight style lines (613.548 -> 614.263 KB gz).
#: Told to Ethan.
#: 615 -> 616 on 2026-10-23 by the bigger lines under every Most Likely pick
#: (Ethan: "If we know a player can do well we should be recommending the
#: higher line"): the fold's renderer, the guard that keeps a fold inside a
#: card from opening the pick, and its seven style rules — +0.59 KB gz
#: (614.606 -> 615.197). app.js stays inside its 498 (497.466 -> 497.965)
#: once the fold's footnote was cut to one line. Told to Ethan.
#: 616 -> 617 on 2026-10-23 by the iPhone Duo: the app.js bump above, the
#: open shell's overrides, the short front screen's and the header date's
#: (615.197 -> 616.506 KB gz). Told to Ethan.
#: 617 -> 618 on 2026-10-24 by every fold and flip: the app.js bump above and
#: the layouts for each shape — the list beside its pick, the panes at a
#: book-folded hinge, Flex Mode's deck, the cover glance and the narrowest
#: cover's card (616.506 -> 617.545 KB gz). Told to Ethan.
#: 618 -> 580 the same day, for the same split: the first visit is
#: 620 -> 570 KB gz.
#: 580 -> 405 the same evening, for the rooms split above: the first visit
#: is 570 -> 398.9 KB gz.
BOOT_BUDGET_KB = 405


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
    # The whole arrow since 2026-10-09: it also picks the 800px phone copy
    # on a narrow screen (tests/test_the_site_feels_quick.py), so it is no
    # longer one line.
    line = app[app.index("const venueSrc = "):]
    line = line[:line.index("\n};\n")]
    assert '.jpg$/, "$1.webp")' in line
    assert '"$1@800.webp")' in line
    assert "_webp(done, out)" in (ROOT / "tools" / "venues_ingest.py").read_text(), \
        "the ingest must write the webp it serves"


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
