#!/usr/bin/env python3
"""Does a defence missing its starters give up more than its rating says? — measured.

    python3 defoutfit.py                      # 2022-2025 (injury reports start in 2022)
    python3 defoutfit.py --seasons 2022-2026  # once 2026 is complete

Ethan's Bills @ Rams reports (2026-10-12) leaned on Ed Oliver, Dee Alford
and Quentin Lake being out. Starters: defenders averaging 60%+ of the
defensive snaps over three or more earlier games this season (nflverse snap
counts). Out: a starter listed Out or Doubtful on that week's injury report
— what the board can know before kickoff. Base: the board's — the form
(from week 4 pulled toward last season) × the defence step. Candidate:
pass-catchers' catches and yards and the quarterback's passing yards ×
(1 + a × defensive backs out); rushing yards × (1 + b × front seven out);
a and b fitted per market on the other seasons, scored on each in turn.

THE BAR, set before the first run: every held-out season improves. Run on
2022-2025 it failed in every market (engine/defensevs's note), so nothing
is applied. Reads data/cache; writes nothing.
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

DB = {"CB", "S", "FS", "SS", "DB", "SAF", "NB"}
FRONT = {"DE", "DT", "NT", "DL", "LB", "ILB", "OLB", "MLB", "EDGE"}
MARKETS = {"receptions": (("WR", "TE", "RB"), "db"), "rec_yds": (("WR", "TE", "RB"), "db"),
           "pass_yds": (("QB",), "db"), "rush_yds": (("RB",), "front")}
SLOPES = [x / 1000 for x in range(-60, 121, 5)]


def snaps(season):
    by = defaultdict(lambda: defaultdict(dict))        # team -> week -> name -> (pos, pct)
    with open(CACHE / f"snap_counts_{season}.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("game_type") != "REG":
                continue
            try:
                pct = float(r.get("defense_pct") or 0)
                wk = int(r["week"])
            except ValueError:
                continue
            if pct > 0:
                by[r["team"]][wk][normalize_name(r["player"])] = (r.get("position") or "", pct)
    return by


def outs(season):
    by = defaultdict(set)                               # (team, week) -> names Out/Doubtful
    with open(CACHE / f"injuries_{season}.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("game_type") != "REG":
                continue
            if str(r.get("report_status") or "").lower() in ("out", "doubtful"):
                by[(r["team"], int(r["week"]))].add(normalize_name(r.get("full_name") or ""))
    return by


def missing(team, wk, sn, inj):
    """(DBs out, front-seven out) among this defence's starters."""
    seen = defaultdict(list)
    for w in range(1, wk):
        for name, (pos, pct) in sn[team].get(w, {}).items():
            seen[name].append((pos, pct))
    db = fr = 0
    listed = inj.get((team, wk), set())
    for name, games in seen.items():
        if len(games) < 3 or sum(p for _x, p in games) / len(games) < 0.60:
            continue
        if name not in listed:
            continue
        pos = games[-1][0].upper()
        if pos in DB:
            db += 1
        elif pos in FRONT:
            fr += 1
    return db, fr


def points(season):
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
    for name, rows in mine.items():
        rows.sort(key=lambda r: int(float(r["week"])))
        pos = str(rows[0].get("position") or "").upper()
        for m, (poss, kind) in MARKETS.items():
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
                key = (opp, wk)
                if key not in miss_cache:
                    miss_cache[key] = missing(opp, wk, sn, inj)
                db, fr = miss_cache[key]
                out.append({"m": m, "s": season, "base": base * f, "x": db if kind == "db" else fr,
                            "y": stat_value(r, m)})
    return out


def sse(pts, a):
    return sum((p["y"] - p["base"] * clamp(1 + a * p["x"], 0.85, 1.25)) ** 2 for p in pts)


def held_out(by: dict, market: str) -> list[tuple]:
    """[(season, slope fitted on the others, % squared error cut)]."""
    out = []
    for s in sorted(by):
        tr = [p for t in by if t != s for p in by[t] if p["m"] == market]
        te = [p for p in by[s] if p["m"] == market]
        if not tr or not te:
            continue
        a = min(SLOPES, key=lambda aa: sse(tr, aa))
        raw = sse(te, 0)
        out.append((s, a, (1 - sse(te, a) / raw) * 100 if raw else 0.0))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="2022-2025")
    a = ap.parse_args(argv)
    lo, _, hi = a.seasons.partition("-")
    by = {s: points(s) for s in range(int(lo), int(hi or lo) + 1)}
    for m in MARKETS:
        allp = [p for s in by for p in by[s] if p["m"] == m]
        buckets = defaultdict(lambda: [0.0, 0.0, 0])
        for p in allp:
            b = buckets[min(p["x"], 3)]
            b[0] += p["y"]
            b[1] += p["base"]
            b[2] += 1
        held = held_out(by, m)
        ok = bool(held) and all(c > 0 for *_x, c in held)
        print(f"{m}: " + "  ".join(f"{x} out: n {n} actual/base {y / b:.3f}"
                                   for x, (y, b, n) in sorted(buckets.items()) if b))
        print("   held out: " + "  ".join(f"{s}: a {sl:+.3f} {c:+.2f}%" for s, sl, c in held)
              + f"   {'SHIPS' if ok else 'fails — not applied'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
