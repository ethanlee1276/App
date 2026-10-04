#!/usr/bin/env python3
"""Can the model sort a market it does not carry yet? — measured.

    python3 marketfit.py                  # the cached 2021-2025 box scores
    python3 marketfit.py 2023 2024 2025   # other seasons (the last is held out)

Ethan, 2026-09-27: "we dont have a market for interceptions, QB over or
under rushing yards, or some other stuff that the ai recommends".

The repo's rule for a new market is measured before added
(sources/nflverse.POSITION_MARKETS, engine/passtd). This is that
measurement, for the markets a book hangs and this board did not carry:

  pass_att    a quarterback's pass attempts        player_pass_attempts
  pass_cmp    his completions                      player_pass_completions
  pass_int    his interceptions (1 or more)        player_pass_interceptions
  rush_att    a back's carries                     player_rush_attempts
  rush_yds    a QUARTERBACK's rushing yards        player_rush_yds (already bought)

plus the markets the board already carries, in the same harness, so the
new figures are read beside known ones rather than against a bar alone.

WALK-FORWARD, HELD OUT. Every game in the last season is projected from
the games before it only (this season and earlier, most recent first):
the passing-touchdown blend — career and last eight averaged, shrunk
toward the league by two notional games — and scored against a
trailing-average line (last five games, rounded to the half like a
book hangs it). The figure is ranking AUC: the chance a game that went
over is ranked above one that went under. Interceptions and passing
touchdowns are scored as one-or-more against a Poisson arm at the rate;
interceptions once more with the opponent's own rate (its games so far)
scaling the arm. Only rows with a real role — three prior games and a
recent role of 15 attempts / 8 carries / 4 targets a game — count, since
those are the men a book prices. A cluster bootstrap gives each figure
its ±.

Measured 2026-09-27 (held-out 2025):

    pass_att    QB   0.707 ± 0.023   n=531
    pass_cmp    QB   0.696 ± 0.023   n=527
    rush_att    RB   0.632 ± 0.023   n=638
    rush_yds    QB   0.616 ± 0.022   n=532     (0.536 in the first, coarser harness)
    rush_yds    RB   0.616 ± 0.023   n=653     same harness: a back ranks no better
    receptions  WR   0.619 ± 0.018   n=1045
    rec_yds     WR   0.603 ± 0.017   n=1107
    pass_td     QB   0.627 ± 0.027   n=539     (engine/passtd's own fit: 0.687)
    pass_int    QB   0.540 ± 0.028   n=539     a coin
    pass_int+opp     0.568 ± 0.026   n=539     still under the bar

So attempts, completions, carries and a quarterback's rushing went on
(engine/models PASS_ATT…, likely.RANK_AUC); interceptions did not. This
harness runs stricter than the one behind likely.RANK_AUC's older
figures (it scores catches at 0.619, not 0.770) — compare within it.

Reads the nflverse cache only; writes nothing.
"""
from __future__ import annotations

import bisect
import csv
import math
import random
import sys
from collections import defaultdict

from engine.sources.fetch import CACHE_DIR

COLS = {"pass_int": "passing_interceptions", "pass_att": "attempts", "pass_cmp": "completions",
        "rush_att": "carries", "rush_yds": "rushing_yards", "receptions": "receptions",
        "pass_td": "passing_tds", "rec_yds": "receiving_yards"}
#: (market, position, how it is scored): "count1" is one-or-more on a
#: Poisson arm; "ou" is over/under a trailing-average line.
CANDIDATES = [("pass_int", "QB", "count1"), ("pass_td", "QB", "count1"), ("pass_att", "QB", "ou"),
              ("pass_cmp", "QB", "ou"), ("rush_att", "RB", "ou"), ("rush_yds", "QB", "ou"),
              ("rush_yds", "RB", "ou"), ("receptions", "WR", "ou"), ("rec_yds", "WR", "ou")]
ROLE_COL = {"QB": "attempts", "RB": "carries", "WR": "targets"}
ROLE_FLOOR = {"QB": 15.0, "RB": 8.0, "WR": 4.0}
MIN_GAMES = 3
RECENT, PRIOR, LINE_GAMES = 8, 2, 5
BOOT = 200


def _f(r, k):
    try:
        return float(r.get(k) or 0)
    except ValueError:
        return 0.0


def load(seasons) -> list:
    rows = []
    for yr in seasons:
        with open(CACHE_DIR / f"player_stats_{yr}.csv", newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r.get("season_type") != "REG":
                    continue
                rows.append((yr, int(r["week"]), r["player_display_name"], r["position"], r))
    rows.sort(key=lambda x: (x[0], x[1]))
    return rows


def auc(pairs) -> tuple[float | None, int]:
    """[(score, outcome)] -> P(a hit is ranked above a miss)."""
    pos = [p for p, y in pairs if y]
    neg = sorted(p for p, y in pairs if not y)
    if not pos or not neg:
        return None, len(pairs)
    s = sum(bisect.bisect_left(neg, p) + 0.5 * (bisect.bisect_right(neg, p) - bisect.bisect_left(neg, p))
            for p in pos)
    return s / (len(pos) * len(neg)), len(pairs)


def boot(pairs, reps=BOOT, seed=1) -> float:
    rnd = random.Random(seed)
    got = []
    for _ in range(reps):
        a, _n = auc([rnd.choice(pairs) for _ in pairs])
        if a is not None:
            got.append(a)
    if len(got) < 2:
        return 0.0
    m = sum(got) / len(got)
    return (sum((g - m) ** 2 for g in got) / (len(got) - 1)) ** 0.5


def blend(vals, league) -> float:
    """engine/passtd.projection's shape: career and the last RECENT
    averaged, shrunk toward the league by PRIOR notional games."""
    career = sum(vals) / len(vals)
    window = vals[:RECENT]
    b = (career + sum(window) / len(window)) / 2
    return (b * len(vals) + league * PRIOR) / (len(vals) + PRIOR)


def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def league_anchors(rows, held_out) -> dict:
    acc = defaultdict(list)
    for yr, _wk, _name, pos, r in rows:
        if yr >= held_out:
            continue
        for mk, want, _kind in CANDIDATES:
            if pos == want and _f(r, ROLE_COL[pos]) >= ROLE_FLOOR[pos]:
                acc[mk].append(_f(r, COLS[mk]))
    return {mk: sum(v) / len(v) for mk, v in acc.items()}


def score(rows, held_out) -> dict:
    league = league_anchors(rows, held_out)
    hist: dict = defaultdict(list)
    def_int: dict = defaultdict(list)
    scored: dict = defaultdict(list)
    for yr, _wk, name, pos, r in rows:
        for mk, want, kind in CANDIDATES:
            if pos != want:
                continue
            y = _f(r, COLS[mk])
            h, rh = hist[(name, mk)], hist[(name, "role")]
            if yr == held_out and len(h) >= MIN_GAMES and len(rh) >= 3 and sum(rh[:3]) / 3 >= ROLE_FLOOR[pos]:
                proj = blend(h, league[mk])
                if kind == "count1":
                    scored[(mk, pos)].append((1 - math.exp(-proj), y >= 1))
                    if mk == "pass_int":
                        od = def_int.get(r.get("opponent_team") or "") or []
                        if len(od) >= 4:
                            adj = proj * (sum(od[:12]) / len(od[:12])) / league[mk]
                            scored[("pass_int+opp", pos)].append((1 - math.exp(-adj), y >= 1))
                else:
                    last = h[:LINE_GAMES]
                    line = max(0.5, round(sum(last) / len(last) * 2) / 2 - 0.5)
                    career = sum(h) / len(h)
                    sd = (sum((v - career) ** 2 for v in h) / max(1, len(h) - 1)) ** 0.5 or 1.0
                    if y != line:
                        scored[(mk, pos)].append((1 - _norm_cdf((line + 0.5 - proj) / sd), y > line))
            h.insert(0, y)
            if mk == "pass_int":
                def_int[r.get("opponent_team") or ""].insert(0, y)
        if pos in ROLE_COL:
            hist[(name, "role")].insert(0, _f(r, ROLE_COL[pos]))
    return {k: (auc(v)[0], boot(v), len(v), sum(1 for _p, y in v if y) / len(v)) for k, v in scored.items()}


def main(argv) -> int:
    seasons = [int(a) for a in argv] or [2021, 2022, 2023, 2024, 2025]
    rows = load(seasons)
    if not rows:
        print("No cached box scores to measure.")
        return 1
    held = seasons[-1]
    print(f"\nRanking AUC, walk-forward, held-out {held} (fitted on nothing — the "
          f"passing-touchdown blend against a trailing-average line)\n")
    for (mk, pos), (a, se, n, base) in sorted(score(rows, held).items()):
        word = "" if a is None else ("  clears 0.60" if a - se >= 0.60 else "  under the bar" if a + se < 0.60 else "  on the line")
        print(f"  {mk:<14}{pos:<4} AUC {a:.3f} ± {se:.3f}   n={n:<5} hit rate {base:.2f}{word}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
