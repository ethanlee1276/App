#!/usr/bin/env python3
"""Does college's projection gain from the NFL's usage bridge? — measured.

    python3 cfbbridgefit.py                  # the cached 2022-2025 play files
    python3 cfbbridgefit.py 2023 2024 2025   # other seasons

Ethan, 2026-10-14: "do all of the ideas", the first a usage step for
college. The NFL's base is w·form + (1−w)·role, w = n/(n+4)
(engine/projection.USAGE_PRIOR_GAMES), the role being his last four games'
opportunities × this season's efficiency (engine/nflusage). College's base
is the form alone. This replays college's base the way the board builds
it — his last twenty games under the school, this season's then last
season's, newest first (engine/cfb/props._log_rows, LOG_LIMIT), at least
MIN_LOGS of them over the market's volume floor, the adopted form curve —
and the same base blended with the role (``role`` below) built from this
season's games before the night. Nothing is fitted: the weight, the
window and the floors are the NFL's (catches at eight, set beforehand).

COLLEGE'S OPPORTUNITIES ARE NOT THE NFL'S. The play file names no target
count it can stand behind (engine/sources/cfbstats, "THERE ARE NO TARGETS
HERE"), so a receiver's volume is his catches and his efficiency yards a
catch. Carries and pass attempts are counted exactly; receptions have no
opportunity under them here and are not measured.

THE BAR, set before the first run: a market ships only if its squared
error falls in EVERY season measured. (The NFL's bar let one unseen season
slip; college has four seasons cached and no unseen ones, so all four
must hold.)

THE RUN, 2026-10-14, the cached 2022-2025 files (default form curves —
this checkout has no fitted store; a box run uses the box's):

    market     2022     2023     2024     2025     pooled     n
    rush_yds  -0.01%   -0.25%   +0.04%   -0.60%   -0.21%   20,946
    pass_yds  -1.23%   +0.42%   +0.77%   -0.16%   -0.02%    6,737
    pass_cmp  -1.65%   +0.37%   +1.73%   +0.16%   +0.21%    6,438
    rec_yds   -0.22%   -0.18%   -0.54%   -0.97%   -0.49%   29,516

NOTHING SHIPS, and the reason is plausible rather than mysterious: the
college board's form already reads twenty games across two seasons, so
its n is large and the role gets a sixth of the weight, and what it adds
there is noise — receiving yards worse in all four seasons. The board
stays as it is; nothing in engine/ reads this file.

The matchup step multiplies both bases alike and is left out: college
rates defences from the box's stored seasons, not the play files.
Reads data/cache only (the files cfbstats parses); writes nothing.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.cfb import props as P                              # noqa: E402
from engine.form import compute_form                           # noqa: E402
from engine.formfit import weights_for                         # noqa: E402
from engine.models import GameLog                              # noqa: E402
from engine.nflusage import VOL_WEEKS                          # noqa: E402
from engine.projection import USAGE_PRIOR_GAMES                # noqa: E402
from engine.sources import cfbstats                            # noqa: E402
from engine.sources.fetch import CACHE_DIR                     # noqa: E402
from engine.sources.oddsapi import normalize_name              # noqa: E402


#: Each market's opportunity column in college's logs (catches for yards
#: a catch: no target count).
OPP_BY_MARKET = {"rush_yds": "carries", "pass_yds": "pass_att",
                 "pass_cmp": "pass_att", "rec_yds": "receptions"}

#: A season's opportunities before an efficiency is a rate: the NFL's
#: floors for carries and attempts (engine/nflusage.MIN_EFF_OPPS); catches
#: at eight, two-thirds of its twelve targets.
MIN_EFF_OPPS = {"carries": 20, "pass_att": 60, "receptions": 8}


def role(games: list[dict], market: str) -> dict | None:
    """The role from this season's games before the night, oldest first,
    each ``{column: value}``: the last VOL_WEEKS games' opportunities a
    game × the season's efficiency, or None under two games with the
    opportunity or MIN_EFF_OPPS of them — the rule
    engine/nflusage.volume_roles applies to the NFL's weeks."""
    opp = OPP_BY_MARKET.get(market)
    if not opp:
        return None
    with_opp = [g for g in games if opp in g]
    if len(with_opp) < 2:
        return None
    recent = with_opp[-VOL_WEEKS:]
    paired = [g for g in with_opp if market in g]
    tot = sum(float(g[opp]) for g in paired)
    if tot < MIN_EFF_OPPS[opp]:
        return None
    return {"opp_per_game": sum(float(g[opp]) for g in recent) / len(recent),
            "eff": sum(float(g[market]) for g in paired) / tot}


def games_of(season: int) -> dict:
    """The regular season's games, keyed by id, dated the way the box
    files them (engine/sources/cfbfastr: ``period`` is the date)."""
    out = {}
    with open(CACHE_DIR / f"cfb_schedules_{season}.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if (r.get("season_type") or "regular") != "regular":
                continue
            out[r["game_id"]] = {"period": (r.get("start_date") or "")[:10],
                                 "home": r["home_team"], "away": r["away_team"],
                                 "home_name": r["home_team"], "away_name": r["away_team"]}
    return out


def load(season: int) -> dict:
    """``{(normalised name, team): {date: {market: value}}}`` for one season,
    or {} when its files are not cached."""
    need = [CACHE_DIR / f"cfb_{k}_{season}.csv" for k in ("schedules", "rosters", "player_stats")]
    if not all(p.exists() for p in need):
        return {}
    with open(need[1], newline="", encoding="utf-8") as fh:
        roster = cfbstats.parse_rosters(csv.DictReader(fh))
    with open(need[2], newline="", encoding="utf-8", errors="replace") as fh:
        rows = cfbstats.parse_player_stats(csv.DictReader(fh), season, games_of(season), roster)["rows"]
    out: dict = defaultdict(dict)
    for r in rows:
        out[(normalize_name(r["player"]), r["team"])].setdefault(r["period"], {})[r["market"]] = float(r["value"])
    return dict(out)


def points(now: dict, before: dict, season: int) -> list[dict]:
    """One row per player-game the board would price and the role covers:
    ``{"m", "s", "cur", "cand", "y"}``."""
    out = []
    for key, by_day in now.items():
        days = sorted(by_day)
        last = [by_day_prev for _d, by_day_prev in sorted((before.get(key) or {}).items(), reverse=True)]
        for market in OPP_BY_MARKET:
            weights = weights_for("cfb", market)
            for i, day in enumerate(days):
                y = by_day[day].get(market)
                if y is None:
                    continue
                earlier = [by_day[d] for d in days[:i]]
                vals = ([g[market] for g in reversed(earlier) if market in g]
                        + [g[market] for g in last if market in g])[:P.LOG_LIMIT]
                if len(vals) < P.MIN_LOGS or sum(vals) / len(vals) < P._MIN_MEAN[market]:
                    continue
                got = role(earlier, market)
                if not got:
                    continue
                logs = [GameLog(week=len(vals) - j, opponent="", value=v) for j, v in enumerate(vals)]
                form = compute_form(logs, sum(vals) / len(vals), None, weights=weights)
                est = got["opp_per_game"] * got["eff"]
                if est <= 0:
                    continue
                w = form.sample_games / (form.sample_games + USAGE_PRIOR_GAMES)
                out.append({"m": market, "s": season, "n": form.sample_games, "y": y,
                            "cur": form.mean, "cand": w * form.mean + (1 - w) * est})
    return out


def cuts(pts: list[dict], market: str) -> list[tuple]:
    """[(season, n, % squared error cut by the bridge)], then the pooled row."""
    out = []
    for s in sorted({p["s"] for p in pts}) + ["all"]:
        t = [p for p in pts if p["m"] == market and (s == "all" or p["s"] == s)]
        cur = sum((p["y"] - p["cur"]) ** 2 for p in t)
        cand = sum((p["y"] - p["cand"]) ** 2 for p in t)
        out.append((s, len(t), (1 - cand / cur) * 100 if cur else 0.0))
    return out


def ships(rows: list[tuple]) -> bool:
    """THE BAR: every season's squared error falls (the pooled row aside)."""
    seasons = [r for r in rows if r[0] != "all"]
    return bool(seasons) and all(n > 0 and c > 0 for _s, n, c in seasons)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    years = [int(a) for a in argv] or [2022, 2023, 2024, 2025]
    pts: list = []
    for s in years:
        now = load(s)
        if not now:
            print(f"  {s}: no cached files, skipped")
            continue
        pts += points(now, load(s - 1), s)
    print("Squared error cut by college's usage bridge (w·form + (1−w)·role, w = n/(n+4)):")
    passed = []
    for m in OPP_BY_MARKET:
        rows = cuts(pts, m)
        ok = ships(rows)
        passed += [m] if ok else []
        print(f"  {m:<9} " + "  ".join(f"{s}: {c:+.2f}% (n {n})" for s, n, c in rows)
              + f"   {'SHIPS' if ok else 'fails'}")
    print(f"\n  passes the bar: {sorted(passed) or 'none'}   (2026-10-14: none; the board reads no role)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
