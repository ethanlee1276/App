"""The NFL board survives the week before Week 1.

Found by the Phase 3 dress rehearsal, 2026-08-19, running the real thing:

    python3 nfl_build.py 2026 1 --injuries --depth --out ...

It printed all 16 games with real spreads and totals, then exited 2 and
wrote NOTHING, because nflverse has no weekly player stats for a season
whose games have not been played. That is the normal state of the world
before every Week 1 — not a fault.

The consequence was the bug. `refresh_nfl` runs ONE build and keeps the
old data when it fails, so from Sep 2 (the first day
`_current_nfl_week()` calls Week 1 current) until roughly Sep 9, every
nightly refresh would fail and the board would carry nothing — through
exactly the week the season arrives, while the games and their lines
were available the whole time.

What is defended here:

  * --games-only WRITES when given somewhere to write. A schedule is
    worth publishing on its own.
  * IT PRICES THE GAME MARKETS. Totals, team totals and spreads need
    team ratings and the schedule's own lines, both of which exist that
    whole week. Only the moneyline needs a book price, so it appears
    only when a cached odds pull has one.
  * IT PUBLISHES NO PROPS, because none have been built. A payload that
    listed recommendations here would be inventing them.
  * ITS JOURNALLING CANNOT DOUBLE-COUNT. That was the objection to
    pricing here at all (Ethan settled it on 2026-08-19: "yes I want the
    2nd -9th priced"), and the answer is structural rather than a
    promise — bets is UNIQUE on (sport, date, player, market, category)
    with INSERT OR IGNORE, and this payload stamps the same
    "<season>-W<week>" date key build_slate() does, so the full build's
    later re-offer of the same row is a no-op in SQLite.
  * IT SAYS WHICH LAYER IS MISSING, so the board reads as "no props
    yet" rather than "no games" or "nothing clears the bar".
  * THE LAUNCHER FALLS BACK TO IT.

Run directly: `python3 tests/test_nfl_week1_fallback.py`
"""

import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
LAUNCH = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()


def _games_only_block():
    """The whole --games-only branch, sliced to its END rather than to a
    fixed character count.

    Every test below used to take BUILD[i:i + 5200]. The branch grew by a
    dozen lines on 2026-08-26 (it started shipping `team_recent`) and the
    window silently stopped covering `gate.publish` — a test that fails
    because the code it reads moved, not because the code is wrong, is a
    test that will be deleted the third time it cries wolf. The branch
    ends where the function returns."""
    i = BUILD.index("if args.games_only:")
    j = BUILD.index("\n        return\n", i)
    return BUILD[i:j]


def test_games_only_writes_a_payload_when_given_an_out():
    block = _games_only_block()
    assert "if args.out:" in block, "--games-only still only prints"
    assert "gate.publish(payload, args.out)" in block, \
        "the fallback must publish through the gate, like every other build"
    assert '"games": [_game_to_dict(g) for g in games]' in block, \
        "the slate must carry the real games, not a stub"


def test_the_fallback_prices_the_game_markets_and_only_those():
    """Ethan, 2026-08-19: "yes I want the 2nd -9th priced".

    The first version of this fallback published a bare schedule out of
    caution about double-journalling. The caution was worth raising and
    turned out to be answered already (see the next test), so the game
    markets price here. The PLAYER layer still does not, because it does
    not exist — that is the whole reason this path runs."""
    block = _games_only_block()
    assert "price_games_only(games, args.season, args.week, config" in block, \
        "the fallback publishes a schedule with no prices again"
    assert '"game_bets": bets' in block, "the priced bets never reach the payload"
    # The player layer stays empty, because nothing built it.
    for empty in ('"recommendations": []', '"long_shots": []'):
        assert empty in block, f"the fallback invented {empty}"
    # `parlays` is ABSENT rather than empty — see the shape test below.
    assert '"parlays"' not in block, \
        "the fallback claims a parlay screen ran on a board with no props"


def test_a_schedule_price_enters_the_record_labelled_as_one():
    """The ledger stores `r.get("book", "best")`, so a game bet with no
    book key journals as "best" — a claim that the price was shopped.
    Without a cached odds pull these are the standard −110 against the
    schedule's own line, which is a different thing, and the record has to
    be able to tell them apart afterwards. It cannot un-mix them later."""
    tree = ast.parse(BUILD)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "price_games_only")
    src = ast.get_source_segment(BUILD, fn)
    assert 'b.setdefault("book", "schedule")' in src, \
        "an unpriced-by-a-book row would enter the record claiming one"
    # Only when no book price was attached — a cached pull's real prices
    # must keep their own provenance.
    assert 'if not rep["moneylines"]:' in src


def test_the_priced_fallback_cannot_double_journal_the_slate():
    """The objection, answered structurally rather than by restraint.

    Two conditions have to hold together, and each is checked where it
    lives: the ledger's own uniqueness, and this payload using the same
    date key the full build stamps. Break either one and the same slate
    lands in the record twice."""
    ledger = open(os.path.join(ROOT, "engine", "ledger.py"),
                  encoding="utf-8").read()
    assert "UNIQUE (sport, date, player, market, category)" in ledger, \
        "the bets table lost the constraint the fallback relies on"
    assert "INSERT OR IGNORE INTO bets" in ledger, \
        "an insert that is not OR IGNORE would raise instead of dedupe"
    # Same date key on both sides — a bare INSERT OR IGNORE dedupes
    # nothing if the two builds file the slate under different dates.
    assert '"date": f"{args.season}-W{args.week:02d}"' in _games_only_block()
    nflverse = open(os.path.join(ROOT, "engine", "sources", "nflverse.py"),
                    encoding="utf-8").read()
    assert 'Slate(date=f"{season}-W{week:02d}"' in nflverse, \
        "build_slate's date key moved; the fallback's no longer matches it"


def test_the_moneyline_is_the_one_market_that_waits_for_a_book():
    """Totals and spreads price off ratings against the schedule's own
    lines. A moneyline has no line to price against — it IS the price —
    so it appears only when a cached pull carries one, and never as a
    guess."""
    tree = ast.parse(BUILD)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "price_games_only")
    src = ast.get_source_segment(BUILD, fn)
    assert "cache_only=True" in src, \
        "the fallback must never spend API quota to price a moneyline"
    assert "cached_odds" in src
    # And a failure to read the cache is not a failure to price.
    assert 'rep["odds_error"]' in src and 'rep["error"] = str(exc)' in src, \
        "one error field would report a missing moneyline as a dead board"


def test_journalling_the_same_slate_twice_files_it_once():
    """The structural claim, exercised rather than grepped.

    The Sep 2-9 sequence in full: the fallback prices and journals Week 1
    on the 3rd, and on the 10th the full build prices the same week again
    — same date key, same teams, same markets — and offers those rows a
    second time. The record must not grow."""
    from engine import ledger

    conn = ledger.connect(":memory:")
    payload = {
        "sport": "nfl", "date": "2026-W01",
        "game_bets": [
            {"bet_type": "spread", "team": "LA", "line": -3.5,
             "matchup": "SF @ LA", "win_prob": 0.55, "edge": 0.05,
             "confidence": 6.8, "grade": "Play", "stake_units": 1.0,
             "recommended": True},
            {"bet_type": "total", "matchup": "SF @ LA", "side": "OVER",
             "line": 48.5, "win_prob": 0.54, "edge": 0.04,
             "confidence": 6.5, "grade": "Play", "stake_units": 1.0,
             "recommended": True},
        ],
    }
    first = ledger.log_recommendations(conn, payload)
    assert first == 2, first
    second = ledger.log_recommendations(conn, payload)
    assert second == 0, f"the same slate journalled {second} extra row(s)"
    assert conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 2


def test_a_week_one_game_bet_settles_against_a_real_played_game():
    """The end of the sequence, and the half that had never been run.

    The fallback journals game bets under the "<season>-W<week>" key from
    Sep 2. Two weeks later those games are played and `settle_from_history`
    has to find them — and NFL is the one sport whose bet date is NOT the
    period the results are filed under. `_hist_where` maps 2025-W05 to
    `season=2025 AND period='005'`, and nothing exercised that mapping for
    a GAME market: every game-bet settle test was MLB, where the date IS
    the period.

    Run against a real completed game rather than a fixture, because the
    thing being tested is whether our key finds nflverse's row.

    The spread's sign convention is the part worth watching. A spread bet
    covers when the team's margin beats the number, so the row stores
    line = -spread and side = OVER and the standard grader applies
    unchanged. Get that backwards and every favourite grades as its own
    opposite — silently, with a plausible-looking record.
    """
    import sqlite3
    from engine import ledger

    hist_path = os.path.join(ROOT, "data", "history.db")
    if not os.path.exists(hist_path):
        print("      (skipped: no history.db on this machine)")
        return
    h = sqlite3.connect(f"file:{hist_path}?mode=ro", uri=True)
    h.row_factory = sqlite3.Row
    g = h.execute("SELECT * FROM games WHERE sport='nfl' AND home_score IS NOT NULL "
                  "AND season=2025 AND period='005' LIMIT 1").fetchone()
    if not g:
        print("      (skipped: 2025 week 5 not ingested here)")
        return
    margin = g["home_score"] - g["away_score"]
    points = g["home_score"] + g["away_score"]

    conn = ledger.connect(":memory:")
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    matchup = f'{g["away"]} @ {g["home"]}'
    payload = {"sport": "nfl", "date": "2025-W05", "game_bets": [
        {"bet_type": "spread", "team": g["home"], "line": -3.5,
         "matchup": matchup, "win_prob": .55, "edge": .05, "confidence": 6.8,
         "grade": "Play", "stake_units": 1.0, "recommended": True,
         "book": "schedule", "odds": -110},
        {"bet_type": "total", "matchup": matchup, "side": "OVER", "line": 40.5,
         "win_prob": .54, "edge": .04, "confidence": 6.5, "grade": "Play",
         "stake_units": 1.0, "recommended": True, "book": "schedule",
         "odds": -110},
    ]}
    assert ledger.log_recommendations(conn, payload) == 2
    assert ledger.settle_from_history(conn, h, sport="nfl") == 2, \
        "a Week-1 game bet never found its game — the week key stopped mapping"

    rows = {r["market"]: r for r in conn.execute("SELECT * FROM bets")}
    spread, total = rows["spread"], rows["total"]
    assert spread["status"] == ("won" if margin > 3.5 else
                                "push" if margin == 3.5 else "lost"), \
        f"spread graded {spread['status']} on a margin of {margin}"
    assert spread["actual"] == margin, "the spread graded off something else"
    assert total["status"] == ("won" if points > 40.5 else
                              "push" if points == 40.5 else "lost")
    assert total["actual"] == points
    # And the provenance survives the round trip, so CLV work can exclude it.
    assert spread["book"] == "schedule"


def test_show_games_hands_back_what_it_drew():
    """It used to return None, so nothing downstream could publish it."""
    tree = ast.parse(BUILD)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "show_games")
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    assert returns, "show_games returns nothing"
    assert any(isinstance(r.value, ast.Name) and r.value.id == "games"
               for r in returns), "show_games never hands back the games"


def test_the_launcher_falls_back_rather_than_keeping_an_empty_board():
    i = LAUNCH.index("def refresh_nfl(")
    body = LAUNCH[i:LAUNCH.index("\ndef ", i + 10)]
    assert '"--games-only", "--cached-odds",' in body, \
        "refresh_nfl has no schedule-only fallback, or stopped reading the "\
        "cached odds the moneyline needs"
    # It must only fall back AFTER the full build failed. (Prefix, not
    # the whole call: the full build grew a 600s ceiling on 2026-09-01,
    # and the ORDER is the contract here.)
    assert body.index("ok, tail = _run_build(args") < body.index("--games-only")
    assert "if not ok:" in body
    # A successful fallback is a success, not a silent failure.
    assert "return True" in body


def test_the_fallback_never_replaces_a_board_that_already_has_props():
    """Ethan, 2026-09-01: "nfl keeps showing props, then not showing
    props, then showing props, then not showing props."

    The full build and the --games-only fallback write the SAME file.
    Under load the full build was guillotined by the 180s default, the
    fallback rewrote the board without props and reported ok, and the
    next cycle put the props back — a flicker the loop called healthy.
    Two rules now: the model board gets the model-board ceiling, and a
    board that carries props is never downgraded to game lines only —
    it is kept, the failure is recorded, and --boards says so."""
    i = LAUNCH.index("def refresh_nfl(")
    body = LAUNCH[i:LAUNCH.index("\ndef ", i + 10)]
    assert "ok, tail = _run_build(args, timeout=600)" in body, \
        "the full NFL build is back on the 180s guillotine"
    guard = body.index("if not ok and _slate_props(out) > 0:")
    assert guard < body.index("--games-only"), \
        "the props guard must stand BEFORE the fallback"
    assert "kept last board" in body[guard:guard + 900]
    assert "return False" in body[guard:guard + 1200], \
        "a kept board is a FAILED refresh, not a quiet ok"
    # And the count reads the FULL copy, or every paywalled board
    # counts as propless.
    j = LAUNCH.index("def _slate_props(")
    assert "full_board_file" in LAUNCH[j:j + 900]

def test_the_edge_board_says_where_a_schedule_only_price_came_from():
    """Pricing the fallback made one existing sentence false.

    The Edge Board's headline read "N market(s) priced against a real book
    number" — true of every build that had one, and not true of this one,
    which prices off team ratings against the schedule's own spread and
    total at the standard −110 because no odds pull ran. Same board,
    different provenance; the line that describes it has to say which."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = app.index("const plays = rows.filter(")
    block = app[i:i + 1600]
    assert '"schedule-only"' in block, \
        "the Edge Board claims a book price on a build that pulled none"
    assert "no book prices were pulled" in block
    assert "priced against a real book number" in block, \
        "the normal build lost its provenance line"


def test_the_board_does_not_claim_a_verdict_it_never_reached():
    """Rendering the schedule-only payload for real (Playwright, phone
    size) showed the last gap: the board said "No props clear the current
    thresholds. Loosen the sliders" — advice that cannot work when nothing
    was ever built, and a claim that the model looked and declined when it
    never ran at all.

    The census branch above it already learned this lesson once, on the
    WNBA. This is the same lesson one step earlier in the season."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    # The heading stops asserting a verdict.
    i = app.index("function noMarketHeading()")
    head = app[i:app.index("\n}", i)]
    assert '"schedule-only"' in head and "Not priced yet" in head

    # The explainer answers the schedule-only case FIRST, before any
    # sentence about odds feeds — none of which are true here.
    j = app.index("function noMarketExplainer()")
    body = app[j:app.index("\n}", j)]
    assert body.index("schedule-only") < body.index("odds_status"), \
        "an odds-feed excuse must not pre-empt the real reason"

    # And the slider prompt is not offered when there is nothing to filter.
    # The default branch's copy, matched on the part that carries the
    # meaning. It read "No props clear the current thresholds. Loosen the
    # sliders…" as one sentence; the empty-state pass split the first
    # half into the slate's TITLE and left the advice as the body, which
    # changed the words without changing which branch says them.
    # ORDER, NOT A LOOKBACK WINDOW. This searched the 1200 characters
    # before "No props clear the current thresholds" for the
    # schedule-only guard, and broke when the empty-state pass split that
    # sentence into a slate title and a body — the branch order never
    # changed. What matters is that schedule-only is TESTED before the
    # default branch runs, so a board with nothing built is never told to
    # loosen sliders that have nothing to filter.
    # Inside renderRecommended's empty branch only. "Loosen the sliders"
    # also appears twice in the COMMENTS above it explaining why it is
    # bad advice here, and the first of those sits before the guard — so
    # a file-wide index() found the comment and called the code wrong.
    i = app.index("function renderRecommended(")
    body = app[i:app.index("\n  // Group by market", i)]
    guard = body.index('=== "schedule-only"')
    cause = body.index("no prop has been built")
    advice = body.index("msg = `Loosen the sliders")
    assert guard < cause < advice, \
        "schedule-only still falls through to \"loosen the sliders\""



def test_the_fallback_publishes_the_shapes_the_page_expects():
    """An empty LIST where every other board carries an OBJECT is a lie
    about which, and truthiness is what made it cost something.

    `renderParlays` guards on `!z`. An empty array is truthy, so the
    guard waved it through and the panel rendered itself out of nothing:
    "Screened undefined candidate tickets built from undefined eligible
    legs on tonight's board" — live, on the board the site publishes
    every day between the schedule appearing and Week 1 being played.
    Found by walking every page in every sport in a browser and looking
    for the word "undefined".

    `market_scan` is an object on every board ({stale, arbs, middles,
    …}); it ships as one here too. `parlays` is dropped outright,
    because the screen did not run — it needs player props — and the
    page has an honest empty state for a board with no screen."""
    block = _games_only_block()
    assert '"market_scan": {}' in block, \
        "market_scan is a list again, and the page reads it as an object"
    assert '"market_scan": []' not in block
    assert '"parlays": []' not in block


def test_the_panel_does_not_trust_the_payload_shape_either():
    """The producer was fixed, and this is the half that cannot be fixed
    anywhere else: a renderer that trusts a payload's shape will meet a
    payload that lies about it again."""
    i = APP.index("function renderParlays(")
    body = APP[i:APP.index("\n}", i)]
    assert 'typeof z !== "object"' in body and "Array.isArray(z)" in body, \
        "an empty array is truthy, and this guard is what catches it"
    # And the counts themselves never print a hole.
    assert "z.considered == null && z.eligible_legs == null" in body, \
        "the census can print 'Screened undefined candidate tickets' again"


# --- what the board's own cards open onto -----------------------------------
#
# Ethan, 2026-08-26: "on nfl im not ablt to click on the game props and it
# show me the bar graph and information and shit." He was reading THIS
# payload — it is what the site publishes every day between the schedule
# appearing and Week 1 being played — and every one of its sixty-four game
# bets opened a page saying "No recent results for this team yet", because
# the fallback shipped without `team_recent`. The full build has attached
# it since the chart existed. Reproduced in a browser against the real
# fallback payload, fixed, and pinned here.

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def test_the_fallback_ships_the_history_its_game_bets_open_onto():
    block = _games_only_block()
    assert "recent_games" in block,         "the schedule-only payload has no team history, so every game bet " \
        "on it opens onto an empty chart"
    assert '"team_recent": _team_recent' in block,         "team history is fetched and then not published"
    # The same guard the full build uses: a missing team log costs the
    # chart, never the board.
    assert "team logs skipped" in block


def test_a_real_board_is_never_labelled_sample_data():
    """Sixteen real games, real kickoffs, and lines priced off real team
    ratings — thirteen of which are JOURNALED to the public record. The
    badge read the string, saw it did not start with "live", and told
    every reader "these are not real games or real prices", while three
    other places in the same file said the opposite in words."""
    i = APP.index("function boardIsReal(")
    fn = APP[i:APP.index("\n}", i)]
    assert "startsWith(\"live\")" in fn and "REAL_BOARDS" in fn
    assert '"schedule-only"' in APP[APP.index("const REAL_BOARDS"):
                                   APP.index("const REAL_BOARDS") + 120]
    j = APP.index("function renderDataSource(")
    body = APP[j:APP.index("\n}", j)]
    assert "boardIsReal(src)" in body,         "the badge is back to reading the raw string"


def test_both_game_bet_surfaces_draw_the_same_chart():
    """The board card and the full page charted the same series through
    two different call sites, and they drifted: the card was fixed to
    stop the strip reading "SPREAD Spread" and to name the handicap, and
    the page never got either fix."""
    i = APP.index("function renderGameBetPage(")
    body = APP[i:APP.index("\nfunction ", i + 10)]
    assert "gameBetChart(b)" in body,         "the full page builds its own chart row again"
    assert "asProp" not in body, "the second, drifting call site came back"


def test_the_spread_chart_names_the_number_it_is_drawn_against():
    """A spread's bars are distance from the handicap, so the geometry's
    baseline is 0 — but the READER's baseline is -3.5, and `propAnalysis`
    takes `lineText` and `pill` for exactly that. Dropping them charted
    every spread on the site as "LINE 0"."""
    i = APP.index("function gameBetChart(")
    body = APP[i:APP.index("\n}", i)]
    assert "lineText: s.lineText" in body and "pill: s.pill" in body
    # And the series still offers them, or there is nothing to forward.
    j = APP.index("function gameBetSeries(")
    series = APP[j:APP.index("\n}\n\n/* The chart itself", j)]
    assert "lineText:" in series and "pill:" in series


def test_a_game_total_is_labelled_with_the_team_whose_games_it_charts():
    """The chart head said CHIEFS and the corner said BRONCOS, on the
    same card: the series draws a total off the HOME team's last games
    and the identity fell through `b.team` — which a total does not
    carry — to the away side."""
    i = APP.index("function gameBetChart(")
    body = APP[i:APP.index("\n}", i)]
    assert '=== "total"' in body and "b.home" in body,         "a game total is labelled with a team whose games it did not draw"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
