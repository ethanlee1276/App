"""The MLB probe says which step stopped when the profit calendar stops
(mlbprobe.journal_report, 2026-10-13).

Ethan, 2026-10-13, on the Record page: "the mlb profit calander isn't
updating, it's stuck on September". The calendar draws settled edge bets,
so the probe prints, for each recent day, the MLB edge bets journaled and
how they stand beside the finals and stat lines on file, then the last
edge bet, the record file's own word, and the last build's lines about its
odds and its journal. Read-only: a missing database is reported, never
created. Everything here runs on throwaway files; nothing reads the box.

    python3 tests/test_the_mlb_probe_reads_the_journal.py
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mlbprobe                                                     # noqa: E402
from engine import db as H                                          # noqa: E402
from engine import ledger as L                                      # noqa: E402


def _files():
    d = Path(tempfile.mkdtemp())
    lc = L.connect(d / "ledger.db")
    for r in (("2026-09-29T20:00:00", "mlb", "2026-09-30", "A", "hits", "UNDER", 0.5, -110, "won", "main", 1.0, 0.9),
              ("2026-09-30T18:00:00", "mlb", "2026-10-01", "B", "hits", "UNDER", 0.5, -110, "open", "main", 1.0, None),
              ("2026-09-30T18:05:00", "mlb", "2026-10-01", "C", "hits", "OVER", 0.5, -110, "open", "paper", 0.6, None),
              ("2026-09-30T18:00:00", "mlb", "2026-10-01", "D", "hits", "OVER", 0.5, -110, "open", "likely", 1.0, None),
              ("2026-09-30T18:00:00", "mlb", "2026-10-01", "E", "hits", "OVER", 0.5, -110, "open", "longshot", 0.2, None),
              ("2026-09-30T18:00:00", "mlb", "2026-10-01", "F", "hits", "OVER", 0.5, -110, "open", "main", 0.0, None),
              ("2026-09-30T18:00:00", "nfl", "2026-10-01", "G", "rec_yds", "OVER", 50.5, -110, "open", "main", 1.0, None)):
        lc.execute("INSERT INTO bets (ts,sport,date,player,market,side,line,odds,status,category,stake_units,pnl_units) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", r)
    lc.commit()
    lc.close()
    hc = H.connect(d / "history.db")
    hc.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score) "
               "VALUES ('mlb', 2026, '2026-10-01', 'NYY@BOS', 'BOS', 'NYY', 3, 2)")
    hc.execute("INSERT INTO games (sport, season, period, game_id, home, away) "
               "VALUES ('mlb', 2026, '2026-10-01', 'LAD@SD', 'SD', 'LAD')")
    hc.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, market, value) "
               "VALUES ('mlb', 2026, '2026-09-30', 'x', 'A', 'NYY', 'hits', 1)")
    hc.commit()
    hc.close()
    (d / "record.json").write_text(json.dumps({
        "generated_at": "2026-10-13T16:12:01",
        "by_sport": {"mlb": {"curve": [{"date": "2026-09-30"}],
                             "edge_state": {"open": 2, "oldest_open": "2026-10-01", "last_placed": "2026-10-01"}}}}))
    (d / "mlb_build.log").write_text(
        "# 2026-10-13T16:10:02 · exit 0 · mlb_build.py 2026-10-13 --cached-odds\n"
        "Live scores: 2 game(s) matched, 1 in progress.\n"
        "Odds API: matched 0 props across 0 games (cached — no API spend) (quota remaining 88000).\n"
        "Done.\n")
    return d


def _report(d, today="2026-10-02", days=4, **paths):
    return mlbprobe.journal_report(paths.get("ledger", d / "ledger.db"), paths.get("history", d / "history.db"),
                                   paths.get("record", d / "record.json"), paths.get("log", d / "mlb_build.log"),
                                   today, days=days)


def test_each_day_says_what_was_journaled_and_what_there_is_to_settle_it():
    lines = _report(_files())
    assert lines[0].startswith("JOURNAL  MLB, 2026-09-29 to 2026-10-02. edge = main + paper + likely_live with a stake")
    assert lines[1] == "  2026-09-29  nothing journaled · finals 0/0 · stat lines 0"
    assert lines[2] == ("  2026-09-30  edge   1 (open 0 · won 1 · lost 0 · push 0 · void 0) · unstaked 0 · "
                        "Most Likely 0 · other 0 · finals 0/0 · stat lines 1")
    # B and C are the edge bets; F is unstaked, D Most Likely, E another book; G is football.
    assert lines[3] == ("  2026-10-01  edge   2 (open 2 · won 0 · lost 0 · push 0 · void 0) · unstaked 1 · "
                        "Most Likely 1 · other 1 · finals 1/2 · stat lines 0")
    assert lines[4] == "  2026-10-02  nothing journaled · finals 0/0 · stat lines 0"
    assert lines[5] == "JOURNAL  last edge bet: day 2026-10-01, journaled 2026-09-30T18:05:00, paper, open"
    assert lines[6] == "JOURNAL  open edge bets from before today: 2, the oldest from 2026-10-01"


def test_the_record_file_and_the_build_say_their_part():
    lines = _report(_files())
    rec = [ln for ln in lines if ln.startswith("RECORD")]
    assert rec == ["RECORD   record.json written 2026-10-13T16:12:01 · MLB curve's last day 2026-09-30 · "
                   "{'open': 2, 'oldest_open': '2026-10-01', 'last_placed': '2026-10-01'}"], rec
    build = [ln for ln in lines if ln.startswith("BUILD")]
    assert build[0] == "BUILD    # 2026-10-13T16:10:02 · exit 0 · mlb_build.py 2026-10-13 --cached-odds"
    assert any("Odds API: matched 0 props across 0 games" in ln for ln in build), build
    assert not any("Live scores" in ln for ln in build), "only the lines about odds and the journal"
    d = _files()
    (d / "mlb_build.log").write_text("# 2026-10-13T16:10:02 · exit -9 · mlb_build.py 2026-10-13\nLive scores: 2 game(s)\n")
    tail = _report(d)[-1]
    assert tail == "BUILD      no line about odds or the journal: the build stopped before it priced", tail
    assert _report(d, log=d / "missing.log")[-1].startswith("BUILD    no MLB build log:")


def test_it_writes_nothing_and_creates_nothing():
    # SQLite's own -wal and -shm files are left out: any reader of a
    # database in WAL mode keeps its index there, read-only or not, and on
    # the box the running site holds them open already. Everything else,
    # the two databases included, must be exactly as it was.
    d = _files()
    sidecar = ("-wal", "-shm")
    before = {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in d.iterdir() if not p.name.endswith(sidecar)}
    _report(d)
    after = {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in d.iterdir() if not p.name.endswith(sidecar)}
    assert before == after, "a read-only probe touched a file"
    import sqlite3
    with sqlite3.connect(d / "ledger.db") as c:
        assert c.execute("SELECT COUNT(*), SUM(status='open') FROM bets").fetchone() == (7, 6)
    gone = d / "nope.db"
    lines = _report(d, ledger=gone)
    assert lines[0].startswith("JOURNAL  unreadable:") and not gone.exists(), "a missing journal is said, never made"
    assert "journal_report(ROOT / \"data\" / \"ledger.db\"" in (ROOT / "mlbprobe.py").read_text()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
