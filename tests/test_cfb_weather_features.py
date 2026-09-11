"""The college information test can ask whether weather moves the total.

Ethan, 2026-09-07: "Weather for totals. College totals were the only
game line with a positive slope, and it was not significant. A stadium
weather feed is cheap."

The feed was stored on 2026-09-07 (`cfbdata.weather_rows`). This is the
reader: the same three inputs the NFL test has always carried — wind,
cold, indoors — read off the same columns, on the total only, and
printed with their sample sizes so an empty column reads as n 0/0 rather
than as a finding.

Run directly: `python3 tests/test_cfb_weather_features.py`
"""

import datetime
import inspect
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import cfbinfo as C, db, nflinfo as N            # noqa: E402


def test_indoors_answers_without_a_forecast_and_outdoors_needs_one():
    assert C.weather_features("dome", None, None) == {"indoor": 1.0, "wind": 0.0, "cold": 0.0}
    assert C.weather_features("closed", 80, 20) == {"indoor": 1.0, "wind": 0.0, "cold": 0.0}
    # A missing forecast is not calm weather.
    assert C.weather_features("outdoor", None, None) == {"indoor": 0.0}
    assert C.weather_features(None, 54, None) == {"indoor": 0.0}
    assert C.weather_features("outdoor", 54, 17) == {"indoor": 0.0, "wind": 17.0, "cold": 0.0}
    assert C.weather_features("outdoor", 28, 9) == {"indoor": 0.0, "wind": 9.0, "cold": 1.0}
    assert C.weather_features("outdoor", None, 9) == {"indoor": 0.0, "wind": 9.0, "cold": 0.0}
    assert C.FREEZING_F == 32.0, "the NFL test's line"


def test_the_total_gets_the_nfl_tests_three_inputs_and_nothing_else_does():
    for name in ("wind", "cold", "indoor"):
        assert name in C.TOTAL_FEATURES and name in N.TOTAL_FEATURES
        assert name not in C.ML_FEATURES and name not in C.SPREAD_FEATURES
    # And the shared column list is untouched: it also shapes the prior
    # table, which is filled with exactly eight values per row.
    assert C.COLS.count(",") == 7 and "wind" not in C.COLS
    assert "_weather_map(conn)" in inspect.getsource(C.build_rows)


def _game(season, wk, home, away, hs, as_, **wx):
    date = str(datetime.date(season, 9, 5) + datetime.timedelta(days=7 * (wk - 1)))
    row = {"sport": "cfb", "season": season, "period": date,
           "game_id": f"{season}-{date}-{away}@{home}", "home": home, "away": away,
           "home_score": hs, "away_score": as_, "spread": -3.0, "total": 52.0,
           "roof": None, "surface": None, "temp": None, "wind": None,
           "extra": json.dumps({"ml": [-110, -110], "neutral": False})}
    row.update(wx)
    return row


def test_the_rows_carry_the_forecast_that_was_on_the_game():
    games = []
    for season in (2022, 2023):
        for wk in range(1, 9):
            games += [_game(season, wk, "A", "B", 30, 20, roof="outdoor", temp=54, wind=17),
                      _game(season, wk, "C", "D", 24, 21, roof="dome"),
                      _game(season, wk, "E", "F", 17, 14)]          # no forecast
    conn = db.connect(":memory:")
    db.upsert_games(conn, games)
    conn.row_factory = sqlite3.Row
    rows = C.build_rows(conn)
    by = {(r.season, r.home): r.f for r in rows}
    assert by[(2023, "A")]["wind"] == 17.0 and by[(2023, "A")]["cold"] == 0.0
    assert by[(2023, "A")]["indoor"] == 0.0
    assert by[(2023, "C")] == {**by[(2023, "C")], "indoor": 1.0, "wind": 0.0, "cold": 0.0}
    assert "wind" not in by[(2023, "E")] and by[(2023, "E")]["indoor"] == 0.0
    # The report prints the three under TOTAL with their sample sizes.
    text = "\n".join(C.report(rows, train=(2022,), test=(2023,)))
    total = text[text.index("TOTAL — each feature alone"):]
    for name in ("wind", "cold", "indoor"):
        assert name in total, name


def test_an_empty_column_reads_as_no_sample_not_as_a_finding():
    games = [_game(s, wk, h, a, 27, 20) for s in (2022, 2023) for wk in range(1, 9)
             for h, a in (("A", "B"), ("C", "D"))]
    conn = db.connect(":memory:")
    db.upsert_games(conn, games)
    conn.row_factory = sqlite3.Row
    rows = C.build_rows(conn)
    assert all("wind" not in r.f for r in rows)
    text = "\n".join(C.report(rows, train=(2022,), test=(2023,)))
    line = next(l for l in text.splitlines() if l.strip().startswith("wind"))
    assert line.rstrip().endswith("n 0/0"), line


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
