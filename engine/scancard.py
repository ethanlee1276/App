"""Score the research reports, our board and the price on what happened.

    python3 -m engine.scancard                                  # the 2026-10-04 claims
    python3 -m engine.scancard docs/research/<file>.json

Ethan, 2026-10-04, after six research reports on Jaguars @ Bengals and
Broncos @ 49ers: debating whose method is better settles nothing; the
games do. Each report pick with a stated chance is written down before
kickoff (docs/research/2026-10-04_claims.json). After the games settle,
this grades every one against the box score and sets three numbers beside
it: the report's chance, OUR chance for the same bet (the journal, at the
same line, any board but the stale-price sampler, whose number is the
field's consensus and not ours), and the price's chance (the report's
quoted price, implied, hold left in).

THE SCORE IS THE BRIER SCORE, mean (chance − result)², lower is better, so
a source that said 70% on a loser pays more than one that said 55%. Each
source is compared with ours only on the picks both priced, because a
source scored on easier picks would look better for no reason. One
weekend is a small sample: this says who was closer THIS time, and the
file keeps growing as more reports are written down.

Read-only. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .tdmanfit import name_key

DEFAULT = Path(__file__).resolve().parents[1] / "docs" / "research" / "2026-10-04_claims.json"
#: Where a market's stat may be stored, first match wins.
LOG_MARKETS = {"rush_att": ("rush_att", "carries"), "pass_cmp": ("pass_cmp", "completions")}
#: The journal books whose chance is the board's own, best first.
OUR_BOOKS = ("board", "likely_live", "likely", "matchup_td", "matchup_prop", "td_scenario",
             "main", "bold", "held", "plan_gap", "longshot")


def implied(price) -> float | None:
    try:
        o = float(price)
    except (TypeError, ValueError):
        return None
    if not o:
        return None
    return 100.0 / (o + 100.0) if o > 0 else -o / (100.0 - o)


def actual(hist, season: int, week: int, team: str, player: str, market: str):
    """His stat for the week, or None when no row carries it."""
    want = name_key(player)
    for mk in LOG_MARKETS.get(market, (market,)):
        for r in hist.execute(
                "SELECT player, team, value FROM player_game_logs WHERE sport='nfl' AND season=? "
                "AND period=? AND market=?", (season, f"{week:03d}", mk)):
            if name_key(r[0]) == want and (not team or not r[1] or r[1] == team):
                return float(r[2] or 0.0)
    return None


def ours(ledger, season: int, week: int, player: str, market: str, side: str, line: float):
    """(our chance, book) for the same bet at the same line, or (None, "")."""
    want = name_key(player)
    found = {}
    for r in ledger.execute(
            "SELECT player, category, hit_prob FROM bets WHERE sport='nfl' AND date=? AND market=? "
            "AND UPPER(side)=? AND ABS(COALESCE(line, 0) - ?) < 0.01 AND hit_prob IS NOT NULL",
            (f"{season}-W{week:02d}", market, side.upper(), line)):
        if name_key(r[0]) == want and r[1] in OUR_BOOKS:
            found.setdefault(r[1], float(r[2]))
    for book in OUR_BOOKS:
        if book in found:
            return found[book], book
    return None, ""


def grade(claims: list[dict], season: int, week: int, hist, ledger) -> list[dict]:
    out = []
    for c in claims:
        val = actual(hist, season, week, c.get("team", ""), c["player"], c["market"])
        hit = None
        if val is not None and val != c["line"]:
            over = val > c["line"]
            hit = int(over if c["side"].upper() == "OVER" else not over)
        our, book = ours(ledger, season, week, c["player"], c["market"], c["side"], c["line"])
        out.append({**c, "actual": val, "hit": hit, "ours": our, "our_book": book,
                    "price_p": implied(c.get("price"))})
    return out


def _brier(pairs) -> float | None:
    pairs = list(pairs)
    return round(sum((p - y) ** 2 for p, y in pairs) / len(pairs), 4) if pairs else None


def scoreboard(rows: list[dict]) -> list[dict]:
    """Per source: graded picks, hits, its Brier, and on the picks we also
    priced, its Brier against ours and against the price."""
    out = []
    for src in dict.fromkeys(r["source"] for r in rows):
        g = [r for r in rows if r["source"] == src and r["hit"] is not None]
        both = [r for r in g if r["ours"] is not None]
        priced = [r for r in g if r["price_p"] is not None]
        out.append({"source": src, "graded": len(g), "hits": sum(r["hit"] for r in g),
                    "said": round(sum(r["prob"] for r in g) / len(g), 3) if g else None,
                    "brier": _brier((r["prob"], r["hit"]) for r in g),
                    "paired": len(both),
                    "brier_them_paired": _brier((r["prob"], r["hit"]) for r in both),
                    "brier_ours_paired": _brier((r["ours"], r["hit"]) for r in both),
                    "priced": len(priced),
                    "brier_price": _brier((r["price_p"], r["hit"]) for r in priced)})
    return out


def report(rows: list[dict]) -> str:
    lines = ["PICK BY PICK (their chance · ours · price → result)"]
    for r in rows:
        res = ("—" if r["actual"] is None else f"{r['actual']:g} " + ("HIT" if r["hit"] else "push" if r["hit"] is None else "miss"))
        o = f"{r['ours']:.0%}" if r["ours"] is not None else "—"
        q = f"{r['price_p']:.0%}" if r["price_p"] is not None else "—"
        lines.append(f"  {r['source'][:18]:18} {r['player'][:20]:20} {r['market']:10} {r['side'][:1]} {r['line']:<6g} "
                     f"them {r['prob']:.0%} · ours {o} · price {q} → {res}")
    lines.append("")
    lines.append("SCOREBOARD (Brier: lower is better; 0.25 is a coin flip's score)")
    for s in scoreboard(rows):
        if not s["graded"]:
            lines.append(f"  {s['source']}: nothing graded yet")
            continue
        vs = (f"; on the {s['paired']} we also priced: them {s['brier_them_paired']} vs ours {s['brier_ours_paired']}"
              if s["paired"] else "; we priced none of these")
        pr = f"; the price on its {s['priced']}: {s['brier_price']}" if s["priced"] else ""
        lines.append(f"  {s['source']}: {s['hits']} of {s['graded']} hit at a claimed {s['said']:.0%}, "
                     f"Brier {s['brier']}{vs}{pr}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.scancard")
    ap.add_argument("claims", nargs="?", default=str(DEFAULT))
    a = ap.parse_args(argv)
    import sqlite3
    from . import db, ledger as L
    spec = json.loads(Path(a.claims).read_text(encoding="utf-8"))
    hist = db.connect()
    led = sqlite3.connect(f"file:{L.DEFAULT_DB}?mode=ro", uri=True)
    print(report(grade(spec["claims"], int(spec["season"]), int(spec["week"]), hist, led)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
