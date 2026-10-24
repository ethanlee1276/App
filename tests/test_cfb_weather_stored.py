"""The college kickoff forecast is written down, not only drawn.

Ethan, 2026-09-07, on the data a winning model needs: "Weather for
totals. College totals were the only game line with a positive slope,
and it was not significant. A stadium weather feed is cheap."

The feed is not merely cheap, it has been running since 2026-08-24:
`engine.cfb.wx` joins ESPN's venue, CollegeFootballData's coordinates
and Open-Meteo's hourly board to stamp a forecast at the kickoff hour on
every college game. All of it was drawn on a card and thrown away.
`cfbfastr.parse_schedule` writes ``"temp": None, "wind": None``, and
measured on this box on 2026-09-07 the games table held 3,133 college
games with not one temperature and not one wind — so the question the
slope belongs to could not be asked, because the column it reads was
empty by construction.

Run directly: `python3 tests/test_cfb_weather_stored.py`
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db                                        # noqa: E402
from engine.sources import cfbdata, cfbfastr                 # noqa: E402


def _game(**kw):
    g = {"game_id": "401", "season": 2026, "date": "2026-09-12",
         "home": "TOL", "away": "BGSU", "weather_checked": True,
         "weather": {"temp_f": 54, "wind_mph": 17, "wind_dir": "NW",
                     "precip_chance": 0.1, "dome": False}}
    g.update(kw)
    return g


def test_the_column_this_fills_had_no_other_source():
    """`cfbfastr` writes both as None on every historical row, so for
    college these columns can only ever be the forecast — which is why
    they mean something different from the NFL's."""
    src = inspect.getsource(cfbfastr.parse_schedule)
    assert '"temp": None' in src and '"wind": None' in src


def test_a_forecast_becomes_a_game_row():
    rows = cfbdata.weather_rows([_game()])
    assert rows == [{"sport": "cfb", "season": 2026, "period": "2026-09-12",
                     "game_id": "401", "home": "TOL", "away": "BGSU",
                     "roof": "outdoor", "temp": 54.0, "wind": 17.0}]


def test_a_dome_is_answered_without_asking_anybody():
    rows = cfbdata.weather_rows([_game(weather={"dome": True})])
    assert rows[0]["roof"] == "dome"
    assert (rows[0]["temp"], rows[0]["wind"]) == (70.0, 0.0)


def test_a_miss_is_a_miss():
    """Unchecked, unanswerable, or unidentifiable — nothing invented."""
    assert cfbdata.weather_rows([_game(weather_checked=False)]) == []
    assert cfbdata.weather_rows([_game(weather={"dome": False})]) == []
    assert cfbdata.weather_rows([_game(weather={"temp_f": 54, "dome": False})]) == []
    assert cfbdata.weather_rows([_game(game_id="")]) == []
    assert cfbdata.weather_rows([_game(date="")]) == []
    assert cfbdata.weather_rows([]) == [] and cfbdata.weather_rows(None) == []


def test_the_write_never_erases_what_the_results_writer_stored():
    """`upsert_games` merges, and the two writers touch different
    columns on purpose: results carry scores and the week/neutral flags,
    the slate carries weather. `engine.cfbinfo` reads the neutral flag
    off `extra` on every game, so blanking it would silently remove a
    feature from the college information test."""
    assert "extra" not in cfbdata.weather_rows([_game()])[0]
    conn = db.connect(":memory:")
    from engine.db import upsert_games
    upsert_games(conn, cfbdata.game_rows([{
        "completed": True, "game_id": "401", "season": 2026,
        "date": "2026-09-12", "home": "TOL", "away": "BGSU",
        "home_score": 31, "away_score": 17, "week": 3,
        "neutral_site": True, "conference_game": False}]))
    upsert_games(conn, cfbdata.weather_rows([_game()]))
    row = dict(conn.execute(
        "SELECT home_score, away_score, temp, wind, roof, extra FROM games "
        "WHERE sport='cfb' AND game_id='401'").fetchone())
    assert (row["home_score"], row["away_score"]) == (31.0, 17.0)
    assert (row["temp"], row["wind"], row["roof"]) == (54.0, 17.0, "outdoor")
    import json
    assert json.loads(row["extra"])["neutral"] is True, row["extra"]


def test_the_build_stores_what_the_attach_stamped():
    import cfb_build
    src = inspect.getsource(cfb_build.main)
    i = src.index("n_wx = _wx.attach(")
    block = src[i:i + 900]
    assert "upsert_games(conn, cfbdata.weather_rows(games))" in block, block[:500]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
