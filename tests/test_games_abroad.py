"""NFL games played abroad: the real venue's weather and stadium, and no home field.

Ethan, 2026-10-10: "we need to be making sure that we're pulling weather
for whatever location they're playing is that is out of the country ...
and we also need to make sure that our models and our bets and all that
shit is being adjusted for them being played out of the country."

These check, one rule each: every 2026 international venue the schedule
names has its own forecast location; a neutral site carries no home field
in the game model (moneyline and spread), and a home game still does; the
game record names the real venue (with Mexico City's altitude) instead of
the home team's building; and the scout raises no "abroad" caution.

THE CAUTION CAME OFF (2026-10-10, Ethan: "yes take it off"). The scout
carried "an over in a game played abroad" for one day. The five-season
replay on the box tested it on every stored international game (2021+,
200-300 player-games a half for catches and touchdowns): catches overs
+1% then -4%, rushing yards -4% then +4%, touchdowns -0.3% then -1.9%.
Nothing held in both halves, so overs abroad do not hit less, and a card
should not warn about something history says does not happen.

Run directly: `python3 tests/test_games_abroad.py`
"""
import os
import sys
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


def test_the_scout_raises_no_abroad_caution():
    assert "abroad_over" not in SC.FLAGS, "history showed overs abroad hit no less"
    s = SC.situation("rec_yds", "OVER", line=60.5, values=[60] * 6)
    assert "abroad" not in s
    games = [{"home": "JAX", "away": "HOU", "spread": -2.5, "total": 44.5, "neutral_site": True,
              "venue": "Wembley Stadium", "weather": {}}]
    rows = [{"player": "Wide Out", "team": "HOU", "opponent": "JAX", "market": "receptions", "side": "OVER",
             "line": 5.5, "odds": -120, "model_prob": 0.62, "recent_values": [6, 5, 6, 7, 5]}]
    C.annotate(rows, {"games": games, "recommendations": []})
    assert not any("abroad" in f for f in rows[0]["scout_flags"])
    assert not hasattr(C, "abroad_keys"), "the history no longer marks games abroad"


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
