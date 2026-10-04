"""A WNBA game could never be shown live, and its board was six hours old.

REPORTED FROM A PHONE, 2026-08-30 at 8:56 PM ET. Two WNBA games — a 3:00
and a 5:00 tip — still reading "lines post closer to tip-off", hours
after both had finished. Ethan: "these games never went live and we
never made any props."

TWO INDEPENDENT FAULTS, either of which alone produces that screen.

ONE: SIX HOURS OF CACHE ON A LIVE FEED. `fetch_scoreboard` defaulted to
`ttl=21600`. The scoreboard carries every game's state and score, so on
today's date it IS the live feed — and the board built six minutes
earlier was reading a snapshot from before either game had tipped. The
old default's reasoning was sound and applied to the wrong days: "a
finished day never changes, so history caches effectively forever and a
re-run of a six-season backfill costs nothing." True of a finished day.
Today is not one, and one constant served both. The lifetime follows the
day now — five minutes for today, a month for a settled one, so the
backfill still costs nothing.

TWO: IN-PROGRESS WAS NOT REPRESENTED AT ALL. `parse_scoreboard` read
`completed` and nothing else, so a hoops game had exactly two states
here: finished, and not finished. A game being played was
indistinguishable from one that had not started. No cache fix reaches
that — with a perfectly fresh fetch the board still could not show a
live game. `cfbdata.parse_scoreboard` has carried the three states since
it was written; this one never did.

AND THE STATE HAD TO TRAVEL. `parse_schedule_day`, the mapping the board
actually reads, listed six fields and dropped the rest — so even once
the parser knew, the page did not. A reason has to reach where the
question is asked.

Run directly: `python3 tests/test_hoops_live_state.py`
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.sources import espnhoops as H


def _ev(state, completed, hs=None, as_=None):
    return {"id": "401", "date": "2026-08-30T19:00Z", "competitions": [{
        "competitors": [
            {"homeAway": "home",
             "team": {"abbreviation": "SEA", "displayName": "Storm"},
             "score": hs},
            {"homeAway": "away",
             "team": {"abbreviation": "LA", "displayName": "Sparks"},
             "score": as_}],
        "status": {"period": 3, "displayClock": "4:21",
                   "type": {"state": state, "completed": completed,
                            "shortDetail": "Q3 4:21"}}}]}


def _one(state, completed, hs=None, as_=None):
    return H.parse_scoreboard({"events": [_ev(state, completed, hs, as_)]})[0]


# --- the three states -----------------------------------------------------
def test_a_game_that_has_not_tipped_is_scheduled():
    assert _one("pre", False)["state"] == "scheduled"


def test_a_game_being_played_is_live():
    """THE STATE THAT DID NOT EXIST. Everything not finished was the
    same thing, so "never went live" was literally true of the data."""
    assert _one("in", False, 54, 49)["state"] == "live"


def test_a_finished_game_is_final():
    assert _one("post", True, 88, 80)["state"] == "final"


def test_the_three_are_distinguishable_from_each_other():
    got = {_one(*a)["state"] for a in
           (("pre", False), ("in", False, 54, 49), ("post", True, 88, 80))}
    assert got == {"scheduled", "live", "final"}, got


def test_an_unknown_status_reads_as_scheduled_rather_than_raising():
    assert _one("weird", False)["state"] == "scheduled"


# --- settlement is not handed a half-played score -------------------------
def test_the_settlement_score_is_still_final_only():
    """Unchanged deliberately: a third-quarter score written to
    `home_score` would grade a bet against a game still being played."""
    assert _one("in", False, 54, 49)["home_score"] is None
    assert _one("post", True, 88, 80)["home_score"] == 88


def test_the_running_score_is_carried_separately():
    assert _one("in", False, 54, 49)["live_home_score"] == 54


def test_a_scheduled_game_has_neither():
    g = _one("pre", False)
    assert g["home_score"] is None and g["live_home_score"] is None


# --- the cache lifetime follows the day -----------------------------------
def _today():
    return (dt.datetime.now() - dt.timedelta(hours=5)).date()


def test_todays_scoreboard_is_a_live_feed():
    assert not H._is_settled(_today().isoformat())
    assert H.LIVE_TTL <= 600


def test_a_finished_day_is_settled_and_caches_long():
    assert H._is_settled((_today() - dt.timedelta(days=1)).isoformat())


def test_the_day_rolls_at_five_am_not_midnight():
    """A game that tips at 10 PM Pacific is still last night's; treating
    it as settled at 00:01 would freeze it mid-fourth-quarter."""
    import inspect
    assert "hours=5" in inspect.getsource(H._is_settled)


def test_a_future_date_is_not_settled():
    assert not H._is_settled((_today() + dt.timedelta(days=1)).isoformat())


def test_a_malformed_date_is_not_assumed_settled():
    """Guessing "settled" on a string we cannot parse would cache a live
    day for a month."""
    assert not H._is_settled("not-a-date")


def test_the_six_hour_default_is_gone():
    import inspect
    src = inspect.getsource(H.fetch_scoreboard)
    assert "21600" not in src
    assert "ttl: int | None = None" in src


# --- and the state reaches the board --------------------------------------
def test_the_mapping_the_board_reads_carries_the_state():
    """It listed six fields and dropped the rest, so even once the
    parser knew, the page did not."""
    import inspect
    src = inspect.getsource(H.parse_schedule_day)
    for key in ("state", "live_home_score", "period", "clock", "completed"):
        assert f'"{key}"' in src, key


def test_the_mapping_does_not_pin_a_ttl_of_its_own():
    """`load_day(date)` with no ttl is what lets the date decide."""
    import inspect
    assert "load_day(date, league=league)" in \
        inspect.getsource(H.parse_schedule_day)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
