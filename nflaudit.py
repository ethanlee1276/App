#!/usr/bin/env python3
"""The NFL Most Likely record, read like a football person would — on the box.

    cd /srv/qellys && sudo -u qellys python3 nflaudit.py              # the graded record
    sudo -u qellys python3 nflaudit.py --history                      # the same flags on 2021-25 games
    sudo -u qellys python3 nflaudit.py --json /tmp/nflaudit.json

Ethan, 2026-10-03: "do a deep dive and deep audit into our NFL most likely
bets and our NFL most likely model and our NFL most likely touchdown model
... think like a human when it comes to making the pick selections."

The other audits slice the record by book, market, side, price and tier
(lossaudit.py), and try selection rules on price and edge (likelyfit.py).
None of them knows the FOOTBALL: what the game was expected to look like,
whether he was just back, whether the book's line sat above everything he
had done. This joins every settled NFL pick to exactly that — the game's
spread, total and weather from the history database, his own results
before the game — and asks each of the scout's flags (engine/scout.py,
thresholds fixed before any of this was run) one question: when this flag
was up, did the picks hit less often than we said?

WHAT IT READS, read-only: data/ledger.db (every settled won/lost NFL pick in
the Most Likely books — the list, the board, the touchdown scenarios, the
matchup picks, the bold picks — each pick once, the first book that holds
it) and data/history.db (games and player logs). It writes nothing.

HOW A FLAG IS JUDGED. Wins against the wins we claimed (sum of hit_prob):
z below −2 says the flag's picks over-claimed. Then the same thing on the
EARLIER and the LATER half of the days separately — a real effect shows in
both halves, a fluke in one. HOLDS = z ≤ −2 and both halves below claim;
WATCH = z ≤ −1; anything else is noise at this sample.

--history asks the larger, rougher question on every 2021-2025 game: with
his own last-five average as the line, does the flagged side hit less often
than the same side does in unflagged games? That is the football effect
before any model; the record is the effect after ours.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import scout as SC                                   # noqa: E402

MIN_N = 15


# --- reading (engine/likelyctx owns the join, so the audit, the fit and the
# board can never disagree about what a flag meant) -----------------------------
from engine.likelyctx import (BOOKS, SOURCE, context, game_keys, history_index,      # noqa: E402,F401
                              journal as picks, log_game, ro as _ro_engine)


def _ro(path: Path) -> sqlite3.Connection:
    return _ro_engine(path)


def _date(s):
    try:
        return _dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


# --- scoring ------------------------------------------------------------------
def score(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    w = sum(r["won"] for r in rows)
    claim = sum(r["p"] for r in rows)
    var = sum(r["p"] * (1 - r["p"]) for r in rows)
    return {"n": n, "hit": w / n, "claimed": claim / n,
            "z": (w - claim) / math.sqrt(var) if var > 0 else 0.0}


def verdict(rows: list[dict], days_split: str) -> dict:
    s = score(rows)
    if s["n"] < MIN_N:
        s["verdict"] = "too few"
        return s
    early = score([r for r in rows if r["day"] < days_split])
    late = score([r for r in rows if r["day"] >= days_split])
    s["early"], s["late"] = early, late
    both_below = all(h.get("n") and h["hit"] < h["claimed"] for h in (early, late))
    s["verdict"] = ("HOLDS" if s["z"] <= -2 and both_below else "WATCH" if s["z"] <= -1 else
                    "BETTER" if s["z"] >= 2 else "noise")
    return s


def auc(rows: list[dict]) -> float | None:
    pos = [r["p"] for r in rows if r["won"]]
    neg = [r["p"] for r in rows if not r["won"]]
    if not pos or not neg:
        return None
    wins = sum((1.0 if a > b else 0.5 if a == b else 0.0) for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


def band(v, edges, labels):
    if v is None:
        return "unknown"
    for e, lab in zip(edges, labels):
        if v < e:
            return lab
    return labels[-1]


def audit(ledger, hist) -> dict:
    rows = picks(ledger)
    games, by_team, logs = history_index(hist, {r["player"] for r in rows})
    for r in rows:
        r["ctx"] = context(r, games, by_team, logs)
        r["flags"] = SC.flags(r["ctx"]) if r["ctx"] else []
    found = [r for r in rows if r["ctx"]]
    days = sorted({r["day"] for r in rows})
    split = days[len(days) // 2] if days else ""
    out = {"n": len(rows), "with_context": len(found), "overall": score(rows),
           "no_flag": score([r for r in found if not r["flags"]]), "flags": {}, "bands": {},
           "td": {}, "ranking": {}, "split_day": split}
    for f in SC.FLAGS:
        out["flags"][f] = verdict([r for r in found if f in r["flags"]], split)
    # The situation, banded — what a reader would sort the slate by.
    def ctx(r, k):
        return (r["ctx"] or {}).get(k)
    cuts = {
        "game total": lambda r: band(ctx(r, "total"), (41, 45, 49), ("≤40.5", "41-44.5", "45-48.5", "49+")),
        "team spread": lambda r: band(ctx(r, "spread"), (-7, -3, 3, 7),
                                      ("fav 7+", "fav 3-6.5", "pick'em ±3", "dog 3-6.5", "dog 7+")),
        "team implied": lambda r: band(ctx(r, "implied"), (18, 21, 24, 27), ("<18", "18-20.9", "21-23.9", "24-26.9", "27+")),
        "market/side": lambda r: f"{r['market']} {str(r.get('side') or '').upper()}",
        "position/side": lambda r: f"{(ctx(r, 'position') or '?')} {str(r.get('side') or '').upper()}",
        "source": lambda r: "+".join(sorted(r["sources"])),
        "flags on the pick": lambda r: band(len(r["flags"]), (1, 2, 3), ("0", "1", "2", "3+")),
        "claimed band": lambda r: band(r["p"], (0.55, 0.6, 0.65, 0.7, 0.75), ("<55", "55-59", "60-64", "65-69", "70-74", "75+")),
    }
    for name, fn in cuts.items():
        grp = defaultdict(list)
        for r in (found if name not in ("market/side", "source", "claimed band") else rows):
            grp[fn(r)].append(r)
        out["bands"][name] = {k: verdict(v, split) for k, v in sorted(grp.items())}
    td = [r for r in rows if r["market"] == "anytime_td"]
    if td:
        dec = defaultdict(list)
        for r in td:
            dec[band(r["p"], (0.3, 0.4, 0.5, 0.6), ("<30", "30-39", "40-49", "50-59", "60+"))].append(r)
        out["td"]["by claim"] = {k: score(v) for k, v in sorted(dec.items())}
        pos = defaultdict(list)
        for r in td:
            pos[(r["ctx"] or {}).get("position") or "?"].append(r)
        out["td"]["by position"] = {k: score(v) for k, v in sorted(pos.items())}
        imp = defaultdict(list)
        for r in td:
            imp[band((r["ctx"] or {}).get("implied"), (18, 22, 26), ("<18", "18-21.9", "22-25.9", "26+"))].append(r)
        out["td"]["by team implied"] = {k: score(v) for k, v in sorted(imp.items())}
        out["td"]["auc"] = auc(td)
    mk = defaultdict(list)
    for r in rows:
        mk[r["market"]].append(r)
    out["ranking"] = {"all": auc(rows), **{m: auc(v) for m, v in mk.items() if len(v) >= MIN_N}}
    # Blowouts, read AFTER the game: how often a loss came in a game decided
    # by 17+ — the script the flags try to see coming.
    lost = [r for r in found if not r["won"] and r["ctx"].get("final_margin") is not None]
    out["losses_in_blowouts"] = (sum(1 for r in lost if abs(r["ctx"]["final_margin"]) >= 17) / len(lost)
                                 if lost else None)
    out["examples"] = {f: [f"{r['day']} {r['player']} {r['market']} {r.get('side')} {r.get('line')} "
                           f"({'W' if r['won'] else 'L'}, said {r['p']:.0%})"
                           for r in found if f in r["flags"]][:4] for f in SC.FLAGS}
    return out


# --- the history replay (engine/scouthist owns it: the weekly job that turns
# what it proves into the board's correction runs the same code) ------------
from engine.scouthist import HISTORY_MARKETS, replay               # noqa: E402,F401


# --- printing -------------------------------------------------------------------
def _line(name, s):
    if not s.get("n"):
        return f"    {name:34} —"
    extra = ""
    if "early" in s and s["early"].get("n") and s["late"].get("n"):
        extra = (f"  early {s['early']['hit']:.0%}/{s['early']['claimed']:.0%}"
                 f"  late {s['late']['hit']:.0%}/{s['late']['claimed']:.0%}")
    return (f"    {name:34} n {s['n']:4}  hit {s['hit']:.0%}  said {s['claimed']:.0%}  "
            f"z {s['z']:+.1f}  {s.get('verdict', ''):8}{extra}")


def report(out: dict) -> None:
    o = out["overall"]
    print(f"\n=== NFL MOST LIKELY — {out['n']} settled picks, {out['with_context']} matched to their game")
    print(_line("everything", o))
    print(_line("no scout flag at all", out["no_flag"]))
    print(f"    halves split at {out['split_day']}")
    print("\n--- THE SCOUT'S FLAGS (HOLDS = over-claimed in both halves, z ≤ −2)")
    for f, s in sorted(out["flags"].items(), key=lambda kv: kv[1].get("z", 0)):
        print(_line(f, s))
    for name, grp in out["bands"].items():
        print(f"\n--- BY {name.upper()}")
        for k, s in grp.items():
            print(_line(str(k), s))
    if out["td"]:
        print("\n--- TOUCHDOWNS")
        for name in ("by claim", "by position", "by team implied"):
            for k, s in out["td"].get(name, {}).items():
                print(_line(f"{name}: {k}", s))
        if out["td"].get("auc") is not None:
            print(f"    ranking (AUC of our chance against who scored): {out['td']['auc']:.3f}")
    print("\n--- DOES A HIGHER CHANCE HIT MORE? (AUC on our own picks; 0.5 = the order means nothing)")
    for m, a in out["ranking"].items():
        if a is not None:
            print(f"    {m:20} {a:.3f}")
    if out.get("losses_in_blowouts") is not None:
        print(f"\n    {out['losses_in_blowouts']:.0%} of the losses came in games decided by 17 or more")
    print("\n--- EXAMPLES (up to four per flag)")
    for f, ex in out["examples"].items():
        if ex:
            print(f"    {f}: " + " | ".join(ex))


def report_history(h: dict) -> None:
    print(f"\n=== THE FLAGS ON EVERY GAME, seasons {h['seasons']} (halves split at {h['split']})")
    print("    line = his last-five average; gap = flagged side's hit rate minus the same side's in unflagged games")
    for f in SC.FLAGS:
        for ms, res in sorted((h["flags"].get(f) or {}).items()):
            parts = [f"{half} {r['rate']:.1%} vs {r['base']:.1%} ({r['gap']:+.1%}, n {r['n']})"
                     for half, r in res.items()]
            both = len(res) == 2 and all(r["gap"] < -0.02 for r in res.values())
            print(f"    {f:20} {ms:18} " + "  ".join(parts) + ("   ← REAL, both halves" if both else ""))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The NFL Most Likely record, read like a football person would.")
    ap.add_argument("--ledger", default=str(ROOT / "data" / "ledger.db"))
    ap.add_argument("--history-db", default=str(ROOT / "data" / "history.db"))
    ap.add_argument("--history", action="store_true", help="replay the flags on every 2021+ game instead")
    ap.add_argument("--json", default="", help="also write the result here")
    a = ap.parse_args(argv)
    hist = _ro(Path(a.history_db))
    if a.history:
        h = replay(hist)
        report_history(h)
        result = h
    else:
        result = audit(_ro(Path(a.ledger)), hist)
        report(result)
    if a.json:
        Path(a.json).write_text(json.dumps(result, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
