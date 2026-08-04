"""Bullpen fatigue, the other half — and the market that had no matchup.

Relief workload has been measured here for a long time: engine/mlb/bullpen
scores each team's weighted relief innings over the two prior nights and
the hitter path lifts opposing production for a tired pen. Two things were
missing from that picture.

**The starter in front of the pen.** The same measurement that says the
opposition will feast late says the manager has nobody to bring in — so
he rides his starter deeper. That is the most reliably observable
managerial behaviour in baseball and it lands directly on the outs
market.

**The outs market had no matchup at all.** ``evaluate_matchup`` routed
hitters and strikeouts and returned a flat 1.0 for everything else, so
the market added specifically to price how deep a start goes was priced
with no matchup input whatsoever.

And underneath both: the multiplier that already ships was never
journaled, so nothing could ever check it. ``pen_own`` and ``pen_opp``
are now dimensions the blind-spot miner bands, slices under false-
discovery control, and can convict — which is how a hand-tuned +6%
finally gets to be right or wrong on the record rather than forever.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger
from engine import losspatterns as lp
from engine.mlb import bullpen
from engine.mlb.matchup import evaluate_matchup
from engine.mlb.models import MLBGame, MLBProp, HITS, OUTS, STRIKEOUTS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _game(own=None, opp=None, home="BOS", away="NYY"):
    g = MLBGame(home=home, away=away, park=home)
    if own is not None:
        g.bullpen_fatigue[home] = own
    if opp is not None:
        g.bullpen_fatigue[away] = opp
    return g


def _prop(market=OUTS, team="BOS", opponent="NYY"):
    return MLBProp(player="A Starter", team=team, opponent=opponent,
                   position="SP", market=market, logs=[], career_avg=15.0,
                   vs_pitcher_avg=None, lines=[])


# --- the leash ---------------------------------------------------------------
def test_a_rested_pen_changes_nothing():
    for score in (0.0, 3.0, bullpen.TIRED_MIN - 0.1):
        assert bullpen.leash_factor(score) == 1.0
        assert bullpen.leash_factor(score, market_is_outs=False) == 1.0
    assert bullpen.leash_factor(None) == 1.0


def test_a_worked_pen_lengthens_the_start_and_is_capped():
    assert bullpen.leash_factor(9.0) > 1.0
    assert bullpen.leash_factor(100.0) == bullpen.LEASH_MAX
    # Monotone in workload.
    assert bullpen.leash_factor(12.0) > bullpen.leash_factor(8.0)


def test_strikeouts_inherit_the_leash_at_half_strength():
    """More batters faced, same per-batter stuff — and a tiring starter's
    rate usually falls, so length must not be priced as though it were
    stuff."""
    outs = bullpen.leash_factor(12.0, market_is_outs=True)
    ks = bullpen.leash_factor(12.0, market_is_outs=False)
    assert 1.0 < ks < outs


# --- the market that had no matchup ------------------------------------------
def test_the_outs_market_is_no_longer_priced_with_nothing():
    """Regression: evaluate_matchup used to fall through to a flat 1.0 for
    outs, so the market built to price start length had no matchup input
    of any kind."""
    tired = evaluate_matchup(_prop(OUTS), _game(own=12.0))
    assert tired.multiplier > 1.0
    assert any("bullpen" in r.lower() for r in tired.reasons)


def test_a_fresh_pen_leaves_the_outs_number_alone():
    flat = evaluate_matchup(_prop(OUTS), _game(own=1.0))
    assert flat.multiplier == 1.0 and not flat.reasons


def test_an_unmeasured_pen_says_nothing_rather_than_assuming_fresh():
    none_known = evaluate_matchup(_prop(OUTS), _game())
    assert none_known.multiplier == 1.0 and not none_known.reasons


def test_the_starters_own_pen_reaches_his_strikeout_prop_too():
    tired = evaluate_matchup(_prop(STRIKEOUTS), _game(own=12.0))
    rested = evaluate_matchup(_prop(STRIKEOUTS), _game(own=1.0))
    assert tired.multiplier > rested.multiplier
    assert any("Own bullpen" in r for r in tired.reasons)


def test_the_opponents_pen_still_drives_the_hitter_path():
    """The half that already worked must keep working — and it reads the
    OPPOSING pen, not the hitter's own."""
    hot = evaluate_matchup(_prop(HITS, team="NYY", opponent="BOS"),
                           _game(own=12.0))
    assert hot.multiplier > 1.0
    assert any("Opposing bullpen worked" in r for r in hot.reasons)


def test_the_two_sides_are_never_confused():
    """A starter whose OPPONENT's pen is gassed gets no longer leash — the
    tired arms are in the other dugout."""
    wrong_side = evaluate_matchup(_prop(OUTS, team="BOS"), _game(opp=12.0))
    assert wrong_side.multiplier == 1.0


# --- journalled, and therefore checkable -------------------------------------
def test_a_journaled_bet_carries_both_pens():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    ledger.log_recommendations(conn, {
        "sport": "mlb", "date": "2099-01-01",
        "recommendations": [{
            "player": "A Starter", "market": "outs", "side": "OVER",
            "line": 16.5, "odds": -110, "grade": "A", "stake_units": 1.0,
            "hit_prob": 0.56, "edge": 0.04, "confidence": 8.0,
            "recommended": True, "team": "BOS", "opponent": "NYY",
            "pen_own": 11.5, "pen_opp": 2.0}],
        "games": []})
    row = conn.execute("SELECT pen_own, pen_opp FROM bets").fetchone()
    assert (row[0], row[1]) == (11.5, 2.0)


def test_the_bands_separate_a_fresh_pen_from_a_gassed_one():
    assert lp.pen_band(1.0) == "pen fresh"
    assert lp.pen_band(4.0) == "pen normal"
    assert lp.pen_band(7.0) == "pen taxed"
    assert lp.pen_band(14.0) == "pen gassed"
    assert lp.pen_band(None) is None and lp.pen_band("x") is None


def test_the_two_pens_are_separate_dimensions():
    """Pooling them would average two opposite effects: the opposing pen
    lifts a hitter's number, the own pen lengthens a starter's."""
    f = lp.features_of(side="OVER", odds=-110, prob=0.55,
                       pen_opp=12.0, pen_own=1.0)
    assert f["pen_opp"] == "pen gassed" and f["pen_own"] == "pen fresh"


def test_the_miner_reads_both_pens_off_the_journal():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, odds,"
        " hit_prob, stake_units, status, category, pen_own, pen_opp)"
        " VALUES ('t','mlb','2026-07-01','X','outs','OVER',16.5,-110,"
        "0.56,1.0,'lost','main',12.0,1.0)")
    conn.commit()
    feats = lp.records_from_ledger(conn)[0]["feats"]
    assert feats["pen_own"] == "pen gassed" and feats["pen_opp"] == "pen fresh"


def test_a_convicted_pen_pocket_vetoes_the_next_matching_pick():
    import json as _json
    path = tempfile.mktemp(suffix=".json")
    open(path, "w").write(_json.dumps({"findings": [], "closed": [
        {"sport": "mlb", "market": "outs", "dim": "pen_own",
         "value": "pen gassed", "reading": "ran hot"}]}))
    hit = lp.veto("mlb", "outs", side="OVER", odds=-110, pen_own=14.0,
                  path=path)
    assert hit and "pen gassed" in hit
    # A fresh pen is a different band; an unmeasured pen is never blocked.
    assert lp.veto("mlb", "outs", side="OVER", odds=-110, pen_own=1.0,
                   path=path) is None
    assert lp.veto("mlb", "outs", side="OVER", odds=-110, path=path) is None


def test_the_miner_can_convict_a_tired_pen_pocket():
    recs = []
    for i in range(120):        # gassed-pen overs: said 60%, hit 40%
        recs.append({"sport": "mlb", "market": "outs", "prob": 0.60,
                     "won": 1 if i < 48 else 0,
                     "feats": lp.features_of(side="OVER", odds=-110,
                                             prob=0.60, pen_own=13.0)})
    for i in range(120):        # fresh pens: calibrated
        recs.append({"sport": "mlb", "market": "outs", "prob": 0.60,
                     "won": 1 if i < 72 else 0,
                     "feats": lp.features_of(side="OVER", odds=-110,
                                             prob=0.60, pen_own=1.0)})
    out = lp.mine(recs)
    pens = [f for f in out["findings"] if f["dim"] == "pen_own"]
    assert any(f["value"] == "pen gassed" for f in pens), out["findings"]


def test_the_board_journals_the_pen_on_every_mlb_pick():
    from engine.mlb.pipeline import run_mlb_slate
    out = run_mlb_slate(os.path.join(ROOT, "data", "mlb_sample_slate.json"))
    recs = out["recommendations"]
    assert recs and all("pen_own" in r and "pen_opp" in r for r in recs)


def test_the_mlb_gate_hands_the_veto_both_pens():
    src = open(os.path.join(ROOT, "engine", "mlb", "betting.py"),
               encoding="utf-8").read()
    i = src.index("pattern_block = lp_veto(")
    assert "pen_own=" in src[i:i + 900] and "pen_opp=" in src[i:i + 900]


def test_the_lab_can_propose_on_the_pen():
    from engine import hypotheses as hyp
    props = hyp.SCHEMA["properties"]["hypotheses"]["items"]
    for dim in ("pen_own", "pen_opp"):
        assert dim in hyp.DIMS
        assert dim in props["properties"] and dim in props["required"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
