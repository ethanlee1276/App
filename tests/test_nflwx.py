"""The NFL finally pulls a forecast, and its coordinates are checked.

WHAT WAS THERE BEFORE was not a forecast. The board's weather came from
the nflverse schedule's `temp` and `wind` columns, which nflverse fills
from the game's OWN box score — so every outdoor game on a forward board
arrived blank and took the engine's mild-day prior of 60°F and 6 mph.
That prior was flagged as one on 2026-08-26 so it could stop posing as a
reading (`tests/test_unmeasured_weather.py`); this is the other half.

THE COORDINATES ARE THE ONLY NEW FACTS IN IT, and a coordinate is
exactly the kind of constant that rots quietly — a wrong one puts a real
forecast in the wrong city and nothing about the output looks broken. So
they are not taken on trust. They are checked against two tables this
repo already runs on:

  * `engine.mlb.sources.mlbstats.PARK_COORDS`, which this site has been
    fetching per-park weather with all season. Twenty-four NFL stadiums
    share a city with a major-league ballpark, and each must sit within
    65km of it — the shared complexes (Baltimore, Detroit, Kansas City,
    Seattle, Philadelphia, Dallas, Cincinnati, Pittsburgh) come out under
    two kilometres, and a wrong city would fail by hundreds.
  * `engine.fatigue.TEAM_UTC_OFFSET_FROM_ET`, an independent table with
    no coordinates in it. A longitude and a time zone that disagree are
    the same typo seen from the other side, and this catches the eight
    cities with no ballpark to lean on.

Run directly: `python3 tests/test_nflwx.py`
"""

import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import nflwx                                       # noqa: E402
from engine.fatigue import TEAM_UTC_OFFSET_FROM_ET as TZ       # noqa: E402
from engine.mlb.sources.mlbstats import PARK_COORDS            # noqa: E402
from engine.models import Game, Weather                        # noqa: E402
from engine.stadiums import STADIUMS, STADIUM_COORDS as COORDS  # noqa: E402


def _km(a, b):
    (la, lo), (lb, lob) = a, b
    return 6371.0 * math.acos(min(1.0,
        math.sin(math.radians(la)) * math.sin(math.radians(lb))
        + math.cos(math.radians(la)) * math.cos(math.radians(lb))
        * math.cos(math.radians(lo - lob))))


# --- the coordinates -------------------------------------------------------

def test_every_club_has_somewhere_to_play():
    missing = sorted(set(STADIUMS) - set(COORDS))
    assert not missing, f"no coordinates for {missing}"
    assert not sorted(set(TZ) - set(COORDS)), "a club the fatigue table knows"


def test_the_two_shared_buildings_share_one_forecast():
    """Two clubs, one building, one answer — and a table that gave them
    different coordinates would be describing a stadium that does not
    exist."""
    assert COORDS["NYG"] == COORDS["NYJ"]
    assert COORDS["LAR"] == COORDS["LAC"] == COORDS["LA"]


def test_every_stadium_is_inside_the_country_it_plays_in():
    for team, (lat, lon) in COORDS.items():
        assert 24.0 <= lat <= 49.5, f"{team} latitude {lat}"
        assert -125.0 <= lon <= -66.0, f"{team} longitude {lon}"


def test_each_stadium_sits_in_the_city_its_ballpark_is_in():
    """The strong check, and the reason this table can be trusted at all:
    a wrong city fails by hundreds of kilometres."""
    checked = 0
    for team, c in COORDS.items():
        near = min((_km(c, pc), pk) for pk, pc in PARK_COORDS.items())
        if near[0] > 65.0:
            continue                       # no ballpark in this city
        checked += 1
        assert near[0] <= 65.0, f"{team} is {near[0]:.0f}km from {near[1]}"
    assert checked >= 20, \
        f"only {checked} stadiums could be cross-checked — the ballpark " \
        "table shrank, and with it the evidence under this one"


#: Longitude bands per time zone. ARIZONA IS THE DOCUMENTED EXCEPTION and
#: not a typo: it keeps mountain time year round and does not observe
#: daylight saving, so through the football season it reads as Pacific
#: while sitting at mountain longitudes — `engine/fatigue.py` says so in
#: its own comment, which is why that table groups it with Seattle.
_BANDS = {-3: (-125.0, -114.0), -2: (-115.0, -102.0),
          -1: (-106.0, -80.5), 0: (-91.0, -66.0)}
_TZ_EXCEPT = {"ARI"}


def test_no_longitude_disagrees_with_its_own_time_zone():
    bad = []
    for team, (_lat, lon) in COORDS.items():
        if team in _TZ_EXCEPT or team not in TZ:
            continue
        lo, hi = _BANDS[TZ[team]]
        if not lo <= lon <= hi:
            bad.append((team, TZ[team], lon))
    assert not bad, f"longitude and time zone disagree: {bad}"


def test_arizona_is_the_exception_on_purpose_and_says_so():
    """Left in the exception list only because the fatigue table already
    explains it; a second club appearing here would be a typo hiding
    behind a comment."""
    assert _TZ_EXCEPT == {"ARI"}
    src = open(os.path.join(ROOT, "engine", "fatigue.py"),
               encoding="utf-8").read()
    assert "does not\n#: observe DST" in src or "does not observe DST" in src.replace("\n#:", "")


def test_the_precision_claimed_is_the_precision_held():
    """Three decimals is about a hundred metres, far inside Open-Meteo's
    ~11km grid. More digits would imply a survey nobody did."""
    for team, (lat, lon) in COORDS.items():
        for v in (lat, lon):
            assert abs(round(v, 3) - v) < 1e-9, f"{team} claims {v}"


# --- the join --------------------------------------------------------------

def _game(home="BUF", roof="outdoors", date="2026-12-13", kickoff="13:00",
          **kw):
    return Game(home=home, away="NE", weather=Weather(), date=date,
                kickoff=kickoff, roof=roof, **kw)


def _fc(**over):
    got = {"temp_f": 34, "wind_mph": 19, "wind_dir": "NW", "precip_chance": 0.7}
    got.update(over)
    return lambda lat, lon, date, kickoff: got


def test_a_real_forecast_lands_and_is_flagged_measured():
    g = _game()
    assert nflwx.attach([g], forecast=_fc()) == 1
    w = g.weather
    assert w.measured is True and w.temp_f == 34 and w.wind_mph == 19
    assert w.wind_dir == "NW" and w.precip_chance == 0.7


def test_the_forecast_is_asked_for_at_the_kickoff_hour():
    """A Saturday slate built on Wednesday: current conditions say
    nothing about Sunday, and the bare Eastern clock the schedule carries
    is not an instant until its own date is joined to it."""
    seen = {}

    def spy(lat, lon, date, kickoff):
        seen.update(lat=lat, lon=lon, date=date, kickoff=kickoff)
        return {"temp_f": 50, "wind_mph": 5}

    nflwx.attach([_game(home="GB", date="2026-12-13", kickoff="16:25")],
                 forecast=spy)
    assert (seen["lat"], seen["lon"]) == COORDS["GB"]
    assert seen["date"] == "2026-12-13"
    assert seen["kickoff"].startswith("2026-12-13T16:25"), seen["kickoff"]
    assert seen["kickoff"].endswith(("-05:00", "-04:00")), \
        "the kickoff went out with no zone on it"


def test_a_dome_is_answered_without_asking_anybody():
    called = []
    g = _game(home="DET", roof="dome")
    assert nflwx.attach([g], forecast=lambda *a: called.append(a) or None) == 1
    assert not called, "a forecast was fetched for an indoor game"
    assert g.weather.dome is True and g.weather.measured is True


def test_an_open_retractable_roof_is_outdoor_weather():
    """`open` is a retractable roof that is OPEN. Reading it as a dome
    would skip the forecast for a game being played in the rain."""
    g = _game(home="HOU", roof="open")
    assert nflwx.attach([g], forecast=_fc()) == 1
    assert g.weather.dome is False and g.weather.measured is True


def test_every_kind_of_miss_keeps_the_prior_and_says_nothing():
    cases = {
        "unknown stadium": _game(home="XXX"),
        "no kickoff": _game(kickoff=""),
        "no date to join it to": _game(date=""),
        "neutral site": _game(neutral_site=True),
    }
    for why, g in cases.items():
        assert nflwx.attach([g], forecast=_fc()) == 0, why
        assert g.weather.measured is False, why
    # And a forecast that refuses is a miss, not a crash.
    def boom(*a):
        raise RuntimeError("open-meteo said no")
    g = _game()
    assert nflwx.attach([g], forecast=boom) == 0
    assert g.weather.measured is False


def test_a_neutral_site_is_not_given_the_home_teams_weather():
    """The schedule says "Neutral" without saying where. A London game
    handed New Jersey's forecast would be a measured-looking number about
    the wrong continent."""
    g = _game(home="NYJ", neutral_site=True)
    assert nflwx.attach([g], forecast=_fc()) == 0
    assert g.weather.measured is False


def test_precipitation_becomes_rain_or_snow_at_the_boards_own_threshold():
    """Both booleans are derived, and narrowly: `engine/weather.py`
    already treats `precip_chance >= 0.6` as rain, so the threshold is
    its own rather than a new one invented here."""
    warm = _game()
    nflwx.attach([warm], forecast=_fc(temp_f=48, precip_chance=0.8))
    assert warm.weather.rain is True and warm.weather.snow is False
    cold = _game()
    nflwx.attach([cold], forecast=_fc(temp_f=28, precip_chance=0.8))
    assert cold.weather.snow is True and cold.weather.rain is False
    dry = _game()
    nflwx.attach([dry], forecast=_fc(temp_f=28, precip_chance=0.1))
    assert dry.weather.snow is False and dry.weather.rain is False


def test_it_reuses_colleges_join_rather_than_growing_a_second_one():
    """`fetch_forecast`, `pick_hour` and `compass` take a latitude, a
    longitude, a date and an instant — none of that is college-shaped,
    and two copies of one join drift apart."""
    src = open(os.path.join(ROOT, "engine", "nflwx.py"), encoding="utf-8").read()
    assert "from .cfb.wx import fetch_forecast, pick_hour" in src
    assert "api.open-meteo.com" not in src, \
        "a second URL appeared here instead of calling the one that works"


def test_the_build_pulls_it_before_anything_reads_the_weather():
    src = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    i = src.index("def show_games(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "nflwx.attach(games)" in body
    assert "not pulled" in body, \
        "the build prints a prior as though it were a reading again"


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
