"""A finished season presented as the current state of the league.

Ethan, 2026-08-24, with the site live: "we are showing the 2025 rankings
still but we should just show that we are still waiting on 2026 season to
progress for like the playoff chart and whatever else still needs that
data."

He was looking at the NFL standings page in August 2026, and it was
showing the league's FINAL 2025 table and the completed 2025 playoff
bracket under a "2025 regular season" header — six months after that
season ended.

THE CAUSE IS A QUESTION ASKED OF THE WRONG FUNCTION. season_of() labels
DATES: an August date sits in no window, so it belongs to the season that
just finished. That is the right answer for keying a game row and exactly
the wrong one for choosing which season a standings page SHOWS. The build
now advances to the upcoming season once the resolved season's window has
closed, and the page waits.

AND WHILE WAITING, THE FEED IS NEVER ASKED. Some feeds 404 on an unplayed
season, some return last season relabelled, some return thirty-two 0-0
rows — every one of those puts a table on a page whose honest answer is
"waiting". The recorder below proves the call count is zero, not just
that the result was ignored.

Run directly: `python3 tests/test_season_wait.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import standings_build as SB                                     # noqa: E402
from engine.db import connect                                    # noqa: E402
from engine.sources import leaguestandings                       # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()

AUG = "2026-08-24"     # the day Ethan was looking at the page


class _Feed:
    """Stands in for the league feed and counts what it was asked."""

    def __init__(self, rows=None):
        self.rows = rows
        self.seen = []

    def __call__(self, sport, season):
        self.seen.append((sport, season))
        if self.rows is None:
            raise RuntimeError("feed down")
        return self.rows


def _build(sport, season=None, today=AUG, feed=None):
    real_fetch = leaguestandings.fetch
    real_connect = SB.connect
    stub = feed or _Feed()
    leaguestandings.fetch = stub
    SB.connect = lambda: connect(":memory:")
    try:
        return SB.build(sport, season=season, today=today), stub
    finally:
        leaguestandings.fetch = real_fetch
        SB.connect = real_connect


# --- which season the page shows ------------------------------------------

def test_the_offseason_gap_waits_on_the_upcoming_season():
    """August 2026: the 2025 window closed in February. The page's season
    is 2026, and it says so as a wait rather than as an empty 2026."""
    for sport, first in (("nfl", "2026-09-01"), ("nba", "2026-10-01")):
        b, _ = _build(sport)
        assert b["season"] == 2026, f"{sport} still shows {b['season']}"
        assert b["season_wait"] is True
        assert b["first_games"] == first
        assert "has not started yet" in b["note"]
        assert "playoff picture" in b["note"], \
            "the note stopped answering the thing Ethan asked about"


def test_a_date_inside_the_window_is_that_season():
    """January 2026 is the 2025 NFL season, mid-playoffs. Nothing waits."""
    b, _ = _build("nfl", today="2026-01-10")
    assert b["season"] == 2025
    assert b["season_wait"] is False


def test_kickoff_ends_the_wait():
    b, feed = _build("nfl", today="2026-09-15")
    assert b["season"] == 2026
    assert b["season_wait"] is False
    assert feed.seen == [("nfl", 2026)], \
        "an in-season build no longer asks the league for its table"


def test_a_sport_in_season_today_is_untouched():
    """MLB is mid-season in August. Its build must not change shape."""
    b, feed = _build("mlb")
    assert b["season"] == 2026
    assert b["season_wait"] is False
    assert feed.seen == [("mlb", 2026)]


def test_an_explicit_season_is_honoured_finished_or_not():
    """--season 2025 in August 2026 means 2025: the flag exists for
    looking at history, and history is allowed to be finished."""
    b, feed = _build("nfl", season=2025)
    assert b["season"] == 2025
    assert b["season_wait"] is False
    assert feed.seen == [("nfl", 2025)]


# --- what waiting means ---------------------------------------------------

def test_the_feed_is_never_asked_while_waiting():
    """Zero calls — not a call whose answer was thrown away. A feed that
    returns last season relabelled would otherwise put the exact table
    Ethan complained about back on the page."""
    rows = [{"team": "KC", "wins": 15, "losses": 2}]
    b, feed = _build("nfl", feed=_Feed(rows))
    assert feed.seen == [], f"the feed was asked during the wait: {feed.seen}"
    assert b["team_count"] == 0


def test_the_bracket_waits_too():
    """The playoff chart was the thing named. An unplayed season has no
    played games, so the bracket must come back not-started and empty."""
    b, _ = _build("nfl")
    assert b["bracket"]["started"] is False
    assert not b["bracket"].get("rounds")
    assert b["projected_seeds"] == []


def test_waiting_is_stamped_as_data_not_only_prose():
    b, _ = _build("nfl")
    assert b["season_wait"] is True and b["first_games"]
    b2, _ = _build("nfl", today="2026-09-15")
    assert b2["season_wait"] is False and b2["first_games"] == ""


# --- the page -------------------------------------------------------------

def test_the_header_says_waiting_not_regular_season():
    """The subtitle branch. Without it an empty 2026 read "2026 regular
    season · 0 games counted (the league's feed was unavailable)" — we
    never asked the feed, and blaming it would send someone to debug a
    working fetcher."""
    # Anchored on the subtitle assignment itself, not on the first
    # `d.season_wait` in the file: the rankings wait section (2026-09-05,
    # tests/test_rankings_never_silent.py) reads the same field and is
    # defined above renderStandings, so "first occurrence" stopped being
    # this branch.
    i = APP.index("sub.textContent = d.season_wait")
    seg = APP[i - 200:i + 400]
    assert "waiting on the ${d.season} season" in seg
    assert "first games" in seg


def test_the_empty_slate_is_titled_for_the_wait():
    i = APP.index('"No standings yet"')
    seg = APP[i - 300:i + 100]
    assert "Waiting on the ${d.season} season" in seg, \
        "the empty slate reads as a fault instead of a wait"


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
