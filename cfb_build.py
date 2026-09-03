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
from engine.cfb.model import LOW, MARQUEE, STANDARD, attention_tier
from engine.cfb.pipeline import run_cfb_slate, store_key as _store_key
from engine.db import connect, upsert_games
from engine.odds import expected_value
from engine.sources import cfbdata
from engine.sources.fetch import DataUnavailable
from engine import gate

# How far back each build re-reads results. A season fills the table one
# rolling window at a time; --backfill does a whole span in one go.
RESULT_WINDOW_DAYS = 14
#: How far past an empty date the build hunts for the next slate. Six
#: covers the longest quiet stretch a football season has (Sunday to
#: Friday); seven would start answering "what is on NEXT Saturday" on a
#: Saturday morning before the feed fills, which is a different question.
LOOKAHEAD_DAYS = 6
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
    # Every name this board resolves is written down (engine/cfbteams):
    # the harvest needs the book's spelling → our abbreviation, and this
    # loop is the only place in the system where both halves exist.
    learned: dict[str, str] = {}
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
        learned.update(team_map)
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
            # The event's own id rides along so the TD-quote pull below
            # can ask for player markets without a second events call.
            entry["event_id"] = ev.get("id", "")
            priced[game["game_id"]] = entry

    if learned:
        try:
            from engine import cfbteams
            n_new = cfbteams.remember(learned)
            if n_new:
                print(f"  CFB team map: learned {n_new} new school name(s) "
                      f"— closing-line harvests can now join them to bets.")
        except Exception:                                    # noqa: BLE001
            pass                     # telemetry never breaks a board

    note = f"{len(priced)} of {len(games)} games priced from 1 request"
    if unmatched:
        note += f" · {len(unmatched)} unmatched ({', '.join(unmatched[:3])}…)"
    if cache_only:
        note += " (cached)"
    return priced, note


#: The player markets ONE college event call buys. The meter bills per
#: market per region, so asking for all five in one request costs exactly
#: what five separate requests would — and saves four round trips, four
#: cache entries and any chance of the five disagreeing about a game.
#:
#: Anytime TD feeds the long-shot board (engine/cfb/tds); the other four
#: are the prop board's, and they are the same Odds API keys the NFL
#: buys because it is the same sport.
PLAYER_MARKETS = ["player_anytime_td", "player_pass_yds",
                  "player_rush_yds", "player_reception_yds",
                  "player_receptions"]

#: What one game costs, by the API's own rule — one credit per market per
#: region, and every request this file makes is one region.
CREDITS_PER_EVENT = len(PLAYER_MARKETS)

#: The most games a player pull will EVER touch, before the budget gets a
#: say. Player markets are event-scoped where the whole game board above
#: is three credits flat, so an uncapped Saturday would be sixty games ×
#: five markets = three hundred credits a cycle. This is the "worth it"
#: ceiling — the games most worth a card — and `oddsbudget.
#: affordable_events` is the "can we" one; the pull takes the lower.
PLAYER_EVENT_CAP = 12

#: Only games kicking off inside this window get a player pull. A quote
#: for Thursday bought on Monday is four days of line movement we would
#: be pricing against.
PLAYER_WINDOW_HOURS = 36

#: Attention tier, as a sort key. WRITTEN DOWN BECAUSE THE OBVIOUS
#: VERSION IS WRONG: the tiers are the strings "marquee", "standard" and
#: "low", and sorting a game board by that string ascending puts LOW
#: first — l < m < s. The cap has therefore been spending its twelve
#: credits on the Tuesday MAC games and skipping the ranked Saturday
#: ones, which is the exact opposite of what the cap was written to do
#: ("chosen by attention tier then kickoff") and is invisible from the
#: outside: the board fills up either way.
_TIER_ORDER = {MARQUEE: 0, STANDARD: 1, LOW: 2}


def attach_player_quotes(games: list[dict], priced: dict, cache_only: bool,
                         api_key: str | None = None,
                         now=None, cap: int | None = None
                         ) -> tuple[dict, dict, str]:
    """Player quotes for the board's best games — one call per game.

    Returns ``(scorers, lines, note)``:

      * ``scorers`` — ``{game_index: {norm_name: [quotes]}}`` keyed by
        each game's INDEX in ``games``, which is what
        `engine.cfb.tds.build_cfb_td_longshots` reads;
      * ``lines`` — ``{(norm_name, market): [SportsbookLine]}`` for the
        yardage/reception props, which is what `engine.cfb.props.
        attach_lines` reads;
      * ``note`` — what was pulled, what it cost, and what was left out,
        for the board to say out loud.

    ``cap`` is the number of games this pull may buy; None asks the
    budget pacer. Games are ordered by attention tier, then by whether
    the game board has a spread and a total on them, then by kickoff.

    THE SPREAD/TOTAL CHECK IS A PREFERENCE HERE AND USED TO BE A FILTER.
    It was the touchdown model's requirement — no implied total, no
    script, no scorer price — and it was applied to the whole pull
    because the whole pull was touchdowns. A yardage prop needs neither,
    so a game whose full-game markets nobody posted is now merely LAST
    in the queue rather than struck from it.
    """
    import datetime as _dt

    from engine.sources import oddsapi

    t = now or _dt.datetime.now(tz=_dt.timezone.utc)
    cands = []
    for i, g in enumerate(games):
        entry = priced.get(g["game_id"]) or {}
        if not entry.get("event_id"):
            continue
        kick = str(g.get("kickoff") or "").replace("Z", "+00:00")
        try:
            ko = _dt.datetime.fromisoformat(kick)
        except ValueError:
            continue
        if ko.tzinfo is None or ko <= t \
                or ko > t + _dt.timedelta(hours=PLAYER_WINDOW_HOURS):
            continue
        priceable = "spread" in entry and "total" in entry
        cands.append((_TIER_ORDER.get(attention_tier(g), 9),
                      0 if priceable else 1, ko, i, entry["event_id"]))
    cands.sort(key=lambda c: (c[0], c[1], c[2]))

    if cap is None:
        cap = PLAYER_EVENT_CAP
        try:
            from engine.oddsbudget import affordable_events
            cap = min(cap, affordable_events(CREDITS_PER_EVENT))
        except Exception:                                    # noqa: BLE001
            pass                       # a pacing hiccup never costs a board
    cap = max(0, int(cap))

    scorers: dict = {}
    lines: dict = {}
    pulled = 0
    for _tier, _pri, _ko, i, event_id in cands[:cap]:
        try:
            payload, _quota = oddsapi.fetch_event_odds(
                event_id, api_key, markets=PLAYER_MARKETS,
                sport="cfb", ttl=1800, cache_only=cache_only)
        except oddsapi.OddsAPIError:
            if cache_only:
                continue               # never paid for — nothing on disk
            break                      # a live failure ends the spend, not the build
        pulled += 1
        quotes: dict = {}
        for (norm, _mkt), qs in oddsapi.parse_event_scorers(payload).items():
            quotes.setdefault(norm, []).extend(qs)
        if quotes:
            scorers[i] = quotes
        for key, got in oddsapi.parse_event_lines(
                payload, oddsapi.SPORT_CONFIG["cfb"]["markets"]).items():
            lines.setdefault(key, []).extend(got)

    note = (f"player quotes: {pulled} of {len(cands)} eligible game(s) "
            f"pulled at {CREDITS_PER_EVENT} credit(s) each"
            + (" (cached)" if cache_only else ""))
    if cap < len(cands):
        # SAID ON THE BOARD, NOT ONLY IN THE LOG. A college Saturday the
        # budget can only half-buy looks exactly like a college Saturday
        # the books did not price, and the difference is the whole
        # question a reader is asking.
        note += (f" · {len(cands) - cap} left unpriced — the pull is capped "
                 f"at {cap} game(s) by attention tier "
                 f"({'budget pacing' if cap < PLAYER_EVENT_CAP else 'board policy'})")
    return scorers, lines, note


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
    #: WHAT THE PRIOR WAS BUILT FROM, because it is about to have two
    #: possible answers and the card must not conflate them.
    source = "composite"
    if not prior and blue:
        # THE HIGH-SCHOOL DATA WE ALREADY PAY FOR, USED INSTEAD OF
        # NOTHING. `talent_prior`'s note is right that blue-chip ratio
        # must not ADD to the composite — same star ratings, counted
        # twice. It says nothing about the case where the composite is
        # absent, and there the ratio is not a second view of a fact we
        # have, it is the only view. CFBD /talent returned no rows for
        # 2026 while /recruiting/players returned 229 teams, so the board
        # sat with no prior for three weeks next to data that could
        # carry one.
        #
        # FITTED ON ITS OWN SCALE, NEVER ON THE COMPOSITE'S. 2.451 points
        # per SD was measured against composite z-scores; blue-chip ratio
        # is a different variable and reusing that slope would be
        # applying a number fitted on one population to another. The fit
        # below runs on blue-chip z against the same realised margins,
        # and if it does not converge the prior stays off rather than
        # borrowing a slope that does not describe it.
        bc_by_year: dict = {}
        for y in range(year - 1, year - 5, -1):
            try:
                rows = cfbd.blue_chip_ratio(y)
            except DataUnavailable:
                continue
            got = {a: v.get("ratio") for a, v in
                   ((_abbr(s), v) for s, v in rows.items()) if a}
            if got:
                bc_by_year[y] = {k: v for k, v in got.items() if v is not None}
        bc_fit = (T.fit_points_per_sd(T.team_seasons_from_db(conn, bc_by_year))
                  if bc_by_year else None)
        if bc_fit is not None and bc_fit.fitted:
            ratios = {a: v.get("ratio") for a, v in blue.items()
                      if v.get("ratio") is not None}
            prior = T.talent_prior(ratios, bc_fit)
            fit, source = bc_fit, "blue_chip"
    blended, blend_report = T.apply_prior(ratings, prior, returning, portal)
    # Each sub-layer is reported separately. "The talent layer is on" and
    # "all four of its inputs arrived" are different facts, and a page that
    # cannot tell them apart will show a September prior built on
    # recruiting alone as though it also knew who transferred.
    layers = {"talent": len(talent), "blue_chip": len(blue),
              "returning": len(returning), "portal": len(portal)}
    missing = [k for k, v in layers.items() if not v]
    # AVAILABLE MEANS A PRIOR IS IN FORCE, not that the fetch did not
    # raise. Reported 2026-08-30 from the live board: a green tick and a
    # green border over the words "Preseason talent prior — 0 team(s)"
    # and "Not loaded: talent", three weeks running. `fetch_talent`
    # returned 200 with an empty array, which is not an exception, so
    # this said True and the page drew a success.
    #
    # An empty successful response and a full one are the same shape at
    # every layer between the API and the card. The only place the
    # difference exists is the row count, so that is what decides.
    in_force = bool(blend_report["teams"])
    report.update(
        ratings=blended if in_force else ratings, available=in_force,
        teams_with_prior=blend_report["teams"],
        # WHICH OF THE TWO SOURCES CARRIED IT, since they are not the
        # same claim and the weaker one must say so.
        prior_source=source,
        # WHICH LAYERS ANSWERED WITH NOTHING, as against which ones
        # failed. `_get` returns [] for a 200-with-no-rows and raises for
        # everything else, so a layer at zero here fetched cleanly and
        # had no data — a different problem with a different fix, and the
        # payload could not tell them apart.
        empty_layers=[k for k, v in {"talent": len(talent),
                                     "blue_chip": len(blue),
                                     "returning": len(returning),
                                     "portal": len(portal)}.items() if not v],
        portal_teams=blend_report.get("portal_teams", 0),
        blue_chip_teams=len(blue), returning_teams=len(returning),
        layers=layers, missing_layers=missing,
        fit={"points_per_sd": fit.points_per_sd, "fitted": fit.fitted,
             "samples": fit.samples, "r": fit.r, "note": fit.note},
        note=((f"Preseason prior from recruiting applied to "
               f"{blend_report['teams']} team(s); portal adjusted "
               f"{blend_report.get('portal_teams', 0)}. {fit.note}")
              + (" Built from the BLUE-CHIP RATIO, not the recruiting "
                 "composite, which returned no rows — the same "
                 "high-school ratings seen a coarser way, on a slope "
                 "fitted to that variable rather than borrowed."
                 if source == "blue_chip" else "")
              if in_force else
              (f"No prior is in force, so the board is running on results "
               f"only. The recruiting composite (CFBD /talent) returned "
               f"no rows for {year}."
               + (f" The blue-chip fallback had {len(blue)} team(s) of "
                  f"high-school data but its own slope would not fit, so "
                  f"nothing was applied rather than a borrowed one."
                  if blue else
                  " No high-school recruiting data arrived either."))
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
                                           home_ml, away_ml, context,
                                           sport="cfb")
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


# A card's market names are the SHARED vocabulary, not the CFB
# pipeline's — "side" becomes "spread" because that is what the ledger,
# the journal fit, the loss-pattern miner and every renderer call it.
# That mapping lived here as `BET_TYPES`, a second copy of a dict the
# pipeline also needed and did not have; see `pipeline.STORE_MARKET` for
# what its absence cost the calibration and closure gates. One of them
# had to be the source, and it is the one the gates read.


def to_game_bet(card: dict, play: dict, game: dict) -> dict:
    """A CFB verdict in the shape every other board's game bets use.

    The shared renderer already knows how to draw a spread, a total and a
    moneyline; what it does not know is attention tier or conditionals, so
    those ride along as extra keys and as reasons — nothing about the
    existing NFL/MLB rendering has to change.

    A REFUSED CARD COMES THROUGH HERE TOO, and `recommended` is what says
    so. `engine.cfb.model` promises a Group of Five game is "priced,
    shown with its number and its edge, never a play"; that promise is
    kept by turning the pass into a card like any other and flagging it,
    not by dropping it. So the flag is read off the verdict — a play is
    recommended, a hold and a pass are not — where it used to be `not
    conditional`, which called every pass a recommendation the moment
    one was allowed onto the board.
    """
    shared = dict(play.get("shared") or {})
    conditional = card["kind"] == "hold"
    refused = card["kind"] == "pass"
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
    elif refused:
        # WHY IT IS NOT A PLAY, on the card rather than only in a census
        # bucket. `evaluate_play` writes one sentence per refusal — the
        # Group of Five rule, the tier's edge bar, the grade floor — and
        # until now that sentence died with the pass list. It is the only
        # thing on a refused card a reader actually wants.
        reasons.append("NOT A PLAY — " + str(card.get("why") or "refused"))

    return {
        **shared,
        "bet_type": _store_key(card["market"]),
        "market": _store_key(card["market"]),
        "market_label": card["market_label"],
        "home": game["home"], "away": game["away"],
        "matchup": f"{game['away']} @ {game['home']}",
        "date": game.get("date", ""), "kickoff": game.get("kickoff", ""),
        # IN PLAY, SAID ON THE CARD. Both other sports stamp this in
        # their `_finish_bet` and college never did, so every consumer
        # that refuses a live game — `likely.from_game_bet` most
        # recently, since a pre-game model cannot price a game already
        # being played — was reading a key that was simply absent here
        # and admitting the row.
        "live": (game.get("live") or {}).get("state") == "live",
        "win_prob": card["p_model"], "fair_prob": card["p_market"],
        "edge": card["edge"], "odds": card["odds"],
        # THE BAR THIS EDGE WAS MEASURED AGAINST, as a number rather than
        # only as English inside a reason string. CFB's bar moves by
        # attention tier (2.5% / 3% / 4%), so "which of these came
        # closest" cannot be answered by sorting on edge alone — and that
        # question is the whole of §11's near-miss list, which the page
        # has never been able to compute for itself.
        "required_edge": card.get("required_edge"),
        "ev_per_unit": round(expected_value(card["p_model"], card["odds"]), 4),
        "confidence": round(card["grade"] / 10.0, 1),
        # A conditional is NOT sized. The number it would be sized at rides
        # alongside so the page can say what confirming the starter is
        # worth, but stake_units — the field the journal and every stake
        # chip read — stays zero until it is a bet.
        "stake_units": to_units(stake_fraction, card["odds"]),
        "stake_if_confirmed_units": to_units(
            card.get("stake_if_confirmed") or 0.0, card["odds"]),
        # …and the same shape for a board held back by an unmeasured
        # variance rather than an unconfirmed starter. The card can say
        # what the measurement is worth without pretending it is a bet.
        "stake_if_measured_units": to_units(
            card.get("stake_if_measured") or 0.0, card["odds"]),
        "on_probation": bool(card.get("on_probation")),
        "grade": "Conditional" if conditional else card["grade_label"],
        "cfb_grade": card["grade"],
        "attention_tier": card["attention_tier"],
        "volatility": card["volatility"],
        "conditional": conditional,
        "conditions_pending": card.get("conditions_pending", []),
        "situational_tags": card.get("situational_tags", []),
        "book": play.get("book", ""),
        "recommended": card["kind"] == "play",
        "reasons": reasons,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?",
                    default=datetime.date.today().isoformat())
    ap.add_argument("--odds", action="store_true")
    ap.add_argument("--cached-odds", action="store_true")
    ap.add_argument("--lines-odds", action="store_true",
                    help="Buy the GAME markets only — one request for the "
                         "whole board, three credits — and read player "
                         "quotes from cache. The middle tier between a full "
                         "pull nobody can afford and no pull at all.")
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
        "long_shots": [], "longshot_watch": [], "most_likely": [],
        "market_scan": {"stale": [], "arbs": [], "middles": [], "low_holds": [],
                        "longshots": []},
        "counts": {"props_analyzed": 0, "recommended": 0},
        # THE BOARD'S OWN FURNITURE, ON EVERY PATH. These lived inside
        # `if args.odds or args.cached_odds:` with the touchdown pull,
        # so a cycle that did not spend on odds — most of them, and
        # every early return — published a likelihood board with NO
        # trust line: no "picked on how likely it is", no "recorded, not
        # staked". That is precisely the confusion engine/boards was
        # written to end, and I had called it fixed for college.
        #
        # Neither depends on a price. `guide()` is a static description
        # of what each board IS, and `shelves()` groups whatever rows
        # exist — none, here, until the odds block fills them and
        # replaces this.
        "board_guide": _boards_guide(),
        "board_shelves": [],
    }

    # Team identity ships in the payload — 134 schools is exactly the list
    # that goes stale in a checked-in file.
    try:
        teams = cfbdata.parse_teams(cfbdata.fetch_teams())
    except DataUnavailable:
        teams = {}
    out["teams"] = teams
    lookup = cfbdata.team_lookup(teams)

    # THE ID MAP, WRITTEN DOWN AND APPLIED. History comes off the
    # sportsdataverse mirror keyed by ESPN's numeric team id; where that
    # backfill ran without this feed it keyed every school ``espn:61``,
    # and four seasons of measured player usage sat next to a board that
    # keys the same school ``UGA`` and therefore could not see any of it.
    # This build has both halves. Persist them so later backfills key
    # correctly from the start, then repair what already landed.
    if teams:
        try:
            from engine import cfbteams as _cfbteams, ingest as _cfbingest
            from engine import db as _cfbdb
            ids = {str(meta.get("id") or ""): abbr
                   for abbr, meta in teams.items() if meta.get("id")}
            _cfbteams.remember_ids(ids)
            fixed = _cfbingest.remap_cfb_team_keys(_cfbdb.connect(), ids)
            if fixed["teams"]:
                print(f"  CFB history: re-keyed {fixed['teams']} school(s) "
                      f"from ESPN ids to abbreviations — "
                      f"{fixed['games']:,} game row(s) and "
                      f"{fixed['player_logs']:,} player row(s) now join "
                      f"the board.")
            if fixed["unmapped"]:
                print(f"  CFB history: {len(fixed['unmapped'])} team id(s) "
                      f"not in the teams feed, still keyed by id "
                      f"(e.g. {', '.join(fixed['unmapped'][:3])})")
        except Exception as exc:                             # noqa: BLE001
            print(f"  CFB history re-key skipped: {exc}")

    try:
        confs = cfbdata.fetch_conferences()
        board = cfbdata.fetch_scoreboard(args.date)
        games = cfbdata.parse_scoreboard(board, confs)
        # WHAT THE FEED LISTED, BESIDE WHAT WE KEPT.
        #
        # `parse_scoreboard` drops any event whose two competitors do not
        # both carry an abbreviation, and it drops them silently. So an
        # empty `games` has two completely different causes: ESPN listed
        # nothing, or ESPN listed sixty games and every one was discarded
        # in that loop. Those need opposite fixes and the board recorded
        # neither, which is why 2026-08-29 — college football's opening
        # Saturday, when the page showed nothing — cannot be explained
        # from anything we still have.
        #
        # One integer, taken before the filter runs, settles it.
        listed = len(board.get("events") or [])
        if not listed:
            # LOOK AHEAD, THE WAY THE NFL BOARD ALWAYS HAS. Football is
            # not a daily sport: the NFL board builds a WEEK, so on the
            # Monday before Week 1 it shows sixteen games with Thursday
            # kickoffs — while this board, keyed to a single date,
            # showed "no games today" every Sunday-through-Thursday of
            # a running season. Asked on 2026-08-31, with Saturday's
            # full slate five days out and lines already posted: "NFL
            # is showing games and it doesn't even start for another
            # week, and yet CFB has started and isn't showing any."
            #
            # So an honestly blank date (listed == 0 — a parse failure
            # is a different problem and must keep saying so) advances
            # to the NEXT day the feed lists games, and the whole
            # pipeline — odds, touchdown pull, venues, journal — runs
            # on that slate. `args.date` moves WITH it so picks journal
            # under the date their games are actually played and settle
            # against the right results; `out["date"]` keeps the build
            # date, and `upcoming` says what the reader is looking at.
            # A day that cannot be fetched is skipped, not fatal: the
            # fallback is today's truthful empty board, never a claim.
            for ahead in range(1, LOOKAHEAD_DAYS + 1):
                nd = (day + datetime.timedelta(days=ahead)).isoformat()
                try:
                    nboard = cfbdata.fetch_scoreboard(nd)
                except DataUnavailable:
                    continue
                ngames = cfbdata.parse_scoreboard(nboard, confs)
                if not ngames:
                    continue
                board, games, listed = (nboard, ngames,
                                        len(nboard.get("events") or []))
                out["upcoming"] = {"date": nd, "days_ahead": ahead}
                args.date = nd
                print(f"CFB: nothing on {out['date']} — building the "
                      f"next slate, {nd} ({len(ngames)} game(s)).")
                break
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

    # THIS season, carried by LAST season until it can stand up — the same
    # `ratings_for_season` rule the NFL and MLB builds run, which this build
    # alone bypassed (CFB readiness audit, 2026-09-02). It read "this
    # season only" on the reasoning that six ingested seasons would rate a
    # team on players who have graduated, and that the recruiting prior
    # fills the gap. Two things were wrong with that in practice: the prior
    # is key-gated and worth 23% of the rating after one game, so 77% of a
    # Week-2 number was one result shrunk to a ninth of itself — every
    # team sat within a few points of zero, the model called LSU a 6-point
    # favourite the market had at 36.5, and the credibility guard refused
    # most of the slate; and §5's own preseason prior is "last year's
    # efficiency × returning production × talent", so last season IS part
    # of the spec. Replayed leak-free on 2023–2025 against closes: the
    # early-season (weeks 1–4) model-vs-close spread RMSE fell from 11.97
    # to 11.06 points and the early ROI at the close from −6.9% (638 bets)
    # to −3.1% (1,163) — still a losing number, stated as such; the pool
    # only lasts until the season averages four games a team, then this
    # season stands alone. The VARIANCE fit underneath uses every season it
    # can get: how far games land from a projection is a property of the
    # sport, not of one roster.
    #
    # And FCS results are OUT of an FBS team's rating once the teams feed
    # has said who is FBS: a non-FBS visitor carries an `espn:{id}` key
    # because it has no abbreviation, and a 70–0 buy game counted at full
    # weight was that team's whole rating for a fortnight. On a box where
    # the teams feed never answered every key is that fallback key, so the
    # exclusion is only asked for when the map actually loaded.
    _fallback = "espn:" if teams else None
    ratings, seasons_used = teamrates.ratings_for_season(
        conn, "cfb", day.year, shrink=8.0, exclude_prefix=_fallback)
    # …AND A SECOND MAP, FOR THE VARIANCE ONLY. `fit_from_history`
    # measures residuals around whatever ratings it is handed, and can
    # only use a game where BOTH teams are in the map — so passing the
    # current-season map meant that in week 1, with two teams rated, the
    # fit found no residuals at all, borrowed all three spreads from the
    # prior, and reported fitted=False. That flag is what
    # `engine.probation` reads: the whole college board would have sat
    # unstaked through the opening weeks with 3,132 measured games in the
    # table. The comment above always said the variance fit "uses every
    # season it can get"; until this map existed it did not.
    #
    # The two maps are not interchangeable. The board projects with the
    # current season because rosters turn over; the variance is a
    # property of the sport and wants every game there is.
    all_seasons = teamrates.compute_team_ratings(conn, "cfb", shrink=8.0,
                                                 exclude_prefix=_fallback)
    fit = cfbratings.fit_from_history(conn, all_seasons or ratings)
    # OPPONENT-ADJUSTED, since 2026-09-02 (Ethan, on the audit's third Ask:
    # "whatever u think"). §5 calls opponent adjustment "everything" in a
    # sport where a Sun Belt schedule and an SEC schedule are not
    # comparable numbers, and the plain rating above averages a team's
    # own margins as if they were. `teamrates.compute_adjusted_ratings`
    # solves offense and defence jointly with the opponent taken out, at
    # the same shrink, with the home field the fit above just solved.
    # Replayed leak-free on 2023–2025 against closes, same gates, same
    # dates: model-vs-close spread RMSE 8.23 → 7.62 points (weeks 1–4:
    # 11.06 → 9.86), ROI at the close −4.1% → −2.7% on ~1,300 bets, max
    # drawdown 81u → 66u. Not a profitable model — a less wrong one; the
    # plain map is kept for the first variance pass because the home
    # field has to be solved before the adjustment can use it, and the
    # variance is then re-fitted around the projection actually priced.
    ratings, seasons_used = teamrates.adjusted_ratings_for_season(
        conn, "cfb", day.year, shrink=8.0, exclude_prefix=_fallback,
        home_field=fit.home_field)
    all_seasons_adj = teamrates.compute_adjusted_ratings(
        conn, "cfb", shrink=8.0, exclude_prefix=_fallback,
        home_field=fit.home_field)
    fit = cfbratings.fit_from_history(conn, all_seasons_adj or all_seasons
                                      or ratings)
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

    # Kickoff weather, joined on the VENUE ESPN names (so neutral sites
    # read the right sky) with CFBD's coordinates and Open-Meteo's hourly
    # board. Degrades to nothing without the CFBD key or with either feed
    # down — a game that cannot be answered keeps weather_checked False
    # and the card keeps saying "weather not pulled".
    try:
        from engine.cfb import wx as _wx
        n_wx = _wx.attach(games, _wx.venue_index(_wx.fetch_venues()))
        outdoor = sum(1 for g in games if not g.get("indoor"))
        print(f"Weather: {n_wx} of {len(games)} game(s) stamped "
              f"({outdoor} outdoor)")
    except Exception as exc:                              # noqa: BLE001
        print(f"Weather: skipped — {type(exc).__name__}: {exc}")

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
                     # What the Weather page and the game card read; the
                     # park_name key is the shape every other league uses.
                     "weather": g.get("weather"),
                     "weather_checked": g.get("weather_checked", False),
                     "park_name": g.get("venue", ""),
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
                      "seasons_used": seasons_used,
                      "fcs_excluded": bool(_fallback),
                      "method": "opponent-adjusted",
                      "margin_sd": fit.margin_sd, "total_sd": fit.total_sd,
                      "home_field": fit.home_field,
                      "scoring_baseline": fit.scoring_baseline,
                      "note": fit.note}
    # The offseason value. Overwritten from the slate result below, once
    # there is one — see the note there.
    out["probation"] = fit.probation
    out["tuning"] = {"calibrated": fit.fitted, "inherited_from": "",
                     "note": fit.note}
    out["qb"] = cfbstatus.summary(games)
    # Published, not merely printed: a log line is gone by the time
    # anyone asks, and the question this answers is always asked later.
    out["feed"] = {"listed": listed, "kept": len(games)}
    if listed and not games:
        print(f"CFB {args.date}: the feed listed {listed} game(s) and the "
              f"parser kept none of them — this is a PARSE failure, not an "
              f"empty schedule.")

    if not games:
        # "OFFSEASON" WAS AN INTERPRETATION ASSERTED AS A FACT, and on
        # 2026-08-30 it was the wrong one: the board read `status:
        # "offseason"` with a note saying the engine "goes live with the
        # schedule", the day AFTER the college season opened.
        #
        # An empty fetch has more than one cause. There may genuinely be
        # no FBS games on this date — a Tuesday in June, or a Sunday in
        # September. The date may fall inside a running season on a quiet
        # day. Or the feed may have answered with nothing. Only the first
        # is the offseason, and the difference is exactly what a reader
        # seeing an empty board needs.
        #
        # The build can tell them apart from data it already pays for:
        # every successful build fetches RESULT_WINDOW_DAYS of history,
        # so those days are in the same 24-hour cache this reads.
        if listed:
            # The schedule was not empty; we discarded all of it. Saying
            # "no games today" here would be the board reporting the
            # league's state when what failed was our own parser.
            out.update(status="feed unreadable",
                       note=f"The schedule feed listed {listed} game(s) for "
                            f"this date and none could be read — every one "
                            f"was missing a team the parser could identify. "
                            f"This is a fault on our side, not an empty "
                            f"slate, and it is being looked at.")
            _write(out, args.out)
            print(f"CFB {args.date}: {listed} listed, 0 readable. "
                  f"Wrote {args.out}")
            return
        recent = _recent_games(day, lookup)
        if recent is None:
            # We could not look. Neither "offseason" nor "quiet day" is
            # a claim we have earned.
            out.update(status="schedule unknown",
                       note="No games came back for this date, and the "
                            "ten-day lookback that would say whether the "
                            "season is running could not be fetched "
                            "either. This is not a claim that there is no "
                            "football — it is that we cannot currently "
                            "tell, and would rather say so.")
            _write(out, args.out)
            print(f"CFB {args.date}: 0 games and no lookback — schedule "
                  f"unknown. Wrote {args.out}")
            return
        if recent:
            last = max(g.get("date", "")[:10] for g in recent)
            out.update(status="no games today",
                       note=f"No FBS games on this date, but the season is "
                            f"running — {len(recent)} game(s) in the last "
                            f"{NEARBY_DAYS} days, most recently {last}. This "
                            f"is a quiet date, not the offseason.")
            _write(out, args.out)
            print(f"CFB {args.date}: no games today (season running, last "
                  f"{last}). Wrote {args.out}")
            return
        out.update(status="offseason",
                   note="No FBS games on this date, and none in the last "
                        f"{NEARBY_DAYS} days either. The engine (attention "
                        "tiers, the two refusals, the 0–100 grade and the "
                        "slate caps) is built and tested — it goes live with "
                        "the schedule.")
        _write(out, args.out)
        print(f"CFB {args.date}: no games, none nearby. Wrote {args.out}")
        return

    priced, odds_note = ({}, "no odds requested — engine ran with no "
                             "bettable prices")
    if args.odds or args.cached_odds or args.lines_odds:
        # TWO PULLS, TWO PRICES, AND THEY USED TO SHARE ONE PERMISSION.
        #
        # This one is the cheap half: full-game markets for the ENTIRE
        # board in a single request, three credits however many games are
        # on it. The player-quote pull below is the dear half — one call
        # per game, five markets each, sixty credits for a twelve-game
        # queue — and `CFB_ODDS_COST` authorises the SUM of the two.
        #
        # So a budget that could not carry the player pull did not buy the
        # game lines either, and college published a board with no
        # moneyline, no spread, no total, and therefore no game bets and
        # nothing on Best Bets. Ethan, 2026-09-03: "we still do not show
        # any cfb props or best bets or anything and there is games
        # today." The two halves are separately authorised now, and
        # --lines-odds is the launcher saying it could afford this one.
        priced, odds_note = attach_odds(
            games, lookup,
            cache_only=args.cached_odds and not (args.odds or args.lines_odds))
    for gd, g in zip(out["games"], games):
        lines = priced.get(g["game_id"]) or {}
        gd["spread"] = (lines.get("spread") or [None])[0]
        gd["total"] = (lines.get("total") or [None])[0]

    # KEEP THE LINES THIS BOARD ALREADY PAID FOR. Free — the prices are in
    # memory — and it is the closing number the spread/total/moneyline
    # model is graded on later. NFL and MLB have done this on every build
    # (engine/lineledger); CFB never did, so its game bets settled with no
    # close and no CLV. The teams here are OUR abbreviations already
    # (resolve_team ran in attach_odds), so these rows join to the journal
    # without the harvest's name map being involved at all.
    if priced:
        try:
            from engine import lineledger, db as _lhdb
            _rows = []
            for g in games:
                e = priced.get(g["game_id"]) or {}
                if not e:
                    continue
                row = {"home": g["home"], "away": g["away"],
                       "date": str(g.get("date") or args.date)[:10]}
                if e.get("spread"):
                    row["spread"], row["spread_home_odds"], \
                        row["spread_away_odds"] = e["spread"]
                if e.get("total"):
                    row["total"], row["total_over_odds"], \
                        row["total_under_odds"] = e["total"]
                if e.get("moneyline"):
                    row["home_ml"], row["away_ml"] = e["moneyline"]
                _rows.append(row)
            _lc = _lhdb.connect()
            _n_lines = lineledger.record(_lc, "cfb", _rows)
            _lc.close()
            if _n_lines:
                print(f"  Line ledger: {_n_lines} CFB game-line row(s) stored "
                      f"(free — closes for CLV).")
        except Exception as _exc:                            # noqa: BLE001
            print(f"  ⚠️  CFB line ledger skipped: {_exc}")

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
    # PROBATION IS NOW A FACT ABOUT THE STAKES, not a banner beside them.
    # `run_cfb_slate` zeroes every size when the variance is a prior, so
    # this key and the board finally agree with each other — it is read
    # off the slate result rather than off `fit` precisely so the two can
    # never drift apart again.
    out["probation"] = bool(result.get("probation", fit.probation))
    # THE MEASUREMENT, ON THE BOARD RATHER THAN ONLY ON THE CARDS. With
    # college football's spread and moneyline shrinks measured at zero
    # there are Saturdays with NO game bets at all, and a note that only
    # rides on a card has nothing to ride on. Without this the page falls
    # through to "waiting on real sportsbook prices", which is false when
    # the prices are there and the model simply turned the card down.
    try:
        from engine.gamecal import board_notes
        out["line_calibration"] = board_notes("cfb")
    except Exception:                                        # noqa: BLE001
        out["line_calibration"] = {}
    out["probation_reasons"] = result.get("probation_reasons") or []
    out["advisories"] = result.get("advisories") or []

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
    # AND THE REFUSALS, which is what `game_bets` has meant everywhere
    # else in this codebase since the day it was written. `_game_bets` in
    # engine/pipeline (NFL) and engine/mlb/pipeline both append EVERY
    # priced market and let `recommended` be a field on the row —
    # nfl_build's own log line prints "64 bet(s) → 13 recommended". The
    # front end agrees: `passesGameBet` in web/js/app.js filters
    # `grade !== "Pass"` at render time, which is only meaningful if Pass
    # rows are expected to be in the payload. College was the one
    # producer that shipped the survivors instead, and three things broke
    # because of it:
    #
    #   * `engine.cfb.model` says a Group of Five game is "priced, SHOWN
    #     with its number and its edge, never a play". The decision
    #     (Ethan, 2026-09-02) was about whether the money follows; the
    #     gate is the first return in `evaluate_play`, so shipping only
    #     survivors turned a rule about MONEY into a rule about
    #     VISIBILITY and the games vanished off every surface.
    #   * `likely.from_game_bet` reads this key and nothing else, so
    #     college moneylines — the best-ranked game market in the system
    #     at 0.752 AUC — could never reach the Most Likely board on a
    #     slate where the edge board published nothing. A ranking board
    #     was being emptied by an EDGE verdict, which is not what it
    #     ranks on. Reproduced on a synthetic nine-game Group of Five
    #     card built through this same chain: 0 game rows before, 20
    #     after, the moneylines ranked and the rest labelled leans.
    #   * `pricedButQuiet()` in web/js/app.js opens with
    #     `const priced = (d.game_bets || []).length; if (!priced)
    #     return null;`, so the one branch written to say "the card is
    #     priced and the model turned it all down" was dead on exactly
    #     the board it exists for, and the page fell through to "waiting
    #     on real sportsbook prices" — false on a night with 9 of 11
    #     games priced. It asks `filter(passesGameBet).length` next,
    #     which is the question it actually wants and which still works.
    #
    # Unstaked and unrecommended by construction: a pass never carried a
    # `stake_fraction`, and `to_game_bet` now reads `recommended` off the
    # verdict rather than off `not conditional`.
    refused = [b for b in (_shared(c) for c in result["pass_list"]) if b]
    # Conditionals ride on the same board, flagged and unstaked, because a
    # separate page for them is a page nobody opens.
    out["game_bets"] = bets + conditionals + refused
    # THE CHART EVERY ONE OF THOSE BETS OPENS ONTO. Same gap the NFL's
    # games-only fallback had (fixed 2026-08-26, Ethan: "on nfl im not
    # able to click on the game props and it show me the bar graph"):
    # a game bet's history is its team's last results, and without
    # `team_recent` in the payload every CFB spread and total opened a
    # page whose centrepiece said "No recent results for this team yet".
    #
    # TWO SEASONS, deliberately. `recent_games` defaults to the season
    # the date falls in, which is right in November and wrong on the
    # opening Saturday — week one would chart nothing at all. The NFL's
    # board effectively spans seasons already (its periods are week
    # numbers, so the date filter never bites), and a reader looking at
    # the same kind of card in two leagues should not get last season's
    # form in one and an empty panel in the other. Empty until the
    # results are ingested either way: `cfb_build.py --backfill` is what
    # fills the prior season.
    try:
        from engine.db import connect as _tl_connect
        from engine.seasons import season_of as _season_of
        # ALIASED AWAY FROM `_recent_games`, which is a MODULE-LEVEL
        # function this same `main()` calls 175 lines above. Python binds
        # a name for the WHOLE function body wherever it is assigned, and
        # an `import ... as` is an assignment — so this line made every
        # earlier reference an unbound local and `main()` died with
        # `UnboundLocalError: cannot access local variable
        # '_recent_games'` on every cycle it reached the no-games branch.
        #
        # That is why the college board was frozen: not a feed, not a
        # timeout, not the offseason logic. The build crashed before it
        # could write, so the file kept its last good payload and the
        # status word on it aged into a fossil.
        from engine.teamlogs import recent_games as _tl_recent_games
        _season = _season_of("cfb", args.date)
        _tlc = _tl_connect()
        out["team_recent"] = _tl_recent_games(
            _tlc, "cfb",
            {t for g in out["games"] for t in (g.get("home"), g.get("away")) if t},
            before=args.date, seasons=[_season - 1, _season])
        _tlc.close()
    except Exception as exc:                                  # noqa: BLE001
        print(f"  ⚠️  team logs skipped: {exc}")
    # THE ROWS ARE GONE FROM HERE, and what is left is the arithmetic.
    #
    # `pass_list` was a 20-row copy of the refusals and `near_misses` the
    # top three of them, published since before either could be drawn:
    # nothing in web/js/app.js has ever read `d.cfb` at all. They were
    # duplication with no reader, and duplication of the one thing this
    # payload has to be careful with — `gate.PAID_KEYS` names both, and
    # both shipped through the paywall in full because `redact` only
    # walked the top level. Fixing the stripper was the urgent half;
    # deleting the second copy is the half that stops it happening again.
    #
    # Nothing is lost. Every refusal now rides in `game_bets` with its
    # price, its edge, the bar it missed and the gate's own sentence
    # (`to_game_bet`), which is a superset of what was trimmed to 20
    # here — and the page computes the near-miss list from those rows
    # (`nearestMisses`), so §11's "closest misses" is finally drawn
    # rather than merely published.
    #
    # The counts stay. They are cheap, they carry no priced row, and
    # `counts` is what tells a reader whether a market was refused or
    # never built at all — the one question this board could not answer
    # about itself on 2026-09-03.
    out["cfb"] = {
        "no_qualifying": result["no_qualifying"],
        "exposure": result["exposure"],
        "counts": result["counts"],
        "by_tier": result["by_tier"],
    }

    # THE PLAYER BOARD (Ethan, twice on 2026-09-02: "make sure everything
    # I'm telling you to do for NFL is also being implemented for college
    # football because I'm still not seeing any props for college
    # football"). College had four seasons of ingested player production
    # and no way to turn it into a prop, so `recommendations` was a
    # literal `[]` from the top of this function to the journal at the
    # bottom — the Best Bets page, the every-market box and the Most
    # Likely shelves all read that key and all had nothing to read.
    #
    # THROUGH THE SAME EVALUATION THE NFL USES, not a college copy of it.
    # `pipeline.price_props` is the shared step; `engine.cfb.props` only
    # supplies the slate. That is what stops the two boards drifting into
    # different arithmetic about the same kind of bet, and it is why the
    # front end needs no college branch to render these rows.
    #
    # WITHOUT ODDS THEY ARE ANALYSIS, NOT BETS. Every prop carries a
    # proxy line until a book price replaces it, and `evaluate_prop`
    # refuses to call a proxy-priced row a market at all (`has_market`),
    # which the ledger's own skip rule and the likelihood board's gate
    # both check. So this runs on every cycle — it costs nothing but the
    # database — and produces a board that says how many players it
    # looked at rather than a page that says college has no players.
    prop_census: dict = {}
    # ONE PULL FOR BOTH PLAYER BOARDS. Anytime TD (the long-shot board)
    # and the four yardage markets (this one) come back in a single
    # event call per game — the meter bills per market, so two requests
    # for the same event cost exactly what one asking for both costs,
    # and one request cannot disagree with itself about a game.
    td_quotes: dict = {}
    prop_lines: dict = {}
    quotes_note = ("no odds pulled on this cycle — player prices are "
                   "metered per event, so they arrive on the cycles that "
                   "can afford them rather than every minute")
    if args.odds or args.cached_odds or args.lines_odds:
        try:
            # NOT bought by --lines-odds. Player markets are event-scoped
            # and cost five credits a game; the cheap tier exists because
            # it does not buy them. Cached quotes still attach — the last
            # paid pull's prices are better than none.
            td_quotes, prop_lines, quotes_note = attach_player_quotes(
                games, priced, cache_only=not args.odds)
            print(f"  {quotes_note}")
        except Exception as _qexc:                           # noqa: BLE001
            quotes_note = f"player quotes unavailable: {_qexc}"
            print(f"  ⚠️  {quotes_note}")

    try:
        from engine.cfb import props as _cfbprops
        from engine.pipeline import price_props as _price_props
        from engine.seasons import season_of as _prop_season_of
        _prop_games = [{**g, "spread": gd.get("spread"),
                        "total": gd.get("total"), "live": gd.get("live")}
                       for g, gd in zip(games, out["games"])]
        _prop_slate = _cfbprops.build_slate(
            conn, _prop_games, args.date,
            _prop_season_of("cfb", args.date), census=prop_census)
        # The book's number replaces the proxy wherever this pull bought
        # one. A prop with no line keeps its proxy, is analysed and
        # shown, and is never staked or journaled — `evaluate_prop`
        # reads the book name and refuses to call it a market.
        _matched, _total = _cfbprops.attach_lines(_prop_slate, prop_lines)
        prop_census["priced"] = _matched
        out["recommendations"] = _price_props(_prop_slate, sport="cfb")
        if prop_census.get("candidates"):
            print(f"  Player props: {prop_census['props']} market(s) across "
                  f"{prop_census['candidates']} placed player(s), "
                  f"{_matched} with a real book line "
                  f"({prop_census['transfers']} found under a former school, "
                  f"{prop_census['thin_history']} with too little history, "
                  f"{prop_census['below_volume']} below the volume floor; "
                  f"usage from {prop_census.get('usage_season')})")
        else:
            print("  Player props: no college player logs joined tonight's "
                  "teams — run `python3 ingest.py cfb --seasons 2022-2026`.")
    except Exception as _pexc:                               # noqa: BLE001
        # ON THE BOARD, NOT ONLY IN A LOG LINE NOBODY IS TAILING.
        #
        # This block fills the census and THEN prices, in that order, so a
        # raise in `price_props` leaves a census reporting hundreds of
        # markets and a `recommendations` list still holding the empty one
        # it was initialised with. From outside that is indistinguishable
        # from an honest "no edge anywhere tonight" — and it is not the
        # same fact at all. Measured on the droplet, 2026-09-03: 612
        # markets built, 70 carrying a real book line, and a Best Bets
        # page with nothing on it. Ethan: "there isnt even any best bets,
        # we should have best bets for cfb."
        #
        # The traceback's last frame rides along because "which line"
        # is the whole question and the message alone rarely answers it.
        import traceback as _tb
        _frames = _tb.extract_tb(_pexc.__traceback__)
        _where = ""
        if _frames:
            _f = _frames[-1]
            _where = f" at {Path(_f.filename).name}:{_f.lineno} in {_f.name}()"
        prop_census["error"] = f"{type(_pexc).__name__}: {_pexc}{_where}"
        print(f"  ⚠️  player props unavailable: {prop_census['error']}")
        _tb.print_exc()
    prop_census["quotes_note"] = quotes_note
    out["prop_census"] = prop_census
    # WHAT THE PULL COVERED, ON THE BOARD RATHER THAN IN THE LOG. The
    # shape NFL and MLB publish and the page already renders
    # (`oddsClockHTML`); college published none, so a Saturday the budget
    # could only half-buy read exactly like a Saturday the books had not
    # priced. Those are different facts and a reader is asking which.
    out["odds_status"] = {"at": out["generated_at"], "note": quotes_note,
                          "games_quoted": len(td_quotes),
                          "props_priced": prop_census.get("priced", 0)}

    # EVERY INGESTED MARKET FOR TONIGHT'S PLAYERS, the same key the NFL
    # and MLB boards publish for the Players page's market chips. Empty
    # on a box with no history database, which is a fresh clone.
    try:
        from engine import statlogs as _statlogs
        out["player_stats"] = _statlogs.for_board(
            out.get("recommendations") or [], "cfb")
    except Exception:                                        # noqa: BLE001
        out["player_stats"] = {}

    # THE TWO NUMBERS THE TILE NEEDS, named the way every other board
    # names them. `props_built` is how many the model projected from
    # history; `props_analyzed` is how many of those a book has actually
    # priced. The gap between them IS the diagnosis, and the page prints
    # it as one — "of 214 built from history — the rest have no book
    # price yet" — which is the honest answer to "why am I not seeing
    # any props for college football" on a cycle that has not bought
    # player odds. (The same shape `nba_build` publishes.)
    _built = list(out.get("recommendations") or [])
    out["counts"] = {"props_built": len(_built),
                     "props_analyzed": sum(1 for r in _built
                                           if r.get("has_market")),
                     "recommended": len(bets),
                     "conditional": len(conditionals),
                     # The GAME markets this board priced, which is what
                     # `props_analyzed` used to hold and what the CFB
                     # page's second tile used to relabel itself to
                     # show. Both numbers are real and they are
                     # different numbers; naming them separately is what
                     # lets the page stop special-casing college to tell
                     # them apart.
                     "markets_priced": len(plays),
                     **result["counts"]}

    # THE LONG-SHOT BOARD (Ethan, 2026-08-25: "fix the odds range for
    # long shot picks for nfl and CFB"). Anytime-TD quotes for the best
    # games on the card, priced by engine/cfb/tds — implied totals, each
    # player's share of team volume, the script, the opponent's scoring
    # generosity and our own kickoff forecast. Only with odds in play:
    # a scorer market has no proxy price worth modelling against.
    if args.odds or args.cached_odds or args.lines_odds:
        try:
            # --lines-odds bought no scorer quotes, but the LAST paid pull's
            # are on disk and `attach_player_quotes` read them back. A board
            # that has them and does not draw them is the same silence this
            # tier exists to break.
            from engine.cfb import tds as _tds
            quotes, td_note = td_quotes, quotes_note
            rows, census, watch = _tds.build_cfb_td_longshots(
                conn, out["games"], quotes, day.year)
            out["long_shots"] = rows
            # The most-likely-scorers list — shown, never journaled.
            out["longshot_watch"] = watch
            # THE MAIN BOARD, ranked by likelihood rather than edge. The
            # college board prices touchdowns and nothing else, so this
            # is that one market ordered honestly — but it belongs on the
            # same page as the NFL's for the same reason, and a sport
            # that publishes an empty one would read as broken rather
            # than as narrow.
            from engine.likely import build as _likely
            from engine import boards as _boards
            # THE CENSUS TRAVELS WITH THE BOARD. College's whole
            # likelihood board is watch rows, so when it comes up short
            # the reason is a refusal count and nothing else — and until
            # `likely.admissible` existed there were no refusals to
            # count, because the bar was only applied on the prop path
            # college does not use.
            _ml_census: dict = {}
            # THE GAME CARDS RIDE ALONG (Ethan, 2026-09-02: "we have no
            # money lines or spreads or totals"). `out["game_bets"]` is
            # already built above; `likely.from_game_bet` keeps the
            # markets college has been measured on — the moneyline ranks
            # at 0.752 over 2,729 replayed games; spreads and totals ride
            # as labelled leans — and refuses the conditionals, which are
            # holds and not picks.
            # THE PROP ROWS RIDE ALONG NOW. `likely.from_prop` gates
            # each one on `rankable(market, "cfb")` — college's own
            # measured AUC from `engine.rankfit`, never the NFL's
            # constants — and on `has_market`, so a proxy-priced row
            # cannot reach a shelf either. Passing them is therefore
            # safe before the measurement exists: the board shows what
            # it can defend and nothing else.
            out["most_likely"] = _likely(out.get("recommendations") or [],
                                         rows, watch, sport="cfb",
                                         census=_ml_census,
                                         game_bets=out.get("game_bets") or [])
            # AND WHY THE PROP HALF IS EMPTY, WHEN IT IS. College's
            # yardage markets have a model and, until the box holding
            # the logs walks them, no measurement — so `from_prop`
            # refuses every one of them before the census sees a row and
            # the shelf is silently absent. Silence is the wrong answer
            # here: "we have not measured this yet" and "nobody hit the
            # bar tonight" look identical on a page and are completely
            # different facts. The same sentence MLB and NBA publish,
            # counted per market so the funnel adds up.
            try:
                from engine.cfb.props import MARKETS as _pm
                from engine.likely import rankable as _rankable
                _unmeasured = [m for m in _pm if not _rankable(m, "cfb")]
                if _unmeasured and out.get("recommendations"):
                    _ml_census["no market measured to rank yet"] = \
                        _ml_census.get("no market measured to rank yet", 0) \
                        + len(_unmeasured)
            except Exception:                                # noqa: BLE001
                pass
            out["likely_census"] = _ml_census
            # THE SAME FURNITURE THE NFL BOARD CARRIES, and college had
            # none of it. `boardGuide` and the shelves both read the
            # payload, so a sport that omits them draws a likelihood
            # board with no trust line — no "picked on how likely it is",
            # no "recorded, not staked" — which is precisely the
            # confusion engine/boards was written to end. The college
            # board prices touchdowns and nothing else, so `shelves`
            # returns the one shelf with rows on it and drops the rest.
            out["board_guide"] = _boards.guide("cfb")
            out["board_shelves"] = _boards.shelves("cfb", out["most_likely"])
            # WHY THE BOARD IS THE SIZE IT IS, published rather than
            # printed. An empty touchdown board has several causes — no
            # game qualified for a pull, the pull returned nothing, every
            # quoted player was missing usage, everyone sat outside the
            # odds window — and a census that only reaches stdout is a
            # census nobody has when they need it, which is the morning
            # the board comes up empty. engine/devigcheck reads this.
            out["td_census"] = dict(census, quotes_note=td_note,
                                    games_quoted=len(quotes or {}))
            # The WHOLE quoted TD field, journaled so this market's
            # one-sided hold can be measured rather than assumed at 6%
            # (engine/holdwatch). Books do not offer "no touchdown", so
            # there is no pair to de-vig; settling every quote against
            # who actually scored is the only honest route to the
            # number. Names are the pull's normalized form and settle
            # normalizes the stat rows to match.
            try:
                from engine import holdwatch as _hw
                _flat: dict = {}
                for _q in (quotes or {}).values():
                    for _name, _qs in _q.items():
                        _flat.setdefault(_name, []).extend(_qs)
                _hqn = _hw.record_quotes(conn, _flat, sport="cfb",
                                         season=day.year, period=args.date,
                                         market="anytime_td")
                if _hqn:
                    print(f"  Quote journal: {_hqn} TD quote(s) recorded "
                          f"for the hold measurement.")
            except Exception as _hexc:                       # noqa: BLE001
                print(f"  ⚠️  quote journal skipped: {_hexc}")
            if census["quoted_players"]:
                print(f"  TD board: {len(rows)} pick(s) + {len(watch)} "
                      f"most-likely from {census['quoted_players']} quoted "
                      f"player(s) ({census['no_usage']} without usage logs, "
                      f"{census.get('transfers', 0)} found under a former "
                      f"school, {census['outside_window']} outside the odds "
                      f"window; roles from {census['usage_season']})")
        except Exception as _exc:                             # noqa: BLE001
            print(f"  ⚠️  TD long shots unavailable: {_exc}")
    else:
        # NO PULL THIS CYCLE, SAID OUT LOUD. Without this the board goes
        # out with games on it and no player props and nothing anywhere
        # explaining which of the several possible reasons it was —
        # which is what "it's not showing any player props" looks like
        # from a phone. Most cycles do not spend on odds: the budget is
        # rationed per slate, and scorer prices are pulled per event.
        #
        # An honest empty census, not a fabricated one. Every count is
        # zero because nothing was asked, and the note says so.
        out["td_census"] = {
            "quoted_players": 0, "no_usage": 0, "outside_window": 0,
            # One sentence, written once, wherever it is said. It used
            # to be typed here a second time and the two copies were
            # already drifting — this one still said "touchdown prices"
            # after the same call started buying yardage as well.
            "quotes_note": quotes_note,
            "games_quoted": 0,
        }
    out["status"] = "slate"
    out["no_qualifying"] = result["no_qualifying"]
    # The funnel under the count (engine/census). CFB's board is game
    # bets, whose rejections carry a written `why` rather than a checks
    # list, so it buckets those sentences — same renderer, same page.
    # Without it a quiet Saturday said "no qualifying plays" and offered
    # a reader nothing to check, which is the difference between an
    # empty board and a broken one.
    try:
        from engine.census import census_from_reasons
        out["gate_census"] = census_from_reasons(
            result.get("plays") or [], result.get("pass_list") or [],
            held=result.get("holds") or [])
    except Exception:                                        # noqa: BLE001
        pass

    try:
        from engine import ledger
        lconn = ledger.connect()
        n = ledger.log_recommendations(lconn, {
            "sport": "cfb", "date": args.date,
            # NO LONGER A LITERAL EMPTY LIST. `journal_skip_reason`
            # still refuses everything without a real book price, so on
            # a cycle that did not buy player odds this journals exactly
            # what it journalled before — the game bets — and starts
            # recording props the moment there is a price behind them.
            "recommendations": out.get("recommendations") or [],
            "game_bets": bets})
        # TD long shots journal to their own measured bucket, exactly as
        # MLB's home runs do — the board is only honest if the record
        # grades it. They settle against the `anytime_td` rows the box
        # ingest now derives (engine/sources/cfbdata.parse_summary).
        ls_n = ledger.log_longshots(
            lconn, {"sport": "cfb", "date": args.date,
                    "long_shots": out.get("long_shots") or []})
        # The likelihood board to its own bucket, same as the NFL's — see
        # `ledger.log_most_likely`. College ranks at 0.675 AUC on who
        # scores against the NFL's 0.721, so it needs the settled record
        # at least as much.
        ml_n = ledger.log_most_likely(
            lconn, {"sport": "cfb", "date": args.date,
                    "most_likely": out.get("most_likely") or []})
        settled = ledger.settle_from_history(lconn, conn, sport="cfb")
        if n or ls_n or ml_n or settled:
            ledger.export_json(lconn, "web/data/record.json")
            print(f"Journal: {n} CFB bet(s) + {ls_n} long shot(s) + "
                  f"{ml_n} likely row(s) logged, {settled} settled.")
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


#: How far back to look before calling an empty date the offseason.
#: Ten days spans a bye week and the gap either side of it, and every one
#: of those days is already in the scoreboard cache on any date the
#: 14-day results window has been fetched for.
NEARBY_DAYS = 10


def _boards_guide() -> list:
    """`engine.boards.guide()`, imported at call time and never aliased
    into `main()` — a local `from ... import` there binds the name for
    that whole function, which is how the college board spent a day
    dying on an UnboundLocalError."""
    from engine import boards as _boards
    return _boards.guide("cfb")


def _recent_games(day, lookup):
    """FBS games in the ten days before `day`, or None if we could not look.

    TRI-STATE, AND THE THIRD STATE IS THE POINT. This returned a bare
    list, and its own docstring rationalised the gap: "a fetch that fails
    is skipped by `load_range` itself, which means the honest failure
    mode here is 'found nothing' — and that lands on the offseason
    branch, which is where an unknown belonged." That is not honest. "We
    could not look" and "we looked and the league is dormant" are
    different facts, and publishing OFFSEASON off the first one asserts
    something about college football on the strength of our own failure.

    Ethan, 2026-08-31: "why does it say offseason if cfb started
    yesterday." Because zero games today plus zero found in the lookback
    reads as a dormant league, and the lookback can come back empty for
    reasons that have nothing to do with the league:

      * every day's fetch failed — the case this now separates.
      * the fetch worked and `parse_scoreboard` discarded the games. On
        opening weekend the lookback window is mostly FBS-vs-FCS, and
        that filter dropped every one of them until the `_team_key`
        fallback landed. The same parser serves this window and the
        slate, so the Saturday that showed one game had a lookback that
        found close to none — and the board called that the offseason.

    Fetching per day rather than through `load_range` because that helper
    swallows a failed day silently, which is the distinction being drawn.
    """
    start = day - datetime.timedelta(days=NEARBY_DAYS)
    got, looked = [], 0
    for n in range(NEARBY_DAYS):
        d = start + datetime.timedelta(days=n)
        try:
            payload = cfbdata.fetch_scoreboard(_iso(d))
        except Exception:                              # noqa: BLE001
            continue
        looked += 1
        try:
            got += cfbdata.parse_scoreboard(payload, lookup)
        except Exception:                              # noqa: BLE001
            continue
    # Not one day answered. We know nothing about the last ten days, and
    # saying "offseason" would be inventing the one thing we lack.
    return got if looked else None


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
    # WHEN THESE PRICES WERE PULLED, which this board has never said.
    #
    # Ethan, 2026-09-03: "The lines on the most likely best bet page ...
    # are completely wrong so we are giving bad bets. A lot of the money
    # lines and shit are wrong." The moneyline arithmetic checks out end
    # to end — the card's side, its price and the flip to the likely
    # side all agree with the book. What the board could not say is how
    # OLD the price beside a pick is, and on a board that had not
    # rebuilt for three hours every one of them was three hours stale.
    # A price that cannot be dated cannot be told apart from a wrong one.
    #
    # MLB has stamped this since the pacing telemetry went in and the
    # page already renders it (`oddsClockHTML`, "last pulled 3:32 PM
    # yesterday"); college published no `odds_status` at all, so the
    # clock had nothing to draw. Same field, same source, same units.
    #
    # HERE RATHER THAN AT THE ODDS BLOCK, because this function is the
    # one door every board goes out of — six call sites, several of them
    # early returns — and the furniture that lived inside `if args.odds`
    # is exactly what went missing from every cycle that did not spend.
    try:
        from engine import oddsbudget
        _st = oddsbudget.load()
        out.setdefault("odds_status", {})["priced_at"] = (
            _st.sport_ts("cfb") or _st.last_refresh_ts or None)
    except Exception:                                     # noqa: BLE001
        pass                       # never cost the board a freshness note
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    gate.publish(out, p)


if __name__ == "__main__":
    main()
