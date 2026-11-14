"""The NFL game markets are graded on the ratings the build ships.

Ethan, 2026-09-07: "Can we Create arithmetic equations to figure out the
outcome nfl moneylines. We can use math for anything and this is one of
them I feel like."

The equations already existed. Measuring what they were worth against
the close found that the figure on the board described the wrong one:
`gamerank.measure_moneylines` walks a rating that accumulates every
team's games forever, while `nfl_build` prices from
`teamrates.ratings_for_season` — this season alone once it can stand,
pooled with last season until then. College had already been given a
walk over its production ratings (`measure_cfb`); `measure_nfl` is the
same thing for the NFL, and this file is the test college never got.

Run directly: `python3 tests/test_gamerank_nfl.py`
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db                                        # noqa: E402
from engine import gamerank as R                             # noqa: E402


def _row(season, week, home, away, hs, as_, ml=None):
    extra = {"spread_odds": [-110, -110], "total_odds": [-110, -110]}
    if ml:
        extra["ml"] = list(ml)
    return {"sport": "nfl", "season": season, "period": f"{week:03d}",
            "game_id": f"{season}-{week}-{away}@{home}", "home": home, "away": away,
            "home_score": hs, "away_score": as_, "spread": -3.0, "total": 44.0,
            "roof": "outdoors", "surface": "grass", "temp": None, "wind": None,
            "extra": json.dumps(extra)}


def _turnaround():
    """A was a forty-point team all of 2024. In 2025 B is, every week.

    Week seven of 2025 is the game under measurement, B at home, with
    a pick'em close. A rating that remembers 2024 makes A the favourite
    — eight blowouts against six. The rating the build ships forgets
    2024 the moment 2025 averages four games a team, and makes B one.
    """
    rows = []
    for wk in range(1, 9):
        rows.append(_row(2024, wk, "A", "B", 40, 0))
    for wk in range(1, 7):
        rows.append(_row(2025, wk, "B", "A", 40, 0))
    rows.append(_row(2025, 7, "B", "A", 24, 21, ml=(-110, -110)))
    conn = db.connect(":memory:")
    db.upsert_games(conn, rows)
    return conn


def test_the_nfl_is_graded_on_the_ratings_the_build_ships():
    conn = _turnaround()
    shipped = {r.market: r for r in R.measure_nfl(conn)}
    ml = shipped["moneyline"]
    assert len(ml.pairs) == 1, ml.pairs
    wp_home, won = ml.pairs[0]
    assert won is True
    # Six 40-0 wins this season and nothing else counted: B is a heavy
    # favourite. (Shrunk 6/(6+6), through the 13.5-point curve.)
    assert wp_home > 0.8, wp_home
    # The cumulative walk on the same game remembers 2024 and leans the
    # other way — which is the figure the board used to carry.
    plain = R.measure_moneylines(conn, "nfl", min_team_games=1)
    assert len(plain.pairs) == 1, plain.pairs
    assert plain.pairs[0][0] < 0.5, plain.pairs


def test_measure_routes_the_nfl_through_the_shipped_walk():
    """`python3 -m engine.gamerank --sport nfl --save` is what writes the
    droplet's rank store; it has to reach this walk, not the plain one."""
    conn = _turnaround()
    got = {r.market: r for r in R.measure(conn, "nfl")}
    assert set(got) == {"total", "spread", "team_total", "moneyline"}
    assert got["moneyline"].pairs and got["moneyline"].pairs[0][0] > 0.8


def test_the_prior_table_holds_only_the_past_by_season_then_week():
    """The in-memory table the production ratings read must not contain
    the week being priced, nor a later season's earlier week — the exact
    leak the plain walk had when it sorted on the week label alone."""
    import sqlite3
    conn = _turnaround()
    cols = "sport, season, period, home, away, home_score, away_score, extra"
    rows = conn.execute(f"SELECT {cols} FROM games ORDER BY season, period").fetchall()
    mem = sqlite3.connect(":memory:")
    mem.row_factory = sqlite3.Row
    mem.execute(f"CREATE TABLE games ({cols})")
    R._prior_table(mem, rows, (2025, "002"), (2024, 2025))
    got = mem.execute("SELECT season, period FROM games ORDER BY season, period").fetchall()
    assert [(r[0], r[1]) for r in got] == [(2024, f"{w:03d}") for w in range(1, 9)] + [(2025, "001")]
    # And "before 2024 week two" is 2024 week one alone — not 2025's.
    R._prior_table(mem, rows, (2024, "002"), (2023, 2024))
    got = mem.execute("SELECT season, period FROM games").fetchall()
    assert [(r[0], r[1]) for r in got] == [(2024, "001")]


def test_the_adjusted_form_is_re_measurable_and_not_shipped():
    """The docstring records that opponent adjustment moved the NFL by two
    thousandths. Anyone doubting it can re-run it; nobody can ship it by
    accident, because the build does not call it."""
    conn = _turnaround()
    got = {r.market: r for r in R.measure_nfl(conn, adjusted=True)}
    assert got["moneyline"].pairs and got["moneyline"].pairs[0][0] > 0.8
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "nfl_build.py")).read()
    assert "adjusted_ratings_for_season" not in src
    assert "ratings_for_season(conn, \"nfl\"" in src


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
