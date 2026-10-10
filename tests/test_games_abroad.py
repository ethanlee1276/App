"""NFL games played abroad: the real venue, no home field, and a measured caution.

Ethan, 2026-10-10: "we need to be making sure that we're pulling weather
for whatever location they're playing is that is out of the country ...
and we also need to make sure that our models and our bets and all that
shit is being adjusted for them being played out of the country."

These check, one rule each: every 2026 international venue the schedule
names has its own forecast location; a neutral site carries no home field
in the game model (moneyline and spread), and a home game still does; the
game record names the real venue (with Mexico City's altitude) instead of
the home team's building; the scout raises "abroad" on overs, never on
unders, and the history replay knows which stored games were abroad from
the cached schedule — regular-season neutral sites only, never a Super
Bowl.

Run directly: `python3 tests/test_games_abroad.py`
"""
import os
import sqlite3
import sys
import tempfile
from types import SimpleNamespace as NS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likelyctx as C                                  # noqa: E402
from engine import scout as SC                                     # noqa: E402

#: The 2026 international venues as nflverse's schedule spells them.
VENUES_2026 = ("Melbourne Cricket Ground", "Maracana Stadium", "Tottenham Hotspur Stadium", "Wembley Stadium",
               "Stade de France", "Bernabeu", "FC Bayern Munich Stadium", "Estadio Banorte")


def test_every_2026_venue_abroad_has_its_own_forecast_location():
    from engine.nflwx import venue_coords
    for v in VENUES_2026:
        assert venue_coords(v), f"{v}: a game there would get no forecast"
    assert venue_coords("Lambeau Field") is None, "a US stadium is never mistaken for one abroad"


def test_a_neutral_site_carries_no_home_field():
    from engine.gamebets import NFL_HOME_FIELD, game_margin, nfl_win_prob
    assert nfl_win_prob(0.0, 0.0) > 0.5, "a home game keeps its home field"
    assert abs(nfl_win_prob(0.0, 0.0, neutral=True) - 0.5) < 1e-9, "level teams abroad are a coin flip"
    assert game_margin("nfl", 3.0, 1.0) == 2.0 + NFL_HOME_FIELD
    assert game_margin("nfl", 3.0, 1.0, neutral=True) == 2.0
    src = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    assert 'nfl_win_prob(g.home_rating, g.away_rating, neutral=_neutral)' in src
    assert 'neutral=bool(getattr(g, "neutral_site", False)))' in src, "the spread reads it too"


def test_the_game_record_names_the_real_venue():
    from engine.pipeline import venue_to_dict
    abroad = NS(home="JAX", venue="Wembley Stadium", neutral_site=True, roof="outdoors", surface="grass")
    s = venue_to_dict(abroad)
    assert s["name"] == "Wembley Stadium" and s["abroad"] and "abroad" in s["plays"]
    mexico = venue_to_dict(NS(home="SF", venue="Estadio Banorte", neutral_site=True, roof="outdoors",
                              surface="grass"))
    assert mexico["altitude_ft"] > 7000, "Mexico City's thin air is a fact about the ball"
    home = venue_to_dict(NS(home="GB", venue="Lambeau Field", neutral_site=False, roof="outdoors", surface="grass"))
    assert home.get("team") == "GB" and not home.get("abroad")


def test_the_scout_flags_overs_abroad_and_never_unders():
    over = SC.flags(SC.situation("rec_yds", "OVER", line=60.5, values=[60] * 6, abroad=True))
    under = SC.flags(SC.situation("rec_yds", "UNDER", line=60.5, values=[60] * 6, abroad=True))
    home = SC.flags(SC.situation("rec_yds", "OVER", line=60.5, values=[60] * 6, abroad=False))
    assert "abroad_over" in over and "abroad_over" not in under and "abroad_over" not in home
    assert "abroad" in SC.note("abroad_over")
    games = [{"home": "JAX", "away": "HOU", "spread": -2.5, "total": 44.5, "neutral_site": True,
              "venue": "Wembley Stadium", "weather": {}}]
    rows = [{"player": "Wide Out", "team": "HOU", "opponent": "JAX", "market": "receptions", "side": "OVER",
             "line": 5.5, "odds": -120, "model_prob": 0.62, "recent_values": [6, 5, 6, 7, 5]}]
    C.annotate(rows, {"games": games, "recommendations": []})
    assert "abroad_over" in rows[0]["scout_flags"]


def test_the_history_knows_which_stored_games_were_abroad():
    d = tempfile.mkdtemp()
    sched = os.path.join(d, "games.csv")
    with open(sched, "w", encoding="utf-8") as fh:
        fh.write("season,week,home_team,away_team,location,stadium\n"
                 "2024,6,CHI,JAX,Neutral,Tottenham Stadium\n"
                 "2024,7,JAX,NE,Neutral,Wembley Stadium\n"
                 "2024,22,PHI,KC,Neutral,Mercedes-Benz Superdome\n"
                 "2024,6,GB,ARI,Home,Lambeau Field\n")
    keys = C.abroad_keys(sched)
    assert keys == {(2024, 6, "CHI"), (2024, 7, "JAX")}, "regular-season neutral sites only — no Super Bowl"
    from engine import db
    c = db.connect(os.path.join(d, "h.db"))
    c.executemany("INSERT INTO games (sport, season, period, game_id, home, away, spread, total, date) "
                  "VALUES (?,?,?,?,?,?,?,?,?)", [
                      ("nfl", 2024, "006", "JAX@CHI", "CHI", "JAX", -1.5, 44.5, "2024-10-13"),
                      ("nfl", 2024, "006", "ARI@GB", "GB", "ARI", -4.5, 47.5, "2024-10-13")])
    c.commit()
    c.row_factory = sqlite3.Row
    real = C.abroad_keys
    C.abroad_keys = lambda path=None: keys
    try:
        games, _by_team, _logs = C.history_index(c, set(), "nfl")
    finally:
        C.abroad_keys = real
    by = {g["raw_id"]: g["abroad"] for g in games.values()}
    assert by == {"JAX@CHI": True, "ARI@GB": False}
    src = open(os.path.join(ROOT, "engine", "scouthist.py"), encoding="utf-8").read()
    assert 'abroad=g.get("abroad")' in src, "the five-season replay must read it"


def test_a_missing_schedule_file_reads_as_nothing_abroad():
    assert C.abroad_keys(os.path.join(tempfile.mkdtemp(), "none.csv")) == set()


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
