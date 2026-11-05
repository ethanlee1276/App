#!/usr/bin/env python3
"""Does the league's player tracking make the NBA board's number better? Held out, on the box. Read-only.

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 nbatrackcheck.py

Ethan, 2026-11-05, on the data hunt's one parked source, stats.nba.com
player tracking: "do it". engine/nba/tracking fetches it into a research
database of its own (``data/research/nba_tracking.db``, runbook KR); this
asks whether it is worth reading. Nothing on the site reads it, and this
script writes nothing.

THE QUESTION, market by market (assists, rebounds, points). The board's
number for a game is the production projection (engine/nba/pipeline.project:
his twenty games before it, the league's fitted tuning, the player memory
held at 1.0 because it was fitted on bets graded after these games, a
neutral spread and rest, as the Lab replays it; engine/hoopsreplay). Does
his tracking over those same twenty games say something about tonight that
the board's number does not?

  * assists: potential assists, passes made, secondary assists and assist
    points created, a minute;
  * rebounds: rebound chances (all, offensive, defensive) and contested
    rebounds, a minute;
  * points: touches, front-court and paint touches, time of possession,
    drives and the free throws off them, a minute.

THE TEST. Two models of his rate a minute tonight, each a least-squares fit
on one season, weighted by his minutes, on games of FIT_MIN or more:

  * the board's number alone: a + b x (the board's projection / its minutes);
  * the board's number and his tracking: the same, plus his tracking rates.

Each is judged on the other season. Its projection is the board's own
minutes x its fitted rate, so the minutes are the same in both and only the
rate is tested, and the board-alone refit gets the same level correction
the tracking model gets: tracking takes credit only for what it adds.
Judged on every game both can price (his window has GAMES_TRACKED or more
tracked games and MIN_TRACKED or more tracked minutes): the root squared
error of the count, the Brier at the half-point line off his last eight
played games (the line the replay prices when no close is stored), and the
ladder's Brier at lines a half point over 0.5, 0.65 and 0.8 of the board's
number (Most Likely's kind of over), all through the board's own curve.

THE BAR, written before the first box run. Tracking MEASURES for a market
when, judged on each season with the other fitted: the root squared error
is at least GAIN lower with tracking than the board alone refitted, and
neither Brier is worse. Each judged season needs MIN_JUDGED games. Anything
less, and nothing is built.

If a market measures, reading tracking on the board is a separate change:
the current season's tracking each morning (four requests a day), the
measured weights in the board's rate, and the owner's call on the terms
(NBA.com allows personal, non-commercial use; docs/DATA_SOURCES.md).

Opened read-only, both databases. Standard library only.
"""
from __future__ import annotations

import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

MARKETS = ("ast", "reb", "pts")
#: Each market's tracking rates, a minute. A name with "|" takes the first
#: of its spellings an answer carries.
FEATURES = {
    "ast": ("POTENTIAL_AST", "PASSES_MADE", "SECONDARY_AST", "AST_POINTS_CREATED|AST_PTS_CREATED"),
    "reb": ("REB_CHANCES", "OREB_CHANCES", "DREB_CHANCES", "REB_CONTEST"),
    "pts": ("TOUCHES", "FRONT_CT_TOUCHES", "PAINT_TOUCHES", "TIME_OF_POSS", "DRIVES", "DRIVE_FTA"),
}
#: His window, as the board reads it (engine/hoopsreplay.WINDOW).
WINDOW = 20
#: A game is judged when his window holds this much tracking.
GAMES_TRACKED = 3
MIN_TRACKED = 60.0
#: The rate is fitted on games of this many minutes or more.
FIT_MIN = 10.0
#: THE BAR: the root squared error this much lower, on each judged season.
GAIN = 0.005
MIN_JUDGED = 2000
#: Most Likely's kind of over: lines a half point over these fractions of
#: the board's number.
LADDER = (0.5, 0.65, 0.8)
#: A feature present in fewer of a market's rows than this is left out (an
#: answer that never carried it), and the report names it.
PRESENT = 0.95


def _ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _pick(row: dict, name: str):
    for n in name.split("|"):
        if n in row:
            return row[n]
    return None


def window_rates(e: dict, i: int, track: dict, names: tuple):
    """His tracking over the board's window for game ``i`` (the twenty games
    before it that he played and the league tracked), as rates a minute in
    ``names`` order, or None when it holds too little to read."""
    from engine.sources.oddsapi import normalize_name
    key = normalize_name(e["name"])
    lo = max(0, i - WINDOW)
    tot = [0.0] * len(names)
    seen = [0] * len(names)
    games, mins = 0, 0.0
    for j in range(lo, i):
        m_box = float((e["minutes"] or [])[j] or 0.0)
        if m_box <= 0:
            continue
        row = track.get((str(e["dates"][j])[:10], key))
        if not row:
            continue
        m = float(row.get("_min") or m_box)
        if m <= 0:
            continue
        games += 1
        mins += m
        for k, name in enumerate(names):
            v = _pick(row, name)
            if v is not None:
                tot[k] += float(v)
                seen[k] += 1
    if games < GAMES_TRACKED or mins < MIN_TRACKED:
        return None
    return [(tot[k] / mins) if seen[k] else None for k in range(len(names))]


def collect(hist: dict, track: dict, tune, markets=MARKETS) -> dict:
    """``{market: [row]}``: every gradeable game the board's projection
    prices, with its tracking rates where his window has them. A row:
    ``{"season", "proj", "pmin", "brate", "f", "actual", "amin", "line"}``."""
    from engine import hoopsreplay as HR
    from engine.nba.pipeline import project
    from engine.seasons import season_of
    out = {}
    for market in markets:
        entries = HR._entries(hist, market)
        names = FEATURES[market]
        rows = []
        for _day, player, n, i in HR._todo(entries, HR.MIN_HISTORY, 0):
            e = entries[n]
            minutes, values, starter = HR._window(e, i, market)
            if len(values) < 3:
                continue
            prop = {"player": player, "market": market, "minutes": minutes, "values": values,
                    "is_starter": starter, "starts": HR._starts(e, i), "spread": 0.0, "rest": "1day",
                    "shooting": HR._shooting(e, i, "nba", market), "rates": HR._rates(e, i, "nba"),
                    "player_mult": 1.0}
            try:
                pj = project(prop, tune)
            except Exception:                                # noqa: BLE001
                continue
            if "skip" in pj:
                continue
            proj, pmin = float(pj["projection"]), float(pj.get("proj_min") or 0.0)
            if pmin <= 0 or proj <= 0:
                continue
            played = [v for v, m in zip(values, minutes) if m > 0][:8] or values[:8]
            rows.append({"season": season_of("nba", str(e["dates"][i])[:10]), "proj": proj, "pmin": pmin,
                         "brate": proj / pmin, "f": window_rates(e, i, track, names),
                         "actual": float(e["values"][i]), "amin": float(e["minutes"][i] or 0.0),
                         "line": HR._naive_line(played)})
        out[market] = rows
    return out


def _solve(A: list, b: list) -> list:
    """Gaussian elimination with partial pivoting; a tiny ridge keeps a
    column that never moves from making the system singular."""
    k = len(b)
    M = [list(A[r]) + [b[r]] for r in range(k)]
    scale = max(1e-12, max(abs(M[r][r]) for r in range(k)))
    for r in range(k):
        M[r][r] += 1e-9 * scale
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        if abs(M[c][c]) < 1e-15:
            continue
        for r in range(k):
            if r != c and M[r][c]:
                f = M[r][c] / M[c][c]
                for q in range(c, k + 1):
                    M[r][q] -= f * M[c][q]
    return [(M[r][k] / M[r][r]) if abs(M[r][r]) > 1e-15 else 0.0 for r in range(k)]


def _x(row: dict, use: list, tracked: bool) -> list:
    x = [1.0, row["brate"]]
    if tracked:
        x += [row["f"][k] for k in use]
    return x


def fit(rows: list, use: list, tracked: bool) -> list:
    """Weighted least squares of his rate a minute on games of FIT_MIN+."""
    k = 2 + (len(use) if tracked else 0)
    A = [[0.0] * k for _ in range(k)]
    b = [0.0] * k
    for r in rows:
        if r["amin"] < FIT_MIN:
            continue
        x, w, y = _x(r, use, tracked), r["amin"], r["actual"] / r["amin"]
        for p in range(k):
            b[p] += w * x[p] * y
            for q in range(k):
                A[p][q] += w * x[p] * x[q]
    return _solve(A, b)


def _rung(f: float, proj: float) -> float:
    return math.floor(f * proj) + 0.5


def judge(rows: list, use: list, coef0: list, coefT: list, market: str, tune) -> dict:
    from engine.nba.prob import p_over
    n = 0
    se = {"board": 0.0, "alone": 0.0, "tracked": 0.0}
    near = {"alone": 0.0, "tracked": 0.0}
    lad = {"alone": 0.0, "tracked": 0.0}
    nl = 0
    for r in rows:
        y = r["actual"]
        p0 = max(0.0, r["pmin"] * sum(c * v for c, v in zip(coef0, _x(r, use, False))))
        pT = max(0.0, r["pmin"] * sum(c * v for c, v in zip(coefT, _x(r, use, True))))
        n += 1
        se["board"] += (y - r["proj"]) ** 2
        se["alone"] += (y - p0) ** 2
        se["tracked"] += (y - pT) ** 2
        hit = 1.0 if y > r["line"] else 0.0
        for name, pj in (("alone", p0), ("tracked", pT)):
            near[name] += (p_over(market, max(pj, 1e-6), r["line"], tune) - hit) ** 2
        for f in LADDER:
            line = _rung(f, r["proj"])
            hit = 1.0 if y > line else 0.0
            nl += 1
            for name, pj in (("alone", p0), ("tracked", pT)):
                lad[name] += (p_over(market, max(pj, 1e-6), line, tune) - hit) ** 2
    if not n:
        return {"n": 0}
    return {"n": n,
            "rmse": {k: math.sqrt(v / n) for k, v in se.items()},
            "near": {k: v / n for k, v in near.items()},
            "ladder": {k: v / max(1, nl) for k, v in lad.items()}}


def measure(by_market: dict, tune) -> dict:
    """``{market: {"use", "dropped", "seasons": {season: result}}}``: each
    season judged with every other season fitted."""
    out = {}
    for market, rows in by_market.items():
        names = FEATURES[market]
        have = [r for r in rows if r["f"] is not None]
        use, dropped = [], []
        for k, name in enumerate(names):
            share = (sum(1 for r in have if r["f"][k] is not None) / len(have)) if have else 0.0
            (use if share >= PRESENT else dropped).append(k)
        have = [r for r in have if all(r["f"][k] is not None for k in use)]
        seasons = sorted({r["season"] for r in have})
        res = {}
        for s in seasons:
            train = [r for r in have if r["season"] != s]
            test = [r for r in have if r["season"] == s]
            if not train or not test:
                continue
            c0, cT = fit(train, use, False), fit(train, use, True)
            res[s] = judge(test, use, c0, cT, market, tune)
            res[s]["coef"] = cT
            res[s]["fitted_on"] = sorted({r["season"] for r in train})
        out[market] = {"use": [names[k] for k in use], "dropped": [names[k] for k in dropped],
                       "seasons": res, "rows": len(rows), "tracked": len(have)}
    return out


def verdict(m: dict, min_judged: int = MIN_JUDGED) -> tuple:
    """``(measures, [why not])`` for one market's results."""
    seasons = m.get("seasons") or {}
    judged = {s: r for s, r in seasons.items() if r.get("n", 0) >= min_judged}
    if len(judged) < 2:
        return False, [f"not judged: {len(judged)} season(s) with {min_judged:,}+ tracked games "
                       f"(two are needed, each judged with the other fitted)"]
    why = []
    for s, r in sorted(judged.items()):
        a, t = r["rmse"]["alone"], r["rmse"]["tracked"]
        gain = 1.0 - t / a if a else 0.0
        if gain < GAIN:
            why.append(f"{_label(s)}: squared error {-gain:+.1%} (needs {-GAIN:+.1%})")
        if r["near"]["tracked"] > r["near"]["alone"] + 1e-6:
            why.append(f"{_label(s)}: Brier near the line worse ({r['near']['alone']:.4f} -> {r['near']['tracked']:.4f})")
        if r["ladder"]["tracked"] > r["ladder"]["alone"] + 1e-6:
            why.append(f"{_label(s)}: ladder Brier worse ({r['ladder']['alone']:.4f} -> {r['ladder']['tracked']:.4f})")
    return (not why), why


def _label(s: int) -> str:
    return f"{int(s)}-{(int(s) + 1) % 100:02d}"


def report(res: dict, coverage: str = "", min_judged: int = MIN_JUDGED) -> list:
    word = {"ast": "ASSISTS", "reb": "REBOUNDS", "pts": "POINTS"}
    lines = ["NBA PLAYER TRACKING, HELD OUT: the board's number alone, refitted, against the board's "
             "number and his tracking (read-only)"]
    if coverage:
        lines.append(coverage)
    for market in MARKETS:
        m = res.get(market)
        if not m:
            continue
        lines.append("")
        lines.append(f"{word[market]}: {m['tracked']:,} of {m['rows']:,} priced games have his tracking"
                     + (f"; not in the stored answers: {', '.join(m['dropped'])}" if m["dropped"] else ""))
        for s, r in sorted(m["seasons"].items()):
            if not r.get("n"):
                continue
            rm = r["rmse"]
            gain = 1.0 - rm["tracked"] / rm["alone"] if rm["alone"] else 0.0
            lines.append(f"  {_label(s)}, fitted on {', '.join(_label(x) for x in r['fitted_on'])}: {r['n']:,} games")
            lines.append(f"    root squared error: board {rm['board']:.3f} | refitted {rm['alone']:.3f} | "
                         f"with tracking {rm['tracked']:.3f} ({-gain:+.1%})")
            lines.append(f"    Brier near the line {r['near']['alone']:.4f} -> {r['near']['tracked']:.4f}; "
                         f"ladder {r['ladder']['alone']:.4f} -> {r['ladder']['tracked']:.4f}")
            names = ["level", "board rate"] + list(m["use"])
            lines.append("    weights: " + ", ".join(f"{n} {c:+.3f}" for n, c in zip(names, r["coef"])))
    lines.append("")
    lines.append(f"THE BAR (written before the first run): with tracking, the root squared error {GAIN:.1%} "
                 f"lower on each season judged with the other fitted, neither Brier worse, {min_judged:,}+ games "
                 f"a season.")
    for market in MARKETS:
        m = res.get(market)
        if not m:
            continue
        ok, why = verdict(m, min_judged)
        lines.append(f"  {word[market].lower()}: " + ("MEASURES on every season judged" if ok
                                                        else "does not measure: " + "; ".join(why[:4])))
    lines.append("Read-only: nothing was written. A market that measures is read by the board only "
                 "after a separate change and the owner's call on the terms (docs/DATA_SOURCES.md).")
    return lines


def main(argv=None) -> int:
    from engine import db, hoopsreplay as HR
    from engine.nba import tracking as TR
    store = TR.read_store()
    if store is None:
        print("No tracking stored yet: run the backfill first "
              "(python3 -m engine.nba.tracking --backfill, runbook KR).")
        return 0
    try:
        track = TR.load(store)
        days = len({d for d, _k in track})
    finally:
        store.close()
    if not track:
        print("The tracking store is empty: run the backfill first (runbook KR).")
        return 0
    conn = _ro(db.DEFAULT_DB)
    conn.row_factory = sqlite3.Row             # the tuning's fit reads its rows by name
    try:
        hist = HR.histories(conn, "nba")
        try:
            from engine.hoops_fit import fitted_tuning
            tune, _rep = fitted_tuning(conn, "nba")
        except Exception:                                   # noqa: BLE001
            from engine.hoops import NBA as tune
    finally:
        conn.close()
    res = measure(collect(hist, track, tune), tune)
    cover = f"tracking stored: {days} game days, {len(track):,} player-days"
    for line in report(res, cover):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
