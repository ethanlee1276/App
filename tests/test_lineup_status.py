"""lineup_status: the PA half of every batter prop, journaled and mined.

The triage bench's third spec, completing the set. Every batter-prop
over is plate appearances times per-PA production; the batting slot and
whether the card was official at pick time are the only journaled-
adjacent levers on the PA half. If the record's gap concentrates in the
projected bands, the blind spot is timing and scratch risk — not the
hitting model — and that distinction decides what gets fixed next.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger
from engine import losspatterns as lp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- the bands ---------------------------------------------------------------
def test_the_slot_bands_carry_both_the_slot_and_its_certainty():
    assert lp.lineup_band(1, True) == "confirmed 1-3"
    assert lp.lineup_band(5, True) == "confirmed 4-6"
    assert lp.lineup_band(9, False) == "projected 7-9"
    assert lp.lineup_band(2, False) == "projected 1-3"
    assert lp.lineup_band(0, True) == "not in lineup"
    assert lp.lineup_band(None, True) is None       # pitcher props, old rows
    assert lp.lineup_band("garbage", True) is None


# --- journal → miner → veto --------------------------------------------------
def test_a_journaled_bet_carries_its_slot_and_certainty():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    ledger.log_recommendations(conn, {
        "sport": "mlb", "date": "2099-01-01",
        "recommendations": [{
            "player": "Slot Bat", "market": "hits", "side": "OVER",
            "line": 1.5, "odds": -110, "grade": "A", "stake_units": 1.0,
            "hit_prob": 0.57, "edge": 0.04, "confidence": 8.0,
            "recommended": True, "team": "CHC", "opponent": "PHI",
            "lineup_slot": 2, "lineup_confirmed": False}],
        "games": []})
    row = conn.execute(
        "SELECT lineup_slot, lineup_conf FROM bets").fetchone()
    assert (row[0], row[1]) == (2, 0)


def test_the_miner_reads_the_slot_off_the_journal():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, odds,"
        " hit_prob, stake_units, status, category, lineup_slot, lineup_conf)"
        " VALUES ('t','mlb','2026-07-01','X','hits','OVER',1.5,-110,"
        "0.57,1.0,'won','main',7,0)")
    conn.commit()
    recs = lp.records_from_ledger(conn)
    assert recs[0]["feats"]["slot"] == "projected 7-9"


def test_a_convicted_projected_pocket_vetoes_and_spares_the_confirmed():
    import json as _json
    path = tempfile.mktemp(suffix=".json")
    open(path, "w").write(_json.dumps({"findings": [], "closed": [
        {"sport": "mlb", "market": "hits", "dim": "slot",
         "value": "projected 7-9", "reading": "ran hot"}]}))
    hit = lp.veto("mlb", "hits", side="OVER", odds=-110,
                  lineup_slot=8, lineup_conf=False, path=path)
    assert hit and "projected 7-9" in hit
    # The SAME slot with the card posted is a different, unconvicted band.
    assert lp.veto("mlb", "hits", side="OVER", odds=-110,
                   lineup_slot=8, lineup_conf=True, path=path) is None
    # And a gate with no slot to report is never falsely blocked.
    assert lp.veto("mlb", "hits", side="OVER", odds=-110, path=path) is None


def test_the_miner_can_convict_a_projected_slot_pocket():
    recs = []
    for i in range(120):    # projected bottom-third overs: said 60%, hit 40%
        recs.append({"sport": "mlb", "market": "hits", "prob": 0.60,
                     "won": 1 if i < 48 else 0,
                     "feats": lp.features_of(side="OVER", odds=-110,
                                             prob=0.60, lineup_slot=8,
                                             lineup_conf=False)})
    for i in range(120):    # confirmed top-third: calibrated
        recs.append({"sport": "mlb", "market": "hits", "prob": 0.60,
                     "won": 1 if i < 72 else 0,
                     "feats": lp.features_of(side="OVER", odds=-110,
                                             prob=0.60, lineup_slot=2,
                                             lineup_conf=True)})
    out = lp.mine(recs)
    slots = [f for f in out["findings"] if f["dim"] == "slot"]
    assert any(f["value"] == "projected 7-9" for f in slots), out["findings"]


# --- the pipeline attaches what the journal records --------------------------
def test_the_board_ships_slot_for_batters_and_none_for_pitchers():
    from engine.mlb.models import PITCHER_MARKETS
    from engine.mlb.pipeline import run_mlb_slate
    out = run_mlb_slate(os.path.join(ROOT, "data", "mlb_sample_slate.json"))
    batters = [r for r in out["recommendations"]
               if r["market"] not in PITCHER_MARKETS]
    pitchers = [r for r in out["recommendations"]
                if r["market"] in PITCHER_MARKETS]
    assert batters and all("lineup_slot" in r and "lineup_confirmed" in r
                           for r in batters)
    assert all("lineup_slot" not in r for r in pitchers), \
        "a pitcher prop has no batting slot; NULL must say so"
    assert all("lineup_slot" in s for s in out["long_shots"])


def test_the_mlb_gate_hands_the_veto_the_slot():
    src = open(os.path.join(ROOT, "engine", "mlb", "betting.py"),
               encoding="utf-8").read()
    i = src.index("pattern_block = lp_veto(")
    before = src[max(0, i - 900):i]
    assert '_env["lineup_slot"]' in before
    assert "PITCHER_MARKETS" in before, \
        "pitcher props must not report a phantom slot"


def test_the_lab_can_propose_on_the_slot():
    from engine import hypotheses as hyp
    assert "slot" in hyp.DIMS
    props = hyp.SCHEMA["properties"]["hypotheses"]["items"]
    assert "slot" in props["properties"] and "slot" in props["required"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
