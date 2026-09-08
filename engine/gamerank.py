"""Does the model RANK game outcomes? Measured, so the likelihood board can carry them.

Ethan, 2026-09-02: "all I see us is doing overs, but we have no unders,
and we also have no money lines or spreads or totals or anything like
that ... there is more bets that we can salvage."

The likelihood board's founding rule (engine/likely.py) is that a
market appears only once the model has been SHOWN to rank it — a
measured AUC over ingested history, not an argument. The prop markets
have theirs (`likely.RANK_AUC`, `engine.rankfit`). Game lines had none,
so they were never on the board. This measures them.

WHAT IS MEASURED. The same walk `engine.gamebacktest` replays — ratings
from games strictly before each date, the production pricers
(`gamebets.price_total`, `price_spread`, `price_moneyline`), the stored
closes — but instead of counting bets above the edge bar it keeps, for
EVERY quoted game, the probability the pricer put on the side it chose
and whether that side won. The AUC of those pairs is the question the
board asks: does a higher number mean a more likely winner? Pushes are
dropped (no outcome to rank against). A market under
`likely.MIN_RANK_AUC` stays off the board; the number is printed
either way.

    python3 -m engine.gamerank              # every sport with history
    python3 -m engine.gamerank --sport nfl
    python3 -m engine.gamerank --sport mlb --save   # into the rank store
    python3 -m engine.gamerank --sport nfl --raw-bar   # the raw-claim bar, measured

MEASURED 2026-09-02 on this repo's history (NFL 2021-25, CFB 2022-25):

    nfl  moneyline 0.6412 (1,181)   spread 0.4911   total 0.4968   team_total 0.5132
    cfb  moneyline 0.7522 (2,729)   spread 0.4963   total 0.5034   team_total 0.4917

RE-MEASURED 2026-09-07 after the NFL walk was found not to be one. An
NFL `period` is a week number that repeats every season, and two
readers assumed it was unique. The walk sorted the games `ORDER BY
period` — so it took week 1 of every season before week 2 of any, and
priced 2021's second week having already seen 2025's first. And the
schedule closes were keyed `(period, home, away)`, so a same-week
rematch a season apart shared a key and sixty-five games were graded
against another year's line. Ordered by season then period, and the
closes joined by season (`gamebacktest.close_for`), the same games give:

    nfl  moneyline 0.6332 (1,181)   spread 0.4807   total 0.4706   team_total 0.4815

Both faults flattered every NFL market and none of them changed side of
the floor. College was never affected: its period is a date.

AND THEN MEASURED ON THE MODEL THE BUILD SHIPS, the same day. The plain
walk above rates a team on every game it has ever played; `nfl_build`
prices from `teamrates.ratings_for_season`. `measure_nfl` walks that —
the college precedent — and it is the figure the board carries:

    nfl  moneyline 0.6773 (1,356)   spread 0.5036   total 0.4961   team_total 0.5002

Moneylines rank; nothing else does. Shipped as `likely.GAME_RANK_AUC`
(the ranked ones) and `likely.GAME_RANK_MEASURED` (the whole table —
the sub-floor markets are on the board as labelled leans since
2026-09-02, by Ethan's call). The college walk rebuilds the production
opponent-adjusted ratings before every date (`measure_cfb`); the plain
walk had put its moneyline at 0.7077 on 2,016 games.

`--save` writes each market the sample supports into `engine.rankfit`'s
store — `likely.rank_auc` reads that store FIRST — which is the only way
an MLB game market can reach the board: its history never leaves the
droplet. A market under MIN_GAMES retires its own stored entry, as the
prop fitter does, so a shelf never outlives its evidence.

Standard library only.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

from .gamebacktest import (SCORING_BASELINE, _rating, _settle_spread,
                           _settle_team_total, _settle_total, _split,
                           close_for, game_line_closes, moneyline_closes,
                           schedule_closes, schedule_moneylines)
from .gamebets import (game_margin, mlb_win_prob, nfl_win_prob,
                       price_spread, price_team_total, price_total,
                       project_team_points, project_total, _sd)
from .rankfit import auc

#: Minimum quoted games before an AUC is a claim. Game markets are one
#: row a game, so this is smaller than rankfit's prop floor, and it is
#: several seasons of a league.
MIN_GAMES = 400

CURVES = {"mlb": mlb_win_prob, "nfl": nfl_win_prob}


def prepare(conn, sport: str) -> str:
    """Register what a sport needs before its game markets can be priced.

    College football keeps its scoring baseline, variance and win curve
    in `engine.cfb.ratings` and pushes them into `gamebets` at build
    time; a measurement run outside a build has to do the same or every
    CFB market fails with "no scoring baseline registered". Returns a
    note for the log; "" when nothing was needed.
    """
    if sport != "cfb" or "cfb" in CURVES:
        return ""
    from . import teamrates
    from .cfb import ratings as cfbratings
    ratings = teamrates.compute_team_ratings(conn, "cfb", shrink=8.0)
    fit = cfbratings.fit_from_history(conn, ratings)
    cfbratings.install(fit)
    CURVES["cfb"] = lambda hr, ar: cfbratings.win_prob(
        (hr or 0.0) - (ar or 0.0) + fit.home_field, fit)
    return (f"cfb baseline installed from {fit.games:,} games "
            f"(home field {fit.home_field:+.1f})")


@dataclass
class GameRank:
    sport: str
    market: str
    games_seen: int = 0
    games_quoted: int = 0
    pairs: list = field(default_factory=list)      # (p_side, won)
    pushes: int = 0
    auc: float | None = None
    note: str = ""

    def finish(self) -> "GameRank":
        self.auc = auc(self.pairs) if len(self.pairs) >= MIN_GAMES else None
        if len(self.pairs) < MIN_GAMES:
            self.note = (f"{len(self.pairs):,} quoted games — needs "
                         f"{MIN_GAMES:,} before it can claim to rank")
        elif self.auc is None:
            self.note = "one-sided outcomes — no AUC"
        return self


def _games(conn, sport: str):
    return conn.execute(
        "SELECT season, period, date, home, away, home_score, away_score FROM games "
        "WHERE sport=? AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "ORDER BY season, period", (sport,)).fetchall()


def measure_lines(conn, sport: str, market: str,
                  min_team_games: int = 15) -> GameRank:
    """Totals or spreads: the pricer's side and its probability, per game."""
    if market not in ("total", "spread"):
        raise ValueError(market)
    baseline = _sd(SCORING_BASELINE, sport, "scoring baseline")
    schedule = schedule_closes(conn, sport, market, require_prices=False)
    harvested = game_line_closes(conn, sport, market)
    r = GameRank(sport=sport, market=market)
    agg: dict = {}
    for row in _games(conn, sport):
        date, home, away = row["period"], row["home"], row["away"]
        hs, as_ = float(row["home_score"]), float(row["away_score"])
        r.games_seen += 1
        quote = close_for(harvested, schedule, row["season"], date, home, away,
                          date=row["date"])
        enough = (agg.get(home, (0, 0, 0))[2] >= min_team_games
                  and agg.get(away, (0, 0, 0))[2] >= min_team_games)
        if quote and enough:
            line, odds_a, odds_b = quote
            h_off, h_def = _split(agg, home, baseline)
            a_off, a_def = _split(agg, away, baseline)
            # A line with no price still ranks: the probability comes
            # from the projection, and a standard price is enough for
            # the pricer to choose a side.
            odds_a = odds_a if odds_a is not None else -110
            odds_b = odds_b if odds_b is not None else -110
            r.games_quoted += 1
            if market == "total":
                proj = project_total(sport, h_off, h_def, a_off, a_def)
                card = price_total(sport, home, away, proj, line, odds_a, odds_b)
                won, push = _settle_total(line, card["side"], hs, as_)
            else:
                proj = game_margin(sport, h_off - h_def, a_off - a_def)
                card = price_spread(sport, home, away, proj, line, odds_a, odds_b)
                won, push = _settle_spread(line, card["team"] == home, hs, as_)
            if push:
                r.pushes += 1
            else:
                r.pairs.append((float(card["win_prob"]), bool(won)))
        pf, pa, n = agg.get(home, (0.0, 0.0, 0))
        agg[home] = (pf + hs, pa + as_, n + 1)
        pf, pa, n = agg.get(away, (0.0, 0.0, 0))
        agg[away] = (pf + as_, pa + hs, n + 1)
    return r.finish()


def measure_team_totals(conn, sport: str, min_team_games: int = 15) -> GameRank:
    """Team totals: the same derived line the live board splits from the
    game total and spread (see `gamebacktest.backtest_team_totals`),
    priced at the total's odds, two rows a game."""
    baseline = _sd(SCORING_BASELINE, sport, "scoring baseline")
    sched_t = schedule_closes(conn, sport, "total", require_prices=False)
    harv_t = game_line_closes(conn, sport, "total")
    sched_s = schedule_closes(conn, sport, "spread", require_prices=False)
    harv_s = game_line_closes(conn, sport, "spread")
    r = GameRank(sport=sport, market="team_total")
    agg: dict = {}
    for row in _games(conn, sport):
        date, home, away = row["period"], row["home"], row["away"]
        hs, as_ = float(row["home_score"]), float(row["away_score"])
        r.games_seen += 1
        tq = close_for(harv_t, sched_t, row["season"], date, home, away, date=row["date"])
        sq = close_for(harv_s, sched_s, row["season"], date, home, away, date=row["date"])
        enough = (agg.get(home, (0, 0, 0))[2] >= min_team_games
                  and agg.get(away, (0, 0, 0))[2] >= min_team_games)
        if tq and sq and enough:
            h_off, h_def = _split(agg, home, baseline)
            a_off, a_def = _split(agg, away, baseline)
            total_line, odds_a, odds_b = tq
            odds_a = odds_a if odds_a is not None else -110
            odds_b = odds_b if odds_b is not None else -110
            r.games_quoted += 1
            h_line = (total_line - sq[0]) / 2.0
            a_line = (total_line + sq[0]) / 2.0
            for team, proj, line, pts in (
                    (home, project_team_points(sport, h_off, a_def), h_line, hs),
                    (away, project_team_points(sport, a_off, h_def), a_line, as_)):
                card = price_team_total(sport, team, home, away, proj, line,
                                        odds_a, odds_b)
                won, push = _settle_team_total(line, card["side"], pts)
                if push:
                    r.pushes += 1
                else:
                    r.pairs.append((float(card["win_prob"]), bool(won)))
        pf, pa, n = agg.get(home, (0.0, 0.0, 0))
        agg[home] = (pf + hs, pa + as_, n + 1)
        pf, pa, n = agg.get(away, (0.0, 0.0, 0))
        agg[away] = (pf + as_, pa + hs, n + 1)
    return r.finish()


def measure_moneylines(conn, sport: str, min_team_games: int = 15) -> GameRank:
    """Moneylines: P(home wins) against whether home won — side-free, so
    the pair is the home probability and the home result."""
    r = GameRank(sport=sport, market="moneyline")
    if sport not in CURVES:
        r.note = f"no win-probability curve for {sport}"
        return r
    win_prob = CURVES[sport]
    baseline = SCORING_BASELINE.get(sport, 0.0)
    harvested = moneyline_closes(conn, sport)
    schedule = {k: {k[2]: h, k[3]: a}
                for k, (h, a) in schedule_moneylines(conn, sport).items()}
    agg: dict = {}
    for row in _games(conn, sport):
        date, home, away = row["period"], row["home"], row["away"]
        hs, as_ = float(row["home_score"]), float(row["away_score"])
        r.games_seen += 1
        quote = close_for(harvested, schedule, row["season"], date, home, away,
                          date=row["date"]) or {}
        enough = (agg.get(home, (0, 0, 0))[2] >= min_team_games
                  and agg.get(away, (0, 0, 0))[2] >= min_team_games)
        if enough and quote.get(home) is not None and quote.get(away) is not None:
            wp_home = win_prob(_rating(agg, home, baseline),
                               _rating(agg, away, baseline))
            r.games_quoted += 1
            if hs != as_:
                r.pairs.append((float(wp_home), hs > as_))
            else:
                r.pushes += 1
        pf, pa, n = agg.get(home, (0.0, 0.0, 0))
        agg[home] = (pf + hs, pa + as_, n + 1)
        pf, pa, n = agg.get(away, (0.0, 0.0, 0))
        agg[away] = (pf + as_, pa + hs, n + 1)
    return r.finish()


def measure_market_moneyline(conn, sport: str) -> GameRank:
    """THE CLOSE ITSELF, graded the way the model is: the book's de-vigged
    home probability against whether home won, over the same scored games
    with a quote, ties excluded.

    This is the number `likely.GAME_RANK_MARKET` carries (NFL 0.722,
    college 0.7905, measured 2026-09-07) and the reason the Most Likely
    game rows rank on the market's figure. It lives HERE, beside the
    model's measurement, and not in the test suite: run_tests.py is
    explicit that the suite must not read the box it runs on, and the
    first version of this measurement was a test that opened the real
    history database — green on a box with closes, a crash on GitHub's
    clone, which has none. Re-measure on the droplet with the command in
    docs/DROPLET_CHECKS.md; the test pins the constants and proves this
    function on a synthetic book.
    """
    from .odds import devig_two_way
    r = GameRank(sport=sport, market="moneyline")
    harvested = moneyline_closes(conn, sport)
    schedule = {k: {k[2]: h, k[3]: a}
                for k, (h, a) in schedule_moneylines(conn, sport).items()}
    for row in _games(conn, sport):
        date, home, away = row["period"], row["home"], row["away"]
        hs, as_ = float(row["home_score"]), float(row["away_score"])
        r.games_seen += 1
        quote = close_for(harvested, schedule, row["season"], date, home, away,
                          date=row["date"]) or {}
        if quote.get(home) is None or quote.get(away) is None:
            continue
        r.games_quoted += 1
        if hs == as_:
            r.pushes += 1
            continue
        fair_home, _ = devig_two_way(int(quote[home]), int(quote[away]))
        r.pairs.append((float(fair_home), hs > as_))
    r = r.finish()
    # Prefixed, not assigned: `finish` writes its own note under MIN_GAMES
    # and that sample warning must survive beside what this number is.
    r.note = ("the close itself, de-vigged — the figure GAME_RANK_MARKET carries"
              + (f" · {r.note}" if r.note else ""))
    return r


def _cfb_prior_table(mem, rows, before: str, seasons) -> None:
    """Refill the in-memory games table with every game strictly before
    `before` from `seasons` — the production solver reads a connection,
    so the walk hands it one that only knows the past."""
    mem.execute("DELETE FROM games")
    mem.executemany(
        "INSERT INTO games VALUES (?,?,?,?,?,?,?,?)",
        [tuple(r)[:8] for r in rows if r["period"] < before and r["season"] in seasons])
    mem.commit()


def measure_cfb(conn, min_team_games: int = 4, keep=None) -> list[GameRank]:
    """College, with the PRODUCTION ratings rather than the plain floor.

    cfb_build prices from `teamrates.adjusted_ratings_for_season` — the
    opponent-adjusted solve with the fitted home field, pooled with the
    prior season until the current one averages four games a team — and
    the plain `_split` walk the NFL and MLB paths use understates it:
    measured 2026-09-02, the moneyline rose from 0.708 (plain, 2,016
    games) to 0.752 (adjusted, 2,729 — the four-game floor admits more
    of each season), while the spread and the total stayed at a coin
    flip either way. So this walk rebuilds the production
    ratings before every date, from games strictly before it, using the
    same function the build calls. An in-memory games table is what
    makes that leak-free: the solver reads a connection, and it is
    handed one that holds only the past.

    `min_team_games` is four, not the fifteen the pro leagues use: a
    college season is twelve games and the build prices week one on the
    pooled prior season, so fifteen would skip most of every season.

    NOT the whole production model: the recruiting prior blended in
    before week four and the FCS exclusion that needs the live team map
    are not replayed, so this is a floor on the build's own number —
    a higher one than the plain walk, and the one the shipped figure
    should carry.
    """
    import sqlite3
    from . import teamrates
    from .cfb import ratings as cfbratings
    prepare(conn, "cfb")
    baseline = _sd(SCORING_BASELINE, "cfb", "scoring baseline")
    plain = teamrates.compute_team_ratings(conn, "cfb", shrink=8.0)
    fit = cfbratings.fit_from_history(conn, plain)
    cols = "sport, season, period, home, away, home_score, away_score, extra"
    rows = conn.execute(
        f"SELECT {cols}, date FROM games WHERE sport='cfb' AND home_score IS NOT NULL "
        f"AND away_score IS NOT NULL ORDER BY season, period").fetchall()
    # The FCS exclusion only when the map loaded (cfb_build's rule): on a
    # box where every key is the espn: fallback, excluding it would drop
    # the league.
    espn = sum(1 for r in rows if str(r["home"]).startswith("espn:")
               or str(r["away"]).startswith("espn:"))
    exclude = "espn:" if rows and espn / len(rows) < 0.5 else None
    sched_s = schedule_closes(conn, "cfb", "spread", require_prices=False)
    harv_s = game_line_closes(conn, "cfb", "spread")
    sched_t = schedule_closes(conn, "cfb", "total", require_prices=False)
    harv_t = game_line_closes(conn, "cfb", "total")
    harv_ml = moneyline_closes(conn, "cfb")
    sched_ml = {k: {k[2]: h, k[3]: a}
                for k, (h, a) in schedule_moneylines(conn, "cfb").items()}
    out = {m: GameRank(sport="cfb", market=m)
           for m in ("total", "spread", "team_total", "moneyline")}
    mem = sqlite3.connect(":memory:")
    mem.row_factory = sqlite3.Row
    mem.execute(f"CREATE TABLE games ({cols})")
    by_date: dict = {}
    for r in rows:
        by_date.setdefault(r["period"], []).append(r)
    for date in sorted(by_date):
        games = by_date[date]
        season = games[0]["season"]
        _cfb_prior_table(mem, rows, date, (season - 1, season))
        ratings, _used = teamrates.adjusted_ratings_for_season(
            mem, "cfb", season, shrink=8.0, exclude_prefix=exclude,
            home_field=fit.home_field)
        for g in games:
            for m in out.values():
                m.games_seen += 1
            hr, ar = ratings.get(g["home"]), ratings.get(g["away"])
            if not hr or not ar or hr.games < min_team_games or ar.games < min_team_games:
                continue
            hs, as_ = float(g["home_score"]), float(g["away_score"])
            margin = (hr.net - ar.net) + fit.home_field
            sq = close_for(harv_s, sched_s, g["season"], date, g["home"], g["away"],
                           date=g["date"])
            tq = close_for(harv_t, sched_t, g["season"], date, g["home"], g["away"],
                           date=g["date"])
            if sq:
                line, oa, ob = sq
                oa, ob = (-110 if oa is None else oa), (-110 if ob is None else ob)
                card = price_spread("cfb", g["home"], g["away"], margin, line, oa, ob)
                won, push = _settle_spread(line, card["team"] == g["home"], hs, as_)
                out["spread"].games_quoted += 1
                if push:
                    out["spread"].pushes += 1
                else:
                    out["spread"].pairs.append((float(card["win_prob"]), bool(won)))
            if tq:
                line, oa, ob = tq
                oa, ob = (-110 if oa is None else oa), (-110 if ob is None else ob)
                proj = project_total("cfb", hr.off, hr.def_, ar.off, ar.def_)
                card = price_total("cfb", g["home"], g["away"], proj, line, oa, ob)
                won, push = _settle_total(line, card["side"], hs, as_)
                out["total"].games_quoted += 1
                if push:
                    out["total"].pushes += 1
                else:
                    out["total"].pairs.append((float(card["win_prob"]), bool(won)))
                if sq:
                    h_line, a_line = (line - sq[0]) / 2.0, (line + sq[0]) / 2.0
                    out["team_total"].games_quoted += 1
                    for team, pr, ln, pts in (
                            (g["home"], project_team_points("cfb", hr.off, ar.def_), h_line, hs),
                            (g["away"], project_team_points("cfb", ar.off, hr.def_), a_line, as_)):
                        c = price_team_total("cfb", team, g["home"], g["away"], pr, ln, oa, ob)
                        won, push = _settle_team_total(ln, c["side"], pts)
                        if push:
                            out["team_total"].pushes += 1
                        else:
                            out["team_total"].pairs.append((float(c["win_prob"]), bool(won)))
            q = close_for(harv_ml, sched_ml, g["season"], date, g["home"], g["away"],
                          date=g["date"]) or {}
            if q.get(g["home"]) is not None and q.get(g["away"]) is not None:
                out["moneyline"].games_quoted += 1
                if hs != as_:
                    out["moneyline"].pairs.append(
                        (float(cfbratings.win_prob(margin, fit)), hs > as_))
                    if keep is not None:
                        keep(_quoted(g["season"], g, q,
                                     float(cfbratings.win_prob(margin, fit)), hs > as_))
                else:
                    out["moneyline"].pushes += 1
    mem.close()
    return [out[m].finish() for m in ("total", "spread", "team_total", "moneyline")]


def _prior_table(mem, rows, before: tuple, seasons) -> None:
    """Refill the in-memory games table with every game strictly before
    ``before`` — a ``(season, period)`` pair — from ``seasons``. The
    production ratings read a connection, so the walk hands them one
    that only knows the past. Ordered by the pair, never by period
    alone: an NFL period is a week number that repeats every season."""
    mem.execute("DELETE FROM games")
    mem.executemany(
        "INSERT INTO games VALUES (?,?,?,?,?,?,?,?)",
        [tuple(r)[:8] for r in rows            # the eight columns the table has; the date rides beside them
         if (r["season"], r["period"]) < before and r["season"] in seasons])
    mem.commit()


def measure_nfl(conn, min_team_games: int = 4,
                adjusted: bool = False, keep=None) -> list[GameRank]:
    """The NFL, with the ratings the build SHIPS rather than the plain
    cumulative walk — the college precedent (`measure_cfb`), applied.

    WHY THE PLAIN WALK IS THE WRONG MODEL TO GRADE. `measure_moneylines`
    accumulates every team's games forever, so by 2025 it rates a team
    on its 2021-25 average. `nfl_build` prices from
    `teamrates.ratings_for_season`: the current season alone once it
    averages four games a team, pooled with the prior season until then.
    Those are different models, and the board's "ranks at" figure was
    the first one's. This walk rebuilds the second before every week,
    from games strictly before it, with the same function the build
    calls, on an in-memory table that holds only the past.

    MEASURED 2026-09-07, both on the same 1,181 quoted games (the
    fifteen-game cumulative floor, so the two are on identical games),
    against the schedule's closing moneyline (which ranks the same
    winners at 0.724):

        cumulative walk (what shipped)     AUC 0.633   Brier 0.235
        ratings_for_season (what ships)    AUC 0.683   Brier 0.222
        …opponent-adjusted, H = 1.6        AUC 0.685
        …opponent-adjusted, H fitted +2.2  AUC 0.684

    Ethan, the same day: "Can we Create arithmetic equations to figure
    out the outcome nfl moneylines." The last two rows are the answer
    to what a better equation on the same inputs is worth: the college
    fix that lifted college from 0.708 to 0.752 moves the NFL by two
    thousandths, because an NFL schedule is close to balanced and the
    plain average was never far from the adjusted one. The calibration
    slope of the shipped model's disagreement with the close is
    −0.057 ± 0.135 — its opinion against the market carries nothing —
    and it is −0.08 for both adjusted forms. ``adjusted=True`` re-runs
    the third row so that refusal stays re-measurable; it is NOT wired
    into the build, and this docstring is why.

    ``min_team_games`` is four, as college's is, and it counts the
    SHIPPED rating's own games — this season's, or the pooled pair's —
    not a cumulative history. The build prices week one on the pooled
    prior season, and a production rating with four games behind it is
    what the board actually shows. Measured 2026-09-07 that is 1,356
    quoted games and a moneyline AUC of 0.6773 (spread 0.5036, total
    0.4961, team total 0.5002), and that is the figure
    `likely.GAME_RANK_AUC` carries. Raising the floor here does NOT
    reproduce the 1,181-game table above: a shipped rating rarely holds
    fifteen games, so fifteen admits only late-season weeks (478). The
    table above came from a walk that took the quoted set off the
    cumulative floor and the probability off these ratings, which is
    the only way to put the two models on identical games.

    Spreads, totals and team totals are measured on the same ratings by
    the same pricers, for the same reason: the leans the board prints
    should be graded on the model that produced them.
    """
    import sqlite3
    from . import teamrates
    from .gamebets import NFL_HOME_FIELD
    baseline = _sd(SCORING_BASELINE, "nfl", "scoring baseline")
    cols = "sport, season, period, home, away, home_score, away_score, extra"
    rows = conn.execute(
        f"SELECT {cols}, date FROM games WHERE sport='nfl' AND home_score IS NOT NULL "
        f"AND away_score IS NOT NULL ORDER BY season, period").fetchall()
    sched_s = schedule_closes(conn, "nfl", "spread", require_prices=False)
    harv_s = game_line_closes(conn, "nfl", "spread")
    sched_t = schedule_closes(conn, "nfl", "total", require_prices=False)
    harv_t = game_line_closes(conn, "nfl", "total")
    harv_ml = moneyline_closes(conn, "nfl")
    sched_ml = {k: {k[2]: h, k[3]: a}
                for k, (h, a) in schedule_moneylines(conn, "nfl").items()}
    out = {m: GameRank(sport="nfl", market=m)
           for m in ("total", "spread", "team_total", "moneyline")}
    mem = sqlite3.connect(":memory:")
    mem.row_factory = sqlite3.Row
    mem.execute(f"CREATE TABLE games ({cols})")
    by_week: dict = {}
    for r in rows:
        by_week.setdefault((r["season"], r["period"]), []).append(r)
    for week in sorted(by_week):
        games = by_week[week]
        season = week[0]
        _prior_table(mem, rows, week, (season - 1, season))
        if adjusted:
            ratings, _used = teamrates.adjusted_ratings_for_season(
                mem, "nfl", season, home_field=NFL_HOME_FIELD)
        else:
            ratings, _used = teamrates.ratings_for_season(mem, "nfl", season)
        for g in games:
            for m in out.values():
                m.games_seen += 1
            hr, ar = ratings.get(g["home"]), ratings.get(g["away"])
            if not hr or not ar or hr.games < min_team_games or ar.games < min_team_games:
                continue
            date = g["period"]
            hs, as_ = float(g["home_score"]), float(g["away_score"])
            margin = game_margin("nfl", hr.net, ar.net)
            sq = close_for(harv_s, sched_s, season, date, g["home"], g["away"],
                           date=g["date"])
            tq = close_for(harv_t, sched_t, season, date, g["home"], g["away"],
                           date=g["date"])
            if sq:
                line, oa, ob = sq
                oa, ob = (-110 if oa is None else oa), (-110 if ob is None else ob)
                card = price_spread("nfl", g["home"], g["away"], margin, line, oa, ob)
                won, push = _settle_spread(line, card["team"] == g["home"], hs, as_)
                out["spread"].games_quoted += 1
                if push:
                    out["spread"].pushes += 1
                else:
                    out["spread"].pairs.append((float(card["win_prob"]), bool(won)))
            if tq:
                line, oa, ob = tq
                oa, ob = (-110 if oa is None else oa), (-110 if ob is None else ob)
                proj = project_total("nfl", hr.off, hr.def_, ar.off, ar.def_)
                card = price_total("nfl", g["home"], g["away"], proj, line, oa, ob)
                won, push = _settle_total(line, card["side"], hs, as_)
                out["total"].games_quoted += 1
                if push:
                    out["total"].pushes += 1
                else:
                    out["total"].pairs.append((float(card["win_prob"]), bool(won)))
                if sq:
                    h_line, a_line = (line - sq[0]) / 2.0, (line + sq[0]) / 2.0
                    out["team_total"].games_quoted += 1
                    for team, pr, ln, pts in (
                            (g["home"], project_team_points("nfl", hr.off, ar.def_), h_line, hs),
                            (g["away"], project_team_points("nfl", ar.off, hr.def_), a_line, as_)):
                        c = price_team_total("nfl", team, g["home"], g["away"], pr, ln, oa, ob)
                        won, push = _settle_team_total(ln, c["side"], pts)
                        if push:
                            out["team_total"].pushes += 1
                        else:
                            out["team_total"].pairs.append((float(c["win_prob"]), bool(won)))
            q = close_for(harv_ml, sched_ml, season, date, g["home"], g["away"],
                          date=g["date"]) or {}
            if q.get(g["home"]) is not None and q.get(g["away"]) is not None:
                out["moneyline"].games_quoted += 1
                if hs != as_:
                    out["moneyline"].pairs.append(
                        (float(nfl_win_prob(hr.net, ar.net)), hs > as_))
                    if keep is not None:
                        keep(_quoted(season, g, q, float(nfl_win_prob(hr.net, ar.net)),
                                     hs > as_))
                else:
                    out["moneyline"].pushes += 1
    mem.close()
    return [out[m].finish() for m in ("total", "spread", "team_total", "moneyline")]


def _quoted(season, g, q, raw_home: float, home_won: bool) -> dict:
    """One quoted, scored, non-tie game off a football walk, for `keep`:
    the model's RAW home probability beside both closing prices."""
    return {"season": season, "home": g["home"], "away": g["away"],
            "home_ml": int(q[g["home"]]), "away_ml": int(q[g["away"]]),
            "raw_home": raw_home, "home_won": bool(home_won)}


@dataclass
class RawBar:
    """Does the model's raw disagreement with the close say anything
    about the close? Counted on the favourites the likelihood board can
    carry (`likely.MIN_PROB`, `likely.HEAVIEST_PRICE`), split by whether
    `likely.MAX_CREDIBLE_EDGE` would have refused the row."""
    sport: str
    games: int = 0                 # quoted, scored, non-tie, rated
    eligible: int = 0              # the board's favourites on the market's number
    refused: int = 0               # …the raw bar would refuse
    kept_claimed: float | None = None
    kept_landed: float | None = None
    refused_claimed: float | None = None
    refused_landed: float | None = None
    ci: tuple | None = None        # 95% bootstrap: refused gap minus kept gap
    bands: list = field(default_factory=list)   # (lo, hi, n, claimed, landed)
    note: str = ""


#: Bands of the raw disagreement the refused rows are read in.
RAW_BAR_BANDS = ((0.10, 0.15), (0.15, 0.20), (0.20, 0.30), (0.30, 1.01))


def measure_raw_bar(conn, sport: str = "nfl", seed: int = 3,
                    resamples: int = 2000) -> RawBar:
    """The credibility bar on a market-ranked moneyline row, measured.

    `likely.engine_credible` refuses a row whose RAW model claim sits
    more than MAX_CREDIBLE_EDGE from the book's fair. On a row that
    RANKS on the market's number (`likely.GAME_RANK_MARKET`) the claim
    shown is the market's, so the question the bar should answer is
    whether the model's disagreement says anything about that number:
    does the market land differently on the games the model disputes?

    Walks the same games `measure_nfl` / `measure_cfb` grade, takes the
    favourite on the market's de-vigged number as the board would, and
    reports the market's claimed and landed rates on the rows the bar
    keeps against the rows it refuses, with a by-game bootstrap of the
    difference and the refused rows by size of disagreement.

    MEASURED 2026-09-08, NFL, 1,356 quoted games: 681 eligible, 207
    refused (30%); kept claimed 61.4% landed 64.3%; refused claimed
    61.4% landed 62.3%; 95% [-9.8%, +5.7%]. The bar was removing three
    rows in ten and changing nothing measurable, and `engine_credible`
    no longer applies it to a market-ranked row. College the same day,
    2,729 games: 1,066 eligible, 401 refused (38%), kept 62.2% -> 60.2%,
    refused 64.0% -> 63.8%, 95% [-4.3%, +7.8%].
    """
    import random
    from .likely import HEAVIEST_PRICE, MAX_CREDIBLE_EDGE, MIN_PROB
    from .odds import devig_two_way
    r = RawBar(sport=sport)
    rows: list = []
    if sport == "nfl":
        measure_nfl(conn, keep=rows.append)
    elif sport == "cfb":
        prepare(conn, "cfb")
        measure_cfb(conn, keep=rows.append)
    else:
        r.note = "only the football walks carry the raw claim"
        return r
    recs = []
    for g in rows:
        fh, fa = devig_two_way(g["home_ml"], g["away_ml"])
        if fh >= fa:
            fair, raw, odds, won = fh, g["raw_home"], g["home_ml"], g["home_won"]
        else:
            fair, raw, odds, won = fa, 1.0 - g["raw_home"], g["away_ml"], not g["home_won"]
        recs.append((float(fair), float(raw), int(odds), bool(won)))
    r.games = len(recs)
    elig = [x for x in recs if x[0] >= MIN_PROB and x[2] >= HEAVIEST_PRICE]
    bad = [x for x in elig if abs(x[1] - x[0]) > MAX_CREDIBLE_EDGE]
    keep = [x for x in elig if abs(x[1] - x[0]) <= MAX_CREDIBLE_EDGE]
    r.eligible, r.refused = len(elig), len(bad)

    def rate(xs):
        if not xs:
            return None, None
        return (sum(x[0] for x in xs) / len(xs), sum(1.0 for x in xs if x[3]) / len(xs))

    r.kept_claimed, r.kept_landed = rate(keep)
    r.refused_claimed, r.refused_landed = rate(bad)
    if keep and bad:
        rng = random.Random(seed)
        diffs = []
        for _ in range(resamples):
            a = [keep[rng.randrange(len(keep))] for _ in keep]
            b = [bad[rng.randrange(len(bad))] for _ in bad]
            ca, la = rate(a)
            cb, lb = rate(b)
            diffs.append((lb - cb) - (la - ca))
        diffs.sort()
        r.ci = (diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs)) - 1])
    for lo, hi in RAW_BAR_BANDS:
        xs = [x for x in bad if lo < abs(x[1] - x[0]) <= hi]
        c, l = rate(xs)
        r.bands.append((lo, hi, len(xs), c, l))
    if not elig:
        r.note = "no favourite the board could carry — nothing to measure"
    return r


def raw_bar_lines(r: RawBar) -> list[str]:
    from .likely import HEAVIEST_PRICE, MAX_CREDIBLE_EDGE, MIN_PROB
    pc = lambda v: "   —  " if v is None else f"{v:6.1%}"       # noqa: E731
    out = [f"raw-claim bar on market-ranked {r.sport.upper()} moneylines · "
           f"{r.games:,} quoted games"]
    if r.note:
        out.append(f"  {r.note}")
        return out
    share = r.refused / r.eligible if r.eligible else 0.0
    out += [f"  favourites the board could carry (fair >= {MIN_PROB:.0%}, "
            f"price >= {HEAVIEST_PRICE}): {r.eligible:,}",
            f"  …the raw bar (|raw - fair| > {MAX_CREDIBLE_EDGE:.0%}) would refuse: "
            f"{r.refused:,} ({share:.0%})",
            f"  market's number on the rows kept:    claimed {pc(r.kept_claimed)}  "
            f"landed {pc(r.kept_landed)}",
            f"  market's number on the rows refused: claimed {pc(r.refused_claimed)}  "
            f"landed {pc(r.refused_landed)}"]
    if r.ci:
        out.append(f"  refused minus kept, landed-vs-claimed, 95% by game: "
                   f"[{r.ci[0]:+.1%}, {r.ci[1]:+.1%}]")
    for lo, hi, n, c, l in r.bands:
        out.append(f"    disagreement {lo:.2f}-{min(hi, 1.0):.2f}: n={n:4d}  "
                   f"claimed {pc(c)}  landed {pc(l)}")
    return out


def measure(conn, sport: str) -> list[GameRank]:
    if sport == "nfl":
        try:
            return measure_nfl(conn)
        except Exception as exc:                          # noqa: BLE001
            return [GameRank(sport="nfl", market=m,
                             note=f"could not measure — {exc}")
                    for m in ("total", "spread", "team_total", "moneyline")]
    if sport == "cfb":
        try:
            return measure_cfb(conn)
        except Exception as exc:                          # noqa: BLE001
            return [GameRank(sport="cfb", market=m,
                             note=f"could not measure — {exc}")
                    for m in ("total", "spread", "team_total", "moneyline")]
    prepare(conn, sport)
    out = []
    for market in ("total", "spread", "team_total"):
        try:
            out.append(measure_lines(conn, sport, market)
                       if market != "team_total"
                       else measure_team_totals(conn, sport))
        except Exception as exc:                          # noqa: BLE001
            out.append(GameRank(sport=sport, market=market,
                                note=f"could not measure — {exc}"))
    out.append(measure_moneylines(conn, sport))
    return out


def lines(results: list[GameRank]) -> list[str]:
    from .likely import MIN_RANK_AUC
    out = []
    for r in results:
        if r.auc is None:
            out.append(f"game rank {r.sport}:{r.market}: {r.note}")
            continue
        word = ("ranked — on the board" if r.auc >= MIN_RANK_AUC
                else f"UNDER the {MIN_RANK_AUC} floor — shown as a lean, "
                     f"not ranked")
        out.append(f"game rank {r.sport}:{r.market}: AUC {r.auc:.4f} on "
                   f"{len(r.pairs):,} quoted games ({r.pushes} pushes) — {word}")
    return out


def measure_and_store(conn, sport: str, log=print, path=None) -> list[str]:
    """Measure, then write what the sample supports into the rank store.

    Same contract as `rankfit.measure`: a market with an AUC is stored
    (floor or not — the shelf logic compares it to `likely.MIN_RANK_AUC`,
    and a sub-floor number on record is what stops a shelf from being
    claimed by prose); a market this box can no longer support retires
    its own entry. A market that could not be measured at all (no
    baseline, no closes) leaves the store alone — a transient failure
    must not erase a number somebody measured.
    """
    from .rankfit import STORE, _save, load
    path = path or STORE
    store = load(path)
    changed = False
    out = []
    for r in measure(conn, sport):
        key = f"{sport}:{r.market}"
        if r.auc is None:
            if key in store and r.games_seen and (store[key].get("kind") == "game"):
                del store[key]
                changed = True
                out.append(f"game rank {key}: {r.note} — measurement RETIRED")
            else:
                out.append(f"game rank {key}: {r.note}")
            continue
        store[key] = {"auc": round(r.auc, 4), "n": len(r.pairs), "kind": "game",
                      "fitted_at": _dt.date.today().isoformat()}
        changed = True
        out.append(lines([r])[0])
    if changed:
        _save(store, path)
    for ln in out:
        log(f"  {ln}")
    return out


def main(argv=None) -> int:
    import argparse
    from . import db
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sport", default="")
    ap.add_argument("--save", action="store_true",
                    help="write the measured markets into the rank store")
    ap.add_argument("--raw-bar", action="store_true",
                    help="the credibility bar on market-ranked moneylines, "
                         "measured (see measure_raw_bar)")
    a = ap.parse_args(argv)
    conn = db.connect()
    try:
        sports = [a.sport] if a.sport else [s[0] for s in conn.execute(
            "SELECT DISTINCT sport FROM games WHERE home_score IS NOT NULL")]
        for sport in sports:
            if a.raw_bar:
                for ln in raw_bar_lines(measure_raw_bar(conn, sport)):
                    print(ln)
                continue
            if a.save:
                measure_and_store(conn, sport, log=print)
                continue
            for ln in lines(measure(conn, sport)):
                print(ln)
    finally:
        conn.close()
    print(f"measured {_dt.date.today().isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
