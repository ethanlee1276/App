"""A started college game keeps the line it had before kickoff (2026-11-14).

The picks audit Ethan ran that afternoon read, among college's reads:
"The lines expect SMU to score only about 7 (+42.5 at home, total 56.5)",
"RUTG ... only about 0 (+31.5 at home, total 31.5)", "VAN ... about 8 (+18.5
at home, total 34.5)". Each was a game under way: the one request college
buys quotes a started game in play, and that number was written as the
game's line, so the reads, the report and the scorer chances read a blowout
in progress as the pregame line. A started game is now left unpriced by the
pull and given back its last pregame line off the line tape.

    python3 tests/test_a_started_college_game_keeps_its_pregame_line.py
"""
import datetime as dt
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cfb_build as B                                   # noqa: E402
from engine import db                                   # noqa: E402
from engine import lineledger as LL                     # noqa: E402


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:00Z")


def test_a_game_is_under_way_by_its_state_or_its_start():
    past = _iso(dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1))
    future = _iso(dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3))
    assert B._under_way({}, {"state": "live"}) and B._under_way({}, {"state": "final"})
    assert B._under_way({"commence_time": past}, {"state": "scheduled"})
    assert not B._under_way({"commence_time": future}, {"state": "scheduled"})
    assert not B._under_way({}, {"state": "scheduled", "kickoff": "half past"})


def test_a_started_game_reads_its_last_line_before_kickoff():
    kick = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0) - dt.timedelta(hours=2)
    date = kick.strftime("%Y-%m-%d")
    conn = sqlite3.connect(":memory:")
    conn.executescript(db.SCHEMA)
    ev = f"{date}-WAKE@SMU"
    tape = []
    for hours, sp, tot in ((-3, 6.5, 57.5), (-1, 7.5, 56.5), (1, 39.5, 69.5)):   # the last one in play
        t = _iso(kick + dt.timedelta(hours=hours))
        tape.append(("cfb", t, ev, "SMU", "WAKE", "SMU", "spread", LL.BEST_BOOK, sp, -110, -110, None))
        tape.append(("cfb", t, ev, "SMU", "WAKE", LL.TOTAL_KEY, "total", LL.BEST_BOOK, tot, -110, -110, None))
    conn.executemany("INSERT OR REPLACE INTO odds_history VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", tape)
    smu = {"home": "SMU", "away": "WAKE", "date": date, "kickoff": _iso(kick), "state": "live",
           "spread": 39.5, "total": 69.5}
    never = {"home": "VAN", "away": "ALA", "date": date, "kickoff": _iso(kick), "state": "live",
             "spread": 18.5, "total": 34.5}
    later = {"home": "ND", "away": "BC", "date": date, "state": "scheduled",
             "kickoff": _iso(kick + dt.timedelta(hours=8)), "spread": -29.5, "total": 51.5}
    assert B.lines_at_kickoff([smu, never, later], conn=conn) == 1
    assert (smu["spread"], smu["total"]) == (7.5, 56.5), "the last line before kickoff, never the in-play one"
    assert (never["spread"], never["total"]) == (None, None), "no pregame line: nothing, not the live number"
    assert (later["spread"], later["total"]) == (-29.5, 51.5), "a game still to play keeps this build's line"


def test_the_pull_leaves_a_started_game_unpriced_and_says_so():
    src = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    i = src.index("def attach_odds(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "if _under_way(ev, game, now):" in body and "under way, kept at their pregame line" in body
    assert '_kept = lines_at_kickoff(out["games"])' in src
    # Not `pregame_lines`: the football and baseball builds may not carry
    # "game_lines(" at all (test_basketball_and_hockey_name_their_pick_from_
    # game_lines, the boards' own bars), and the old name held it.
    assert "game_lines(" not in src
    assert time.time() > 0


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
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
