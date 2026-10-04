"""A push is not a missing row, and the record check said it was.

Ethan, 2026-09-19, running `python3 homecheck.py record` on the droplet:

    mlb   by_sport settled   743  open    2  |  books: ...
        !! journal 1733 graded, file 1724 — 9 row(s) did not reach the page

All nine rows were on the page. They were his PUSHED bets.

`book_records` counts a push in its own `push` field — deliberately,
because a pushed bet handed its stake back and is outside the ROI
denominator — so `w + l` is the graded count and cannot ever include
one. The reconciliation compared that sum against a journal count of
``status IN ('won','lost','push')``, so every push in the book read as
a row the export had dropped.

A check that invents a discrepancy is worse than no check: it sends the
next reader hunting an export bug that does not exist, which is what it
did to me for the length of an afternoon. Both sides count won and lost
now, and the pushes are printed beside the book rather than vanishing
into the arithmetic.

It also covers what the check PRINTS, which grew the same day: the
quarantined books per sport and the scope-chip count, so "is college
showing every bet it placed?" is answerable from the droplet instead of
by scrolling the site.

Run directly:
`python3 tests/test_the_record_check_counts_the_same_thing_twice.py`
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import homecheck
from engine import gate, ledger

SRC = (ROOT / "homecheck.py").read_text()


def _journal(wins, losses, pushes, sport="mlb", category="main"):
    """A journal with a known W-L-P, returned as a path."""
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "ledger.db"))
    n = [0]
    for status, count in (("won", wins), ("lost", losses), ("push", pushes)):
        for _ in range(count):
            n[0] += 1
            conn.execute(
                "INSERT INTO bets (sport,date,player,market,side,line,odds,"
                "book,hit_prob,edge,stake_units,stake_dollars,ts,status,"
                "category,pnl_units) VALUES (?,?,?,'home_runs','OVER',0.5,"
                "-120,'DK',0.6,0,1.0,0,'now',?,?,0)",
                (sport, ledger.RECORD_EPOCH, f"P{n[0]}", status, category))
    conn.commit()
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    conn.close()
    return path


def _run(journal_path, doc, monkey=[]):
    """`homecheck.record()` against a given journal and published file."""
    art = Path(tempfile.mkdtemp()) / "record.json"
    art.write_text(json.dumps(doc), encoding="utf-8")
    old_db, old_src = ledger.DEFAULT_DB, gate.board_source
    try:
        ledger.DEFAULT_DB = journal_path
        gate.board_source = lambda _p: art
        return "\n".join(homecheck.record())
    finally:
        ledger.DEFAULT_DB, gate.board_source = old_db, old_src


def _doc(w, l, push, shadow=None, journaled=None):
    """What the export publishes for that journal."""
    doc = {
        "generated_at": "", "record_epoch": ledger.RECORD_EPOCH,
        "tracked_sports": ["mlb"],
        "by_sport": {"mlb": {"overall": {"settled": w + l + push, "open": 0}}},
        "book_records": {"mlb": {"edge": {
            "label": "Edge bets", "n": w + l + push,
            "w": w, "l": l, "push": push, "net_u": 0.0, "markets": {}}}},
    }
    if shadow is not None:
        doc["shadow_books"] = shadow
    if journaled is not None:
        doc["journaled"] = journaled
    return doc


# --- the quarantined books are visible from the terminal too ----------
def test_the_shadow_books_are_printed_beside_the_headline_ones():
    """Ethan, 2026-09-19: "i want all bets shown on the record page."
    Whether they made it into the FILE has to be answerable without
    scrolling the site."""
    out = _run(_journal(5, 4, 9),
               _doc(5, 4, 9, shadow={"mlb": {"stale": {
                   "w": 40, "l": 170, "push": 2}}}))
    assert "also tracked, never staked: stale 210 (+2 push)" in out, out


def test_a_sport_with_only_shadow_rows_still_gets_a_line():
    """College's case: nothing in the three headline books, 210 rows in
    a book that used to be invisible. A check that skipped it would
    reproduce the bug it exists to catch."""
    out = _run(_journal(0, 0, 0),
               _doc(0, 0, 0, shadow={"cfb": {"stale": {"w": 39, "l": 171}}}))
    assert "cfb" in out and "stale 210" in out, out


def test_the_chip_count_is_printed():
    out = _run(_journal(5, 4, 9),
               _doc(5, 4, 9, journaled={"by_sport": {
                   "mlb": {"settled": 18, "open": 3}}}))
    assert "scope chip reads 21 (18 settled, 3 open)" in out, out


def test_a_file_from_before_the_chip_fix_is_named_as_such():
    """A published file with no `journaled` key means the chips are
    falling back to the staked edge book — worth saying out loud rather
    than leaving a reader to wonder why college reads 0."""
    out = _run(_journal(5, 4, 9), _doc(5, 4, 9))
    assert "predates the chip-count fix" in out, out


# --- Ethan's case ------------------------------------------------------
def test_a_book_whose_pushes_are_all_present_reports_no_gap():
    """THE CASE, in miniature: every row exported, nine of them pushes."""
    out = _run(_journal(5, 4, 9), _doc(5, 4, 9))
    assert "did not reach the page" not in out, out


def test_the_pushes_are_printed_rather_than_swallowed():
    """They are still nine settled bets. Dropping them from the count
    is only honest if the line says where they went."""
    out = _run(_journal(5, 4, 9), _doc(5, 4, 9))
    assert "(+9 push)" in out, out


def test_the_book_number_says_which_number_it_is():
    out = _run(_journal(5, 4, 9), _doc(5, 4, 9))
    assert "books W-L:" in out, out


# --- and it still catches a real gap -----------------------------------
def test_a_genuinely_missing_graded_row_is_still_caught():
    """The check exists for an export that drops rows. Journal has 9
    W-L, the file carries 7."""
    out = _run(_journal(5, 4, 9), _doc(4, 3, 9))
    assert "2 graded row(s) did not reach the page" in out, out


def test_a_league_the_file_carries_nothing_for_is_still_caught():
    doc = _doc(5, 4, 9)
    doc["book_records"] = {}
    out = _run(_journal(5, 4, 9), doc)
    assert "carries NONE of them" in out, out


def test_a_push_only_book_is_not_reported_as_missing():
    """Nothing graded, nine pushes: there is no graded row to miss."""
    out = _run(_journal(0, 0, 9), _doc(0, 0, 9))
    assert "did not reach the page" not in out, out
    assert "carries NONE" not in out, out


# --- the source says what it counts ------------------------------------
def test_the_journal_count_excludes_pushes():
    i = SRC.index("def record()")
    body = SRC[i:SRC.index("\ndef ", i + 10)]
    assert "AND status IN ('won','lost') " in body, \
        "the journal side is counting pushes again"
    assert "status IN ('won','lost','push')" not in body, \
        "the two sides are counting different things again"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
