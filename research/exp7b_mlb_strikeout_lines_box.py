#!/usr/bin/env python3
"""EXP-007b — EXP-007's strikeout models priced at the books' REAL lines, against the de-vigged market.

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp7b_mlb_strikeout_lines_box.py
    cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp7b_mlb_strikeout_lines_box.py --holdout

EXP-007 asks whether a starter's strikeouts read better as batters faced
times a strikeout rate (B), or as the direct model's mean with that shape
(H), than directly (A), across the whole distribution. A bet is made at
one line, so this asks it there, as EXP-001c does for the NFL and EXP-004c
for college. Backlog B17. Registry EXP-007b.

THE STARTS AND THE MODELS are EXP-007's, imported unchanged: its starts
(the pitcher his opponents saw first), its rows (three earlier starts that
season), its splits and its Fit on the training starts. Each model's chance
of the over at the line is recalibrated (a logistic on its logit) at the
proxy line, A's median plus a half, on the training starts (A*, B*, H*),
as EXP-001c does.

THE LINES, from two stores the box already keeps, so no credits are spent:
odds_history (sport 'mlb', market 'strikeouts'; the paid harvest from
2026-06-01) and the line snapshots (data/cache/line_history.jsonl), main
lines only (every writer stores a prop's lines, never its alternate
ladder). For each start, each book's LAST two-sided quote before it; the
line most books hang (ties to the lower); the books' de-vigged consensus
at that line (exp1_lines_box.consensus: engine/odds.consensus_fair with its
own minimum of books). The table keeps each start's date, not its first
pitch, so a quote is placed thus: one carrying its game's start (an
odds_history commence_time, a snapshot's start_ts) lands on his start that
day, only if taken before that start; one carrying none lands on his next
start within LOOKAHEAD days, and on the day itself only if taken before
EARLY (11 a.m. Eastern) that day, so a price read after first pitch is
never the line. That matters here: until 2026-09-30 the nightly close
harvest (23:00 UTC) also stored games already under way at their live
prices, and its rows carry no start. A push is left out.

THE DECISION, WRITTEN BEFORE ANY RUN (2026-10-19), on EXP-007's holdout
starts only (the decision period below), read once with ``--holdout`` and
under EXP-007's own guards (every season's plays at COMPLETE of its finals,
no fitted constant on its grid's edge):
  Q1  B* beats A* in log loss
  Q2  H* beats A* in log loss
each PASSES when the pitcher-season-clustered bootstrap's upper bound is
under zero at 97.5% (0.05 / 2), and the holdout holds MIN_DECIDE scored
props; right direction otherwise INCONCLUSIVE; wrong direction FAILS; under
MIN_DECIDE, NO DECISION. Every earlier start with a line is development and
decides nothing; so are D (the average of logit(C) and logit(B*)), the
market's own log loss and the flat-stake ROI.

Read-only on every database and file.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pricetrust as PT                                           # noqa: E402
from research import exp1_lines_box as EL                        # noqa: E402
from research import exp7_mlb_strikeouts_box as E7               # noqa: E402

MARKET = "strikeouts"
LOOKAHEAD = 2
EARLY = 15                     # UTC hour on the start's day: 11 a.m. Eastern in summer, 10 a.m. in winter
MIN_DECIDE = 300
KEYS = ("A", "A*", "B", "B*", "H", "H*", "C", "D")

_NAMES: dict = {}


def _norm(name: str) -> str:
    n = _NAMES.get(name)
    if n is None:
        from engine.sources.oddsapi import normalize_name
        n = _NAMES[name] = normalize_name(name)
    return n


def _day(t: _dt.datetime) -> str:
    """The US calendar day of a UTC instant (Eastern, near enough for a
    day game or a night game)."""
    return (t - _dt.timedelta(hours=5)).date().isoformat()


def start_days(rows: list[dict]) -> dict:
    """``{normalized pitcher: sorted [start date]}`` for the scored starts."""
    out: dict = defaultdict(set)
    for x in rows:
        out[_norm(x["name"])].add(x["date"])
    return {n: sorted(v) for n, v in out.items()}


def place(days: list, taken: _dt.datetime, start: _dt.datetime | None) -> str | None:
    """The start date a quote belongs to, or None (see THE LINES)."""
    if start is not None:
        day = _day(start)
        return day if day in days and taken < start else None
    today = _day(taken)
    for d in days:
        if d < today:
            continue
        if taken >= _dt.datetime.fromisoformat(d).replace(hour=EARLY, tzinfo=_dt.timezone.utc):
            return None             # on the day, too late to know he had not thrown a pitch
        gap = (_dt.date.fromisoformat(d) - _dt.date.fromisoformat(today)).days
        return d if gap <= LOOKAHEAD else None
    return None


def gather(days: dict, snapshots=(), history=(), funnel: Counter | None = None) -> dict:
    """``{(pitcher, date): {book: (line, over, under)}}``, each book's last
    two-sided quote placed on a start."""
    from engine.odds import pair_is_sane
    funnel = funnel if funnel is not None else Counter()
    last: dict = {}

    def keep(name, day, book, taken, line, over, under):
        if not pair_is_sane(over, under):
            funnel["one-sided quotes left out"] += 1
            return
        k = (name, day, str(book or "").lower())
        if k not in last or taken > last[k][0]:
            last[k] = (taken, line, over, under)

    for r in snapshots:
        funnel["snapshot quotes on a scored pitcher"] += 1
        name = _norm(r.get("player") or "")
        try:
            taken = _dt.datetime.fromtimestamp(float(r["ts"]), _dt.timezone.utc)
            start = (_dt.datetime.fromtimestamp(float(r["start_ts"]), _dt.timezone.utc)
                     if r.get("start_ts") is not None else None)
            line = float(r["line"])
        except (KeyError, TypeError, ValueError):
            continue
        day = place(days.get(name) or [], taken, start)
        if day:
            funnel["snapshot quotes placed before a start"] += 1
            keep(name, day, r.get("book"), taken, line, r.get("over_odds"), r.get("under_odds"))
    for taken_at, player, book, line, over, under, commence in history:
        funnel["odds_history quotes read"] += 1
        name = _norm(player or "")
        if name not in days or line is None or not taken_at:
            continue
        try:
            taken = EL._utc(taken_at)
            start = EL._utc(commence) if commence else None
        except ValueError:
            continue
        day = place(days[name], taken, start)
        if day:
            funnel["odds_history quotes placed before a start"] += 1
            keep(name, day, book, taken, float(line), over, under)
    per: dict = defaultdict(dict)
    for (name, day, book), (_t, line, over, under) in last.items():
        per[(name, day)][book] = (line, over, under)
    funnel["props (pitcher, start)"] += len(per)
    return dict(per)


def history_rows(conn) -> list:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(odds_history)")}
    start = "commence_time" if "commence_time" in cols else "NULL"
    return conn.execute(f"SELECT taken_at, player, book, line, over_odds, under_odds, {start} FROM odds_history "
                        f"WHERE sport='mlb' AND market=?", (MARKET,)).fetchall()


def chances(fit: E7.Fit, x: dict, line: float) -> dict:
    """A's, B's and H's chance of the over at a half line (A read at the
    line itself, as exp1_lines_box.over_chances; B and H are counts)."""
    k = min(len(E7.GRID) - 1, int(line))
    fb = fit.cdf_b(x)
    mb = fit.mean_b(x)
    fh = fit.cdf_b(x, scale=x["mu_a"] / mb) if mb > 0 else fb
    return {"A": 1.0 - fit.cdf_a(x, line), "B": 1.0 - fb[k], "H": 1.0 - fh[k]}


def proxy_line(fit: E7.Fit, x: dict) -> float:
    """A's median plus a half (exp1_lines_box.proxy_line's rule)."""
    med = next((t for t in E7.GRID if fit.cdf_a(x, t) >= 0.5), E7.GRID[-1])
    return math.floor(med) + 0.5


def calibrators(fit: E7.Fit, rows: list[dict]) -> dict:
    """``{model: Calibrator}`` fitted at the proxy line on ``rows``."""
    pairs: dict = defaultdict(list)
    for x in rows:
        line = proxy_line(fit, x)
        y = 1.0 if x["y"] > line else 0.0
        for k, p in chances(fit, x, line).items():
            pairs[k].append((p, y))
    return {k: EL.Calibrator(v) for k, v in pairs.items()}


def scored(fit: E7.Fit, cals: dict, props: dict, rows: list[dict], funnel: Counter | None = None) -> list[dict]:
    funnel = funnel if funnel is not None else Counter()
    out = []
    for x in rows:
        q = props.get((_norm(x["name"]), x["date"]))
        c = EL.consensus(q) if q else None
        if not c:
            continue
        line, fair, books, price = c
        funnel["props joined to a scored start"] += 1
        if line != int(line) + 0.5:
            funnel["whole-number lines left out"] += 1
            continue
        raw = chances(fit, x, line)
        row = {"who": x["who"], "wk": x["who"], "date": x["date"], "y": 1.0 if x["y"] > line else 0.0,
               "line": line, "books": books, "price": price, "C": fair, **raw}
        for k in ("A", "B", "H"):
            row[k + "*"] = cals[k](raw[k])
        row["D"] = EL._sig(0.5 * EL._logit(row["B*"]) + 0.5 * EL._logit(fair))
        out.append(row)
    return out


def describe(label: str, rows: list[dict], say=print) -> None:
    if not rows:
        say(f"  {label}: no rows")
        return
    ll = {k: sum(EL._ll(r[k], r["y"]) for r in rows) / len(rows) for k in KEYS}
    hit = sum(r["y"] for r in rows) / len(rows)
    n, roi = EL.roi(rows, "B*")
    say(f"  {label}: n={len(rows):,}  over hit {hit:.3f}  log loss " + "  ".join(f"{k} {v:.4f}" for k, v in ll.items()))
    say(f"  {'':<{len(label) + 2}}secondary: B* off the market by >{EL.EDGE:.0%} on {n:,} props, flat ROI {roi:+.3f}")


def study(conn, snapshots=None, holdout: bool = False, say=print) -> dict:
    """The run, printed through ``say``; returns the decision for tests."""
    say("EXP-007b — EXP-007's strikeout models at the books' own lines")
    cover = E7.coverage(conn)
    rows = E7.rows_from(E7.starts(conn))
    got = E7.splits(rows)
    if not got:
        say(f"  NOT YET: no season with {E7.MIN_SEASON_STARTS} scored starts")
        return {"verdict": "NOT YET"}
    train, valid, hold, labels, seasons = got
    fit = E7.Fit(train)
    cals = calibrators(fit, train)
    blocked = E7.on_edge(fit) + E7.incomplete(cover, seasons)
    funnel: Counter = Counter()
    days = start_days(rows)
    snaps = PT._snapshot_rows(snapshots, {MARKET}, set(days), _norm)
    props = gather(days, snaps, history_rows(conn), funnel)
    sc = scored(fit, cals, props, rows, funnel)
    say("  funnel: " + " → ".join(f"{k} {v:,}" for k, v in funnel.items()))
    for k, c in sorted(cals.items()):
        say(f"  calibration {k}*: a {c.a:+.3f} b {c.b:.3f}")
    hold_who = {(x["who"], x["date"]) for x in hold}
    dev = [r for r in sc if (r["who"], r["date"]) not in hold_who]
    post = [r for r in sc if (r["who"], r["date"]) in hold_who]
    describe(f"DEVELOPMENT (every start with a line before the decision period, {labels[2]} excluded)", dev, say)
    say(f"DECISION ({labels[2]}; one read, --holdout): {len(post):,} props")
    if not holdout:
        say("  not read (run with --holdout, once, after the development numbers look sound)")
        return {"verdict": "NOT READ", "dev": len(dev), "post": len(post)}
    if blocked:
        say("  NOT READ: " + "; ".join(blocked))
        return {"verdict": "NOT READ", "why": blocked}
    if len(post) < MIN_DECIDE:
        say(f"  NO DECISION: {len(post)} scored props, under {MIN_DECIDE}")
        return {"verdict": "NO DECISION", "post": len(post)}
    out = {}
    for key, name in (("B*", "Q1 B* beats A*"), ("H*", "Q2 H* beats A*")):
        mean, lo, hi = EL.compare(post, key, "A*")
        verdict = "PASSES" if hi < 0 else ("INCONCLUSIVE" if mean < 0 else "FAILS")
        out[key] = verdict
        say(f"  {name:<18} {mean:+.5f} [{lo:+.5f}, {hi:+.5f}]  {verdict}")
    describe("decision rows", post, say)
    return {"verdict": out}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(ROOT / "data" / "history.db"))
    ap.add_argument("--snapshots", help="the line snapshots (default data/cache/line_history.jsonl)")
    ap.add_argument("--holdout", action="store_true", help="also read the decision period (once; see THE DECISION)")
    a = ap.parse_args(argv)
    if not Path(a.db).exists():
        print(f"No database at {a.db}.")
        return 1
    study(sqlite3.connect(f"file:{a.db}?mode=ro", uri=True), a.snapshots, a.holdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
