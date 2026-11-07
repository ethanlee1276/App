"""What the spread actually does to a touchdown board, measured twice.

Every earlier check on game script, the game total and opponent defence
was run WITHIN a game — player-level AUC, mostly. That design cannot see
any of them. The spread and the total are constant inside a game, so they
never separate two players on the same team; the measurement understates
them by construction and reading a 0.55 from it as "game script does not
matter" is reading the design, not the data.

This module asks the two questions those factors are actually for:

  BETWEEN GAMES — how many touchdowns is a team worth? One row per
  team-game, target the offensive touchdowns its skill players scored,
  leave-one-season-out held-out RMSE.

  WITHIN A TEAM — once the team scores, who gets it? One row per
  team-game, target the lead back's and lead receiver's share of those
  touchdowns, scored by chi-square of band means against realised.

THE SECOND SCORE IS NOT SQUARED ERROR, AND THAT IS DELIBERATE. One
player's share of one game is noisy enough to hide a 20% systematic
shift, so per-game squared error calls a badly biased multiplier a tie.
Chi-square of band means measures the thing a multiplier is for.

AND THE POPULATION IS THE LEAD PLAYER, NOT THE POSITION GROUP. Scored on
the whole WR+TE group the shipped college receiver curve looks worse than
no curve at all; scored on the lead receiver — the one a book quotes — it
wins by 24 chi-square points. Both are true, because a heavy favourite's
WR1 loses share to his own backups. Measure the population the model is
applied to or the number is about something else.

Standard library only. Needs `games` with spreads and `player_game_logs`
with `anytime_td`; no odds history, so it runs anywhere.

    python3 -m engine.scriptfit [nfl|cfb ...]
"""

from __future__ import annotations

import math
import sqlite3
import sys
from collections import defaultdict

from engine.cfb import tds as C
from engine.models import Game, Weather
from engine.db import DEFAULT_DB
from engine.touchdowns import script_td_multiplier

#: Positions that carry the ball and catch it. `FB` is rare and belongs
#: with the backs; college feeds spell it inconsistently.
RB_POS = {"RB", "FB", "HB"}
WR_POS = {"WR", "TE"}

#: Past this the fit extrapolates rather than measures — the same cap the
#: shipped curve holds its lead at.
LEAD_CAP = 35.0

#: Bands for the chi-square. Wide enough that each holds a real sample in
#: both sports, which college spreads running to 45 makes awkward.
BANDS = ((-99, -21), (-21, -14), (-14, -7), (-7, -3), (-3, 3),
         (3, 7), (7, 14), (14, 21), (21, 99))

#: A band thinner than this is noise wearing a mean.
MIN_BAND = 25

#: Below this a held-out season cannot train or score anything.
MIN_TRAIN, MIN_TEST = 300, 100


def team_lines(conn, sport: str) -> dict:
    """``{(season, period, team): spread}`` from that TEAM's own side."""
    out = {}
    for (season, period, home, away, spread, _total) in conn.execute(
            "SELECT season, period, home, away, spread, total FROM games "
            "WHERE sport=? AND spread IS NOT NULL AND total IS NOT NULL",
            (sport,)):
        out[(season, period, home)] = float(spread)
        out[(season, period, away)] = -float(spread)
    return out


def team_implied(conn, sport: str) -> dict:
    """``{(season, period, team): implied points}`` — (total -/+ spread)/2."""
    out = {}
    for (season, period, home, away, spread, total) in conn.execute(
            "SELECT season, period, home, away, spread, total FROM games "
            "WHERE sport=? AND spread IS NOT NULL AND total IS NOT NULL",
            (sport,)):
        out[(season, period, home)] = (float(total) - float(spread)) / 2.0
        out[(season, period, away)] = (float(total) + float(spread)) / 2.0
    return out


def team_touchdowns(conn, sport: str, keys) -> dict:
    """``{(season, period, team): offensive TDs}``.

    KEYED ON TEAM, NOT GAME ID. The NFL logs spell a game "ARI-001" while
    `games` spells it "DAL@TB", so the obvious join returns zero rows and
    reads as missing data. A team plays once per period in both sports.
    """
    out = defaultdict(float)
    for (season, period, team, value) in conn.execute(
            "SELECT season, period, team, SUM(value) FROM player_game_logs "
            "WHERE sport=? AND market='anytime_td' GROUP BY 1, 2, 3", (sport,)):
        key = (season, period, team)
        if key in keys:
            out[key] = float(value or 0.0)
    return out


def lead_players(conn, sport: str, group: str) -> dict:
    """``{(season, team): player}`` — the season's volume leader.

    The ROLE, keyed on the whole season, not "whoever scored today":
    picking the leader by touchdowns would be scoring the model on its
    own answer.
    """
    # College carries a single `targets` row in the entire table, so
    # keying a receiver on it silently yields a 0.000 share and a tidy
    # zero chi-square that looks like a clean tie.
    market = "receptions" if group == "WR" else "carries"
    want = WR_POS if group == "WR" else RB_POS
    volume = defaultdict(float)
    for (season, team, player, pos, value) in conn.execute(
            "SELECT season, team, player, position, SUM(value) "
            "FROM player_game_logs WHERE sport=? AND market=? "
            "GROUP BY 1, 2, 3, 4", (sport, market)):
        if (pos or "").upper() in want:
            volume[(season, team, player)] += float(value or 0.0)
    best: dict = {}
    for (season, team, player), value in volume.items():
        key = (season, team)
        if key not in best or value > best[key][1]:
            best[key] = (player, value)
    return {k: v[0] for k, v in best.items()}


def player_touchdowns(conn, sport: str, lead: dict, keys) -> dict:
    out = defaultdict(float)
    for (season, period, team, player, value) in conn.execute(
            "SELECT season, period, team, player, SUM(value) "
            "FROM player_game_logs WHERE sport=? AND market='anytime_td' "
            "GROUP BY 1, 2, 3, 4", (sport,)):
        key = (season, period, team)
        if key in keys and lead.get((season, team)) == player:
            out[key] += float(value or 0.0)
    return out


def shipped_multiplier(sport: str, spread: float, group: str) -> float:
    """The multiplier the board would actually apply to this player."""
    if sport == "cfb":
        # `script_multiplier` takes the HOME line and derives the lead
        # itself: lead = -spread_home for the home side. Passing -spread
        # here runs the curve backwards, which reads as the shipped form
        # being twice as bad as no curve at all.
        return C.script_multiplier(spread, True, group)[0]
    game = Game(home="A", away="B", weather=Weather(dome=True),
                spread=spread, total=47.0)
    return script_td_multiplier(game, "A", group)[0]


def wmean(rows, key: str) -> float:
    weight = sum(r["n"] for r in rows)
    return sum(r[key] * r["n"] for r in rows) / weight if weight else 0.0


def solve(A, b):
    """Gaussian elimination with partial pivoting; None if singular."""
    k = len(b)
    A = [row[:] for row in A]
    b = b[:]
    for i in range(k):
        p = max(range(i, k), key=lambda t: abs(A[t][i]))
        A[i], A[p] = A[p], A[i]
        b[i], b[p] = b[p], b[i]
        if abs(A[i][i]) < 1e-12:
            return None
        for t in range(i + 1, k):
            f = A[t][i] / A[i][i]
            for c in range(i, k):
                A[t][c] -= f * A[i][c]
            b[t] -= f * b[i]
    out = [0.0] * k
    for i in range(k - 1, -1, -1):
        out[i] = (b[i] - sum(A[i][j] * out[j] for j in range(i + 1, k))) / A[i][i]
    return out


def wls(rows, key: str, design):
    """Weighted least squares. `design(row)` returns the row's features."""
    k = len(design(rows[0]))
    A = [[0.0] * k for _ in range(k)]
    b = [0.0] * k
    for r in rows:
        x = design(r)
        for i in range(k):
            b[i] += r["n"] * x[i] * r[key]
            for j in range(k):
                A[i][j] += r["n"] * x[i] * x[j]
    return solve(A, b)


def rmse(rows, key: str, pred) -> float:
    weight = sum(r["n"] for r in rows)
    if not weight:
        return float("nan")
    return math.sqrt(sum(r["n"] * (pred(r) - r[key]) ** 2 for r in rows) / weight)


def chi_square(rows, key: str, pred) -> float:
    """Systematic bias in an expectation, band by band."""
    total = 0.0
    for lo, hi in BANDS:
        sel = [r for r in rows if lo <= r["spread"] < hi]
        if len(sel) < MIN_BAND:
            continue
        weight = sum(r["n"] for r in sel)
        if weight <= 0:
            continue
        obs = wmean(sel, key)
        exp = sum(r["n"] * pred(r) for r in sel) / weight
        var = sum(r["n"] * (r[key] - obs) ** 2 for r in sel) / weight
        se2 = var / len(sel)
        if se2 > 0:
            total += (obs - exp) ** 2 / se2
    return total


def held_out(rows, key: str, make, score):
    """Leave-one-season-out, pooled over every season that can be held."""
    seasons = sorted({r["season"] for r in rows})
    total, weight = 0.0, 0.0
    for season in seasons:
        train = [r for r in rows if r["season"] != season]
        test = [r for r in rows if r["season"] == season]
        if len(train) < MIN_TRAIN or len(test) < MIN_TEST:
            continue
        pred = make(train, key)
        if pred is None:
            continue
        w = sum(r["n"] for r in test)
        total += score(test, key, pred) * w
        weight += w
    if not weight:
        return None
    return total / weight


def between_games(conn, sport: str) -> list:
    """One row per team-game: what is this TEAM worth in touchdowns?"""
    lines = team_lines(conn, sport)
    implied = team_implied(conn, sport)
    tds = team_touchdowns(conn, sport, lines)
    # A team-game with no logged touchdown on EITHER side is a missing
    # feed, not a shutout, and counting it as a zero would drag every
    # expectation down. Keep the genuine zeroes, drop the unplayed games.
    played = {(s, p) for (s, p, _t) in tds if tds[(s, p, _t)] > 0}
    rows = []
    for key, spread in lines.items():
        if (key[0], key[1]) not in played:
            continue
        rows.append({"season": key[0], "team": key[2],
                     "spread": max(-LEAD_CAP, min(LEAD_CAP, spread)),
                     "implied": implied[key], "tds": tds.get(key, 0.0),
                     "n": 1.0})
    return rows


def within_team(conn, sport: str, group: str) -> list:
    """One row per team-game: the lead player's share of its touchdowns."""
    lines = team_lines(conn, sport)
    team_td = team_touchdowns(conn, sport, lines)
    lead = lead_players(conn, sport, group)
    mine = player_touchdowns(conn, sport, lead, lines)
    rows = []
    for key, spread in lines.items():
        total = team_td.get(key, 0.0)
        if total < 1:                 # no split to measure
            continue
        rows.append({"season": key[0],
                     "spread": max(-LEAD_CAP, min(LEAD_CAP, spread)),
                     "n": total, "share": mine.get(key, 0.0) / total})
    return rows


def report_between(rows, sport: str) -> list:
    out = [f"=== {sport.upper()} between games — {len(rows)} team-games"]
    if len(rows) < MIN_TRAIN:
        return out + ["  too few team-games to measure"]
    mean = wmean(rows, "tds")
    out.append(f"  offensive TDs per team-game: {mean:.2f}")

    def const(train, key):
        m = wmean(train, key)
        return lambda r: m

    def fitted(feats):
        def make(train, key):
            coef = wls(train, key, lambda r: [1.0] + [f(r) for f in feats])
            if coef is None:
                return None
            return lambda r: coef[0] + sum(
                c * f(r) for c, f in zip(coef[1:], feats))
        return make

    imp = lambda r: r["implied"]                              # noqa: E731
    spr = lambda r: r["spread"]                               # noqa: E731
    for label, make in (("nothing but the mean", const),
                        ("implied total", fitted([imp])),
                        ("implied total + spread", fitted([imp, spr]))):
        got = held_out(rows, "tds", make, rmse)
        out.append(f"    {label:<26} held-out RMSE "
                   + (f"{got:.4f}" if got is not None else "n/a"))
    out.append("  (the spread cannot add anything here and should not: "
               "implied total IS (total - spread) / 2)")
    return out


def report_within(rows, sport: str, group: str) -> list:
    label = "back" if group == "RB" else "receiver"
    out = [f"=== {sport.upper()} lead {label} — {len(rows)} team-games, "
           f"share {wmean(rows, 'share'):.3f}"]
    if len(rows) < MIN_TRAIN:
        return out + ["  too few team-games to measure"]

    def flat(train, key):
        m = wmean(train, key)
        return lambda r: m

    def ship(train, key):
        # The multiplier claims a RATIO, so put it on the share scale
        # using the training mean — otherwise this scores its level.
        m = wmean(train, key)
        w = sum(r["n"] for r in train)
        z = sum(r["n"] * shipped_multiplier(sport, r["spread"], group)
                for r in train) / w
        return lambda r: m * shipped_multiplier(sport, r["spread"], group) / z

    def two_sided(train, key):
        coef = wls(train, key, lambda r: [1.0, min(r["spread"], 0.0),
                                          max(r["spread"], 0.0)])
        if coef is None:
            return None
        return lambda r: (coef[0] + coef[1] * min(r["spread"], 0.0)
                          + coef[2] * max(r["spread"], 0.0))

    scores = {}
    for name, make in (("no script at all", flat), ("SHIPPED curve", ship),
                       ("fitted two-sided", two_sided)):
        scores[name] = held_out(rows, "share", make, chi_square)
    best = min((k for k, v in scores.items() if v is not None),
               key=lambda k: scores[k], default=None)
    for name, got in scores.items():
        mark = "   <-- best" if name == best else ""
        out.append(f"    {name:<20} held-out chi-square "
                   + (f"{got:8.1f}{mark}" if got is not None else "n/a"))
    if best == "no script at all":
        out.append("  THE SHIPPED CURVE IS WORSE THAN NO CURVE on the "
                   "population it is applied to — that is a real finding")
    return out


def report(sport: str, db_path=None) -> list:
    conn = sqlite3.connect(str(db_path or DEFAULT_DB))
    try:
        lines = report_between(between_games(conn, sport), sport)
        for group in ("RB", "WR"):
            lines.append("")
            lines.extend(report_within(within_team(conn, sport, group),
                                       sport, group))
        return lines
    finally:
        conn.close()


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    sports = args or ["nfl", "cfb"]
    for i, sport in enumerate(sports):
        if i:
            print()
        for line in report(sport):
            print(line)
    return 0


if __name__ == "__main__":                                # pragma: no cover
    raise SystemExit(main())
