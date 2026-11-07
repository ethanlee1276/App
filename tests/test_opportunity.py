"""Tests for the plate-appearance opportunity model (in-memory SQLite)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine.mlb.opportunity import (
    avg_pa_by_player, expected_pa, attach_opportunity,
)


def _seed_pa(conn, player="Nine Hole Guy", n=20, pa=3.7):
    logs = []
    for i in range(1, n + 1):
        date = f"2026-{4 + i // 28:02d}-{(i % 28) + 1:02d}"
        logs.append({"sport": "mlb", "season": 2026, "period": date,
                     "game_id": f"NH-{date}", "player": player,
                     "team": "NYY", "opponent": "BOS", "position": "RF",
                     "home": 1, "market": "pa", "value": pa})
    db.upsert_player_logs(conn, logs)


def test_avg_pa_needs_history():
    conn = db.connect(":memory:")
    _seed_pa(conn, "Nine Hole Guy", n=20, pa=3.7)
    _seed_pa(conn, "September Callup", n=4, pa=4.0)
    hist = avg_pa_by_player(conn)
    assert hist["nine hole guy"] == {"avg_pa": 3.7, "n": 20}
    # Thin histories never produce an average.
    assert "september callup" not in hist


def test_expected_pa_scales_with_run_environment():
    # Leadoff in a shootout beats leadoff in a pitchers' duel.
    neutral = expected_pa(1, 4.5)
    assert neutral == expected_pa(1)          # league total = no adjustment
    assert expected_pa(1, 6.0) > neutral > expected_pa(1, 3.5)
    # The environment nudge is clamped — a silly total can't be a lever.
    assert expected_pa(1, 20.0) <= neutral * 1.08 + 1e-9


def test_attach_compares_tonight_to_own_average():
    from engine.mlb.models import MLBGame, MLBProp, MLBGameLog, TOTAL_BASES
    from engine.models import SportsbookLine
    from engine.mlb.data_loader import MLBSlate

    def prop_at(spot):
        return MLBProp("Nine Hole Guy", "NYY", "BOS", "RF", TOTAL_BASES,
                       [MLBGameLog(i, "BOS", 1) for i in range(1, 6)], 1.0,
                       None, [SportsbookLine("proxy", 1.5)], bats="R",
                       lineup_spot=spot)

    game = MLBGame(home="NYY", away="BOS", park="yankee", total=9.0)
    promoted, usual = prop_at(2), prop_at(9)
    slate = MLBSlate(date="2026-07-26", games=[game],
                     props=[promoted, usual])
    hist = {"nine hole guy": {"avg_pa": 3.7, "n": 20}}

    n = attach_opportunity(slate, hist)
    # Usual nine-hole guy hitting SECOND tonight: ~4.5 PA vs his 3.7 — a
    # real, clamped volume boost with a human-readable reason.
    assert promoted.pa_factor > 1.05
    assert promoted.pa_factor <= 1.12
    assert "Batting 2nd" in promoted.pa_note and "volume boost" in promoted.pa_note
    # Same slot as always: expected ≈ his average, factor ≈ 1.
    assert abs(usual.pa_factor - 1.0) < 0.03
    assert n >= 1

    # The matchup layer uses the measured factor INSTEAD of the static bump.
    from engine.mlb.matchup import evaluate_matchup
    eff = evaluate_matchup(promoted, game)
    assert any("volume boost" in r for r in eff.reasons)
    assert not any("extra plate appearances" in r for r in eff.reasons)


def test_unmeasured_player_falls_back_to_static_bump():
    from engine.mlb.models import MLBGame, MLBProp, MLBGameLog, TOTAL_BASES
    from engine.models import SportsbookLine
    from engine.mlb.data_loader import MLBSlate
    from engine.mlb.matchup import evaluate_matchup

    game = MLBGame(home="NYY", away="BOS", park="yankee", total=9.0)
    prop = MLBProp("No History", "NYY", "BOS", "RF", TOTAL_BASES,
                   [MLBGameLog(i, "BOS", 1) for i in range(1, 6)], 1.0, None,
                   [SportsbookLine("proxy", 1.5)], bats="R", lineup_spot=1)
    slate = MLBSlate(date="2026-07-26", games=[game], props=[prop])

    assert attach_opportunity(slate, {}) == 0
    assert prop.pa_factor == 1.0
    eff = evaluate_matchup(prop, game)
    assert any("extra plate appearances" in r for r in eff.reasons)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
