"""A called-off game must not hold a night's picks open forever.

The failure this covers, seen on live data: three finished nights each
reported "results only PARTIALLY ingested (11/12 games final)" and refused
to grade, night after night, no matter how many settle passes ran.

Two independent causes, both here.

1. A postponed game keeps its schedule slot, so the per-date slate ingest
   stores it as a row with no score. That is byte-for-byte what a game
   still in progress looks like, and the settle guard deliberately refuses
   to grade a team-day containing one — otherwise a bet grades against a
   partial line in the 6th inning. So the night waits on a game that is
   never going to be played.

2. The schedule payload was cached for 24 hours even when it was captured
   mid-game. Re-running a settle at 4 AM replayed the 11 PM snapshot and
   saw the same unfinished games, so it could not have graded them even
   if nothing else were wrong.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine.mlb.sources.mlbstats import (parse_abandoned, parse_results,
                                         schedule_is_settled)


def _game(home_id, away_id, abstract, coded, hs=None, as_=None, num=1,
          detailed="Scheduled"):
    return {
        "officialDate": "2026-07-27",
        "gameNumber": num,
        "status": {"abstractGameState": abstract, "codedGameState": coded,
                   "detailedState": detailed},
        "teams": {"home": {"team": {"id": home_id}, "score": hs},
                  "away": {"team": {"id": away_id}, "score": as_}},
        "venue": {"name": "Yankee Stadium"},
    }


FINAL = _game(147, 115, "Final", "F", 5, 3)
LIVE = _game(112, 143, "Live", "I")
PPD = _game(111, 121, "Preview", "D", detailed="Postponed")


def _sched(*games):
    return {"dates": [{"games": list(games)}]}


def test_a_settled_day_is_recognised():
    assert schedule_is_settled(_sched(FINAL))
    # Postponed is settled too — it is not pending, it is not happening.
    assert schedule_is_settled(_sched(FINAL, PPD))


def test_a_day_with_a_live_game_is_not_settled():
    # This is what stops the payload being cached for 24 hours and replayed
    # after the games end.
    assert not schedule_is_settled(_sched(FINAL, LIVE))
    assert not schedule_is_settled(_sched(_game(147, 115, "Preview", "S")))


def test_postponed_games_are_reported_separately():
    got = parse_abandoned(_sched(FINAL, LIVE, PPD))
    assert len(got) == 1, "only the postponed game"
    assert got[0]["state"] == "Postponed"
    assert got[0]["date"] == "2026-07-27"


def test_a_postponed_game_is_never_mistaken_for_a_result():
    # It has no score, and must not reach the history DB as one.
    assert parse_results(_sched(PPD)) == []
    assert len(parse_results(_sched(FINAL, PPD))) == 1


def test_dropping_a_called_off_game_unblocks_the_night():
    conn = db.connect(":memory:")
    common = {"sport": "mlb", "season": 2026, "period": "2026-07-27",
              "spread": 0.0, "total": None, "roof": "open", "surface": "grass",
              "temp": None, "wind": None, "extra": "generic"}
    db.upsert_games(conn, [
        {**common, "game_id": "BOS@NYY", "home": "NYY", "away": "BOS",
         "home_score": 5.0, "away_score": 3.0},
        # The phantom: scheduled, never played, no score.
        {**common, "game_id": "TB@BAL", "home": "BAL", "away": "TB",
         "home_score": None, "away_score": None},
    ])

    def unfinished():
        r = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(home_score IS NOT NULL), 0) "
            "FROM games WHERE period='2026-07-27'").fetchone()
        return int(r[0]) != int(r[1])

    assert unfinished(), "the phantom row is what blocks settling"
    assert db.drop_games(conn, [{"sport": "mlb", "period": "2026-07-27",
                                 "game_id": "TB@BAL"}]) == 1
    assert not unfinished(), "the night should grade once the phantom is gone"


def test_a_played_game_is_never_dropped():
    """The guard that matters: a game in progress looks exactly like a
    postponed one in the DB. Only a scoreless row may ever be removed, so a
    stale schedule read can't delete a real result."""
    conn = db.connect(":memory:")
    db.upsert_games(conn, [{
        "sport": "mlb", "season": 2026, "period": "2026-07-27",
        "game_id": "BOS@NYY", "home": "NYY", "away": "BOS",
        "home_score": 5.0, "away_score": 3.0, "spread": 0.0, "total": None,
        "roof": "open", "surface": "grass", "temp": None, "wind": None,
        "extra": "generic"}])
    assert db.drop_games(conn, [{"sport": "mlb", "period": "2026-07-27",
                                 "game_id": "BOS@NYY"}]) == 0
    assert conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1


def test_dropping_nothing_is_not_an_error():
    conn = db.connect(":memory:")
    assert db.drop_games(conn, []) == 0
    assert db.drop_games(conn, [{"sport": "mlb", "period": "2026-01-01",
                                 "game_id": "NOPE@NOPE"}]) == 0


def test_the_second_leg_of_a_doubleheader_keeps_its_own_id():
    # A postponement is often made up as a doubleheader; if leg 2 were
    # dropped under leg 1's id it would delete the wrong game.
    got = parse_abandoned(_sched(_game(111, 121, "Preview", "D", num=2,
                                       detailed="Postponed")))
    assert got[0]["game_number"] == 2


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
