"""A number nobody measured never reaches the glass or the journal.

Ethan, 2026-08-26: "We should never ever display fake numbers on the
site." That rule was written about a strip of model-baseline prop lines.
This is the same rule, found by following the football weather down.

WHAT WAS HAPPENING. `engine/sources/nflverse.weather_from_row` reads a
schedule row's temp and wind, and nflverse fills those columns from the
game's own box score — so every outdoor game on a forward board is
blank, every time, and took the engine's mild-day prior of 60°F and
6 mph. Nothing said so. The consequences ran the length of the site:

  * the game card printed "60° · 6mph" and the wind gauge drew it as a
    compass reading with a green arrow, as though somebody had looked;
  * the journal recorded `wind_out = 6.0` as the wind each pick was made
    in, so every outdoor football bet landed in the miner's "calm
    (<8mph)" band — a constant it could convict or exonerate a slice on;
  * `engine/rules.py`'s 25-mph deep-passing warning and
    `engine/touchdowns.py`'s 20-mph suppression could never fire, because
    the number they tested was a constant three times below its own bar.

WHAT CHANGED. The defaults stay: the pricing paths need a number and a
mild day is the right prior. What they gained is a flag saying which
they are, and every surface that SHOWS or JOURNALS the number checks it.
College football already did this properly — `weather_checked`, and a
card that says "weather not pulled" — so its sentence became the shared
one rather than its own special case.

WHAT THIS DOES NOT DO is give the NFL real forecasts. CFB pulls them
(CFBD venue coordinates + Open-Meteo at the kickoff hour, keyless);
NFL has no such layer, and docs/NEXT.md carries that as the follow-up.
Until then the site says it does not know, which is the honest half.

Run directly: `python3 tests/test_unmeasured_weather.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.models import Weather                             # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


APP = _read("web", "js", "app.js")
VIS = _read("web", "js", "visuals.js")


def test_the_flag_exists_and_defaults_to_the_careful_answer():
    """An unflagged Weather is UNMEASURED, so a caller that forgets is
    quiet rather than confident."""
    assert Weather().measured is False


def test_the_payload_carries_the_flag_to_the_page():
    src = _read("engine", "pipeline.py")
    i = src.index('"weather": {')
    assert '"measured"' in src[i:i + 700], \
        "the board ships weather with no way to tell a reading from a prior"


def test_the_prop_journal_records_no_wind_it_did_not_measure():
    src = _read("engine", "pipeline.py")
    i = src.index('d["wind_out"]')
    assert "measured" in src[i:i + 260], \
        "an unmeasured prior is journaled as the wind a bet was made in"


def test_the_veto_is_asked_with_no_wind_dimension_either():
    """The miner's slices are keyed by band. Asking the veto about a
    'calm' game that nobody measured would let a closed slice refuse — or
    spare — a pick on a constant."""
    src = _read("engine", "betting.py")
    i = src.index('"wind_out": None if _w.dome')
    assert "measured" in src[i - 200:i + 200]


def test_the_game_bet_journal_checks_it_too():
    src = _read("engine", "ledger.py")
    i = src.index("def _weather_map(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "measured" in body and "weather_checked" in body, \
        "game bets journal a wind nobody pulled"


def test_the_card_stops_printing_a_forecast_nobody_pulled():
    i = APP.index("const wxKnown =")
    assert "w.measured" in APP[i:i + 200] and "weather_checked" in APP[i:i + 200]
    # The chip's own guard was `temp_f != null`, which the prior satisfies.
    j = APP.index("game-wx-chip")
    assert "wxKnown" in APP[j - 400:j], \
        "the stadium chip prints the prior again"


def test_every_other_weather_surface_asks_the_same_question():
    """Four of them, and a fix that reached three would leave the number
    on the site in the fourth."""
    # The game page header.
    assert 'w.measured === false ? "Outdoor · weather not pulled"' in APP
    # The key-insights list (a 12mph note off a 6mph constant).
    assert 'w.measured !== false && (w.wind_mph || 0) >= 12' in APP
    # The weather page's own row.
    i = APP.index('const cells = w.dome')
    assert "w.measured === false" in APP[i:i + 500]
    # And the animated gauge, which drew the prior as a compass reading.
    assert "weather.measured === false" in VIS
    k = VIS.index("weather.measured === false")
    assert "NOT PULLED" in VIS[k:k + 1400]


def test_absence_of_the_flag_reads_as_known_so_mlb_is_untouched():
    """MLB really does pull its weather, and its payload predates this
    flag. `=== false` rather than a truthiness test is what keeps that
    board reading exactly as it did."""
    for src, name in ((APP, "app.js"), (VIS, "visuals.js")):
        assert "measured === false" in src, name
        assert "!w.measured ?" not in src, \
            f"{name} turned an absent flag into 'unmeasured'"


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
