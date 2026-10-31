"""College's usage bridge is measured before it moves a number.

Ethan, 2026-10-14: "do all of the ideas", the first a usage step for
college — the NFL's blend of a thin outcome log with the measured role
(last four games' opportunities × this season's efficiency). It was
measured first on the cached college play files (`cfbbridgefit.py`) and
failed the bar set before the run in every market, so the board reads no
role. Pinned here: the role is the NFL's rule on college's columns
(catches, never targets), the bar takes every season, and the replay
blends exactly what the board would.

Fixture games in memory, never the cache.

Run directly: `python3 tests/test_the_college_usage_bridge_is_measured_first.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cfbbridgefit as F                                           # noqa: E402


def test_the_role_is_the_nfls_rule_on_colleges_columns():
    games = [{"carries": 5, "rush_yds": 20}, {"carries": 10, "rush_yds": 50},
             {"carries": 12, "rush_yds": 60}, {"carries": 15, "rush_yds": 75},
             {"carries": 18, "rush_yds": 95}]
    got = F.role(games, "rush_yds")
    assert got["opp_per_game"] == (10 + 12 + 15 + 18) / 4, "the last four games' carries"
    assert abs(got["eff"] - 300 / 60) < 1e-9, "yards a carry over the whole season"
    assert F.role(games[:1], "rush_yds") is None, "one game is no role"
    assert F.role([{"carries": 4, "rush_yds": 9}] * 3, "rush_yds") is None, "under twenty carries"
    assert F.OPP_BY_MARKET["rec_yds"] == "receptions", "college's receiving volume is catches"
    assert "receptions" not in F.OPP_BY_MARKET, "no opportunity under catches themselves"


def test_the_bar_needs_every_season():
    assert F.ships([(2022, 10, 0.5), (2023, 10, 0.1), ("all", 20, 0.3)])
    assert not F.ships([(2022, 10, 0.5), (2023, 10, -0.1), ("all", 20, 0.3)]), "one season worse fails"
    assert not F.ships([(2022, 0, 0.0), ("all", 0, 0.0)]), "nothing measured fails"


def test_the_replay_blends_what_the_board_would():
    day = lambda d, c, y: (f"2025-09-{d:02d}", {"carries": c, "rush_yds": y})      # noqa: E731
    now = {("a back", "TEAM"): dict([day(1, 10, 40), day(8, 12, 50), day(15, 20, 110), day(22, 22, 120)])}
    before = {("a back", "TEAM"): dict([day(1, 3, 10), day(8, 4, 15)])}
    pts = F.points(now, before, 2025)
    assert [p["n"] for p in pts] == [4, 5], "this season's games, then last season's, under the floor of four"
    last = pts[-1]
    w = 5 / (5 + 4)
    est = (12 + 20 + 10) / 3 * (200 / 42)
    assert abs(last["cand"] - (w * last["cur"] + (1 - w) * est)) < 1e-9
    assert last["y"] == 120


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
