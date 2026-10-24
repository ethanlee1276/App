"""A bet journalled before `game_day` existed still settles by the no-show rule.

Found 2026-09-25 on the droplet: a week-1 anytime-touchdown bet on Jake
Tonges sat open a fortnight beside a final game. He played 12% of the
snaps and logged no stat, which `_absent_player_verdict` grades — but
only for a bet that knows its calendar day, and week-1 rows were written
before the column was filled (fixed 2026-09-11). The backfill that dates
old rows places them by the player's log; the rule that reads the log
needed the date first. Neither could start. The rule now asks the
backfill's placement itself.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db as hist_db                                 # noqa: E402
from engine import ledger                                        # noqa: E402


def _world(snap):
    conn = ledger.connect(":memory:")
    result = {"sport": "nfl", "date": "2026-W01", "long_shots": [
        {"player": "Jake Tonges", "market": "anytime_td", "odds": 900,
         "book": "FanDuel", "model_prob": 0.12}], "longshot_watch": []}
    assert ledger.log_longshots(conn, result) == 1
    conn.execute("UPDATE bets SET game_day=NULL")        # the week-1 shape
    day = (dt.date.today() - dt.timedelta(days=18)).isoformat()
    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [
        {"sport": "nfl", "season": 2026, "period": "001", "game_id": "SF@SEA",
         "home": "SEA", "away": "SF", "home_score": 17, "away_score": 13,
         "date": day, "spread": 0.0, "total": 44.0, "roof": "", "surface": "",
         "temp": None, "wind": None, "extra": None}])
    logs = [{"sport": "nfl", "season": 2026, "period": "001", "game_id": "SF@SEA",
             "player": p, "team": t, "opponent": o, "position": "WR", "home": h,
             "market": mk, "value": v}
            for p, t, o, h in (("Other SF", "SF", "SEA", 0), ("Other SEA", "SEA", "SF", 1))
            for mk, v in (("anytime_td", 0.0), ("snap_pct", 0.8))]
    if snap is not None:
        logs.append({"sport": "nfl", "season": 2026, "period": "001", "game_id": "SF@SEA",
                     "player": "Jake Tonges", "team": "SF", "opponent": "SEA",
                     "position": "TE", "home": 0, "market": "snap_pct", "value": snap})
    hist_db.upsert_player_logs(hist, logs)
    ledger.settle_from_history(conn, hist, sport="nfl")
    return conn.execute("SELECT status, game_day FROM bets").fetchone()


def test_an_active_player_with_no_stat_is_graded_at_zero():
    got = _world(snap=0.12)
    assert got["status"] == "lost", dict(got)


def test_a_player_with_no_snaps_is_void():
    assert _world(snap=0.0)["status"] == "void"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
