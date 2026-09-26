"""College player logs for the season being PLAYED, not only the four before it.

Ethan, 2026-09-18: "CFB still hasn't graded any edge bets or most likely
bets." Then: "It's been like that since week zero."

Every college player-market bet — props, TD long shots, Most Likely
player rows, stale flags on player markets — settles against
`player_game_logs`. On the container this was found in, that table held,
for the 2026 season, ZERO college rows, beside 100 ingested games. So
the whole college player book sat open from the opener, and correctly:
`settle_from_history` leaves a bet open rather than inventing a grade,
and `_absent_player_verdict`'s college branch voids only when the team's
box IS filed. Nothing was mis-graded. Nothing could be graded.

THE DATA WAS THERE THE WHOLE TIME. A dry run against the cfbfastR mirror
on 2026-09-18 parsed 12,179 rows covering 2026-08-29 through 09-06 — the
exact games that were not grading — and `cfb_games_for(conn, 2026)`
returned 199 joinable games. Source, parse and join were all fine.

WHAT WAS WRONG WAS THE SCHEDULE, in two compounding ways:

  1. The one-time historical backfill is `[today.year - n for n in
     (4, 3, 2, 1)]` — 2022-2025 in 2026. The season being played has
     never been in that list. A box that ran it came away with four
     years of history and nothing from the year its board prices. That
     is the fingerprint in the file: college logs from 2022-08-27 to
     2025-10-26, and nothing after.

  2. The only other path was `elif today.weekday() == 0` — Mondays, and
     only while `have` was under the floor. `have` counts EVERY season's
     anytime_td rows (54,610 there), so five years of history satisfied
     a threshold that says nothing about whether this season landed, and
     the `elif` made the Monday branch unreachable besides.

The results half of the same nightly already refreshes the current
season with `[season] if in_season else []`, which is exactly why
`games` was current to the day while the player half was a month behind.
This file pins the same rule on both halves.

Run directly: `python3 tests/test_the_season_being_played_is_ingested.py`
"""

import datetime as dt
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.maintenance import (CFB_MIN_PLAYER_ROWS,                # noqa: E402
                                cfb_player_seasons)

#: A stocked box: five seasons of history, far over the floor. This is
#: the state every box reaches after its first backfill and stays in.
STOCKED = 54_610
EMPTY = 0


# --- the season being played --------------------------------------------
def test_a_stocked_box_still_ingests_the_season_it_is_pricing():
    """THE BUG. Before this, a stocked box asked for nothing on six days
    of seven, and the season being played was never in the seventh's
    list either unless the floor happened to be unmet."""
    for day in (dt.date(2026, 9, 15), dt.date(2026, 9, 16),
                dt.date(2026, 9, 17), dt.date(2026, 9, 18),
                dt.date(2026, 9, 19), dt.date(2026, 9, 20)):
        got = cfb_player_seasons(day, STOCKED)
        assert got == [2026], (
            f"{day} ({day.strftime('%a')}) asked for {got} — the season "
            f"being played must be ingested every night it is on")


def test_monday_is_not_special_any_more():
    """It was the ONLY day, which is why a month of Saturdays never
    reached the journal."""
    mon = cfb_player_seasons(dt.date(2026, 9, 21), STOCKED)
    tue = cfb_player_seasons(dt.date(2026, 9, 22), STOCKED)
    assert mon == tue == [2026], (mon, tue)


def test_the_first_run_takes_the_current_season_with_the_history():
    """`(4, 3, 2, 1)` is 2022-2025. A box backfilling on opening week
    must not come away with four finished seasons and none of the one
    that is being played."""
    got = cfb_player_seasons(dt.date(2026, 8, 24), EMPTY)
    assert got == [2022, 2023, 2024, 2025, 2026], got
    assert 2026 in got, "the season being played is missing from the backfill"


def test_the_current_season_is_asked_for_once_not_twice():
    """A first run in, say, 2025 would have 2025 in both lists; asking
    for it twice would walk a 200k-row file for nothing."""
    got = cfb_player_seasons(dt.date(2026, 8, 24), EMPTY)
    assert len(got) == len(set(got)), got


# --- the rules that must NOT change --------------------------------------
def test_the_historical_backfill_still_runs_only_once():
    """It is four seasons of a large file. A stocked box must not walk
    them again every night — that is what the floor is for."""
    assert cfb_player_seasons(dt.date(2026, 9, 18), STOCKED) == [2026]
    assert cfb_player_seasons(dt.date(2026, 9, 18), CFB_MIN_PLAYER_ROWS) == [2026]
    under = cfb_player_seasons(dt.date(2026, 9, 18), CFB_MIN_PLAYER_ROWS - 1)
    assert 2022 in under, "a box under the floor stopped backfilling history"


def test_the_offseason_asks_for_nothing():
    """June has no college football and the finished file is already on
    disk. A nightly fetch there is pure waste."""
    for day in (dt.date(2026, 3, 1), dt.date(2026, 6, 10),
                dt.date(2026, 7, 31)):
        assert cfb_player_seasons(day, STOCKED) == [], day


def test_january_is_still_in_season():
    """Bowls and the playoff are January, and they are the games the
    board is pricing then."""
    assert cfb_player_seasons(dt.date(2027, 1, 5), STOCKED) == [2026], \
        "January still belongs to the season that started in August"


# --- the file being read has to be a fresh one ---------------------------
def test_the_season_still_being_played_is_not_served_from_a_week_old_cache():
    """`fetch_season` defaults to a seven-day TTL, which is right for a
    finished season — that file never changes again — and exactly wrong
    for the one gaining a week of games every Saturday. Refreshing
    nightly against a seven-day cache would re-parse last week's file six
    nights running and call it current."""
    from engine import ingest
    assert ingest.CFB_LIVE_SEASON_TTL < 86_400 * 7, \
        "the live season's cache is no shorter than a finished season's"
    src = inspect.getsource(ingest.ingest_cfb_player_history)
    assert "fresh" in src and "CFB_LIVE_SEASON_TTL" in src, \
        "the short TTL is defined and never reaches fetch_season"


def test_the_nightly_tells_the_ingest_which_season_is_live():
    """The TTL only applies to the season named as still being played;
    a caller that does not name one gets the old behaviour exactly."""
    import engine.maintenance as m
    src = inspect.getsource(m)
    i = src.index("ingest_cfb_player_history(_pconn")
    assert "fresh=season" in src[i:i + 200], (
        "the nightly does not name the live season, so every file keeps "
        "the seven-day cache")


def test_a_finished_season_keeps_the_long_cache():
    from engine import ingest
    sig = inspect.signature(ingest.ingest_cfb_player_history)
    assert sig.parameters["fresh"].default is None, \
        "every season is being treated as live; a finished file never changes"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
