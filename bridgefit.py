#!/usr/bin/env python3
"""Should the usage bridge lean on his last season too? — measured.

    python3 bridgefit.py                           # 2022-2025, then 2017-2021 unseen
    python3 bridgefit.py --seasons 2022-2025 --unseen 2017-2021

The board's base from week 4 is w·form + (1−w)·role, w = n/(n+4)
(engine/projection.USAGE_PRIOR_GAMES), where the form is pulled toward his
own last season (engine/carry.SEASON_PRIOR_GAMES, seasonpriorfit.py) and the
role — recent opportunities × this season's efficiency, engine/nflusage —
is not. At four games the role is half the base, so the measured pull
reached the board about half as hard as it was measured.

The candidate adds no number: the role pulled toward the same last-season
number by the same n/(n+k), under the same condition (the form was shrunk:
last season holds more games than this one). Both sides × the defence step,
as the board does. THE BAR, set before the run: every season of --seasons
improves, and at most one of --unseen is worse. The markets that pass are
engine/carry.BRIDGE_SEASON_MARKETS. Reads data/cache; writes nothing.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import carry as C                                    # noqa: E402
from engine import defensevs as D                                # noqa: E402
from engine.form import compute_form                             # noqa: E402
from engine.models import GameLog                                # noqa: E402
from engine.nflusage import MIN_EFF_OPPS, VOL_WEEKS              # noqa: E402
from engine.projection import USAGE_PRIOR_GAMES                  # noqa: E402
from engine.sources.nflverse import quarterbacked, stat_value    # noqa: E402
from qbscriptfit import load                                     # noqa: E402

#: market -> (opportunity column in the box scores, its usage-map name, positions)
OPP = {"receptions": ("targets", "targets", ("WR", "TE", "RB")),
       "rec_yds": ("targets", "targets", ("WR", "TE", "RB")),
       "rush_yds": ("carries", "carries", ("RB",)),
       "pass_yds": ("attempts", "pass_att", ("QB",))}


def _num(row: dict, col: str) -> float:
    try:
        return float(row.get(col) or 0)
    except (TypeError, ValueError):
        return 0.0


def role(opps: list[float], vals: list[float], opp_key: str) -> float | None:
    """The bridge's role as engine/nflusage.volume_roles builds it: the last
    VOL_WEEKS games' opportunities a game × this season's efficiency, or
    None under two games or MIN_EFF_OPPS opportunities."""
    tot = sum(opps)
    if len(opps) < 2 or tot < MIN_EFF_OPPS[opp_key]:
        return None
    recent = opps[-VOL_WEEKS:]
    return (sum(recent) / len(recent)) * (sum(vals) / tot)


def blend(form_mean: float, n: int, est: float, prior: float | None, k: float) -> tuple[float, float]:
    """(as the board blended it, with the role pulled toward ``prior``)."""
    w = n / (n + USAGE_PRIOR_GAMES)
    now = w * form_mean + (1 - w) * est
    if prior is None:
        return now, now
    s = n / (n + k)
    return now, w * form_mean + (1 - w) * (s * est + (1 - s) * prior)


def points(now: list[dict], before: list[dict], season: int) -> list[dict]:
    prior_ratings = D.ratings(before, 99)
    rated = {w: D.ratings(now, w, prior=prior_ratings, week_one_prior=True) for w in range(4, 23)}
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
        for m, (col, opp_key, poss) in OPP.items():
            if pos not in poss:
                continue
            last = [stat_value(r, m) for r in prev.get(name, ()) if quarterbacked(r, m)]
            games = [r for r in rows if quarterbacked(r, m)]
            k = C.SEASON_PRIOR_GAMES.get(m)
            for i, r in enumerate(games):
                if int(float(r["week"])) < 4 or i < 3:
                    continue
                hist = games[:i]
                vals = [stat_value(x, m) for x in hist]
                logs = [GameLog(week=int(float(x["week"])), opponent="", value=v)
                        for x, v in zip(hist, vals)][::-1]
                career = sum(vals) / len(vals)
                if compute_form(logs, career, None).mean < C.SEASON_PRIOR_FLOOR[m]:
                    continue
                anchored = bool(k) and len(last) >= C.MIN_PRIOR_GAMES
                form = (compute_form(logs, career, None, prior=sum(last) / len(last), prior_n=len(last),
                                     prior_games=k) if anchored else compute_form(logs, career, None))
                est = role([_num(x, col) for x in hist], vals, opp_key)
                if est is None or est <= 0:
                    continue
                cur, cand = blend(form.mean, form.sample_games, est,
                                  form.shrunk_to if anchored else None, float(k or 0))
                opp = r.get("opponent_team") or ""
                f = D.effect(opp, (rated.get(int(float(r["week"]))) or {}).get(opp) or {}, pos, m)[0]
                out.append({"m": m, "s": season, "cur": cur * f, "cand": cand * f, "y": stat_value(r, m)})
    return out


def cuts(by_season: dict, market: str) -> list[tuple]:
    """[(season, n, % squared error cut by the candidate)]."""
    out = []
    for s in sorted(by_season):
        t = [p for p in by_season[s] if p["m"] == market]
        cur = sum((p["y"] - p["cur"]) ** 2 for p in t)
        cand = sum((p["y"] - p["cand"]) ** 2 for p in t)
        out.append((s, len(t), (1 - cand / cur) * 100 if cur else 0.0))
    return out


def ships(held: list[tuple], unseen: list[tuple]) -> bool:
    return bool(held) and all(c > 0 for *_x, c in held) and sum(1 for *_x, c in unseen if c < 0) <= 1


def _seasons(text: str) -> range:
    lo, _, hi = text.partition("-")
    return range(int(lo), int(hi or lo) + 1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="2022-2025", help="every season here must improve")
    ap.add_argument("--unseen", default="2017-2021", help="at most one season here may be worse")
    a = ap.parse_args(argv)
    by = {s: points(load(s), load(s - 1), s) for s in _seasons(a.seasons)}
    old = {s: points(load(s), load(s - 1), s) for s in _seasons(a.unseen)}
    print("Squared error cut by pulling the usage bridge toward last season:")
    passed = []
    for m in OPP:
        held, unseen = cuts(by, m), cuts(old, m)
        ok = ships(held, unseen)
        passed += [m] if ok else []
        print(f"  {m:<10} " + "  ".join(f"{s}: {c:+.2f}%" for s, _n, c in held) + "  | "
              + "  ".join(f"{s}: {c:+.2f}%" for s, _n, c in unseen) + f"   {'SHIPS' if ok else 'fails'}")
    print(f"\n  BRIDGE_SEASON_MARKETS = {sorted(passed)}")
    print(f"  shipped:                {sorted(C.BRIDGE_SEASON_MARKETS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
