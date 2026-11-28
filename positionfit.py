#!/usr/bin/env python3
"""Which defence number should a catcher's matchup read count? (step AHO, 25 November 2026)

    python3 positionfit.py                      # 2022-2025
    python3 positionfit.py --seasons 2022-2026

Ethan, on a Packers at Rams fade of Tucker Kraft that read only "LA gives up the second-fewest passing yards":
"you're not going into specifics about how many passing yards they give up to tight ends ... how a real sports
bettor would use it". The read now SAYS what a defence gives up to his own position (engine/gamescan.position_line);
this measures whether it should also COUNT.

For every regular-season receiver and tight end game from week 4 on, with three earlier games that season and 15+
receiving yards a game in them, what he gained against his own average in those games, split by the defence's
rank in the games before this one (rank 1 gives up the most):

  * by its passing yards allowed overall (what the read counts: engine/defensevs.MODEL_STAT);
  * by what it gives up to his own position;
  * by the two together, either way.

A rule's split is the yards gained, as a share of his own average, in the games it calls good against the games it
calls tough. Reads data/cache/player_stats_<season>.csv (the NFL build's own nflverse box scores).
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from engine import defensevs as D

ROOT = Path(__file__).resolve().parent
FIRST_WEEK, MIN_PRIOR_GAMES, FLOOR = 4, 3, 15.0


def quarter(rank: int, n: int) -> int:
    """+1 in the league's softest quarter, −1 its stingiest (gamescan._allowed_line's cut), else 0."""
    q = max(1, round(n * 0.25))
    return 1 if rank <= q else (-1 if rank > n - q else 0)


def third(rank: int, n: int) -> int:
    return 1 if rank <= n / 3 else (-1 if rank > n * 2 / 3 else 0)


#: The rules measured: (overall rank, its n, position rank, its n) -> +1 / −1 / 0.
RULES = {
    "overall, quarter (the read now)": lambda o, on, p, pn: quarter(o, on),
    "position, quarter": lambda o, on, p, pn: quarter(p, pn),
    "position, third": lambda o, on, p, pn: third(p, pn),
    "overall quarter or position third, none if they disagree": lambda o, on, p, pn: (
        0 if quarter(o, on) * third(p, pn) < 0 else (quarter(o, on) or third(p, pn))),
    "both thirds agree": lambda o, on, p, pn: third(o, on) if third(o, on) == third(p, pn) else 0,
}


def samples(rows: list[dict]) -> list[tuple]:
    """[(group, expected yards, yards, overall rank, n, position rank, n)] for one season's weekly rows."""
    reg = [r for r in rows if D._regular(r)]
    games = D.allowed_by_game(reg, 99)
    by_player: dict = {}
    for r in reg:
        g = D.GROUP_OF.get(str(r.get("position") or "").upper())
        if g in ("WR", "TE"):
            by_player.setdefault(str(r.get("player_id") or r.get("player_display_name")), []).append((D._week(r), g, r))
    cache: dict = {}

    def ranks(wk):
        if wk not in cache:
            cut = {t: {w: v for w, v in g.items() if w < wk} for t, g in games.items()}
            per = {t: {s: sum(v[s] for v in g.values()) / len(g) for s in D.STATS} for t, g in cut.items() if g}
            out: dict = {}
            for s in ("qb_pass_yds", "wr_rec_yds", "te_rec_yds"):
                order = sorted(per, key=lambda t: (-per[t][s], t))
                for i, t in enumerate(order):
                    out.setdefault(t, {})[s] = (i + 1, len(order))
            cache[wk] = out
        return cache[wk]
    out = []
    for logs in by_player.values():
        logs.sort(key=lambda x: x[0])
        for i, (wk, g, r) in enumerate(logs):
            if wk < FIRST_WEEK or i < MIN_PRIOR_GAMES:
                continue
            prev = [x[2] for x in logs[:i]]
            e = sum(D._f(p, "receiving_yards") for p in prev) / len(prev)
            if e < FLOOR:
                continue
            rk = ranks(wk).get(str(r.get("opponent_team") or ""))
            if not rk:
                continue
            (o, on), (p, pn) = rk["qb_pass_yds"], rk[f"{g.lower()}_rec_yds"]
            out.append((g, e, D._f(r, "receiving_yards"), o, on, p, pn))
    return out


def split(pts: list[tuple], rule) -> dict:
    """{"good": share, "tough": share, "voted": share of games}: yards against his own average."""
    acc = {1: [0.0, 0.0, 0], -1: [0.0, 0.0, 0], 0: [0.0, 0.0, 0]}
    for _g, e, y, o, on, p, pn in pts:
        a = acc[rule(o, on, p, pn)]
        a[0] += e
        a[1] += y
        a[2] += 1
    share = {k: (v[1] / v[0] if v[0] else None) for k, v in acc.items()}
    n = sum(v[2] for v in acc.values())
    return {"good": share[1], "tough": share[-1], "voted": (acc[1][2] + acc[-1][2]) / n if n else 0.0, "n": n}


def _load(season: int) -> list[dict]:
    with open(ROOT / "data" / "cache" / f"player_stats_{season}.csv", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="2022-2025")
    a, _, b = ap.parse_args().seasons.partition("-")
    years = list(range(int(a), int(b or a) + 1))
    per = {y: samples(_load(y)) for y in years}
    pool = [x for y in years for x in per[y]]
    print(f"{len(pool)} receiver and tight end games, {years[0]}-{years[-1]}: yards as a share of his own average")
    for name, rule in RULES.items():
        print(f"\n{name}")
        for grp in ("all", "WR", "TE"):
            line = []
            for y in years + ["pool"]:
                pts = pool if y == "pool" else per[y]
                s = split([x for x in pts if grp == "all" or x[0] == grp], rule)
                if s["good"] is None or s["tough"] is None:
                    continue
                line.append(f"{y}: {s['good']:.0%}/{s['tough']:.0%}")
            s = split([x for x in pool if grp == "all" or x[0] == grp], rule)
            print(f"  {grp:<3} " + "  ".join(line) + f"   (votes in {s['voted']:.0%} of games)")


if __name__ == "__main__":
    main()
