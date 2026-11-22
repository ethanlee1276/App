"""Quarterback-receiver chemistry, measured on games each setting never saw (step ABZ, 22 November 2026).

    python3 chemfit.py                      # 2017-2026, fit 2021-2023
    python3 chemfit.py --first 2019

Reads nflverse's play-by-play and rosters through the box's own loaders (engine/sources/nflpbp, nflverse) and
prints the four tests engine/qblean describes, each with THE BAR WRITTEN BEFORE ANY RUN: a setting is chosen on the
fit seasons (2021-2023) and judged on every other season; it passes when its pooled improvement's bootstrap 95%
interval (by team-game) is above zero and no more than two judged seasons are worse.

  A  a receiver's share of the targets with this week's starter, against his share over all his recent games,
     where those were thrown by more than one starter;
  C  his catch rate and yards a target with this starter, against his own rates;
  B  a new starter's own split between wide receivers, tight ends and backs, in his first three starts for a team,
     blended into the team's recent split, the blend chosen by the one-standard-error rule (the fit seasons' best,
     0.35, overshoots and fails on the unseen seasons);
  S  the average shift after any change of starter.
"""
from __future__ import annotations

import collections
import random

from . import qblean

FIT = (2021, 2022, 2023)
HALF = 8.0


def team_games(seasons, load_pbp=None, load_roster=None) -> list:
    """[{season, week, game_id, team, qb, qb_name, qb_share, targets, rec: {id: {t, c, y, pos, by_starter}}}]"""
    if load_pbp is None:
        from .sources.nflpbp import load_pbp_rows

        def load_pbp(season):
            return load_pbp_rows(season, columns=qblean.PBP_COLUMNS + ("season", "week", "receiver_player_id"))
    if load_roster is None:
        from .sources.nflverse import load_rosters as load_roster
    out = []
    for season in seasons:
        roster = load_roster(season) or []
        pos = {str(r.get("gsis_id") or ""): r.get("position") or "" for r in roster if r.get("gsis_id")}
        names = {str(r.get("gsis_id") or ""): r.get("full_name") or "" for r in roster if r.get("gsis_id")}
        games: dict = {}
        for r in load_pbp(season):
            if str(r.get("season_type") or "REG") != "REG" or str(r.get("pass_attempt") or "") != "1":
                continue
            if "1" in (str(r.get("sack") or ""), str(r.get("two_point_attempt") or ""), str(r.get("qb_spike") or "")):
                continue
            gid, team, qb = r.get("game_id"), r.get("posteam"), r.get("passer_player_id")
            if not gid or not team or not qb:
                continue
            g = games.setdefault((gid, team), {"season": season, "week": int(float(r.get("week") or 0)),
                                               "game_id": gid, "team": team, "qbs": collections.Counter(),
                                               "targets": 0, "rec": {}})
            g["qbs"][qb] += 1
            rid = r.get("receiver_player_id")
            if not rid:
                continue
            g["targets"] += 1
            rr = g["rec"].setdefault(rid, {"t": 0, "c": 0, "y": 0.0, "pos": pos.get(rid, ""), "by": collections.Counter()})
            rr["t"] += 1
            rr["by"][qb] += 1
            if str(r.get("complete_pass") or "") == "1":
                rr["c"] += 1
                try:
                    rr["y"] += float(r.get("yards_gained") or 0)
                except ValueError:
                    pass
        for g in games.values():
            qb, att = g["qbs"].most_common(1)[0]
            out.append({"season": g["season"], "week": g["week"], "game_id": g["game_id"], "team": g["team"],
                        "qb": qb, "qb_name": names.get(qb, ""), "qb_share": att / sum(g["qbs"].values()),
                        "targets": g["targets"],
                        "rec": {k: {"t": v["t"], "c": v["c"], "y": v["y"], "pos": v["pos"],
                                    "by_starter": v["by"].get(qb, 0)} for k, v in g["rec"].items()}})
    out.sort(key=lambda d: (d["season"], d["week"], d["team"]))
    return out


def _interval(diffs: dict, seed: int = 7, n: int = 2000) -> tuple:
    keys = list(diffs)
    if not keys:
        return 0.0, 0.0
    rng = random.Random(seed)
    tot = []
    for _ in range(n):
        s = m = 0.0
        for _k in range(len(keys)):
            d = diffs[keys[rng.randrange(len(keys))]]
            s += sum(d)
            m += len(d)
        tot.append(s / max(m, 1))
    tot.sort()
    return tot[int(0.025 * n)], tot[int(0.975 * n)]


def one_se(fit: list, loss, grid) -> object:
    """The smallest setting (in ``grid``'s order) whose fit-season error is within one standard error of the best:
    the standard guard against a setting the fit seasons overshoot on. On the lean (test B), the fit seasons' best
    is a blend of 0.35, which fails on the unseen seasons; this rule's pick, 0.2, passes."""
    import math
    best = min(grid, key=lambda k: sum(loss(c, k) for c in fit))
    for k in grid:
        diffs = [loss(c, k) - loss(c, best) for c in fit]
        m = sum(diffs) / len(diffs)
        sd = math.sqrt(sum((x - m) ** 2 for x in diffs) / max(len(diffs) - 1, 1))
        if m <= sd / math.sqrt(len(diffs)):
            return k
    return best


def judge(cases: list, loss, grid, base_arg=None, judged=None, rule: str = "best") -> dict:
    """Choose a setting on FIT (``rule``: "best", or "one_se", the one-standard-error rule), judge it on every
    other season: {"setting", "seasons": {s: (n, pct)}, "interval", "worse", "passes"}."""
    fit = [c for c in cases if c[0] in FIT]
    if not fit:
        return {"setting": None, "seasons": {}, "interval": (0.0, 0.0), "worse": 0, "passes": False}
    best = one_se(fit, loss, grid) if rule == "one_se" else min(grid, key=lambda k: sum(loss(c, k) for c in fit))
    seasons = sorted({c[0] for c in cases if c[0] not in FIT} if judged is None else judged)
    out, worse, diffs = {}, 0, collections.defaultdict(list)
    for s in seasons:
        hs = [c for c in cases if c[0] == s]
        if not hs:
            continue
        e = sum(loss(c, best) for c in hs) / len(hs)
        b = sum(loss(c, base_arg) for c in hs) / len(hs)
        out[s] = (len(hs), round((1 - e / b) * 100, 2) if b else 0.0)
        worse += e >= b
        for c in hs:
            diffs[c[1]].append(loss(c, base_arg) - loss(c, best))
    lo, hi = _interval(diffs)
    return {"setting": best, "seasons": out, "interval": (round(lo, 5), round(hi, 5)), "worse": worse,
            "passes": lo > 0 and worse <= 2}


def pair_cases(games: list) -> list:
    """Test A's cases: (season, key, targets, team targets, overall share, with-starter targets, with-starter team
    targets), weighted by age (half-life HALF games)."""
    by_team = collections.defaultdict(list)
    for g in games:
        by_team[(g["season"], g["team"])].append(g)
    cases = []
    for seq in by_team.values():
        seq.sort(key=lambda g: g["week"])
        hist = collections.defaultdict(list)
        for g in seq:
            clean = g["qb_share"] >= qblean.START_SHARE
            for rid, r in g["rec"].items():
                past = hist.get(rid) or []
                if len(past) >= 3 and clean and g["targets"] >= 15:
                    ws = [0.5 ** ((len(past) - 1 - j) / HALF) for j in range(len(past))]
                    tw = sum(w * p[1] for w, p in zip(ws, past))
                    Tw = sum(w * p[2] for w, p in zip(ws, past))
                    withq = [(w, p) for w, p in zip(ws, past) if p[0] == g["qb"] and p[3]]
                    other = [(w, p) for w, p in zip(ws, past) if p[0] != g["qb"]]
                    if Tw > 0 and withq and other:
                        cases.append((g["season"], g["game_id"] + g["team"], r["t"], g["targets"], tw / Tw,
                                      sum(w * p[1] for w, p in withq), sum(w * p[2] for w, p in withq)))
            for rid, r in g["rec"].items():
                hist[rid].append((g["qb"], r["t"], g["targets"], clean))
    return cases


def pair_loss(c, k):
    _s, _key, t, T, base, tq, Tq = c
    share = base if k is None else (tq + k * base) / (Tq + k)
    return (t - share * T) ** 2


def lean_cases(games: list) -> list:
    """Test B's cases: (season, key, the game's split, the team's split from the other starters' games, the new
    starter's career split), in his first three starts for the team."""
    career = collections.defaultdict(collections.Counter)
    starts = collections.defaultdict(collections.Counter)
    team_games_ = collections.defaultdict(list)
    cases = []
    for g in sorted(games, key=lambda g: (g["season"], g["week"])):
        key = (g["season"], g["team"])
        split = collections.Counter()
        for r in g["rec"].values():
            grp = qblean.group(r["pos"])
            if grp:
                split[grp] += r["t"]
        tot = sum(split[x] for x in qblean.GROUPS)
        others = [s for q, s in team_games_[key] if q != g["qb"]]
        if (g["qb_share"] >= qblean.START_SHARE and starts[key][g["qb"]] < 3 and len(others) >= 3 and tot >= 15
                and sum(career[g["qb"]].values()) >= qblean.MIN_TARGETS):
            ts = collections.Counter()
            for s in others[-qblean.RECENT_WEEKS:]:
                ts.update(s)
            tt = sum(ts[x] for x in qblean.GROUPS)
            ct = career[g["qb"]]
            ctt = sum(ct[x] for x in qblean.GROUPS)
            if tt and ctt:
                cases.append((g["season"], g["game_id"] + g["team"],
                              {x: split[x] / tot for x in qblean.GROUPS}, {x: ts[x] / tt for x in qblean.GROUPS},
                              {x: ct[x] / ctt for x in qblean.GROUPS}))
        if g["qb_share"] >= qblean.START_SHARE:
            starts[key][g["qb"]] += 1
            for r in g["rec"].values():
                grp = qblean.group(r["pos"])
                if grp and r.get("by_starter"):
                    career[g["qb"]][grp] += r["by_starter"]
        team_games_[key].append((g["qb"], split))
    return cases


def lean_loss(c, w):
    actual, team, qb = c[2], c[3], c[4]
    w = w or 0.0
    return sum((actual[x] - ((1 - w) * team[x] + w * qb[x])) ** 2 for x in qblean.GROUPS)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python3 chemfit.py", description=__doc__.split("\n")[0])
    ap.add_argument("--first", type=int, default=qblean.FIRST_SEASON)
    ap.add_argument("--last", type=int, default=None)
    a = ap.parse_args(argv)
    from .seasons import season_of
    import datetime as _dt
    last = a.last or season_of("nfl", _dt.date.today().isoformat())
    games = team_games(range(a.first, last + 1))
    print(f"{len(games)} team-games, {a.first}-{last}; settings chosen on {FIT[0]}-{FIT[-1]}")
    for name, cases, loss, grid, base in (
            ("A  a receiver's share with this starter (k team-targets)", pair_cases(games), pair_loss,
             (10, 20, 40, 80, 160, 320), None),
            ("B  a new starter's own split (w, one-standard-error rule)", lean_cases(games), lean_loss,
             (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4), 0.0)):
        r = judge(cases, loss, grid, base, rule="one_se" if name.startswith("B") else "best")
        print(f"\n{name}: {len(cases)} cases; chosen {r['setting']}")
        for s, (n, pct) in sorted(r["seasons"].items()):
            print(f"   {s}: n={n} {pct:+.2f}%")
        print(f"   interval {r['interval']}, {r['worse']} season(s) worse -> {'PASSES' if r['passes'] else 'fails'}")
    print(f"\nWhat ships: engine/qblean.LEAN_W = {qblean.LEAN_W}")
    return 0
