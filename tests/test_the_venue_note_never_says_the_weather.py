"""A venue's note is about the building; tonight's weather is the model's.

Ethan, 2026-09-24, beside Falcons at Packers — 69°F, 6 mph — under a
Lambeau note reading "Late-season cold here is severe enough to affect
ball handling and kicking": "we are giving misleading info here so we
need to fix that and make sure weather is linked correctly".

Two faults. The note is printed at every game at the venue, so anything
seasonal in it is wrong half the year; and the cold claim was one this
repo measured and did not find (engine/weather: "cold on its own
measured nothing clear once wind, rain and snow were separated"). The
link itself was right — the forecast is the home stadium's, at the
kickoff hour (engine/nflwx), and the board's `conditions.why` is the
same engine/weather read the props were priced with — it was just never
shown. Now it is, under its own heading, and Ask is handed it too.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import askbot as A                                     # noqa: E402
from engine.models import Weather                                  # noqa: E402
from engine.stadiums import STADIUMS                               # noqa: E402
from engine.weather import evaluate_weather                        # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")

SEASONAL = re.compile(r"\b(cold|winter|december|january|november|late[- ]season|late in the|"
                      r"early[- ]season|heat|humid\w*|snow|freez\w*|thunderstorm\w*|climate)\b", re.I)


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_no_venue_note_says_what_the_weather_will_be():
    bad = {k: s.plays for k, s in STADIUMS.items()
           if s.roof == "outdoors" and SEASONAL.search(s.plays)}
    assert not bad, bad
    assert STADIUMS["GB"].plays == "Open air in Green Bay."


def test_the_page_prints_the_models_read_under_its_own_heading():
    panel = _fn("stadiumPanel")
    assert "${stadiumTonightHTML(g)}" in panel
    assert "The live weather above is the number that moves a total" not in panel
    tonight = _fn("stadiumTonightHTML")
    assert "(g.conditions || {}).why" in tonight, "the same read the props were priced with"
    assert "Tonight’s weather, as the model used it" in tonight
    assert "temperature is not adjusted for" in tonight


def test_the_read_for_a_mild_night_says_wind_and_nothing_about_cold():
    w = Weather(dome=False, temp_f=69, wind_mph=6, wind_dir="SE", precip_chance=0.1,
                measured=True, forecast=True)
    why = evaluate_weather(w).reasons
    assert len(why) == 1 and why[0].startswith("Wind 6 mph forecast"), why
    assert not any("cold" in x.lower() for x in why)


def test_ask_is_handed_the_same_read():
    g = {"home": "GB", "away": "ATL", "weather": {"temp_f": 69, "wind_mph": 6},
         "conditions": {"why": ["Wind 6 mph forecast — passing yards −0.9%"]},
         "stadium": {"plays": "Open air in Green Bay."}}
    out = A.game_facts({"games": [g]}, g)
    assert out["weather_read"] == ["Wind 6 mph forecast — passing yards −0.9%"]
    assert out["stadium_note"] == "Open air in Green Bay."


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
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
