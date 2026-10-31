#!/usr/bin/env python3
"""EXP-004 — does EXP-001's opportunities-first model hold in college football?

    python3 research/exp4_college_two_stage.py              (fit, then validation only)
    python3 research/exp4_college_two_stage.py --holdout    (adds the holdout; run ONCE, result recorded)

Backlog B11 of the research lab (docs/RESEARCH_LAB.md). The spec, Part 2:
"Do not assume that an NFL discovery transfers successfully to another sport
without independent validation." This is that validation for EXP-001, on
college games neither model has seen, with the same two models, the same
score and the same kind of bar. Registry entry EXP-004.

THE MODELS are EXP-001's, imported unchanged (research/exp1_two_stage.Fit):
A, the direct model (the form blend's mean, the training pool's shape), and
B, the two-stage model (opportunities ~ NegBin around his age-weighted
opportunities, production given them). The age weights are the NFL's
(engine/nflusage.ROLE_HALF_LIFE), NOT refitted on college: B gets nothing
fitted on college but its NegBin size, shrink and spread, from the training
games only. H is A's mean with B's shape (EXP-001b's idea).

THE DATA. cfbfastR play-by-play (data/cache/cfb_player_stats_<season>.csv),
folded into player-games by the site's own parser
(engine/sources/cfbstats.parse_player_stats, which settles the feed's
swapped passer and receiver columns). Its target count, which the parser
keeps internally and never writes, is read here by asking it for one more
column. Roles: the season's roster (WR/TE receivers, RB/FB backs, QBs left
out); a player the roster does not name takes his role from his own games
before this one (any pass thrown: left out; more carries than targets: a
back; otherwise a receiver). 2026 has no roster file, so 2026 reads 2025's.

WHAT THE FEED CAN AND CANNOT TEST (measured 2026-10-17, before any model
was fitted). Every rushing play names its runner, so carries are whole in
every season. Incompletions are not: the share naming the target is 45%
(2022), 38% (2023), 21% (2024), 78-84% by week (2025) and 92% (2026). A
target count whose meaning moves between the training and test seasons
would test the feed, not the model, so the receiving markets run only on
2025 and 2026, where the share is steady within each season:

  EXP-004a  rush_yds (backs)     fit 2022-2023, validate 2024, hold out 2025 + 2026 to date
  EXP-004b  receptions, rec_yds  fit 2025 weeks 1-8, validate 2025 weeks 9+, hold out 2026 to date

EXP-004b's caveat, written now: 2026 names about ten points more of its
incompletions than 2025, so counted targets run a few percent higher in the
holdout than in training. B's opportunity mean and catch rate come from the
player's own 2026 games, so only its fitted prior and NegBin size carry
2025's level; it is a real but small tilt, and it is stated, not corrected.

THE SCORE is EXP-001's CRPS on the same grids (receptions 0..15, yards -10..250
by 5), and the same player-season-clustered bootstrap.

THE BAR, WRITTEN BEFORE ANY RUN (2026-10-17). Two families, each held to
0.05 by Bonferroni within it:

  EXP-004a (two tests, 97.5% intervals): B against A on rush_yds, and H
    against A on rush_yds. Each ADVANCES only if its validation mean CRPS
    is below A's AND on the holdout it is below A's with the clustered
    upper bound under zero. Right direction with the bound over zero is
    INCONCLUSIVE; wrong direction is REJECTED.
  EXP-004b (two tests, 97.5% intervals): B against A on receptions and on
    rec_yds, by the same rule.

Anything else printed (H in the receiving markets, the proxy Brier, MAE,
calibration) is description and decides nothing. Nothing is tuned after
the holdout is read; an amendment before it is logged here with its reason.

THE RESULT (2026-10-17, holdout read once, after the freeze commit 0ad7173c):

  family    test             holdout              CRPS A    test     diff [97.5% clustered]     decision
  EXP-004a  B v A rush_yds   2025 + 2026 to date  19.8970  19.7447  -0.1523 [-0.3386, +0.0205]  INCONCLUSIVE
  EXP-004a  H v A rush_yds   2025 + 2026 to date  19.8970  19.7066  -0.1905 [-0.2455, -0.1366]  ADVANCE
  EXP-004b  B v A receptions 2026 to date          1.2397   1.2126  -0.0271 [-0.0525, -0.0019]  ADVANCE
  EXP-004b  B v A rec_yds    2026 to date         19.7514  19.5397  -0.2116 [-0.6368, +0.1891]  INCONCLUSIVE

What it says beside the NFL's. Receptions: the two-stage gain is the same
size in both sports (-0.0271 here, -0.0270 in the NFL), and in both B is
worse at a line-like threshold (proxy Brier 0.2296 v 0.2257 here) and in
its mean (MAE 1.77 v 1.71): the gain is the distribution's shape, not its
centre. Rushing yards: the hybrid H — the direct model's centre with the
two-stage shape — wins in college as a preregistered test; in the NFL it
was seen after looking and waits on EXP-001b's games. Neither moves a
pick: both go to a test at the college lines the box holds (EXP-004c).

Reads data/cache only; writes nothing.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import carry as C                                    # noqa: E402
from engine.form import compute_form                             # noqa: E402
from engine.models import GameLog                                # noqa: E402
from engine.nflusage import MIN_EFF_OPPS, ROLE_HALF_LIFE, ewma_opps   # noqa: E402
from engine.sources import cfbstats                              # noqa: E402
from research import exp1_two_stage as E1                        # noqa: E402

CACHE = ROOT / "data" / "cache"
FREEZE = "2026-10-17"
#: family -> (markets, train, validate, hold); a period is ((season, first week, last week), ...)
FAMILIES = {
    "EXP-004a": (("rush_yds",),
                 ((2022, 0, 99), (2023, 0, 99)), ((2024, 0, 99),), ((2025, 0, 99), (2026, 0, 99))),
    "EXP-004b": (("receptions", "rec_yds"),
                 ((2025, 0, 8),), ((2025, 9, 99),), ((2026, 0, 99),)),
}
#: The tests that decide, per family; each family is held to 0.05.
TESTS = {"EXP-004a": (("rush_yds", "b"), ("rush_yds", "ba")),
         "EXP-004b": (("receptions", "b"), ("rec_yds", "b"))}
ALPHA_FAMILY = 0.05
#: market -> (opportunity, its nflusage key, production, roles)
MARKETS = {"receptions": ("targets", "targets", "receptions", ("REC", "RB")),
           "rec_yds": ("targets", "targets", "rec_yds", ("REC", "RB")),
           "rush_yds": ("carries", "carries", "rush_yds", ("RB",))}
ROSTER_ROLE = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "REC", "TE": "REC"}
_STATS = ("targets", "receptions", "rec_yds", "carries", "rush_yds", "pass_att")


def games_of(season: int) -> dict:
    """The regular season's games, as the parser wants them."""
    out = {}
    path = CACHE / f"cfb_schedules_{season}.csv"
    if not path.exists():
        return out
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if (r.get("season_type") or "regular") != "regular":
                continue
            out[r["game_id"]] = {"period": f"{int(float(r.get('week') or 0)):03d}",
                                 "home": r["home_team"], "away": r["away_team"],
                                 "home_name": r["home_team"], "away_name": r["away_team"]}
    return out


def _games_from_plays(season: int) -> dict:
    """A season with no schedule file (2026): its games off the play file."""
    out = {}
    with open(CACHE / f"cfb_player_stats_{season}.csv", newline="", encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            gid = r.get("game_id")
            if not gid or gid in out:
                continue
            team, opp = r.get("team") or "", r.get("opponent") or ""
            out[gid] = {"period": f"{int(float(r.get('week') or 0)):03d}",
                        "home": team, "away": opp, "home_name": team, "away_name": opp}
    return out


def roster_of(season: int) -> dict:
    for yr in (season, season - 1):
        path = CACHE / f"cfb_rosters_{yr}.csv"
        if path.exists():
            with open(path, newline="", encoding="utf-8") as fh:
                return cfbstats.parse_rosters(csv.DictReader(fh))
    return {}


def player_games(season: int) -> dict:
    """{(player, team): [{"week", "gid", "pos", "stats"}...]} sorted by week."""
    games = games_of(season) or _games_from_plays(season)
    keep = cfbstats.MARKETS
    cfbstats.MARKETS = keep + ("targets",)            # the count it keeps and never writes
    try:
        with open(CACHE / f"cfb_player_stats_{season}.csv", newline="", encoding="utf-8",
                  errors="replace") as fh:
            out = cfbstats.parse_player_stats(csv.DictReader(fh), season, games, roster_of(season))
    finally:
        cfbstats.MARKETS = keep
    by: dict = {}
    for r in out["rows"]:
        if r["market"] not in _STATS:
            continue
        k = (r["player"], r["team"], r["game_id"])
        slot = by.setdefault(k, {"week": int(r["period"] or 0), "gid": r["game_id"],
                                 "pos": (r.get("position") or "").upper(), "stats": {}})
        slot["stats"][r["market"]] = float(r["value"])
    mine: dict = defaultdict(list)
    for (player, team, _gid), g in by.items():
        mine[(player, team)].append(g)
    for gs in mine.values():
        gs.sort(key=lambda g: g["week"])
    return mine


def role(pos: str, hist: list) -> str | None:
    if pos in ROSTER_ROLE:
        return ROSTER_ROLE[pos]
    if not hist or sum(g["stats"].get("pass_att", 0.0) for g in hist) > 0:
        return None
    car = sum(g["stats"].get("carries", 0.0) for g in hist)
    tgt = sum(g["stats"].get("targets", 0.0) for g in hist)
    return "RB" if car > tgt else "REC"


_CACHE: dict = {}


def _season(season: int) -> dict:
    if season not in _CACHE:
        _CACHE[season] = player_games(season) if (CACHE / f"cfb_player_stats_{season}.csv").exists() else {}
    return _CACHE[season]


def rows_for(season: int, markets, weeks=(0, 99)) -> list[dict]:
    """EXP-001's rows (research/exp1_two_stage.rows_for), from college games."""
    now, before = _season(season), _season(season - 1)
    prev: dict = defaultdict(list)
    for (name, _team), gs in before.items():
        prev[name].extend(gs)
    out = []
    for (name, team), gs in now.items():
        for m in markets:
            ocol, okey, pcol, roles = MARKETS[m]
            last = [g["stats"].get(pcol, 0.0) for g in prev.get(name, ())]
            k = C.SEASON_PRIOR_GAMES.get(m)
            for i, g in enumerate(gs):
                if g["week"] < 4 or i < 3 or not (weeks[0] <= g["week"] <= weeks[1]):
                    continue
                hist = gs[:i]
                rl = role(g["pos"], hist)
                if rl not in roles:
                    continue
                vals = [x["stats"].get(pcol, 0.0) for x in hist]
                opps = [x["stats"].get(ocol, 0.0) for x in hist]
                if sum(opps) < MIN_EFF_OPPS[okey]:
                    continue
                logs = [GameLog(week=x["week"], opponent="", value=v) for x, v in zip(hist, vals)][::-1]
                career = sum(vals) / len(vals)
                if compute_form(logs, career, None).mean < C.SEASON_PRIOR_FLOOR[m]:
                    continue
                anchored = bool(k) and len(last) >= C.MIN_PRIOR_GAMES
                form = (compute_form(logs, career, None, prior=sum(last) / len(last), prior_n=len(last),
                                     prior_games=k) if anchored else compute_form(logs, career, None))
                if form.mean <= 0:
                    continue
                row = {"m": m, "s": season, "pos": "RB" if rl == "RB" else "REC",
                       "who": f"{name}|{team}|{season}", "name": name, "team": team, "gid": g["gid"],
                       "week": g["week"], "y": g["stats"].get(pcol, 0.0), "o": g["stats"].get(ocol, 0.0),
                       "mu_a": form.mean, "mu_o": ewma_opps(opps, ROLE_HALF_LIFE.get(okey)),
                       "opps": sum(opps), "prod": sum(vals)}
                if m == "rec_yds":
                    row["catches"] = sum(x["stats"].get("receptions", 0.0) for x in hist)
                out.append(row)
    return out


def period_rows(period, markets) -> list[dict]:
    return [x for (s, lo, hi) in period for x in rows_for(s, markets, (lo, hi))]


def bounded(scored, key, alpha):
    keep = E1.ALPHA
    E1.ALPHA = alpha
    try:
        return E1.boot_diff(scored, key_b=key)
    finally:
        E1.ALPHA = keep


def label(period) -> str:
    return " + ".join(f"{s}" + ("" if (lo, hi) == (0, 99) else f" wk {lo}-{hi}" if hi < 99 else f" wk {lo}+")
                      for s, lo, hi in period)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--holdout", action="store_true", help="also score the holdout (run once)")
    a = ap.parse_args(argv)
    verdicts = []
    for fam, (markets, train, valid, hold) in FAMILIES.items():
        alpha = ALPHA_FAMILY / len(TESTS[fam])
        fit_rows = period_rows(train, markets)
        fit = E1.Fit(fit_rows)
        print(f"\n{fam} — {', '.join(markets)}: fitted on {label(train)}, {len(fit_rows):,} rows")
        for key in sorted(fit.r):
            print(f"  fit {key[0]:<10} {key[1]:<3} NB size {fit.r[key]:g}  shrink k {fit.k[key]:g}"
                  + (f"  spread² {fit.s2[key]:.1f}" if key in fit.s2 else ""))
        periods = [("validation", valid)] + ([("holdout", hold)] if a.holdout else [])
        res: dict = {}
        for name, period in periods:
            scored = E1.score(period_rows(period, markets), fit)
            res[name] = scored
            print(f"  {name} {label(period)}")
            for m in markets:
                t = [p for p in scored if p["m"] == m]
                if not t:
                    print(f"    {m:<10} no rows")
                    continue
                sm = E1.summarise(scored, m)
                db = bounded(t, "b", alpha)
                dh = bounded(t, "ba", alpha)
                print(f"    {m:<10} n={sm['n']:,} ({sm['players']:,} player-seasons)  CRPS A {sm['crps_a']:.4f}  "
                      f"B {sm['crps_b']:.4f}  H {sm['crps_ba']:.4f}  | B-A {db[0]:+.4f} [{db[1]:+.4f}, {db[2]:+.4f}]"
                      f"  H-A {dh[0]:+.4f} [{dh[1]:+.4f}, {dh[2]:+.4f}]  | Brier@proxy A {sm['brier_a']:.4f} "
                      f"B {sm['brier_b']:.4f}  | MAE A {sm['mae_a']:.2f} B {sm['mae_b']:.2f}")
        print(f"  decision ({1 - alpha:.1%} intervals, bar written before the run):")
        for m, key in TESTS[fam]:
            v = [p for p in res["validation"] if p["m"] == m]
            vd = (sum(p[key] for p in v) - sum(p["a"] for p in v)) / len(v) if v else 0.0
            h = [p for p in res.get("holdout", []) if p["m"] == m]
            hold_b = bounded(h, key, alpha) if h else None
            d = E1.decide(vd, hold_b) if v else "no validation rows"
            who = "B" if key == "b" else "H"
            verdicts.append((fam, m, who, d))
            print(f"    {who} vs A  {m:<10} {d}")
    print("\nSummary: " + "; ".join(f"{f} {w} {m}: {d}" for f, m, w, d in verdicts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
