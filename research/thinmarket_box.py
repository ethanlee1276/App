#!/usr/bin/env python3
"""EXP-R06 — the books' chance for the board's THIN picks, from their main lines — tried on weeks it never saw.

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/thinmarket_box.py
    python3 research/thinmarket_box.py --db data/ledger.db --snapshots data/cache/line_history.jsonl

THE GAP IT ADDRESSES. The NFL one board shows the books' price where our
chance runs above it (likelyboard.trust_price), but only where three books
or more price both sides of the pick's own line. On the box's first full
board under that rule, 133 of 230 player picks had no such field (Ethan's
paste, 2026-10-17): alternate rungs, mostly, which books hang one-sided.
They keep our chance, unjudged — and they are where our chance can run
furthest from the middle.

THE MARKET'S CHANCE FOR THEM (engine/fieldcurve). Each book's MAIN line is
two-sided, so it pins that book's middle; with a shape measured on
2022-2025 games (variance = PHI × mean per market, fieldcurvefit.py) the
field's middle — the median of three books or more — gives the chance at
the pick's own line. From our own snapshots (data/cache/line_history.jsonl,
which keep every book's main line, both sides): each book's last two-sided
quote for the player and market in the SNAPSHOT_HOURS before the pick was
journaled, never after it, never after the game's start. Nothing else.

THE POPULATION. Settled (won or lost) NFL picks in the one board's journal
(category ``board``) in a market with a measured shape, for which
pricetrust.attach_market found NO market chance — no journaled field and
no three-book field at the pick's own line in the snapshots. Exactly the
picks the live rule leaves alone.

THE TEST AND THE BAR — pricetrust's, imported, unchanged: shown = ours −
w × max(0, ours − market − T) on the same grid, w and T chosen each week on
the weeks before it, and PASSES when every held-out week's log loss is no
worse than our chance alone AND the pooled log loss is better; NOT YET
under MIN_WEEKS held-out weeks or MIN_HELD picks; otherwise FAILS.

HOW STRICT THAT IS, tried on made-up seasons of 80 thin picks a week
(tests/test_thin_market.py): where the curve is the truth and our chance a
12-point overclaim it passes 33 runs in 40; where our chance is the truth,
1 in 40. A FAIL means not shown, not disproved.

ONE READ (written before any run, 2026-10-19). The decision is made on the
FIRST held-out weeks, in order, at which the walk has both MIN_WEEKS weeks
and MIN_HELD picks — fixed from then on, the same on every later run.
Later weeks are printed beneath it as description, so a run that happens to
come out well can never be chosen over one that did not.

A PASS CHANGES NOTHING BY ITSELF. It is reported to Ethan with the w and T
the decision's last week chose; the board extends the rule to thin picks
only on his yes.

DESCRIPTION, DECIDING NOTHING: how many thin picks the curve could price,
by market; the gap bands; and, for comparison, the single book's own price
at the pick's line as the board journaled it (hit_prob − edge — one book,
and on a one-sided rung a guessed vig, which is why it is never the test).

Read-only: the ledger opens mode=ro; the snapshot file is streamed.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pricetrust as PT                                           # noqa: E402
from engine import fieldcurve as FC                               # noqa: E402

BOOK = "board"
SPORT = "nfl"


def thin_picks(bets: list[dict], snapshots=None) -> tuple[list[dict], dict]:
    """The board's settled picks with no market chance from pricetrust, in
    a market with a shape; and the count of what pricetrust found."""
    board = [b for b in bets if b.get("category") == BOOK]
    found = PT.attach_market(board, snapshots)
    thin = [b for b in board if b["market_src"] == "none" and b.get("market") in FC.PHI
            and str(b.get("side") or "").upper() in ("OVER", "UNDER")]
    return thin, found


def curve_quotes(bets: list[dict], path=None) -> dict:
    """``{bet id: [(book, line, over, under)]}`` — each book's last two-sided
    main-line quote for the bet's player and market in the window before
    it was journaled, never after the game's start."""
    from engine.odds import pair_is_sane
    from engine.sources.oddsapi import normalize_name
    want: dict = defaultdict(list)
    for b in bets:
        t = PT._epoch(b.get("ts"))
        if t is None or not b.get("player") or not b.get("market"):
            continue
        want[(normalize_name(b["player"]), b["market"])].append((b["id"], t))
    if not want:
        return {}
    names: dict = {}

    def norm(p):
        n = names.get(p)
        if n is None:
            n = names[p] = normalize_name(p)
        return n

    window = PT.SNAPSHOT_HOURS * 3600.0
    latest: dict = {}
    for r in PT._snapshot_rows(path, {k[1] for k in want}, {k[0] for k in want}, norm):
        hits = want.get((norm(r.get("player") or ""), r.get("market")))
        if not hits:
            continue
        try:
            ts = float(r["ts"])
            line = float(r["line"])
        except (KeyError, TypeError, ValueError):
            continue
        if r.get("start_ts") is not None and ts >= float(r["start_ts"]):
            continue
        book = str(r.get("book") or "").lower()
        if not book or book == "proxy" or not pair_is_sane(r.get("over_odds"), r.get("under_odds")):
            continue
        for bid, t in hits:
            if t - window <= ts <= t:
                k = (bid, book)
                if k not in latest or ts >= latest[k][0]:
                    latest[k] = (ts, line, int(r["over_odds"]), int(r["under_odds"]))
    out: dict = defaultdict(list)
    for (bid, book), (_ts, line, o, u) in latest.items():
        out[bid].append((book, line, o, u))
    return dict(out)


def attach_curve(bets: list[dict], quotes: dict) -> Counter:
    """Each thin pick's ``market_p`` from the field's curve; the count of
    picks priced, by market."""
    priced: Counter = Counter()
    for b in bets:
        b["market_p"] = None
        try:
            line = float(b["line"])
        except (TypeError, ValueError):
            continue
        got = FC.field_chance(b["market"], quotes.get(b["id"]) or (), line, b.get("side"))
        if got:
            b["market_p"], b["curve_books"], b["curve_mean"] = got
            priced[b["market"]] += 1
    return priced


def decision_weeks(weeks: list[dict]) -> tuple[list[dict], list[dict]]:
    """(the decision's weeks, the weeks after them) — ONE READ: the first
    held-out weeks at which the walk has MIN_WEEKS weeks and MIN_HELD picks."""
    held = 0
    for i, w in enumerate(weeks):
        held += w["n"]
        if i + 1 >= PT.MIN_WEEKS and held >= PT.MIN_HELD:
            return weeks[:i + 1], weeks[i + 1:]
    return weeks, []


def single_book(conn, bets: list[dict]) -> dict:
    """``{bet id: the board's own journaled price at the pick's line}``
    (hit_prob − edge) — for the comparison line only."""
    ids = [b["id"] for b in bets]
    out = {}
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        q = f"SELECT id, hit_prob, edge FROM bets WHERE id IN ({','.join('?' * len(part))})"
        for bid, hp, edge in conn.execute(q, part):
            try:
                p = float(hp) - float(edge)
            except (TypeError, ValueError):
                continue
            if 0.0 < p < 1.0:
                out[bid] = p
    return out


def study(conn, snapshots=None) -> dict:
    bets = PT.load(conn, SPORT)
    thin, found = thin_picks(bets, snapshots)
    priced = attach_curve(thin, curve_quotes(thin, snapshots))
    rows = PT.scorable(thin)
    weeks = PT.walk(rows)
    decide, later = decision_weeks(weeks)
    rep = {"board_settled": sum(found.values()), "pricetrust_sources": dict(found), "thin": len(thin),
           "thin_by_market": dict(Counter(b["market"] for b in thin)), "curve_priced": dict(priced),
           "scored": len(rows), "decision": {**PT.verdict(decide), "walk": decide},
           "later": later, "bands": PT.bands(rows)}
    if decide:
        rep["decision"]["choice"] = {"w": decide[-1]["w"], "T": decide[-1]["T"]}
    single = single_book(conn, thin)
    comp = []
    for b in thin:
        if b["id"] in single:
            comp.append(dict(b, market_p=single[b["id"]]))
    srows = PT.scorable(comp)
    rep["single_book"] = {"scored": len(srows), **PT.verdict(PT.walk(srows))}
    return rep


def render(rep: dict) -> str:
    out = ["EXP-R06 — THE BOOKS' CHANCE FOR THE NFL BOARD'S THIN PICKS, from their main lines",
           f"  board picks settled: {rep['board_settled']}  (pricetrust found a market for "
           + ", ".join(f"{k} {v}" for k, v in sorted(rep['pricetrust_sources'].items())) + ")",
           f"  thin picks in a market with a shape: {rep['thin']}  ("
           + ", ".join(f"{k} {v}" for k, v in sorted(rep['thin_by_market'].items())) + ")",
           f"  priced by the field's curve (3+ books' main lines): {sum(rep['curve_priced'].values())}  ("
           + ", ".join(f"{k} {v}" for k, v in sorted(rep['curve_priced'].items())) + ")",
           f"  scored: {rep['scored']}", ""]
    d = rep["decision"]
    out.append(f"DECISION (one read: the first held-out weeks reaching {PT.MIN_WEEKS} weeks and "
               f"{PT.MIN_HELD} picks): {d['verdict']} — {d['why']}")
    if d.get("held"):
        out.append(f"  pooled held-out log loss: ours {d['base_ll']:.4f}  with the rule {d['rule_ll']:.4f}  "
                   f"({d['held']} picks, {d['weeks']} weeks)")
    for w in d["walk"]:
        flag = "  worse" if w["rule_sum"] > w["base_sum"] + 1e-9 else ""
        out.append(f"     {w['week']:22} n {w['n']:4}  w {w['w']:.1f} T {w['T']:.2f}  moved {w['moved']:4}  "
                   f"hit {PT._pct(w['hit'])} ours {PT._pct(w['ours'])} market {PT._pct(w['market'])}  "
                   f"log loss {w['base_sum'] / w['n']:.4f} → {w['rule_sum'] / w['n']:.4f}{flag}")
    if d.get("choice"):
        out.append(f"  the decision's last week chose w {d['choice']['w']:.1f}, T {d['choice']['T']:.2f}")
    if rep["later"]:
        out.append("  -- after the decision's weeks (description, decides nothing)")
        for w in rep["later"]:
            out.append(f"     {w['week']:22} n {w['n']:4}  log loss {w['base_sum'] / w['n']:.4f} → "
                       f"{w['rule_sum'] / w['n']:.4f}")
    if rep["bands"]:
        out.append("  -- by how far our chance ran above the curve (all scored, describes only)")
        for b in rep["bands"]:
            zo = "—" if b["z_ours"] is None else f"{b['z_ours']:+.1f}"
            zm = "—" if b["z_market"] is None else f"{b['z_market']:+.1f}"
            out.append(f"     {b['band']:24} n {b['n']:4}  hit {PT._pct(b['hit'])}  ours "
                       f"{PT._pct(b['ours'])} (z {zo})  curve {PT._pct(b['market'])} (z {zm})")
    s = rep["single_book"]
    out.append(f"  -- for comparison only: the one book's own price at the line, {s['scored']} scored: "
               f"{s['verdict']}" + (f" (log loss {s['base_ll']:.4f} → {s['rule_ll']:.4f})" if s.get("held") else ""))
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(PT.LEDGER))
    ap.add_argument("--snapshots", help="the odds snapshots (default data/cache/line_history.jsonl)")
    ap.add_argument("--json", help="also write the report here")
    a = ap.parse_args(argv)
    if not Path(a.db).exists():
        print(f"No ledger at {a.db}.")
        return 1
    rep = study(PT.open_ledger(a.db), a.snapshots)
    print(render(rep))
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
