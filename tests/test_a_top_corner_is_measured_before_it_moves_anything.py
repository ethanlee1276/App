"""A bettor's corner rules are measured on history before they move anything.

Ethan, 2026-10-04: "yeah lets do those" — test the breakdowns' two rules
(a WR1 against a shutdown corner keeps catches better than yards; his WR2
catches more) before either reaches a card. Checks, one rule each: the
top corner is the defence's most-targeted defender BEFORE the week; an
effect planted in both halves of the seasons is found and proven; the same
data with no effect is not; an effect in one half only is not.

Run directly: `python3 tests/test_a_top_corner_is_measured_before_it_moves_anything.py`
"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import cbfit as C                                        # noqa: E402


def test_the_top_corner_is_read_from_earlier_weeks_only():
    rows = [{"team": "JAX", "week": 1, "pfr_player_name": "T.Hunter", "def_targets": 12,
             "def_completions_allowed": 5, "def_yards_allowed": 50, "def_receiving_td_allowed": 0, "def_ints": 1},
            {"team": "JAX", "week": 2, "pfr_player_name": "T.Hunter", "def_targets": 10,
             "def_completions_allowed": 4, "def_yards_allowed": 40, "def_receiving_td_allowed": 0, "def_ints": 0},
            {"team": "JAX", "week": 2, "pfr_player_name": "M.Brown", "def_targets": 30,
             "def_completions_allowed": 25, "def_yards_allowed": 300, "def_receiving_td_allowed": 3, "def_ints": 0}]
    tc = C.top_corners(rows)
    assert tc[("JAX", 2)]["name"] == "T.Hunter", "week 2's own game is not yet known in week 2"
    assert tc[("JAX", 3)]["name"] == "M.Brown" and tc[("JAX", 3)]["targets"] == 30


def _rows(effect_h1, effect_h2, seasons=(2021, 2022, 2023, 2024), n=400, seed=7):
    rnd = random.Random(seed)
    out = []
    for season in seasons:
        e1 = effect_h1(season)
        e2 = effect_h2(season)
        for _ in range(n):
            elite = rnd.random() < 0.3
            base = rnd.gauss(1.0, 0.3)
            out.append({"season": season, "rank": 1, "elite": elite,
                        "rec": base + (e1 / 2 if elite else 0), "yds": base - (e1 / 2 if elite else 0)})
            out.append({"season": season, "rank": 2, "elite": elite,
                        "rec": rnd.gauss(1.0, 0.3) + (e2 if elite else 0), "yds": rnd.gauss(1.0, 0.3)})
    return out


def test_an_effect_in_both_halves_is_proven_and_noise_is_not():
    got = C.effects(_rows(lambda s: 0.12, lambda s: 0.10))
    assert got["h1"]["proven"] and got["h2"]["proven"], got
    flat = C.effects(_rows(lambda s: 0.0, lambda s: 0.0))
    assert not flat["h1"]["proven"] and not flat["h2"]["proven"], flat


def test_an_effect_in_one_half_only_is_not_proven():
    got = C.effects(_rows(lambda s: 0.15 if s < 2023 else 0.0, lambda s: 0.0))
    assert not got["h1"]["proven"], got["h1"]


def test_the_whole_measurement_runs_on_a_history_database():
    from engine import db
    conn = db.connect(":memory:")
    rows = []
    for wk in range(1, 10):
        for player, tg, rec, yds in (("Ja'Marr Chase", 9, 6, 80), ("Tee Higgins", 7, 5, 70), ("Andrei Iosivas", 3, 2, 20)):
            for mk, v in (("targets", tg), ("receptions", rec), ("rec_yds", yds)):
                rows.append({"sport": "nfl", "season": 2025, "period": f"{wk:03d}", "game_id": f"CIN-{wk:03d}",
                             "player": player, "team": "CIN", "opponent": "JAX", "position": "WR", "home": 1,
                             "market": mk, "value": v})
    db.upsert_player_logs(conn, rows)
    defs = [{"team": "JAX", "week": wk, "pfr_player_name": "T.Hunter", "def_targets": 6,
             "def_completions_allowed": 2, "def_yards_allowed": 20, "def_receiving_td_allowed": 0, "def_ints": 0}
            for wk in range(1, 10)]
    res = C.measure(conn, seasons=(2025,), load_def=lambda yr: defs)
    assert res["rows"] > 0 and set(res["effects"]) == {"h1", "h2"}, res


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
