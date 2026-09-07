"""A trade has to show up on the board, and suffixes must not hide it.

"Deebo Samuel Sr. was traded and the board still shows the old team" has
two candidate causes, and they need separating.

The first is a name join. Stats feeds and roster feeds disagree about
generational suffixes constantly — one has "Deebo Samuel Sr.", the other
"Deebo Samuel" — and a player whose name doesn't join simply never gets
checked for a move. He isn't reported as unmoved; he's reported as
nothing, which is why the absence is so easy to miss.

The second is staleness: the roster feed is cached, and on a failed fetch
the last good copy is served indefinitely. Nothing local can fix a feed
that hasn't published the trade yet, but the cache must not be what's
hiding it — hence a TTL measured in hours and a way to force a pull.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import offseason


def _blob(*players):
    """A Sleeper-shaped players payload."""
    return {str(i): p for i, p in enumerate(players)}


def _p(full, team, pos="WR", active=True):
    return {"full_name": full, "team": team, "position": pos,
            "active": active, "years_exp": 5}


def test_a_suffix_mismatch_still_finds_the_move():
    # Roster feed says plain, stats say "Sr." — the exact shape that hides
    # a trade behind a name that never joined.
    idx = offseason.index_players(_blob(_p("Deebo Samuel", "SF")))
    rows = [{"player": "Deebo Samuel Sr.", "team": "WAS", "position": "WR"}]
    moves = offseason.stamp_current_teams(rows, idx, moves=[], seen=set())
    assert len(moves) == 1, "the suffix hid the trade"
    assert moves[0]["from"] == "WAS" and moves[0]["to"] == "SF"
    # …and the row itself is restamped, so the board shows the new team.
    assert rows[0]["team"] == "SF"
    assert rows[0]["moved_from"] == "WAS"


def test_it_works_in_the_other_direction_too():
    idx = offseason.index_players(_blob(_p("Deebo Samuel Sr.", "SF")))
    rows = [{"player": "Deebo Samuel", "team": "WAS", "position": "WR"}]
    assert len(offseason.stamp_current_teams(rows, idx, moves=[], seen=set())) == 1


def test_every_generational_suffix_is_handled():
    for suffix in ("Jr.", "Sr.", "II", "III", "IV"):
        idx = offseason.index_players(_blob(_p(f"Test Player {suffix}", "SF")))
        rows = [{"player": "Test Player", "team": "WAS", "position": "WR"}]
        moves = offseason.stamp_current_teams(rows, idx, moves=[], seen=set())
        assert len(moves) == 1, f"{suffix} broke the join"


def test_a_player_who_did_not_move_is_not_reported():
    idx = offseason.index_players(_blob(_p("Deebo Samuel", "SF")))
    rows = [{"player": "Deebo Samuel Sr.", "team": "SF", "position": "WR"}]
    assert offseason.stamp_current_teams(rows, idx, moves=[], seen=set()) == []


def test_position_disambiguates_a_shared_name():
    # The short-key trap this module already documents: two players who
    # collapse to the same key must not be mistaken for one another.
    idx = offseason.index_players(
        _blob(_p("A.J. Brown", "NE", "WR"), _p("Amon-Ra St. Brown", "DET", "WR")))
    rows = [{"player": "Amon-Ra St. Brown", "team": "DET", "position": "WR"}]
    assert offseason.stamp_current_teams(rows, idx, moves=[], seen=set()) == [], \
        "Amon-Ra was reported as following A.J. to New England"


def test_a_missing_player_is_skipped_not_guessed():
    idx = offseason.index_players(_blob(_p("Someone Else", "SF")))
    rows = [{"player": "Deebo Samuel Sr.", "team": "WAS", "position": "WR"}]
    assert offseason.stamp_current_teams(rows, idx, moves=[], seen=set()) == []
    assert rows[0]["team"] == "WAS", "an unmatched name must not be restamped"


def test_a_free_agent_is_flagged_rather_than_moved():
    idx = offseason.index_players(_blob(_p("Deebo Samuel", "")))
    rows = [{"player": "Deebo Samuel", "team": "WAS", "position": "WR"}]
    assert offseason.stamp_current_teams(rows, idx, moves=[], seen=set()) == []
    assert rows[0]["roster_flag"] == "free agent"


def test_the_roster_cache_cannot_hide_a_trade_for_a_day():
    # Trades break rosters on news, not on a schedule. A day-long cache
    # meant the page could show yesterday's teams with nothing saying so.
    assert offseason.ROSTER_TTL_S <= 6 * 3600
    import inspect
    sig = inspect.signature(offseason.load_sleeper_players)
    assert sig.parameters["max_age_s"].default == offseason.ROSTER_TTL_S


def test_there_is_a_way_to_force_a_pull():
    with open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "launch.py"), encoding="utf-8") as fh:
        src = fh.read()
    assert '"--refresh-rosters" in argv' in src
    fn = src[src.index("def refresh_rosters("):src.index("def odds_doctor(")]
    assert "unlink()" in fn, "forcing a pull means deleting the cached copy"
    assert "max_age_s=0" in fn, "…and asking for a zero-age read"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
