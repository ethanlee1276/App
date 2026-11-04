"""The NBA scout names only the spots two seasons measured to go wrong
(engine/nba/scout, docs/NBA_LAB.md "The scout").

Ethan, 2026-11-04: "I don't know much about NBA, so I want to make sure
we're picking the right bets, reading the right scripts." The scout writes
down what a basketball person checks before trusting a pick, with every
threshold fixed BEFORE it was measured. Then each was measured, before any
model and after ours, and given a verdict:

  * WARNING (on the card): an under while a regular teammate sits, an
    over the night one returns, an over after his minutes dropped, an
    under in a projected shootout, a man whose games swing, a man barely
    into his season — still over-claimed after everything else;
  * PRICED (our number carries it now): his first games back, a role
    jump, a hot shooting run;
  * REFUSED (not a warning at all): overs in a projected blowout, on a
    back-to-back;
  * UNMEASURED: lines far from his last five (the seasons hold no book
    lines), an over in a projected grind (too rare).

A flag moves no number. Every card — the Edge side, and Most Likely's own
side and rung — reads its flags for the side it takes.

Run directly: `python3 tests/test_the_nba_scout_reads_the_measured_spots.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.nba import pipeline as P              # noqa: E402
from engine.nba import scout as S                 # noqa: E402


def test_the_thresholds_are_the_ones_written_before_measuring():
    assert (S.BLOWOUT_SPREAD, S.FAST_TOTAL, S.SLOW_TOTAL) == (10.0, 236.0, 214.0)
    assert (S.LINE_STRETCH, S.LINE_SHRINK, S.ROLE_UP, S.ROLE_DOWN) == (1.15, 0.85, 1.20, 0.80)
    assert (S.BOOM_BUST_CV, S.THIN_GAMES, S.HOT_HAND, S.HOT_HAND_ATTEMPTS) == (0.55, 5, 0.08, 25)


def test_every_flag_has_its_verdict_and_only_warnings_reach_the_card():
    assert set(S.VERDICT) == set(S.FLAGS)
    assert {v for v, _t in S.VERDICT.values()} == {"warning", "priced", "refused", "unmeasured"}
    assert S.CARD == ("fast_under", "mate_out_under", "mate_back_over", "role_down_over", "boom_bust", "thin")
    assert {c for c, (v, _t) in S.VERDICT.items() if v == "priced"} == {"back_over", "role_up_under", "hot_hand_over"}
    assert {c for c, (v, _t) in S.VERDICT.items() if v == "refused"} == {"blowout_over", "b2b_over"}


CTX = {"starter": True, "spread": -12.0, "total": 240.0, "rest": "b2b_home",
       "values": [20.0, 22.0, 18.0, 21.0, 19.0, 20.0, 23.0, 17.0, 20.0, 20.0],
       "minutes": [34.0, 34.0, 35.0, 25.0, 25.0, 24.0, 25.0, 25.0, 26.0, 25.0],
       "games_season": 12, "missed_last": True, "mate_out": True, "mate_back": True}


def test_an_under_reads_the_warnings_and_an_over_reads_none_of_the_refused():
    codes, said = S.read(CTX, "pts", "UNDER", 20.5)
    assert codes == ["fast_under", "mate_out_under"], codes
    assert len(said) == 2 and all(t.endswith(".") for t in said)
    assert "regular teammate sits" in said[1] and "3-7% less often" in said[1], said[1]
    over, _said = S.read(CTX, "pts", "OVER", 20.5)
    # Blowout, back-to-back, first game back: each raised by `flags`, none on
    # the card (refused, or our number has it); a regular's return is.
    raised = S.flags(S.situation("pts", "OVER", 20.5, CTX["values"], CTX["minutes"], True, -12.0, 240.0,
                                 "b2b_home", 12, True, True, True))
    assert {"blowout_over", "b2b_over", "back_over", "mate_back_over"} <= set(raised), raised
    assert over == ["mate_back_over"], over
    drop = dict(CTX, minutes=[20.0, 21.0, 19.0, 30.0, 31.0, 29.0, 30.0, 30.0, 31.0, 29.0], mate_back=False)
    assert S.read(drop, "pts", "OVER", 20.5)[0] == ["role_down_over"], "a drop that holds: on the card"


def test_a_swinging_man_and_an_early_season_man():
    swing = dict(CTX, values=[2.0, 9.0, 0.0, 7.0, 1.0, 8.0, 3.0, 0.0, 10.0, 2.0], games_season=3,
                 total=225.0, mate_out=False, mate_back=False)
    codes, said = S.read(swing, "ast", "OVER", 4.5)
    assert codes == ["boom_bust", "thin"], codes
    assert S.read(dict(swing, games_season=None), "ast", "OVER", 4.5)[0] == ["boom_bust"], \
        "an unknown season count raises nothing"
    assert S.read(None, "pts", "UNDER", 20.5) == ([], []) and S.read(CTX, "pts", "", 20.5) == ([], [])


def test_each_row_reads_its_own_side_and_rung():
    rows = [{"market": "pts", "side": "UNDER", "line": 20.5, "scout_ctx": CTX},
            {"market": "pts", "side": "over", "line": 15.5, "scout_ctx": CTX},
            {"market": "pts", "side": "UNDER", "line": 20.5},
            "not a row"]
    assert S.annotate(rows) == 2
    assert rows[0]["scout_flags"] == ["fast_under", "mate_out_under"]
    assert rows[1]["scout_flags"] == ["mate_back_over"] and len(rows[1]["scout_notes"]) == 1, \
        "the other side reads its own: the over the night a regular returns"
    quiet = [{"market": "pts", "side": "OVER", "line": 15.5, "scout_ctx": dict(CTX, mate_back=False)}]
    assert S.annotate(quiet) == 0 and quiet[0]["scout_flags"] == [] and quiet[0]["scout_notes"] == []
    assert "scout_flags" not in rows[2], "a row the build gave no facts is left alone"


def test_the_edge_card_carries_them_and_most_likely_rereads_them():
    prop = {"player": "X", "team": "BOS", "opponent": "NYK", "market": "pts", "line": 14.5,
            "over_odds": -110, "under_odds": -110, "book": "fanduel",
            "minutes": [30.0] * 12, "values": [15.0] * 12, "is_starter": True,
            "spread": -3.0, "rest": "1day", "scout_ctx": dict(CTX, total=238.0)}
    rows = [r for r in P.shared_recommendations([prop]) if r.get("player") == "X"]
    assert rows, "the board's own rows"
    r = rows[0]
    assert r["scout_ctx"] == prop["scout_ctx"]
    assert r["scout_flags"] == S.read(prop["scout_ctx"], "pts", r["side"], r["line"])[0]
    assert r["scout_notes"] == S.read(prop["scout_ctx"], "pts", r["side"], r["line"])[1]
    if r["side"] == "UNDER":
        assert "mate_out_under" in r["scout_flags"]
    bare = [x for x in P.shared_recommendations([dict(prop, scout_ctx=None)]) if x.get("player") == "X"][0]
    assert bare["scout_flags"] == [] and bare["scout_notes"] == [], "no facts, no flags (the WNBA's rows)"
    src = (ROOT / "engine" / "nba" / "pipeline.py").read_text()
    assert '"scout_ctx": prop.get("scout_ctx")' in src and '"scout_flags": scout_flags' in src
    likely = (ROOT / "engine" / "likely.py").read_text()
    assert '"scout_ctx": row.get("scout_ctx")' in likely, "Most Likely rows keep the facts"
    board = (ROOT / "engine" / "likelyboard.py").read_text()
    i = board.index("THE NBA SCOUT'S READ")
    assert 'if sport == "nba":' in board[i:i + 900] and "_nsc.annotate(" in board[i:i + 900]
    js = (ROOT / "web" / "js" / "app.js").read_text()
    i = js.index("function cardHTML(r)")
    assert "r.scout_notes" in js[i:i + 700], "the Edge card draws them"
    build = (ROOT / "nba_build.py").read_text()
    assert '"scout_ctx": (scout_context(' in build and 'if args.league == "nba" else None' in build, \
        "the NBA only: the WNBA was not measured"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, f in tests:
        try:
            f()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
