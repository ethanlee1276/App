"""Do not pay for a Tuesday in football season.

`harvest_odds.py` walks every date in its range and makes one historical
events call per day. That call is billed whether or not it finds a game,
and an NFL season is ~123 days of which 18 are Sundays — so harvesting a
season as one range spends a hundred calls on days nobody played before
buying a single price. On a 20,000-credit plan that is real money for
nothing.

`--weekdays` filters the list BEFORE the estimate, the confirmation
prompt and the loop, so all three agree about how much work is being
asked for. A filter applied inside the loop would still have quoted the
unfiltered cost at the one moment the operator is deciding whether to
spend it.
"""

import datetime as dt
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import harvest_odds as H

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = ("2025-09-04", "2026-01-04")


def _days():
    return list(H.daterange(*SEASON))


def test_a_full_nfl_season_is_mostly_days_nobody_plays():
    assert len(_days()) == 123


def test_sundays_only_is_eighteen_days_not_a_hundred_and_twenty_three():
    kept = H.keep_weekdays(_days(), "sun")
    assert len(kept) == 18
    assert all(d.weekday() == 6 for d in kept)


def test_the_nfls_three_game_days_can_be_asked_for_together():
    kept = H.keep_weekdays(_days(), "thu,sun,mon")
    assert {d.weekday() for d in kept} == {0, 3, 6}


def test_the_abbreviation_and_the_whole_word_both_work():
    assert H.keep_weekdays(_days(), "SUNDAY") == H.keep_weekdays(_days(), "sun")
    assert H.keep_weekdays(_days(), " Sun , Mon ") == \
        H.keep_weekdays(_days(), "sun,mon")


def test_a_prefix_is_not_a_weekday():
    """Truncating to three characters accepted 'sundy' — a typo that
    harvests the right days by luck — and 'monsoon' as Monday."""
    for junk in ("sundy", "monsoon", "s", "su"):
        try:
            H.keep_weekdays(_days(), junk)
        except ValueError:
            continue
        raise AssertionError(f"{junk!r} was accepted as a weekday")


def test_an_empty_spec_keeps_every_day():
    """`--weekdays` unset must not quietly become `--weekdays mon`."""
    assert H.keep_weekdays(_days(), "") == _days()
    assert H.keep_weekdays(_days(), " , ") == _days()


def test_a_misspelled_day_is_refused_by_name_rather_than_ignored():
    """Silently harvesting nothing because 'sunday' was typed 'sundy' is a
    run that looks successful and buys nothing."""
    try:
        H.keep_weekdays(_days(), "sundy")
    except ValueError as exc:
        assert "sun" in str(exc)          # the list of valid names
    else:
        raise AssertionError("a bad weekday name must raise")


def test_the_weekday_index_matches_the_standard_library():
    for i, name in enumerate(H.WEEKDAYS):
        day = dt.date(2025, 9, 1) + dt.timedelta(days=i)   # 2025-09-01 = Mon
        assert H.keep_weekdays([day], name) == [day], name


# --- through the CLI ---------------------------------------------------------
def _run(*args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "harvest_odds.py"),
                           *args], capture_output=True, text=True, timeout=60)


def test_the_plan_line_counts_the_filtered_days_not_the_range():
    out = _run("nfl", "--from", SEASON[0], "--to", SEASON[1],
               "--markets", "receptions", "--weekdays", "sun", "--dry-run")
    assert out.returncode == 0, out.stderr
    assert "for 18 day(s)" in out.stdout
    assert "sun only" in out.stdout


def test_a_bad_weekday_stops_before_any_request():
    out = _run("nfl", "--from", SEASON[0], "--to", SEASON[1],
               "--weekdays", "funday", "--dry-run")
    assert "unknown weekday" in out.stdout
    assert "Dry run" not in out.stdout, "it must not go on to plan a harvest"


def test_a_range_with_none_of_the_asked_for_days_says_so_and_stops():
    out = _run("nfl", "--from", "2025-09-08", "--to", "2025-09-09",
               "--weekdays", "sun", "--dry-run")
    assert "nothing to harvest" in out.stdout


def test_the_hour_help_warns_that_the_default_is_a_baseball_hour():
    """23:00 UTC is 6pm ET — after the NFL's 1pm games have finished.
    Harvesting a season at the default hour buys post-game snapshots for
    the whole early slate."""
    out = _run("--help")
    assert "AFTER the NFL's 1pm games" in out.stdout


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
