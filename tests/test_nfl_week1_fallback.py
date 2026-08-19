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
  * IT PUBLISHES NO OPINION. No recommendations, no game bets, no
    journalling — a fallback that priced and journalled could
    double-journal the same slate when the full build later succeeds,
    and the record is the one thing that must never be double-counted.
  * IT SAYS WHY IT IS EMPTY, so the board reads as "nothing priced yet"
    rather than "no games".
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
    block = BUILD[i:i + 2600]
    assert "if args.out:" in block, "--games-only still only prints"
    assert "gate.publish(payload, args.out)" in block, \
        "the fallback must publish through the gate, like every other build"
    assert '"games": [_game_to_dict(g) for g in games]' in block, \
        "the slate must carry the real games, not a stub"


def test_the_fallback_publishes_no_opinion():
    """The restraint IS the feature. A fallback that priced and journalled
    could double-journal a slate the full build later prices again."""
    i = BUILD.index("if args.games_only:")
    block = BUILD[i:i + 2600]
    for empty in ('"recommendations": []', '"game_bets": []',
                  '"long_shots": []', '"parlays": []'):
        assert empty in block, f"the schedule-only payload invented {empty}"
    assert "journal" not in block.lower().split("if args.out:")[1][:1200], \
        "the fallback must never journal a bet"
    # And it says why it is empty.
    assert '"note":' in block
    assert "not published weekly player stats" in block


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
    assert '"--games-only", "--out", out' in body, \
        "refresh_nfl has no schedule-only fallback"
    # It must only fall back AFTER the full build failed.
    assert body.index("ok, tail = _run_build(args)") < body.index("--games-only")
    assert "if not ok:" in body
    # A successful fallback is a success, not a silent failure.
    assert "return True" in body

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
