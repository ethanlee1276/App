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

MEASURED 2026-09-02 on this repo's history (NFL 2021-25, CFB 2022-25):

    nfl  moneyline 0.6412 (1,181)   spread 0.4911   total 0.4968   team_total 0.5132
    cfb  moneyline 0.7522 (2,729)   spread 0.4963   total 0.5034   team_total 0.4917

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
                           game_line_closes, moneyline_closes,
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
        "SELECT period, home, away, home_score, away_score FROM games "
        "WHERE sport=? AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "ORDER BY period", (sport,)).fetchall()


def measure_lines(conn, sport: str, market: str,
                  min_team_games: int = 15) -> GameRank:
    """Totals or spreads: the pricer's side and its probability, per game."""
    if market not in ("total", "spread"):
        raise ValueError(market)
    baseline = _sd(SCORING_BASELINE, sport, "scoring baseline")
    closes = dict(schedule_closes(conn, sport, market, require_prices=False))
    closes.update(game_line_closes(conn, sport, market))
    r = GameRank(sport=sport, market=market)
    agg: dict = {}
    for row in _games(conn, sport):
        date, home, away = row["period"], row["home"], row["away"]
        hs, as_ = float(row["home_score"]), float(row["away_score"])
        r.games_seen += 1
        quote = closes.get((date, home, away))
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
    totals = dict(schedule_closes(conn, sport, "total", require_prices=False))
    totals.update(game_line_closes(conn, sport, "total"))
    spreads = dict(schedule_closes(conn, sport, "spread", require_prices=False))
    spreads.update(game_line_closes(conn, sport, "spread"))
    r = GameRank(sport=sport, market="team_total")
    agg: dict = {}
    for row in _games(conn, sport):
        date, home, away = row["period"], row["home"], row["away"]
        hs, as_ = float(row["home_score"]), float(row["away_score"])
        r.games_seen += 1
        tq, sq = totals.get((date, home, away)), spreads.get((date, home, away))
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
    closes = moneyline_closes(conn, sport)
    if not closes:
        closes = {k: {k[1]: h, k[2]: a}
                  for k, (h, a) in schedule_moneylines(conn, sport).items()}
    agg: dict = {}
    for row in _games(conn, sport):
        date, home, away = row["period"], row["home"], row["away"]
        hs, as_ = float(row["home_score"]), float(row["away_score"])
        r.games_seen += 1
        quote = closes.get((date, home, away)) or {}
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


def _cfb_prior_table(mem, rows, before: str, seasons) -> None:
    """Refill the in-memory games table with every game strictly before
    `before` from `seasons` — the production solver reads a connection,
    so the walk hands it one that only knows the past."""
    mem.execute("DELETE FROM games")
    mem.executemany(
        "INSERT INTO games VALUES (?,?,?,?,?,?,?,?)",
        [tuple(r) for r in rows if r["period"] < before and r["season"] in seasons])
    mem.commit()


def measure_cfb(conn, min_team_games: int = 4) -> list[GameRank]:
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
        f"SELECT {cols} FROM games WHERE sport='cfb' AND home_score IS NOT NULL "
        f"AND away_score IS NOT NULL ORDER BY period").fetchall()
    # The FCS exclusion only when the map loaded (cfb_build's rule): on a
    # box where every key is the espn: fallback, excluding it would drop
    # the league.
    espn = sum(1 for r in rows if str(r["home"]).startswith("espn:")
               or str(r["away"]).startswith("espn:"))
    exclude = "espn:" if rows and espn / len(rows) < 0.5 else None
    spreads = dict(schedule_closes(conn, "cfb", "spread", require_prices=False))
    spreads.update(game_line_closes(conn, "cfb", "spread"))
    totals = dict(schedule_closes(conn, "cfb", "total", require_prices=False))
    totals.update(game_line_closes(conn, "cfb", "total"))
    mls = moneyline_closes(conn, "cfb")
    if not mls:
        mls = {k: {k[1]: h, k[2]: a}
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
            key = (date, g["home"], g["away"])
            hs, as_ = float(g["home_score"]), float(g["away_score"])
            margin = (hr.net - ar.net) + fit.home_field
            sq, tq = spreads.get(key), totals.get(key)
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
            q = mls.get(key) or {}
            if q.get(g["home"]) is not None and q.get(g["away"]) is not None:
                out["moneyline"].games_quoted += 1
                if hs != as_:
                    out["moneyline"].pairs.append(
                        (float(cfbratings.win_prob(margin, fit)), hs > as_))
                else:
                    out["moneyline"].pushes += 1
    mem.close()
    return [out[m].finish() for m in ("total", "spread", "team_total", "moneyline")]


def measure(conn, sport: str) -> list[GameRank]:
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
    a = ap.parse_args(argv)
    conn = db.connect()
    try:
        sports = [a.sport] if a.sport else [s[0] for s in conn.execute(
            "SELECT DISTINCT sport FROM games WHERE home_score IS NOT NULL")]
        for sport in sports:
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
