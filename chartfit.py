#!/usr/bin/env python3
"""Does the play charting tell us anything the box score does not? — measured.

    python3 chartfit.py                 # fit 2022-2024, held-out 2025
    python3 chartfit.py 2023 2025       # other first/held-out seasons

Ethan, 2026-09-28: "what else can we add that's free". engine/sources/ftn
reads FTN's per-play charting (free by way of nflverse, 2022 on) and
engine/sources/nflscheme now reads all four of PFR's weekly files. This
is the information test each number has to pass before it reaches a
projection — the same harness as ngsfit.py, walk-forward and held out:

    every game in the held-out season is projected from the games before
    it only (marketfit's blend), and scored against a trailing-average
    line by ranking AUC. Each market is scored twice on the same games:
    the box-score projection alone, and the same projection tilted by
    the charting number from the last six charted weeks — the tilt's
    size fitted on the seasons BEFORE the held-out one (a grid over k,
    per standard deviation of the number), so the held-out figure is
    never fitted on itself.

The number can be the player's own (a receiver's drop rate, a passer's
interception-worthy rate), his offence's (whoever threw, how often it
was catchable), or the DEFENCE he faces (how often it blitzes, how often
it stacks the box) — the last is the kind the scan's notes carry and
scanfit found no lift in with sacks and hits; here it is the charted
rushers and box count.

THE RULE, as everywhere in this repo: a number ships only if the held-out
gain is two standard errors from zero and positive in at least three of
the fit seasons. Anything else is shown and left alone.

RESULT (2026-09-28, fitted 2022-2024, held out 2025): none of the nineteen
clears. The one with a consistent direction is a passer's play-action
rate on his passing yards, +0.005 ± 0.005 AUC, up in all three fit
seasons — inside one standard error, the first to re-test next season.
Interception-worthy throws on the interceptions market fitted hardest
(k 0.20) and lost it held out (−0.016 ± 0.009): interceptions are near
coin flips (base AUC 0.537) and the charted rate did not change that.
Drops, catchable balls, contested targets, the defence's blitz and box
rates, PFR's pressure rate, broken tackles and yards after contact, and
the separation and cushion a defence allows all fit at zero or went the
wrong way. So: this season's charting is on the scan as what was
noticed, the reads quote it, and no projection reads it.
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict

import marketfit as M
import ngsfit as NG
from engine.sources import ftn as F
from engine.sources import nflscheme as N

#: (market, position, who the number belongs to, table, numerator,
#:  denominator, the tilt's sign, the least denominator for a prior)
#: ``who``: player (by gsis id), name (by PFR's name), team (his offence),
#: opp (the defence he faces). ``den`` None: the prior is the mean of a
#: weekly rate PFR already gives.
TESTS = [
    ("pass_int", "QB", "player", "qb", "iw", "attempts", +1, 60),
    ("pass_yds", "QB", "player", "qb", "catchable", "attempts", +1, 60),
    ("pass_yds", "QB", "player", "qb", "play_action", "dropbacks", +1, 60),
    ("pass_yds", "QB", "opp", "defense", "blitz", "dropbacks", +1, 100),
    ("pass_yds", "QB", "opp", "defense", "pressures", "dropbacks", -1, 100),
    ("pass_yds", "QB", "name", "pfr_pass", "times_pressured_pct", None, -1, 3),
    ("receptions", "WR", "player", "receiver", "drops", "catchable", -1, 15),
    ("receptions", "WR", "team", "offense", "catchable", "attempts", +1, 60),
    ("receptions", "WR", "opp", "defense", "blitz", "dropbacks", +1, 100),
    ("rec_yds", "WR", "team", "offense", "catchable", "attempts", +1, 60),
    ("rec_yds", "WR", "player", "receiver", "contested", "targets", -1, 15),
    ("rush_yds", "RB", "opp", "defense", "heavy_box", "runs", -1, 60),
    ("rush_yds", "RB", "opp", "defense", "light_box", "runs", +1, 60),
    ("rush_yds", "RB", "name", "pfr_rush", "rushing_broken_tackles", "carries", +1, 40),
    ("rush_yds", "RB", "name", "pfr_rush", "rushing_yards_after_contact", "carries", +1, 40),
    # THE DEFENCE'S SIDE OF NEXT GEN STATS (engine/sources/ngs.defense_weeks):
    # the separation and cushion a defence allowed the receivers it faced.
    ("rec_yds", "WR", "opp", "ngs_def", "avg_separation_x", "targets", +1, 60),
    ("rec_yds", "WR", "opp", "ngs_def", "avg_cushion_x", "targets", +1, 60),
    ("receptions", "WR", "opp", "ngs_def", "avg_separation_x", "targets", +1, 60),
    ("receptions", "WR", "opp", "ngs_def", "avg_cushion_x", "targets", +1, 60),
]
KIND = {mk: kind for mk, _pos, kind in M.CANDIDATES}
COLS = NG.COLS
KS = NG.KS


def _merge(parts: list) -> dict:
    """Season tables {key: [(s, w, counts)]} into one history per key."""
    out: dict = defaultdict(list)
    for tbl in parts:
        for key, weeks in tbl.items():
            out[key].extend(weeks)
    for key in out:
        out[key].sort(key=lambda t: (t[0], t[1]))
    return dict(out)


def _pfr_weeks(rows, season: int, key_col: str, fields: tuple) -> dict:
    """PFR rows into {key: [(season, week, counts)]}, summing ``fields``
    per game; ``games`` counts the rows for a mean-of-rates prior."""
    acc: dict = defaultdict(lambda: defaultdict(float))
    for r in rows:
        if r.get("game_type") not in ("REG", ""):
            continue
        key = N.name_key(r.get("pfr_player_name") or "") if key_col == "name" else (r.get("team") or "")
        wk = int(float(r.get("week") or 0))
        if not key or not wk:
            continue
        a = acc[(key, season, wk)]
        a["games"] += 1
        for f in fields:
            a[f] += N._f(r.get(f))
    return F._weeks(acc)


def tables(first: int, held: int) -> dict:
    """Every history the tests read, over the seasons fitted and held."""
    qb, rc, df, of, pp, pr, pd = [], [], [], [], [], [], []
    for yr in range(first, held + 1):
        rows = F.joined(yr)
        qb.append(F.qb_weeks(rows, yr))
        rc.append(F.receiver_weeks(rows, yr))
        d = F.defense_weeks(rows, yr)
        df.append(d)
        of.append(F.offense_weeks(rows, yr))
        pp.append(_pfr_weeks(N.load_pfr_pass(yr), yr, "name", ("times_pressured_pct",)))
        pr.append(_pfr_weeks(N.load_pfr_rush(yr), yr, "name",
                             ("carries", "rushing_broken_tackles", "rushing_yards_after_contact")))
        # PFR's pressures per defender, summed to the defence, over the
        # charted dropbacks it faced that week.
        dd = _pfr_weeks(N.load_pfr_def(yr), yr, "team", ("def_pressures",))
        for team, weeks in dd.items():
            faced = {(s, w): c.get("dropbacks", 0) for s, w, c in d.get(team, [])}
            for i, (s, w, c) in enumerate(weeks):
                weeks[i] = (s, w, {"pressures": c["def_pressures"], "dropbacks": faced.get((s, w), 0)})
        pd.append(dd)
    merged_def = _merge(df)
    for team, weeks in _merge(pd).items():
        merged_def.setdefault(team, [])
        merged_def[team] = sorted(merged_def[team] + [(s, w, {"pressures": c["pressures"]}) for s, w, c in weeks
                                                      if c["dropbacks"]], key=lambda t: (t[0], t[1]))
    from engine.sources import ngs as NGS
    ngs_def = NGS.defense_weeks(NGS.fetch("receiving"))
    return {"qb": _merge(qb), "receiver": _merge(rc), "defense": merged_def, "offense": _merge(of),
            "pfr_pass": _merge(pp), "pfr_rush": _merge(pr), "ngs_def": ngs_def}


def _prior(hist, yr, wk, num, den, min_den):
    if den is None:
        before = [c for s, w, c in hist if (s, w) < (yr, wk)][-6:]
        if len(before) < min_den:
            return None
        return sum(c.get(num, 0.0) for c in before) / len(before)
    if num == "pressures":
        # Two histories interleaved: PFR's pressures and FTN's dropbacks
        # for the same weeks; pool each over the window.
        before = [(s, w, c) for s, w, c in hist if (s, w) < (yr, wk)]
        weeks = sorted({(s, w) for s, w, _c in before})[-6:]
        p = sum(c.get("pressures", 0) for s, w, c in before if (s, w) in weeks)
        d = sum(c.get("dropbacks", 0) for s, w, c in before if (s, w) in weeks)
        return p / d if d >= min_den else None
    return F.rate_prior(hist, yr, wk, num, den, n=6, min_den=min_den)


def _cases(rows, T, test, seasons):
    market, pos, who, table, num, den, _sign, min_den = test
    league = {market: NG._league(rows, market, pos, max(seasons) + 1)}
    hist: dict = defaultdict(list)
    kind = KIND.get(market, "ou")
    out = []
    for yr, wk, name, p, r in rows:
        if p != pos:
            continue
        y = M._f(r, COLS.get(market) or M.COLS[market])
        h, rh = hist[(name, market)], hist[(name, "role")]
        if (yr in seasons and len(h) >= M.MIN_GAMES and len(rh) >= 3
                and sum(rh[:3]) / 3 >= M.ROLE_FLOOR[pos]):
            key = {"player": r.get("player_id"), "name": N.name_key(name), "team": r.get("team"),
                   "opp": r.get("opponent_team")}[who]
            pri = _prior(T[table].get(key) or [], yr, wk, num, den, min_den) if key else None
            proj = M.blend(h, league[market])
            if pri is not None:
                if kind == "count1":
                    out.append((yr, proj, None, 0.5, pri, y >= 1))
                else:
                    last = h[:NG.LINE_GAMES]
                    line = max(0.5, round(sum(last) / len(last) * 2) / 2 - 0.5)
                    career = sum(h) / len(h)
                    sd = (sum((v - career) ** 2 for v in h) / max(1, len(h) - 1)) ** 0.5 or 1.0
                    if y != line:
                        out.append((yr, proj, sd, line, pri, y > line))
        h.insert(0, y)
        hist[(name, "role")].insert(0, M._f(r, M.ROLE_COL[pos]))
    return out


def _score(cases, k, sign, mu, sd_m):
    pairs = []
    for _yr, proj, sd, line, pri, hit in cases:
        tilt = max(0.05, 1.0 + k * sign * (pri - mu) / sd_m)
        if sd is None:
            pairs.append((1 - math.exp(-proj * tilt), hit))
        else:
            pairs.append((1 - M._norm_cdf((line + 0.5 - proj * tilt) / sd), hit))
    return pairs


def run(first: int, held: int, out=print) -> list:
    rows = M.load(range(first - 1, held + 1))
    T = tables(first, held)
    results = []
    out(f"Play charting, walk-forward: fitted on {first}-{held - 1}, held out {held}. "
        f"AUC of the box-score projection alone → with the charted number tilted in (Δ ± bootstrap).\n")
    for test in TESTS:
        market, pos, who, table, num, den, sign, _min = test
        label = f"{who}:{table}.{num}" + (f"/{den}" if den else "")
        fit = _cases(rows, T, test, set(range(first, held)))
        held_cases = _cases(rows, T, test, {held})
        if len(fit) < 100 or len(held_cases) < 60:
            out(f"  {market:10} {pos:3} {label:42} too few charted games (fit {len(fit)}, held {len(held_cases)})")
            continue
        mu, sd_m = NG._z([c[4] for c in fit])
        best_k, best = 0.0, None
        for k in KS:
            a = M.auc(_score(fit, k, sign, mu, sd_m))[0]
            if a is not None and (best is None or a > best + 1e-9):
                best_k, best = k, a
        base = _score(held_cases, 0.0, sign, mu, sd_m)
        tilted = _score(held_cases, best_k, sign, mu, sd_m)
        a0, a1 = M.auc(base)[0], M.auc(tilted)[0]
        se = NG._boot_diff(base, tilted)
        per = {}
        for yr in range(first, held):
            fy = [c for c in fit if c[0] == yr]
            if len(fy) >= 40:
                b0 = M.auc(_score(fy, 0.0, sign, mu, sd_m))[0]
                b1 = M.auc(_score(fy, best_k, sign, mu, sd_m))[0]
                if b0 is not None and b1 is not None:
                    per[yr] = round(b1 - b0, 4)
        delta = (a1 - a0) if a0 is not None and a1 is not None else 0.0
        up = sum(1 for v in per.values() if v > 0)
        ships = best_k > 0 and delta >= 2 * se and up >= min(3, len(per))
        results.append({"market": market, "pos": pos, "who": who, "table": table, "metric": num, "den": den,
                        "k": best_k, "auc0": a0, "auc1": a1, "delta": delta, "se": se, "n": len(held_cases),
                        "per": per, "ships": ships})
        out(f"  {market:10} {pos:3} {label:42} {a0:.3f} → {a1:.3f}  Δ {delta:+.4f} ± {se:.4f}  "
            f"k {best_k:.2f}  n {len(held_cases)}  fit seasons up {up}/{len(per)}  "
            f"{'CLEARS' if ships else 'stays a signal'}")
    return results


def main(argv) -> int:
    first = int(argv[1]) if len(argv) > 1 else F.FIRST_SEASON
    held = int(argv[2]) if len(argv) > 2 else 2025
    run(first, held)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
