"""A retractable roof the schedule has not called yet is read as closed, not as
open air (engine/nflwx.retractable_unset, attach; engine/weather
RETRACTABLE_REASON; engine/models.Weather.retractable; the page's label).

Found 12 November 2026, checking Ethan's "I feel like we are not putting
weather as a factor for the picks" against the board: Sunday's 49ers at the
Cowboys took a 15 mph wind and a 56% chance of rain on its passing and
receiving props (−12% passing yards). nflverse writes a game's roof only once
it is played, so every coming game at the five retractable roofs (Arizona,
Atlanta, Dallas, Houston, Indianapolis) arrived blank and the board pulled a
forecast as if it were open air. The played games: 2016-2025, 362 of those
clubs' 412 home games were played closed, and the 48 played open were fair
days (wind 5 mph on average, none in rain). What these hold:

  * a blank roof at a retractable stadium is read as closed, with no
    forecast fetched, and the card says why rather than calling it a dome;
  * a roof the schedule calls is taken as written ("open" is open air);
  * an open-air stadium, a fixed dome and a neutral site are unchanged;
  * the board's game carries the flag and the page labels it.

Run directly: `python3 tests/test_a_retractable_roof_is_read_closed.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import nflwx                                           # noqa: E402
from engine import weather as W                                    # noqa: E402
from engine.models import Game, Weather                            # noqa: E402

STORM = {"temp_f": 54.0, "wind_mph": 15.0, "precip_chance": 0.56, "wind_dir": "S"}


def _attach(**game):
    asked = []

    def fc(lat, lon, day, when):
        asked.append((lat, lon))
        return dict(STORM)
    g = Game(home=game.pop("home"), away=game.pop("away", "SF"), weather=Weather(), date="2026-11-15",
             kickoff="16:25", **game)
    nflwx.attach([g], forecast=fc)
    return g, asked


def test_the_cowboys_roof_unset_reads_closed():
    g, asked = _attach(home="DAL", roof="")
    assert asked == [], "no forecast pulled for a roof that will be shut"
    assert g.weather.dome is True and g.weather.retractable is True and g.weather.measured is True
    eff = W.evaluate_weather(g.weather, "QB")
    assert all(v == 1.0 for v in eff.multipliers.values())
    assert eff.reasons == [W.RETRACTABLE_REASON]
    assert W.td_multiplier(g.weather, "WR") == (1.0, ["Retractable roof, read as closed — weather is "
                                                       "not a factor"])
    for team in ("ARI", "ATL", "HOU", "IND"):
        assert _attach(home=team, roof="")[0].weather.retractable is True, team


def test_a_roof_the_schedule_calls_is_taken_as_written():
    g, asked = _attach(home="DAL", roof="open")
    assert len(asked) == 1 and g.weather.dome is False and g.weather.wind_mph == 15.0
    assert g.weather.retractable is False
    g, asked = _attach(home="DAL", roof="closed")
    assert asked == [] and g.weather.dome is True and g.weather.retractable is False


def test_open_air_domes_and_neutral_sites_are_unchanged():
    g, asked = _attach(home="NYG", roof="outdoors")
    assert len(asked) == 1 and g.weather.dome is False and g.weather.precip_chance == 0.56
    g, asked = _attach(home="NYG", roof="")
    assert len(asked) == 1 and g.weather.dome is False, "a blank roof at an open-air stadium is open air"
    g, asked = _attach(home="NO", roof="dome")
    assert asked == [] and g.weather.dome is True and g.weather.retractable is False
    assert W.evaluate_weather(g.weather).reasons == ["Dome game — no weather impact on the passing game"]
    # Abroad the venue decides (a Munich game listed under a retractable home team is still open air).
    g, asked = _attach(home="DAL", roof="outdoors", neutral_site=True, venue="FC Bayern Munich Stadium")
    assert len(asked) == 1 and not g.weather.dome
    assert nflwx.retractable_unset(Game(home="DAL", away="SF", weather=Weather(), roof="",
                                        neutral_site=True)) is False


def test_the_measured_basis_is_written_down():
    m = nflwx.RETRACTABLE_CLOSED
    assert (m["games"], m["closed"], m["open"]) == (412, 362, 48)
    assert m["closed"] / m["games"] > 0.85


def test_the_board_carries_the_flag_and_the_page_says_it():
    from engine.pipeline import _game_to_dict
    g, _ = _attach(home="DAL", roof="")
    d = _game_to_dict(g)
    assert d["weather"]["dome"] is True and d["weather"]["retractable"] is True
    assert d["conditions"]["why"] == [W.RETRACTABLE_REASON]
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    det = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    label = 'w.dome ? (w.retractable ? "Retractable roof · expected closed" : "Indoor")'
    assert label in app and label in det


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
