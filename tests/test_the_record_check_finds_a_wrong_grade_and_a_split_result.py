"""recordcheck.py: the Record page's numbers, checked read-only on the box.

Ethan, 2026-09-28: the Most Likely section's Spread row read 2/2 while Pick
of the Day listed a CAR spread lost — "make sure all the numbers are
correct". The check re-derives every grade on an in-memory copy (the
settler's own repair pass), finds a bet carrying two results in two
sections, lists every game-line bet by section, and recounts each
section. Fixture ledger and history in a temp directory — never the box's.

Run directly: `python3 tests/test_the_record_check_finds_a_wrong_grade_and_a_split_result.py`
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import recordcheck as RC                                        # noqa: E402
from engine import db, ledger                                   # noqa: E402


def _fixtures():
    tmp = Path(tempfile.mkdtemp())
    lpath, hpath = tmp / "ledger.db", tmp / "history.db"
    conn = ledger.connect(lpath)
    rows = [
        # Pick of the Day: CAR +2.5 (stored negated), CAR lost by 7 — graded lost, right.
        ("potd", "2026-W03", "2026-09-20", "CAR", "spread", "OVER", -2.5, -102, "lost", -7.0, 1.0),
        # Most Likely: BUF -4.5 won by 10 — right.
        ("likely", "2026-W02", "2026-09-14", "BUF", "spread", "OVER", 4.5, -104, "won", 10.0, 0.1),
        # Most Likely: HOU moneyline graded WON though HOU lost — the wrong grade to find.
        ("likely", "2026-W02", "2026-09-14", "HOU", "moneyline", "OVER", 0.5, -136, "won", 1.0, 0.1),
        # The same BUF spread in Pick of the Day, graded LOST — a split result.
        ("potd", "2026-W02", "2026-09-14", "BUF", "spread", "OVER", 4.5, -104, "lost", 10.0, 1.0),
    ]
    for cat, date, day, player, market, side, line, odds, status, actual, stake in rows:
        pnl = stake * (100 / abs(odds)) if status == "won" else -stake
        conn.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, hit_prob, "
                     "stake_units, stake_dollars, status, actual, pnl_units, category) VALUES "
                     "('t','nfl',?,?,?,?,?,?,?,0.6,?,0,?,?,?,?)",
                     (date, day, player, market, side, line, odds, stake, status, actual, pnl, cat))
    conn.commit()
    conn.close()
    h = db.connect(hpath)
    h.executemany("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, away_score) "
                  "VALUES ('nfl', 2026, ?, ?, ?, ?, ?, ?, ?)",
                  [("003", "CAR@TB", "2026-09-20", "TB", "CAR", 24, 17),
                   ("002", "BUF@MIA", "2026-09-14", "MIA", "BUF", 17, 27),
                   ("002", "HOU@JAX", "2026-09-14", "JAX", "HOU", 20, 13)])
    h.commit()
    h.close()
    return lpath, hpath


def test_the_ledger_is_never_written():
    lpath, hpath = _fixtures()
    before = lpath.read_bytes()
    RC.main(["--db", str(lpath), "--history", str(hpath)])
    assert lpath.read_bytes() == before, "the real ledger is untouched; the repair pass ran on a copy"


def test_the_wrong_grade_the_split_and_the_game_lines_are_found():
    lpath, hpath = _fixtures()
    mem = RC.copy_to_memory(lpath)
    fixes = RC.regrade(mem, RC._ro(hpath))
    hou = [f for f in fixes if f.get("player") == "HOU"]
    assert hou and hou[0]["was"] == "won" and hou[0]["now"] == "lost", fixes
    assert not [f for f in fixes if f.get("player") == "CAR"], "a right grade is left alone"
    split = RC.split_grades(RC.copy_to_memory(lpath), "nfl")
    assert len(split) == 1 and split[0][0][1] == "BUF"
    assert sorted(split[0][1]) == [("likely", "won"), ("potd", "lost")]
    lines = RC.game_lines(RC.copy_to_memory(lpath), "nfl")
    assert {(r["category"], r["player"]) for r in lines} == {("potd", "CAR"), ("likely", "BUF"),
                                                             ("likely", "HOU"), ("potd", "BUF")}


def test_a_result_that_contradicts_its_own_number_is_found():
    """The repair pass audits a grade against NEW numbers; a row graded
    against its own stored number wrongly (BUF won by 10 on −4.5, recorded
    lost) is invisible to it, so the check reads the row against itself."""
    lpath, _ = _fixtures()
    bad = RC.self_contradictions(RC.copy_to_memory(lpath), "nfl")
    assert [(r["category"], r["player"], r["status"], r["want"]) for r in bad] == [("potd", "BUF", "lost", "won")]
    assert RC.expected_status("OVER", -2.5, -7.0) == "lost", "CAR +2.5 lost by 7"
    assert RC.expected_status("OVER", 3.0, 3.0) == "push"
    assert RC.expected_status("UNDER", 45.5, 41.0) == "won"
    assert RC.expected_status("YES", 0.5, 1.0) == "won"
    assert RC.expected_status("OVER", None, 3) is None


def test_the_sections_recount_clean_on_a_consistent_ledger():
    lpath, _ = _fixtures()
    assert RC.recount(RC.copy_to_memory(lpath), "nfl") == [], "the report functions agree with a plain count"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
