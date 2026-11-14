#!/usr/bin/env python3
"""Past UFC voids that look like the midnight bug. Read-only, on the box.

    cd /srv/qellys && sudo -u qellys python3 ufcvoids.py

Ethan, 2026-10-14, to "a read-only list of the past voids that look like
it? Their grades stay as they are": yes.

THE BUG (fixed 2026-10-13, step 47): a fight's result was read from a copy
of ESPN's bout cached for six hours. A copy saved before the bell says "no
winner", and once the UTC date turned, a bout dated the day before with no
winner read exactly like a draw, which the ledger voids, as a book voids a
draw or a no contest. So a pick could be voided on a fight somebody won.

This lists every UFC pick the ledger voided, in two groups:

* NO WINNER: voided because the bout read as having no winner, the way the
  bug voided. Each is read again from ESPN now (fresh, never the cached
  copy the void came from), and says what ESPN shows: he won or lost (the
  bug's mark: "LOOKS LIKE THE BUG", with what it would have graded), or
  still no winner (a real draw or no contest; the void stands).
* NO BOUT WITHIN TEN DAYS: voided because no completed bout was found for
  him at all within ten days of the card (scratched, moved, or a name the
  results feed spells another way). Not this bug; read again too, for
  completeness.

Then one line: how many look like the bug and what they would have
graded. NOTHING IS CHANGED: the ledger is opened read-only and every grade
stays as it is. ESPN's answers refresh the MMA cache files, as any settle
pass does.
"""

import datetime as _dt
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

#: A bout on the card is dated the card's UTC day or the next (a main card
#: that starts at 10 PM Eastern is the next day in UTC); one day either side.
NEAR_DAYS = (-1, 2)


def _ro(path):
    """Read-only, never created: a missing file is an error, not an empty
    database the check made."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _fresh_json(M, url: str, cache_name: str):
    """(payload, read_now): ESPN's answer, and whether it came from ESPN
    just now. The fetch layer hands back the copy on disk when ESPN can't be
    reached, and that copy may be the very one the void came from, so a
    copy not written by this read is never taken as ESPN's answer now."""
    path = M.CACHE_DIR / cache_name
    t0 = time.time()
    try:
        data = M._get_json(url, cache_name, ttl=0)
    except M.DataUnavailable:
        return None, False
    try:
        now = path.stat().st_mtime >= t0 - 1
    except OSError:
        now = False
    return data, now


def espn_bout(name: str, card_day: _dt.date) -> dict:
    """What ESPN says now about this fighter's bout on the card.

    ``{"found": "bout", "won": True/False/None, "date": iso}``, or
    ``{"found": "no fighter"}`` (no ESPN athlete by that name),
    ``{"found": "no bout"}`` (none dated near the card), or
    ``{"found": "unreachable"}`` (ESPN did not answer just now)."""
    from engine.sources import espnmma as M
    try:
        aid = M.find_athlete_id(name)
    except M.DataUnavailable:
        return {"found": "unreachable"}
    if not aid:
        return {"found": "no fighter"}
    ev, now = _fresh_json(M, f"{M.CORE}/athletes/{aid}/eventlog?page=1",
                          f"espn_mma_evlog_{aid}_p1.json")
    if not now:
        return {"found": "unreachable"}
    lo = card_day + _dt.timedelta(days=NEAR_DAYS[0])
    hi = card_day + _dt.timedelta(days=NEAR_DAYS[1])
    best = None
    for it in ((ev.get("events") or {}).get("items") or [])[:12]:
        ref = ((it.get("competition") or {}).get("$ref") or "").replace("http://", "https://")
        if not ref:
            continue
        cid = ref.rstrip("/").split("/")[-1].split("?")[0]
        # The DATE does not change, so the cached copy finds the bout; the
        # RESULT is then read fresh.
        try:
            comp = M.parse_competition(M._get_json(ref, f"espn_mma_res_{cid}.json"), aid)
        except M.DataUnavailable:
            continue
        d = comp.get("date")
        if not d or not lo <= d <= hi:
            continue
        if best is None or abs((d - card_day).days) < abs((best[0] - card_day).days):
            best = (d, ref, cid)
    if best is None:
        return {"found": "no bout"}
    d, ref, cid = best
    raw, now = _fresh_json(M, ref, f"espn_mma_res_{cid}.json")
    if not now:
        return {"found": "unreachable"}
    comp = M.parse_competition(raw, aid)
    return {"found": "bout", "won": comp["winner"], "date": d.isoformat()}


def _voided_at(led, bet_id) -> str:
    """When the audit trail saw this bet turn void, or ''."""
    try:
        rows = led.execute("SELECT ts, new FROM bets_audit WHERE bet_id=? ORDER BY seq",
                           (bet_id,)).fetchall()
    except sqlite3.Error:
        return ""
    for ts, new in rows:
        try:
            if (json.loads(new or "{}") or {}).get("status") == "void":
                return str(ts or "").replace("T", " ").replace("Z", " UTC")
        except ValueError:
            continue
    return ""


def _units(u: float) -> str:
    return f"{u:+.2f}u"


def report(ledger_path, lookup=None) -> list:
    """The lines to print. ``lookup(name, card_day) -> dict`` is ESPN by
    default (``espn_bout``); injectable for tests."""
    from engine import ledger as L
    lookup = lookup or espn_bout
    led = _ro(ledger_path)
    led.row_factory = sqlite3.Row
    rows = led.execute("SELECT * FROM bets WHERE sport='ufc' AND status='void' "
                       "ORDER BY date, id").fetchall()
    out = ["UFC VOIDS  read-only: nothing here changes a grade "
           "(Ethan, 2026-10-14: \"their grades stay as they are\")"]
    unresolved = [b for b in rows
                  if "why_note" in b.keys() and (b["why_note"] or "") == L.UFC_UNRESOLVED_NOTE]
    no_winner = [b for b in rows if b not in unresolved]
    out.append(f"{len(rows)} UFC pick(s) voided in all: {len(no_winner)} as no winner "
               f"(the way the midnight bug voided), {len(unresolved)} with no bout found "
               f"within {L.UFC_UNRESOLVED_DAYS} days of the card.")
    bug = []
    for title, group, mine in (
            ("NO WINNER", no_winner, True),
            (f"NO BOUT WITHIN {L.UFC_UNRESOLVED_DAYS} DAYS (not this bug: no result was found "
             "at all)", unresolved, False)):
        if not group:
            continue
        out.append("")
        out.append(title)
        for b in group:
            try:
                card = _dt.date.fromisoformat(str(b["date"])[:10])
            except ValueError:
                out.append(f"  {b['date']}  {b['player']}: no card date — not read")
                continue
            when = _voided_at(led, b["id"])
            out.append(f"  {card}  {b['player']} ({int(b['odds']):+d}, {b['book'] or 'no book'}, "
                       f"{float(b['stake_units'] or 0):g}u)  voided "
                       + (when or "(the audit trail has no time for it)"))
            try:
                got = lookup(b["player"], card) or {}
            except Exception as exc:  # noqa: BLE001 - one fighter's error is one line
                got = {"found": "unreachable", "error": type(exc).__name__}
            found = got.get("found")
            if found == "bout" and got.get("won") is not None:
                status, pnl = L._grade_side_aware(b, 1.0 if got["won"] else 0.0)
                word = "WON" if got["won"] else "LOST"
                if mine:
                    bug.append(pnl)
                    out.append(f"      ESPN now: he {word} (bout dated {got['date']}) — "
                               f"LOOKS LIKE THE BUG; it would have graded {status}, {_units(pnl)}")
                else:
                    out.append(f"      ESPN now: he {word} (bout dated {got['date']}) — the "
                               f"results feed missed him then (a name or the timing), not the "
                               f"midnight bug; it would have graded {status}, {_units(pnl)}")
            elif found == "bout":
                out.append(f"      ESPN now: no winner (bout dated {got['date']}): a draw or "
                           f"no contest — the void stands")
            elif found == "no bout":
                out.append("      ESPN now: no bout for him near the card (scratched or moved) "
                           "— the void stands")
            elif found == "no fighter":
                out.append("      ESPN has no fighter by that name — can't say")
            else:
                out.append("      ESPN did not answer just now — can't say; run it again later")
    out.append("")
    won = [p for p in bug if p > 0]
    lost = [p for p in bug if p <= 0]
    if bug:
        out.append(f"LOOKS LIKE THE BUG: {len(bug)} — would have won {len(won)} "
                   f"({_units(sum(won))}), lost {len(lost)} ({_units(sum(lost))}); net "
                   f"{_units(sum(bug))}. Their grades stay as they are (void).")
    else:
        out.append("LOOKS LIKE THE BUG: none.")
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
