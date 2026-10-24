#!/usr/bin/env python3
"""Does the spread move a player's volume beyond the board's base? — measured.

    python3 qbscriptfit.py                         # 2022-2025 held out, 2017-2021 unseen
    python3 qbscriptfit.py --seasons 2022-2025 --unseen 2017-2021

Ethan's Bills @ Rams reports (2026-10-12) put the market's extra Josh Allen
attempts down to Buffalo being the underdog: "trailing teams throw". The
board had one script term, engine/matchup.SCRIPT_COEF_PASS (+0.4% a point
on passing yards, catches and receiving yards for an underdog), measured
once on catches against a player's own prior form, before the board had
its defence step or his last season.

For every player-game from week 4 with three games this season, the base
is the board's: his form (engine/form.compute_form), pulled toward his own
last season where engine/carry.SEASON_PRIOR_GAMES applies, times the
defence step (engine/defensevs.effect on the walk-forward ratings, last
season as the prior, as engine/sources/nflverse builds them). Then:

  1. A QUARTERBACK'S VOLUME. Attempts and completions × (1 + b × his
     team's spread), within ±10%, b fitted on three seasons and squared
     error scored on the fourth. THE BAR, set before the run: every
     held-out season improves, and the fitted slope must not fail the
     unseen seasons.
  2. THE TILT THE BOARD HAD. Passing yards, catches and receiving yards
     with the board's +0.004 a point (×0.95-×1.05) against none. It stays
     unless dropping it improves every held-out season, and the unseen
     seasons do not disagree in three or more.

The spread is the closing line from nflverse's games.csv, from his team's
side: negative when it is favoured. Reads data/cache; writes nothing.
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
from engine.matchup import SCRIPT_CLAMP, SCRIPT_COEF_PASS        # noqa: E402
from engine.models import GameLog                                # noqa: E402
from engine.sources.nflverse import quarterbacked, stat_value    # noqa: E402
from engine.statmath import clamp                                # noqa: E402

#: market -> positions measured. A quarterback's volume is the candidate;
#: the other three carried the board's old tilt.
QB_CANDIDATES = ("pass_att", "pass_cmp")
OLD_TILT = ("pass_yds", "receptions", "rec_yds")
POSITIONS = {"pass_att": ("QB",), "pass_cmp": ("QB",), "pass_yds": ("QB",),
             "receptions": ("WR", "TE", "RB"), "rec_yds": ("WR", "TE", "RB")}
CANDIDATE_CLAMP = (0.90, 1.10)
SLOPES = tuple(x / 10000 for x in range(-100, 201, 5))
FIRST_WEEK = 4


def load(season: int) -> list[dict]:
    with open(ROOT / "data" / "cache" / f"player_stats_{season}.csv", newline="") as fh:
        return [r for r in csv.DictReader(fh) if str(r.get("season_type") or "REG") == "REG"]


def load_games() -> dict:
    with open(ROOT / "data" / "cache" / "games.csv", newline="") as fh:
        return {g["game_id"]: g for g in csv.DictReader(fh)}


def team_spread(row: dict, games: dict) -> float | None:
    """His team's closing spread, negative when it is favoured (the board's
    sign). nflverse's ``spread_line`` is positive when the HOME side is."""
    g = games.get(row.get("game_id") or "")
    line = str((g or {}).get("spread_line") or "").strip()
    if not line:
        return None
    sl = float(line)
    return -sl if row.get("team") == g.get("home_team") else sl


def points(now: list[dict], before: list[dict], games: dict, season: int) -> list[dict]:
    """[{m, s, base, ts, y}] — one per player-game and market, the base as
    the board computes it before any script term."""
    prior_ratings = D.ratings(before, 99)
    rated = {w: D.ratings(now, w, prior=prior_ratings, week_one_prior=True) for w in range(FIRST_WEEK, 23)}
    prev: dict = defaultdict(list)
    for r in before:
        prev[r["player_display_name"]].append(r)
    mine: dict = defaultdict(list)
    for r in now:
        mine[r["player_display_name"]].append(r)
    out = []
    for name, rows in mine.items():
        rows.sort(key=lambda r: int(float(r["week"])))
        pos = str(rows[0].get("position") or "").upper()
        for m, poss in POSITIONS.items():
            if pos not in poss:
                continue
            last = [stat_value(r, m) for r in prev.get(name, ()) if quarterbacked(r, m)]
            games_m = [r for r in rows if quarterbacked(r, m)]
            for i, r in enumerate(games_m):
                wk = int(float(r["week"]))
                if wk < FIRST_WEEK or i < 3:
                    continue
                ts = team_spread(r, games)
                if ts is None:
                    continue
                vals = [stat_value(x, m) for x in games_m[:i]]
                logs = [GameLog(week=int(float(x["week"])), opponent="", value=v)
                        for x, v in zip(games_m[:i], vals)][::-1]
                career = sum(vals) / len(vals)
                plain = compute_form(logs, career, None).mean
                if plain < C.SEASON_PRIOR_FLOOR.get(m, 0.0):
                    continue
                base = plain
                if len(last) >= C.MIN_PRIOR_GAMES and m in C.SEASON_PRIOR_GAMES:
                    base = compute_form(logs, career, None, prior=sum(last) / len(last), prior_n=len(last),
                                        prior_games=C.SEASON_PRIOR_GAMES[m]).mean
                opp = r.get("opponent_team") or ""
                factor = D.effect(opp, (rated.get(wk) or {}).get(opp) or {}, pos, m)[0]
                out.append({"m": m, "s": season, "base": base * factor, "ts": ts, "y": stat_value(r, m)})
    return out


def estimate(p: dict, b: float, bounds: tuple = CANDIDATE_CLAMP) -> float:
    return p["base"] * clamp(1.0 + b * p["ts"], *bounds)


def sse(pts: list[dict], b: float, bounds: tuple = CANDIDATE_CLAMP) -> float:
    return sum((p["y"] - estimate(p, b, bounds)) ** 2 for p in pts)


def held_out(by_season: dict, market: str) -> list[tuple]:
    """[(season, b fitted on the others, n, % squared error cut)]."""
    out = []
    for s in sorted(by_season):
        train = [p for t in by_season if t != s for p in by_season[t] if p["m"] == market]
        test = [p for p in by_season[s] if p["m"] == market]
        if not train or not test:
            continue
        b = min(SLOPES, key=lambda bb: sse(train, bb))
        raw = sse(test, 0.0)
        out.append((s, b, len(test), (1 - sse(test, b) / raw) * 100 if raw else 0.0))
    return out


def fixed(by_season: dict, market: str, b: float) -> list[tuple]:
    """[(season, n, % cut)] for one slope fixed in advance."""
    out = []
    for s in sorted(by_season):
        test = [p for p in by_season[s] if p["m"] == market]
        raw = sse(test, 0.0)
        out.append((s, len(test), (1 - sse(test, b) / raw) * 100 if raw else 0.0))
    return out


def dropping_cuts(by_season: dict, market: str) -> list[tuple]:
    """[(season, n, % of squared error cut by DROPPING the board's tilt)]."""
    out = []
    for s in sorted(by_season):
        test = [p for p in by_season[s] if p["m"] == market]
        with_tilt = sse(test, SCRIPT_COEF_PASS, SCRIPT_CLAMP)
        out.append((s, len(test), (1 - sse(test, 0.0) / with_tilt) * 100 if with_tilt else 0.0))
    return out


def _seasons(text: str) -> range:
    lo, _, hi = text.partition("-")
    return range(int(lo), int(hi or lo) + 1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="2022-2025", help="seasons held out one at a time")
    ap.add_argument("--unseen", default="2017-2021", help="older seasons, scored once at the end")
    a = ap.parse_args(argv)
    games = load_games()
    by = {s: points(load(s), load(s - 1), games, s) for s in _seasons(a.seasons)}
    old = {s: points(load(s), load(s - 1), games, s) for s in _seasons(a.unseen)}

    print("1. A quarterback's volume × (1 + b × spread), b fitted on the other seasons:")
    for m in QB_CANDIDATES:
        held = held_out(by, m)
        passed = bool(held) and all(c > 0 for *_x, c in held)
        allp = [p for s in by for p in by[s] if p["m"] == m]
        b_all = min(SLOPES, key=lambda bb: sse(allp, bb)) if allp else 0.0
        print(f"  {m:<9} " + "  ".join(f"{s}: b {b:+.4f} n {n} {c:+.2f}%" for s, b, n, c in held))
        if passed:
            unseen = fixed(old, m, b_all)
            ok = all(c > 0 for *_x, c in unseen)
            print(f"            unseen at b {b_all:+.4f}: " + "  ".join(f"{s}: {c:+.2f}%" for s, _n, c in unseen))
            print(f"            {'SHIPS' if ok else 'fails the unseen seasons — not applied'}")
        else:
            print("            fails a held-out season — not applied")

    print("\n2. The board's old tilt (+0.004 a point), % of error cut by DROPPING it:")
    for m in OLD_TILT:
        held = dropping_cuts(by, m)
        unseen = dropping_cuts(old, m)
        retire = all(c > 0 for *_x, c in held) and sum(1 for *_x, c in unseen if c < 0) < 3
        print(f"  {m:<10} " + "  ".join(f"{s}: {c:+.2f}%" for s, _n, c in held)
              + "  | " + "  ".join(f"{s}: {c:+.2f}%" for s, _n, c in unseen)
              + f"   {'RETIRE' if retire else 'keep'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
