#!/usr/bin/env python3
"""Can the college model sort the volume markets? — measured on the cached plays.

    python3 cfbmarketfit.py                  # the cached 2022-2025 play files
    python3 cfbmarketfit.py 2023 2024 2025   # other seasons (the last is held out)

Ethan, 2026-10-05: "for nfl and CFB For the most likely bets, we need to
implement picks for QB interceptions, QB Pass Attempts, QB Completions,
and any other market we are missing that we can be winning in". The NFL
board added attempts, completions and carries on 2026-09-27 after
marketfit.py measured them; college carried none of the three, and its
feed did not even count completions or interceptions. The feed does now
(engine/sources/cfbstats: pass_cmp, pass_int, rush_att), and this is the
same measurement, for college, on the same play files the box ingests:

  pass_att    a quarterback's pass attempts        player_pass_attempts
  pass_cmp    his completions                      player_pass_completions
  pass_int    his interceptions (1 or more)        player_pass_interceptions
  rush_att    a back's carries                     player_rush_attempts
  rush_yds    a QUARTERBACK's rushing yards        player_rush_yds

beside the four the college board already carries, in the same harness,
so a new figure is read next to known ones rather than against a bar
alone. The walk, the line, the blend and the role floors are
marketfit.py's (imported), held-out last season, cluster-bootstrapped.

ROLES come from the cached roster where it names a position, else from
the player's own usage (a man with fifteen attempts a game is the
quarterback whatever the roster says). College has no target column, so
a receiver's role is his catches.

Reads data/cache only (the play, schedule and roster files cfbstats
fetches); writes nothing. The shelf itself opens through
engine/rankfit's walk on the box's ingested logs — this is the reading
that says whether to expect it to.
"""
from __future__ import annotations

import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.sources.fetch import CACHE_DIR                     # noqa: E402
from engine.sources import cfbstats                            # noqa: E402
from marketfit import auc, boot, blend, _norm_cdf, MIN_GAMES, LINE_GAMES   # noqa: E402

#: (market, role, how it is scored) — as marketfit.CANDIDATES.
CANDIDATES = [("pass_att", "QB", "ou"), ("pass_cmp", "QB", "ou"), ("pass_int", "QB", "count1"),
              ("rush_att", "RB", "ou"), ("rush_yds", "QB", "ou"),
              ("pass_yds", "QB", "ou"), ("rush_yds", "RB", "ou"),
              ("receptions", "WR", "ou"), ("rec_yds", "WR", "ou")]
ROLE_COL = {"QB": "pass_att", "RB": "carries", "WR": "receptions"}
ROLE_FLOOR = {"QB": 15.0, "RB": 8.0, "WR": 3.0}
ROSTER_ROLE = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "WR"}


def games_of(season: int) -> dict:
    """The schedule as cfbstats wants it: game id → sides, week, points."""
    out = {}
    with open(CACHE_DIR / f"cfb_schedules_{season}.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if (r.get("season_type") or "regular") != "regular":
                continue
            hp, ap = cfbstats._num(r.get("home_points")), cfbstats._num(r.get("away_points"))
            out[r["game_id"]] = {"period": f"{int(float(r.get('week') or 0)):03d}",
                                 "home": r["home_team"], "away": r["away_team"],
                                 "home_name": r["home_team"], "away_name": r["away_team"],
                                 "points": hp + ap, "home_points": hp, "away_points": ap}
    return out


def load(seasons) -> list:
    """[(season, week, player, roster position, {market: value}, opponent)]."""
    rows = []
    for yr in seasons:
        games = games_of(yr)
        with open(CACHE_DIR / f"cfb_rosters_{yr}.csv", newline="", encoding="utf-8") as fh:
            roster = cfbstats.parse_rosters(csv.DictReader(fh))
        with open(CACHE_DIR / f"cfb_player_stats_{yr}.csv", newline="", encoding="utf-8",
                  errors="replace") as fh:
            out = cfbstats.parse_player_stats(csv.DictReader(fh), yr, games, roster)
        by: dict = {}
        for r in out["rows"]:
            k = (yr, int(r["period"] or 0), r["player"], r["team"])
            slot = by.setdefault(k, {"pos": (r.get("position") or "").upper(),
                                     "opp": r.get("opponent") or "", "stats": {}})
            slot["stats"][r["market"]] = float(r["value"])
        for (season, week, player, _team), slot in by.items():
            rows.append((season, week, player, slot["pos"], slot["stats"], slot["opp"]))
    rows.sort(key=lambda x: (x[0], x[1]))
    return rows


def role_of(pos: str, recent: dict) -> str | None:
    """The roster's word, else the usage's: the first role whose floor
    the last three games clear, quarterback first."""
    if ROSTER_ROLE.get(pos):
        return ROSTER_ROLE[pos]
    for role, col in ROLE_COL.items():
        vals = recent.get(col) or []
        if len(vals) >= 3 and sum(vals[:3]) / 3 >= ROLE_FLOOR[role]:
            return role
    return None


def league_anchors(rows, held_out) -> dict:
    acc = defaultdict(list)
    recent: dict = defaultdict(lambda: defaultdict(list))
    for yr, _wk, name, pos, stats, _opp in rows:
        role = role_of(pos, recent[name])
        if yr < held_out and role:
            for mk, want, _kind in CANDIDATES:
                if role == want and (recent[name].get(ROLE_COL[role]) or [0])[0] >= ROLE_FLOOR[role]:
                    acc[mk].append(stats.get(mk, 0.0))
        for col in ROLE_COL.values():
            recent[name][col].insert(0, stats.get(col, 0.0))
    return {mk: sum(v) / len(v) for mk, v in acc.items() if v}


def score(rows, held_out) -> dict:
    league = league_anchors(rows, held_out)
    hist: dict = defaultdict(list)
    recent: dict = defaultdict(lambda: defaultdict(list))
    def_int: dict = defaultdict(list)
    scored: dict = defaultdict(list)
    for yr, _wk, name, pos, stats, opp in rows:
        role = role_of(pos, recent[name])
        for mk, want, kind in CANDIDATES:
            if role != want or mk not in league:
                continue
            y = stats.get(mk, 0.0)
            h = hist[(name, mk)]
            rh = recent[name].get(ROLE_COL[role]) or []
            if yr == held_out and len(h) >= MIN_GAMES and len(rh) >= 3 and sum(rh[:3]) / 3 >= ROLE_FLOOR[role]:
                proj = blend(h, league[mk])
                if kind == "count1":
                    scored[(mk, role)].append((1 - math.exp(-proj), y >= 1))
                    od = def_int.get(opp) or []
                    opp_f = (sum(od[:12]) / len(od[:12])) / league[mk] if len(od) >= 4 and league[mk] > 0 else None
                    if opp_f is not None:
                        scored[(mk + "+opp", role)].append((1 - math.exp(-proj * opp_f), y >= 1))
                    # THE RATE ARM: his interceptions PER ATTEMPT (shrunk to
                    # the league's) times the attempts he is projected to
                    # throw — a quarterback who throws forty is at risk
                    # forty times, whatever his count last month said.
                    ratio = int_rate(hist[(name, "pass_att")], h, league)
                    att = hist[(name, "pass_att")]
                    if ratio is not None and len(att) >= MIN_GAMES and "pass_att" in league:
                        lam = ratio * blend(att, league["pass_att"])
                        scored[(mk + "/att×att", role)].append((1 - math.exp(-lam), y >= 1))
                        if opp_f is not None:
                            scored[(mk + "/att×att+opp", role)].append((1 - math.exp(-lam * opp_f), y >= 1))
                else:
                    last = h[:LINE_GAMES]
                    line = max(0.5, round(sum(last) / len(last) * 2) / 2 - 0.5)
                    career = sum(h) / len(h)
                    sd = (sum((v - career) ** 2 for v in h) / max(1, len(h) - 1)) ** 0.5 or 1.0
                    if y != line:
                        scored[(mk, role)].append((1 - _norm_cdf((line + 0.5 - proj) / sd), y > line))
            h.insert(0, y)
            if mk == "pass_int":
                def_int[opp].insert(0, y)
        for col in ROLE_COL.values():
            recent[name][col].insert(0, stats.get(col, 0.0))
    return {k: (auc(v)[0], boot(v), len(v), sum(1 for _p, y in v if y) / len(v)) for k, v in scored.items()}


def int_rate(att_hist: list, int_hist: list, league: dict, prior_att: float = 120.0):
    """Interceptions per attempt, career and the last eight averaged,
    shrunk toward the league's rate by ``prior_att`` notional attempts.
    The two histories are the same games, most recent first."""
    n = min(len(att_hist), len(int_hist))
    if n < MIN_GAMES or not league.get("pass_att") or not league.get("pass_int"):
        return None
    lg = league["pass_int"] / league["pass_att"]
    a_all, i_all = sum(att_hist[:n]), sum(int_hist[:n])
    k = min(n, 8)
    a_rec, i_rec = sum(att_hist[:k]), sum(int_hist[:k])
    career = (i_all + lg * prior_att) / (a_all + prior_att)
    recent = (i_rec + lg * prior_att) / (a_rec + prior_att)
    return (career + recent) / 2


def report(results: dict, held: int) -> list[str]:
    out = [f"College ranking AUC, walk-forward, held-out {held} (marketfit.py's harness on the "
           f"cfbstats play feed)", ""]
    for (mk, pos), (a, se, n, base) in sorted(results.items()):
        if a is None:
            out.append(f"  {mk:<14}{pos:<4} unscoreable (n={n})")
            continue
        word = ("  clears 0.60" if a - se >= 0.60 else "  under the bar" if a + se < 0.60 else "  on the line")
        out.append(f"  {mk:<14}{pos:<4} AUC {a:.3f} ± {se:.3f}   n={n:<5} hit rate {base:.2f}{word}")
    return out


def main(argv) -> int:
    seasons = [int(a) for a in argv] or [2022, 2023, 2024, 2025]
    try:
        rows = load(seasons)
    except FileNotFoundError as exc:
        print(f"No cached college files to measure: {exc}")
        return 1
    if not rows:
        print("No college player-games parsed.")
        return 1
    held = seasons[-1]
    print()
    for line in report(score(rows, held), held):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
