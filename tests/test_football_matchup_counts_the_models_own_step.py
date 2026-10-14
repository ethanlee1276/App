"""Football's matchup check counts the model's own Matchup step when the
scan has no lean on him.

Ethan, 2026-10-14, "do 1-11", to the call "The football matchup check. It
follows the board's rule: only the scan's lean on him counts. A
quarterback's runs and most backup roles have no lean, so their tier tops
out at Strong. Say if you want the model's own matchup step to count when
the scan has nothing": yes.

NFL and college now read the matchup the way baseball has since the board
was built (engine/likelyboard.MATCHUP_SOURCE "scan+model"): the scan's lean
decides where it has one; where it has none, the projection's own Matchup
step (engine/projection, the step the pick page draws) backs the pick when
it moved the number at least MODEL_MATCHUP_STEP toward its side, is against
it the other way, and says nothing in between. The off-board read in the
parlay checker asks the same question the same way.

    python3 tests/test_football_matchup_counts_the_models_own_step.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likelyboard as B                                  # noqa: E402

GAME = {"home": "DET", "away": "NYJ"}


def _rec(player, market, mult, why="NYJ allow 7.4 catches a game to slot receivers"):
    return {"player": player, "position": "WR", "market": market,
            "chain": {"base": 1.0, "steps": [{"key": "usage", "mult": 1.03},
                                             {"key": "matchup", "mult": mult, "why": why}]}}


def _ml(player, market, side="over", prob=0.64, odds=-150):
    """Our chance and the book's within the market check's agreement."""
    return {"player": player, "team": "DET", "opponent": "NYJ", "market": market, "side": side,
            "line": 5.5, "model_prob": prob, "odds": odds, "implied_prob": 0.60, "kind": "prop"}


def _board(sport, recs, rows, reads=None):
    result = {"games": [GAME], "recommendations": recs, "most_likely": rows,
              "matchup_picks": [], "td_scenarios": [],
              "scan_reads": reads or {}}
    out = B.build(result, record={}, sport=sport, band_verdict=None)
    return {r["player"]: r for r in out["rows"]}, out


def test_the_rule_is_footballs_as_it_is_baseballs():
    assert B.MATCHUP_SOURCE["nfl"] == B.MATCHUP_SOURCE["cfb"] == B.MATCHUP_SOURCE["mlb"] == "scan+model"
    assert B.MODEL_MATCHUP_STEP == 0.03


def test_no_lean_the_models_step_backs_the_pick_and_it_can_be_top():
    for sport in ("nfl", "cfb"):
        by, out = _board(sport, [_rec("Sam LaPorta", "receptions", 1.07)], [_ml("Sam LaPorta", "receptions")])
        r = by["Sam LaPorta"]
        assert out["matchup_source"] == "scan+model"
        assert r["checks"]["matchup"] is True, (sport, r["checks"], r["check_notes"])
        assert r["check_notes"]["matchup"].startswith("matchup moved our number +7%")
        assert "NYJ allow 7.4 catches" in r["check_notes"]["matchup"]
        assert r["tier"] == "top", (sport, r["checks"])


def test_no_lean_a_step_against_the_side_says_no_and_a_small_one_says_nothing():
    recs = [_rec("Jameson Williams", "rec_yds", 0.93), _rec("Kalif Raymond", "receptions", 1.02)]
    rows = [_ml("Jameson Williams", "rec_yds"), _ml("Kalif Raymond", "receptions")]
    by, _ = _board("nfl", recs, rows)
    assert by["Jameson Williams"]["checks"]["matchup"] is False
    assert by["Jameson Williams"]["check_notes"]["matchup"].endswith("— against this side")
    assert by["Kalif Raymond"]["checks"]["matchup"] is None
    assert by["Kalif Raymond"]["check_notes"]["matchup"].endswith("— not enough to call")
    assert by["Kalif Raymond"]["tier"] != "top", "nothing to call: tops out at Strong, as before"
    under, _ = _board("nfl", [_rec("Jameson Williams", "rec_yds", 0.93)],
                      [_ml("Jameson Williams", "rec_yds", side="under")])
    assert under["Jameson Williams"]["checks"]["matchup"] is True, "an under reads the step the other way"


def test_a_lean_still_decides_where_the_scan_has_one():
    reads = {"NYJ@DET": {"players": [{"player": "Amon-Ra St. Brown", "team": "DET", "opp": "NYJ", "pos": "WR",
                                      "read": "tough", "label": "Tough matchup", "lean": ["receptions"]}]}}
    by, _ = _board("nfl", [_rec("Amon-Ra St. Brown", "receptions", 1.09)],
                   [_ml("Amon-Ra St. Brown", "receptions", side="over")], reads=reads)
    r = by["Amon-Ra St. Brown"]
    assert r["checks"]["matchup"] is False and "Tough matchup" in r["check_notes"]["matchup"], \
        "the scan leans under; the model's +9% is not asked"


def test_no_step_at_all_is_said_and_stays_under_top():
    """A quarterback's carries: the defence never moves that number (shown,
    kept out — engine/defensevs), so there is no step to count."""
    by, _ = _board("nfl", [{"player": "Josh Allen", "position": "QB", "market": "rush_att",
                            "chain": {"base": 7.0, "steps": [{"key": "usage", "mult": 1.0}]}}],
                   [dict(_ml("Josh Allen", "rush_att"), team="BUF", opponent="MIA")])
    r = by["Josh Allen"]
    assert r["checks"]["matchup"] is None and r["tier"] != "top"
    assert r["check_notes"]["matchup"] == "the model has no matchup step for this market"


def test_the_touchdown_lane_is_untouched():
    td = {"kind": "td", "player": "Sam LaPorta", "team": "DET", "opponent": "NYJ", "market": "anytime_td",
          "side": "YES", "line": 0.5, "odds": 150, "model_prob": 0.45, "implied_prob": 0.40}
    by, _ = _board("nfl", [_rec("Sam LaPorta", "anytime_td", 1.20)], [td])
    assert by["Sam LaPorta"]["checks"]["matchup"] is None, "a scorer reads his touchdown matchup, never the step"


def test_the_parlay_checkers_read_asks_it_the_same_way():
    src = open(os.path.join(ROOT, "engine", "slipread.py"), encoding="utf-8").read()
    i = src.index("def checks(")
    body = src[i:src.index("\ndef ", i + 1)]
    assert 'source = LB.MATCHUP_SOURCE.get(league, "none")' in body
    assert 'elif source in ("scan+model", "model")' in body
    assert "LB._model_matchup(r, steps)" in body


def test_the_runbook_says_so():
    doc = open(os.path.join(ROOT, "docs", "WHEN_YOU_ARE_HOME.md"), encoding="utf-8").read()
    assert "football matchup check counts the model's own Matchup step" in doc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
