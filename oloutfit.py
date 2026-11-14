#!/usr/bin/env python3
"""Does an offense missing its starting linemen do less than its form says? — measured.

    python3 oloutfit.py                      # 2022-2025 (injury reports start in 2022)
    python3 oloutfit.py --seasons 2022-2026  # once 2026 is complete

Ethan's Patriots–Bears research (2026-10-22): all four docs led with New
England starting two backup interior linemen (Alijah Vera-Tucker and Ben
Brown out). The model's one line rule is a starting tackle's
(engine/injuries.KNOCK_ONS: own LT/OT out, receivers' yards × 0.96; the
quarterback's version was measured and dropped). Guards and centers had
never been measured.

Starters: offensive linemen averaging 60%+ of the offensive snaps over
three or more earlier games this season (nflverse snap counts — the same
bar as defoutfit.py). Out: a starter listed Out or Doubtful on his team's
injury report that week — what the board can know before kickoff. Which
spot he plays is read off the report (G, C, T), else the snap counts.

Base: the board's — the form (from week 4 pulled toward last season) × the
defence step against the opponent. Candidate: base × (1 + a × linemen
out), on the player's OWN team, ``a`` fitted per market on the other
seasons and scored on each in turn — once for every starting lineman out,
once for guards and centers alone. Sacks have no market; they are shown
against the quarterback's own form, not fitted.

THE BAR, set before the first run: every held-out season improves, as for
defoutfit.py. Reads data/cache, fetching any season's nflverse file it
lacks (the box keeps the seasons it prices); writes nothing else.

RUN ON 2022-2025 (2026-10-22) IT FAILED IN EVERY MARKET, so nothing is
applied. The first run printed "SHIPS" for four markets, and that was the
base running about 2–3% high in every week, none out included: a slope
fitted alone soaked it up from every week with one out. With the level
fitted beside it (`fit`), no shape held in every held-out season:

  * one starting lineman out: nothing (passing yards −1.0% on none,
    completions −0.2%, catches −0.1%, rushing −0.1%);
  * two out: the passing game short — yards −6.8%, completions −6.3%,
    catches −7.1%, receiving yards −7.5% — on 39 quarterback games in four
    seasons, and the "two" step that fits it held in 2022-2024 and failed
    in 2025;
  * sacks went DOWN, not up: −6.4% with one out, −11.1% with two, against
    the quarterback's own form.

"Two" was shaped after looking, so it is re-run once 2026 is complete —
the one season it has not seen.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import carry as C                                    # noqa: E402
from engine import defensevs as D                                # noqa: E402
from engine.form import compute_form                             # noqa: E402
from engine.models import GameLog                                # noqa: E402
from engine.sources.nflverse import quarterbacked, stat_value    # noqa: E402
from engine.statmath import clamp                                # noqa: E402
from engine.teammates import _norm as normalize_name             # noqa: E402
from qbscriptfit import load                                     # noqa: E402

CACHE = ROOT / "data" / "cache"

LINE = {"T", "G", "C", "OL", "OT", "OG", "LT", "LG", "RG", "RT"}
INTERIOR = {"G", "C", "OG", "LG", "RG"}
MARKETS = {"pass_yds": ("QB",), "pass_cmp": ("QB",), "rush_yds": ("RB",),
           "receptions": ("WR", "TE", "RB"), "rec_yds": ("WR", "TE", "RB")}
#: Which absences each run counts. "two" is a step, not a slope: one
#: starting lineman out showed nothing on the first run, two showed the
#: passing game short — so that shape was added AFTER looking, and its
#: verdict waits on a season it has not seen (2026).
KINDS = {"line": LINE, "interior": INTERIOR, "two": LINE}
SLOPES = [x / 1000 for x in range(-120, 61, 5)]


def ensure(season: int) -> None:
    """The nflverse files a season reads, fetched into the cache if absent."""
    from engine.sources.injuries import load_injuries
    from engine.sources.nflverse import load_snap_counts, load_weekly_stats
    for name, fetch, year in ((f"player_stats_{season - 1}.csv", load_weekly_stats, season - 1),
                              (f"player_stats_{season}.csv", load_weekly_stats, season),
                              (f"snap_counts_{season}.csv", load_snap_counts, season),
                              (f"injuries_{season}.csv", load_injuries, season)):
        if not (CACHE / name).exists():
            fetch(year)


def snaps(season):
    by = defaultdict(lambda: defaultdict(dict))        # team -> week -> name -> (pos, pct)
    with open(CACHE / f"snap_counts_{season}.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("game_type") != "REG":
                continue
            try:
                pct = float(r.get("offense_pct") or 0)
                wk = int(r["week"])
            except ValueError:
                continue
            if pct > 0:
                by[r["team"]][wk][normalize_name(r["player"])] = ((r.get("position") or "").upper(), pct)
    return by


def outs(season):
    by = defaultdict(dict)                              # (team, week) -> name -> report position
    with open(CACHE / f"injuries_{season}.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("game_type") != "REG":
                continue
            if str(r.get("report_status") or "").lower() in ("out", "doubtful"):
                by[(r["team"], int(r["week"]))][normalize_name(r.get("full_name") or "")] = \
                    str(r.get("position") or "").upper()
    return by


def missing(team, wk, sn, inj):
    """{kind: starting linemen out} for this offence this week."""
    seen = defaultdict(list)
    for w in range(1, wk):
        for name, (pos, pct) in sn[team].get(w, {}).items():
            seen[name].append((pos, pct))
    listed = inj.get((team, wk), {})
    got = {"line": 0, "interior": 0}
    for name, games in seen.items():
        if name not in listed or len(games) < 3 or sum(p for _x, p in games) / len(games) < 0.60:
            continue
        pos = listed[name] if listed[name] in LINE else games[-1][0]
        if pos not in LINE:
            continue
        got["line"] += 1
        got["interior"] += pos in INTERIOR
    got["two"] = int(got["line"] >= 2)
    return got


def _team(r):
    return r.get("team") or r.get("recent_team") or ""


def points(season):
    ensure(season)
    now, before = load(season), load(season - 1)
    sn, inj = snaps(season), outs(season)
    prior_r = D.ratings(before, 99)
    rated = {w: D.ratings(now, w, prior=prior_r, week_one_prior=True) for w in range(4, 23)}
    prev = defaultdict(list)
    for r in before:
        prev[r["player_display_name"]].append(r)
    mine = defaultdict(list)
    for r in now:
        mine[r["player_display_name"]].append(r)
    miss_cache = {}
    out = []

    def miss(team, wk):
        if (team, wk) not in miss_cache:
            miss_cache[(team, wk)] = missing(team, wk, sn, inj)
        return miss_cache[(team, wk)]

    for name, rows in mine.items():
        rows.sort(key=lambda r: int(float(r["week"])))
        pos = str(rows[0].get("position") or "").upper()
        for m, poss in MARKETS.items():
            if pos not in poss:
                continue
            last = [stat_value(r, m) for r in prev.get(name, ()) if quarterbacked(r, m)]
            games = [r for r in rows if quarterbacked(r, m)]
            for i, r in enumerate(games):
                wk = int(float(r["week"]))
                if wk < 4 or i < 3:
                    continue
                vals = [stat_value(x, m) for x in games[:i]]
                logs = [GameLog(week=int(float(x["week"])), opponent="", value=v)
                        for x, v in zip(games[:i], vals)][::-1]
                career = sum(vals) / len(vals)
                plain = compute_form(logs, career, None).mean
                if plain < C.SEASON_PRIOR_FLOOR[m]:
                    continue
                k = C.SEASON_PRIOR_GAMES.get(m)
                base = (compute_form(logs, career, None, prior=sum(last) / len(last), prior_n=len(last),
                                     prior_games=k).mean if len(last) >= C.MIN_PRIOR_GAMES and k else plain)
                opp = r.get("opponent_team") or ""
                f = D.effect(opp, rated[wk].get(opp) or {}, pos, m)[0]
                gone = miss(_team(r), wk)
                out.append({"m": m, "s": season, "base": base * f, "y": stat_value(r, m), **gone})
        # SACKS, the quarterback's own: shown, not fitted (no market).
        if pos == "QB":
            games = [r for r in rows if quarterbacked(r, "pass_yds")]
            for i, r in enumerate(games):
                wk = int(float(r["week"]))
                if wk < 4 or i < 3:
                    continue
                vals = [float(x.get("sacks_suffered") or x.get("sacks") or 0) for x in games[:i]]
                logs = [GameLog(week=int(float(x["week"])), opponent="", value=v)
                        for x, v in zip(games[:i], vals)][::-1]
                base = compute_form(logs, sum(vals) / len(vals), None).mean
                gone = miss(_team(r), wk)
                out.append({"m": "sacks", "s": season, "base": base,
                            "y": float(r.get("sacks_suffered") or r.get("sacks") or 0), **gone})
    return out


def _scaled(p, a, kind):
    return p["base"] * clamp(1 + a * p[kind], 0.75, 1.25)


def sse(pts, level, a, kind):
    return sum((p["y"] - level * _scaled(p, a, kind)) ** 2 for p in pts)


def fit(pts, kind, slopes) -> tuple:
    """(slope, level) with the least squared error. THE LEVEL IS FITTED
    TOO: the base runs a little high in every week (actual/base under 1
    with no lineman out), and a slope fitted alone soaks that up from every
    week with one out — the first run's "SHIPS" on receptions was that,
    with 0.974 at none out and 0.973 at one. For each slope the level has
    a closed form."""
    best = None
    for a in slopes:
        g = [_scaled(p, a, kind) for p in pts]
        den = sum(x * x for x in g)
        level = sum(p["y"] * x for p, x in zip(pts, g)) / den if den else 1.0
        e = sum((p["y"] - level * x) ** 2 for p, x in zip(pts, g))
        if best is None or e < best[0]:
            best = (e, a, level)
    return best[1], best[2]


def held_out(by: dict, market: str, kind: str) -> list[tuple]:
    """[(season, slope fitted on the others, % squared error cut against
    the level alone)]."""
    out = []
    for s in sorted(by):
        tr = [p for t in by if t != s for p in by[t] if p["m"] == market]
        te = [p for p in by[s] if p["m"] == market]
        if not tr or not te:
            continue
        a, level = fit(tr, kind, SLOPES)
        _z, level0 = fit(tr, kind, [0.0])
        raw = sse(te, level0, 0.0, kind)
        out.append((s, a, (1 - sse(te, level, a, kind) / raw) * 100 if raw else 0.0))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="2022-2025")
    a = ap.parse_args(argv)
    lo, _, hi = a.seasons.partition("-")
    by = {s: points(s) for s in range(int(lo), int(hi or lo) + 1)}
    for m in list(MARKETS) + ["sacks"]:
        allp = [p for s in by for p in by[s] if p["m"] == m]
        print(f"{m} ({len(allp)} player-games):")
        for kind in KINDS:
            buckets = defaultdict(lambda: [0.0, 0.0, 0])
            for p in allp:
                b = buckets[min(p[kind], 3)]
                b[0] += p["y"]
                b[1] += p["base"]
                b[2] += 1
            none = buckets[0][0] / buckets[0][1] if buckets[0][1] else 1.0
            print(f"   {kind:<8} " + "  ".join(
                f"{x}{'+' if x == 3 else ''}: n {n} actual/base {y / b:.3f}"
                + (f" ({(y / b) / none - 1:+.1%} on none)" if x else "")
                for x, (y, b, n) in sorted(buckets.items()) if b))
            if m == "sacks":
                continue
            held = held_out(by, m, kind)
            ok = bool(held) and all(c > 0 for *_x, c in held)
            print(f"            held out: " + "  ".join(f"{s}: a {sl:+.3f} {c:+.2f}%" for s, sl, c in held)
                  + f"   {'SHIPS' if ok else 'fails — not applied'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
