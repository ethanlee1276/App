"""Measure the team-defense projection against each defense's season average.

    python3 dstfit.py                        # 2023-2025, weeks 4-17
    python3 dstfit.py --seasons 2024 --weeks 4-10
    python3 dstfit.py --save                 # keep the league rates and the score

Each season replayed needs its turnover counts (team_weeks.takeaways,
counted since 2026-10-20); a season stored before then is named, nothing is
measured, and the one command that fills it is printed:

    python3 -m engine.sources.nflpbp --team-weeks 2023-2025

THE QUESTION (engine/dstproj, 2026-10-27). A team defense's fantasy week was
never projected here: every league desk valued one at zero. The projection
reads the opponent's implied points off the line, both sides' sack rates and
takeaway rates. Does it put defenses in a better order, and closer to what
they scored, than the obvious baseline a manager uses: the defense's own
average so far this season?

WALKED FORWARD: each week is projected from the weeks before it (this season
and last season's at `dstproj.LAST_SEASON_WEIGHT`) and the game's closing
line (the `games` table), then scored against what the defense did that week:
its points-allowed tier from the final score, its sacks (`team_units`) and
its takeaways (`team_weeks`), on the default scoring.

WHAT THE SCORE LEAVES OUT, on both sides alike: touchdowns, safeties and
blocked kicks. The tables hold no count of a defense's own touchdowns, so the
projection's expected touchdowns are taken off it before the two are
compared, and the baseline is built from the same non-touchdown points.

NUMBERS: per week, of every two defenses which scored more (pairs), the
Spearman rank correlation, and the mean miss, for the projection and for the
baseline; the league's rates over the seasons read (sack rate, dropbacks and
takeaways a game, the spread of points around the implied total), which
`--save` keeps for `dstproj.league_rates`.

Standard library only. Reads the DB; writes only with --save.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys

from engine import dstproj
from engine.db import connect


def _weeks(spec: str) -> list[int]:
    a, _, b = spec.partition("-")
    return list(range(int(a), int(b or a) + 1))


def _games(conn, season: int, week: int) -> list[dict]:
    rows = conn.execute(
        "SELECT home, away, home_score, away_score, spread, total FROM games WHERE sport='nfl' "
        "AND season=? AND period=? AND home_score IS NOT NULL AND away_score IS NOT NULL",
        (season, f"{week:03d}")).fetchall()
    return [{"home": dstproj.code(r[0]), "away": dstproj.code(r[1]), "home_score": float(r[2]),
             "away_score": float(r[3]), "spread": r[4], "total": r[5]} for r in rows]


def _week_stats(conn, season: int, week: int) -> dict:
    """{team: (sacks made, takeaways)} for one week."""
    out: dict = {}
    p = f"{week:03d}"
    for r in conn.execute("SELECT team, sacks FROM team_units WHERE sport='nfl' AND season=? "
                          "AND period=? AND side='def'", (season, p)):
        out.setdefault(dstproj.code(r[0]), [0.0, 0.0])[0] = float(r[1] or 0)
    for r in conn.execute("SELECT team, takeaways FROM team_weeks WHERE sport='nfl' AND season=? "
                          "AND period=?", (season, p)):
        out.setdefault(dstproj.code(r[0]), [0.0, 0.0])[1] = float(r[1] or 0)
    return out


def actual_points(allowed: float, sacks: float, takeaways: float) -> float:
    """A defense's week on the default scoring, touchdowns aside."""
    tier = next(t[2] for t in dstproj.DEFAULT["pts_allow"] if t[0] <= allowed <= t[1])
    return tier + sacks * dstproj.DEFAULT["sack"] + takeaways * dstproj.DEFAULT["int"]


def projected_no_td(row: dict) -> float:
    d = dict(row.get("dst") or {})
    for k in ("def_td", "st_td", "safe", "blk_kick"):
        d[k] = 0.0
    return dstproj.points(d)


def _rank(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2.0
        i = j + 1
    return ranks


def spearman(a: list[float], b: list[float]) -> float | None:
    if len(a) < 3:
        return None
    ra, rb = _rank(a), _rank(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else None


def pairs(pred: list[float], real: list[float]) -> tuple[int, int]:
    """(right, counted) over every two defenses whose real weeks differ."""
    right = n = 0
    for i in range(len(real)):
        for j in range(i + 1, len(real)):
            if real[i] == real[j] or pred[i] == pred[j]:
                continue
            n += 1
            right += int((pred[i] > pred[j]) == (real[i] > real[j]))
    return right, n


def run(conn, seasons: list[int], weeks: list[int]) -> dict:
    lg = dstproj.league_rates()
    out = {"weeks": 0, "n": 0, "pairs_proj": [0, 0], "pairs_base": [0, 0], "rank_proj": [], "rank_base": [],
           "abs_proj": 0.0, "abs_base": 0.0, "resid": [], "sacks": 0.0, "dropbacks": 0.0, "takeaways": 0.0,
           "ta_games": 0, "team_games": 0}
    for season in seasons:
        history: dict = {}                                   # team -> [non-TD points this season]
        for week in range(1, max(weeks) + 1):
            games = _games(conn, season, week)
            if not games:
                continue
            stats = _week_stats(conn, season, week)
            rates = dstproj.season_rates(conn, season, week)
            pred, base, real = [], [], []
            for g in games:
                for d, allowed in ((g["home"], g["away_score"]), (g["away"], g["home_score"])):
                    row = dstproj.project(g, d, rates, lg)
                    if row is None or d not in stats:
                        continue
                    sacks, ta = stats[d]
                    pts = actual_points(allowed, sacks, ta)
                    own = history.get(d) or []
                    if week in weeks and own:
                        pred.append(projected_no_td(row))
                        base.append(sum(own) / len(own))
                        real.append(pts)
                        opp = g["away"] if d == g["home"] else g["home"]
                        out["resid"].append(allowed - dstproj.implied(g, opp, lg))
                    history.setdefault(d, []).append(pts)
            if week in weeks and len(real) >= 4:
                out["weeks"] += 1
                out["n"] += len(real)
                for key, xs in (("proj", pred), ("base", base)):
                    r, n = pairs(xs, real)
                    out[f"pairs_{key}"][0] += r
                    out[f"pairs_{key}"][1] += n
                    rho = spearman(xs, real)
                    if rho is not None:
                        out[f"rank_{key}"].append(rho)
                    out[f"abs_{key}"] += sum(abs(x - y) for x, y in zip(xs, real))
        for r in conn.execute("SELECT SUM(sacks), SUM(dropbacks) FROM team_units WHERE sport='nfl' "
                              "AND season=? AND side='def'", (season,)):
            out["sacks"] += float(r[0] or 0)
            out["dropbacks"] += float(r[1] or 0)
        for r in conn.execute("SELECT SUM(takeaways), COUNT(takeaways), COUNT(*) FROM team_weeks "
                              "WHERE sport='nfl' AND season=?", (season,)):
            out["takeaways"] += float(r[0] or 0)
            out["ta_games"] += int(r[1] or 0)
            out["team_games"] += int(r[2] or 0)
    return out


def turnovers_missing(conn, seasons: list[int]) -> list[int]:
    """The seasons whose team_weeks rows hold no turnover counts. Stored
    before the columns were (2026-10-20), they read NULL; summed as none,
    they measured the league at 0.0 takeaways a game and scored every
    defense's week without its takeaways (the box, 2026-10-28)."""
    out = []
    for season in seasons:
        n, counted, total = conn.execute(
            "SELECT COUNT(*), COUNT(takeaways), COALESCE(SUM(takeaways), 0) FROM team_weeks "
            "WHERE sport='nfl' AND season=?", (season,)).fetchone()
        if n and (counted < n or not total):
            out.append(season)
    return out


def _span(seasons: list[int]) -> str:
    """2023-2025 for a run of seasons, else 2023,2025."""
    s = sorted(seasons)
    if len(s) > 1 and s == list(range(s[0], s[-1] + 1)):
        return f"{s[0]}-{s[-1]}"
    return ",".join(map(str, s))


def summary(res: dict, seasons: list[int], weeks: list[int]) -> dict:
    n = max(1, res["n"])
    pp, pb = res["pairs_proj"], res["pairs_base"]
    resid = res["resid"]
    sd = math.sqrt(sum(x * x for x in resid) / len(resid)) if resid else None
    league = {}
    if res["dropbacks"]:
        league["sack_rate"] = round(res["sacks"] / res["dropbacks"], 4)
    if res["team_games"]:
        league["dropbacks"] = round(res["dropbacks"] / res["team_games"], 2)
    if res["ta_games"] and res["takeaways"] > 0:              # none counted is no measurement
        league["takeaways"] = round(res["takeaways"] / res["ta_games"], 3)
    if sd:
        league["pa_sd"] = round(sd, 2)
    return {
        "measured": dt.date.today().isoformat(),
        "seasons": f"{min(seasons)}-{max(seasons)}", "weeks": f"{min(weeks)}-{max(weeks)}",
        "score": {"n": res["n"], "weeks": res["weeks"],
                  "pairs_proj": round(pp[0] / pp[1], 4) if pp[1] else None,
                  "pairs_base": round(pb[0] / pb[1], 4) if pb[1] else None,
                  "rank_proj": round(sum(res["rank_proj"]) / len(res["rank_proj"]), 4) if res["rank_proj"] else None,
                  "rank_base": round(sum(res["rank_base"]) / len(res["rank_base"]), 4) if res["rank_base"] else None,
                  "mae_proj": round(res["abs_proj"] / n, 3), "mae_base": round(res["abs_base"] / n, 3)},
        "league": league,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seasons", default="2023-2025", help="seasons to replay, e.g. 2023-2025 or 2024")
    ap.add_argument("--weeks", default="4-17", help="weeks of each season to score, e.g. 4-17")
    ap.add_argument("--save", action="store_true",
                    help="keep the league rates and the score in data/models/dst_fit.json for dstproj")
    args = ap.parse_args(argv)
    seasons, weeks = _weeks(args.seasons), _weeks(args.weeks)
    conn = connect()
    try:
        missing = turnovers_missing(conn, seasons)
        res = None if missing else run(conn, seasons, weeks)
    finally:
        conn.close()
    if missing:
        print(f"The turnover counts are missing for {', '.join(map(str, missing))}: those weeks were stored "
              "before takeaways were counted, so every defense would score without its takeaways and the "
              "league would read zero a game. Nothing measured, nothing saved. Fill them first:")
        print(f"    python3 -m engine.sources.nflpbp --team-weeks {_span(missing)}")
        return 1
    doc = summary(res, seasons, weeks)
    s = doc["score"]
    if not s["n"]:
        print("No defense-weeks to score: the games, team_units and team_weeks tables hold nothing "
              f"for {doc['seasons']} weeks {doc['weeks']}.")
        return 1
    print(f"Team defenses, {doc['seasons']} weeks {doc['weeks']}: {s['n']} defense-weeks over {s['weeks']} weeks.")
    print(f"  Of every two defenses, the higher scorer ahead: projection {s['pairs_proj']:.1%}, "
          f"season average {s['pairs_base']:.1%}.")
    if s["rank_proj"] is not None:
        print(f"  Rank correlation a week: projection {s['rank_proj']:.3f}, season average {s['rank_base']:.3f}.")
    print(f"  Missed by (points, touchdowns aside): projection {s['mae_proj']:.2f}, season average {s['mae_base']:.2f}.")
    print(f"  League: {json.dumps(doc['league'])}")
    if args.save:
        dstproj.FIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        dstproj.FIT_PATH.write_text(json.dumps(doc, indent=1))
        print(f"  Saved: {dstproj.FIT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
