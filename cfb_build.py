#!/usr/bin/env python3
"""Build the college football slate: ratings → prices → the attention dial.

    python3 cfb_build.py 2026-09-05 --cached-odds --out web/data/cfb.json

Schedule, conferences, rankings and results come from ESPN's keyless
college-football feed; prices from The Odds API in ONE bulk request for the
whole board (a 60-game Saturday priced event-by-event would cost sixty
credits and the pacer would never authorise it).

The projection layer is deliberately the shared one — ``engine.teamrates``
for opponent-adjusted strength, ``engine.gamebets`` for turning a rating
gap into a price. What is college-specific is everything downstream:
``engine.cfb`` decides how much of the resulting edge to believe based on
how hard the market was looking at that game, and refuses to grade a play
whose quarterback nobody has confirmed.

Two honesty rails run through this file. The variance constants are FITTED
from ingested results when there are enough of them and flagged as priors
when there aren't — an unfitted board is journaled and graded, never
staked. And a game with no quarterback confirmation publishes as a
conditional, with its number and its edge, rather than as a bet.
"""

from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

from engine import gamebets, teamrates
from engine.staking import to_units
from engine.cfb import context as cfbcontext
from engine.cfb import ratings as cfbratings
from engine.cfb import status as cfbstatus
from engine.cfb.model import attention_tier
from engine.cfb.pipeline import run_cfb_slate
from engine.db import connect, upsert_games
from engine.odds import expected_value
from engine.sources import cfbdata
from engine.sources.fetch import DataUnavailable
from engine import gate

# How far back each build re-reads results. A season fills the table one
# rolling window at a time; --backfill does a whole span in one go.
RESULT_WINDOW_DAYS = 14
# Either side of the slate, for the letdown / lookahead / short-week reads.
NEIGHBOUR_DAYS = 8


def _iso(d: datetime.date) -> str:
    return d.isoformat()


def ingest_results(conn, games: list[dict]) -> int:
    rows = cfbdata.game_rows(games)
    return upsert_games(conn, rows) if rows else 0


def attach_odds(games: list[dict], lookup: dict, cache_only: bool,
                api_key: str | None = None) -> tuple[dict, str]:
    """``{game_id: {...market prices...}}`` plus a human note.

    One request covers the entire board. Events whose team names can't be
    resolved are counted rather than silently dropped — an unmatched school
    is a bug in the name map, and a board that quietly prices 40 of 60
    games looks exactly like a light Saturday.
    """
    from engine.sources import oddsapi

    by_pair = {frozenset((g["home"], g["away"])): g for g in games}
    try:
        events, quota = oddsapi.fetch_sport_odds(
            "cfb", api_key=api_key, cache_only=cache_only)
    except oddsapi.OddsAPIError as exc:
        return {}, f"odds unavailable: {exc}"

    priced: dict[str, dict] = {}
    unmatched: list[str] = []
    for ev in events:
        home_raw = ev.get("home_team", "")
        away_raw = ev.get("away_team", "")
        home = cfbdata.resolve_team(home_raw, lookup)
        away = cfbdata.resolve_team(away_raw, lookup)
        if not home or not away:
            unmatched.append(f"{away_raw} @ {home_raw}")
            continue
        game = by_pair.get(frozenset((home, away)))
        if not game:
            continue
        # The parsers key on the exact strings this feed uses, so build the
        # map from the event itself rather than guessing at spellings.
        team_map = {home_raw: home, away_raw: away}
        entry: dict = {}
        mls = oddsapi.parse_event_h2h(ev, team_map)
        if mls.get(home) and mls.get(away):
            entry["moneyline"] = (mls[home], mls[away])
        sp = oddsapi.parse_event_spreads(ev, team_map, home, away)
        if sp:
            entry["spread"] = sp
        tot = oddsapi.parse_event_totals(ev)
        if tot:
            entry["total"] = tot
        if entry:
            entry["books"] = _books_for(ev, entry, home, away, team_map)
            priced[game["game_id"]] = entry

    note = f"{len(priced)} of {len(games)} games priced from 1 request"
    if unmatched:
        note += f" · {len(unmatched)} unmatched ({', '.join(unmatched[:3])}…)"
    if cache_only:
        note += " (cached)"
    return priced, note


def _books_for(ev: dict, entry: dict, home: str, away: str,
               team_map: dict) -> dict:
    """Which book is actually offering each chosen price.

    The parsers take the best number across the field but don't say where
    it came from, and naming the wrong book is worse than naming none —
    it sends you to a window that isn't quoting that price.
    """
    from engine.sources.oddsapi import BOOK_TITLES, SHARP_BOOKS

    wanted: dict[str, tuple] = {}
    if "spread" in entry:
        line, home_odds, _ = entry["spread"]
        wanted["spread"] = ("spreads", home, line, home_odds)
    if "total" in entry:
        line, over_odds, _ = entry["total"]
        wanted["total"] = ("totals", "Over", line, over_odds)
    if "moneyline" in entry:
        wanted["moneyline"] = ("h2h", home, None, entry["moneyline"][0])

    found: dict[str, str] = {}
    for bm in ev.get("bookmakers", []):
        key = bm.get("key", "")
        if key in SHARP_BOOKS:
            continue
        title = BOOK_TITLES.get(key, bm.get("title") or key)
        for mkt in bm.get("markets", []):
            for name, (mkey, who, point, price) in wanted.items():
                if name in found or mkt.get("key") != mkey:
                    continue
                for o in mkt.get("outcomes", []):
                    label = team_map.get(o.get("name", ""), o.get("name", ""))
                    if label != who or o.get("price") != price:
                        continue
                    if point is not None and o.get("point") != point:
                        continue
                    found[name] = title
    return found


def attach_talent(conn, ratings: dict, year: int, lookup: dict) -> dict:
    """Blend the recruiting-based preseason prior into the team ratings.

    Everything here is key-gated behind CollegeFootballData, and the whole
    block degrades to "no prior" rather than to a guess — which costs
    accuracy in September and nothing at all by November, the exact shape
    of the thing a preseason prior is for.
    """
    from engine.cfb import talent as T
    from engine.sources import cfbd
    from engine.sources.fetch import DataUnavailable

    report: dict = {"ratings": ratings, "available": False,
                    "note": "", "fit": {}, "teams_with_prior": 0}
    try:
        raw_talent = cfbd.fetch_talent(year)
    except DataUnavailable as exc:
        report["note"] = str(exc)
        return report

    # CFBD speaks school names ("Ohio State"); our ratings are keyed by the
    # ESPN abbreviations the schedule uses.
    def _abbr(school: str) -> str:
        return cfbdata.resolve_team(school, lookup)

    talent = {a: v for a, v in
              ((_abbr(s), v) for s, v in raw_talent.items()) if a}
    try:
        blue = {a: v for a, v in
                ((_abbr(s), v) for s, v in cfbd.blue_chip_ratio(year).items()) if a}
    except DataUnavailable:
        blue = {}
    try:
        returning = {a: v for a, v in
                     ((_abbr(s), v) for s, v in cfbd.fetch_returning(year).items()) if a}
    except DataUnavailable:
        returning = {}
    # The portal. A recruiting composite describes the roster a team
    # signed, not the one it has after a dozen starters transfer out — and
    # in the modern sport that gap is the single biggest reason a
    # preseason prior is wrong about a team.
    try:
        portal = {a: v for a, v in
                  ((_abbr(s), v) for s, v in cfbd.fetch_portal(year).items()) if a}
    except DataUnavailable:
        portal = {}

    # Fit the talent→points slope against our own completed seasons before
    # trusting it. Prior seasons are pulled from cache when present.
    by_year: dict = {}
    for y in range(year - 1, year - 5, -1):
        try:
            rows = cfbd.fetch_talent(y)
        except DataUnavailable:
            continue
        by_year[y] = {a: v for a, v in
                      ((_abbr(s), v) for s, v in rows.items()) if a}
    fit = T.fit_points_per_sd(T.team_seasons_from_db(conn, by_year)) \
        if by_year else T.PRIOR_FIT

    prior = T.talent_prior(talent, fit, blue)
    blended, blend_report = T.apply_prior(ratings, prior, returning, portal)
    # Each sub-layer is reported separately. "The talent layer is on" and
    # "all four of its inputs arrived" are different facts, and a page that
    # cannot tell them apart will show a September prior built on
    # recruiting alone as though it also knew who transferred.
    layers = {"talent": len(talent), "blue_chip": len(blue),
              "returning": len(returning), "portal": len(portal)}
    missing = [k for k, v in layers.items() if not v]
    report.update(
        ratings=blended, available=True,
        teams_with_prior=blend_report["teams"],
        portal_teams=blend_report.get("portal_teams", 0),
        blue_chip_teams=len(blue), returning_teams=len(returning),
        layers=layers, missing_layers=missing,
        fit={"points_per_sd": fit.points_per_sd, "fitted": fit.fitted,
             "samples": fit.samples, "r": fit.r, "note": fit.note},
        note=(f"Preseason prior from recruiting applied to "
              f"{blend_report['teams']} team(s); portal adjusted "
              f"{blend_report.get('portal_teams', 0)}. {fit.note}"
              + (f" NOT loaded: {', '.join(missing)}." if missing else "")))
    return report


def build_plays(games: list[dict], priced: dict, ratings: dict,
                fit, prev: dict, nxt: dict) -> list[dict]:
    """Every game with a price → the plays the CFB pipeline will judge."""
    plays: list[dict] = []
    for g in games:
        lines = priced.get(g["game_id"])
        if not lines:
            continue
        hr, ar = ratings.get(g["home"]), ratings.get(g["away"])
        if not hr or not ar:
            continue                     # no rating = no opinion, not a guess

        tier = attention_tier(g)
        tags = cfbcontext.situational_tags(g, prev, nxt)
        neutral = g.get("neutral_site")
        proj_margin = (hr.net - ar.net) + (0.0 if neutral else fit.home_field)
        proj_total = gamebets.project_total("cfb", hr.off, hr.def_,
                                            ar.off, ar.def_)
        books = lines.get("books") or {}
        common = {
            "game": g,
            "information_certainty": cfbstatus.certainty(g),
            "information_certainty_confirmed": cfbstatus.certainty(
                g, assume_confirmed=True),
            "attention_fit": cfbcontext.attention_fit(tier),
            "situational_fit": cfbcontext.situational_fit(tags),
            "matchup_fit": cfbcontext.matchup_fit(hr.games, ar.games),
            "situational_tags": tags,
        }
        context = [f"Ratings: {g['home']} {hr.net:+.1f}, {g['away']} "
                   f"{ar.net:+.1f} net points/game over "
                   f"{min(hr.games, ar.games)} graded games"]
        if neutral:
            context.append("Neutral site — no home field applied")
        for t in tags:
            context.append(f"Situational: {t.replace('_', ' ')}")

        if "spread" in lines:
            home_spread, home_odds, away_odds = lines["spread"]
            card = gamebets.price_spread("cfb", g["home"], g["away"],
                                         proj_margin, home_spread,
                                         home_odds, away_odds, context)
            picked_home = card["team"] == g["home"]
            plays.append({**common, "market": "side",
                          "selection": card["pick_label"],
                          "line": card["line"], "odds": card["odds"],
                          "opposing_odds": away_odds if picked_home else home_odds,
                          "p_model": card["win_prob"],
                          "book": books.get("spread", ""),
                          "environment_fit": cfbcontext.environment_fit(g, "side"),
                          "shared": card})

        if "total" in lines:
            market_total, over_odds, under_odds = lines["total"]
            card = gamebets.price_total("cfb", g["home"], g["away"],
                                        proj_total, market_total,
                                        over_odds, under_odds, context=context)
            over = card["side"] == "Over"
            plays.append({**common, "market": "total",
                          "selection": card["pick_label"],
                          "line": card["line"], "odds": card["odds"],
                          "opposing_odds": under_odds if over else over_odds,
                          "p_model": card["win_prob"],
                          "book": books.get("total", ""),
                          "environment_fit": cfbcontext.environment_fit(g, "total"),
                          "shared": card})

        if "moneyline" in lines:
            home_ml, away_ml = lines["moneyline"]
            wp_home = cfbratings.win_prob(proj_margin, fit)
            rec = gamebets.price_moneyline(g["home"], g["away"], wp_home,
                                           home_ml, away_ml, context)
            card = gamebets.moneyline_to_dict(rec)
            plays.append({**common, "market": "moneyline",
                          "selection": card["pick_label"],
                          "line": 0.0, "odds": card["odds"],
                          "opposing_odds": away_ml if rec.pick_is_home else home_ml,
                          "p_model": card["win_prob"],
                          "book": books.get("moneyline", ""),
                          "environment_fit": cfbcontext.environment_fit(g, "moneyline"),
                          "shared": card})
    return plays


BET_TYPES = {"side": "spread", "total": "total", "moneyline": "moneyline"}


def to_game_bet(card: dict, play: dict, game: dict) -> dict:
    """A CFB verdict in the shape every other board's game bets use.

    The shared renderer already knows how to draw a spread, a total and a
    moneyline; what it does not know is attention tier or conditionals, so
    those ride along as extra keys and as reasons — nothing about the
    existing NFL/MLB rendering has to change.
    """
    shared = dict(play.get("shared") or {})
    conditional = card["kind"] == "hold"
    stake_fraction = card.get("stake_fraction") or 0.0
    reasons = list(shared.get("reasons") or [])
    from engine.cfb.model import HAIRCUT
    held_back = HAIRCUT.get(card["attention_tier"], 0.5)
    reasons.append(
        f"Attention tier: {card['attention_tier']} — {held_back:.0%} of the raw "
        f"edge held back as model error, leaving {card['edge']:+.1%} against a "
        f"{card['required_edge']:.1%} bar")
    reasons.append(f"Volatility {card['volatility']} · grade {card['grade']}/100")
    if conditional:
        reasons.append("CONDITIONAL — " + card["why"])

    return {
        **shared,
        "bet_type": BET_TYPES.get(card["market"], card["market"]),
        "market": BET_TYPES.get(card["market"], card["market"]),
        "market_label": card["market_label"],
        "home": game["home"], "away": game["away"],
        "matchup": f"{game['away']} @ {game['home']}",
        "date": game.get("date", ""), "kickoff": game.get("kickoff", ""),
        "win_prob": card["p_model"], "fair_prob": card["p_market"],
        "edge": card["edge"], "odds": card["odds"],
        "ev_per_unit": round(expected_value(card["p_model"], card["odds"]), 4),
        "confidence": round(card["grade"] / 10.0, 1),
        # A conditional is NOT sized. The number it would be sized at rides
        # alongside so the page can say what confirming the starter is
        # worth, but stake_units — the field the journal and every stake
        # chip read — stays zero until it is a bet.
        "stake_units": to_units(stake_fraction, card["odds"]),
        "stake_if_confirmed_units": to_units(
            card.get("stake_if_confirmed") or 0.0, card["odds"]),
        "grade": "Conditional" if conditional else card["grade_label"],
        "cfb_grade": card["grade"],
        "attention_tier": card["attention_tier"],
        "volatility": card["volatility"],
        "conditional": conditional,
        "conditions_pending": card.get("conditions_pending", []),
        "situational_tags": card.get("situational_tags", []),
        "book": play.get("book", ""),
        "recommended": not conditional,
        "reasons": reasons,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?",
                    default=datetime.date.today().isoformat())
    ap.add_argument("--odds", action="store_true")
    ap.add_argument("--cached-odds", action="store_true")
    ap.add_argument("--out", default="web/data/cfb.json")
    ap.add_argument("--backfill", metavar="START:END",
                    help="ingest completed games across a date span, then exit")
    args = ap.parse_args()

    conn = connect()
    if args.backfill:
        start, _, end = args.backfill.partition(":")
        got = cfbdata.load_results(start, end or start)
        n = ingest_results(conn, got)
        print(f"CFB backfill {start}–{end or start}: {n} finished game(s) stored.")
        return

    day = datetime.date.fromisoformat(args.date)
    out: dict = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "date": args.date, "sport": "cfb", "generated_from": "live-cfb",
        "games": [], "recommendations": [], "game_bets": [],
        "long_shots": [], "longshot_watch": [],
        "market_scan": {"stale": [], "arbs": [], "middles": [], "low_holds": [],
                        "longshots": []},
        "counts": {"props_analyzed": 0, "recommended": 0},
    }

    # Team identity ships in the payload — 134 schools is exactly the list
    # that goes stale in a checked-in file.
    try:
        teams = cfbdata.parse_teams(cfbdata.fetch_teams())
    except DataUnavailable:
        teams = {}
    out["teams"] = teams
    lookup = cfbdata.team_lookup(teams)

    try:
        confs = cfbdata.fetch_conferences()
        games = cfbdata.parse_scoreboard(cfbdata.fetch_scoreboard(args.date),
                                         confs)
    except DataUnavailable as exc:
        # KEEP THE LAST GOOD BOARD. This used to publish `out` — an empty
        # payload carrying the error as its note — which meant one 403 or
        # one timeout from ESPN replaced a full Saturday board with a
        # blank page, and left it blank until a later cycle happened to
        # succeed. A stale board is worse than a fresh one and far better
        # than no board; the masthead's stale bar already tells a reader
        # how old what they are looking at is.
        #
        # It is also the pattern the rest of the codebase already uses —
        # pm_build's "keeping last board" on the same exception — so CFB
        # was the outlier, not the precedent.
        #
        # Nothing is written at all in that case, deliberately: rewriting
        # the file would refresh `generated_at` and hide the very
        # staleness the reader needs to see, and republishing a public
        # copy through the gate would overwrite the unredacted full board
        # with the redacted one.
        if _has_board(args.out):
            print(f"CFB {args.date}: schedule unreachable — {exc}\n"
                  f"  Keeping the last board rather than publishing an "
                  f"empty one.")
            return
        out.update(status="unreachable", note=str(exc))
        _write(out, args.out)
        print(f"CFB {args.date}: schedule unreachable — {exc}\n"
              f"  No previous board to keep, so an empty one was published "
              f"with the reason on it.")
        return

    # Results keep the ratings honest; the surrounding boards give the
    # letdown / lookahead reads. Both are keyless and cached for a day.
    history = cfbdata.load_range(_iso(day - datetime.timedelta(days=RESULT_WINDOW_DAYS)),
                                 _iso(day - datetime.timedelta(days=1)))
    ingest_results(conn, [g for g in history if g["completed"]])
    ingest_results(conn, [g for g in games if g["completed"]])
    upcoming = cfbdata.load_range(_iso(day + datetime.timedelta(days=1)),
                                  _iso(day + datetime.timedelta(days=NEIGHBOUR_DAYS)))
    prev, nxt = cfbcontext.neighbours(history, upcoming)

    # THIS season only. College rosters turn over ~25% a year, so blending
    # six ingested seasons would rate a team on players who have graduated
    # — and it is exactly the gap the recruiting prior below exists to fill
    # while the current season is still young. The VARIANCE fit underneath
    # deliberately uses every season it can get: how far games land from a
    # projection is a property of the sport, not of one roster.
    ratings = teamrates.compute_team_ratings(conn, "cfb", shrink=8.0,
                                             seasons=[day.year])
    fit = cfbratings.fit_from_history(conn, ratings)
    cfbratings.install(fit)

    # §5/§6 — the preseason prior, built from high-school recruiting. In
    # September a team's own results are two games against opponents nobody
    # has measured either; without this the model quietly asserts that an
    # unproven Alabama and an unproven Kent State are both average.
    talent_report = attach_talent(conn, ratings, day.year, lookup)
    ratings = talent_report.pop("ratings")
    out["talent"] = talent_report

    store = cfbstatus.load_store()
    games = [cfbstatus.annotate_game(g, store) for g in games]

    out["games"] = [{"home": g["home"], "away": g["away"],
                     "date": g.get("date") or args.date,
                     "kickoff": g.get("kickoff", ""),
                     "label": g.get("label", ""),
                     "home_conference": g.get("home_conference", ""),
                     "away_conference": g.get("away_conference", ""),
                     "home_rank": g.get("home_rank"),
                     "away_rank": g.get("away_rank"),
                     "attention_tier": attention_tier(g),
                     "qb_confirmed": g.get("qb_confirmed", False),
                     "venue": g.get("venue", ""), "indoor": g.get("indoor", False),
                     "state": g.get("state", "scheduled"),
                     # The shape every other league's payload speaks. The
                     # Live tab keeps a game with live.state == "live" and
                     # reads its score off the same dict — CFB carried only
                     # the top-level state, so a Saturday in progress never
                     # appeared there at all. The scoreboard parser had the
                     # score and the clock the whole time.
                     "live": {"state": g.get("state", "scheduled"),
                              "home_score": g.get("home_score"),
                              "away_score": g.get("away_score"),
                              "period": g.get("detail", "")}}
                    for g in games]
    out["ratings"] = {"fitted": fit.fitted, "games": fit.games,
                      "margin_sd": fit.margin_sd, "total_sd": fit.total_sd,
                      "home_field": fit.home_field,
                      "scoring_baseline": fit.scoring_baseline,
                      "note": fit.note}
    out["probation"] = fit.probation
    out["tuning"] = {"calibrated": fit.fitted, "inherited_from": "",
                     "note": fit.note}
    out["qb"] = cfbstatus.summary(games)

    if not games:
        out.update(status="offseason",
                   note="No FBS games on this date. The engine (attention "
                        "tiers, the two refusals, the 0–100 grade and the "
                        "slate caps) is built and tested — it goes live with "
                        "the schedule.")
        _write(out, args.out)
        print(f"CFB {args.date}: no games. Wrote {args.out}")
        return

    priced, odds_note = ({}, "no odds requested — engine ran with no "
                             "bettable prices")
    if args.odds or args.cached_odds:
        priced, odds_note = attach_odds(
            games, lookup, cache_only=args.cached_odds and not args.odds)
    for gd, g in zip(out["games"], games):
        lines = priced.get(g["game_id"]) or {}
        gd["spread"] = (lines.get("spread") or [None])[0]
        gd["total"] = (lines.get("total") or [None])[0]

    # Live win-probability track — the wiring every other league carries
    # ("we should be showing that for ALL live games"). CFB waited on one
    # thing: the other builds hand `pull_and_record` a hand-written
    # {feed name -> abbr} table, and 134 schools is exactly the list that
    # goes stale in a checked-in file. So the feed's names resolve through
    # the same runtime lookup the odds attach already trusts. The pull is
    # behind the paid-odds flag AND a live game (the budget discipline
    # test_live_line_chart pins for MLB); the attach is unconditional —
    # the history is on disk and drawing it is free.
    try:
        from engine import livelines as _ll

        class _FeedNames:
            """dict-shaped adapter: livelines calls .get(feed_name)."""

            def __init__(self, lk):
                self._lk = lk

            def get(self, name, default=None):
                return cfbdata.resolve_team(name or "", self._lk) or default

        _live_games = [gd for gd in out["games"]
                       if (gd.get("live") or {}).get("state") == "live"]
        if _live_games and args.odds:
            _n, _note = _ll.pull_and_record("cfb", _FeedNames(lookup))
            if _n:
                print(f"  Live line: {_note}")
        _midnight = datetime.datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0).timestamp()
        _tracked = _ll.attach(out["games"], "cfb", since=_midnight)
        if _tracked:
            print(f"  Live line: charting {_tracked} game(s)")
    except Exception as _exc:                                 # noqa: BLE001
        print(f"  ⚠️  live line tracking unavailable: {_exc}")

    plays = build_plays(games, priced, ratings, fit, prev, nxt)
    by_id = {g["game_id"]: g for g in games}
    result = run_cfb_slate(plays, meta={
        "games": len(games), "priced": len(priced), "odds": odds_note,
        "ratings": out["ratings"], "qb": out["qb"]})

    # Match each verdict back to the play that produced it, so the shared
    # card keeps the pricing reasons the model actually used.
    play_by_key = {(p["market"], p["game"]["game_id"], p["selection"]): p
                   for p in plays}

    def _shared(card):
        p = play_by_key.get((card["market"], card["game_id"], card["selection"]))
        g = by_id.get(card["game_id"])
        return to_game_bet(card, p or {}, g) if p and g else None

    bets = [b for b in (_shared(c) for c in result["plays"]) if b]
    conditionals = [b for b in (_shared(c) for c in result["holds"]) if b]
    # Conditionals ride on the same board, flagged and unstaked, because a
    # separate page for them is a page nobody opens.
    out["game_bets"] = bets + conditionals
    # The pass list on a 60-game Saturday is ~180 markets; shipping all of
    # it would make the payload the slowest thing on a phone. The near
    # misses are the part that says something.
    out["cfb"] = {
        "near_misses": result["near_misses"],
        "no_qualifying": result["no_qualifying"],
        "exposure": result["exposure"],
        "counts": result["counts"],
        "by_tier": result["by_tier"],
        "pass_list": sorted(result["pass_list"],
                            key=lambda p: -(p.get("edge") or 0))[:20],
    }
    out["counts"] = {"props_analyzed": len(plays),
                     "recommended": len(bets),
                     "conditional": len(conditionals),
                     **result["counts"]}
    out["status"] = "slate"
    out["no_qualifying"] = result["no_qualifying"]

    try:
        from engine import ledger
        lconn = ledger.connect()
        n = ledger.log_recommendations(lconn, {"sport": "cfb",
                                               "date": args.date,
                                               "recommendations": [],
                                               "game_bets": bets})
        settled = ledger.settle_from_history(lconn, conn, sport="cfb")
        if n or settled:
            ledger.export_json(lconn, "web/data/record.json")
            print(f"Journal: {n} CFB bet(s) logged, {settled} settled.")
    except Exception as exc:
        print(f"⚠️  CFB journal skipped: {exc}")

    _write(out, args.out)
    conn.close()
    print(f"CFB {args.date}: {len(games)} game(s), {len(priced)} priced → "
          f"{len(bets)} play(s), {len(conditionals)} conditional(s). "
          f"Wrote {args.out}")
    if not fit.fitted:
        print("  ⚠️  Variance is a prior, not a fit — this board is journaled "
              "and graded, not staked.")
    if result["no_qualifying"]:
        print("  No qualifying plays at current numbers — the expected output "
              "on most Saturdays, not a failure.")


def _has_board(path: str) -> bool:
    """Is there already a published board here with games on it?

    "The file exists" is not the question — a previous run that also
    failed leaves a zero-game payload behind, and keeping THAT is keeping
    nothing. Games are the test because they are what the page draws
    before any pricing happens.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return bool((json.load(fh) or {}).get("games"))
    except (OSError, ValueError):
        return False

def _write(out: dict, path: str) -> None:
    # §14: screen the board for parlays last, over the plays that already
    # cleared the singles gates. CFB carries the highest bar in the system —
    # 8 points for three legs, one ticket per Saturday, and December closed
    # entirely (§6.4) — all of which lives in engine/parlays.py.
    # The outside view: what similar past spots actually did, counted off
    # CFB's own logs. Evidence only, never a price input.
    from engine.pipeline import _attach_comps
    out["comps"] = _attach_comps(out.get("recommendations") or [], "cfb")
    from engine.parlays import attach
    attach(out, "cfb")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    gate.publish(out, p)


if __name__ == "__main__":
    main()
