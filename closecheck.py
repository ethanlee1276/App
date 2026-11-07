#!/usr/bin/env python3
"""The close, bet by bet — read-only, on the box.

    cd /srv/qellys && sudo -u qellys python3 closecheck.py
    sudo -u qellys python3 closecheck.py --sport nfl
    sudo -u qellys python3 closecheck.py --since 2026-09-01
    sudo -u qellys python3 closecheck.py --all          (no cap on the lists)

Ethan's box run of the loss audit, 2026-09-29: the Most Likely picks that
LOST the close hit 18% (staked, 8-37) and 12% (the one board, 9-63) where
we claimed 62%. A market moving against a pick should cost it a few
points, not forty-five. Three things produce a number like that, and each
leaves a different mark on the rows:

  A SCRATCH GRADED ZERO. He never played; the book voided the ticket; the
    ledger graded it lost at 0. The final number reads 0 (or nothing) on
    a line that said he was a regular, and the close moved a long way
    because the books pulled the market. That is a grading gap, and the
    fix belongs in the settler.
  NEWS THE MARKET HAD. His role changed before kickoff — a questionable
    tag, a lineup change — the line moved a point or more, and he then
    did what the new line said. The pick should have come off the board
    when the market moved; the board has that rule, and whether it fired
    in time is what the list shows.
  A CLOSE THAT IS NOT ONE. The closing line came from a different day's
    or a different market's snapshot: the move looks absurd (5.5
    receptions closing at 1.5) and the final number sits near OUR line,
    not the close's.

WHAT IT PRINTS, per published book (lossaudit.BOOKS; the ledger opened in
mode=ro, so it can never write):
  1. the record by how far the close moved — beat by 2+, by 1, by under
     a point, same, lost by under a point, by 1, by 2+, moved on price
     only, no close — with what we claimed, so the size of the move is
     read against the size of the damage; and, for the bets that lost
     the close, whether the final number sat nearer the close than our
     line (the market knew) or nearer our line (the close is suspect);
  2. the lost-the-close bets by sport and by market;
  3. scratch suspects — lost-the-close bets whose final number is
     missing, or 0 on a line of SCRATCH_LINE or more;
  4. every lost-the-close bet, one line each: the line we took, the
     close, the price and its close, the final number, the grade;
  5. which markets never get a close — the share of each book's settled
     bets with no close at all, by sport and market — since the audit
     found half the Edge picks and six in ten Most Likely picks carry
     none, and a CLV that is only measured on the other half is a CLV
     measured on whichever half the pipeline happened to see.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.ledger import _bet_clv, _bet_price_clv                       # noqa: E402
from lossaudit import BOOKS, LEDGER, close_verdict, load, open_ledger, score  # noqa: E402

#: A final number of 0 on a line this high or higher is a scratch
#: suspect: the line said he was a regular, the box score says he did
#: nothing. Below it a 0 is an ordinary night (0-for-4, 1.5 total bases).
SCRATCH_LINE = 2.5

#: The buckets of section 1, in print order. Line moves in line points,
#: the price-only moves where the line could not move (0.5 home runs).
BUCKETS = ("beat the close by 2+ pts", "beat the close by 1-1.9 pts", "beat the close by under 1 pt",
           "beat the close on price only", "same as the close", "lost the close on price only",
           "lost the close by under 1 pt", "lost the close by 1-1.9 pts", "lost the close by 2+ pts",
           "no close captured")

#: The lists of sections 3 and 4 stop here unless --all lifts it.
LIST_CAP = 60


def bucket(b) -> str:
    """Section 1's bucket for one settled bet: the verdict the audit
    gives it (lossaudit.close_verdict), sized when the line moved."""
    verdict = close_verdict(b)
    if verdict not in ("beat the close", "lost the close"):
        return verdict
    line = _bet_clv(b)
    if line is None or line == 0:
        return f"{verdict} on price only"
    size = abs(line)
    how = "2+ pts" if size >= 2 else "1-1.9 pts" if size >= 1 else "under 1 pt"
    return f"{verdict} by {how}"


def lost_close(b) -> bool:
    return close_verdict(b) == "lost the close"


def scratch_suspect(b) -> bool:
    """A lost-the-close bet whose final number says he may not have played."""
    if not lost_close(b):
        return False
    if b["actual"] is None:
        return True
    try:
        return float(b["actual"]) == 0 and float(b["line"] or 0) >= SCRATCH_LINE
    except (TypeError, ValueError):
        return False


def nearer_the_close(b) -> bool | None:
    """Did the final number land nearer the close than our line? None
    when the line did not move or the final is missing."""
    if b["closing_line"] is None or b["actual"] is None or b["line"] is None:
        return None
    try:
        actual, line, close = float(b["actual"]), float(b["line"]), float(b["closing_line"])
    except (TypeError, ValueError):
        return None
    if close == line:
        return None
    return abs(actual - close) < abs(actual - line)


def check(conn, since=None, sport=None) -> dict:
    """The whole report as data; `render` prints it."""
    rows = load(conn, since, sport)
    books = {}
    for label, cats in BOOKS:
        mine = [b for b in rows if b["category"] in cats]
        if not mine:
            continue
        by_bucket = defaultdict(list)
        for b in mine:
            by_bucket[bucket(b)].append(b)
        lost = [b for b in mine if lost_close(b)]
        nearer = [nearer_the_close(b) for b in lost]
        knew = sum(1 for x in nearer if x is True)
        judged = sum(1 for x in nearer if x is not None)
        by_sport = defaultdict(list)
        by_market = defaultdict(list)
        for b in lost:
            by_sport[str(b["sport"] or "?").upper()].append(b)
            by_market[f"{str(b['sport'] or '?').upper()} {b['market']}"].append(b)
        no_close = defaultdict(lambda: [0, 0])
        for b in mine:
            k = f"{str(b['sport'] or '?').upper()} {b['market']}"
            no_close[k][1] += 1
            if close_verdict(b) == "no close captured":
                no_close[k][0] += 1
        books[label] = {
            "total": score(mine),
            "buckets": {k: score(v) for k, v in by_bucket.items()},
            "lost": lost,
            "knew": knew, "judged": judged,
            "by_sport": {k: score(v) for k, v in sorted(by_sport.items())},
            "by_market": {k: score(v) for k, v in sorted(by_market.items(), key=lambda kv: -len(kv[1]))},
            "scratch": [b for b in lost if scratch_suspect(b)],
            "no_close": {k: {"none": v[0], "n": v[1]} for k, v in
                         sorted(no_close.items(), key=lambda kv: (-kv[1][0], kv[0]))},
        }
    return {"since": since, "sport": sport, "books": books}


def _pct(x) -> str:
    return "  — " if x is None else f"{x * 100:3.0f}%"


def _num(x) -> str:
    if x is None:
        return "—"
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    return f"{f:g}"


def _odds(x) -> str:
    try:
        return f"{int(x):+d}"
    except (TypeError, ValueError):
        return "—"


def _score_line(label: str, s: dict) -> str:
    wlp = f"{s['w']}-{s['l']}" + (f"-{s['p']}" if s["p"] else "")
    return (f"    {label[:32]:32} {wlp:>9}  hit {_pct(s['hit'])}  claimed {_pct(s.get('claim_avg'))}  "
            f"needed {_pct(s.get('price_avg'))}  {s['units']:+7.2f}u")


def bet_line(b) -> str:
    """One settled bet, everything the close says about it."""
    move = _bet_clv(b)
    pmove = _bet_price_clv(b)
    line_part = f"{_num(b['line'])} → {_num(b['closing_line'])}" if b["closing_line"] is not None else f"{_num(b['line'])} → (no close)"
    price_part = f"{_odds(b['odds'])} → {_odds(b['closing_odds'])}" if b["closing_odds"] is not None else f"{_odds(b['odds'])}"
    size = (f"{move:+.1f} pts" if move not in (None, 0) else
            f"{pmove * 100:+.1f} pr pts" if pmove is not None else "")
    flag = "  SCRATCH?" if scratch_suspect(b) else ""
    return (f"    {str(b['date'])[:10]:10} {str(b['sport'] or '?').upper():4} {str(b['player'] or '')[:22]:22} "
            f"{str(b['market'])[:12]:12} {str(b['side'] or 'OVER'):5} {line_part:>14}  {price_part:>13}  "
            f"{size:>10}  final {_num(b['actual']):>6}  {b['status']}{flag}")


def render(report: dict, cap: int | None = LIST_CAP) -> str:
    out = []
    scope = ", ".join(x for x in (report.get("sport") and report["sport"].upper(),
                                  report.get("since") and f"since {report['since']}") if x)
    out.append(f"CLOSE CHECK — every settled bet{f' ({scope})' if scope else ''}, each book on its own "
               f"(read-only: the ledger is opened in mode=ro)")
    out.append("  A line move is in line points (an over wants the line to rise); a price move is in "
               "probability points.\n")
    if not report["books"]:
        out.append("  No settled bets in the published books.")
        return "\n".join(out)
    for label, bk in report["books"].items():
        out.append(f"=== {label}")
        out.append(_score_line("ALL", bk["total"]))
        out.append("  1. by how far the close moved")
        for k in BUCKETS:
            if k in bk["buckets"]:
                out.append(_score_line(k, bk["buckets"][k]))
        if bk["judged"]:
            share = bk["knew"] / bk["judged"]
            read = ("the market knew" if share >= 0.6 else
                    "the close looks wrong more often than not" if share <= 0.4 else "no clear lean")
            out.append(f"     of the {bk['judged']} that lost the close with a line move, the final number "
                       f"sat nearer the close than our line on {bk['knew']} ({share * 100:.0f}%) — {read}")
        lost = bk["lost"]
        out.append(f"  2. lost the close: {len(lost)} bet{'' if len(lost) == 1 else 's'}")
        for k, s in bk["by_sport"].items():
            out.append(_score_line(k, s))
        for k, s in list(bk["by_market"].items())[:12]:
            out.append(_score_line(k, s))
        sus = bk["scratch"]
        out.append(f"  3. scratch suspects (final missing, or 0 on a line of {SCRATCH_LINE:g}+): {len(sus)}"
                   + (f" of {len(lost)} — {len(sus) / len(lost) * 100:.0f}% of the lost-the-close bets"
                      if lost else ""))
        for b in (sus if cap is None else sus[:cap]):
            out.append(bet_line(b))
        if cap is not None and len(sus) > cap:
            out.append(f"    … and {len(sus) - cap} more (--all lists them)")
        out.append(f"  4. every bet that lost the close")
        for b in (lost if cap is None else lost[:cap]):
            out.append(bet_line(b))
        if cap is not None and len(lost) > cap:
            out.append(f"    … and {len(lost) - cap} more (--all lists them)")
        out.append("  5. no close captured, by market (none / settled)")
        for k, v in list(bk["no_close"].items())[:15]:
            if v["none"]:
                out.append(f"    {k[:32]:32} {v['none']:4} / {v['n']:<4}  {v['none'] / v['n'] * 100:3.0f}%")
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--since", help="only bets dated on or after YYYY-MM-DD")
    ap.add_argument("--sport", help="one league: nfl, cfb, mlb, nba, wnba")
    ap.add_argument("--db", default=str(LEDGER), help="the ledger (default data/ledger.db)")
    ap.add_argument("--all", action="store_true", help="no cap on the lists")
    a = ap.parse_args(argv)
    if not Path(a.db).exists():
        print(f"no ledger at {a.db}")
        return 1
    print(render(check(open_ledger(a.db), a.since, a.sport), None if a.all else LIST_CAP))
    return 0


if __name__ == "__main__":
    sys.exit(main())
