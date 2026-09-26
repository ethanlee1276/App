"""Red-zone chances are this week's, not last month's.

Ethan, 2026-09-26, on Cam Skattebo's scenario reading "4.0 expected
red-zone chances": "last week the starting QB for that team was announced
out for the season so no way that number is correct now."

The 4.0 was his per-game average from games the old quarterback started,
carried forward unchanged. His touchdown CHANCE already moved (it is built
on the market's implied total, which knows the quarterback is gone); the
red-zone line and the scenario's red-zone score did not.
`RedZoneUsage.expected_this_week` scales the measured average by the
points his team is expected to score now against what it was expected to
score in those games (engine/nflusage records the latter), clamped; the
reason, the watch row, the read and the scenario carry both numbers, and a
quarterback change on his team is its own scenario line.
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import tdscenarios as S                              # noqa: E402
from engine.touchdowns import RedZoneUsage, RZ_SCALE_CLAMP       # noqa: E402


def test_a_lower_total_scales_his_chances_down_and_the_clamp_holds():
    rz = RedZoneUsage(carries_inside_10=3.5, targets_inside_10=0.5, rz_touch_share=0.4,
                      measured=True, team_implied=25.0, games=3)
    assert rz.opportunities == 4.0
    assert abs(rz.expected_this_week(20.0) - 3.2) < 1e-9, "25 expected points then, 20 now"
    assert rz.expected_this_week(None) == 4.0 and RedZoneUsage(carries_inside_10=4.0).expected_this_week(20.0) == 4.0
    assert abs(rz.expected_this_week(5.0) - 4.0 * RZ_SCALE_CLAMP[0]) < 1e-9, "one strange total cannot halve a role"


def test_the_reason_says_both_numbers():
    from engine import touchdowns as T
    src = open(os.path.join(ROOT, "engine", "touchdowns.py"), encoding="utf-8").read()
    assert "rz_now = rz.expected_this_week(implied)" in src
    assert 'f" this week — {rz.opportunities:.1f} a game before, scaled to "' in src
    assert '"rz_expected": round(rz_now, 2),' in src and '"rz_chances": info.get("rz_expected"),' in src
    assert '"opportunities": rz.opportunities,' in src, "the value board's grade input is unchanged"
    assert T.RZ_SCALE_CLAMP == (0.6, 1.4)


def test_the_measurement_records_what_his_team_was_expected_to_score():
    from engine import nflusage as U
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE player_game_logs (sport, season, period, player, team, market, value)")
    conn.execute("CREATE TABLE games (sport, season, period, home, away, spread, total)")
    for wk in ("001", "002"):
        conn.execute("INSERT INTO player_game_logs VALUES ('nfl', 2026, ?, 'Cam Skattebo', 'NYG', 'rz_car', 4)", (wk,))
        conn.execute("INSERT INTO player_game_logs VALUES ('nfl', 2026, ?, 'Other Back', 'NYG', 'rz_car', 2)", (wk,))
    # NYG at home, laying 3 in a 47 (25 expected), then away getting 1 in a 47 (23).
    conn.execute("INSERT INTO games VALUES ('nfl', 2026, '001', 'NYG', 'DAL', -3, 47)")
    conn.execute("INSERT INTO games VALUES ('nfl', 2026, '002', 'PHI', 'NYG', -1, 47)")
    got = U.red_zone_usage(conn, 2026)
    rz = next(v for k, v in got.items() if "skattebo" in str(k).lower())
    assert rz.team_implied == 24.0 and rz.games == 2 and rz.carries_inside_10 == 4.0, rz


def _read(td):
    return {"player": "Cam Skattebo", "team": "NYG", "opp": "TEN", "pos": "RB", "read": "neutral",
            "usage": {"carry_share": 0.48, "snap_pct": 0.56}, "td": td}


def test_the_scenario_says_the_scaled_number_and_the_quarterback_change():
    units = {"blend": 0.55, "def": {"rushing": {"rank": 29}, "passing": {"rank": 10}}}
    td = {"model_prob": 0.42, "odds": 113, "book": "Novig", "implied_total": 20.5,
          "rz_chances": 3.35, "rz_before": 4.0, "rz_then_implied": 24.5,
          "qb_change": "Russell Wilson (OUT) — Jameis Winston starts"}
    s = S.score(_read(td), units)
    assert s, "still a scenario"
    assert ("3.4 expected red-zone chances this week (4.0 a game before, scaled to 20.5 expected points "
            "from 24.5)") in s["lines"], s["lines"]
    assert "QB change: Russell Wilson (OUT) — Jameis Winston starts — the lines above already account for it" \
        in s["lines"]
    # Unmoved, the line reads as before.
    flat = dict(td, rz_chances=4.0, qb_change=None)
    assert "4.0 expected red-zone chances" in S.score(_read(flat), units)["lines"]


def test_the_read_stamp_carries_them():
    src = open(os.path.join(ROOT, "engine", "gamescan.py"), encoding="utf-8").read()
    assert '"rz_before": r.get("rz_before"), "rz_then_implied": r.get("rz_then_implied"),' in src
    assert '"qb_change": ((r.get("qb_card") or {}).get("headline") or None),' in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
