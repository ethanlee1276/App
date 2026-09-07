"""Tests for the offseason layer (synthetic schedule + Sleeper fixtures,
plus a smoke pass over the real cached schedule when present)."""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import offseason


def _game(season, gameday, away, home, away_coach="", home_coach="",
          home_score="", away_qb="", home_qb=""):
    return {"season": str(season), "gameday": gameday, "week": "1",
            "away_team": away, "home_team": home,
            "away_coach": away_coach, "home_coach": home_coach,
            "home_score": home_score,
            "away_qb_name": away_qb, "home_qb_name": home_qb}


def _sched():
    """2025 played (KC coached by Old Guy, PIT by Interim Man after a
    firing), 2026 upcoming (KC has New Guy, PIT keeps Interim Man)."""
    return [
        _game(2025, "2025-09-07", "KC", "PIT", "Old Guy", "Fired Man",
              home_score="20", away_qb="Kaycee Starter", home_qb="Steel QB"),
        _game(2025, "2025-12-28", "PIT", "KC", "Interim Man", "Old Guy",
              home_score="24", away_qb="Steel QB", home_qb="Kaycee Starter"),
        _game(2026, "2026-09-13", "KC", "PIT", "New Guy", "Interim Man"),
    ]


def _blob():
    return {
        "1": {"full_name": "Kaycee Starter", "team": "KC", "position": "QB",
              "years_exp": 8, "depth_chart_order": 1, "active": True,
              "status": "Active"},
        # Pittsburgh signed a new QB1; last year's starter is now a backup.
        "2": {"full_name": "Shiny Newcomer", "team": "PIT", "position": "QB",
              "years_exp": 5, "depth_chart_order": 1, "active": True,
              "status": "Active"},
        "3": {"full_name": "Steel QB", "team": "PIT", "position": "QB",
              "years_exp": 6, "depth_chart_order": 2, "active": True,
              "status": "Active"},
        # A WR who changed teams since the stats were recorded.
        "4": {"full_name": "Moved Receiver", "team": "PIT", "position": "WR",
              "years_exp": 4, "depth_chart_order": 1, "active": True,
              "status": "Active"},
        # A rookie with a real depth-chart slot, and one without a team
        # (undrafted, unsigned) who must not appear.
        "5": {"full_name": "Fresh Rookie", "team": "KC", "position": "RB",
              "years_exp": 0, "depth_chart_order": 2, "active": True,
              "status": "Active"},
        "6": {"full_name": "Campless Rookie", "team": None, "position": "WR",
              "years_exp": 0, "depth_chart_order": None, "active": True,
              "status": "Active"},
        # Sleeper's LAR spelling must canonicalize to nflverse's LA.
        "7": {"full_name": "Rams Guy", "team": "LAR", "position": "TE",
              "years_exp": 3, "depth_chart_order": 1, "active": True,
              "status": "Active"},
    }


def test_seasons_in_finds_completed_and_upcoming():
    last, upcoming = offseason.seasons_in(_sched())
    assert (last, upcoming) == (2025, 2026)


def test_coach_changes_diff_final_2025_vs_2026():
    """KC changed (Old Guy -> New Guy). PIT did NOT: the baseline is the
    coach who FINISHED 2025 — the interim — so keeping him is no change,
    and the fired man never produces a false flag."""
    changes = offseason.coach_changes(_sched())
    assert changes == [{"team": "KC", "before": "Old Guy", "now": "New Guy"}]


def test_qb_changes_cross_schedule_with_depth_chart():
    idx = offseason.index_players(_blob())
    changes = offseason.qb_changes(_sched(), idx)
    assert changes == [{"team": "PIT", "before": "Steel QB",
                        "now": "Shiny Newcomer"}]


def test_rookie_board_needs_a_team_and_orders_by_depth():
    rookies = offseason.rookie_board(_blob())
    names = [r["player"] for r in rookies]
    assert "Fresh Rookie" in names
    assert "Campless Rookie" not in names


def test_apply_current_rosters_moves_team_and_keeps_projection():
    kit = {"board": [{"player": "Moved Receiver", "team": "KC",
                      "position": "WR", "proj": 14.0}],
           "tiers": {}, "sleepers": []}
    idx = offseason.index_players(_blob())
    moves = offseason.apply_current_rosters(kit, idx)
    row = kit["board"][0]
    assert moves == [{"player": "Moved Receiver", "position": "WR",
                      "from": "KC", "to": "PIT"}]
    assert row["team"] == "PIT" and row["moved_from"] == "KC"
    # The projection must be untouched: we know he moved, we don't know
    # what the new offense does to his volume, and inventing it is worse
    # than flagging it.
    assert row["proj"] == 14.0


def test_team_alias_canonicalizes_sleeper_spellings():
    idx = offseason.index_players(_blob())
    rec = offseason._lookup(idx, "Rams Guy", "TE")
    assert rec["team"] == "LA"


def test_short_key_collisions_do_not_cross_players():
    """A.J. Brown and Amon-Ra St. Brown both collapse to ("a", "brown")
    and both play WR — the first live run reported Amon-Ra following
    A.J. to New England. Full names must win before the short key is
    ever consulted."""
    blob = {
        "1": {"full_name": "A.J. Brown", "team": "NE", "position": "WR",
              "years_exp": 7, "depth_chart_order": 1, "active": True,
              "status": "Active"},
        "2": {"full_name": "Amon-Ra St. Brown", "team": "DET", "position": "WR",
              "years_exp": 5, "depth_chart_order": 1, "active": True,
              "status": "Active"},
    }
    idx = offseason.index_players(blob)
    assert offseason._lookup(idx, "Amon-Ra St. Brown", "WR")["team"] == "DET"
    assert offseason._lookup(idx, "A.J. Brown", "WR")["team"] == "NE"

    kit = {"board": [
        {"player": "Amon-Ra St. Brown", "team": "DET", "position": "WR", "proj": 18.3},
        {"player": "A.J. Brown", "team": "PHI", "position": "WR", "proj": 17.0},
    ], "tiers": {}, "sleepers": []}
    moves = offseason.apply_current_rosters(kit, idx)
    assert moves == [{"player": "A.J. Brown", "position": "WR",
                      "from": "PHI", "to": "NE"}]
    assert kit["board"][0]["team"] == "DET"          # Amon-Ra stays home
    assert "moved_from" not in kit["board"][0]


def test_abbreviated_names_still_match_via_the_short_key():
    """The short key exists for abbreviated feeds — "P. Mahomes" has no
    full-name entry but must still resolve."""
    blob = {"1": {"full_name": "Patrick Mahomes", "team": "KC", "position": "QB",
                  "years_exp": 9, "depth_chart_order": 1, "active": True,
                  "status": "Active"}}
    idx = offseason.index_players(blob)
    assert offseason._lookup(idx, "P. Mahomes", "QB")["team"] == "KC"


def test_build_offseason_without_sleeper_says_so():
    out = offseason.build_offseason(_sched(), None, kit=None)
    assert out["rosters_live"] is False
    assert out["coach_changes"]          # schedule part still works
    assert out["rookies"] == [] and out["moves"] == []


def test_resolve_trending_joins_names_and_canonicalizes():
    """Trending ids join to real names (unknown ids skipped, never shown
    as numbers), Sleeper spellings canonicalize, and teamless players
    read FA instead of a blank."""
    blob = {"4034": {"full_name": "Puka Nacua", "team": "LAR",
                     "position": "WR"},
            "9999": {"first_name": "Cut", "last_name": "Yesterday",
                     "team": None, "position": "RB"}}
    raw = [{"player_id": "4034", "count": 18321},
           {"player_id": "404", "count": 5},          # not in the blob
           {"player_id": "9999", "count": 900}]
    out = offseason.resolve_trending(raw, blob)
    assert out == [
        {"player": "Puka Nacua", "team": "LA", "position": "WR",
         "count": 18321},
        {"player": "Cut Yesterday", "team": "FA", "position": "RB",
         "count": 900}]
    assert offseason.resolve_trending(raw, blob, limit=1) == out[:1]


def test_trending_without_a_players_blob_is_none():
    """No blob = no roster layer: the page must see 'unreachable', never
    an empty list that reads as 'a quiet day'."""
    assert offseason.load_trending("add", None) is None


def test_real_schedule_smoke():
    """Against the actual cached nflverse file when present: parse, find
    the seasons, and demand structurally sane output — every change has
    both names, teams are 2-3 letters, nothing raises."""
    path = Path(__file__).resolve().parents[1] / "data" / "cache" / "games.csv"
    if not path.exists():
        print("      (no cached games.csv — smoke skipped)")
        return
    import csv
    rows = list(csv.DictReader(open(path)))
    last, upcoming = offseason.seasons_in(rows)
    assert last is not None
    changes = offseason.coach_changes(rows)
    for c in changes:
        assert c["before"] and c["now"] and 2 <= len(c["team"]) <= 3
    # A league where NOBODY changed coaches has never happened; if the
    # data says so, the diff is broken, not the league.
    if upcoming is not None:
        assert changes, "upcoming season present but zero coach changes found"


def test_stamp_reaches_every_board_with_one_shared_moves_list():
    """Trades must show on the usage and buy/sell boards too, not just the
    draft kit — and a player on several boards is reported as ONE move."""
    idx = offseason.index_players(_blob())
    usage = [{"player": "Moved Receiver", "position": "WR", "team": "KC",
              "fp_pg": 14.2},
             {"player": "Kaycee Starter", "position": "QB", "team": "KC"}]
    buy_low = [{"player": "Moved Receiver", "position": "WR", "team": "KC"}]
    moves, seen = [], set()
    offseason.stamp_current_teams(usage, idx, moves=moves, seen=seen)
    offseason.stamp_current_teams(buy_low, idx, moves=moves, seen=seen)
    assert usage[0]["team"] == "PIT" and usage[0]["moved_from"] == "KC"
    assert buy_low[0]["team"] == "PIT"
    assert moves == [{"player": "Moved Receiver", "position": "WR",
                      "from": "KC", "to": "PIT"}]
    assert usage[0]["fp_pg"] == 14.2          # projection never re-modeled
    assert "moved_from" not in usage[1]       # unmoved player untouched


def test_free_agents_get_flagged_not_ghost_teams():
    """A cut player keeps his last known team but wears the flag — showing
    him teamless would erase him; showing him unflagged would lie."""
    blob = {"9": {"full_name": "Cut Veteran", "team": None, "position": "WR",
                  "years_exp": 9, "depth_chart_order": None, "active": True,
                  "status": ""}}
    idx = offseason.index_players(blob)
    rows = [{"player": "Cut Veteran", "position": "WR", "team": "DAL"}]
    assert offseason.stamp_current_teams(rows, idx) == []
    assert rows[0]["roster_flag"] == "free agent" and rows[0]["team"] == "DAL"


# Runner at the TRUE END — a test defined after it never runs.
if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
