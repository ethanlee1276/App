#!/usr/bin/env python3
"""Past UFC picks recorded at a price you could not bet, or under a book
that was not posting it. Read-only, on the box.

    cd /srv/qellys && sudo -u qellys python3 ufcbooks.py

Found 2026-10-14 building the card's Pick of the Day (step 97): two faults
in `ufc_build.best_h2h`, fixed that day.

* THE SHARP BOOK COULD BE "BEST". Pinnacle's price was shopped with the
  books you can bet, so when it was the best number on a fighter the card
  showed it and the journal recorded it: a price nobody in the US can take.
* THE SECOND FIGHTER WORE THE FIRST FIGHTER'S BOOK. The price was his best
  one; the book named beside it was the other corner's.

Every UFC row the ledger holds is read, in two groups:

* AT A SHARP BOOK: recorded at Pinnacle's price, with what it graded.
* UNDER ANOTHER BOOK'S NAME: the line-move store (`linemoves.HISTORY_PATH`,
  every paid pull since 2026-08-10) holds the pull the price came from — the
  last one at or before the row was written — and the book on the row was
  not posting that price for him there. The book that was is named. The
  price itself was real, so this is a label, not a grade.

A row with no stored pull before it is counted, not judged. NOTHING IS
CHANGED: the ledger is opened read-only, the store is only read, and every
grade stays as it is.
"""

import datetime as _dt
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _ro(path):
    """Read-only, never created: a missing file is an error, not an empty
    database the check made."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _epoch(ts) -> float | None:
    """The journal's UTC stamp ("2026-09-27T14:05:09") as a UNIX time."""
    try:
        t = _dt.datetime.fromisoformat(str(ts or ""))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return t.timestamp()


def _pulls(path, fighters: set) -> dict:
    """``{fighter: [(ts, book, price)]}``: his moneyline rows in the store,
    oldest first. One pass over the file; anything unreadable is skipped."""
    out: dict = {}
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return out
    with fh:
        for line in fh:
            if '"moneyline"' not in line:
                continue
            try:
                r = json.loads(line)
                who = r.get("player")
                if who in fighters and r.get("market") == "moneyline":
                    out.setdefault(who, []).append(
                        (float(r["ts"]), str(r.get("book") or ""), int(r["over_odds"])))
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
    for rows in out.values():
        rows.sort()
    return out


def _pull_at(rows, ts) -> tuple:
    """``(when, {book: price})``: the last pull at or before ``ts`` (one
    pull writes every book under one stamp), or ``(None, {})``."""
    before = [r for r in rows if ts is not None and r[0] <= ts]
    if not before:
        return None, {}
    last = before[-1][0]
    return last, {book: price for t, book, price in before if t == last}


def _graded(b) -> str:
    status = str(b["status"] or "open")
    if status in ("won", "lost", "push"):
        return f"graded {status} {float(b['pnl_units'] or 0):+.2f}u"
    return status


def report(ledger_path, history_path=None) -> list:
    """The lines to print. ``history_path`` is the line-move store
    (`linemoves.HISTORY_PATH` by default)."""
    from engine.odds import is_sharp_book
    if history_path is None:
        from engine.linemoves import HISTORY_PATH as history_path
    led = _ro(ledger_path)
    led.row_factory = sqlite3.Row
    try:
        rows = led.execute("SELECT * FROM bets WHERE sport='ufc' ORDER BY date, id").fetchall()
    finally:
        led.close()
    sharp = [b for b in rows if is_sharp_book(str(b["book"] or ""))]
    pulls = _pulls(history_path, {b["player"] for b in rows})
    wrong, unchecked = [], 0
    for b in rows:
        if is_sharp_book(str(b["book"] or "")):
            continue
        when, books = _pull_at(pulls.get(b["player"]) or [], _epoch(b["ts"]))
        if not books:
            unchecked += 1
            continue
        if books.get(b["book"]) == b["odds"]:
            continue
        posted = sorted(k for k, v in books.items() if v == b["odds"] and not is_sharp_book(k))
        wrong.append((b, when, books.get(b["book"]), posted))
    out = ["UFC BOOKS  read-only: nothing here changes a grade",
           f"{len(rows)} UFC row(s) in the ledger: {len(sharp)} at a sharp book, "
           f"{len(wrong)} under another book's name, {unchecked} with no stored pull "
           f"to check against."]
    if sharp:
        out += ["", "AT A SHARP BOOK (Pinnacle takes no US bets: the price was never one to take)"]
        for b in sharp:
            out.append(f"  {b['date']}  {b['player']} ({int(b['odds']):+d}, {b['book']}, "
                       f"{float(b['stake_units'] or 0):g}u, {b['category']})  {_graded(b)}")
    if wrong:
        out += ["", "UNDER ANOTHER BOOK'S NAME (the price was real; the name beside it was not "
                    "the book posting it)"]
        for b, when, theirs, posted in wrong:
            at = _dt.datetime.fromtimestamp(when, _dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            who = (", ".join(posted) + " posted it") if posted else "no book posted it"
            had = (f"{b['book']} had {theirs:+d}" if theirs is not None
                   else f"{b['book']} had no price on him")
            out.append(f"  {b['date']}  {b['player']} ({int(b['odds']):+d} at {b['book']}, "
                       f"{b['category']})  pull of {at}: {who}; {had}")
    out += ["", "Every grade stays as it is."]
    return out


def main() -> int:
    try:
        for line in report(ROOT / "data" / "ledger.db"):
            print(line)
    except sqlite3.Error as exc:
        print(f"unreadable: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
