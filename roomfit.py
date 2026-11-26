#!/usr/bin/env python3
"""When a team's receivers sit, how much more do the ones left get? (step AHW, 26 November 2026)

    python3 roomfit.py                                  # data/cache/player_stats_<season>.csv, 2022-2025
    python3 roomfit.py --dir /path/to/files --seasons 2016-2025

Ethan, 26 November, after Packers at Rams (Puka Nacua and Davante Adams on injured reserve): "when there is alot of
players out we dont reccomend any props for the backups ... or how there usage could step up in the game reports".
The projection lifts a receiver whose teammate ranked AHEAD of him at his own position is out (engine/teammates,
measured on 2022-2025: catches x1.19 the first game, x1.09 after); it adds nothing for the rest of the room, for a
second man out, or for the receiver whose own share is small. This measures what the room gets.

For every regular-season game from week 4 on, the team's "regulars" are its receivers, tight ends and backs who
played three or more of its earlier games this season. A regular SITS when he had 10%+ of the targets in the games
he played and has no row this week while he played in one of the team's last two games (a fresh absence: one gone
longer is in his teammates' own form already). The VACATED share is the sum of those shares.

For each regular who plays: his form is his targets (catches, receiving yards) a game over his earlier games; his
share is his share of the team's targets in them. Printed, by vacated share and by his rank among the regulars
left (by share): what he did against his form (a multiplier, pooled), how the proportional guess (his share
scaled up by 1 / (1 - vacated), times the team's own targets a game) does against it, and the same with each
season held out. Reads only the weekly box scores; writes nothing.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POS = ("WR", "TE", "RB", "FB")
FIRST_WEEK, MIN_PRIOR, SIT_SHARE, FRESH = 4, 3, 0.10, 2
BUCKETS = ((0.10, 0.20), (0.20, 0.35), (0.35, 1.01))
STATS = ("targets", "receptions", "receiving_yards")


def _f(r, k) -> float:
    try:
        return float(r.get(k) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def engine_lift(rows: list[dict]):
    """A function (team, week, name, pos, market) -> the lift our projection already applies (engine/teammates.EFFECT,
    the targets-ranked depth order engine/matefit measured it on), 1.0 where it applies none."""
    from engine import matefit as MF
    from engine.teammates import EFFECT
    games, team_weeks = MF._games_from_stats(rows)
    cache: dict = {}

    def lift(team, wk, name, pos, market):
        key = (team, wk, pos)
        if key not in cache:
            order = MF.ranked(games, team, pos, wk)
            playing = {o[0] for o in order if wk in games[(team, pos, o[0])]}
            last = max((w for w in team_weeks.get(team, ()) if w < wk), default=0)
            cache[key] = (order, playing, last)
        order, playing, last = cache[key]
        case = MF.case_for(order, name, playing, last)
        return EFFECT.get((market, pos, case), 1.0) if case else 1.0
    return lift


def load(path: Path) -> dict:
    """{team: {week: {player_id: row}}} for one season's regular-season receivers, tight ends and backs."""
    out: dict = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if str(r.get("season_type") or "").upper() != "REG":
                continue
            pos = str(r.get("position") or "").upper()
            team = r.get("team") or r.get("recent_team") or ""
            try:
                wk = int(r.get("week") or 0)
            except ValueError:
                continue
            if not team or not wk:
                continue
            week = out.setdefault(team, {}).setdefault(wk, {})
            if pos in POS:
                week[r.get("player_id") or r.get("player_display_name")] = {
                    "name": r.get("player_display_name") or r.get("player_name") or "", "pos": pos,
                    **{k: _f(r, k) for k in STATS}}
            else:
                week.setdefault("_team_played", {})
    for weeks in out.values():
        for wk in weeks.values():
            wk.pop("_team_played", None)
    return out


def samples(season: int, teams: dict, lift=None) -> list[dict]:
    """One row per regular who played: in a game in which a teammate's share sat (`SIT_SHARE`, fresh), or in one
    where nobody did (the control, vacated 0). ``lift`` (`engine_lift`) stamps what our projection already adds."""
    got = []
    for team, weeks in teams.items():
        order = sorted(weeks)
        for i, wk in enumerate(order):
            if wk < FIRST_WEEK:
                continue
            prior = order[:i]
            if len(prior) < MIN_PRIOR:
                continue
            team_t = {w: sum(p["targets"] for p in weeks[w].values()) for w in prior}
            seen: dict = {}
            for w in prior:
                for pid, p in weeks[w].items():
                    s = seen.setdefault(pid, {"games": 0, "t": 0.0, "team_t": 0.0, "pos": p["pos"],
                                              "name": p["name"], **{k: 0.0 for k in STATS}})
                    s["games"] += 1
                    s["team_t"] += team_t[w]
                    for k in STATS:
                        s[k] += p[k]
            regs = {pid: s for pid, s in seen.items() if s["games"] >= MIN_PRIOR and s["team_t"] > 0}
            last = set(prior[-FRESH:])
            now = weeks[wk]
            sat = []
            for pid, s in regs.items():
                share = s["targets"] / s["team_t"]
                if pid in now or share < SIT_SHARE:
                    continue
                if not any(pid in weeks[w] for w in last):
                    continue
                sat.append((share, s["pos"], s["name"]))
            # NOBODY SAT: the control. The weekly file has no row for a game with no catch and no carry, so a
            # low-volume player's form and his games both leave his empty ones out; the same players in games
            # where nobody sat carry that bias too, and the step up is read against them.
            vacated = min(0.8, sum(x[0] for x in sat)) if sat else 0.0
            team_pg = sum(team_t.values()) / len(prior)
            left = sorted(((s["targets"] / s["team_t"], pid, s) for pid, s in regs.items() if pid in now),
                          key=lambda x: -x[0])
            # THE GAMES THIS SEASON WITHOUT THE MAN WHO LEFT THE MOST: each player's own numbers in the team's
            # earlier games the biggest share that sat tonight also missed (`without`).
            top_sat = max(((s_["targets"] / s_["team_t"], pid_) for pid_, s_ in regs.items()
                           if pid_ not in now and pid_ in {p_ for w_ in last for p_ in weeks[w_]}
                           and s_["targets"] / s_["team_t"] >= SIT_SHARE), default=(0.0, None))[1]
            wo_weeks = [w for w in prior if top_sat and top_sat not in weeks[w]]
            for rank, (share, pid, s) in enumerate(left, 1):
                form = {k: s[k] / s["games"] for k in STATS}
                if form["targets"] < 1.0:
                    continue
                prop_t = share / (1.0 - vacated) * team_pg
                eng = {k: (lift(team, wk, s["name"], s["pos"], m) if lift else 1.0)
                       for k, m in (("targets", "receptions"), ("receptions", "receptions"),
                                    ("receiving_yards", "rec_yds"))}
                mine = [weeks[w][pid] for w in wo_weeks if pid in weeks[w]]
                wo = {k: sum(g[k] for g in mine) / len(mine) for k in STATS} if mine else None
                got.append({"season": season, "team": team, "week": wk, "name": s["name"], "pos": s["pos"],
                            "engine": eng, "wo": wo, "n_wo": len(mine),
                            "rank": rank, "share": share, "vacated": vacated, "form": form,
                            "prop_t": prop_t, "actual": {k: now[pid][k] for k in STATS},
                            "same_pos": any(x[1] == s["pos"] for x in sat),
                            "team_actual_t": sum(p["targets"] for p in now.values()), "team_pg": team_pg})
    return got


RANKS = ((1, 1, "top left"), (2, 2, "second"), (3, 3, "third"), (4, 99, "fourth on"))
#: The cells the projection would take (vacated buckets from 20%, by rank left).
CELLS = [(lo, hi, rlo, rhi) for lo, hi in BUCKETS[1:] for rlo, rhi, _l in RANKS]


def residual(rows, ctl, stat) -> tuple:
    """(actual / (form x the engine's own lift), divided by the control's actual / form; se; n)."""
    m, se, n = ratio(rows, stat, pred=lambda r: r["form"][stat] * r["engine"][stat])
    c, sec, _ = ratio(ctl, stat)
    if not m or not c:
        return None, None, n
    return m / c, math.sqrt((se / c) ** 2 + (m * sec / c / c) ** 2), n


def held_out(pool, per, stat) -> list:
    """Each season held out: the residual cells fitted on the others, and the held-out season's squared error with
    the engine's lift alone against with the cells too (both times the rank's own lean)."""
    out = []
    for y in sorted(per):
        train = [r for r in pool if r["season"] != y]
        test = [r for r in pool if r["season"] == y]
        lean, cell = {}, {}
        for rlo, rhi, _l in RANKS:
            ctl = [r for r in train if r["vacated"] == 0.0 and rlo <= r["rank"] <= rhi]
            lean[(rlo, rhi)] = ratio(ctl, stat)[0] or 1.0
        for lo, hi, rlo, rhi in CELLS:
            sub = [r for r in train if lo <= r["vacated"] < hi and rlo <= r["rank"] <= rhi]
            ctl = [r for r in train if r["vacated"] == 0.0 and rlo <= r["rank"] <= rhi]
            cell[(lo, hi, rlo, rhi)] = residual(sub, ctl, stat)[0] or 1.0
        e0 = e1 = 0.0
        n = 0
        for r in test:
            if r["vacated"] < BUCKETS[1][0]:
                continue
            k = next((c for c in CELLS if c[0] <= r["vacated"] < c[1] and c[2] <= r["rank"] <= c[3]), None)
            if not k:
                continue
            base = r["form"][stat] * r["engine"][stat] * lean[(k[2], k[3])]
            e0 += (r["actual"][stat] - base) ** 2
            e1 += (r["actual"][stat] - base * cell[k]) ** 2
            n += 1
        if n:
            out.append((y, n, math.sqrt(e0 / n), math.sqrt(e1 / n)))
    return out


def net(pool, lo, hi, rank_lo, rank_hi, stat) -> tuple:
    """(his multiplier over form when lo-hi of the targets sat, divided by the same rank's in games where
    nobody sat; its standard error; n)."""
    sub = [r for r in pool if lo <= r["vacated"] < hi and rank_lo <= r["rank"] <= rank_hi]
    ctl = [r for r in pool if r["vacated"] == 0.0 and rank_lo <= r["rank"] <= rank_hi]
    m, se, n = ratio(sub, stat)
    c, sec, _nc = ratio(ctl, stat)
    if not m or not c:
        return None, None, n
    return m / c, math.sqrt((se / c) ** 2 + (m * sec / c / c) ** 2), n


def ratio(rows, stat: str, pred=None) -> tuple:
    """(pooled actual / predicted, its standard error by the delta method, n)."""
    if not rows:
        return None, None, 0
    a = [r["actual"][stat] for r in rows]
    p = [pred(r) if pred else r["form"][stat] for r in rows]
    sa, sp = sum(a), sum(p)
    if sp <= 0:
        return None, None, len(rows)
    m = sa / sp
    resid = [x - m * y for x, y in zip(a, p)]
    var = sum(e * e for e in resid) / max(1, len(rows) - 1)
    return m, math.sqrt(var * len(rows)) / sp, len(rows)


def mae(rows, pred) -> float:
    return sum(abs(r["actual"]["targets"] - pred(r)) for r in rows) / len(rows) if rows else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="2022-2025")
    ap.add_argument("--dir", default=str(ROOT / "data" / "cache"))
    a, _, b = ap.parse_args().seasons.partition("-")
    args = ap.parse_args()
    years = list(range(int(a), int(b or a) + 1))
    per = {}
    for y in years:
        for name in (f"player_stats_{y}.csv", f"ps{y}.csv", f"stats_player_week_{y}.csv"):
            path = Path(args.dir) / name
            if path.is_file():
                with open(path, newline="", encoding="utf-8") as fh:
                    lift = engine_lift(list(csv.DictReader(fh)))
                per[y] = samples(y, load(path), lift)
                break
    pool = [r for y in per for r in per[y]]
    print(f"{sum(1 for r in pool if r['vacated'] > 0):,} receiver games in games where 10%+ of the targets sat, "
          f"{sum(1 for r in pool if r['vacated'] == 0):,} where nobody did, {min(per)}-{max(per)}")
    print("\nThe same players in games where nobody sat (the control: the file's own lean on small roles):")
    for rank_lo, rank_hi, label in RANKS:
        sub = [r for r in pool if r["vacated"] == 0.0 and rank_lo <= r["rank"] <= rank_hi]
        m, se, n = ratio(sub, "targets")
        my, _s, _n = ratio(sub, "receiving_yards")
        print(f"      {label:<10} targets x{m:.3f} ± {se:.3f}, yards x{my:.3f} (n {n:,})")
    print("\nNET of the control: what the room gets over the same rank's own lean, targets and yards, by season:")
    for lo, hi in BUCKETS:
        for rank_lo, rank_hi, label in RANKS:
            m, se, n = net(pool, lo, hi, rank_lo, rank_hi, "targets")
            my, sey, _ = net(pool, lo, hi, rank_lo, rank_hi, "receiving_yards")
            seasons = []
            for y in sorted(per):
                mm, _s, nn = net([r for r in pool if r["season"] == y], lo, hi, rank_lo, rank_hi, "targets")
                if mm:
                    seasons.append(f"{mm:.2f}")
            if m:
                print(f"  {lo:.0%}-{min(hi, 1):.0%} {label:<10} targets x{m:.3f} ± {se:.3f}, yards x{my:.3f} ± "
                      f"{sey:.3f} (n {n:,})   by season " + " ".join(seasons))
    print("\nBEYOND WHAT WE PRICE: over form times the lift engine/teammates already applies, net of the control:")
    for lo, hi, rlo, rhi in CELLS:
        sub = [r for r in pool if lo <= r["vacated"] < hi and rlo <= r["rank"] <= rhi]
        ctl = [r for r in pool if r["vacated"] == 0.0 and rlo <= r["rank"] <= rhi]
        label = next(lb for a_, b_, lb in RANKS if a_ == rlo)
        bits = []
        for stat in STATS:
            m, se, n = residual(sub, ctl, stat)
            bits.append(f"{stat} x{m:.3f} ± {se:.3f}")
        lifted = sum(1 for r in sub if r["engine"]["receptions"] != 1.0)
        seasons = []
        for y in sorted(per):
            mm = residual([r for r in sub if r["season"] == y], [r for r in ctl if r["season"] == y], "targets")[0]
            seasons.append(f"{mm:.2f}" if mm else "-")
        print(f"  {lo:.0%}-{min(hi, 1):.0%} {label:<10} " + "; ".join(bits)
              + f" (n {len(sub):,}, {lifted:,} already lifted)   by season " + " ".join(seasons))
    for stat in STATS:
        print(f"\nHeld out by season, {stat}: root mean squared error, the engine's lift alone vs with the cells:")
        for y, n, e0, e1 in held_out(pool, per, stat):
            print(f"  {y}: {e0:.3f} vs {e1:.3f} over {n:,} games{'  better' if e1 < e0 else ''}")
    for stat in STATS:
        print(f"\nHIS OWN GAMES WITHOUT HIM, {stat}: where the biggest share that sat also missed earlier games this "
              f"season, the blend (games without x their number + k x the projection) / (games without + k), k "
              f"fitted on the other seasons; root mean squared error, the projection alone vs the blend:")
        for y in sorted(per):
            train = [r for r in pool if r["season"] != y and r["vacated"] >= 0.20 and r["wo"]]
            test = [r for r in pool if r["season"] == y and r["vacated"] >= 0.20 and r["wo"]]
            if not train or not test:
                continue

            def base(r):
                return r["form"][stat] * r["engine"][stat]

            def err(rows, k):
                return math.sqrt(sum((r["actual"][stat] - (r["n_wo"] * r["wo"][stat] + k * base(r))
                                      / (r["n_wo"] + k)) ** 2 for r in rows) / len(rows))
            best = min((0.5, 1, 2, 3, 4, 6, 8, 12, 20, 50), key=lambda k: err(train, k))
            e0 = math.sqrt(sum((r["actual"][stat] - base(r)) ** 2 for r in test) / len(test))
            e1 = err(test, best)
            print(f"  {y}: k {best}, {e0:.3f} vs {e1:.3f} over {len(test):,} games{'  better' if e1 < e0 else ''}")
    print("\nHOW OFTEN HE BEAT OUR NUMBER (form x the engine's lift), the over/under question: the share of games "
          "above it (ties left out), in games where nobody sat and in each cell:")
    for stat in STATS:
        print(f"  {stat}:")
        for rlo, rhi, label in RANKS:
            def over(rows, mult=1.0):
                xs = [(r["actual"][stat], r["form"][stat] * r["engine"][stat] * mult) for r in rows]
                xs = [(a_, b_) for a_, b_ in xs if abs(a_ - b_) > 1e-9]
                return (sum(1 for a_, b_ in xs if a_ > b_) / len(xs), len(xs)) if xs else (None, 0)
            ctl = [r for r in pool if r["vacated"] == 0.0 and rlo <= r["rank"] <= rhi]
            c, nc = over(ctl)
            cells = []
            for lo, hi in BUCKETS:
                sub = [r for r in pool if lo <= r["vacated"] < hi and rlo <= r["rank"] <= rhi]
                o, n = over(sub)
                yrs = []
                for y in sorted(per):
                    oy, ny = over([r for r in sub if r["season"] == y])
                    yrs.append(f"{oy:.0%}" if oy is not None else "-")
                cells.append(f"{lo:.0%}+ {o:.1%} (n {n:,}; " + " ".join(yrs) + ")")
            print(f"    {label:<10} nobody sat {c:.1%} (n {nc:,}) | " + " | ".join(cells))
    print("\nTHE CALIBRATING MULTIPLIER: per cell, the multiplier on our number that brings his over rate to the same "
          "rank's rate in games where nobody sat; fitted on the other seasons, the held-out season's gap to that "
          "rate (points) without it and with it:")
    grid = [x / 100 for x in range(90, 181, 2)]
    for stat in STATS:
        print(f"  {stat}:")
        for lo, hi, rlo, rhi in CELLS:
            label = next(lb for a_, b_, lb in RANKS if a_ == rlo)

            def over(rows, mult=1.0):
                xs = [(r["actual"][stat], r["form"][stat] * r["engine"][stat] * mult) for r in rows]
                xs = [(a_, b_) for a_, b_ in xs if abs(a_ - b_) > 1e-9]
                return sum(1 for a_, b_ in xs if a_ > b_) / len(xs) if xs else None

            def fit(rows, ctl_rows):
                target = over(ctl_rows)
                if target is None or not rows:
                    return 1.0
                return min(grid, key=lambda m: abs((over(rows, m) or 0) - target))
            sub_all = [r for r in pool if lo <= r["vacated"] < hi and rlo <= r["rank"] <= rhi]
            ctl_all = [r for r in pool if r["vacated"] == 0.0 and rlo <= r["rank"] <= rhi]
            m_all = fit(sub_all, ctl_all)
            better = tot = 0
            gaps0 = gaps1 = 0.0
            for y in sorted(per):
                tr = [r for r in sub_all if r["season"] != y]
                ct = [r for r in ctl_all if r["season"] != y]
                te = [r for r in sub_all if r["season"] == y]
                cte = [r for r in ctl_all if r["season"] == y]
                if not te or not cte:
                    continue
                m = fit(tr, ct)
                target = over(cte)
                g0 = abs((over(te) or 0) - target)
                g1 = abs((over(te, m) or 0) - target)
                gaps0 += g0
                gaps1 += g1
                tot += 1
                better += g1 < g0
            print(f"    {lo:.0%}-{min(hi, 1):.0%} {label:<10} x{m_all:.2f} (n {len(sub_all):,}): held out, mean gap "
                  f"{gaps0 / tot * 100:.1f} -> {gaps1 / tot * 100:.1f} points, closer in {better} of {tot} seasons")
    print("\nWhat he did against his own form (pooled multiplier ± standard error, n), by vacated share (raw):")
    for lo, hi in BUCKETS:
        rows = [r for r in pool if lo <= r["vacated"] < hi]
        line = []
        for stat in STATS:
            m, se, n = ratio(rows, stat)
            line.append(f"{stat} x{m:.3f} ± {se:.3f}" if m else f"{stat} -")
        print(f"  {lo:.0%}-{min(hi, 1):.0%} (n {len(rows):,}): " + "; ".join(line))
        for rank_lo, rank_hi, label in ((1, 1, "top left"), (2, 2, "second"), (3, 3, "third"), (4, 99, "fourth on")):
            sub = [r for r in rows if rank_lo <= r["rank"] <= rank_hi]
            m, se, n = ratio(sub, "targets")
            my, sey, _ = ratio(sub, "receiving_yards")
            by_season = []
            for y in sorted(per):
                mm, _s, nn = ratio([r for r in sub if r["season"] == y], "targets")
                if mm:
                    by_season.append(f"{y}: {mm:.2f}")
            if m:
                print(f"      {label:<10} targets x{m:.3f} ± {se:.3f}, yards x{my:.3f} ± {sey:.3f} (n {n:,})   "
                      + "  ".join(by_season))
    print("\nThe team's own targets that game against its targets a game before (does the room shrink?):")
    for lo, hi in BUCKETS:
        rows = {(r["season"], r["team"], r["week"]): r for r in pool if lo <= r["vacated"] < hi}
        a_ = sum(r["team_actual_t"] for r in rows.values())
        p_ = sum(r["team_pg"] for r in rows.values())
        print(f"  {lo:.0%}-{min(hi, 1):.0%}: x{a_ / p_:.3f} over {len(rows):,} team games" if p_ else "")
    print("\nTargets, mean absolute error: his form, the proportional guess, and the blend that weighs the guess k:")
    for lo, hi in BUCKETS:
        rows = [r for r in pool if lo <= r["vacated"] < hi]
        cells = []
        for k in (0.0, 0.25, 0.5, 0.75, 1.0):
            cells.append(f"k {k:.2f}: {mae(rows, lambda r, k=k: r['form']['targets'] + k * (r['prop_t'] - r['form']['targets'])):.3f}")
        print(f"  {lo:.0%}-{min(hi, 1):.0%}: " + "  ".join(cells))
    print("\nThe blend's k, fitted on the other seasons and scored on each one held out (targets MAE, form vs blend):")
    for y in sorted(per):
        train = [r for r in pool if r["season"] != y and r["vacated"] >= 0.20]
        test = [r for r in per[y] if r["vacated"] >= 0.20]
        if not train or not test:
            continue
        best = min((k / 20 for k in range(21)),
                   key=lambda k: mae(train, lambda r: r["form"]["targets"] + k * (r["prop_t"] - r["form"]["targets"])))
        f0 = mae(test, lambda r: r["form"]["targets"])
        f1 = mae(test, lambda r: r["form"]["targets"] + best * (r["prop_t"] - r["form"]["targets"]))
        print(f"  {y}: k {best:.2f} (fitted on the rest), form {f0:.3f} vs blend {f1:.3f} over {len(test):,} games")
    if os.environ.get("ROOMFIT_EXAMPLES"):
        for r in [r for r in pool if r["vacated"] >= 0.35][:10]:
            print(r["season"], r["team"], r["week"], r["name"], r["rank"], round(r["vacated"], 2), r["form"],
                  r["actual"])


if __name__ == "__main__":
    main()
