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


def test_games_only_writes_a_payload_when_given_an_out():
    i = BUILD.index("if args.games_only:")
    block = BUILD[i:i + 5200]
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
    i = BUILD.index("if args.games_only:")
    block = BUILD[i:i + 5200]
    assert "price_games_only(games, args.season, args.week, config" in block, \
        "the fallback publishes a schedule with no prices again"
    assert '"game_bets": bets' in block, "the priced bets never reach the payload"
    # The player layer stays empty, because nothing built it.
    for empty in ('"recommendations": []', '"long_shots": []', '"parlays": []'):
        assert empty in block, f"the fallback invented {empty}"


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
    i = BUILD.index("if args.games_only:")
    assert '"date": f"{args.season}-W{args.week:02d}"' in BUILD[i:i + 5200]
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
    # It must only fall back AFTER the full build failed.
    assert body.index("ok, tail = _run_build(args)") < body.index("--games-only")
    assert "if not ok:" in body
    # A successful fallback is a success, not a silent failure.
    assert "return True" in body

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
    k = app.index("No props clear the current thresholds")
    seg = app[max(0, k - 1200):k]
    # The condition wraps across lines in the source, so match on the
    # parts rather than one brittle contiguous string.
    assert "generated_from" in seg and '"schedule-only"' in seg, \
        "schedule-only still falls through to \"loosen the sliders\""
    assert "no prop has been built" in seg, \
        "the copy must name the real cause"



if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
