"""A game bet is a door too, and its chart is the team's own results.

Ethan, 2026-08-13, circling MIL +1.5 on the dashboard: "i dont think u get
what im saying. i should be able to click on this prop and it shows more
info for the prop and it will show the bar graph too. you need to
implement that now."

HE WAS RIGHT AND I HAD BUILT HALF THE FEATURE. The pick he circled is a
GAME bet, and `propOpenable` opens with `if (!r.player) return false` — a
run line has no player, so it stayed inert while the props beside it
opened. The gate was not wrong about props. It was answering "is this a
player prop" when the question is "is there anything behind this door".

The reason it read as finished from my side is the reason it is pinned
here: on the Recommended board every card IS a player prop, so the
feature looked complete on the page I was checking. The dashboard mixes
the two, and that is the only screen where the difference shows.

WHAT A GAME BET CHARTS. Not a player's game log — the team's own last
results, which the site has been ingesting all along to grade itself
with. Each market reads a different quantity out of the same row and
charting the wrong one is worse than charting nothing, so the mapping is
asserted here bet by bet:

    moneyline    margin, against 0
    spread       margin, against the handicap with its SIGN FLIPPED
    team total   what that team scored
    game total   the combined score
"""

import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.teamlogs import recent_games

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
VIS = open(os.path.join(ROOT, "web", "js", "visuals.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()


# --- the door ---------------------------------------------------------------
def test_a_game_bet_can_be_opened():
    assert "function gameBetId(" in APP
    assert "function gameBetOpenable(" in APP
    assert "function gameBetAttrs(" in APP


def test_the_top_picks_strip_opens_its_game_cards():
    """The exact card in his screenshot. It used to render with no
    data-prop at all, which is why nothing happened when he clicked."""
    i = APP.index("const gameCardMini")
    block = APP[i:i + 700]
    assert "gameBetAttrs(g)" in block, "the dashboard's game card is still inert"
    assert "openable" in block


def test_the_board_and_the_edge_list_open_them_too():
    """"anywhere we show a prop" was the ask the first time, and a game
    bet is shown in three places. Two of them being doors is the same
    half-finished state as before, one screen over."""
    i = APP.index("function gameBetCard(")
    assert "gameBetAttrs(r)" in APP[i:i + 3000]
    # The window grew with the function: the 2026-08-17 chart pass added
    # the per-row values (and their comment) ahead of the games map.
    j = APP.index("function edgeBoardRows(")
    assert "gameBetAttrs(b)" in APP[j:j + 2600]


def test_the_game_page_defines_its_park_factors():
    """`const f = g.factors` was dropped in the 08-11 desktop-sheet
    rewrite while two Key-insights lines kept reading f.hr — and both
    sit behind `mlb &&`, so the short-circuit hid the ReferenceError
    from every NFL page and every NFL fixture while EVERY MLB game page
    crashed blank for a week (Ethan, 2026-08-18: "when you click on a
    live game, it just takes you to a blank screen"). A guard that only
    trips on one sport is exactly how a crash dodges a render sweep, so
    the definition is pinned ABOVE the first read."""
    i = APP.index("function renderGamePage(")
    # The CODE read, not the word — the definition's own comment says
    # "f.hr" a few lines above it (guard-matches-own-prose, again).
    assert APP.index("const f = g.factors || {};", i) \
        < APP.index("f.hr >= 1.05", i)


def test_the_id_survives_a_rebuild():
    """Keyed on the matchup, market, side and line — never an index into
    a list, which would point at a different pick the moment the board
    rebuilds and make a bookmarked link quietly lie. Same rule propId
    already follows."""
    fn = APP[APP.index("function gameBetId("):APP.index("function teamRecent(")]
    assert "index" not in fn
    for part in ("home", "away", "market", "side", "line"):
        assert part in fn


def test_the_page_routes_on_the_id_prefix():
    i = APP.index("function renderPropPage()")
    assert 'startsWith("game|")' in APP[i:i + 500]
    assert "function renderGameBetPage(" in APP


# --- what each market charts ------------------------------------------------
def _series_block():
    return APP[APP.index("function gameBetSeries("):APP.index("function gameBetChart(")]


def test_a_spread_flips_the_sign_of_its_handicap():
    """+1.5 covers whenever the margin beats −1.5. Charting the margin
    against +1.5 would paint every cover as a miss — a chart that is
    confidently backwards, which is worse than no chart."""
    b = _series_block()
    assert "line: -Number(b.line)" in b, "the handicap's sign is not flipped"


def test_each_market_reads_its_own_quantity():
    b = _series_block()
    assert 'kind === "moneyline"' in b and "g.margin" in b
    assert 'kind === "team_total"' in b and "g.scored" in b
    assert 'kind === "total"' in b and "g.total" in b


def test_an_unknown_market_draws_nothing():
    """The four markets are handled by name and the function ends by
    returning null. A default that guessed at a quantity would put a
    wrong chart under a real pick — the failure this whole file is
    built around, one level down."""
    b = _series_block()
    tail = b[b.rindex('kind === "total"'):]
    assert "return null;" in tail, "no explicit fall-through"
    # Nothing is charted after the last named market.
    assert "values:" not in tail.split("return null;")[1]


def test_the_chart_needs_history_but_the_DOOR_does_not():
    """Two different questions, and conflating them is how this bug comes
    back wearing a disguise.

    The CHART needs three games — fewer is not a trend, it is a rumour.
    The DOOR does not: a game bet's page carries the model's number
    against the market's, the edge, the reasons and the model's own
    objections whether or not we have ingested that club's results.

    Gating the door on the chart made the card's clickability depend on
    the history DB — so a thin ingest, a season boundary or a club we
    have not stored would silently reproduce the exact symptom this file
    exists to fix, arriving by a route that has nothing to do with the
    click handling. The page states a missing series in a line instead.
    """
    b = _series_block()
    assert "rows.length < 3" in b, "three games is the floor the chart needs"
    fn = APP[APP.index("function gameBetOpenable("):]
    fn = fn[:fn.index("\n}\n")]
    assert "gameBetSeries" not in fn, \
        "the door is gated on the chart again — a thin ingest makes the " \
        "card unclickable and it looks like the click is broken"
    i = APP.index("function renderGameBetPage(")
    assert "No recent results for this team yet" in APP[i:i + 4000], \
        "a missing chart must be stated, not left as an empty frame"


# --- the chart has to be able to go below zero ------------------------------
def test_the_axis_can_go_below_zero():
    """A margin is the first quantity this chart has ever been given that
    can be NEGATIVE. Clamping the floor at zero would draw a three-run
    loss as a three-unit bar above the baseline — a loss rendered as a
    win."""
    fn = VIS[VIS.index("function propAnalysis("):VIS.index("/* ---------------- Game-log bars")]
    assert "const lo = Math.min(0, ...data, line);" in fn
    assert "downRungs" in fn and "bottom" in fn
    # And a bar below the line hangs DOWN from it rather than up.
    assert "const yt = y(v), y0 = y(0), down = v < 0;" in fn
    assert "down ? y0 : y0 - h" in fn


def test_the_chart_is_the_same_one_the_props_use():
    """One block, one set of rules about what colour is allowed to mean.
    A second chart drawn for game bets would be a second place for the
    two to disagree about which side of a line is good news."""
    assert "function gameBetChart(" in APP
    i = APP.index("function gameBetChart(")
    assert "propAnalysis(" in APP[i:i + 800]


def test_the_labels_are_the_callers_to_set():
    """"OVER" is wrong over a run line and "PROP" is wrong over a game
    total. The words are options with the old strings as defaults, so
    every existing caller renders exactly as before."""
    assert 'opts.what || "PROP"' in VIS
    assert "opts.head || `LAST ${n} GAMES vs PROP LINE`" in VIS
    assert '(opts.legend || ["OVER", "UNDER"])' in VIS


# --- the game page's stadium ------------------------------------------------
def test_the_game_page_shows_the_photo_when_the_game_is_live():
    """Ethan, same message: "also when you click on the stadium, it still
    shows the old stadium on this page."

    The strip card had exactly this bug — a `!isLive` guard that
    suppressed the photograph and left the drawn ballpark showing — and
    fixing it there left the page BEHIND the card still doing it. So one
    stadium changed appearance between the card and the page it opens,
    which reads as two different venues rather than one bug.
    """
    i = APP.index("const gpPhoto")
    decl = APP[i:i + 400]
    assert "!isLive ?" not in decl, "the game page still hides the photo when live"
    assert "venueSrc(" in decl
    # The bases the drawing used to carry ride over the photo instead.
    assert "mlb && isLive ? runnerOverlay(g)" in APP[APP.index('<div class="gp-art">'):
                                                     APP.index('<div class="gp-art">') + 300]


def test_the_runner_overlay_is_a_chip_in_both_containers():
    """`.gp-art svg { width: 100% }` stretches every SVG in the hero, and
    the overlay is an SVG in that box — on the game page it inflated to
    three bases the size of the outfield. The strip card's box is small
    enough that the same rule did not read as wrong, which is why this
    only appeared one click deeper."""
    assert ".gp-art .venue-runners, .stadium-wrap .venue-runners {" in CSS
    m = re.search(r"\.gp-art \.venue-runners[^{]*\{([^}]*)\}", CSS)
    assert m and "width: 40px" in m.group(1), m and m.group(1)


# --- the Edge Board's faces -------------------------------------------------
def test_the_edge_board_carries_a_mark_per_row():
    """Ethan: "we need to show headshots on this page." Every other board
    leads with the player; this one was a wall of text, which makes the
    list with the most rows the slowest on the site to scan."""
    i = APP.index("function edgeRowHTML(")
    # Widened again 2026-08-25: the spark's tooltip now names which side
    # the bet is on, which pushed the row markup further down the
    # function. The claim is that the row leads with a face, not that the
    # face appears within N characters of the declaration.
    assert 'class="pick-id"' in APP[i:i + 1400]
    # Window widened 2026-08-17: the chart pass added per-row values
    # (and their comment) to both maps, pushing the games map deeper in.
    j = APP.index("function edgeBoardRows(")
    block = APP[j:j + 2800]
    assert "betMark(r, 30)" in block, "player rows must use the face chain"
    assert "teamMark(b.team" in block, "a game line wears its team's logo"


# --- the phone's second tab -------------------------------------------------
def test_the_phone_tab_points_at_tonights_bets():
    """Ethan: "where it shows the 'props' button on the mobile site, that
    should be replaced with a page that shows todays reccomended bets
    with the bar graphs and shit like we have."

    It pointed at the Edge Board — a research table of every positively
    priced number on the card, most of which we are not betting.
    """
    # Scoped to the tab bar itself. The sidebar carries data-view buttons
    # too, and a scan of the whole document would find the Edge Board
    # there and report the phone unchanged when it had changed.
    bar = HTML[HTML.index('<nav class="tabbar"'):]
    bar = bar[:bar.index("</nav>")]
    views = re.findall(r'data-view="([a-z]+)"', bar)
    assert "tonight" in views, f"no Tonight tab: {views}"
    assert "edge" not in views, "the phone still leads with the Edge Board"
    assert "Tonight</button>" in bar


def test_the_tonight_page_exists_and_draws_the_charts():
    assert 'id="view-tonight"' in HTML
    assert 'id="tonight-body"' in HTML
    assert "function renderTonight(" in APP
    i = APP.index("function renderTonight(")
    block = APP[i:i + 2200]
    # It reuses the board's own cards rather than a phone-shaped copy —
    # a second renderer is a second place for the two to drift.
    assert "cardHTML" in block and "gameBetCard" in block


def test_tonight_is_recommended_only():
    """The distinction from the Edge Board is the whole point of the
    page. Showing everything priced would make it the same table with a
    different heading."""
    i = APP.index("function renderTonight(")
    block = APP[i:i + 1200]
    assert "passesFilters(r)" in block and "passesGameBet(b)" in block
    assert "r._ok" in block and "b._ok" in block


def test_the_view_is_routed():
    assert '"tonight"' in APP[APP.index("const VIEW_ORDER"):APP.index("const VIEW_ORDER") + 400]
    assert 'if (name === "tonight") renderTonight();' in APP


# --- the data behind it -----------------------------------------------------
def _db(rows):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE games (sport TEXT, season INTEGER, period TEXT, "
                 "game_id TEXT, home TEXT, away TEXT, home_score REAL, "
                 "away_score REAL)")
    conn.executemany("INSERT INTO games (sport, season, period, home, away, "
                     "home_score, away_score) VALUES (?,?,?,?,?,?,?)", rows)
    return conn


def test_recent_games_reads_both_sides_of_one_row():
    conn = _db([("mlb", 2026, "2026-08-10", "SEA", "CWS", 5, 3)])
    out = recent_games(conn, "mlb", seasons=[2026])
    assert out["SEA"][0]["margin"] == 2 and out["SEA"][0]["home"] is True
    assert out["CWS"][0]["margin"] == -2 and out["CWS"][0]["home"] is False
    assert out["SEA"][0]["total"] == out["CWS"][0]["total"] == 8


def test_tonights_own_result_is_never_in_tonights_chart():
    """The day being priced is excluded. A chart that quietly included
    the game it is arguing about would be reporting the answer as if it
    were the reasoning — the same rule `team_form` documents."""
    conn = _db([("mlb", 2026, "2026-08-12", "SEA", "CWS", 5, 3),
                ("mlb", 2026, "2026-08-13", "SEA", "CWS", 9, 0)])
    out = recent_games(conn, "mlb", ["SEA"], before="2026-08-13", seasons=[2026])
    assert [g["when"] for g in out["SEA"]] == ["2026-08-12"]


def test_newest_first_and_trimmed():
    conn = _db([("mlb", 2026, f"2026-08-{d:02d}", "SEA", "CWS", 4, 1)
                for d in range(1, 13)])
    out = recent_games(conn, "mlb", ["SEA"], n=5, seasons=[2026])
    whens = [g["when"] for g in out["SEA"]]
    assert len(whens) == 5
    assert whens == sorted(whens, reverse=True), whens


def test_a_week_numbered_period_is_not_compared_to_a_date():
    """The NFL stores week numbers in `period`, and "018" < "2026-08-13"
    is a comparison that always succeeds and never means anything — it
    would silently drop a league's whole season."""
    conn = _db([("nfl", 2026, "018", "KC", "BUF", 27, 24)])
    out = recent_games(conn, "nfl", ["KC"], before="2026-08-13", seasons=[2026])
    assert out.get("KC"), "week-numbered rows were dropped by a date compare"


def test_no_games_table_is_no_history_not_a_crash():
    bare = sqlite3.connect(":memory:")
    assert recent_games(bare, "mlb") == {}


def test_the_build_ships_it():
    build = open(os.path.join(ROOT, "mlb_build.py"), encoding="utf-8").read()
    assert 'result["team_recent"]' in build
    assert "before=args.date" in build, "the priced day must be excluded"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
