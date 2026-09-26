"""lineupwatch: rebuild when the cards post, and not otherwise.

§5 holds every MLB hitter until its lineup is posted, so an afternoon board
carries one leg per game and no same-game parlay can exist on it. The fix
is a rebuild once the cards land — and the whole risk of automating that is
the opposite failure: a watcher that rebuilds on every poll and drains the
day's Odds credits to learn what one build at the end would have said.

So the decision is a pure function and these test it directly, with no
network and no clock. The API half is a thin wrapper by design; what has
to be right is when it says yes.

Run directly: `python3 tests/test_lineupwatch.py`
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lineupwatch as lw                                      # noqa: E402

TODAY = "2026-08-05"


def _decide(live=6, total=13, built=0, built_date=TODAY, builds=0,
            gap=None, **kw):
    return lw.decide(live, total, built, built_date, TODAY, builds, gap, **kw)


# --- when it should build ----------------------------------------------------
def test_new_cards_since_the_build_trigger_a_rebuild():
    go, why = _decide(live=6, built=0)
    assert go
    assert "6 lineup(s) posted since" in why


def test_a_board_from_another_day_is_rebuilt_regardless_of_lineups():
    """A stale slate is a different failure and must not wait on cards."""
    go, why = _decide(live=0, total=13, built=0, built_date="2026-08-04")
    assert go
    assert "stale slate" in why


# --- when it must not --------------------------------------------------------
def test_no_new_cards_means_no_rebuild():
    """The trigger is cards posted SINCE the build, never an absolute count —
    otherwise every poll after the first rebuilds forever."""
    go, why = _decide(live=6, built=6)
    assert not go
    assert "nothing new to build on" in why
    assert not _decide(live=3, built=6)[0], "went backwards and still built"


def test_an_empty_schedule_is_not_a_reason_to_build():
    go, why = _decide(live=0, total=0, built=0)
    assert not go
    assert "no MLB games" in why


def test_the_gap_floor_holds_a_second_rebuild_back():
    """Cards trickle out over an hour. Rebuilding on each one spends a day's
    credits to reach the same board."""
    go, why = _decide(live=9, built=6, gap=8, min_gap=25)
    assert not go
    assert "8m ago" in why and "floor is 25m" in why
    # Past the floor, the same state builds.
    assert _decide(live=9, built=6, gap=30, min_gap=25)[0]


def test_the_build_ceiling_stops_a_pathological_night():
    go, why = _decide(live=12, built=6, builds=3, max_builds=3)
    assert not go
    assert "already rebuilt 3 time(s)" in why
    # The ceiling outranks the gap: no amount of waiting re-opens it.
    assert not _decide(live=12, built=6, builds=3, gap=999, max_builds=3)[0]


def test_the_ceiling_is_checked_before_the_gap():
    """Otherwise a run at its ceiling reports a wait that will never end."""
    _, why = _decide(live=12, built=6, builds=5, gap=1, max_builds=3)
    assert "already rebuilt" in why and "floor is" not in why


# --- reading the board -------------------------------------------------------
def _board(**over):
    d = {"date": TODAY,
         "games": [{"lineups_confirmed": True}, {"lineups_confirmed": False}],
         "parlays": {"lineups_posted": 1, "games_total": 2}}
    d.update(over)
    p = Path(tempfile.mkdtemp()) / "mlb.json"
    p.write_text(json.dumps(d))
    return p


def test_the_board_census_is_read_from_the_parlay_screen():
    assert lw.posted_in_build(_board()) == (1, 2, TODAY)


def test_a_board_predating_the_census_is_counted_from_its_games():
    """An older build has no lineups_posted field. Falling back to the games
    array keeps the watcher working across the upgrade instead of rebuilding
    on every poll because it read zero."""
    p = _board(parlays={"tickets": []})
    assert lw.posted_in_build(p) == (1, 2, TODAY)


def test_a_missing_or_unreadable_board_reads_as_nothing_built():
    tmp = Path(tempfile.mkdtemp())
    assert lw.posted_in_build(tmp / "nope.json") == (0, 0, "")
    junk = tmp / "junk.json"
    junk.write_text("{not json")
    assert lw.posted_in_build(junk) == (0, 0, "")
    # …and "nothing built" plus games on the slate is a build.
    assert _decide(live=1, total=2, built=0, built_date="")[0]


# --- the stop condition ------------------------------------------------------
def test_settled_only_when_every_card_is_out():
    assert lw.settled(13, 13)
    assert lw.settled(14, 13)          # doubleheader arithmetic, not a hang
    assert not lw.settled(12, 13)
    assert not lw.settled(0, 0), "an empty slate is not a settled one"


def test_the_poll_gap_respects_the_boxscore_cache():
    """Polling faster than the cache TTL re-reads one file and learns
    nothing, so the default must not invite it."""
    import inspect

    from engine.mlb.sources import statslogs
    src = inspect.getsource(statslogs.fetch_boxscore)
    assert "ttl=300" in src
    assert lw.EVERY_MIN * 60 >= 300


def test_polling_is_free_and_only_the_rebuild_is_not():
    """The whole design rests on this asymmetry. If the lineup read ever
    starts going through the metered odds feed, the defaults above become
    a way to burn the budget rather than protect it."""
    import inspect

    src = inspect.getsource(lw.posted_live)
    assert "statslogs" in src and "mlbstats" in src
    assert "odds" not in src.lower(), "the lineup poll reached a metered feed"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
