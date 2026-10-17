#!/usr/bin/env python3
"""EXP-001c — EXP-001's models priced at REAL book lines, against the de-vigged market.

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp1_lines_box.py
    python3 research/exp1_lines_box.py --db path/to/history.db

Research spec Part 8 Experiment 1's secondary evaluation, the market half
(Ethan, 2026-10-17). Registry EXP-001c. Runs on the box: its odds_history
already holds 2025 and 2026 NFL player props from 16 books (counted by
research/audit_box.py on 2026-10-17), so no credits are spent.

THE ROWS. Every NFL receptions, receiving-yards and rushing-yards prop in
odds_history for a player the models can score. Each quote is placed by
the player's next kickoff in the schedule (games.csv), not by the row's
own start time, which many stored rows do not carry (AMENDMENT 1, after a
first development run joined only 100 props and before any decision row
existed). Each book's LAST quote before that kickoff is kept; the line is the one most books hang (ties to the
lower); the market's chance for the over is the median de-vigged fair of
the books quoting both sides at that line (engine/odds.consensus_fair, the
function the site journals with, with its own minimum of books). The prop
joins the player's nflverse row by name and the game's date. A push is
left out of scoring.

THE FORECASTS of "over", all from information before the game:
  A     the direct model (EXP-001's A), fitted on 2017-2024
  B     the two-stage model (EXP-001's B), fitted on 2017-2024
  A*,B* each one's over-chance recalibrated (a logistic on its logit) on
        2023-2024 player-games at the proxy line: the fix EXP-001 asked for,
        fitted where no real line is needed
  C     the market: the books' de-vigged consensus
  D     the prespecified blend: the average of logit(B*) and logit(C)

DEVELOPMENT AND DECISION. 2025 was EXP-001's holdout (read once) and the
2026 games already played are in the box's history, so both are
DEVELOPMENT here: they say where things stand and decide nothing.

THE DECISION, PREREGISTERED 2026-10-17 BEFORE ANY RUN, uses only games
played after 2026-10-17, receptions only (the market EXP-001 advanced):
  Q1  B* beats A* in log loss            (the two-stage model, at real lines)
  Q2  D beats C in log loss              (our number adds to the market's)
each with the game-week-clustered bootstrap's upper bound under zero at
97.5% (0.05 / 2), and at least MIN_DECIDE rows; under that it says NOT YET.
A secondary table, deciding nothing, shows flat-stake ROI at the median
book price for props where B* sits above the market by more than EDGE.

Read-only on every database. The only thing it may write is an nflverse
season file the cache lacks, fetched once through the site's own loader.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import math
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research import exp1_two_stage as E1                        # noqa: E402

FREEZE = E1.FREEZE
MARKETS = ("receptions", "rec_yds", "rush_yds")
TRAIN = range(2017, 2025)
CALIB = (2023, 2024)
MIN_DECIDE = 300
EDGE = 0.04
ALPHA = 0.05 / 2
BOOT = 1000


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def _sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-35.0, min(35.0, x))))


def _ll(p: float, y: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def et_date(iso: str) -> str:
    """The US calendar day of a UTC start (five hours back covers both
    daylight and standard time for every NFL kickoff)."""
    t = _utc(iso)
    return (t - _dt.timedelta(hours=5)).date().isoformat()


def _utc(iso: str) -> _dt.datetime:
    t = _dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)


def kickoff_utc(gameday: str, gametime: str) -> _dt.datetime | None:
    """A schedule's local (US Eastern) kickoff as UTC; None when either is missing."""
    if not gameday or not gametime:
        return None
    try:
        local = _dt.datetime.fromisoformat(f"{gameday}T{gametime}")
    except ValueError:
        return None
    try:
        from zoneinfo import ZoneInfo
        return local.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(_dt.timezone.utc)
    except Exception:                                         # noqa: BLE001 — no tz database
        return (local + _dt.timedelta(hours=5)).replace(tzinfo=_dt.timezone.utc)


def consensus(quotes: dict) -> tuple | None:
    """{book: (line, over, under)} -> (line, fair over, books, median over price)."""
    from engine.models import SportsbookLine
    from engine.odds import consensus_fair, pair_is_sane
    sane = {b: q for b, q in quotes.items() if b != "proxy" and pair_is_sane(q[1], q[2])}
    if not sane:
        return None
    counts = Counter(q[0] for q in sane.values())
    top = max(counts.values())
    line = min(ln for ln, c in counts.items() if c == top)
    lines = [SportsbookLine(book=b, line=q[0], over_odds=int(q[1]), under_odds=int(q[2]))
             for b, q in sane.items() if q[0] == line]
    got = consensus_fair(lines, line)
    if not got:
        return None
    overs = sorted(int(q[1]) for q in sane.values() if q[0] == line)
    return line, got[0], got[1], overs[len(overs) // 2]


#: How far ahead of a quote its game may be: a Thursday line is hung days early.
LOOKAHEAD = _dt.timedelta(days=5)


def book_props(conn, kickoffs: dict, markets=MARKETS, funnel: Counter | None = None) -> dict:
    """{(normalized name, game day, market): (line, fair over, books, price)}
    from each book's last quote before the player's kickoff.

    ``kickoffs`` is {normalized name: sorted [(kickoff UTC, game day)]} from
    the schedule, so a quote is placed by the game it precedes, not by the
    row's own start time, which many stored rows do not carry."""
    import bisect
    from engine.sources.oddsapi import normalize_name
    funnel = funnel if funnel is not None else Counter()
    names: dict = {}
    last: dict = {}
    q = ("SELECT taken_at, player, market, book, line, over_odds, under_odds FROM odds_history "
         "WHERE sport='nfl' AND market IN (%s)" % ",".join("?" * len(markets)))
    for taken, player, market, book, line, over, under in conn.execute(q, markets):
        funnel["quotes read"] += 1
        if not player or line is None or not taken:
            continue
        n = names.get(player)
        if n is None:
            n = names[player] = normalize_name(player)
        games = kickoffs.get(n)
        if not games:
            continue
        funnel["quotes on a scored player"] += 1
        try:
            t = _utc(taken)
        except ValueError:
            continue
        i = bisect.bisect_right([g[0] for g in games], t)
        if i >= len(games) or games[i][0] - t > LOOKAHEAD:
            continue
        funnel["quotes before his next kickoff"] += 1
        k = (n, games[i][1], market, str(book or "").lower())
        if k not in last or t > last[k][0]:
            last[k] = (t, float(line), over, under)
    per: dict = defaultdict(dict)
    for (n, day, market, book), (_t, line, over, under) in last.items():
        per[(n, day, market)][book] = (line, over, under)
    funnel["props (player, game, market)"] += len(per)
    out = {}
    for key, quotes in per.items():
        c = consensus(quotes)
        if c:
            out[key] = c
    funnel["props with a three-book consensus"] += len(out)
    return out


def kickoffs_for(rows: list[dict]) -> dict:
    """{normalized name: sorted [(kickoff UTC, game day)]} for the scored rows."""
    from engine.sources.oddsapi import normalize_name
    sched = game_schedule()
    out: dict = defaultdict(set)
    for x in rows:
        g = sched.get(x.get("gid") or "")
        if not g:
            continue
        k = kickoff_utc(*g)
        if k:
            out[normalize_name(x["name"])].add((k, g[0]))
    return {n: sorted(v) for n, v in out.items()}


def game_schedule() -> dict:
    """{game_id: (game day, local kickoff time)} from the schedule file."""
    import csv
    with open(ROOT / "data" / "cache" / "games.csv", newline="") as fh:
        return {g["game_id"]: (g.get("gameday") or "", g.get("gametime") or "") for g in csv.DictReader(fh)}


def game_dates() -> dict:
    """{game_id: game day}."""
    return {gid: day for gid, (day, _t) in game_schedule().items()}


class Calibrator:
    """σ(a + b·logit p), fitted by Newton's method on (p, outcome) pairs."""

    def __init__(self, pairs: list):
        a, b = 0.0, 1.0
        for _ in range(50):
            ga = gb = haa = hab = hbb = 0.0
            for p, y in pairs:
                x = _logit(p)
                q = _sig(a + b * x)
                d = q * (1 - q)
                ga += q - y
                gb += (q - y) * x
                haa += d
                hab += d * x
                hbb += d * x * x
            det = haa * hbb - hab * hab
            if abs(det) < 1e-12:
                break
            da = (hbb * ga - hab * gb) / det
            db = (haa * gb - hab * ga) / det
            a, b = a - da, b - db
            if abs(da) + abs(db) < 1e-9:
                break
        self.a, self.b = a, b

    def __call__(self, p: float) -> float:
        return _sig(self.a + self.b * _logit(p))


def over_chances(fit, x: dict, line: float) -> tuple[float, float]:
    return 1.0 - fit.cdf_a(x, line), 1.0 - fit.cdf_b(x, [line])[0]


def proxy_line(fit, x: dict) -> float:
    grid = E1.GRID[x["m"]]
    med = next((t for t in grid if fit.cdf_a(x, t) >= 0.5), grid[-1])
    return math.floor(med) + 0.5


def calibrators(fit) -> dict:
    """{market: (A*, B*)} fitted at the proxy line on CALIB seasons."""
    pairs = defaultdict(lambda: ([], []))
    for s in CALIB:
        for x in E1.rows_for(s):
            line = proxy_line(fit, x)
            if x["y"] == line:
                continue
            pa, pb = over_chances(fit, x, line)
            y = 1.0 if x["y"] > line else 0.0
            pairs[x["m"]][0].append((pa, y))
            pairs[x["m"]][1].append((pb, y))
    return {m: (Calibrator(a), Calibrator(b)) for m, (a, b) in pairs.items()}


def scored(fit, cals: dict, props: dict, rows: list[dict]) -> list[dict]:
    from engine.sources.oddsapi import normalize_name
    dates = game_dates()
    out = []
    for x in rows:
        s = x["s"]
        day = dates.get(x.get("gid") or "", "")
        p = props.get((normalize_name(x["name"]), day, x["m"]))
        if not p or not day:
            continue
        line, fair, books, price = p
        if x["y"] == line:
            continue
        pa, pb = over_chances(fit, x, line)
        ca, cb = cals[x["m"]]
        pas, pbs = ca(pa), cb(pb)
        out.append({"m": x["m"], "day": day, "wk": f"{s}-{x['week']:02d}", "after": day > FREEZE,
                    "y": 1.0 if x["y"] > line else 0.0, "line": line, "books": books, "price": price,
                    "A": pa, "B": pb, "A*": pas, "B*": pbs, "C": fair,
                    "D": _sig(0.5 * _logit(pbs) + 0.5 * _logit(fair))})
    return out


def compare(rows: list[dict], k1: str, k2: str, seed: int = 9) -> tuple:
    by = defaultdict(list)
    for r in rows:
        by[r["wk"]].append(_ll(r[k1], r["y"]) - _ll(r[k2], r["y"]))
    groups = [(sum(v), len(v)) for v in by.values()]
    n = sum(c for _s, c in groups)
    mean = sum(s for s, _c in groups) / n
    rng = random.Random(seed)
    stats = []
    for _ in range(BOOT):
        tot = cnt = 0.0
        for _ in range(len(groups)):
            s, c = groups[rng.randrange(len(groups))]
            tot += s
            cnt += c
        stats.append(tot / cnt)
    stats.sort()
    return mean, stats[int(BOOT * ALPHA / 2)], stats[min(BOOT - 1, int(BOOT * (1 - ALPHA / 2)))]


def roi(rows: list[dict], key: str = "B*") -> tuple:
    picks = [r for r in rows if abs(r[key] - r["C"]) > EDGE]
    pnl = 0.0
    for r in picks:
        over = r[key] > r["C"]
        won = r["y"] == (1.0 if over else 0.0)
        price = r["price"] if over else None
        # the over's median price is stored; an under is priced from the
        # consensus fair with the same margin the over carried
        if price is None:
            imp_over = (-r["price"] / (-r["price"] + 100.0)) if r["price"] < 0 else 100.0 / (r["price"] + 100.0)
            vig = max(0.0, imp_over - r["C"])
            imp_under = min(0.99, (1 - r["C"]) + vig)
            price = -100.0 * imp_under / (1 - imp_under) if imp_under >= 0.5 else 100.0 * (1 - imp_under) / imp_under
        win = price / 100.0 if price > 0 else 100.0 / -price
        pnl += win if won else -1.0
    return len(picks), (pnl / len(picks) if picks else 0.0)


def report(label: str, rows: list[dict]) -> None:
    print(f"\n{label}")
    for m in MARKETS:
        t = [r for r in rows if r["m"] == m]
        if not t:
            print(f"  {m:<10} no rows")
            continue
        ll = {k: sum(_ll(r[k], r["y"]) for r in t) / len(t) for k in ("A", "A*", "B", "B*", "C", "D")}
        hit = sum(r["y"] for r in t) / len(t)
        print(f"  {m:<10} n={len(t):,}  over hit {hit:.3f}  log loss " +
              "  ".join(f"{k} {v:.4f}" for k, v in ll.items()))
        n, r_ = roi(t)
        print(f"  {'':<10} secondary: B* off the market by >{EDGE:.0%} on {n:,} props, flat ROI {r_:+.3f}")


def pace(dev: list[dict], post: list[dict], market: str = "receptions") -> tuple | None:
    """(props a week, weeks still needed) for the decision, read off this
    season's weeks before the freeze — description, it decides nothing."""
    weeks = Counter(r["wk"] for r in dev if r["m"] == market and r["wk"].startswith(FREEZE[:4]))
    if not weeks:
        return None
    rate = sum(weeks.values()) / len(weeks)
    need = max(0, MIN_DECIDE - sum(1 for r in post if r["m"] == market))
    return rate, (math.ceil(need / rate) if rate > 0 else None)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(ROOT / "data" / "history.db"))
    a = ap.parse_args(argv)
    targets = [x for s in (2025, 2026) for x in E1.rows_for(s)]
    funnel: Counter = Counter()
    conn = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    props = book_props(conn, kickoffs_for(targets), funnel=funnel)
    conn.close()
    print(f"EXP-001c — {len(props):,} NFL props with a pre-game consensus (receptions, rec_yds, rush_yds)")
    print("  funnel: " + " → ".join(f"{k} {v:,}" for k, v in funnel.items())
          + f" → scorable player-games {len(targets):,}")
    fit = E1.Fit([x for s in TRAIN for x in E1.rows_for(s)])
    cals = calibrators(fit)
    for m, (ca, cb) in sorted(cals.items()):
        print(f"  calibration {m:<10} A*: a {ca.a:+.3f} b {ca.b:.3f}   B*: a {cb.a:+.3f} b {cb.b:.3f}")
    rows = scored(fit, cals, props, targets)
    dev = [r for r in rows if not r["after"]]
    post = [r for r in rows if r["after"]]
    print(f"  joined {len(rows):,} props to a player-game ({len(dev):,} development, {len(post):,} after {FREEZE})")
    report("DEVELOPMENT (2025 and 2026 before the freeze) — decides nothing", dev)
    rec = [r for r in post if r["m"] == "receptions"]
    print(f"\nDECISION (receptions, games after {FREEZE}): {len(rec):,} rows")
    if len(rec) < MIN_DECIDE:
        print(f"  NOT YET: needs {MIN_DECIDE}")
        got = pace(dev, post)
        if got:
            rate, weeks = got
            print(f"  pace: {FREEZE[:4]}'s weeks before the freeze averaged {rate:.0f} receptions props a week, "
                  f"so about {weeks} more week(s) of games, scored once nflverse posts each week's stats")
        return 0
    for k1, k2, name in (("B*", "A*", "Q1 two-stage beats direct"), ("D", "C", "Q2 our number adds to the market")):
        mean, lo, hi = compare(rec, k1, k2)
        verdict = "PASSES" if hi < 0 else ("INCONCLUSIVE" if mean < 0 else "FAILS")
        print(f"  {name:<34} {mean:+.5f} [{lo:+.5f}, {hi:+.5f}]  {verdict}")
    report("decision rows, every market (receptions decides)", post)
    return 0


if __name__ == "__main__":
    sys.exit(main())
