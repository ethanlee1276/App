#!/usr/bin/env python3
"""Price somebody else's legs with our engine, off the built board. Read-only.

    cd /srv/qellys && python3 legcheck.py                      # tonight's six (Eagles-Bears)
    python3 legcheck.py "Jalen Hurts" pass_yds over 199.5 "DeVonta Smith" receptions over 5.5

Ethan, 2026-09-28, with two research reports on Eagles-Bears: "see how it
aligns with the site and see what seems better than what we are doing."
For each leg this prints our chance at that exact number (the same
derivation the Most Likely board prices a ladder rung with —
likely._prob_at), the best price our books hang there and whether that
rung cleared the board's bars, what the board actually seated for the
player, and the matchup read's label — then every Most Likely row on the
game, so the two boards sit side by side. Writes nothing.
"""

import json
import sys

from engine import likely
from engine.gate import board_source
from engine.sources.oddsapi import normalize_name

TONIGHT = [("Jalen Hurts", "pass_yds", "over", 199.5),        # report 2: 71%, DK -167
           ("Dontayvion Wicks", "rec_yds", "over", 39.5),      # report 2: 69%, DK -124
           ("DeVonta Smith", "receptions", "over", 5.5),       # both: 55% / 65%
           ("Kalif Raymond", "receptions", "over", 2.5),       # report 1: 58%
           ("Kyle Monangai", "rush_att", "over", 9.5),         # report 1: 57%
           ("D'Andre Swift", "anytime_td", "yes", 0.5)]        # report 1 passed at +110


def _legs(argv):
    if len(argv) < 5:
        return TONIGHT
    out, a = [], argv[1:]
    for i in range(0, len(a) - 3, 4):
        out.append((a[i], a[i + 1], a[i + 2].lower(), float(a[i + 3])))
    return out


def _row(board, player, market):
    key = normalize_name(player)
    for r in board.get("recommendations") or []:
        if r.get("market") == market and normalize_name(str(r.get("player") or "")) == key:
            return r
    if market == "anytime_td":
        for r in (board.get("longshot_watch") or []) + (board.get("long_shots") or []):
            if normalize_name(str(r.get("player") or "")) == key:
                return r
    return None


def _best_price(r, side, line):
    """((odds, book), fair) — the best bettable price hung at this exact
    number, by `rungs`' own book rule (no proxy, no sharp book), and the
    de-vigged fair there. Shown even when a bar refuses the rung."""
    from engine.odds import devig_two_way, is_sharp_book
    key = "over_odds" if side == "over" else "under_odds"
    best, fair = None, None
    for ln in r.get("alt_lines") or []:
        try:
            if abs(float(ln.get("line")) - line) >= 0.01:
                continue
            odds = int(ln.get(key) or 0)
        except (TypeError, ValueError):
            continue
        book = str(ln.get("book") or "")
        if not odds or not book or book.lower() == "proxy" or is_sharp_book(book):
            continue
        if best is None or odds > best[0]:
            best = (odds, book)
            try:
                fo, fu = devig_two_way(int(ln.get("over_odds") or 0), int(ln.get("under_odds") or 0))
                fair = fu if side == "under" else fo
            except (TypeError, ValueError, ZeroDivisionError):
                fair = None
    return best, fair


def _seated(board, player):
    key = normalize_name(player)
    return [r for r in ((board.get("likely_board") or {}).get("rows") or [])
            if normalize_name(str(r.get("player") or "")) == key]


def _read(board, player):
    key = normalize_name(player)
    for game in (board.get("scan_reads") or {}).values():
        for x in (game or {}).get("players") or []:
            if normalize_name(str(x.get("player") or "")) == key:
                return x
    return None


def check(board, legs, out=print):
    """One block per leg; returns the rows for a test to read."""
    got = []
    for player, market, side, line in legs:
        r = _row(board, player, market)
        rec = {"player": player, "market": market, "side": side, "line": line}
        if not r:
            out(f"  {player:20} {side} {line:g} {market:11} — not on our board (no prop priced)")
            got.append(rec)
            continue
        if market == "anytime_td":
            p = float(r.get("model_prob") or 0)
            out(f"  {player:20} yes anytime TD        ours {p:.0%} at {r.get('odds')} {r.get('book') or ''}")
            rec.update(prob=p, odds=r.get("odds"))
        else:
            p = likely._prob_at(r, market, side, line)
            best, fair = _best_price(r, side, line)
            cleared = any(abs(float(c["line"]) - line) < 0.01 and c["side"] == side
                          for c in likely.rungs(r, market, floor=0.0))
            price = f"{best[0]} {best[1]} (fair {fair:.0%})" if best else "not hung by a book we can bet"
            if p is None:
                verdict = "no fit for this market"
            elif cleared:
                verdict = "clears the board's bars"
            elif p < likely.MIN_PROB:
                verdict = "under the 55% floor"
            elif best and best[0] < likely.HEAVIEST_PRICE:
                verdict = "past the -250 cap"
            elif best and not likely._credible(p, fair):
                verdict = (f"our {p:.0%} sits more than {likely.MAX_CREDIBLE_EDGE:.0%} from the book's "
                           f"{fair:.0%} — the board would not seat it")
            else:
                verdict = "not seated"
            out(f"  {player:20} {side} {line:g} {market:11} ours {p:.0%}  · price {price}  · {verdict}"
                if p is not None else f"  {player:20} {side} {line:g} {market:11} ours —  · price {price}  · {verdict}")
            out(f"  {'':20} main line {r.get('side')} {r.get('line')} at {r.get('odds')} · projection {r.get('projection')}")
            rec.update(prob=p, best=best, fair=fair, verdict=verdict, main=(r.get("side"), r.get("line"), r.get("odds")))
        for s in _seated(board, player):
            out(f"  {'':20} on Most Likely: {s.get('side')} {s.get('line')} {s.get('market')} {s.get('odds')} · "
                f"{float(s.get('model_prob') or 0):.0%} · {s.get('tier')}")
        x = _read(board, player)
        if x:
            out(f"  {'':20} read: {x.get('label')} ({x.get('read')})"
                + (f" · pick {x['pick'].get('side')} {x['pick'].get('line')}" if x.get("pick") else "")
                + (f" · no pick: {(x.get('no_pick') or {}).get('refused') or 'nothing on the read’s side clears'}"
                   if x.get("no_pick") else ""))
        got.append(rec)
    return got


def main(argv):
    board = json.load(open(board_source("web/data/recommendations.json")))
    print(f"board built {board.get('built_at')}")
    for c in board.get("qb_changes") or []:
        print(f"QB: {c.get('headline')} — {c.get('note')}")
    legs = _legs(argv)
    print("\nTheir legs, our numbers")
    check(board, legs)
    games = {f"{r.get('game')}" for r in ((board.get("likely_board") or {}).get("rows") or [])}
    for g in sorted(games):
        rows = [r for r in board["likely_board"]["rows"] if r.get("game") == g]
        if not rows:
            continue
        print(f"\nOur Most Likely board, {g} ({len(rows)} rows)")
        for r in sorted(rows, key=lambda r: -float(r.get("model_prob") or 0)):
            print(f"  {float(r.get('model_prob') or 0):.0%}  {r.get('player'):22} {r.get('side')} {r.get('line')} "
                  f"{r.get('market'):11} {r.get('odds')} · {r.get('tier')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
