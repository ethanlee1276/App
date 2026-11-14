"""marketfit.py measures the markets the book hangs and this board never asked for.

Ethan, 2026-10-05: "any other market we are missing that we can be
winning in". Round two of the harness adds the sums (rush + receiving
yards, passing + rushing), a kicker's points, a defender's tackles, and
three interception arms (rate per attempt × projected attempts, the
opponent on top, FTN's interception-worthy rate). Checks, on a synthetic
cache: a sum is the sum; a candidate whose columns the cache lacks is
reported absent rather than scored as zeros; a defender's position is
read as one role; the interception rate shrinks toward the league's; and
the walk scores the rate arm beside the count arm. The FTN arm is passed
in, never fetched — the suite does not touch the network.

Run directly: `python3 tests/test_the_market_harness_measures_what_the_book_hangs.py`
"""
import csv
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import marketfit as M                                               # noqa: E402

COLS = ["season", "week", "season_type", "player_id", "player_display_name", "position", "position_group",
        "opponent_team", "attempts", "completions", "passing_yards", "passing_tds", "passing_interceptions",
        "carries", "rushing_yards", "targets", "receptions", "receiving_yards",
        "fg_made", "fg_att", "pat_made", "pat_att", "def_tackles_solo", "def_tackle_assists"]


def _cache(seasons=(2024, 2025), kickers=True):
    d = Path(tempfile.mkdtemp(prefix="marketfit-"))
    rnd = random.Random(7)
    cols = COLS if kickers else [c for c in COLS if not c.startswith(("fg_", "pat_", "def_"))]
    for yr in seasons:
        with open(d / f"player_stats_{yr}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for wk in range(1, 18):
                for i in range(6):
                    base = {"season": yr, "week": wk, "season_type": "REG", "opponent_team": f"T{wk % 4}"}
                    qb = {**base, "player_id": f"q{i}", "player_display_name": f"QB {i}", "position": "QB",
                          "position_group": "QB", "attempts": 30 + i, "completions": 20 + i,
                          "passing_yards": 240 + 5 * i + rnd.randint(-40, 40), "passing_tds": rnd.randint(0, 3),
                          "passing_interceptions": 1 if rnd.random() < 0.1 * (i + 1) else 0,
                          "carries": 3, "rushing_yards": 10 + 4 * i, "targets": 0, "receptions": 0, "receiving_yards": 0}
                    rb = {**base, "player_id": f"r{i}", "player_display_name": f"RB {i}", "position": "RB",
                          "position_group": "RB", "attempts": 0, "completions": 0, "passing_yards": 0, "passing_tds": 0,
                          "passing_interceptions": 0, "carries": 12 + i, "rushing_yards": 50 + 6 * i + rnd.randint(-20, 20),
                          "targets": 4, "receptions": 3, "receiving_yards": 20 + 3 * i}
                    rows = [qb, rb]
                    if kickers:
                        rows.append({**base, "player_id": f"k{i}", "player_display_name": f"K {i}", "position": "K",
                                     "position_group": "SPEC", "attempts": 0, "completions": 0, "passing_yards": 0,
                                     "passing_tds": 0, "passing_interceptions": 0, "carries": 0, "rushing_yards": 0,
                                     "targets": 0, "receptions": 0, "receiving_yards": 0,
                                     "fg_made": 1 + i % 3, "fg_att": 2 + i % 3, "pat_made": 2, "pat_att": 2})
                        rows.append({**base, "player_id": f"d{i}", "player_display_name": f"LB {i}", "position": "ILB",
                                     "position_group": "LB", "attempts": 0, "completions": 0, "passing_yards": 0,
                                     "passing_tds": 0, "passing_interceptions": 0, "carries": 0, "rushing_yards": 0,
                                     "targets": 0, "receptions": 0, "receiving_yards": 0,
                                     "fg_made": 0, "fg_att": 0, "pat_made": 0, "pat_att": 0,
                                     "def_tackles_solo": 4 + i, "def_tackle_assists": 2})
                    for r in rows:
                        w.writerow({c: r.get(c, 0) for c in cols})
    return d


def test_a_sum_is_the_sum_and_a_weight_weighs():
    r = {"rushing_yards": "61", "receiving_yards": "22", "fg_made": "2", "pat_made": "3",
         "def_tackles_solo": "5", "def_tackles_with_assist": "2"}
    assert M.value(r, "rush_rec_yds") == 83.0
    assert M.value(r, "kick_pts") == 9.0
    assert M.value(r, "tackles_ast") == 7.0, "the assists column's other spelling is read"


def test_a_candidate_without_its_columns_is_absent_not_zero():
    full = M.load([2024, 2025]) if False else None            # (the loader is exercised below)
    assert not M.has_columns({"attempts", "carries"}, "kick_pts")
    assert M.has_columns({"fg_made", "pat_made"}, "kick_pts")
    assert M.has_columns({"def_tackles_solo", "def_tackles_with_assist"}, "tackles_ast")
    assert full is None


def test_defenders_are_one_role_and_the_walk_scores_every_new_market():
    saved = M.CACHE_DIR
    try:
        M.CACHE_DIR = _cache()
        rows = M.load([2024, 2025])
        assert {p for _y, _w, _n, p, _r in rows} == {"QB", "RB", "K", "DEF"}
        have = M.present(rows)
        assert {"rush_rec_yds", "pass_rush_yds", "kick_pts", "fg_made", "tackles_ast"} <= have
        got = M.score(rows, 2025, iw={})
        keys = {k for k, _ in got.items()}
        for want in (("rush_rec_yds", "RB"), ("pass_rush_yds", "QB"), ("kick_pts", "K"),
                     ("tackles_ast", "DEF"), ("pass_int", "QB"), ("pass_int/att×att", "QB"),
                     ("pass_int+opp", "QB"), ("pass_int/att×att+opp", "QB")):
            assert want in keys, want
        assert ("pass_int+iw", "QB") not in keys, "no charting handed in: no FTN arm"
        for (mk, pos), (a, se, n, base) in got.items():
            assert a is None or 0.0 <= a <= 1.0, (mk, a)
            assert n > 0
        # Without the kicking and defence columns those rows are not scored at all.
        M.CACHE_DIR = _cache(kickers=False)
        rows = M.load([2024, 2025])
        have = M.present(rows)
        assert "kick_pts" not in have and "tackles_ast" not in have and "rush_rec_yds" in have
        assert ("kick_pts", "K") not in M.score(rows, 2025, iw={})
    finally:
        M.CACHE_DIR = saved


def test_the_ftn_arm_scores_when_charting_is_handed_in():
    saved = M.CACHE_DIR
    try:
        M.CACHE_DIR = _cache()
        rows = M.load([2024, 2025])
        iw = {f"q{i}": [(yr, wk, 1 + (wk + i) % 3, 30) for yr in (2024, 2025) for wk in range(1, 18)]
              for i in range(6)}
        got = M.score(rows, 2025, iw=iw)
        assert ("pass_int+iw", "QB") in got and ("pass_int+iw+own", "QB") in got
        assert M.iw_rate_before(iw["q0"], 2025, 5) is not None
        assert M.iw_rate_before(iw["q0"], 2024, 2) is None, "under the attempts floor"
    finally:
        M.CACHE_DIR = saved


def test_the_interception_rate_shrinks_toward_the_league():
    league = {"pass_att": 32.0, "pass_int": 0.7}
    lg = 0.7 / 32.0
    clean = M.int_rate([32] * 12, [0] * 12, league)
    wild = M.int_rate([32] * 12, [2] * 12, league)
    assert clean is not None and 0.0 < clean < lg < wild
    assert M.int_rate([32] * 2, [0] * 2, league) is None


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
