"""Tests for measured platoon splits (in-memory SQLite)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine.mlb.platoon import platoon_splits, attach_platoon


def _seed(conn):
    """Lefty Masher: 1.0 TB/game overall, but 1.8 vs LHP and 0.6 vs RHP."""
    logs, starters = [], []
    for i in range(1, 31):
        date = f"2026-{4 + i // 28:02d}-{(i % 28) + 1:02d}"
        hand = "L" if i % 2 else "R"
        val = 1.8 if hand == "L" else 0.6
        logs.append({"sport": "mlb", "season": 2026, "period": date,
                     "game_id": f"LM-{date}", "player": "Lefty Masher",
                     "team": "NYY", "opponent": "BOS", "position": "RF",
                     "home": 1, "market": "total_bases", "value": val})
        starters.append({"sport": "mlb", "season": 2026, "period": date,
                         "game_id": "NYY@BOS", "team": "BOS",
                         "pitcher": f"P{hand}", "throws": hand})
    db.upsert_player_logs(conn, logs)
    db.upsert_game_starters(conn, starters)


def test_splits_measure_shrink_and_clamp():
    conn = db.connect(":memory:")
    _seed(conn)
    s = platoon_splits(conn, "total_bases")
    m = s["lefty masher"]
    # Crushes lefties, struggles vs righties — shrunk and clamped, so the
    # raw 1.5x becomes a bounded nudge, never a lever.
    assert m["L"] > 1.05 and m["R"] < 0.95
    assert 0.85 <= m["R"] and m["L"] <= 1.18
    assert m["nL"] == 15 and m["nR"] == 15
    # Thin histories never produce a split.
    assert "someone else" not in s


def test_attach_uses_tonights_starter_hand():
    from engine.mlb.models import (MLBGame, MLBProp, MLBGameLog, Pitcher,
                                   TOTAL_BASES)
    from engine.models import SportsbookLine
    from engine.mlb.data_loader import MLBSlate

    game = MLBGame(home="NYY", away="BOS", park="yankee",
                   pitchers={"BOS": Pitcher(name="Southpaw", throws="L")})
    prop = MLBProp("Lefty Masher", "NYY", "BOS", "RF", TOTAL_BASES,
                   [MLBGameLog(i, "BOS", 1) for i in range(1, 6)], 1.0, None,
                   [SportsbookLine("proxy", 1.5)], bats="R", lineup_spot=2)
    slate = MLBSlate(date="2026-07-26", games=[game], props=[prop])
    splits = {TOTAL_BASES: {"lefty masher": {"L": 1.12, "R": 0.92,
                                             "nL": 15, "nR": 15}}}
    assert attach_platoon(slate, splits) == 1
    assert prop.platoon_factor == 1.12
    assert "vs lefties" in prop.platoon_note

    # The matchup layer uses the measured split INSTEAD of the generic bump.
    from engine.mlb.matchup import evaluate_matchup
    eff = evaluate_matchup(prop, game)
    assert any("Measured split" in r for r in eff.reasons)
    assert not any("Platoon edge —" in r for r in eff.reasons)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
