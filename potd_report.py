#!/usr/bin/env python3
"""What the Pick of the Day saw, chose, and refused — on a real board.

Ethan, 2026-09-15: "I wanna make sure we access all the data we can and
all the tools we can to dish out the best picks of the day possible."

THE QUESTION THIS ANSWERS is the one no test can. The suite proves the
selector obeys its rules; it cannot say whether a real Tuesday board
carries anything for those rules to bite on. If the answer on the
droplet is "68 rows considered, 61 outside the band, 7 with only our own
model behind them, 0 picks", that is not a bug — it is the pool being
wrong, and it names which gate to argue with.

READ-ONLY. It opens the published board JSON, runs `potd.choose` over
it, and prints. Nothing is written, nothing is journaled, no price is
fetched, so it is safe to run on the production box mid-cycle.

    python3 potd_report.py                    # every board in web/data
    python3 potd_report.py nfl cfb            # just these
    python3 potd_report.py --dir /srv/qellys/web/data
    python3 potd_report.py nfl --rows 12      # show the near misses

WHY IT LIVES AT THE ROOT rather than under engine/: it is a droplet
tool, in the same family as `stale_lines.py` and `shopping_value.py`,
and those are where a person looks for it.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import potd                                       # noqa: E402

#: Boards that carry a `most_likely` list. Same spelling the builds use.
BOARDS = ("mlb", "nfl", "cfb", "nba", "wnba")


def _load(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:                                  # noqa: BLE001
        return {"_error": f"{type(exc).__name__}: {exc}"}


def _one_line(row: dict) -> str:
    """A candidate in a line: who, at what, on whose say-so."""
    who = row.get("player") or row.get("team") or "?"
    what = row.get("market_label") or row.get("market") or ""
    side = str(row.get("side") or "").upper()
    line = row.get("line")
    odds = row.get("odds")
    fair = potd.fair_prob(row)
    ev = potd.edge(row)
    bits = [f"{who} {side} {line if line is not None else ''} {what}".strip(),
            f"{odds:+d}" if isinstance(odds, (int, float)) else str(odds),
            f"{potd.evidence(row)} fair {fair:.1%}" if fair is not None else "no fair",
            f"{ev:+.1%} EV" if ev is not None else "no EV"]
    if row.get("reserve"):
        bits.append("[reserve]")
    return "  ".join(str(b) for b in bits)


def report(payload: dict, sport: str, rows_shown: int = 5) -> str:
    if payload.get("_error"):
        return f"{sport.upper()}: could not read the board — {payload['_error']}"
    rows = [r for r in (payload.get("most_likely") or []) if isinstance(r, dict)]
    pick, near, census = potd.choose(rows)
    out = [f"{sport.upper()}  ·  board built {payload.get('built_at', '?')}  ·  "
           f"{len(rows)} row(s) considered"]

    if not rows:
        out.append("  The board carries no Most Likely rows at all — the pool "
                   "is empty before this feature is even asked.")
        return "\n".join(out)

    # WHERE THE ROWS WENT, biggest gate first. This is the whole point:
    # a day with no pick should say which bar was binding rather than
    # shrugging, exactly as `likely.build`'s own funnel does.
    out.append(f"  Band        {potd.MIN_ODDS:+d} to {potd.MAX_ODDS:+d} "
               f"(pays {potd.MIN_PAYOUT:.2f}u to {potd.MAX_PAYOUT:.2f}u)  ·  "
               f"EV floor {potd.MIN_EV:.0%}  ·  fair floor {potd.MIN_FAIR:.0%}")
    if census:
        out.append("  Refused:")
        for why, n in sorted(census.items(), key=lambda kv: -kv[1]):
            out.append(f"    {n:>4}  {why}")

    if pick is not None:
        out.append(f"  PICK        {_one_line(pick)}")
    elif near is not None:
        out.append(f"  no pick     best available: {_one_line(near)}")
        out.append(f"              ({potd.shortfall(near)}) — shown, not recorded")
    else:
        out.append("  no pick     and nothing in the band at a real price to show")

    # The near misses, so a reader can see what one gate away looks like.
    misses = [r for r in rows if not potd.disqualify(r) and potd.shortfall(r)]
    if misses and rows_shown:
        misses.sort(key=potd.rank_key)
        out.append(f"  In the band but short ({len(misses)}):")
        for r in misses[:rows_shown]:
            out.append(f"    {_one_line(r)}")
            out.append(f"        {potd.shortfall(r)}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sports", nargs="*", help="leagues to report (default: all found)")
    ap.add_argument("--dir", default=os.path.join("web", "data"),
                    help="where the *_picks.json boards live")
    ap.add_argument("--rows", type=int, default=5,
                    help="how many near misses to print per board (0 for none)")
    args = ap.parse_args(argv)

    wanted = [s.lower() for s in args.sports] or list(BOARDS)
    found = 0
    for sport in wanted:
        path = os.path.join(args.dir, f"{sport}_picks.json")
        if not os.path.exists(path):
            # A league that simply is not in season is not an error; say
            # so once and move on rather than printing a stack of them.
            continue
        found += 1
        print(report(_load(path), sport, args.rows))
        print()
    if not found:
        looked = os.path.join(args.dir, "*_picks.json")
        have = sorted(os.path.basename(p) for p in glob.glob(looked))
        print(f"No board found for {', '.join(wanted)} in {args.dir!r}.")
        print(f"  Present: {', '.join(have) if have else '(nothing)'}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
