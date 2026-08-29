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


def home_teams(seasons=None) -> dict:
    """``{(season, week): home_team}`` per game, keyed for lookup by side.

    Kept apart from `game_dates` because that map is keyed by team and a
    team does not know from its own key whether it was hosting.
    """
    from .sources.nflverse import load_schedules, _s
    out: dict = {}
    for r in load_schedules():
        try:
            season, week = int(_s(r, "season")), int(_s(r, "week"))
        except (TypeError, ValueError):
            continue
        if seasons and season not in seasons:
            continue
        home, away = _s(r, "home_team"), _s(r, "away_team")
        if home:
            out[(season, week, home)] = 1
        if away:
            out[(season, week, away)] = 0
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
              dates: dict | None = None, keep_key: bool = False) -> list:
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
                row = (list(hist), list(career.get(player, [])),
                       list(versus.get((player, opponent), [])),
                       line, int(actual > line))
                out.append(((season, week, player, team, opponent),) + row
                           if keep_key else row)
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


#: Everything the game logs carry that could plausibly order a prop,
#: beyond the outcome's own history. Named per market because air yards
#: mean nothing to a runner and carries nothing to a receiver.
FEATURES = {
    "rush_yds": ("carries", "snap_pct", "rz_car", "i5_car", "xfp"),
    "rec_yds": ("targets", "air_yards", "snap_pct", "rz_tgt", "xfp"),
    "receptions": ("targets", "air_yards", "snap_pct", "rz_tgt", "xfp"),
    "pass_yds": ("pass_att",),
}


def _feature_logs(conn, markets, seasons=None) -> dict:
    """``{(season, week, short_key): {market: value}}`` for the features.

    KEYED BY `fantasy._short_key`, NOT BY THE NAME. `player_game_logs`
    holds two naming conventions in one table because it holds two feeds:
    the weekly box score writes "A.J. Brown" and the play-by-play
    aggregates write "A.Abdullah". Keyed on the raw name they never meet
    — measured, 6,321 carry rows and 5,384 red-zone rows for 2025 produced
    11,705 keys, which is exactly the sum, meaning zero overlap.

    That is how the first signal scan silently dropped rz_car, rz_tgt,
    i5_car and xfp — the four richest features and the ones the
    touchdown model leans on — and still reported "6 candidates tried"
    as though that were the whole field. `engine/nflusage` has always
    joined these through `_short_key`; this file did not.
    """
    if not markets:
        return {}
    from .fantasy import _short_key
    sql = ("SELECT season, period, player, team, market, value "
           "FROM player_game_logs WHERE sport='nfl' AND market IN (%s) "
           % ",".join("?" * len(markets)))
    args = list(markets)
    if seasons:
        sql += "AND season IN (%s) " % ",".join("?" * len(seasons))
        args.extend(seasons)
    out: dict = {}
    for r in conn.execute(sql, args):
        try:
            week = int(r["period"])
        except (TypeError, ValueError):
            continue
        if r["value"] is None:
            continue
        key = (int(r["season"]), week, _short_key(r["player"], r["team"] or ""))
        out.setdefault(key, {})[r["market"]] = float(r["value"])
    return out


def _recent(vals, n=4):
    got = [v for v in vals[:n] if v is not None]
    return sum(got) / len(got) if got else None


def schedule_context(dates: dict) -> dict:
    """``{(season, week, team): {"rest": days, "off_bye": 0/1}}``.

    Rest is days since that team's previous game, so a Thursday game off
    a Sunday reads 4 and a Monday-to-Sunday reads 13. A bye is inferred
    from the gap rather than from a bye table, because the gap is the
    thing that actually affects a body and it is right even when a team
    is coming off a postponement or a week 18 rest.
    """
    by_team: dict = {}
    for (season, week, team), date in dates.items():
        by_team.setdefault((season, team), []).append((week, date))
    out: dict = {}
    for (season, team), games in by_team.items():
        games.sort()
        prev = None
        for week, date in games:
            rest = None
            if prev:
                import datetime as _dt
                try:
                    rest = (_dt.date.fromisoformat(date)
                            - _dt.date.fromisoformat(prev)).days
                except ValueError:
                    rest = None
            out[(season, week, team)] = {
                "rest": rest,
                # 13 days clears a normal Sunday-to-Sunday week (7) and a
                # Monday-to-Sunday (13 exactly is the long end of normal),
                # so the bar sits above it.
                "off_bye": (1 if (rest is not None and rest > 13) else 0),
            }
            prev = date
    return out


def signal_scan(conn, market: str, seasons=None, min_pairs: int = MIN_PAIRS,
                dates: dict | None = None) -> dict:
    """Does ANYTHING we record order this market against a book?

    THE QUESTION LEFT WHEN THE DIAL ANSWERS NO. `scan` sweeps the recency
    family and, on rush_yds and rec_yds, no setting orders the outcome to
    significance — the best of twenty-one dials reached AUC 0.517 (z=0.9)
    and 0.508 (z=0.6). That closes the curve as a cause but not the
    market: a curve reweights the outcome's own history, and the book's
    number may simply already contain everything that history holds.

    So this scores the OTHER columns. Each candidate is a ranking over
    player-weeks, scored by AUC against whether the game beat the closing
    number. A raw feature knows nothing about the line, which is exactly
    what makes it a fair test of the book: if the market prices volume
    correctly then high-volume players go over half the time and the AUC
    sits at 0.5. A feature that clears it is one the book under-weights.

    Nothing here is a bet. It is the question of whether a bet is
    possible, asked before any more model is built on top.
    """
    from .fantasy import _short_key
    from .form import compute_form
    from .formfit import base_for
    from .models import GameLog

    feats = FEATURES.get(market, ())
    fl = _feature_logs(conn, feats, seasons)
    rows = pairs_for(conn, market, seasons, dates=dates, keep_key=True)
    if len(rows) < min_pairs:
        return {"market": market, "n": len(rows),
                "skipped": f"{len(rows)} book-priced pairs, needs {min_pairs}"}

    base = base_for("nfl")
    ctx = schedule_context(dates if dates is not None else game_dates(seasons))
    hosts = home_teams(seasons)
    cand: dict = {}
    for key, hist, career, vs_opp, line, over in rows:
        season, week, player, team, opponent = key
        logs = [GameLog(week=0, opponent="", value=v) for v in hist]
        car = (sum(career) / len(career)) if career else (
            sum(hist) / len(hist) if hist else 0.0)
        form = compute_form(logs, car, None, weights=base)
        vals = {
            # The signal the board actually uses, as the thing to beat.
            "proj_gap": form.mean - line,
            "season_gap": (sum(hist) / len(hist)) - line,
            "last3_gap": _recent(hist, 3) - line if hist else None,
            # THE FACTORS THE MODEL DECLARES BUT DOES NOT PRICE.
            # `vs_opponent_avg` carries a weight in the recency curve and
            # `sources/nflverse` passes None for every NFL prop, so
            # head-to-head history has never entered a projection. Rest
            # and the bye are computed by `engine/fatigue` for display
            # and by `engine/byes` for the draft board, and neither
            # reaches the price. Tested here rather than argued about.
            "vs_opp_gap": (_recent(vs_opp, 99) - line) if vs_opp else None,
            "rest_days": (ctx.get((season, week, team)) or {}).get("rest"),
            "off_bye": (ctx.get((season, week, team)) or {}).get("off_bye"),
            # Home/away is read today only to pick the SIGN of the spread
            # (`matchup.is_home`); it is not a factor on the player.
            "is_home": hosts.get((season, week, team)),
        }
        skey = _short_key(player, team)
        for f in feats:
            series = [fl.get((season, w, skey), {}).get(f)
                      for w in range(week - 1, 0, -1)]
            vals[f] = _recent(series)
            if f in ("carries", "targets", "pass_att"):
                # Role CHANGE, not role level: recent minus the season
                # behind it. A back who just took the job reads high here
                # while his own yardage history still reads like a backup.
                older = _recent(series[4:], 12)
                vals[f + "_trend"] = (
                    (vals[f] - older) if (vals[f] is not None
                                          and older is not None) else None)
        for name, v in vals.items():
            if v is not None:
                cand.setdefault(name, []).append((float(v), over))

    out = {"market": market, "n": len(rows), "signals": {}, "thin": {}}
    for name in sorted(set(cand) | set(feats)):
        pairs = cand.get(name) or []
        if len(pairs) < min_pairs:
            # NAMED, not skipped. A candidate that quietly vanishes makes
            # the list look like the whole field, and the count printed
            # underneath it becomes a lie about how many things were
            # tried. This is how the join bug above stayed invisible.
            out["thin"][name] = len(pairs)
            continue
        g = _auc(pairs)
        if g.get("ran"):
            out["signals"][name] = {"n": len(pairs), "auc": g["auc"],
                                    "z": g["z"]}
    return out


def signal_lines(out: dict) -> list:
    """Every candidate, strongest ordering first."""
    if out.get("skipped"):
        return [f"  {out['market']}: skipped — {out['skipped']}"]
    lines = [f"  {out['market']}: {out['n']:,} book-priced pairs"]
    rows = sorted(out["signals"].items(), key=lambda kv: -abs(kv[1]["z"]))
    for name, d in rows:
        mark = "  <-- what the board uses" if name == "proj_gap" else ""
        flag = "" if abs(d["z"]) < 2 else ("  ** orders it **" if d["z"] > 0
                                           else "  ** orders it BACKWARDS **")
        lines.append(f"      {name:<16} n={d['n']:<5} AUC {d['auc']:.3f}  "
                     f"z={d['z']:+.1f}{flag}{mark}")
    for name, n in sorted((out.get("thin") or {}).items()):
        lines.append(f"      {name:<16} n={n:<5} too few to score — not "
                     f"tested, not absent")
    if not any(abs(d["z"]) >= 2 for _n, d in rows):
        # MANY CANDIDATES, so the bar is not one z of 2. Said plainly
        # because the whole point of the scan is to stop work, and a
        # scan that always finds something cannot do that.
        lines.append(f"      nothing here orders this market — {len(rows)} "
                     f"candidates tried, none reaching z=2, and trying "
                     f"{len(rows)} makes even that a low bar")
    return lines


__all__ = ["MARKETS", "MIN_PAIRS", "MIN_HISTORY", "FEATURES", "game_dates",
           "home_teams", "schedule_context", "pairs_for", "scan",
           "report_lines", "signal_scan", "signal_lines"]
