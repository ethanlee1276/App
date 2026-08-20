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


def test_the_drawer_has_more_than_one_exit():
    """Ethan's 08-17 screen recording: "the only way to exit the menu is
    by clicking the menu button itself and thats confusing and makes you
    feel stuck in the page." Three causes, each pinned here:

      * the scrim (body::after) is paint with no element to listen on,
        and nothing else listened either — so a document-level handler
        now closes the drawer on any tap outside it;
      * `z-index: 60` raised the open drawer OVER the tab bar, hiding
        Home/Tonight/Live/Results — the five obvious exits — behind it;
        the drawer now stays under the bar and clears it with padding;
      * opening the menu yanked the page to the top (a leftover from the
        in-flow dropdown era), so closing it dumped you somewhere you
        never scrolled. Open must not move the page — and the DRAWER
        must open at its own top, because it keeps its scroll while
        hidden and reopening mid-list reads as broken.

    The iOS touchmove guard is part of the same recording: iOS ignores
    body{overflow:hidden} for touch, so the board wobbled under the open
    drawer. passive: false is load-bearing — a passive listener's
    preventDefault is silently ignored."""
    fn = APP[APP.index("function initMobileMenu("):]
    fn = fn[:fn.index("\nfunction ")]
    assert 'closest("#sidebar, .tabbar, .topbar")' in fn, \
        "the outside-tap exit is gone"
    assert '"touchmove"' in fn and "passive: false" in fn, \
        "the iOS background-scroll guard is gone"
    assert "scrollTop = 0" in fn, "the drawer no longer opens at its top"
    assert "window.scrollTo" not in fn, \
        "opening the menu moves the page again"
    assert "body.menu-open .sidebar { z-index" not in CSS, \
        "the drawer covers the tab bar again — the five exits vanish"
    i = CSS.index(".sidebar { padding-bottom: calc(96px")
    assert "@media (max-width: 760px)" in CSS[CSS.rindex("@media", 0, i):i], \
        "the drawer's tab-bar clearance left the phone block"
    # The scrim is a REAL element, not body::after paint. The pseudo did
    # not own its hit-testing: a tap on it fell through, the browser
    # focused whatever sat under the finger and scrolled it into view
    # before any click could be cancelled (measured, #futures: 600 -> 0).
    assert 'id="scrim"' in HTML, "the scrim element is gone"
    assert "body.menu-open #scrim { display: block;" in CSS
    assert "menu-open::after" not in CSS, \
        "the scrim is paint again — taps will fall through to the page"
    # Both scroll locks, because the ROOT is the scroller: overflow on
    # body alone still let the page move under the open drawer.
    assert "html:has(body.menu-open) { overflow: hidden; }" in CSS


def test_props_players_and_record_carry_their_charts_and_chips():
    """Three asks in one message, 2026-08-17.

    "the 'player prop' page should have the charts along with the player
    props" — every edge row with 3+ logged games draws gamelogBars
    against ITS line, in a fixed-width slot so the number columns stay
    aligned, wrapping to its own row on phones instead of crushing the
    label.

    "you should be able to look through mulitpul props for that player"
    — the Players page keeps EVERY market: rec rows grouped per player
    (the old dedupe threw all but the first away), chips for tonight's
    priced markets plus the build's player_stats history, and a
    history-only market renders chart + log with NO invented line.

    "organize the record page. its very cluttered" — the scoreboard
    renders ONCE (the tile stacks that repeated it are gone), splits are
    one switchable table instead of four stacked, market ids come out as
    words, and the settled list opens at a dozen rows with a real count
    on the expander."""
    # Edge rows: chart present, from the row's own log, against its line.
    fn = APP[APP.index("function edgeRowHTML("):]
    fn = fn[:fn.index("\n}")]
    assert "edge-spark" in fn and "gamelogBars(r.vals" in fn
    assert "line: r.line" in fn
    src = APP[APP.index("function edgeBoardRows("):]
    src = src[:src.index("\nfunction edgeRowHTML")]
    assert "vals: (r.logs || []).map((l) => l.value)" in src
    # Phone: the chart wraps, it does not vanish — Ethan asked for the
    # charts, and display:none at 700px would be quietly taking them back.
    i = CSS.index(".edge-spark { flex: 0 0 92px")
    phone = CSS[CSS.index("@media (max-width: 700px)", i):]
    phone = phone[:phone.index("}", phone.index("edge-spark"))]
    assert "display: none" not in phone
    # Players: grouped rows, chips, and the honest history card.
    assert "_profRows.get(player)" in APP
    assert 'class="prof-tab' in APP and "data-mkt" in APP
    hist = APP[APP.index("function historyProfileHTML("):]
    hist = hist[:hist.index("\n}")]
    assert "no line on tonight" in hist
    assert "line:" not in hist.split("gamelogBars")[1].split("})")[0], \
        "the history chart invented a threshold"
    # Record: one scoreboard, switchable splits with words, capped list.
    ra = APP[APP.index("function recAnalytics("):]
    ra = ra[:ra.index("\nfunction recEraSection")]
    assert "ra-tiles" not in ra, "the tile stacks that repeated the scoreboard are back"
    assert "_recSetSplit" in APP and "MARKET_WORDS" in APP
    assert '["market", "Market", o.by_market]' in APP
    rr = APP[APP.index("function recRecentSection("):]
    rr = rr[:rr.index("\n}")]
    assert "slice(0, 12)" in rr and "Show all" in rr


def test_the_performance_panel_answers_for_the_sport_in_view():
    """Ethan, 2026-08-17: "when you on a specific sport, when it shows
    the 'my performance' it should only show the performance for that
    specific sport." The ledger exported per-sport curves all along —
    the panel just read the global block on every page. Now it reads
    by_sport[state.sport] when that sport has settled picks, TITLES
    itself with the sport, and when the sport has nothing settled it
    falls back to the whole book AND SAYS SO — an unlabelled global
    number on a sport's own page was the bug.

    Scoping is gated on tracked_sports so a standalone page can never
    ask for "your MEMES performance"."""
    fn = APP[APP.index("async function renderHomePerf("):]
    fn = fn[:fn.index("\nfunction ")]
    assert "by_sport" in fn and "tracked_sports" in fn
    assert "scopedToSport ? section.curve : _perfCache.curve" in fn, \
        "the curve must come from the same scope as the tiles"
    assert "no ${sportName} picks settled yet" in fn, \
        "the whole-book fallback lost its label"


def test_line_shopping_rows_wear_a_face():
    """Ethan, 2026-08-17: "the line shopping page doesnt show any
    headshots." Same contract the Edge Board got on 08-13: every list
    leads with who the bet is about. The scan rows now carry player/team
    from the engine, and the guard in scanMark keeps a pre-upgrade
    payload rendering its old rows instead of broken avatars."""
    assert "function scanMark(" in APP
    assert "(t.player || t.team)" in APP, "the legacy-payload guard is gone"
    assert APP.count("${scanMark(") >= 3, \
        "pairs, stale and plus-money rows each lead with the mark"
    scan = open(os.path.join(ROOT, "engine", "marketscan.py"),
                encoding="utf-8").read()
    assert scan.count('"player": r.get("player", "")') >= 3, \
        "a scanner section stopped shipping who the bet is about"
    assert scan.count('"team": r.get("team", "")') >= 4


def test_line_charts_scrub_under_a_finger():
    """Ethan, 2026-08-18: "you can glide your finger across it an it
    will show the data for wherever your finger is gliding, we should
    have that for any line chart we have on the site."

    One shared engine in visuals.js; a chart opts in with data-scrub on
    its svg. ALL FIVE remaining line charts carry it — the Record curve,
    the dashboard performance spark, the My Bets P&L curve, the coin
    tape spark (with per-point x fractions: snapshots are not evenly
    spaced), and the live win-probability track via sparkline itself.

    The liveability contract is pinned hardest: pan-y touch-action and
    passive listeners mean a horizontal glide reads the chart while a
    vertical drag still scrolls the page — a chart that traps scrolling
    would get the feature turned off within a day."""
    vis = open(os.path.join(ROOT, "web", "js", "visuals.js"),
               encoding="utf-8").read()
    i = vis.index("finger scrubbing on line charts")
    engine = vis[i:]
    assert 'closest("svg[data-scrub]")' in engine
    # The CALL form, not the word — the engine's own comment says
    # "never preventDefault" and a prose match would fail on the rule
    # being stated (the guard-matches-own-prose class, again).
    assert ".preventDefault()" not in engine, \
        "the scrubber must never eat the page's scroll"
    assert engine.count("passive: true") >= 4
    assert '"x":[optional' in engine or "d.x" in engine  # uneven spacing
    assert "svg[data-scrub] { touch-action: pan-y; }" in CSS
    assert ".scrub-rail" in CSS
    # The five charts: four in app.js, the track via sparkline's own emit.
    assert APP.count('data-scrub="${') == 4, \
        "a line chart lost (or grew without) its scrub data"
    assert 'data-scrub="${scrub}"' in vis, "sparkline stopped embedding scrub data"
    # The rec curve's per-dot hover circles retired with this — two
    # tooltips fighting over one chart is worse than either.
    fn = APP[APP.index("function recCurveChart("):]
    fn = fn[:fn.index("\n  const head")]
    assert "data-tip" not in fn


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
    # boardFetch, not fetch, since 2026-08-20: every board payload goes
    # through the wrapper that tells "the wire refused us" apart from
    # "the payload was empty". The claim here is unchanged — this panel
    # reads the SAME record.json the Record page renders.
    assert 'boardFetch("data/record.json"' in fn
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
    # The all-time stats moved from a tile row to one ledger line in the
    # 2026-08-17 declutter — the CONTRACT (staked/returned/avg price/
    # streak all shipped, honestly labelled) is what this pins, not the
    # container they render in.
    assert "staked all-time" in APP and "implied_breakeven(b[\"odds\"])" in LEDGER
    assert "best_streak" in LEDGER and "returned_units" in LEDGER
    fn = APP[APP.index("function renderBankrollExtras("):]
    fn = fn[:fn.index("\n}")]
    assert "qb_bk_goal" in fn and "mbProfit" in fn
    assert 'id="nav-acct"' in HTML
    # The insights panel renders data fields only; its title says so.
    assert "this game’s own data, not narratives" in APP

def test_the_drawer_outranks_its_scrim_by_source_order_too():
    """Ethan's 2026-08-19 recording: on iPhone the page dimmed and blurred
    but no drawer arrived — three taps, three times. It reproduces on no
    desktop engine, because on paper the ordering is already right (drawer
    z-index 50 over scrim 45).

    Both elements build their own stacking context — the drawer through
    `transform`, the scrim through `backdrop-filter` — and a compositor
    that promotes the blurred layer out of that comparison paints it over
    a drawer that is genuinely there. Two things fix the whole class, and
    both are pinned here: the blur is gone (it was 2px of decoration and
    the only property changing how the layer composites), and the scrim
    now comes BEFORE the drawer in source order, so last-painted-wins
    lands on the drawer even where z-index is ignored.
    """
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    i_scrim = html.index('<div id="scrim"')
    i_draw = html.index('<aside class="sidebar"')
    assert i_scrim < i_draw, \
        "the scrim must precede the drawer, or a promoted blur layer hides it"

    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    j = css.index("body.menu-open #scrim")
    rule = css[j:css.index("}", j)]
    assert "backdrop-filter" not in rule, \
        "the scrim's blur is what promotes the layer over the drawer"
    assert "background:" in rule, "the dim is the part that does the work"
    # And the declared order still says the drawer wins, for engines that
    # honour it.
    import re
    z_scrim = int(re.search(r"z-index:\s*(\d+)", rule).group(1))
    k = css.index(".sidebar { position: fixed")
    z_draw = int(re.search(r"z-index:\s*(\d+)", css[k:k + 240]).group(1))
    assert z_draw > z_scrim, f"drawer z{z_draw} must beat scrim z{z_scrim}"


def test_a_dead_pipeline_cannot_hide_behind_a_small_number():
    """The 2026-08-10 freeze ran nine days on a page that looked normal.
    Two reasons it stayed invisible, both fixed here.

    THE AGE STOPPED AT HOURS, so nine days rendered "216h" — and the
    PHONE chip shows the age and nothing else, so that tiny amber number
    was the entire warning. It says days once it is days, and carries the
    word "Stale" on the phone.

    AND NOTHING SHOUTED. The server keeps serving the last good build
    when the refresh loop dies, so a broken site and a working one are
    identical. The check cannot live in the loop — the doctor runs INSIDE
    the refresh cycle, which is why nobody was told. It lives on the page,
    which is always holding the timestamp."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = app.index("function updateAgo()")
    body = app[i:app.index("\nfunction ", i + 10)]
    assert "86400" in body, "the age still tops out below days"
    assert '`Stale ${ago}`' in body, "the phone chip is still a bare number"
    assert "renderStaleBar(" in body, "nothing drives the loud bar"

    j = app.index("function renderStaleBar(")
    bar = app[j:app.index("\nfunction ", j + 10)]
    assert "STALE_LOUD_MS" in bar
    assert "host.hidden" in bar, "the bar must vanish when the data is fine"
    # It has to say the age, or it is an alarm without a fact in it.
    assert "${escapeHtml(ago)}" in bar

    # Loud threshold must be far above the ordinary chip threshold, or a
    # quiet night cries wolf.
    import re
    loud = app[app.index("const STALE_LOUD_MS"):]
    loud = re.search(r"=\s*(\d+)\s*\*\s*(\d+)\s*\*\s*(\d+)", loud)
    hours = int(loud.group(1))
    assert hours >= 6, f"{hours}h is too eager for a nightly build"

    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    assert 'id="stalebar"' in html and "hidden" in html[html.index('id="stalebar"'):
                                                        html.index('id="stalebar"') + 60]
    css = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
    assert "#stalebar {" in css and "#stalebar[hidden]" in css



if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
