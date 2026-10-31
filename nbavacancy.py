#!/usr/bin/env python3
"""When a regular sits, how far off is the NBA board's number for his teammates? On the box.

    cd /srv/qellys && sudo -u qellys python3 nbavacancy.py          # NBA, every stored season
    cd /srv/qellys && sudo -u qellys python3 nbavacancy.py wnba     # the same for the WNBA
    cd /srv/qellys && sudo -u qellys python3 nbavacancy.py --heldout         # the rule, held out
    cd /srv/qellys && sudo -u qellys python3 nbavacancy.py --heldout --save  # ...and keep its verdict

Read-only: it opens the history database read-only and writes nothing.

Ethan, 2026-10-13: "We worked so hard on nfl so ik CFB and mlb and nba
and ufc is missing stuff." The NBA board reads the injury board now
(nba_build.hoops_injuries): a man ruled out is held, and his teammates'
cards say he is out. What the number does NOT do is move. The minutes
model has a slot for the minutes a vacancy opens
(`engine/nba/minutes.project_minutes(vacancy_minutes=...)`) and nothing
has ever filled it, so a teammate's number is the same whether the star
plays or sits — while the books raise that teammate's line the moment
the star is ruled out. If the board's number runs LOW for teammates in
those games, its card leans UNDER on exactly the lines the books just
raised, and no hold catches it: the hold is on the star, not on them.

This replays every stored season with the board's own projection
(`engine/nba/pipeline.project`: his last 20 games for the club, his
role's minutes, the per-minute rate, the league's fitted tuning).
Tonight's spread, total and defence are not known here and are held
neutral, and the player memory (`engine/playerfit`) is held at 1.0,
because it was fitted on bets graded after these games. Every teammate
who played is scored, and his game is one of two kinds:

  * FRESH ABSENCE — a regular (24 or more minutes a game over his last
    ten for the club) who played in one of the club's last three games
    is not in tonight's box score (the board's own rule for "out
    tonight" is news, `nba_build.NEW_ABSENCE_GAMES`);
  * NORMAL — nobody like that is missing.

For minutes and each stat it prints the mean of (actual − projection)
with a 95% interval, counted per team-game — teammates in one game share
the absence, so a game is one observation, not eight.

THE BAR, set before the first run: the vacancy slot is worth a candidate
rule only if, in EVERY season measured, teammates' minutes run at least
+1.0 above the projection in fresh-absence games with the interval above
0, AND points run above the projection with the interval above 0. A
candidate that clears it still has to beat the empty slot on held-out
seasons before it moves a number; this script changes nothing.

THE HELD-OUT TEST (`--heldout`, 2026-10-17, after the bar above was MET on
the box): the rule in engine/nba/vacancy — ``k`` × the absent regulars'
usual minutes, shared over the teammates who played in proportion to each
one's own base minutes — replayed through the board's own minutes model
(`project_minutes(vacancy_minutes=...)`, its caps included) and the same
per-minute rate. Each season held out in turn, ``k`` fitted on the others
(least squared error on minutes). THE BAR, written before the run: in
EVERY held-out season the squared error of BOTH minutes and points in
fresh-absence games falls against the empty slot. `--save` writes the
verdict (data/models/nba_vacancy.json) with ``k`` fitted on every season;
the board fills the slot only when it holds (engine/nba/vacancy.k_for).
Opened read-only like the rest; `--save` writes only that one file.
"""

import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

STATS = ("min", "pts", "reb", "ast", "fg3m")
#: A regular: this many minutes a game over his last REGULAR_GAMES for the club.
REGULAR_MIN = 24.0
REGULAR_GAMES = 10
#: A FRESH absence: he played in one of the club's last FRESH games.
FRESH = 3
#: The board's own history length and its floor for a prop (nba_build).
WINDOW = 20
MIN_PRIOR = 3
#: The bar's minutes threshold.
BAR_MINUTES = 1.0


def load(conn, sport: str) -> dict:
    """``{(season, team): {date: {player: {stat: value, "starter": bool}}}}``."""
    clubs: dict = {}
    marks = ",".join("?" * len(STATS))
    for season, team, date, player, pos, market, value in conn.execute(
            f"SELECT season, team, period, player, position, market, value "
            f"FROM player_game_logs WHERE sport=? AND market IN ({marks})",
            (sport, *STATS)):
        g = clubs.setdefault((int(season), str(team)), {}).setdefault(str(date), {})
        row = g.setdefault(str(player), {})
        row[market] = float(value or 0.0)
        if market == "min":
            row["starter"] = (pos == "S")
    return clubs


def _absent(hist: dict, game: dict, recent: set) -> list:
    """The fresh-absent regulars tonight: played lately, not in the box."""
    out = []
    for name, past in hist.items():
        if name in game:
            continue
        last = past[-REGULAR_GAMES:]
        mins = [s.get("min", 0.0) for _d, s in last]
        if len(mins) < MIN_PRIOR or sum(mins) / len(mins) < REGULAR_MIN:
            continue
        if any(d in recent for d, _s in past[-FRESH:]):
            out.append(name)
    return out


def replay(clubs: dict, sport: str, tune=None) -> dict:
    """``{season: {"absence"|"normal": {stat: [per-game mean residual]}}}`` and
    the counts, from the board's own projection."""
    from engine import playerfit
    from engine.hoops import for_league
    from engine.nba import pipeline
    tune = tune or for_league(sport)
    keep = playerfit.mult_for
    playerfit.mult_for = lambda *a, **k: 1.0
    out: dict = {}
    try:
        for (season, _team), games in sorted(clubs.items()):
            by = out.setdefault(season, {"absence": {s: [] for s in STATS},
                                         "normal": {s: [] for s in STATS},
                                         "games": {"absence": 0, "normal": 0},
                                         "skipped": 0})
            dates = sorted(games)
            hist: dict = {}
            for i, d in enumerate(dates):
                game = games[d]
                recent = set(dates[max(0, i - FRESH):i])
                kind = "absence" if _absent(hist, game, recent) else "normal"
                resid = {s: [] for s in STATS}
                for name, s in game.items():
                    if s.get("min", 0.0) <= 0:
                        continue
                    prior = list(reversed(hist.get(name, [])[-WINDOW:]))   # newest first
                    if len(prior) < MIN_PRIOR:
                        continue
                    mins = [p.get("min", 0.0) for _d, p in prior]
                    base = {"player": name, "minutes": mins, "spread": 0.0,
                            "is_starter": bool(prior[0][1].get("starter")),
                            "is_favorite": False, "rest": "1day"}
                    pj_min = None
                    for stat in STATS[1:]:
                        pj = pipeline.project({**base, "market": stat,
                                               "values": [p.get(stat, 0.0) for _d, p in prior]},
                                              tune)
                        if "skip" in pj:
                            by["skipped"] += 1
                            continue
                        pj_min = pj["proj_min"]
                        resid[stat].append(s.get(stat, 0.0) - pj["projection"])
                    if pj_min is not None:
                        resid["min"].append(s.get("min", 0.0) - pj_min)
                if resid["min"]:
                    by["games"][kind] += 1
                    for stat, vals in resid.items():
                        if vals:
                            by[kind][stat].append(sum(vals) / len(vals))
                for name, s in game.items():
                    hist.setdefault(name, []).append((d, s))
    finally:
        playerfit.mult_for = keep
    return out


def cases(clubs: dict, sport: str, tune=None) -> list:
    """Every teammate who played in a fresh-absence game, with what the
    board projected for him and what it would have with a vacancy:
    ``[{season, min, pts, proj_min, proj_pts, base, starter, high, absent, share}]``.
    ``absent`` is the absent regulars' usual minutes summed; ``share`` his
    base minutes over the base minutes of every teammate who played."""
    from engine import playerfit
    from engine.hoops import for_league
    from engine.nba import pipeline
    from engine.nba.minutes import base_minutes, role_minutes
    tune = tune or for_league(sport)
    keep = playerfit.mult_for
    playerfit.mult_for = lambda *a, **k: 1.0
    out: list = []
    try:
        for (season, team), games in sorted(clubs.items()):
            dates = sorted(games)
            hist: dict = {}
            for i, d in enumerate(dates):
                game = games[d]
                recent = set(dates[max(0, i - FRESH):i])
                gone = _absent(hist, game, recent)
                if gone:
                    absent = sum(sum(s.get("min", 0.0) for _d, s in hist[g][-REGULAR_GAMES:])
                                 / len(hist[g][-REGULAR_GAMES:]) for g in gone)
                    rows = []
                    for name, s in game.items():
                        if s.get("min", 0.0) <= 0:
                            continue
                        prior = list(reversed(hist.get(name, [])[-WINDOW:]))   # newest first
                        if len(prior) < MIN_PRIOR:
                            continue
                        mins = [p.get("min", 0.0) for _d, p in prior]
                        pj = pipeline.project({"player": name, "minutes": mins, "spread": 0.0,
                                               "is_starter": bool(prior[0][1].get("starter")),
                                               "is_favorite": False, "rest": "1day", "market": "pts",
                                               "values": [p.get("pts", 0.0) for _d, p in prior]}, tune)
                        if "skip" in pj or not pj.get("proj_min"):
                            continue
                        base = base_minutes(role_minutes(mins)[0], tune) or 0.0
                        rows.append({"season": season, "team": team, "date": d,
                                     "min": s.get("min", 0.0), "pts": s.get("pts", 0.0),
                                     "proj_min": float(pj["proj_min"]), "proj_pts": float(pj["projection"]),
                                     "base": float(base), "starter": bool(prior[0][1].get("starter")),
                                     "high": max(mins) if mins else None, "absent": absent})
                    tot = sum(r["base"] for r in rows if r["base"] > 0)
                    for r in rows:
                        r["share"] = (r["base"] / tot) if tot > 0 and r["base"] > 0 else 0.0
                        out.append(r)
                for name, s in game.items():
                    hist.setdefault(name, []).append((d, s))
    finally:
        playerfit.mult_for = keep
    return out


def _with_k(r: dict, k: float, tune) -> tuple:
    """(minutes, points) the board would have projected with ``k``."""
    from engine.nba.minutes import project_minutes
    if k <= 0 or r["share"] <= 0:
        return r["proj_min"], r["proj_pts"]
    m0 = project_minutes(r["base"], 0.0, r["starter"], False, "1day",
                         recent_high=r["high"], tune=tune)
    mk = project_minutes(r["base"], 0.0, r["starter"], False, "1day",
                         vacancy_minutes=k * r["absent"] * r["share"], recent_high=r["high"], tune=tune)
    if not m0:
        return r["proj_min"], r["proj_pts"]
    return r["proj_min"] * mk / m0, r["proj_pts"] * mk / m0


def _sse(rows: list, k: float, tune) -> tuple:
    em = ep = 0.0
    for r in rows:
        pm, pp = _with_k(r, k, tune)
        em += (r["min"] - pm) ** 2
        ep += (r["pts"] - pp) ** 2
    return em, ep


def heldout(rows: list, sport: str = "nba", tune=None) -> dict:
    """Each season held out in turn: ``k`` fitted on the others, scored
    against the empty slot. ``{"holds", "k", "by_season", "n"}`` — ``k``
    refitted on every season for the board to use if it holds."""
    from engine.hoops import for_league
    from engine.nba.vacancy import K_GRID
    tune = tune or for_league(sport)
    seasons = sorted({r["season"] for r in rows})
    by: dict = {}

    def fit(train):
        return min(K_GRID, key=lambda k: (_sse(train, k, tune)[0], k))

    for s in seasons:
        train = [r for r in rows if r["season"] != s]
        test = [r for r in rows if r["season"] == s]
        if not train or not test:
            continue
        k = fit(train)
        m0, p0 = _sse(test, 0.0, tune)
        mk, pk = _sse(test, k, tune)
        by[str(s)] = {"k": k, "n": len(test),
                      "minutes_gain": round(1 - mk / m0, 4) if m0 else 0.0,
                      "points_gain": round(1 - pk / p0, 4) if p0 else 0.0}
    holds = len(by) >= 2 and all(v["k"] > 0 and v["minutes_gain"] > 0 and v["points_gain"] > 0
                                 for v in by.values())
    return {"holds": holds, "k": fit(rows) if rows else 0.0, "by_season": by, "n": len(rows),
            "bar": "every held-out season: squared error of minutes AND points falls against the empty slot"}


def heldout_report(res: dict, sport: str) -> list:
    lines = [f"{sport.upper()} VACANCY RULE, HELD OUT — k × the absent regulars' minutes, shared by base "
             f"minutes over the teammates who played ({res['n']} teammate-games in fresh absences)", ""]
    for s, v in sorted(res["by_season"].items()):
        lines.append(f"  {s} held out   k {v['k']:.2f} (fitted on the others)   n {v['n']:5d}   "
                     f"minutes {100 * v['minutes_gain']:+.2f}%   points {100 * v['points_gain']:+.2f}%")
    lines.append("")
    lines.append(f"THE BAR ({res['bar']}): " + ("HOLDS" if res["holds"] else "does not hold")
                 + (f" — the board fills the slot at k {res['k']:.2f} once saved (--save)." if res["holds"]
                    else " — the slot stays empty."))
    return lines


def _mean_ci(vals: list) -> tuple:
    n = len(vals)
    if n < 2:
        return (sum(vals) / n if n else 0.0), 0.0, n
    m = sum(vals) / n
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1))
    return m, 1.96 * sd / math.sqrt(n), n


def verdict(res: dict) -> tuple[bool, list]:
    """Does every season clear THE BAR? ``(met, reasons it did not)``."""
    why = []
    seasons = [s for s, by in res.items() if by["games"]["absence"] >= 2]
    if not seasons:
        return False, ["no season has fresh-absence games to measure"]
    for season in seasons:
        by = res[season]["absence"]
        m, ci, _n = _mean_ci(by["min"])
        if not (m >= BAR_MINUTES and m - ci > 0):
            why.append(f"{season}: minutes {m:+.2f} ± {ci:.2f}")
        p, pci, _pn = _mean_ci(by["pts"])
        if not (p - pci > 0):
            why.append(f"{season}: points {p:+.2f} ± {pci:.2f}")
    return not why, why


def report(res: dict, sport: str) -> list:
    lines = [f"{sport.upper()}  actual − the board's projection, per team-game "
             f"(95% interval); fresh absence = a {REGULAR_MIN:.0f}+ minute regular "
             f"who played in one of the last {FRESH} games is not in the box", ""]
    head = f"{'season':<7}{'games':<16}" + "".join(f"{s:>16}" for s in STATS)
    lines.append(head)
    for season in sorted(res):
        by = res[season]
        for kind in ("absence", "normal"):
            cells = []
            for stat in STATS:
                m, ci, n = _mean_ci(by[kind][stat])
                cells.append(f"{m:+7.2f} ±{ci:5.2f}" if n else f"{'—':>14}")
            lines.append(f"{season:<7}{kind + ' ' + str(by['games'][kind]):<16}"
                         + "".join(f"{c:>16}" for c in cells))
    met, why = verdict(res)
    lines.append("")
    lines.append(f"THE BAR (set before the first run): every season, minutes ≥ +{BAR_MINUTES:.1f} "
                 f"and points above 0 in fresh-absence games, intervals clear of 0 — "
                 + ("MET: a vacancy rule has earned a held-out test." if met else
                    "NOT MET: " + "; ".join(why[:6])))
    lines.append("Nothing is changed by this run; the minutes model's vacancy slot stays empty.")
    return lines


def _ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    flags = {a for a in argv if a.startswith("--")}
    argv = [a for a in argv if not a.startswith("--")]
    sport = (argv[0] if argv else "nba").lower()
    from engine import db
    conn = _ro(db.DEFAULT_DB)
    conn.row_factory = sqlite3.Row
    try:
        clubs = load(conn, sport)
        # The tuning the board itself runs on (hoops_fit), read from the
        # same read-only connection.
        try:
            from engine.hoops_fit import fitted_tuning
            tune, _rep = fitted_tuning(conn, sport)
        except Exception:                                   # noqa: BLE001
            tune = None
    finally:
        conn.close()
    if not clubs:
        print(f"No {sport} logs stored.")
        return 0
    if "--heldout" in flags:
        res = heldout(cases(clubs, sport, tune), sport, tune)
        for line in heldout_report(res, sport):
            print(line)
        if "--save" in flags:
            from engine.nba import vacancy
            print(f"saved: {vacancy.save(sport, res)}")
        return 0
    for line in report(replay(clubs, sport, tune), sport):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
