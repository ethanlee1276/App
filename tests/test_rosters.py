"""Active rosters, and trades found without a news feed.

The roster page answers "who is on this team right now" from the players
blob the fantasy layer already fetches — no new source, no new request.

The part worth guarding is what makes it honest rather than merely
present:

* a free agent is not on a roster, and must not appear on one;
* an unavailable player (IR, PUP, suspended) is SHOWN with his status —
  a roster with the injuries quietly filtered reads as a healthy team;
* depth order is the coaching staff's opinion, so an unranked player
  sorts after the ranked ones rather than to the top, where he would read
  as the starter;
* and transactions come from diffing our own daily snapshots, which means
  a player appearing for the FIRST time is not a signing — we can't tell
  that from the feed adding someone it didn't carry yesterday.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import rosters


def _p(full, team, pos="WR", order=None, status="Active", exp=3, age=25):
    return {"full_name": full, "team": team, "position": pos,
            "depth_chart_order": order, "status": status,
            "years_exp": exp, "age": age}


def _blob(*players):
    return {str(i): p for i, p in enumerate(players)}


def test_a_free_agent_is_on_no_roster():
    out = rosters.build_rosters(_blob(_p("Signed Guy", "SF"),
                                      _p("Free Agent", None),
                                      _p("Also Free", "")))
    assert out["player_count"] == 1
    assert list(out["teams"]) == ["SF"]


def test_the_injured_are_listed_not_hidden():
    out = rosters.build_rosters(_blob(
        _p("Healthy", "SF", order=1),
        _p("Hurt", "SF", order=2, status="Injured Reserve")))
    sf = out["teams"]["SF"]
    assert sf["count"] == 2, "an IR player is still on the roster"
    assert sf["unavailable"] == 1
    names = [p["player"] for p in sf["players"]]
    assert "Hurt" in names
    hurt = next(p for p in sf["players"] if p["player"] == "Hurt")
    assert hurt["unavailable"] and hurt["status"] == "Injured Reserve"
    # …and sorted below the available players at his position.
    assert names.index("Healthy") < names.index("Hurt")


def test_unranked_players_sort_below_ranked_ones():
    out = rosters.build_rosters(_blob(
        _p("No Slot", "SF", "QB"),
        _p("Starter", "SF", "QB", order=1),
        _p("Backup", "SF", "QB", order=2)))
    assert [p["player"] for p in out["teams"]["SF"]["players"]] == \
        ["Starter", "Backup", "No Slot"], "an unlisted slot read as QB1"


def test_positions_group_in_depth_chart_order():
    out = rosters.build_rosters(_blob(
        _p("Kicker", "SF", "K", order=1),
        _p("Corner", "SF", "CB", order=1),
        _p("Quarterback", "SF", "QB", order=1)))
    assert [p["player"] for p in out["teams"]["SF"]["players"]] == \
        ["Quarterback", "Corner", "Kicker"]
    assert rosters.group_of("QB") == "Offense"
    assert rosters.group_of("CB") == "Defense"
    assert rosters.group_of("K") == "Special teams"


def test_rookies_are_counted():
    out = rosters.build_rosters(_blob(_p("Rook", "SF", exp=0),
                                      _p("Vet", "SF", exp=8)))
    assert out["teams"]["SF"]["rookies"] == 1
    rook = next(p for p in out["teams"]["SF"]["players"] if p["player"] == "Rook")
    assert rook["rookie"] and rook["years_exp"] == 0


def test_no_feed_is_not_an_empty_league():
    assert rosters.build_rosters(None) == {"teams": {}, "team_count": 0,
                                           "player_count": 0}
    assert rosters.build_rosters({}) == {"teams": {}, "team_count": 0,
                                         "player_count": 0}


# --- transactions -----------------------------------------------------------
def test_a_trade_is_the_day_the_answer_changed():
    store = {"2026-07-30": {"Deebo Samuel Sr.": "WAS", "Brock Purdy": "SF"},
             "2026-07-31": {"Deebo Samuel Sr.": "SF", "Brock Purdy": "SF"}}
    tx = rosters.transactions(store)
    assert tx["moves"] == [{"player": "Deebo Samuel Sr.", "from": "WAS",
                            "to": "SF", "date": "2026-07-31"}]


def test_a_new_name_is_not_a_signing():
    # He might be a signing; he might be a player the feed didn't carry
    # yesterday. Nothing distinguishes them, so neither is claimed.
    store = {"2026-07-30": {"Old Guy": "SF"},
             "2026-07-31": {"Old Guy": "SF", "New Name": "SF"}}
    assert rosters.transactions(store)["moves"] == []


def test_both_legs_of_a_double_move_are_kept():
    store = {"2026-07-29": {"Journeyman": "SF"},
             "2026-07-30": {"Journeyman": "KC"},
             "2026-07-31": {"Journeyman": "BUF"}}
    moves = rosters.transactions(store)["moves"]
    assert len(moves) == 2, "only the net move survived"
    assert [(m["from"], m["to"]) for m in moves] == [("KC", "BUF"), ("SF", "KC")]


def test_one_snapshot_has_nothing_to_diff():
    assert rosters.transactions({"2026-07-31": {"A": "SF"}})["moves"] == []
    assert rosters.transactions({})["moves"] == []


def test_the_window_limits_how_far_back_it_looks():
    store = {f"2026-07-{d:02d}": {"Guy": "SF" if d < 20 else "KC"}
             for d in range(1, 32)}
    assert rosters.transactions(store, days=3)["moves"] == [], \
        "a move outside the window was reported as recent"
    assert len(rosters.transactions(store, days=30)["moves"]) == 1


def test_the_snapshot_covers_more_than_fantasy_positions():
    # The camp watch only snapshots fantasy positions with a depth slot. A
    # trade is a trade whether or not the player is on somebody's board.
    snap = rosters.team_snapshot(_blob(_p("Left Tackle", "SF", "OT"),
                                       _p("Long Snapper", "SF", "LS")))
    assert snap == {"Left Tackle": "SF", "Long Snapper": "SF"}


def test_history_survives_the_cache_pruner():
    # The pruner works from an ALLOWLIST of prefixes; this file matches
    # none of them, which is what keeps accumulated history alive.
    from engine.maintenance import PRUNABLE_CACHE_PREFIXES
    assert not rosters.SNAPSHOT_FILE.startswith(PRUNABLE_CACHE_PREFIXES)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
