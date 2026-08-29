"""Fit the recency dial against a book's number, not against our own.

THE CIRCULARITY THIS REMOVES. `engine.formfit` picks a market's recency
curve by grid-searching `logwalk.walk`, which prices every game against
`logwalk._naive_line` — the player's own trailing average. So the
question it answers is "which look-back windows best predict a number
computed from those same look-back windows", and the hot end of the
family wins because it is nearest to being the same object. Measured on
the droplet, `nfl:rush_yds` and `nfl:rec_yds` both ran the dial to +1.0
and adopted the hot anchor; `receptions` (-0.6) and `pass_yds` (-0.5)
landed inside. The first two are exactly the markets shut for AUC 0.47
against a real book. The dial was answering honestly. The question was
wrong.

`engine.propcal` made this same repair for the calibrations, and the
temperature that came back was a different number entirely. This is that
repair one layer down, for the curve the calibration is applied to.

WHY IT DOES NOT REPLAY THE SEASON. propcal costs nine minutes because it
rebuilds a slate per week; twenty-one dial settings that way is over
three hours. But scoring a dial against a close needs only three things
— the games already played, the number the book hung, and what happened
— so this joins the game logs to `odds_history` directly and evaluates
every dial setting in one pass over the pairs. Minutes, not hours, which
is what makes it a thing anyone will actually re-run.

The join is on the PLAYER'S OWN GAME DATE, from the schedule, keyed by
team: a week holds a Thursday, a Sunday and a Monday, and those are
three different closes.

WHAT IT REPORTS, and the order matters. Brier picks the dial, because
that is what `formfit` optimises and the two must be comparable. But AUC
decides whether the answer is worth anything: a curve can be beautifully
calibrated about a ranking it cannot do, and ordering is what a prop bet
needs. A dial whose best Brier still leaves AUC at 0.5 has found the
least-wrong way to know nothing.

Standard library only.
"""

from __future__ import annotations

import math

#: Prior games in the same season before a player-week can be scored.
MIN_HISTORY = 3

#: Book-priced pairs a market needs before its dial means anything.
#: Matches `propcal.MIN_BOOK_PAIRS` — the same evidence bar for the same
#: kind of claim.
MIN_PAIRS = 400

MARKETS = ("rush_yds", "rec_yds", "receptions", "pass_yds")


def game_dates(seasons=None) -> dict:
    """``{(season, week, team): 'YYYY-MM-DD'}`` from the schedule feed."""
    from .sources.nflverse import load_schedules, _s
    out: dict = {}
    for r in load_schedules():
        try:
            season, week = int(_s(r, "season")), int(_s(r, "week"))
        except (TypeError, ValueError):
            continue
        if seasons and season not in seasons:
            continue
        date = (_s(r, "gameday") or "")[:10]
        if not date:
            continue
        for side in ("home_team", "away_team"):
            team = _s(r, side)
            if team:
                out[(season, week, team)] = date
    return out


def _logs(conn, market: str, seasons=None) -> list:
    """``[(season, week, player, team, opponent, value)]`` in time order."""
    sql = ("SELECT season, period, player, team, opponent, value "
           "FROM player_game_logs WHERE sport='nfl' AND market=? ")
    args: list = [market]
    if seasons:
        sql += "AND season IN (%s) " % ",".join("?" * len(seasons))
        args.extend(seasons)
    sql += "ORDER BY season, period, player"
    out = []
    for r in conn.execute(sql, args):
        try:
            week = int(r["period"])
        except (TypeError, ValueError):
            continue
        if r["value"] is None:
            continue
        out.append((int(r["season"]), week, r["player"], r["team"] or "",
                    r["opponent"] or "", float(r["value"])))
    return out


def pairs_for(conn, market: str, seasons=None, min_history: int = MIN_HISTORY,
              dates: dict | None = None) -> list:
    """``[(history, career, vs_opp, line, went_over)]`` on real closes.

    Everything a dial needs to be scored, and nothing that depends on
    which dial is being scored — so the expensive join happens once and
    all twenty-one settings read the same list.
    """
    from . import db as _db
    closes = _db.closing_odds_by_date(conn, "nfl", market)
    if not closes:
        return []
    if dates is None:
        dates = game_dates(seasons)
    # The SAME normaliser `backtest.apply_real_lines` uses, not a third
    # one. `db.closing_odds_by_date` keys on the raw harvested name and
    # the backtest looks it up with this — the two line up only because
    # the harvester normalises on write, so a second spelling here would
    # silently match nothing and read as "no closes stored".
    from .backtest import _norm

    out: list = []
    seen: dict = {}
    career: dict = {}
    versus: dict = {}
    season_now = None
    for season, week, player, team, opponent, actual in _logs(
            conn, market, seasons):
        if season != season_now:
            for (p, _s), vals in seen.items():
                career.setdefault(p, []).extend(vals)
            seen, season_now = {}, season
        hist = seen.get((player, season)) or []
        date = dates.get((season, week, team))
        quote = closes.get((_norm(player), date)) if date else None
        if quote and len(hist) >= min_history:
            try:
                line = float(quote["line"])
            except (KeyError, TypeError, ValueError):
                line = None
            # A push decided nothing and carries no outcome to learn from,
            # the same exclusion propcal.book_pairs makes.
            if line is not None and actual != line:
                out.append((list(hist), list(career.get(player, [])),
                            list(versus.get((player, opponent), [])),
                            line, int(actual > line)))
        seen.setdefault((player, season), []).insert(0, actual)
        versus.setdefault((player, opponent), []).append(actual)
    return out


def _prob(hist, career, vs_opp, line, market, weights) -> float | None:
    """P(over) under one dial setting, the way the engine computes it."""
    from .form import compute_form
    from .models import GameLog
    from .projection import CV_FLOOR
    from .statmath import prob_over

    logs = [GameLog(week=0, opponent="", value=v) for v in hist]
    car = (sum(career) / len(career)) if career else None
    opp = (sum(vs_opp) / len(vs_opp)) if vs_opp else None
    if car is None:
        car = sum(hist) / len(hist) if hist else 0.0
    form = compute_form(logs, car, opp, weights=weights)
    mean = form.mean
    # Mirrors projection.build_projection: the log-derived spread alone is
    # too smooth to price a prop, so a market-typical floor sits under it.
    std = max(form.std, CV_FLOOR.get(market, 0.35) * max(mean, 1.0))
    if std <= 0:
        return None
    return prob_over(line, mean, std)


def _auc(pairs: list) -> dict:
    """AUC with its standard error — `propcal.discrimination`, not a
    second copy of it. Two implementations of one statistic is how they
    drift, and this file already exists because a measurement drifted
    from the thing it was supposed to describe."""
    from .propcal import discrimination
    return discrimination(pairs)


def scan(conn, market: str, seasons=None, min_pairs: int = MIN_PAIRS,
         dates: dict | None = None, log=None) -> dict:
    """Score every dial setting against real closes."""
    from .formfit import GRID, base_for, family

    rows = pairs_for(conn, market, seasons, dates=dates)
    if len(rows) < min_pairs:
        return {"market": market, "n": len(rows),
                "skipped": f"{len(rows)} book-priced pairs, needs {min_pairs}"}
    base = base_for("nfl")
    out = {"market": market, "n": len(rows), "dial": {}}
    for r in GRID:
        weights = family(base, r)
        scored = []
        for hist, career, vs_opp, line, over in rows:
            p = _prob(hist, career, vs_opp, line, market, weights)
            if p is not None:
                scored.append((p, over))
        if not scored:
            continue
        brier = sum((p - o) ** 2 for p, o in scored) / len(scored)
        g = _auc(scored)
        out["dial"][r] = {"brier": brier, "n": len(scored),
                          "auc": g.get("auc"), "z": g.get("z")}
        if log:
            log(f"    {market} dial {r:+.1f}: Brier {brier:.4f} "
                f"AUC {g.get('auc', 0.5):.3f} (z={g.get('z', 0):+.1f})")
    if not out["dial"]:
        return {"market": market, "n": len(rows),
                "skipped": "no dial setting could be scored"}
    best = min(out["dial"], key=lambda r: out["dial"][r]["brier"])
    top = max(out["dial"], key=lambda r: out["dial"][r]["auc"] or 0.0)
    out["best_brier_r"] = best
    out["best_auc_r"] = top
    return out


def report_lines(out: dict) -> list:
    """One market's dial, and whether the answer is worth having."""
    if out.get("skipped"):
        return [f"  {out['market']}: skipped — {out['skipped']}"]
    d = out["dial"]
    best, top = out["best_brier_r"], out["best_auc_r"]
    lines = [f"  {out['market']}: {out['n']:,} book-priced pairs"]
    lines.append(f"      best Brier at dial {best:+.1f} "
                 f"({d[best]['brier']:.4f}, AUC {d[best]['auc']:.3f})")
    lines.append(f"      best AUC   at dial {top:+.1f} "
                 f"({d[top]['auc']:.3f}, Brier {d[top]['brier']:.4f})")
    # THE NUMBER THAT DECIDES WHETHER ANY OF THIS MATTERS. A dial can
    # find the least-wrong way to know nothing: Brier improves as the
    # projection is dragged toward the line while the ordering it needs
    # to actually pick a side stays at a coin.
    #
    # Judged by z and not by a bare AUC threshold. On 660 synthetic pairs
    # with outcomes independent of everything, the best of twenty-one
    # dials read 0.537 — over a hardcoded 0.52 bar and 1.6 standard
    # errors from nothing. Taking the max of twenty-one noisy numbers
    # flatters itself, and a fixed cutoff cannot see that.
    if abs(d[top].get("z") or 0.0) < 2.0:
        lines.append("      ⚠️  no dial setting orders this market to "
                     "significance — the recency curve is not what is "
                     "wrong with it")
    elif best != top:
        lines.append(f"      note: Brier and AUC disagree; ordering is what "
                     f"a prop needs, so {top:+.1f} is the honest read")
    return lines


__all__ = ["MARKETS", "MIN_PAIRS", "MIN_HISTORY", "game_dates", "pairs_for",
           "scan", "report_lines"]
