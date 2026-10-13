#!/usr/bin/env python3
"""When a regular sits, how far off is the NBA board's number for his teammates? On the box.

    cd /srv/qellys && sudo -u qellys python3 nbavacancy.py          # NBA, every stored season
    cd /srv/qellys && sudo -u qellys python3 nbavacancy.py wnba     # the same for the WNBA

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
    for line in report(replay(clubs, sport, tune), sport):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
