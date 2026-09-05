"""Fit the basketball tuning to a league's OWN results.

`engine.hoops` says it plainly: the WNBA inherits the NBA's fitted numbers
— margin SD and the per-stat spreads — because there was no WNBA sample to
fit them against. That was true when it was written. It stopped being true
when the WNBA backfill landed 1,576 games and 151,765 player logs, and an
inherited number that could now be measured is just a wrong number with a
good excuse.

Two constants are directly measurable and both matter:

* **margin_sd** — how far a game's margin lands from what the ratings
  projected. It sets every moneyline and spread probability, and the two
  leagues are not the same: a 40-minute game with 12-woman rosters does
  not have an NBA game's spread.
* **sd_cv** — the coefficient of variation of each stat, per league. It is
  the width of every prop distribution on the board. Rebounds in a
  40-minute game are not rebounds in a 48-minute one.

What this deliberately does NOT do is flip `calibrated`. Fitting the
constants and earning the right to bet are different claims: the first
says our numbers describe this league, the second says our PICKS have been
graded against real prices in it. Probation is about the second, and only
the journal's promotion bar can lift it. Fitting the numbers makes a
probation model better; it does not end probation.
"""

from __future__ import annotations

import math
from dataclasses import replace

from . import teamrates
from .hoops import LEAGUES, LeagueTuning

# Below these, a fit is noise dressed as a measurement and the inherited
# number is the better answer. A season is ~44 WNBA games a team; 200
# games is several seasons of margins, and 400 lines of a stat is enough
# to see its shape.
MIN_GAMES = 200
MIN_STAT_ROWS = 400

# The stats whose spread the prop model reads.
STATS = ("pts", "reb", "ast", "pra", "fg3m", "stl", "blk")


def _sd(values: list[float]) -> float | None:
    """Sample SD, or None when there is no sample.

    None rather than 0.0 on purpose — see engine/cfb/ratings.py, where
    that exact conflation let a prior report itself as a fitted number for
    every college game on the board.
    """
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def fit_margin_sd(conn, league: str, seasons: list[int] | None = None
                  ) -> tuple[float | None, int]:
    """(SD of margin around the ratings' projection, games used)."""
    rates = teamrates.compute_team_ratings(conn, league, seasons=seasons,
                                           shrink=4.0)
    if not rates:
        return None, 0
    q = ("SELECT home, away, home_score, away_score FROM games "
         "WHERE sport=? AND home_score IS NOT NULL AND away_score IS NOT NULL")
    args: list = [league]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    res = []
    for r in conn.execute(q, args):
        hr, ar = rates.get(r["home"]), rates.get(r["away"])
        if not hr or not ar:
            continue
        res.append((float(r["home_score"]) - float(r["away_score"]))
                   - (hr.net - ar.net))
    return _sd(res), len(res)


def fit_stat_cvs(conn, league: str, seasons: list[int] | None = None,
                 min_games: int = 12) -> tuple[dict, dict]:
    """({stat: cv}, {stat: rows}) from this league's own player logs.

    The CV is measured PER PLAYER and then averaged, not pooled across the
    league. Pooling would measure how different players are from each
    other — a star and a bench end have wildly different rebound means —
    when the number the model needs is how much ONE player's line moves
    game to game. Those are different quantities and the pooled one is
    much larger, which would widen every distribution and quietly kill
    every edge on the board.
    """
    by_player: dict[tuple, list] = {}
    q = ("SELECT player, market, value FROM player_game_logs "
         "WHERE sport=? AND market IN (%s)"
         % ",".join("?" * (len(STATS) + 1)))
    args: list = [league, *STATS, "min"]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    for r in conn.execute(q, args):
        by_player.setdefault((r["player"], r["market"]), []).append(
            float(r["value"]))

    # PRA is the sum of three columns we already store; deriving it here
    # keeps the history and the line referring to the same three numbers.
    pra: dict[str, list] = {}
    for (player, market), vals in list(by_player.items()):
        if market in ("pts", "reb", "ast"):
            pra.setdefault(player, [])
    for player in pra:
        parts = [by_player.get((player, m)) for m in ("pts", "reb", "ast")]
        if all(parts) and len({len(p) for p in parts}) == 1:
            pra[player] = [a + b + c for a, b, c in zip(*parts)]
    for player, vals in pra.items():
        if vals:
            by_player[(player, "pra")] = vals

    cvs: dict[str, float] = {}
    counts: dict[str, int] = {}
    for stat in STATS:
        per_player = []
        rows = 0
        for (player, market), vals in by_player.items():
            if market != stat or len(vals) < min_games:
                continue
            mean = sum(vals) / len(vals)
            sd = _sd(vals)
            rows += len(vals)
            # A player who never records the stat has no spread to measure,
            # and dividing by ~0 would manufacture an enormous CV.
            if sd is not None and mean > 0.5:
                per_player.append(sd / mean)
        counts[stat] = rows
        if len(per_player) >= 10 and rows >= MIN_STAT_ROWS:
            per_player.sort()
            mid = len(per_player) // 2
            # Median, not mean: one player with a freak season should not
            # set the width of every distribution in the league.
            cvs[stat] = round(per_player[mid] if len(per_player) % 2
                              else (per_player[mid - 1] + per_player[mid]) / 2,
                              3)
    return cvs, counts


def fitted_tuning(conn, league: str, seasons: list[int] | None = None
                  ) -> tuple[LeagueTuning, dict]:
    """This league's tuning with whatever we could measure swapped in.

    Returns ``(tuning, report)``. Anything not measurable keeps the
    inherited value, and the report names exactly which is which — an
    inherited number and a fitted one must never be indistinguishable on
    the page.
    """
    base = LEAGUES.get(league, LEAGUES["nba"])
    report: dict = {"league": league, "fitted": [], "inherited": [],
                    "games": 0, "stat_rows": {}}

    changes: dict = {}
    sd, n = fit_margin_sd(conn, league, seasons)
    report["games"] = n
    if sd is not None and n >= MIN_GAMES:
        changes["margin_sd"] = round(sd, 2)
        report["fitted"].append(f"margin_sd {base.margin_sd} → {sd:.2f} "
                                f"(from {n} games)")
    else:
        report["inherited"].append(
            f"margin_sd {base.margin_sd} — {n} games, need {MIN_GAMES}")

    cvs, counts = fit_stat_cvs(conn, league, seasons)
    report["stat_rows"] = counts
    merged = dict(base.sd_cv)
    # Every stat is accounted for either way. A report that collapses to
    # "not enough logs" when nothing fits tells you less than one naming
    # each gap and its row count — and the gaps are the actionable half.
    for stat in STATS:
        if stat in cvs:
            report["fitted"].append(
                f"sd_cv[{stat}] {merged.get(stat)} → {cvs[stat]} "
                f"({counts.get(stat, 0)} rows)")
            merged[stat] = cvs[stat]
        else:
            report["inherited"].append(
                f"sd_cv[{stat}] {base.sd_cv.get(stat)} — "
                f"{counts.get(stat, 0)} rows, need {MIN_STAT_ROWS}")
    if cvs:
        changes["sd_cv"] = merged

    if not changes:
        return base, report
    # `calibrated` is deliberately untouched. Fitting the constants says
    # our numbers describe this league; probation is about whether our
    # PICKS have been graded against real prices in it. Only the journal's
    # promotion bar answers the second, and a better model does not get to
    # award itself the first.
    note = base.note
    if report["fitted"]:
        note = note + " " + fitted_sentence(report)
    return replace(base, note=note, **changes), report


def fitted_sentence(report: dict) -> str:
    """One sentence for the PAGE. The detail belongs in the terminal.

    The report's lines are written for a developer reading a build log —
    "sd_cv[pts] 0.3 → 0.84 (29662 rows); sd_cv[reb] 0.4 → 0.811 (29662
    rows); ..." — and they were being concatenated straight into the note
    that renders on the board. Six variable names and their row counts in a
    paragraph a bettor is meant to read is not transparency, it is a log
    file with a border around it, and it is exactly what "machine-made"
    looks like on a page.

    So: say how many numbers are now measured, on how much, and what that
    does and does not buy. `describe()` below still prints every line for
    whoever is actually debugging the fit.
    """
    n_fit = len(report["fitted"])
    games = report.get("games") or 0
    rows = max((report.get("stat_rows") or {}).values(), default=0)
    on = []
    if games:
        on.append(f"{games:,} games")
    if rows:
        on.append(f"{rows:,} player games")
    where = f" from {' and '.join(on)}" if on else ""
    is_are = "is" if n_fit == 1 else "are"
    return (f"UPDATE: {n_fit} of these constants {is_are} now measured"
            f"{where or ''} of this league's own results rather than "
            f"borrowed. That makes the numbers this league's; it does not "
            f"make the picks proven, which is what probation is about.")


def describe(report: dict) -> str:
    lines = [f"{report['league'].upper()} tuning — "
             f"{len(report['fitted'])} fitted, "
             f"{len(report['inherited'])} inherited"]
    for line in report["fitted"]:
        lines.append(f"  ✅ {line}")
    for line in report["inherited"]:
        lines.append(f"  ↩︎  {line}")
    return "\n".join(lines)
