"""The settle pass's prep says its steps, and the hoops relabel reads its names off the kept lists (step AHH,
25 November 2026).

Ethan: "Ok keep going and work more on these issues as they are not fixed". On the live box a settle pass ran 812.8 s,
576.6 s of it in "prep", and nothing said which of prep's steps took them; the box has one core, and every page shares
it with the pass. Each step's seconds now ride the heartbeat (`prep_parts`). One step was plainly wasteful: the hoops
relabel read every stored NBA and WNBA name off the logs on every pass. It reads nothing with no open hoops bet, and
otherwise reads the names off db.folded_names, kept on disk and grown by the rows added since.

Offline. Run directly: `python3 tests/test_the_settle_passes_prep_says_its_steps.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, ledger  # noqa: E402


class _Seen:
    def __init__(self, conn):
        self.conn, self.sql = conn, []

    def execute(self, sql, args=()):
        self.sql.append(sql)
        return self.conn.execute(sql, args)


def _journal(rows):
    lconn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    for sport, player in rows:
        lconn.execute("INSERT INTO bets (sport,date,player,market,side,line,odds,grade,stake_units,stake_dollars,"
                      "status,category) VALUES (?,?,?,'pts','OVER',18.5,-110,'Play',0.5,5.0,'open','main')",
                      (sport, "2026-07-31", player))
    lconn.commit()
    return lconn


def _history():
    hconn = db.connect(os.path.join(tempfile.mkdtemp(), "history.db"))
    db.upsert_player_logs(hconn, [
        {"sport": "wnba", "season": 2026, "period": "2026-07-31", "game_id": "gW", "player": "Caitlin Clark",
         "team": "IND", "opponent": "NYL", "position": "G", "home": 1, "market": "pts", "value": 24.0},
        {"sport": "nba", "season": 2026, "period": "2026-11-20", "game_id": "gN", "player": "Jalen Brunson",
         "team": "NYK", "opponent": "BOS", "position": "G", "home": 1, "market": "pts", "value": 31.0}])
    return hconn


def test_no_open_hoops_bet_reads_no_logs():
    lconn = _journal([("nfl", "Amon-Ra St. Brown")])
    seen = _Seen(_history())
    assert ledger.relabel_cross_league(lconn, seen) == 0
    assert not any("player_game_logs" in s for s in seen.sql), seen.sql


def test_the_names_come_off_the_kept_lists_and_grow_by_the_rows_since():
    hconn = _history()
    lconn = _journal([("nba", "Caitlin Clark")])
    first = _Seen(hconn)
    assert ledger.relabel_cross_league(lconn, first) == 1, "a WNBA bet filed under the NBA is re-filed, as before"
    db.upsert_player_logs(hconn, [
        {"sport": "wnba", "season": 2026, "period": "2026-08-02", "game_id": "gW2", "player": "Sophie Cunningham",
         "team": "IND", "opponent": "LVA", "position": "G", "home": 0, "market": "pts", "value": 12.0}])
    lconn2 = _journal([("nba", "Sophie Cunningham"), ("nba", "Jalen Brunson")])
    again = _Seen(hconn)
    assert ledger.relabel_cross_league(lconn2, again) == 1, "a name in the rows added since is in the list"
    whole = [s for s in again.sql if "SELECT DISTINCT player FROM player_game_logs WHERE" in s]
    since = [s for s in again.sql if "rowid > ?" in s]
    assert not whole and since, ("the second pass reads the rows since, not every name", again.sql)
    moved = {r["player"]: r["sport"] for r in lconn2.execute("SELECT player, sport FROM bets")}
    assert moved == {"Sophie Cunningham": "wnba", "Jalen Brunson": "nba"}, moved


def test_the_pass_says_each_prep_steps_seconds():
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    body = src[src.index('prep_parts = phases.setdefault("prep_parts", {})'):src.index("res = ingest_for_open_bets(")]
    for name in ("ledger_connect", "history_connect", "game_days", "open_days", "relabel_hoops", "refile_football",
                 "longshots"):
        assert f'part("{name}", t0)' in body, name
    assert body.index('part("open_days", t0)') < body.index('lap("prep")'), "inside the phase it parts"


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
