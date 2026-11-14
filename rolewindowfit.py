#!/usr/bin/env python3
"""Should the usage bridge weight a player's recent games by age, not four flat? — measured.

    python3 rolewindowfit.py                       # pick on 2017-2021, judge on 2022-2025
    python3 rolewindowfit.py --train 2017-2021 --test 2022-2025

Ethan, 2026-10-17: "new equations ... make the NFL elite". The loss autopsy
(engine/autopsy) names volume the step most often wrong, and volumecheck.py
found the team's volume is mostly unknowable before kickoff, so what is
left to improve is the player's own volume. The bridge reads it as the flat
mean of his last VOL_WEEKS games (engine/nflusage.volume_roles): the fourth
game back counts as much as last week's and the fifth counts nothing.

THE CANDIDATE: every game he has played for his team this season, the one
`a` games back weighted 0.5 ** (a / H). A short half-life believes a new
role fast; a long one keeps more games and less noise. One H per
opportunity (targets, carries, attempts), chosen from HALF_LIVES on the
--train seasons only. The comparison is the board's own base, rebuilt as
bridgefit.py rebuilds it: the form blend, the bridge, the last-season pull
where engine/carry.BRIDGE_SEASON_MARKETS applies it, times the defence step.
Only the bridge's opportunities differ.

THE BAR, set before the run: on --test, every season's squared error
improves, for every market that opportunity feeds. An opportunity whose
markets all pass is written into engine/nflusage.ROLE_HALF_LIFE.

THE ANSWER, 2026-10-17: targets (H=8) and carries (H=2) pass, 0.1 to 1.1%
a season; attempts fail (2024 worse) and stay flat. The run's numbers sit
beside the setting in engine/nflusage.ROLE_HALF_LIFE.

Reads data/cache (nflverse's weekly player stats); writes nothing.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bridgefit import OPP, _num, _seasons, blend                 # noqa: E402
from engine import carry as C                                    # noqa: E402
from engine import defensevs as D                                # noqa: E402
from engine.form import compute_form                             # noqa: E402
from engine.models import GameLog                                # noqa: E402
from engine.nflusage import MIN_EFF_OPPS, ewma_opps              # noqa: E402
from engine.sources.nflverse import quarterbacked, stat_value    # noqa: E402
from qbscriptfit import load                                     # noqa: E402

HALF_LIVES = (2.0, 3.0, 4.0, 6.0, 8.0)


def role(opps: list[float], vals: list[float], opp_key: str, half_life: float | None) -> float | None:
    """The bridge's role: opportunities a game × this season's efficiency.
    ``half_life`` None is the board as shipped (the last VOL_WEEKS games,
    flat); a number weights every game by its age."""
    tot = sum(opps)
    if len(opps) < 2 or tot < MIN_EFF_OPPS[opp_key]:
        return None
    return ewma_opps(opps, half_life) * (sum(vals) / tot)


def points(now: list[dict], before: list[dict], season: int) -> list[dict]:
    """[{m, s, y, base, by: {H: candidate}}] — the board's base and each
    half-life's, per player-game and market, as bridgefit.points builds them."""
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
            pulled = m in C.BRIDGE_SEASON_MARKETS
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
                opps = [_num(x, col) for x in hist]
                prior = form.shrunk_to if anchored else None

                def base(est):
                    now_, with_pull = blend(form.mean, form.sample_games, est, prior, float(k or 0))
                    return with_pull if pulled else now_
                flat = role(opps, vals, opp_key, None)
                if flat is None or flat <= 0:
                    continue
                opp = r.get("opponent_team") or ""
                f = D.effect(opp, (rated.get(int(float(r["week"]))) or {}).get(opp) or {}, pos, m)[0]
                out.append({"m": m, "s": season, "y": stat_value(r, m), "base": base(flat) * f,
                            "by": {h: base(role(opps, vals, opp_key, h)) * f for h in HALF_LIVES}})
    return out


def sq(pts: list[dict], h: float | None) -> float:
    return sum((p["y"] - (p["base"] if h is None else p["by"][h])) ** 2 for p in pts)


def choose(train: list[dict], opp_key: str) -> float:
    """The half-life with the least pooled squared error, over every market
    this opportunity feeds, on the training seasons."""
    pts = [p for p in train if OPP[p["m"]][1] == opp_key]
    return min(HALF_LIVES, key=lambda h: sq(pts, h) / max(1e-9, sq(pts, None)))


def cuts(by_season: dict, market: str, h: float) -> list[tuple]:
    """[(season, n, % squared error cut by half-life h)]."""
    out = []
    for s in sorted(by_season):
        t = [p for p in by_season[s] if p["m"] == market]
        cur = sq(t, None)
        out.append((s, len(t), (1 - sq(t, h) / cur) * 100 if cur else 0.0))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--train", default="2017-2021", help="the half-life is chosen here")
    ap.add_argument("--test", default="2022-2025", help="every season here must improve")
    a = ap.parse_args(argv)
    train = [p for s in _seasons(a.train) for p in points(load(s), load(s - 1), s)]
    test = {s: points(load(s), load(s - 1), s) for s in _seasons(a.test)}
    print("Squared error cut by weighting the bridge's games by age (chosen on "
          f"{a.train}, judged on {a.test}):")
    ships = {}
    for opp_key in sorted({v[1] for v in OPP.values()}):
        h = choose(train, opp_key)
        ok = True
        for m in [m for m, v in OPP.items() if v[1] == opp_key]:
            c = cuts(test, m, h)
            ok = ok and bool(c) and all(x > 0 for *_y, x in c)
            print(f"  {opp_key:<9} half-life {h:g}  {m:<10} "
                  + "  ".join(f"{s}: {x:+.2f}%" for s, _n, x in c))
        if ok:
            ships[opp_key] = h
        print(f"  {'':<9} {'SHIPS' if ok else 'fails'}")
    print(f"\n  ROLE_HALF_LIFE = {ships}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
