#!/usr/bin/env python3
"""Trust the price more where our chance runs far above it? — tried on weeks it never saw.

    cd /srv/qellys && sudo -u qellys python3 pricetrust.py
    sudo -u qellys python3 pricetrust.py --sport nfl
    sudo -u qellys python3 pricetrust.py --json /tmp/pricetrust.json

Step 109, from Ethan's loss-audit pastes of 2026-10-15: on the one board,
the picks whose chance ran furthest above the price were the furthest
wrong — claimed 65%, hit 53%, 367 NFL picks; the 70-80% claims hit 59%.
The idea waiting in the runbook (H): "measure, on settled picks held out
by week, whether pulling our chance part of the way toward the price's
de-vigged chance would have been closer to what happened, with the bar
set before the run (every held-out week no worse, the pooled log loss
better). Nothing changes unless it clears; your call."

WHAT IT READS. The ledger (data/ledger.db), opened READ-ONLY, and our own
odds snapshots (data/cache/line_history.jsonl), streamed. It writes
nothing. Every pick settled won or lost (a push or void has no outcome to
score) in the books the site publishes, each book on its own, as
lossaudit.py splits them:

    Edge picks            main + paper
    Most Likely, staked   likely_live
    Most Likely, paper    likely
    The one board         board

and within each book each sport on its own: a week is a sport's week (the
NFL's "2026-W03", every other league's calendar week from its Monday).

OUR CHANCE is the row's `hit_prob`, the number the page showed.

THE MARKET'S CHANCE AT PICK TIME, for the side we took, in this order:

  1. `fair_consensus`, journaled with the row (the Edge book's rows): the
     field's de-vigged fair for the over, so an under is one minus it.
  2. Otherwise rebuilt from our own snapshots: each book's last quote at
     the bet's own line in the SNAPSHOT_HOURS before the pick was
     journaled, never after it and never after the game's start; books
     quoting both sides only (a one-sided quote would need a guessed
     vig); de-vigged and the median taken by `engine.odds.consensus_fair`,
     the function that writes `fair_consensus`, with its three-book floor.
  3. Otherwise none, and the pick is left out and counted. Never the
     close (it is after the pick), never the price we took with a vig
     assumed off it.

THE RULE BEING TRIED, one family, written before any run:

    shown = ours − w × max(0, ours − market − T)

    w   0, 0.1, 0.2 … 1.0   how much of the gap to give back to the price
    T   0, .05, .10, .15     how far above the market before any is given

Only where our chance runs ABOVE the market (that is the idea); a pick
whose chance sits at or under the market keeps it. w = 0 is "change
nothing", and it is always on the menu.

HOW IT IS TRIED. Week by week in order. For each week with at least
MIN_TRAIN settled picks before it, w and T are chosen on every earlier
week (the lowest log loss; a tie goes to the smaller change) and scored
on that week, which chose nothing. The score is log loss, the penalty
for the chance we showed against what happened (lower is closer);
Brier is printed beside it and judges nothing.

THE BAR, WRITTEN BEFORE ANY RUN — the contract:

  * PASSES when every held-out week's log loss with the rule is no worse
    than without it, AND the pooled held-out log loss is better.
  * NOT YET when there are fewer than MIN_WEEKS held-out weeks or
    MIN_HELD held-out picks: not enough to judge either way.
  * otherwise FAILS.

How strict that is, tried on made-up seasons the NFL board's size (about
180 picks a week, five held-out weeks): where the market is right and our
extra chance is pure overclaim it passes about three runs in four; where
our chance is right, about one in twenty to forty; where the truth is half
way it mostly fails. A FAIL means not shown, not disproved.

Changing the grid or these constants after seeing a run is fitting the
bar. A PASS changes nothing by itself: it is reported to Ethan with the
w and T the latest week chose, and the board moves only on his yes.

Also printed, as description only (every settled pick at once, so it
judges nothing): how the picks did by how far our chance ran above the
market, and how many picks had no market chance to measure against.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

LEDGER = ROOT / "data" / "ledger.db"
BOOKS = (("Edge picks", ("main", "paper")),
         ("Most Likely, staked", ("likely_live",)),
         ("Most Likely, paper", ("likely",)),
         ("The one board", ("board",)))
COLUMNS = ("id", "sport", "date", "game_day", "ts", "player", "market", "side", "line",
           "book", "odds", "hit_prob", "status", "category", "fair_consensus")

#: The rule's menu (see THE RULE above). Written before any run.
GRID_W = tuple(round(i / 10, 1) for i in range(11))
GRID_T = (0.0, 0.05, 0.10, 0.15)
#: A week is scored only with this many settled picks before it to choose on.
MIN_TRAIN = 60
#: The bar needs this many held-out weeks and picks before it judges.
MIN_WEEKS = 3
MIN_HELD = 100
#: A snapshot older than this before the pick is not the price it was taken against.
SNAPSHOT_HOURS = 6.0
#: Log loss of a certainty is infinite; every chance is held inside this.
CLIP = 0.005
#: How far our chance ran above the market, for the description.
GAP_BANDS = ((0.15, 9.0, "15+ points above"), (0.10, 0.15, "10-15 above"),
             (0.05, 0.10, "5-10 above"), (0.0, 0.05, "0-5 above"),
             (-9.0, 0.0, "at or under the market"))
_WEEK = re.compile(r"^(\d{4})-W(\d{1,2})$")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")


def open_ledger(path) -> sqlite3.Connection:
    """The ledger, read-only: a mode=ro connection cannot write."""
    conn = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load(conn, sport=None) -> list[dict]:
    """Every pick settled won or lost in the published books."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(bets)")}
    cols = [c for c in COLUMNS if c in have]
    cats = sorted({c for _label, cs in BOOKS for c in cs})
    sql = (f"SELECT {', '.join(cols)} FROM bets WHERE status IN ('won','lost') "
           f"AND category IN ({','.join('?' * len(cats))})")
    args: list = list(cats)
    if sport:
        sql += " AND LOWER(sport) = ?"
        args.append(sport.lower())
    out = []
    for r in conn.execute(sql + " ORDER BY id", args):
        d = {c: None for c in COLUMNS}
        d.update(dict(r))
        out.append(d)
    return out


def under(side) -> bool:
    return str(side or "").upper() in ("UNDER", "NO")


def week(b) -> str:
    """The sport's week: the NFL's own label, or the Monday of the day."""
    m = _WEEK.match(str(b.get("date") or ""))
    if m:
        return f"{m.group(1)}-W{int(m.group(2)):02d}"
    for k in ("game_day", "date", "ts"):
        v = str(b.get(k) or "")
        if _ISO.match(v):
            d = dt.date.fromisoformat(v[:10])
            return f"week of {(d - dt.timedelta(days=d.weekday())).isoformat()}"
    return ""


def _epoch(ts) -> float | None:
    """The journal's `ts` (UTC, written without a zone) as a UNIX time."""
    try:
        d = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.timestamp()


def _field(raw: str, key: str):
    """One string field read straight off a snapshot line, or None when
    the line is not in `record_snapshots`' plain shape."""
    tag = f'"{key}": "'
    i = raw.find(tag)
    if i < 0:
        return None
    j = raw.find('"', i + len(tag))
    s = raw[i + len(tag):j]
    return s if j > 0 and "\\" not in s else None


def _snapshot_rows(path, markets, people, norm):
    """The snapshot file's rows of these markets and players. The box's
    file is millions of rows, so a line is parsed only once its market and
    player, read straight off the text, are ones a bet asks about."""
    from engine import linemoves
    p = Path(path) if path else linemoves.HISTORY_PATH
    if not p.exists():
        return
    with p.open(encoding="utf-8") as fh:
        for raw in fh:
            m = _field(raw, "market")
            if m is not None and m not in markets:
                continue
            who = _field(raw, "player")
            if who is not None and norm(who) not in people:
                continue
            try:
                r = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(r, dict) and r.get("market") in markets:
                yield r


def snapshot_fairs(bets, path=None) -> dict:
    """``{bet id: (the market's chance for the bet's side, books)}`` rebuilt
    from our own snapshots (see THE MARKET'S CHANCE, 2)."""
    from engine.models import SportsbookLine
    from engine.odds import consensus_fair, pair_is_sane
    from engine.sources.oddsapi import normalize_name
    want: dict = defaultdict(list)
    side_of = {}
    for b in bets:
        t = _epoch(b.get("ts"))
        try:
            ln = round(float(b["line"]), 1)
        except (TypeError, ValueError):
            continue
        if t is None or not b.get("player") or not b.get("market"):
            continue
        want[(normalize_name(b["player"]), b["market"], ln)].append((b["id"], t))
        side_of[b["id"]] = (ln, under(b.get("side")))
    if not want:
        return {}
    markets = {k[1] for k in want}
    people = {k[0] for k in want}
    names: dict = {}

    def norm(p):
        n = names.get(p)
        if n is None:
            n = names[p] = normalize_name(p)
        return n

    latest: dict = {}
    window = SNAPSHOT_HOURS * 3600.0
    for r in _snapshot_rows(path, markets, people, norm):
        n = norm(r.get("player") or "")
        try:
            hits = want.get((n, r["market"], round(float(r["line"]), 1)))
            ts = float(r["ts"])
        except (KeyError, TypeError, ValueError):
            continue
        if not hits:
            continue
        if r.get("start_ts") is not None and ts >= float(r["start_ts"]):
            continue                                  # an in-play price
        book = str(r.get("book") or "").lower()
        if not book or book == "proxy" or not pair_is_sane(r.get("over_odds"), r.get("under_odds")):
            continue
        for bid, t in hits:
            if t - window <= ts <= t:
                k = (bid, book)
                if k not in latest or ts >= latest[k][0]:
                    latest[k] = (ts, int(r["over_odds"]), int(r["under_odds"]))
    per: dict = defaultdict(list)
    for (bid, book), (_ts, o, u) in latest.items():
        per[bid].append(SportsbookLine(book=book, line=side_of[bid][0], over_odds=o, under_odds=u))
    out = {}
    for bid, lines in per.items():
        got = consensus_fair(lines, side_of[bid][0])
        if got:
            fair_over, books = got
            out[bid] = (1.0 - fair_over if side_of[bid][1] else fair_over, books)
    return out


def attach_market(bets, snapshots=None) -> dict:
    """Give each bet its `market` chance and where it came from; returns
    the count by source (see THE MARKET'S CHANCE)."""
    need = []
    for b in bets:
        b["market_p"], b["market_src"] = None, "none"
        fc = b.get("fair_consensus")
        if fc is not None:
            try:
                fc = float(fc)
            except (TypeError, ValueError):
                fc = None
        if fc is not None and 0.0 < fc < 1.0:
            b["market_p"] = 1.0 - fc if under(b.get("side")) else fc
            b["market_src"] = "journaled"
        else:
            need.append(b)
    found = snapshot_fairs(need, snapshots) if need else {}
    for b in need:
        if b["id"] in found:
            b["market_p"], b["market_src"] = found[b["id"]][0], "snapshots"
    counts: dict = defaultdict(int)
    for b in bets:
        counts[b["market_src"]] += 1
    return dict(counts)


def shown(ours: float, market: float, w: float, t: float) -> float:
    """The rule: give back share ``w`` of the gap beyond ``t``."""
    return ours - w * max(0.0, ours - market - t)


def logloss(p: float, won: bool) -> float:
    p = min(1.0 - CLIP, max(CLIP, p))
    return -math.log(p if won else 1.0 - p)


def _brier(p: float, won: bool) -> float:
    return (p - (1.0 if won else 0.0)) ** 2


def _sum(rows, w, t, score=logloss) -> float:
    return sum(score(shown(r["ours"], r["market"], w, t), r["won"]) for r in rows)


def fit(rows) -> tuple[float, float]:
    """(w, T) with the lowest log loss on ``rows``; a tie goes to the
    smaller change (smaller w, then larger T)."""
    best = None
    for w in GRID_W:
        for t in (GRID_T if w else (0.0,)):
            key = (round(_sum(rows, w, t), 9), w, -t)
            if best is None or key < best:
                best = key
    return best[1], -best[2] + 0.0


def scorable(bets) -> list[dict]:
    """The bets with a chance, a market chance and a week, in the walk's shape."""
    out = []
    for b in bets:
        try:
            ours = float(b["hit_prob"])
        except (TypeError, ValueError):
            continue
        wk = week(b)
        if b.get("market_p") is None or not (0.0 < ours < 1.0) or not wk:
            continue
        out.append({"id": b["id"], "week": wk, "ours": ours, "market": float(b["market_p"]),
                    "won": b["status"] == "won"})
    return out


def walk(rows) -> list[dict]:
    """Each week scored with the w and T every earlier week chose."""
    weeks = sorted({r["week"] for r in rows})
    out = []
    for wk in weeks:
        train = [r for r in rows if r["week"] < wk]
        test = [r for r in rows if r["week"] == wk]
        if len(train) < MIN_TRAIN or not test:
            continue
        w, t = fit(train)
        n = len(test)
        out.append({"week": wk, "n": n, "train": len(train), "w": w, "T": t,
                    "moved": sum(1 for r in test if shown(r["ours"], r["market"], w, t) != r["ours"]),
                    "hit": sum(r["won"] for r in test) / n,
                    "ours": sum(r["ours"] for r in test) / n,
                    "market": sum(r["market"] for r in test) / n,
                    "base_sum": _sum(test, 0.0, 0.0), "rule_sum": _sum(test, w, t),
                    "base_brier": _sum(test, 0.0, 0.0, _brier) / n,
                    "rule_brier": _sum(test, w, t, _brier) / n})
    return out


def verdict(weeks: list[dict]) -> dict:
    """THE BAR (see the docstring), on the walk's weeks."""
    held = sum(w["n"] for w in weeks)
    base = sum(w["base_sum"] for w in weeks)
    rule = sum(w["rule_sum"] for w in weeks)
    worse = [w["week"] for w in weeks if w["rule_sum"] > w["base_sum"] + 1e-9]
    out = {"weeks": len(weeks), "held": held, "worse_weeks": worse,
           "base_ll": round(base / held, 5) if held else None,
           "rule_ll": round(rule / held, 5) if held else None}
    if len(weeks) < MIN_WEEKS or held < MIN_HELD:
        out["verdict"] = "NOT YET"
        out["why"] = (f"{len(weeks)} held-out week(s) and {held} pick(s); the bar needs "
                      f"{MIN_WEEKS} weeks and {MIN_HELD} picks")
    elif not worse and rule < base - 1e-9:
        out["verdict"] = "PASSES"
        out["why"] = "every held-out week no worse, and the pooled log loss better"
    else:
        out["verdict"] = "FAILS"
        why = []
        if worse:
            why.append(f"{len(worse)} of {len(weeks)} held-out weeks worse ({', '.join(worse)})")
        if not rule < base - 1e-9:
            why.append("the pooled log loss no better")
        out["why"] = "; ".join(why)
    return out


def bands(rows) -> list[dict]:
    """How the picks did by how far our chance ran above the market —
    every settled pick at once, so description only."""
    groups: dict = defaultdict(list)
    for r in rows:
        gap = r["ours"] - r["market"]
        label = next(lb for lo, hi, lb in GAP_BANDS if lo < gap <= hi)
        groups[label].append(r)
    out = []
    for _lo, _hi, label in GAP_BANDS:
        g = groups.get(label) or []
        if not g:
            continue
        n = len(g)
        won = sum(r["won"] for r in g)
        row = {"band": label, "n": n, "hit": won / n,
               "ours": sum(r["ours"] for r in g) / n, "market": sum(r["market"] for r in g) / n}
        for k in ("ours", "market"):
            var = sum(r[k] * (1 - r[k]) for r in g)
            row[f"z_{k}"] = round((won - sum(r[k] for r in g)) / math.sqrt(var), 2) if var > 0 else None
        out.append(row)
    return out


def study(bets, snapshots=None) -> dict:
    """The whole report: each book, each sport, walked and judged."""
    coverage = attach_market(bets, snapshots)
    books = {}
    for label, cats in BOOKS:
        mine = [b for b in bets if b["category"] in cats]
        if not mine:
            continue
        sports = {}
        for sp in sorted({str(b["sport"] or "").lower() for b in mine}):
            these = [b for b in mine if str(b["sport"] or "").lower() == sp]
            rows = scorable(these)
            weeks = walk(rows)
            src: dict = defaultdict(int)
            for b in these:
                src[b["market_src"]] += 1
            rep = {"settled": len(these), "sources": dict(src), "scored": len(rows),
                   "walk": weeks, "bands": bands(rows), **verdict(weeks)}
            if weeks:
                rep["latest_choice"] = {"w": weeks[-1]["w"], "T": weeks[-1]["T"]}
            sports[sp] = rep
        books[label] = sports
    return {"coverage": coverage, "books": books}


def _pct(v) -> str:
    return "  —  " if v is None else f"{v * 100:4.1f}%"


def render(report: dict) -> str:
    out = ["TRUST THE PRICE MORE WHERE OUR CHANCE RUNS FAR ABOVE IT? — each week scored on the "
           "w and T the earlier weeks chose",
           "  rule: shown = ours − w × max(0, ours − market − T);  bar: every held-out week no "
           "worse AND the pooled log loss better",
           "  market chance at pick time: " + (", ".join(
               f"{k} {v}" for k, v in sorted(report["coverage"].items())) or "no picks") + "\n"]
    if not report["books"]:
        out.append("  No settled picks in the published books.")
        return "\n".join(out)
    for book, sports in report["books"].items():
        for sp, r in sports.items():
            src = ", ".join(f"{k} {v}" for k, v in sorted(r["sources"].items()))
            out.append(f"=== {book} · {sp.upper()}  — {r['settled']} settled, {r['scored']} with a "
                       f"market chance ({src})")
            out.append(f"  VERDICT: {r['verdict']} — {r['why']}")
            if r["walk"]:
                out.append(f"  pooled held-out log loss: as shown {r['base_ll']:.4f}  with the rule "
                           f"{r['rule_ll']:.4f}  (lower is closer; {r['held']} picks, {r['weeks']} weeks)")
                out.append("  -- each held-out week (w and T chosen on the weeks before it)")
                for w in r["walk"]:
                    flag = "  worse" if w["rule_sum"] > w["base_sum"] + 1e-9 else ""
                    out.append(f"     {w['week']:22} n {w['n']:4}  w {w['w']:.1f} T {w['T']:.2f}  "
                               f"moved {w['moved']:4}  hit {_pct(w['hit'])} ours {_pct(w['ours'])} "
                               f"market {_pct(w['market'])}  log loss {w['base_sum'] / w['n']:.4f} → "
                               f"{w['rule_sum'] / w['n']:.4f}  Brier {w['base_brier']:.4f} → "
                               f"{w['rule_brier']:.4f}{flag}")
            if r["bands"]:
                out.append("  -- by how far our chance ran above the market (all settled, describes only)")
                for b in r["bands"]:
                    zo = "—" if b["z_ours"] is None else f"{b['z_ours']:+.1f}"
                    zm = "—" if b["z_market"] is None else f"{b['z_market']:+.1f}"
                    out.append(f"     {b['band']:24} n {b['n']:4}  hit {_pct(b['hit'])}  ours "
                               f"{_pct(b['ours'])} (z {zo})  market {_pct(b['market'])} (z {zm})")
            out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sport", help="one league: nfl, cfb, mlb, nba, wnba, nhl")
    ap.add_argument("--db", default=str(LEDGER), help="the ledger (default data/ledger.db)")
    ap.add_argument("--snapshots", help="the odds snapshots (default data/cache/line_history.jsonl)")
    ap.add_argument("--json", help="also write the full report here")
    a = ap.parse_args(argv)
    if not Path(a.db).exists():
        print(f"No ledger at {a.db}.")
        return 1
    report = study(load(open_ledger(a.db), a.sport), a.snapshots)
    print(render(report))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1, default=str)
        print(f"\nFull report: {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
