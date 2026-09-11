"""Tests for measured streak reversion (in-memory SQLite, synthetic data)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine.mlb.streaks import (
    classify, measure_reversion, attach_streaks, WINDOW, FACTOR_CLAMP,
)


def test_classify_needs_a_real_departure():
    assert classify(3.0, 2.0) == "hot"          # 150% of his level
    assert classify(1.0, 2.0) == "cold"         # 50%
    assert classify(2.3, 2.0) == "normal"       # ordinary variance
    # Tiny means (HR-like) never classify — ratio tests are noise there.
    assert classify(0.6, 0.2) == "normal"


def _seed(conn, reverting: bool):
    """60 players, one clean hot window each: level 2.0 for 12 games, then
    five 2.9 games (ratio 1.45 — hot ONLY when all five are in the window,
    so partial windows never contaminate), then the tested next game: a
    0.5 crater in the ``reverting`` world, the plain 2.0 level otherwise."""
    logs = []
    for p in range(60):
        vals = ([2.0] * 12 + [2.9] * 5
                + [0.5 if reverting else 2.0] + [2.0] * 4)
        for i, v in enumerate(vals):
            logs.append({"sport": "mlb", "season": 2026,
                         "period": f"2026-{4 + i // 28:02d}-{(i % 28) + 1:02d}",
                         "game_id": f"P{p}-{i}", "player": f"Player {p}",
                         "team": "NYY", "opponent": "BOS", "position": "RF",
                         "home": 1, "market": "total_bases", "value": v})
    db.upsert_player_logs(conn, logs)


def test_measured_reversion_only_when_the_data_shows_it():
    conn = db.connect(":memory:")
    _seed(conn, reverting=True)
    f = measure_reversion(conn, "total_bases")
    # Hot streaks measurably crater afterward -> factor below 1, clamped.
    assert "hot" in f and f["hot"]["factor"] < 1.0
    assert f["hot"]["factor"] >= FACTOR_CLAMP[0]
    assert f["hot"]["n"] >= 50

    conn2 = db.connect(":memory:")
    _seed(conn2, reverting=False)
    f2 = measure_reversion(conn2, "total_bases")
    # No reversion in the data -> essentially no factor (never invented).
    if "hot" in f2:
        assert abs(f2["hot"]["factor"] - 1.0) < 0.03


def test_attach_stamps_only_streaking_players():
    from engine.mlb.models import MLBGame, MLBProp, MLBGameLog, TOTAL_BASES
    from engine.models import SportsbookLine
    from engine.mlb.data_loader import MLBSlate

    def prop_with(recent, base_val, name):
        # logs newest-first: 5 recent games then 12 baseline games.
        vals = [recent] * WINDOW + [base_val] * 12
        return MLBProp(name, "NYY", "BOS", "RF", TOTAL_BASES,
                       [MLBGameLog(len(vals) - i, "BOS", v, date=f"2026-07-{i+1:02d}")
                        for i, v in enumerate(vals)], 2.0, None,
                       [SportsbookLine("proxy", 1.5)], bats="R", lineup_spot=3)

    hot = prop_with(4.0, 2.0, "Heater")
    steady = prop_with(2.1, 2.0, "Steady")
    cold = prop_with(0.8, 2.0, "Slumper")
    game = MLBGame(home="NYY", away="BOS", park="yankee")
    slate = MLBSlate(date="2026-07-26", games=[game], props=[hot, steady, cold])

    factors = {"total_bases": {"hot": {"factor": 0.95, "n": 800},
                               "cold": {"factor": 1.04, "n": 500}}}
    assert attach_streaks(slate, factors) == 2
    assert hot.streak_factor == 0.95 and "give back" in hot.streak_note
    assert cold.streak_factor == 1.04 and "bounce back" in cold.streak_note
    assert steady.streak_factor == 1.0 and steady.streak_note == ""

    # The matchup layer applies the measured factor with the note as reason.
    from engine.mlb.matchup import evaluate_matchup
    e_hot = evaluate_matchup(hot, game)
    e_steady = evaluate_matchup(steady, game)
    assert e_hot.multiplier < e_steady.multiplier
    assert any("give back" in r for r in e_hot.reasons)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
