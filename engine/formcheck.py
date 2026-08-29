"""Does the base projection beat a trailing average at predicting the stat?

THE QUESTION THE AUC LEFT BEHIND. `engine.propcal` measured the NFL prop
markets against real harvested closes and found rush_yds at AUC 0.479 and
rec_yds at 0.468 — the model does not rank a hit above a miss at a book's
number. A temperature cannot fix an ordering, so that result sends the
work back to the projection itself.

But "cannot beat a book" and "knows nothing" are different failures, and
the first does not imply the second. A book line is a strong opponent;
losing to it is ordinary. So this asks the weaker, prior question that
needs no odds at all: does `engine.form.compute_form` — the base every
multiplier in `engine.projection` is applied to — predict the actual
number better than the trailing average it is built from?

If it does not, the multipliers are decorating noise and the prop model
needs rebuilding rather than retuning. If it does, the base carries
information that something downstream is losing, and the search moves to
what sits between the two.

WALK-FORWARD BY CONSTRUCTION. A predictor for week W sees only weeks
before W in the same season, plus prior seasons for the career anchor.
This is the same discipline `propcal.walk_forward_brier` applies for the
same reason: the pairs arrive in time order and anything else leaks.

NO ODDS ARE READ. That is the point — this container has none, and a
measurement priced against a proxy line is what produced the bug this
whole line of work exists to undo. Predicting the stat is a question the
game logs can answer on their own.

Standard library only.
"""

from __future__ import annotations

import math

#: Games of in-season history a player-week needs before it is scored. A
#: predictor with one prior game is measuring the log's noise, not the
#: model — and `compute_form`'s own windows do not separate until there
#: are a few.
MIN_HISTORY = 3

#: Weeks of opportunity that define "the role he holds now". Short on
#: purpose — a role change is the event worth catching.
VOLUME_WINDOW = 4

#: Season opportunities an efficiency rate needs before it means
#: anything. Mirrors `nflusage.MIN_EFF_OPPS`, loosened because this walks
#: from week 4 rather than pricing a live card.
MIN_OPPORTUNITIES = 10

#: The markets with a prop board behind them. `anytime_td` is binary and
#: belongs to `engine.tdbacktest`, not here.
MARKETS = ("rush_yds", "rec_yds", "receptions", "pass_yds")

#: A long-window control curve, shaped like the two NFL markets whose
#: fitted weights actually beat a season average. Not a proposal — a
#: control, so the curve can be told apart from everything else the
#: projection does.
GENTLE = {
    "last1": 0.09,
    "last3": 0.16,
    "last5": 0.14,
    "last10": 0.22,
    "season": 0.25,
    "career": 0.07,
    "vs_opp": 0.07,
}


#: The opportunity behind each outcome. Yards are not a quantity a player
#: produces directly — they are chances times what he does with each, and
#: the two halves behave nothing alike (see `volume_predictor`).
OPPORTUNITY = {
    "rush_yds": "carries",
    "rec_yds": "targets",
    "receptions": "targets",
    "pass_yds": "pass_att",
}


def _rows(conn, market: str, seasons=None) -> list:
    """``[(season, week, player, opponent, value, opp)]`` in time order.

    ``opp`` is that game's opportunity count for the market (carries for
    rushing, targets for receiving), or None where it was not logged.
    """
    opp_market = OPPORTUNITY.get(market)
    sql = ("SELECT season, period, player, opponent, market, value "
           "FROM player_game_logs WHERE sport='nfl' AND market IN (?, ?) ")
    args: list = [market, opp_market or market]
    if seasons:
        sql += "AND season IN (%s) " % ",".join("?" * len(seasons))
        args.extend(seasons)
    sql += "ORDER BY season, period, player"
    merged: dict = {}
    order: list = []
    for r in conn.execute(sql, args):
        try:
            week = int(r["period"])
        except (TypeError, ValueError):
            continue
        if r["value"] is None:
            continue
        key = (int(r["season"]), week, r["player"], r["opponent"] or "")
        if key not in merged:
            merged[key] = [None, None]
            order.append(key)
        slot = 1 if (opp_market and r["market"] == opp_market
                     and market != opp_market) else 0
        merged[key][slot] = float(r["value"])
    return [(k[0], k[1], k[2], k[3], merged[k][0], merged[k][1])
            for k in order if merged[k][0] is not None]


def _mean(vals) -> float | None:
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def volume_predictor(history: list, opps: list) -> float | None:
    """Opportunities times efficiency, forecast apart.

    THE DECOMPOSITION THE FORM BLEND THROWS AWAY. Rushing yards are not a
    quantity a player emits; they are carries times what he does with
    each. Those two halves could hardly behave less alike:

      * OPPORTUNITY is role. Who gets the carries is a coaching decision
        that persists week to week, and it is the thing that actually
        changes when a starter goes down — which is most of what moves a
        prop line.
      * EFFICIENCY is close to noise. Yards per carry swings wildly on a
        handful of touches, and last week's 6.1 says very little about
        this week's.

    Smoothing the PRODUCT applies one recency curve to both, which is
    necessarily wrong for at least one of them: fast enough to track a
    role change is far too fast for efficiency, and slow enough to
    stabilise efficiency cannot see the role change at all. That is a
    plausible reason `rush_yds` and `rec_yds` measured AUC 0.47 against
    real closes while `receptions` — whose outcome IS nearly its own
    opportunity, so the decomposition is already half done — measured
    0.564 and carries the only edge on the board.

    So: recent opportunities (short window, it is a role) times
    season-long efficiency (long window, it is a rate).
    """
    if not opps or len(opps) < 2:
        return None
    recent = [o for o in opps[:VOLUME_WINDOW] if o is not None]
    if not recent:
        return None
    opp_now = sum(recent) / len(recent)
    total_opp = sum(o for o in opps if o is not None)
    if total_opp < MIN_OPPORTUNITIES:
        # An efficiency measured over three touches is one screen pass
        # wearing a trend costume. No estimate beats a bad one.
        return None
    paired = [(v, o) for v, o in zip(history, opps) if o is not None]
    produced = sum(v for v, _o in paired)
    eff = produced / total_opp
    return opp_now * eff


def predictors(history: list, career: list, vs_opp: list,
               weights: dict | None, opps: list | None = None) -> dict:
    """Every candidate's number for one player-week.

    ``history`` is this season's prior values, MOST RECENT FIRST — the
    order `compute_form` documents and the order its windows assume.
    """
    from .form import compute_form
    from .models import GameLog

    out = {
        "last1": history[0],
        "last3": _mean(history[:3]),
        "last5": _mean(history[:5]),
        "season": _mean(history),
    }
    logs = [GameLog(week=0, opponent="", value=v) for v in history]
    form = compute_form(logs, _mean(career) or _mean(history),
                        _mean(vs_opp), weights=weights)
    out["form"] = form.mean
    # The same blend under the GENTLE curve, as a control. receptions and
    # pass_yds were fitted to something close to this and beat their
    # baselines; rush_yds was fitted to a hard recency tilt and rec_yds
    # fell back to the hard-coded default, and both lose to a plain
    # season average. This isolates the curve from everything else.
    gentle = compute_form(logs, _mean(career) or _mean(history),
                          _mean(vs_opp), weights=GENTLE)
    out["gentle"] = gentle.mean
    if opps is not None:
        vol = volume_predictor(history, opps)
        if vol is not None:
            out["volume"] = vol
            # Half the decomposition, half the smoothing. The blend is
            # what `projection.build_projection` already does live via
            # its usage bridge, so measuring it here says whether that
            # bridge is worth what it costs.
            out["vol_blend"] = 0.5 * vol + 0.5 * (out["gentle"] or vol)
    return out


def run(conn, market: str, seasons=None, min_history: int = MIN_HISTORY,
        log=None) -> dict:
    """Score every candidate over every eligible player-week."""
    from .formfit import weights_for
    weights = weights_for("nfl", market)
    rows = _rows(conn, market, seasons)
    if not rows:
        return {"market": market, "n": 0,
                "skipped": "no game logs for this market"}

    seen: dict = {}          # (player, season) -> [values, most recent first]
    seen_opp: dict = {}      # the same, for the opportunity behind each
    career: dict = {}        # player -> every value from EARLIER seasons
    versus: dict = {}        # (player, opponent) -> values before this game
    rows_kept: list = []     # (season, week, {name: pred}, actual)
    season_now = None
    scored = 0

    for season, week, player, opponent, actual, opp in rows:
        if season != season_now:
            # A new season starts every player's in-season log empty, and
            # folds the finished one into the career anchor. Doing this on
            # the season boundary rather than per row is what keeps the
            # career average from containing the game being predicted.
            for (p, _s), vals in seen.items():
                career.setdefault(p, []).extend(vals)
            seen, seen_opp, season_now = {}, {}, season
        hist = seen.get((player, season)) or []
        opps = seen_opp.get((player, season)) or []
        if len(hist) >= min_history:
            preds = predictors(hist, career.get(player, []),
                               versus.get((player, opponent), []), weights,
                               opps=opps)
            rows_kept.append((season, week, preds, actual))
            scored += 1
        seen.setdefault((player, season), []).insert(0, actual)
        seen_opp.setdefault((player, season), []).insert(0, opp)
        versus.setdefault((player, opponent), []).append(actual)
        if log and scored and scored % 20000 == 0:
            log(f"    {market}: {scored:,} player-weeks scored")

    # THE COMMON SUBSET, and nothing else is comparable.
    #
    # `volume` returns None below MIN_OPPORTUNITIES, so on rush_yds it
    # prices only the ~33% of rows belonging to actual ball-carriers,
    # while every other candidate is also scored on ~6,000 receivers
    # whose rushing yards are zero and for whom predicting zero is free.
    # Scored on their own rows the two are not in the same contest:
    # measured that way `volume` read MAE 19.89 against `gentle`'s 7.34,
    # which says nothing at all about the model and everything about
    # which rows each one was handed.
    names = sorted({n for _s, _w, preds, _a in rows_kept for n in preds})
    usable = [r for r in rows_kept
              if all(r[2].get(n) is not None for n in names)]
    err: dict = {n: [] for n in names}
    sq: dict = {n: [] for n in names}
    by_week: dict = {}
    for season_, week_, preds, actual in usable:
        for name in names:
            e = preds[name] - actual
            err[name].append(abs(e))
            sq[name].append(e * e)
        by_week.setdefault((season_, week_), []).append((preds, actual))
    out = {"market": market, "n": scored, "compared_on": len(usable),
           "candidates": {}}
    if not usable:
        out["skipped"] = "no row carried every candidate"
        return out
    for name in names:
        out["candidates"][name] = {
            "n": len(usable),
            "mae": sum(err[name]) / len(usable),
            "rmse": math.sqrt(sum(sq[name]) / len(usable)),
            "rank": _mean_week_rank(by_week, name),
        }
    return out


def _mean_week_rank(by_week: dict, name: str) -> float | None:
    """Mean within-week Spearman between a candidate and the actual.

    MAE ANSWERS THE WRONG QUESTION FOR A PROP. A predictor that shades
    every player toward the league mean wins on average error while
    ordering nobody, and ordering is the whole job: a bet is a claim that
    THIS player beats THIS number, not that the league is well described.
    So the ordering is scored separately, within a week, where every
    player faced the same slate.
    """
    scores = []
    for rows in by_week.values():
        pairs = [(r[0].get(name), r[1]) for r in rows
                 if r[0].get(name) is not None]
        if len(pairs) < 8:
            continue
        rho = _spearman([p for p, _a in pairs], [a for _p, a in pairs])
        if rho is not None:
            scores.append(rho)
    return _mean(scores)


def _ranks(vals: list) -> list:
    """1-based ranks with ties averaged."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        shared = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = shared
        i = j + 1
    return out


def _spearman(xs: list, ys: list) -> float | None:
    """Pearson on the ranks, which handles the ties a formula cannot."""
    rx, ry = _ranks(xs), _ranks(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return num / (dx * dy) if dx and dy else None


def report_lines(out: dict) -> list:
    """One market's table, best rank first."""
    if out.get("skipped"):
        return [f"  {out['market']}: skipped — {out['skipped']}"]
    lines = [f"  {out['market']}: {out['n']:,} player-weeks, "
             f"{out.get('compared_on', out['n']):,} carrying every candidate "
             f"— the only rows any of these numbers compare on"]
    rows = sorted(out["candidates"].items(),
                  key=lambda kv: -(kv[1]["rank"] or -1))
    best = rows[0][0] if rows else ""
    form = (out["candidates"].get("form") or {}).get("rank")
    for name, d in rows:
        rank = "  n/a " if d["rank"] is None else f"{d['rank']:+.3f}"
        flag = "  <-- ours" if name == "form" else ""
        lines.append(f"      {name:<8} MAE {d['mae']:6.2f}   RMSE "
                     f"{d['rmse']:6.2f}   rank {rank}{flag}")
    if form is not None and best != "form":
        lines.append(f"      ⚠️  a plain '{best}' orders this market better "
                     f"than the fitted form blend does")
    return lines


__all__ = ["MARKETS", "MIN_HISTORY", "run", "report_lines", "predictors"]
