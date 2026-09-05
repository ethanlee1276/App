"""The Live tab showed nothing while bets were running.

"the live board for mlb is not displaying bets. we have live bets going on
right now and its not showing anything"

Two filters on one query were doing it, and neither was obviously wrong on
its own:

    WHERE status='open' AND sport='mlb' AND date=? AND category='main'

`category='main'` excludes 'longshot' — the home-run board. On an MLB slate
that is where most of the night's action is: real picks, real prices,
journaled and graded, scored on the Record page. They were never eligible
to appear on the Live tab at all.

`date=?` excludes any bet whose journal date drifted off the slate's. That
drift is not hypothetical — we fixed it in the other direction last week.
`log_longshots` stamps a row with its GAME's date, so a 10:10 PM first
pitch is filed under tomorrow in UTC. Live on tonight's card, filed under a
date this query never asked for.

And even once the rows arrived, `assemble_live_picks` placed player props
by looking them up in `recommendations`, which does not contain long shots.
Every one of them would have come back "unmapped" — visible, but with no
game, no score, and no live stat line.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.livepicks import assemble_live_picks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = open(os.path.join(ROOT, "mlb_build.py"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()

LIVE_GAME = {"home": "PHI", "away": "CHC", "game_number": 1,
             "date": "2026-08-01", "kickoff": "2026-08-02T02:10:00Z",
             "live": {"state": "live", "period": "Top 6th",
                      "home_score": 3, "away_score": 1}}
HR_PICK = {"player": "Bryce Harper", "team": "PHI", "opponent": "CHC",
           "market": "home_runs", "market_label": "Home Runs"}
HR_BET = {"player": "Bryce Harper", "market": "home_runs", "side": "OVER",
          "line": 0.5, "odds": 400, "stake_units": 0.19}


# --- the mapping gap --------------------------------------------------------
def test_a_long_shot_maps_to_its_game_instead_of_reporting_unmapped():
    rows = assemble_live_picks([HR_BET], [], [LIVE_GAME], {}, [HR_PICK])
    assert len(rows) == 1
    assert rows[0]["status"] != "unmapped", \
        "the long-shot board was not consulted, so the bet found no game"
    assert rows[0]["phase"] == "live"
    assert rows[0]["game"]["home"] == "PHI"


def test_without_the_long_shot_board_it_still_degrades_to_unmapped():
    """A negative control: if this passed either way the test above would
    be measuring nothing."""
    rows = assemble_live_picks([HR_BET], [], [LIVE_GAME], {})
    assert rows[0]["status"] == "unmapped"


def test_a_mapped_long_shot_tracks_the_live_home_run_count():
    progress = {"bryce harper": {"home_runs": 1.0}}
    rows = assemble_live_picks([HR_BET], [], [LIVE_GAME], progress, [HR_PICK])
    assert rows[0]["current"] == 1.0
    assert rows[0]["status"] == "cleared", \
        "over 0.5 home runs with one already hit is locked, not 'tracking'"


def test_the_main_board_wins_a_collision():
    """If the same player+market is on both boards, the main row carries the
    staked bet's context — team, opponent, doubleheader leg."""
    main = dict(HR_PICK, team="XXX")
    rows = assemble_live_picks([HR_BET], [main], [LIVE_GAME], {}, [HR_PICK])
    # main's team is bogus, so it cannot map — which proves main was tried.
    assert rows[0]["status"] == "unmapped"


def test_the_long_shot_board_is_optional():
    """Every other caller passes four arguments and must keep working."""
    rows = assemble_live_picks([], [], [LIVE_GAME], {})
    assert rows == []


# --- the query scope --------------------------------------------------------
def _tracker_block():
    """The whole try: body, not a fixed slice — a character budget silently
    stops covering the code it was written to check the moment anything
    above it grows."""
    i = BUILD.index("from engine.livepicks import assemble_live_picks")
    j = BUILD.index('result["live_picks_error"]', i)
    return BUILD[i:j]


def test_the_query_no_longer_excludes_the_home_run_board():
    b = _tracker_block()
    assert "category IN ('main','longshot')" in b
    assert "AND category='main'" not in b, \
        "the Live tab still cannot see a single long-shot bet"


def test_the_watchlist_stays_out():
    """'longshot_watch' is a calibration sample — every real-priced homer on
    the slate, often 100+ names. Tracking those live would bury the three
    bets that were actually placed."""
    b = _tracker_block()
    assert "longshot_watch" not in b


def test_bets_filed_under_a_neighbouring_date_are_still_considered():
    b = _tracker_block()
    assert "_shift_day(args.date, d) for d in (-1, 1)" in b
    assert "date IN (?,?)" in b


def test_a_neighbour_day_bet_only_shows_if_it_lands_on_tonights_card():
    """Widening the window without this turns the tracker into a list of
    every stale open bet in the journal."""
    b = _tracker_block()
    assert 'if r["status"] != "unmapped"' in b


def test_todays_own_bets_are_never_dropped_mapped_or_not():
    """The section's count has to reconcile with the Record's — a bet we
    cannot place is a fact worth showing, not hiding."""
    b = _tracker_block()
    first = b.index("rows = assemble_live_picks(open_today")
    second = b.index("rows += [r for r in assemble_live_picks(open_near")
    assert first < second
    assert 'if r["status"]' not in b[first:second], \
        "today's rows are being filtered too"


def test_the_leftover_count_is_everything_not_shown():
    """It used to be 'open bets whose date is not today', which double-counts
    the moment a neighbouring day's bet gets shown."""
    b = _tracker_block()
    # EDGE ROWS ONLY on the shown side since 2026-09-05, when the tracker
    # began selecting category='likely' too. `_all_open` counts edge bets
    # alone, so subtracting every shown row would understate "open on
    # other boards" by exactly the number of likelihood rows on the card.
    assert "_all_open - _edge_shown" in b
    assert 'r.get("category") != "likely"' in b
    assert "_all_open - len(rows)" not in b, "the likely rows are subtracted again"
    assert "AND date != ?" not in b


def test_dates_are_shifted_with_date_arithmetic_and_not_string_math():
    assert "datetime.date.fromisoformat" in BUILD
    from mlb_build import _shift_day
    assert _shift_day("2026-08-01", -1) == "2026-07-31"
    assert _shift_day("2026-08-31", 1) == "2026-09-01"     # month boundary
    assert _shift_day("2026-12-31", 1) == "2027-01-01"     # year boundary


# --- the frontend -----------------------------------------------------------
def test_a_tracked_long_shot_is_not_labelled_off_the_board():
    """`onBoard` was built from the main board only, so every home-run bet
    was marked 'no longer recommended' while sitting, recommended, on the
    Long Shots page two tabs over."""
    i = APP.index("const onBoard = new Set();")
    block = APP[i:i + 900]
    assert "state.data.long_shots" in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
