"""THE NEW LOOK — Ethan's render, shipped 2026-08-11, pinned here.

"go new look. i want everything you see besides the balance chip thing,
and the bet slip thing … copy my render and ship it fully. make sure to
do mobile as well."

What this file guards, in order of how much it matters:

1. THE LINE WE DID NOT CROSS. The render was drawn in the visual language
   of a sportsbook. The two elements Ethan excluded — the balance chip
   and the bet slip — are exactly the two that would make this site LOOK
   like it holds money. It never does: no "Place Bet", no deposits, no
   balance, no "To Win". If one of these strings ever ships, the page
   has started impersonating a book.

2. THE SHELL. One slim bar; every destination in a sidebar that IS the
   phone drawer (one element, two positions — never two copies to drift
   apart); the rail on Home only; the dashboard fed by the same payloads
   the board and the Record page already read.

3. THE SYSTEM UNDER THE SKIN. Glow and gradients are legal now, but only
   through the tokens, so every light on the site is the same light.
   High Confidence Mode is a REAL filter wired into the same gate every
   card list passes through — never a marketing toggle.

Run directly: `python3 tests/test_newlook.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web/css/styles.css"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "web/index.html"), encoding="utf-8").read()


def _strip_comments(s):
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)
    return re.sub(r"<!--.*?-->", " ", s, flags=re.S)


def test_no_sportsbook_cosplay_ever():
    """The excluded-by-Ethan list, plus everything else that would imply
    this site holds money. Checked against the words a USER sees."""
    visible = _strip_comments(HTML) + _strip_comments(APP)
    for phrase in ("Place Bet", "place bet", "To Win $", "Deposit",
                   ">Balance<", "your balance", "Cash Out", "cash out"):
        assert phrase not in visible, f"sportsbook cosplay shipped: {phrase!r}"
    # And the bankroll page says out loud what it is not.
    i = HTML.index('id="view-bankroll"')
    assert "never holds a balance" in HTML[i:i + 1200]


def test_the_sidebar_is_the_drawer_not_a_second_menu():
    """One element, two positions. The phone drawer is the SAME #sidebar
    the desktop shows — transformed in, behind the same #menu-toggle and
    body.menu-open machinery — so the two can never disagree about what
    the site contains."""
    assert HTML.count('id="sidebar"') == 1
    i = CSS.index(".sidebar { position: fixed;")
    media = CSS.rindex("@media", 0, i)
    assert "max-width: 900px" in CSS[media:media + 40], "the drawer breakpoint moved"
    assert "body.menu-open .sidebar { transform: translateX(0)" in CSS
    # The bar's own nav hides on phones — the drawer carries everything.
    i = CSS.index("@media (max-width: 760px) {", CSS.index("NEW LOOK — 2026-08-11"))
    assert ".nav { display: none; }" in CSS[i:i + 900]


def test_every_destination_survived_the_redesign():
    """Nothing Ethan could reach before is more than one sidebar tap away
    now. Counted by the same data attributes the router binds."""
    sb = HTML[HTML.index('id="sidebar"'):HTML.index("</aside>")]
    for sport in ("nfl", "cfb", "mlb", "nba", "wnba", "ufc", "intel",
                  "fantasy", "memes", "record", "lab", "mybets", "why", "about"):
        assert f'data-sport="{sport}"' in sb, f"{sport} fell out of the sidebar"
    # "parlays" left this list 2026-08-11: the page became Parlay Mode
    # (the second sidebar toggle) — test_parlays.py owns that contract.
    for view in ("recommended", "live", "edge", "longshots",
                 "futures", "standings", "trending", "players", "rosters",
                 "injuries", "scanner"):
        assert f'data-view="{view}"' in sb, f"{view} fell out of the sidebar"
    assert 'id="pz-toggle"' in sb, "the Parlay Mode switch fell out"


def test_the_drawer_has_one_door_per_page():
    """Ethan, 2026-08-17: "theres so much on the site and its hard and
    confusing to navigate." Measured before the declutter: 37 rows and
    1672px of drawer against a 788px phone viewport — and FOUR of those
    rows opened the same Dashboard (its own row, a Top Picks anchor, and
    the Game Lines and Watchlist sub-tab links). Rows that are doors to
    the same page teach a reader that the menu cannot be trusted to mean
    anything.

    The other half of this contract is the test above: everything that
    left the drawer is still IN the drawer once, or one visible tap away
    on the Dashboard's own sub-tab bar. This test pins ONCE."""
    sb = HTML[HTML.index('id="sidebar"'):HTML.index("</aside>")]
    views = re.findall(r'data-view="([a-z]+)"', sb)
    assert len(views) == len(set(views)), (
        f"a page has two drawer rows again: "
        f"{sorted(v for v in views if views.count(v) > 1)}")
    sports = re.findall(r'data-sport="([a-z]+)"', sb)
    assert len(sports) == len(set(sports)), (
        f"a sport has two drawer rows again: "
        f"{sorted(s for s in sports if sports.count(s) > 1)}")
    # Anchor rows duplicate a section of a page the drawer already lists.
    assert "sb-anchor" not in sb, \
        "an anchor row is back — it is a second door to the Dashboard"
    # One sub-tab row is earned: Game Lines, the market bettors scan a
    # menu for. Watchlist's row was cut — its tab is visible on the
    # Dashboard itself.
    assert sb.count("sb-subtab") == 1, \
        "a second sub-tab row — the Dashboard's own tab bar is its door"
    # The Models group's three rows were the MLB/NFL/UFC chips wearing
    # the model names…
    assert "sb-model" not in sb, "the Models group is back"
    # …and the names must survive its dissolution: they live in the
    # league taglines now (and the chips' title tooltips).
    assert "Scalpy 2.0" in APP, "the MLB model's name vanished with its menu row"
    assert "The NFL Book" in APP, "the NFL model's name vanished with its menu row"


def test_the_library_folds_and_remembers():
    """Six reference pages (injuries, weather, trending, rosters,
    players, rankings) fold behind one Library heading, SHUT by default —
    they are visited weekly, not nightly. The daily groups ship open.

    Three parts, each load-bearing:
      * the default lives in the MARKUP (aria-expanded + [hidden]) so it
        holds before app.js runs, with no flash of the long menu;
      * `.sb-group[hidden] { display: none; }` exists in the stylesheet,
        because .sb-group's display:flex otherwise beats the UA's
        [hidden] rule and the fold only pretends;
      * the person's choice outlives the default via localStorage."""
    sb = HTML[HTML.index('id="sidebar"'):HTML.index("</aside>")]
    assert sb.count('class="sb-label sb-fold"') == 3, \
        "the foldable heads changed — Betting, Library, My Book"
    lib = sb[sb.index('data-fold="library"'):]
    assert 'aria-expanded="false"' in lib[:220], "Library no longer ships shut"
    assert '<div class="sb-group" data-group="library" hidden>' in sb, \
        "Library's group lost its markup-default [hidden]"
    for fold in ('data-fold="research"', 'data-fold="tools"'):
        seg = sb[sb.index(fold):]
        assert 'aria-expanded="true"' in seg[:220], \
            f"{fold} must ship open — it is a daily surface"
    assert ".sb-group[hidden] { display: none; }" in CSS, \
        "a folded group only pretends to fold without this rule"
    assert "qb_sb_folds" in APP, "the fold choice is no longer remembered"
    # Folding must never orphan a page: every library row is still a
    # .nav-btn the router binds, so search, hash routes and the fold all
    # reach the same six views.
    libgrp = sb[sb.index('data-group="library"'):]
    libgrp = libgrp[:libgrp.index("</div>")]
    for view in ("injuries", "weather", "trending", "rosters", "players",
                 "standings"):
        assert f'data-view="{view}"' in libgrp, f"{view} left the Library"


def test_the_rail_belongs_to_home_only():
    """The render puts insights and live-now beside the dashboard. On
    every other page the content gets the room back."""
    fn = APP[APP.index("function syncRail("):]
    fn = fn[:fn.index("\n}")]
    assert 'state.view === "recommended"' in fn
    assert APP.count("syncRail") >= 3          # def + switchView + boot


def test_high_confidence_mode_is_a_real_filter():
    """The render's toggle, wired to the journal's own grade bands: ON
    filters the board and the Top Picks strip to quality >= 80 (A/A+) —
    inside passesFilters, the ONE gate every card list already passes
    through, so no list can forget to respect it."""
    fn = APP[APP.index("function passesFilters("):]
    fn = fn[:fn.index("\n}")]
    assert "hcmOn()" in fn and "80" in fn
    tp = APP[APP.index("function renderTopPicks("):]
    tp = tp[:tp.index("\n}")]
    assert "hcmOn()" in tp
    assert 'role="switch"' in HTML                 # a switch, announced as one


def test_glow_and_gradients_go_through_the_tokens():
    """The pivot legalized light — as a SYSTEM. Any raw gradient in the
    chrome outside the token definitions is freelancing. (The venue art
    in visuals.js draws its own skies; this audits the stylesheet.)"""
    # Every gradient must be DEFINED on a custom property (--grad-*,
    # --skeleton, …) — a gradient written directly into a rule is
    # freelancing outside the system.
    body = _strip_comments(CSS)
    for line in body.splitlines():
        if "gradient(" not in line:
            continue
        assert re.match(r"\s*--[a-z-]+:", line), f"raw gradient: {line.strip()[:70]}"


def test_the_dashboard_reads_the_real_journal():
    """The performance panel is the render's best idea and it must never
    become decoration: it fetches the SAME record.json the Record page
    renders, shows losses in red, and links to the full record."""
    fn = APP[APP.index("async function renderHomePerf("):]
    fn = fn[:fn.index("\n}")]
    assert 'fetch("data/record.json"' in fn
    assert "net_units" in fn and "roi" in fn
    assert 'href="#record"' in fn
    # No invented numbers: an empty journal renders NOTHING, not zeros.
    assert "host.innerHTML = \"\"" in fn.replace("''", '""')


def test_the_top_game_ribbon_is_earned_not_asserted():
    """The render's TOP GAME badge. Ours goes to the game with the most
    recommended bets tonight — one game, only when something is actually
    recommended."""
    fn = APP[APP.index("function renderGames("):]
    fn = fn[:fn.index("\n}")]
    assert "gameBetCount(g)" in fn
    assert "topN > 0" in fn


def test_the_greeting_never_fakes_a_name():
    """"Good evening, Alex" in the render — powered by the real account
    here, and a plain welcome when there is none. No placeholder names."""
    fn = APP[APP.index("function renderGreeting("):]
    fn = fn[:fn.index("\n}")]
    assert "acctState" in fn
    assert "Alex" not in APP, "the render's placeholder name shipped"


def test_the_wordmark_is_gold_and_the_interface_is_violet():
    """One gold element — the Qellys mark — on a violet interface. The
    render's split, pinned so neither leaks into the other's job."""
    i = CSS.index(".qmark", CSS.index("NEW LOOK — 2026-08-11"))
    assert "var(--gold)" in CSS[i:i + 200]
    i = CSS.index("--brand:", CSS.index("NEW LOOK — 2026-08-11"))
    assert "#8D5BF2" in CSS[i:i + 40]


def test_the_page_never_pans_sideways():
    """Ethan's screen recording, 2026-08-10: the whole mobile site
    scrolled left-right. Root cause: the header's status cluster kept
    its desktop flex:0 0 auto on phones and overflowed the bar, and
    nothing clipped the document. Both halves pinned — the fit (the
    cluster shrinks on phones) and the seatbelt (the document refuses
    horizontal overflow, with clip so sticky survives)."""
    assert "html, body { overflow-x: clip; }" in CSS
    i = CSS.index("@media (max-width: 760px) {", CSS.index("NEW LOOK — 2026-08-11"))
    block = CSS[i:i + 1600]
    assert "flex: 1 1 auto; min-width: 0" in block, \
        "the status cluster stopped shrinking — the sideways pan is back"


def test_ethans_venue_renders_are_plugged_in():
    """Ethan, 2026-08-11: "Ok can you just plug them in for me?" — a
    contact sheet of night renders, six lighting colours per building
    family. Pinned: all 24 sliced files ship; a card falls back
    team photo -> colour-matched family render -> drawing (the data-alt
    hop); live games still never show a photo; the UFC page banners an
    octagon picked by card identity, since no fight has a home team."""
    vdir = os.path.join(ROOT, "web/img/venues/variants")
    hues = ("red", "gold", "green", "blue", "violet", "steel")
    expected = {f"{fam}-{h}.jpg" for fam in ("football", "basketball", "baseball")
                for h in hues} | {f"octagon-{i}.jpg" for i in range(1, 7)}
    have = {f for f in os.listdir(vdir) if f.endswith(".jpg")}
    assert have == expected, f"variant art drifted: {have ^ expected}"
    # Every sport with a stadium card maps to a family; the hop exists.
    fam_line = APP[APP.index("const VENUE_FAMILY"):APP.index("const VENUE_FAMILY") + 200]
    for sport in ("nfl", "cfb", "mlb", "nba", "wnba"):
        assert f"{sport}:" in fam_line, f"{sport} lost its render family"
    assert "window.vpFall" in APP and "data-alt" in APP
    # THE HOP IS NO LONGER GATED ON not-live. It used to be: live cards
    # suppressed the photo and drew the SVG ballpark, because the drawing
    # lights the occupied bases. Ethan reported the result three times as
    # "the stadium issue" — a flat vector diagram beside photoreal
    # stadiums on the same strip — and on 2026-08-13 chose photo
    # everywhere with the runners overlaid instead. This assertion
    # encoded the behaviour he rejected, so it moves with the rule.
    i = APP.index("class=\"venue-photo\"")
    slot = APP[max(0, i - 400):i + 500]
    assert "venueVariant(homeTeam)" in slot and "vpFall(this)" in slot
    assert "!isLive ? (() => {" not in APP, "the photo is gated on live again"
    assert "mlb && isLive ? runnerOverlay(g)" in APP, \
        "photo on live cards without the overlay loses the base runners"
    # UFC: hash-picked octagon banner, styled.
    assert "octagon-${octN}" in APP
    assert ".ufc-banner" in CSS


def test_the_render_sheet_pass_shipped_its_honest_subset():
    """Ethan's 12-panel mobile sheet, 2026-08-11: "matching these pages
    to a tee ... Obviously we won't use some of the pages". What shipped:
    My Bets as status-filtered cards, the Results range analytics, the
    Live board's per-team line grid, the Props market tiles, the art
    weather chip. What must NEVER ship from that sheet stays pinned by
    test_the_site_never_cosplays_a_sportsbook."""
    # My Bets: the card list with status chips replaced the agate table.
    fn = APP[APP.index("function renderMyBets("):]
    fn = fn[:fn.index("\n}")]
    assert "mbc-chip" in fn and "mbc-list" in fn
    assert 'chip("open", "Open")' in fn and 'chip("win", "Won")' in fn
    # "To win" is arithmetic on the user's own stake and price — pinned
    # to the formula so nobody swaps in a projection later.
    assert "b.stake * b.odds / 100" in fn
    # Results: the analytics block computes INSIDE the window and the
    # ALL window can never reach toISOString (Invalid Date blanks the page).
    fn = APP[APP.index("function recAnalytics("):]
    fn = fn[:fn.index("\nfunction recEraSection")]
    assert "isFinite(days)" in fn
    assert "rows.reduce((a, p) => a + p.w, 0)" in fn
    # Live board: SPREAD | TOTAL | ML as columns, no invented -110 juice
    # (the form placeholder elsewhere may SAY -110; the live grid never
    # renders one it didn't get from the slate).
    fn = APP[APP.index("function liveCardHTML("):]
    fn = fn[:fn.index("function miniDiamond")]
    assert "lb-table" in fn and "-110" not in fn
    # Props: tiles counted from what is actually priced tonight.
    assert "pm-grid" in APP and "byMarket[r.market]" in APP
    # The art chip only speaks when a real reading exists, never live.
    assert "w.temp_f != null && !w.dome" in APP
    # The curve rows carry the per-day fields the range math needs.
    LEDGER = open(os.path.join(ROOT, "engine/ledger.py"), encoding="utf-8").read()
    assert "SUM(status='won') AS w" in LEDGER
    # Desktop sheet (same day): the event page's lines + insights, the
    # analytics footer, the bankroll goal, the avatar chip. The footer's
    # average price is a mean of implied probabilities re-expressed in
    # American odds — never a mean of the American ints themselves.
    assert "gp-lines" in APP and "gp-note-list" in APP
    assert "ra-alltime" in APP and "implied_breakeven(b[\"odds\"])" in LEDGER
    assert "best_streak" in LEDGER and "returned_units" in LEDGER
    fn = APP[APP.index("function renderBankrollExtras("):]
    fn = fn[:fn.index("\n}")]
    assert "qb_bk_goal" in fn and "mbProfit" in fn
    assert 'id="nav-acct"' in HTML
    # The insights panel renders data fields only; its title says so.
    assert "this game’s own data, not narratives" in APP


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
