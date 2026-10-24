#!/usr/bin/env python3
"""Is every league's Pick of the Day reaching its record? Read-only, on the box.

    cd /srv/qellys && sudo -u qellys python3 potdcheck.py

Ethan, 2026-10-14: "we only show the pick of the day record for nfl and
mlb but no other sport. Fix that". The college and basketball builds
journaled the card before `potd.attach` had made it, so they recorded
nothing (fixed that day: `ledger.journal_potd`, after the attach). One
line per league, journal then card:

* journal — the Picks of the Day recorded under that league: how many,
  how many riding, W-L-P, the first and the last day. "none ever" is
  the bug this check was written for when the card has been saying BET.
* card — what the league's board shows now: BET (pick, price, book,
  whose fair) or NO BET and why. "recorded today" when the card is the
  pick the journal holds for today; "NOT RECORDED" when the card says
  BET and today's journal holds nothing for the league — after a build
  on this code that line should never stay.
* record — the leagues record.json carries a Pick of the Day record for,
  which is what the Record page draws under each league.

Writes nothing.
"""

import argparse
import datetime as _dt
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

#: Every league the journal keeps, in the launcher's order, with the
#: board the page reads its card from (launch.py's *_OUT).
BOARDS = {
    "nfl": "web/data/recommendations.json",
    "cfb": "web/data/cfb.json",
    "mlb": "web/data/mlb_recommendations.json",
    "nba": "web/data/nba.json",
    "wnba": "web/data/wnba.json",
    "nhl": "web/data/nhl.json",
    "ufc": "web/data/ufc.json",
}


def _journal(conn) -> dict:
    """{sport: {"n", "open", "won", "lost", "push", "first", "last"}}."""
    out: dict = {}
    for sport, status, n, first, last in conn.execute(
            "SELECT sport, status, COUNT(*), MIN(substr(ts,1,10)), MAX(substr(ts,1,10)) "
            "FROM bets WHERE category='potd' GROUP BY sport, status"):
        s = out.setdefault(sport, {"n": 0, "open": 0, "won": 0, "lost": 0, "push": 0,
                                   "first": first, "last": last})
        s["n"] += n
        if status in s:
            s[status] += n
        s["first"], s["last"] = min(s["first"], first), max(s["last"], last)
    return out


def _journal_line(j) -> str:
    if not j:
        return "none ever"
    return (f"{j['n']} recorded ({j['open']} riding) {j['won']}-{j['lost']}-{j['push']}, "
            f"first {j['first']}, last {j['last']}")


def _card_line(card, today_key) -> str:
    """What the league's card says, and whether the journal holds it."""
    from engine import ledger
    if not isinstance(card, dict) or not card:
        return "no card on this board"
    pick = card.get("pick")
    call = str((card.get("verdict") or {}).get("call") or "")
    if not isinstance(pick, dict) or pick.get("below_bar") or call != "bet":
        why = (pick or {}).get("below_bar") if isinstance(pick, dict) else ""
        why = why or (card.get("verdict") or {}).get("why") or card.get("note") or "no pick"
        return f"NO BET — {why}"
    fair = pick.get("fair_prob")
    said = (f"BET {pick.get('player') or pick.get('pick_label') or '?'} at {pick.get('odds')} "
            f"{pick.get('book') or ''} ({pick.get('evidence') or '?'} fair "
            f"{'?' if fair is None else f'{float(fair):.0%}'})").replace("  ", " ")
    key = ledger.potd_row_key(pick)
    if today_key is None:
        return f"{said} — NOT RECORDED: today's journal holds nothing for this league"
    if key is not None and tuple(key) == tuple(today_key):
        return f"{said} — recorded today"
    return f"{said} — today's record holds a different pick ({today_key[0]} {today_key[1]})"


def _locks(conn, day: str) -> dict:
    """{sport: journal key} — the pick each league locked for ``day``
    (Eastern), found the way `ledger.relock_potd` finds it: journaled on
    that UTC date or the next (an evening pick in the East is written
    after midnight UTC), and only a lock whose game is that day."""
    from engine import ledger
    nxt = (_dt.date.fromisoformat(day) + _dt.timedelta(days=1)).isoformat()
    out: dict = {}
    for utc_day in (day, nxt):
        for sport, got in ledger.locked_potd_picks(conn, utc_day).items():
            gday = str(got.get("game_day") or "")[:10]
            if sport not in out and (not gday or gday == day):
                out[sport] = got["_key"]
    return out


def report(conn, cards: dict, record=None, day: str | None = None) -> list[str]:
    """The check's lines. ``cards`` is {sport: the board's pick_of_the_day
    or None}; ``record`` is record.json as published (None to skip);
    ``day`` is the Eastern slate day (`potd.slate_day`, the default)."""
    from engine import ledger, potd
    day = day or potd.slate_day()
    journal = _journal(conn)
    locked = _locks(conn, day)
    out = [f"pick of the day check — slate day {day} (Eastern)"]
    for sport in BOARDS:
        bench = " (benched — off the Record page)" if ledger.is_benched(sport) else ""
        out.append(f"{sport:<5} journal: {_journal_line(journal.get(sport))}{bench}")
        out.append(f"{'':<5} card:    {_card_line(cards.get(sport), locked.get(sport))}")
    if record is not None:
        by = record.get("potd_by_sport") or {}
        pooled = record.get("potd") or {}
        out.append(f"record.json: a Pick of the Day record for {', '.join(sorted(by)) or 'no league'}"
                   f" (pooled {pooled.get('settled', 0)} settled, {pooled.get('open', 0)} riding)")
    return out


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main(argv=None) -> int:
    from engine import gate, ledger
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(ledger.DEFAULT_DB))
    a = ap.parse_args(argv)
    conn = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cards = {}
        for sport, rel in BOARDS.items():
            board = _load(gate.board_source(ROOT / rel))
            cards[sport] = (board or {}).get("pick_of_the_day")
        for line in report(conn, cards, _load(ROOT / "web/data/record.json")):
            print(line)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
