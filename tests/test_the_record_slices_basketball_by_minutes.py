"""The record slices basketball by its minutes and hockey by its ice time
(2026-11-14).

A basketball prop is a minutes bet wearing a stat's name, and every
basketball pick has journaled the minutes it assumed (`bets.proj_minutes`)
for months. Neither the loss miner nor the hypothesis lab could slice on it,
so "do our overs on the bench's 18-minute men run hot?" had the rows and no
dimension, and the lab, which had never proposed a basketball hypothesis,
had no basketball lever to propose with. The minutes are a dimension now,
banded where each league's rotation sits, on the rows already settled; a
hockey skater's projected ice time is journaled and banded the same way;
and the loss veto reads both, so a slice the record closes is refused.

    python3 tests/test_the_record_slices_basketball_by_minutes.py
"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import hypotheses as HY                  # noqa: E402
from engine import losspatterns as LP                # noqa: E402


def test_minutes_are_banded_where_each_leagues_rotation_sits():
    for sport in ("nba", "wnba", "cbb"):
        assert LP.minutes_band(16.0, sport) == "under 20 min"
        assert LP.minutes_band(24.5, sport) == "20-28 min"
        assert LP.minutes_band(31.0, sport) == "28-34 min"
        assert LP.minutes_band(36.2, sport) == "34+ min"
    assert LP.minutes_band(12.0, "nhl") == "under 14 min"
    assert LP.minutes_band(16.5, "nhl") == "14-18 min"
    assert LP.minutes_band(19.8, "nhl") == "18-21 min"
    assert LP.minutes_band(23.0, "nhl") == "21+ min"
    assert LP.minutes_band(30.0, "nfl") is None, "a league without the dimension has none"
    assert LP.minutes_band(None, "nba") is None and LP.minutes_band(0, "nba") is None


def test_the_settled_rows_already_carry_it():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cols = ("sport, market, side, odds, hit_prob, book, date, ts, status, category, lead_min, park_hr, "
            "wind_out, roofed, lineup_slot, lineup_conf, rest_days, body_clock, pen_own, pen_opp, "
            "velo_delta, tto_proj, opp_zone_rate, proj_minutes")
    conn.execute(f"CREATE TABLE bets ({cols})")
    conn.execute(f"INSERT INTO bets ({cols}) VALUES ('nba','pts','OVER',-110,0.56,'DK','2026-11-01',"
                 "'2026-11-01T15:00:00','won','paper',NULL,NULL,NULL,0,NULL,0,NULL,NULL,NULL,NULL,"
                 "NULL,NULL,NULL,18.4)")
    rec = LP.records_from_ledger(conn)[0]
    assert rec["feats"]["minutes"] == "under 20 min", rec["feats"]


def test_the_lab_can_propose_on_it_and_the_veto_enforces_it():
    assert "minutes" in HY.DIMS, "a dimension absent from DIMS is one the lab can never propose about"
    path = Path(tempfile.mkdtemp()) / "losspatterns.json"
    path.write_text(json.dumps({"closed": [{"sport": "nba", "market": "reb", "dim": "minutes",
                                            "value": "under 20 min", "reading": "ran hot"}]}))
    said = LP.veto("nba", "reb", side="OVER", odds=-110, prob=0.55, proj_minutes=17.0, path=path)
    assert said and "under 20 min" in said, said
    assert LP.veto("nba", "reb", side="OVER", odds=-110, prob=0.55, proj_minutes=31.0, path=path) is None


def test_both_boards_hand_the_veto_their_minutes():
    nba = (ROOT / "engine" / "nba" / "pipeline.py").read_text(encoding="utf-8")
    assert 'rest_days=prop.get("rest_days"),\n                     proj_minutes=proj_min)' in nba
    nhl = (ROOT / "nhl_build.py").read_text(encoding="utf-8")
    body = nhl[nhl.index("def price_prop("):nhl.index("# --- game lines")]
    assert 'toi = None if prop.market in M.GOALIE_MARKETS else proj.get("toi")' in body
    assert "proj_minutes=toi)" in body and '"proj_minutes": round(toi, 1) if toi else None,' in body


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
