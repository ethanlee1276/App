#!/usr/bin/env python3
"""Where the real record loses — read-only, on the box.

    cd /srv/qellys && sudo -u qellys python3 lossaudit.py
    sudo -u qellys python3 lossaudit.py --since 2026-09-01
    sudo -u qellys python3 lossaudit.py --sport nfl
    sudo -u qellys python3 lossaudit.py --json /tmp/lossaudit.json

Ethan, 2026-09-28: "Go" — after six free data sources in a row measured to
zero against past seasons. The projections already know what box scores
know; the next place to look is the graded record itself: where the picks
we published have actually lost, and whether that is the price, the
claim, the market, the side, or luck.

WHAT IT READS. The ledger (data/ledger.db), opened READ-ONLY — it writes
nothing and never repairs, re-grades or re-tags a row. Every settled bet
(won, lost or push; voids left out) in the books the site publishes,
each book on its own, never pooled — one pick can sit in more than one:

    Edge picks            main + paper (the headline record's own book)
    Most Likely, staked   likely_live
    Most Likely, paper    likely
    The one board         board (its tier is the grade)

HOW EACH SLICE IS SCORED. W-L-P; how often it hit, against what we
claimed (hit_prob) and against what the price needed to break even; units
and ROI at the stake journaled; and two z-scores:

    z vs price  — wins against the wins the prices implied. The "is it
                  luck?" number: between −2 and +2 the honest reading is
                  "not enough to say".
    z vs claim  — wins against the wins our probabilities claimed. Below
                  −2 the model OVER-CLAIMED on that slice: it said the
                  picks were likelier than they were.

THE CLOSE. Side-aware closing-line value, the ledger's own definitions
(engine/ledger._bet_clv in line points, _bet_price_clv in probability
points): a bet "beat the close" when the line or the price moved our way
after we took it. Winning while losing the close is luck; losing while
beating it is a good bet that missed.

THE PROJECTION. Per market, the mean of (actual − projection) over every
settled bet that journaled a projection, as a share of the projection:
a market whose projections run high loses its overs and wins its unders
for the same reason, and this is the number that says so.

THE LEAKS. At the end, every slice with at least MIN_N settled bets that
lost units and is two standard errors from its price or its claim, the
biggest loss first. That list is the work.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.ledger import _bet_clv, _bet_price_clv            # noqa: E402
from engine.odds import american_to_prob                        # noqa: E402

LEDGER = ROOT / "data" / "ledger.db"
BOOKS = (("Edge picks", ("main", "paper")),
         ("Most Likely, staked", ("likely_live",)),
         ("Most Likely, paper", ("likely",)),
         ("The one board", ("board",)))
SETTLED = ("won", "lost", "push")
#: A slice needs this many settled bets before it is named as a leak.
MIN_N = 30
#: And this far from its price or its claim.
LEAK_Z = -2.0
#: Price bands by break-even probability, with the American range each is.
PRICE_BANDS = ((0.75, 1.01, "-300 or shorter"), (0.667, 0.75, "-299 to -200"),
               (0.60, 0.667, "-199 to -150"), (0.524, 0.60, "-149 to -111"),
               (0.455, 0.524, "-110 to +120"), (0.0, 0.455, "+121 or longer"))
CLAIM_BANDS = ((0.80, 1.01, "80%+"), (0.70, 0.80, "70-80%"), (0.60, 0.70, "60-70%"),
               (0.50, 0.60, "50-60%"), (0.0, 0.50, "under 50%"))
COLUMNS = ("id", "sport", "date", "player", "market", "side", "line", "book", "odds", "projection",
           "hit_prob", "edge", "grade", "stake_units", "status", "actual", "pnl_units",
           "closing_line", "closing_odds", "category", "loss_cause")


def open_ledger(path) -> sqlite3.Connection:
    """The ledger, read-only: a URI connection in mode=ro cannot write,
    so the audit can never change the record it reads."""
    conn = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load(conn, since=None, sport=None) -> list[dict]:
    have = {r[1] for r in conn.execute("PRAGMA table_info(bets)")}
    cols = [c for c in COLUMNS if c in have]
    cats = sorted({c for _label, cs in BOOKS for c in cs})
    sql = (f"SELECT {', '.join(cols)} FROM bets WHERE status IN ({','.join('?' * len(SETTLED))}) "
           f"AND category IN ({','.join('?' * len(cats))})")
    args: list = list(SETTLED) + cats
    if since:
        sql += " AND date >= ?"
        args.append(since)
    if sport:
        sql += " AND LOWER(sport) = ?"
        args.append(sport.lower())
    out = []
    for r in conn.execute(sql + " ORDER BY date, id", args):
        d = {c: None for c in COLUMNS}
        d.update(dict(r))
        out.append(d)
    return out


def _implied(odds) -> float | None:
    try:
        return american_to_prob(int(odds)) if odds else None
    except (TypeError, ValueError):
        return None


def _band(p, bands) -> str:
    if p is None:
        return "no price"
    for lo, hi, label in bands:
        if lo <= p < hi:
            return label
    return bands[-1][2]


def close_verdict(b) -> str:
    """Beat, same, or lost the close — the line when it moved, the price
    when the line could not; "no close" when neither was captured."""
    line = _bet_clv(b)
    price = _bet_price_clv(b)
    if line is not None and line != 0:
        return "beat the close" if line > 0 else "lost the close"
    if price is not None and abs(price) >= 0.005:
        return "beat the close" if price > 0 else "lost the close"
    if line is not None or price is not None:
        return "same as the close"
    return "no close captured"


def score(bets: list) -> dict:
    """One slice's numbers (see the module docstring)."""
    w = sum(1 for b in bets if b["status"] == "won")
    lo = sum(1 for b in bets if b["status"] == "lost")
    p = sum(1 for b in bets if b["status"] == "push")
    graded = [b for b in bets if b["status"] in ("won", "lost")]
    units = sum(float(b["pnl_units"] or 0.0) for b in bets)
    staked = sum(float(b["stake_units"] or 0.0) for b in bets)
    out = {"n": w + lo, "w": w, "l": lo, "p": p, "units": round(units, 3),
           "roi": round(units / staked, 4) if staked else None,
           "hit": round(w / (w + lo), 4) if (w + lo) else None}
    for key, col in (("price", "odds"), ("claim", "hit_prob")):
        ps = [(_implied(b["odds"]) if col == "odds" else (float(b["hit_prob"]) if b["hit_prob"] is not None else None))
              for b in graded]
        pairs = [(pp, b["status"] == "won") for pp, b in zip(ps, graded) if pp is not None and 0 < pp < 1]
        if pairs:
            exp = sum(pp for pp, _ in pairs)
            var = sum(pp * (1 - pp) for pp, _ in pairs)
            got = sum(1 for _, won in pairs if won)
            out[f"{key}_avg"] = round(exp / len(pairs), 4)
            out[f"z_{key}"] = round((got - exp) / math.sqrt(var), 2) if var > 0 else None
        else:
            out[f"{key}_avg"], out[f"z_{key}"] = None, None
    return out


def _week(b) -> str:
    """The Monday of the bet's week — so a model change shows as a step.

    A football bet is dated by its week label ("2026-W03"), and read as a
    calendar date that is ISO week 3 — January. The box's first run
    (2026-09-29) filed every NFL bet under "week of 2026-01-12". The
    label is the week; say so."""
    import datetime as _dt
    import re
    m = re.match(r"^(\d{4})-W(\d{1,2})$", str(b["date"] or ""))
    if m:
        return f"{str(b.get('sport') or 'football').upper()} week {int(m.group(2))}"
    try:
        d = _dt.date.fromisoformat(str(b["date"])[:10])
    except ValueError:
        return "(no date)"
    return f"week of {(d - _dt.timedelta(days=d.weekday())).isoformat()}"


def slices(bets: list) -> dict:
    """{slice name: {value: score}} for one book."""
    keys = {
        "sport": lambda b: (b["sport"] or "").upper(),
        "market": lambda b: f"{(b['sport'] or '').upper()} {b['market']}",
        "side": lambda b: (b["side"] or "").upper(),
        "market and side": lambda b: f"{(b['sport'] or '').upper()} {b['market']} {(b['side'] or '').upper()}",
        "price": lambda b: _band(_implied(b["odds"]), PRICE_BANDS),
        "claimed": lambda b: _band(float(b["hit_prob"]) if b["hit_prob"] is not None else None, CLAIM_BANDS),
        "the close": close_verdict,
        "sportsbook": lambda b: (b["book"] or "").lower() or "(none)",
        "week": _week,
    }
    if any(b["category"] == "board" for b in bets):
        keys["tier"] = lambda b: b["grade"] or "(none)"
    out = {}
    for name, fn in keys.items():
        groups: dict = defaultdict(list)
        for b in bets:
            groups[fn(b)].append(b)
        order = (sorted(groups.items(), reverse=True) if name == "week"
                 else sorted(groups.items(), key=lambda kv: -len(kv[1])))
        out[name] = {k: score(v) for k, v in order}
    return out


def causes(bets: list) -> dict:
    """How the losses are tagged (engine/causes): blowout, short run,
    variance — or not yet swept."""
    c: dict = defaultdict(int)
    for b in bets:
        if b["status"] == "lost":
            tag = str(b["loss_cause"] or "not tagged yet")
            c["blowout" if tag.startswith("blowout") else "short run" if tag.startswith("short run") else tag] += 1
    return dict(sorted(c.items(), key=lambda kv: -kv[1]))


def projection_bias(bets: list, min_n: int = 15) -> list:
    """Per sport and market: mean (actual − projection), in the stat's units
    and as a share of the projection, with its standard error."""
    groups: dict = defaultdict(list)
    for b in bets:
        try:
            proj, act = float(b["projection"]), float(b["actual"])
        except (TypeError, ValueError):
            continue
        if proj > 0:
            groups[f"{(b['sport'] or '').upper()} {b['market']}"].append((act - proj, (act - proj) / proj))
    out = []
    for key, errs in groups.items():
        n = len(errs)
        if n < min_n:
            continue
        m = sum(e for e, _ in errs) / n
        rel = sum(r for _, r in errs) / n
        sd = (sum((e - m) ** 2 for e, _ in errs) / (n - 1)) ** 0.5 if n > 1 else 0.0
        se = sd / math.sqrt(n) if n else 0.0
        out.append({"market": key, "n": n, "mean_miss": round(m, 2), "share": round(rel, 3),
                    "t": round(m / se, 2) if se else None})
    return sorted(out, key=lambda r: -abs(r["t"] or 0))


def leaks(report: dict, min_n: int = MIN_N, z: float = LEAK_Z) -> list:
    """Every slice with enough bets that lost units and sits ``z`` or
    further below its price or its claim — the biggest loss first."""
    out = []
    for book, rep in report["books"].items():
        for name, groups in rep["slices"].items():
            for value, s in groups.items():
                if s["n"] < min_n or s["units"] >= 0:
                    continue
                zp, zc = s.get("z_price"), s.get("z_claim")
                why = []
                if zp is not None and zp <= z:
                    why.append(f"hit {s['hit']:.0%} where the prices needed {s['price_avg']:.0%}")
                if zc is not None and zc <= z:
                    why.append(f"hit {s['hit']:.0%} where we claimed {s['claim_avg']:.0%}")
                if why:
                    out.append({"book": book, "slice": name, "value": value, "n": s["n"],
                                "units": s["units"], "roi": s["roi"], "why": "; ".join(why)})
    return sorted(out, key=lambda r: r["units"])


def overclaimed(report: dict, min_n: int = MIN_N, z: float = LEAK_Z) -> list:
    """Every slice where we said the picks were likelier than they were —
    ``z`` or further below the claim — money or not. Most Likely ranks by
    that claim, so a slice that over-claims is seated too high even while
    its price keeps it in the black."""
    out = []
    for book, rep in report["books"].items():
        for name, groups in rep["slices"].items():
            for value, s in groups.items():
                zc = s.get("z_claim")
                if s["n"] >= min_n and zc is not None and zc <= z:
                    out.append({"book": book, "slice": name, "value": value, "n": s["n"], "hit": s["hit"],
                                "claimed": s["claim_avg"], "units": s["units"], "z": zc})
    return sorted(out, key=lambda r: r["z"])


def audit(conn, since=None, sport=None) -> dict:
    rows = load(conn, since, sport)
    books = {}
    for label, cats in BOOKS:
        mine = [b for b in rows if b["category"] in cats]
        if not mine:
            continue
        books[label] = {"total": score(mine), "slices": slices(mine), "causes": causes(mine),
                        "projection": projection_bias(mine),
                        "first": mine[0]["date"], "last": mine[-1]["date"]}
    report = {"since": since, "sport": sport, "books": books}
    report["leaks"] = leaks(report)
    report["overclaimed"] = overclaimed(report)
    return report


def _pct(v) -> str:
    return "  —  " if v is None else f"{v * 100:4.0f}%"


def _line(label: str, s: dict) -> str:
    roi = "   —  " if s["roi"] is None else f"{s['roi'] * 100:+5.1f}%"
    zp = "  —" if s.get("z_price") is None else f"{s['z_price']:+4.1f}"
    zc = "  —" if s.get("z_claim") is None else f"{s['z_claim']:+4.1f}"
    wlp = f"{s['w']}-{s['l']}" + (f"-{s['p']}" if s["p"] else "")
    return (f"  {label[:34]:34} {wlp:>11}  hit {_pct(s['hit'])}  claimed {_pct(s.get('claim_avg'))}  "
            f"needed {_pct(s.get('price_avg'))}  {s['units']:+8.2f}u  ROI {roi}  z {zp} / {zc}")


def render(report: dict, top: int = 12) -> str:
    out = []
    scope = ", ".join(x for x in (report.get("sport") and report["sport"].upper(),
                                  report.get("since") and f"since {report['since']}") if x)
    out.append(f"LOSS AUDIT — every settled bet{f' ({scope})' if scope else ''}, each book on its own")
    out.append("  z = wins against the price / against our claim; between -2 and +2 is 'not enough to say'.\n")
    if not report["books"]:
        out.append("  No settled bets in the published books.")
        return "\n".join(out)
    for book, rep in report["books"].items():
        out.append(f"=== {book}  ({rep['first']} to {rep['last']})")
        out.append(_line("ALL", rep["total"]))
        for name, groups in rep["slices"].items():
            shown = [(k, s) for k, s in groups.items() if s["n"] >= 5][:top]
            if len(shown) < 2 and name not in ("tier", "the close"):
                continue
            out.append(f"  -- by {name}")
            out += [_line(str(k), s) for k, s in shown]
        if rep["causes"]:
            out.append("  -- how the losses are tagged: " + ", ".join(f"{k} {v}" for k, v in rep["causes"].items()))
        if rep["projection"]:
            out.append("  -- projection vs what happened (actual − projection; t beyond ±2 is a real lean)")
            for r in rep["projection"][:top]:
                t = "—" if r["t"] is None else f"{r['t']:+.1f}"
                out.append(f"     {r['market'][:30]:30} n {r['n']:4}  {r['mean_miss']:+7.2f} a bet "
                           f"({r['share'] * 100:+.0f}% of the projection)  t {t}")
        out.append("")
    lk = report["leaks"]
    out.append(f"THE LEAKS — slices of {MIN_N}+ settled bets that lost units and sit {abs(LEAK_Z):.0f}+ "
               f"standard errors below their price or their claim, biggest loss first:")
    if not lk:
        out.append("  None yet. Nothing loses by more than luck explains — or there are not enough bets to say.")
    for r in lk[:25]:
        roi = "—" if r["roi"] is None else f"{r['roi'] * 100:+.1f}%"
        out.append(f"  {r['units']:+8.2f}u  {r['book']} · {r['slice']}: {r['value']}  (n {r['n']}, ROI {roi}) — {r['why']}")
    oc = report.get("overclaimed") or []
    out.append(f"\nOVER-CLAIMED — slices of {MIN_N}+ where we said likelier than it was "
               f"({abs(LEAK_Z):.0f}+ standard errors), money or not:")
    if not oc:
        out.append("  None yet.")
    for r in oc[:25]:
        out.append(f"  z {r['z']:+.1f}  {r['book']} · {r['slice']}: {r['value']}  (n {r['n']}) — "
                   f"claimed {r['claimed']:.0%}, hit {r['hit']:.0%}, {r['units']:+.2f}u")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--since", help="only bets dated on or after YYYY-MM-DD")
    ap.add_argument("--sport", help="one league: nfl, cfb, mlb, nba, wnba")
    ap.add_argument("--db", default=str(LEDGER), help="the ledger (default data/ledger.db)")
    ap.add_argument("--json", help="also write the full report here")
    a = ap.parse_args(argv)
    if not Path(a.db).exists():
        print(f"No ledger at {a.db}.")
        return 1
    report = audit(open_ledger(a.db), a.since, a.sport)
    print(render(report))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1, default=str)
        print(f"\nFull report: {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
