"""Games off the usual schedule are priced, reported and posted on their own day (step AED, 24 November 2026).

Ethan, 24 November 2026: "since it's thanksgiving week there is nfl games Wednesday Thursday Friday and Sunday so make
sure the models and game reports and bets and all that shit automatically adjusts and is ready too fire on those
games and any other games that isn't on the normal nfl schedule. And also make sure that the same for any other
sport too".

What was read that day, and is pinned here so it stays so:
  * the board turns to week 13 on Tuesday morning, the week of the next game still to be played: Wednesday's;
  * the odds plan buys the NFL on any day it plays (`oddsplan.day_need` from the real slate) and nothing on a day
    it does not, whatever the weekday;
  * every game's picks and parlays post 75 minutes before its own kickoff, a Wednesday night's and a Friday
    afternoon's alike, never on a weekday rule;
  * a short week is said as one (engine/fatigue): three days' rest from a Sunday to a Wednesday or a Thursday;
  * the featured games are Ethan's three (a Lions game, a Thursday night, a Monday night): Thanksgiving's Lions game
    is one, the Thursday night game another, a Wednesday or a Friday game neither;
  * a neutral site is said as one in every league's report: college basketball's tournaments sit on the board as
    ``neutral``, which the reports never read (football's key is ``neutral_site``), so a Maui or Bahamas game was
    "at home" for its listed home side.

Offline. Run directly: `python3 tests/test_off_day_games_fire_on_their_own_day.py`
"""
import datetime as dt
import os
import sys
import tempfile
import types
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import launch                                                        # noqa: E402
from engine import featured, gameparlays, oddsplan                   # noqa: E402
from engine import gamereport as R                                   # noqa: E402
from engine.fatigue import rest_band                                 # noqa: E402

ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
WED, THU, FRI, SUN = (dt.date(2026, 11, 25), dt.date(2026, 11, 26), dt.date(2026, 11, 27), dt.date(2026, 11, 29))


def _rows():
    games = [(2026, 12, "2026-11-22"), (2026, 12, "2026-11-23"), (2026, 13, "2026-11-25"), (2026, 13, "2026-11-26"),
             (2026, 13, "2026-11-27"), (2026, 13, "2026-11-29"), (2026, 13, "2026-11-30")]
    return [{"season": str(s), "week": str(w), "gameday": d} for s, w, d in games]


def test_the_board_turns_to_the_wednesday_games_week_on_tuesday_morning():
    tue_7am = dt.datetime(2026, 11, 24, 7, 0, tzinfo=ET)
    assert launch._current_nfl_week(launch._nfl_slate_day(tue_7am), _rows()) == (2026, 13)
    mon_late = dt.datetime(2026, 11, 24, 0, 30, tzinfo=ET)      # Monday night's game still on
    assert launch._current_nfl_week(launch._nfl_slate_day(mon_late), _rows()) == (2026, 12)


def test_the_odds_plan_buys_the_nfl_on_any_day_it_plays():
    for day in (WED, THU, FRI, SUN):
        assert oddsplan.day_need("nfl", day, games=1) > 0, day
        assert oddsplan.day_need("nfl", day, games=0) == 0, day
    assert oddsplan.day_need("nfl", THU, games=3) > oddsplan.day_need("nfl", WED, games=1), \
        "three games on Thanksgiving cost more than one on Wednesday"


def _game(date, kickoff, home="LA", away="GB"):
    return {"date": date, "kickoff": kickoff, "home": home, "away": away}


def test_each_game_posts_75_minutes_before_its_own_kickoff():
    wed = gameparlays.game_start(_game("2026-11-25", "20:00"))
    assert wed == dt.datetime(2026, 11, 26, 1, 0, tzinfo=UTC), wed
    due, at, waiting = gameparlays.post_due(wed, "nfl", dt.datetime(2026, 11, 25, 18, 0, tzinfo=ET), ready=True)
    assert (due, at, waiting) == (False, dt.datetime(2026, 11, 25, 23, 45, tzinfo=UTC), False)
    due, _at, _w = gameparlays.post_due(wed, "nfl", dt.datetime(2026, 11, 25, 18, 50, tzinfo=ET), ready=True)
    assert due, "posted at 6:45 PM ET, a Wednesday like a Sunday"
    fri = gameparlays.game_start(_game("2026-11-27", "15:00", "PHI", "CHI"))
    _due, at, _w = gameparlays.post_due(fri, "nfl", dt.datetime(2026, 11, 27, 9, 0, tzinfo=ET), ready=True)
    assert at == dt.datetime(2026, 11, 27, 18, 45, tzinfo=UTC), at


def test_a_short_week_is_said_as_one():
    assert rest_band(3) == "short week" and rest_band(4) == "short week", "Sunday to Wednesday or Thursday"
    assert rest_band(5) == "6 days or fewer" and rest_band(7) == "normal week"


def test_the_featured_games_are_ethans_three_on_a_holiday_week():
    assert featured.of_game(_game("2026-11-26", "12:30", "DET", "CHI"), "nfl") == ["lions"]
    assert featured.of_game(_game("2026-11-26", "20:20", "BAL", "CIN"), "nfl") == ["thursday"]
    assert featured.of_game(_game("2026-11-26", "16:30", "DAL", "KC"), "nfl") == [], "a day game is no night"
    assert featured.of_game(_game("2026-11-25", "20:00"), "nfl") == [] and \
        featured.of_game(_game("2026-11-27", "15:00", "PHI", "CHI"), "nfl") == []


def _ctx(g, sport="cbb", meta=None):
    return types.SimpleNamespace(g=g, meta=meta or {}, sport=sport, home=g["home"], away=g["away"])


def test_a_neutral_site_is_said_as_one_in_every_league():
    assert R.is_neutral(_ctx({"home": "KU", "away": "DUKE", "neutral": True}))
    assert R.is_neutral(_ctx({"home": "MIN", "away": "PIT", "neutral_site": True}, "nfl"))
    assert R.is_neutral(_ctx({"home": "KU", "away": "DUKE"}, meta={"neutral_site": True}))
    assert not R.is_neutral(_ctx({"home": "KU", "away": "DUKE", "neutral": False}))
    assert not R.is_neutral(types.SimpleNamespace())
    from engine import leaguereport as LR
    c = R.Ctx({"home": "KU", "away": "DUKE", "neutral": True, "date": "2026-11-25"}, {"date": "2026-11-25"},
              names={"KU": "Kansas", "DUKE": "Duke"}, sport="cbb")
    form = {"KU": {"n": 5, "w": 4, "margin": 6.0, "venue_w": 3, "venue_l": 0},
            "DUKE": {"n": 5, "w": 3, "margin": 2.0, "venue_w": 1, "venue_l": 1}}
    where = [x for x in LR.form_lines(c, form) if x.startswith("Where they play")]
    assert where and where[0].startswith("Where they play: a neutral site tonight; "), where
    home = R.Ctx({"home": "KU", "away": "DUKE", "date": "2026-11-25"}, {"date": "2026-11-25"},
                 names={"KU": "Kansas", "DUKE": "Duke"}, sport="cbb")
    assert [x for x in LR.form_lines(home, form) if x.startswith("Where they play: Kansas")], \
        "a home game reads as it did"


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
