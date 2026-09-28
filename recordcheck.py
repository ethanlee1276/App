#!/usr/bin/env python3
"""Are the Record page's numbers right? Read-only, on the box.

    cd /srv/qellys && sudo -u qellys python3 recordcheck.py            # NFL
    sudo -u qellys python3 recordcheck.py --sport mlb

Ethan, 2026-09-28, two Record-page screenshots: the Most Likely section's
Spread row read 2/2 while Pick of the Day listed a CAR spread LOST — "make
sure all the numbers are correct". Four checks, nothing written:

1. EVERY GRADE, RE-DERIVED. The ledger is copied into memory and the
   settler's own repair pass (engine/ledger.resettle_mismatches) runs on
   the copy against the history database: every settled bet whose stored
   grade disagrees with the final numbers now on file is listed. The real
   ledger is opened read-only and never touched.
2. THE SAME BET, TWO GRADES. One pick journaled in two sections (Most
   Likely and Pick of the Day, say) must carry one result.
3. EVERY GAME-LINE BET, BY SECTION. Spreads, totals and moneylines listed
   with the section that counts each, so a row can be matched to the
   number above it.
4. EACH SECTION RECOUNTED. The report functions the page draws from
   (likely_report, board_report, performance) against a plain count of
   the rows; any difference is printed.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import ledger as L                                  # noqa: E402

SECTION = {"main": "Edge picks", "paper": "Edge picks", "likely": "Most Likely", "likely_live": "Most Likely",
           "board": "Most Likely by tier", "potd": "Pick of the Day"}


def _ro(path) -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def copy_to_memory(path) -> sqlite3.Connection:
    src = _ro(path)
    mem = sqlite3.connect(":memory:")
    src.backup(mem)
    src.close()
    mem.row_factory = sqlite3.Row
    return mem


def regrade(mem, hist) -> list:
    """What the settler's repair pass would change, run on the copy."""
    try:
        return L.resettle_mismatches(mem, hist) or []
    except Exception as exc:                                    # noqa: BLE001
        return [{"error": f"{type(exc).__name__}: {exc}"}]


def expected_status(side, line, actual) -> str | None:
    """The result a bet's own stored number implies — side-aware, a push on
    the number (spreads are stored as margin OVER the negated line)."""
    try:
        a, ln = float(actual), float(line)
    except (TypeError, ValueError):
        return None
    s = str(side or "").upper()
    if s in ("OVER", "YES"):
        return "won" if a > ln else "push" if a == ln else "lost"
    if s in ("UNDER", "NO"):
        return "won" if a < ln else "push" if a == ln else "lost"
    return None


def self_contradictions(conn, sport) -> list:
    """Settled bets whose result disagrees with their own stored number."""
    out = []
    for r in conn.execute(f"SELECT category, {L.day_expr()} AS day, player, market, side, line, actual, status "
                          "FROM bets WHERE status IN ('won','lost','push') AND actual IS NOT NULL "
                          "AND LOWER(sport)=?", (sport,)):
        want = expected_status(r["side"], r["line"], r["actual"])
        if want and want != r["status"]:
            out.append(dict(r, want=want))
    return out


def split_grades(conn, sport) -> list:
    """Settled bets journaled in more than one section with different results."""
    q = (f"SELECT category, {L.day_expr()} AS day, player, market, side, line, status FROM bets "
         "WHERE status IN ('won','lost','push') AND LOWER(sport)=?")
    groups: dict = defaultdict(list)
    for r in conn.execute(q, (sport,)):
        groups[(r["day"], r["player"], r["market"], (r["side"] or "").upper(), r["line"])].append(
            (r["category"], r["status"]))
    return [(k, v) for k, v in groups.items() if len({s for _c, s in v}) > 1]


def game_lines(conn, sport) -> list:
    marks = ",".join("?" * len(L.GAME_MARKETS))
    return [dict(r) for r in conn.execute(
        f"SELECT category, {L.day_expr()} AS day, date, player, market, side, line, odds, status, actual, stake_units "
        f"FROM bets WHERE LOWER(sport)=? AND market IN ({marks}) AND status IN ('won','lost','push','open') "
        "ORDER BY day, category", (sport, *L.GAME_MARKETS))]


def recount(conn, sport) -> list:
    """(section, what, report says, raw count says) for every disagreement."""
    out = []
    lk = L.likely_report(conn, sport=sport)
    raw = {r["market"]: (r["n"], r["w"]) for r in conn.execute(
        "SELECT market, COUNT(*) n, SUM(status='won') w FROM bets WHERE status IN ('won','lost') "
        "AND category IN ('likely','likely_live') AND LOWER(sport)=? GROUP BY market", (sport,))}
    for m, d in (lk.get("by_market") or {}).items():
        got, want = (d.get("n"), d.get("w")), raw.get(m, (0, 0))
        if tuple(got) != tuple(want):
            out.append(("Most Likely", f"by market {m} (n, won)", got, want))
    for m, (n, w) in raw.items():
        if m not in (lk.get("by_market") or {}):
            out.append(("Most Likely", f"by market {m} (n, won)", "missing", (n, w)))
    tw = conn.execute("SELECT SUM(status='won') w, SUM(status='lost') l FROM bets WHERE category IN "
                      "('likely','likely_live') AND LOWER(sport)=?", (sport,)).fetchone()
    if (lk.get("wins"), lk.get("losses")) != (tw["w"] or 0, tw["l"] or 0):
        out.append(("Most Likely", "wins-losses", (lk.get("wins"), lk.get("losses")), (tw["w"] or 0, tw["l"] or 0)))
    br = L.board_report(conn, sport=sport)
    for t in br.get("tiers") or []:
        r = conn.execute("SELECT SUM(status='won') w, SUM(status='lost') l FROM bets WHERE category='board' "
                         "AND grade=? AND LOWER(sport)=?", (t["tier"], sport)).fetchone()
        if (t["w"], t["l"]) != (r["w"] or 0, r["l"] or 0):
            out.append(("Most Likely by tier", t["tier"], (t["w"], t["l"]), (r["w"] or 0, r["l"] or 0)))
    for label, cats in (("Pick of the Day", (L.POTD_CATEGORY,)), ("Edge picks", L.BOOK)):
        p = L.performance(conn, sport, cats if len(cats) > 1 else cats[0])
        marks = ",".join("?" * len(cats))
        r = conn.execute(f"SELECT SUM(status='won') w, SUM(status='lost') l FROM bets WHERE category IN ({marks}) "
                         "AND stake_units > 0 AND LOWER(sport)=?", (*cats, sport)).fetchone()
        got = (p.get("wins"), p.get("losses"))
        if got != (r["w"] or 0, r["l"] or 0):
            out.append((label, "wins-losses", got, (r["w"] or 0, r["l"] or 0)))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default="nfl")
    ap.add_argument("--db", default=str(ROOT / "data" / "ledger.db"))
    ap.add_argument("--history", default=str(ROOT / "data" / "history.db"))
    a = ap.parse_args(argv)
    sport = a.sport.lower()
    mem = copy_to_memory(a.db)
    hist = _ro(a.history)
    print(f"RECORD CHECK — {sport.upper()} (read-only: the ledger is checked on an in-memory copy)\n")

    fixes = regrade(mem, hist)
    print(f"1. GRADES THAT DISAGREE WITH THE FINAL NUMBERS ON FILE (every sport): {len(fixes)}")
    for f in fixes[:40]:
        if "error" in f:
            print(f"    could not re-derive: {f['error']}")
            continue
        print(f"    {f.get('date')} {f.get('player')} {f.get('market')}: graded {f.get('was')}, "
              f"the final numbers say {f.get('now')} (actual {f.get('actual')})")
    mem2 = copy_to_memory(a.db)       # the untouched copy, for the rest
    selfc = self_contradictions(mem2, sport)
    print(f"\n1b. RESULTS THAT CONTRADICT THEIR OWN NUMBER: {len(selfc)}")
    for r in selfc[:40]:
        print(f"    {r['day']} {SECTION.get(r['category'], r['category'])}: {r['player']} {r['market']} "
              f"{r['side']} {r['line']} — actual {r['actual']}, recorded {r['status']}, should be {r['want']}")
    split = split_grades(mem2, sport)
    print(f"\n2. THE SAME BET GRADED DIFFERENTLY IN TWO SECTIONS: {len(split)}")
    for (day, player, market, side, line), v in split[:40]:
        print(f"    {day} {player} {market} {side} {line}: " + ", ".join(f"{SECTION.get(c, c)} {s}" for c, s in v))
    rows = game_lines(mem2, sport)
    print(f"\n3. EVERY {sport.upper()} GAME-LINE BET ({len(rows)}), with the section that counts it")
    for r in rows:
        line = r["line"]
        shown = -line if r["market"] == "spread" and line is not None else line
        print(f"    {r['day']}  {SECTION.get(r['category'], r['category']):20} {r['player']:10} {r['market']:9} "
              f"{r['side'] or '':5} {shown!s:>6} {r['odds']!s:>6}  {r['status']:5}  actual {r['actual']}")
    diffs = recount(mem2, sport)
    print(f"\n4. SECTION TOTALS THAT DISAGREE WITH A PLAIN COUNT: {len(diffs)}")
    for sec, what, got, want in diffs:
        print(f"    {sec} · {what}: page {got}, rows {want}")
    if not (fixes or selfc or split or diffs):
        print("\nAll four checks clean: every grade matches the final numbers, no bet carries two results,"
              " and every section's totals match its rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
