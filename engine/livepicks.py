"""Live picks — journaled PRE-GAME picks whose games are now in progress.

The pre-game model never recommends an in-play bet (its projections assume
a full game of opportunity), so once first pitch passes, a recommended
pick vanishes from the board — even though it was placed and is live right
now. This module brings those picks back as a TRACKER: the open journal
rows for today's slate, matched to their (live) games, with the player's
current stat line where the boxscore provides one.

Nothing here creates a bet. It answers "how are the bets we already made
doing?" — the question every bettor asks the moment the game starts.

Pure assembly; the callers supply journal rows, the slate's games and
recommendations, and (optionally) live per-player stats.
"""

from __future__ import annotations

from .sources.oddsapi import normalize_name

TEAM_MARKETS = {"moneyline", "spread", "team_total"}


def _live_prob(bet, market, side, line, current, game, live, progress,
               rec_means, pitching, out=None):
    """The bet's win probability right now, or None.

    NONE IS A REAL ANSWER HERE and is returned far more often than a
    number. Every input this needs can be missing — the game may not be
    live, the boxscore may not name the hitter, total bases may be on the
    board without the hits and home-run means that give it a shape — and
    in each case the honest output is no number, not a number computed
    from a stand-in.

    MONEYLINE is the one market that does NOT go through the model here.
    Its answer is already sitting on the game: `livelines` pulls the live
    de-vigged price for the whole slate for one credit, so for a
    moneyline the market's own number is both cheaper and better than
    anything we could infer, and using ours instead would be inventing a
    disagreement with a price we already paid for.

    SPREAD and TOTAL still get nothing, and it is NOT a cost problem any
    more — both markets are pulled now. It is the alternate-line problem:
    the live market quotes them at ITS number, not ours. A bet on −1.5
    gets no answer from a live price on −0.5, and Over 8.5 gets none from
    a market that has moved to 10.5. Converting between the two needs the
    dispersion of final results around a live line, which nothing here has
    a sample of. `live_market` carries where the market sits instead,
    which is a fact rather than a forecast.
    """
    if (live or {}).get("state") != "live":
        return None
    if market == "moneyline":
        # The live market, de-vigged, from the chart already on the card.
        t = (game or {}).get("line_track") or {}
        p_home = t.get("now")
        if p_home is None:
            return None
        pick_home = bet.get("player") == game.get("home")
        p = float(p_home) / 100.0
        return p if pick_home else 1.0 - p
    if market in TEAM_MARKETS or market == "total":
        return None
    try:
        from .mlb import liveprops as lp
    except Exception:                                         # noqa: BLE001
        return None

    name = normalize_name(bet.get("player", ""))
    stat = (progress or {}).get(name) or {}
    sit = (live or {}).get("situation") or {}
    inning, half = sit.get("inning"), sit.get("half")
    if not inning:
        return None
    is_home = (bet.get("team") or "") == game.get("home") \
        or stat.get("side") == "home"

    if market in lp.PITCHER_MARKETS:
        # A pitcher who has left the game cannot add to his line. That is
        # not an estimate — it is the whole prop, settled, and it is the
        # single most useful thing this can say about a strikeout bet.
        still_in = name in (pitching or set())
        # He works against the OTHER team's remaining outs.
        opp_outs = lp.outs_left(inning, half, sit.get("outs", 0),
                                is_home=not is_home,
                                home_score=live.get("home_score"),
                                away_score=live.get("away_score"))
        # His OWN pen's measured workload stretches the leash: a manager
        # with nobody available rides the starter longer, which is more
        # batters faced and more chances at the strikeout number. Same
        # function and same reading the pre-game outs model uses.
        own_pen = (game.get("bullpen_fatigue") or {}).get(
            bet.get("team") or ("home" if is_home else ""))
        if own_pen is None:
            own_pen = (game.get("bullpen_fatigue") or {}).get(
                game.get("home") if is_home else game.get("away"))
        left = lp.bf_left(opp_outs, stat.get("bf", 0),
                          own_pen_score=own_pen) if still_in else 0.0
        if out is not None:
            # The sweat page's sentence: "~9 batters left" or "pitcher
            # done". Rounded here so two surfaces cannot round apart.
            out["opp_left"] = round(float(left), 1)
            out["opp_unit"] = "BF"
            out["still_in"] = bool(still_in)
        mean = (rec_means.get(name) or {}).get("strikeouts")
        bf_seen = float(stat.get("bf") or 0)
        if mean is None or bf_seen <= 0:
            # Without a rate there is no forecast — but a finished outing
            # still has a definite answer, and withholding it because the
            # projection is missing would hide the certain case behind the
            # uncertain one.
            if left <= 0 and current is not None:
                return 1.0 if ((current > line) == (side != "UNDER")) else 0.0
            return None
        # Strikeouts per batter faced, from tonight's own projection over
        # the batters a starter is expected to face.
        return lp.pitcher_probability(float(mean) / lp.STARTER_BF, line,
                                      side, current or 0.0, left)

    if market not in lp.HITTER_MARKETS:
        return None
    spot = stat.get("spot")
    at_bat = (progress or {}).get(normalize_name(sit.get("batter", ""))) or {}
    at_bat_spot = at_bat.get("spot")
    if not spot or not at_bat_spot:
        return None
    rates = lp.rates_for(market, rec_means.get(name) or {}, spot)
    if rates is None:
        return None

    # WHICH PITCHER THE REST OF HIS NIGHT IS AGAINST. The rates come from a
    # whole-game projection, and that projection has the opposing pen's
    # factor baked flat across it — a blend of the innings he faces the
    # starter and the innings he faces relievers. Live, that blend is
    # knowable: the opposing starter is either still out there or he is
    # not. `pen_rebase` divides the pen bonus back out while he is in and
    # applies it at reliever strength once he is gone.
    opp = game.get("away") if is_home else game.get("home")
    opp_starter = ((game.get("pitchers") or {}).get(
        "away" if is_home else "home") or {}).get("name", "")
    # None, not False, when the starter is not named: we cannot tell who is
    # pitching, and `pen_rebase` leaves the projection alone rather than
    # adjusting it on a missing field.
    facing_pen = (normalize_name(opp_starter) not in (pitching or set())
                  if opp_starter else None)
    shift = lp.pen_rebase(
        _mlb_pen_multiplier(game, opp),
        facing_pen=facing_pen)
    rates = lp.scale_rates(rates, shift)

    team_outs = lp.outs_left(inning, half, sit.get("outs", 0), is_home,
                             live.get("home_score"), live.get("away_score"))
    pa_left = lp.remaining_pa(spot, at_bat_spot, team_outs)
    if out is not None:
        out["opp_left"] = round(float(pa_left), 1)
        out["opp_unit"] = "PA"
    return lp.hitter_probability(rates, market, line, side,
                                 current or 0.0, pa_left)


def _live_market(market, game, live, bet=None):
    """The market's current number for a spread or total bet, or None.

    ORIENTED TO THE BET'S OWN TEAM. `livelines` stores the HOME spread,
    which is the feed's convention; a journaled spread is signed for
    whichever side was taken. Handing an away bet the home number puts the
    comparison on the wrong side of zero — "market now −0.5, you have
    +1.5" reads as a huge move when nothing happened.

    Deliberately NOT converted into a probability. A bettor holding Over
    8.5 while the live market has moved to 10.5 has learned something real
    and exact; dressing it up as a win chance needs the one conversion
    this module refuses to guess at.
    """
    if (live or {}).get("state") != "live" or market not in ("spread", "total"):
        return None
    t = (game or {}).get("line_track") or {}
    if market == "total":
        now = t.get("total")
        return None if now is None else float(now)
    now = t.get("spread")
    if now is None:
        return None
    pick_home = (bet or {}).get("player") == (game or {}).get("home")
    return float(now) if pick_home else -float(now)


def _mlb_pen_multiplier(game, opponent) -> float:
    """The whole-game opposing-pen factor this projection already carries.

    Returns 1.0 when the build did not measure a pen — an unmeasured pen
    contributed nothing to the projection, so there is nothing to take
    back out, and assuming otherwise would move a number on the strength
    of a missing input.
    """
    if not opponent:
        return 1.0
    try:
        from .mlb.bullpen import pen_multiplier
    except Exception:                                         # noqa: BLE001
        return 1.0
    return pen_multiplier(
        rank=(game.get("bullpen_rank") or {}).get(opponent),
        fatigue=(game.get("bullpen_fatigue") or {}).get(opponent))


def assemble_live_picks(open_bets: list[dict], recommendations: list[dict],
                        games: list[dict],
                        progress: dict | None = None,
                        longshots: list[dict] | None = None,
                        identity: dict | None = None,
                        pitching: set | None = None) -> list[dict]:
    """One row per open journaled pick whose game is LIVE right now.

    ``progress``: {normalized player name: {market: current value}} from
    engine.mlb.livestats — optional; rows render without it.

    ``longshots``: the Long Shots board. A player prop is placed on the
    field by looking its name up in the recommendations, and long shots are
    NOT in that list — they are a separate board with its own bucket in the
    journal. Without them here, every home-run bet the site recommends maps
    to nothing and reports itself as unmapped, which is how a full night of
    live long shots renders as an empty tracker.

    ``identity``: {player: {team, headshot}} from engine.rosters.identity_map
    — who a player IS, independent of tonight's prices. THIS IS THE ONE
    SOURCE HERE THAT SURVIVES FIRST PITCH, and the reason it had to exist
    is below.

    ``pitching``: normalized names of whoever is currently on the mound,
    from engine.mlb.livestats.current_pitchers. A starter absent from it
    has finished, which turns his strikeout prop from a forecast into a
    settled fact.
    """
    progress = progress or {}
    rec_idx = {(normalize_name(r.get("player", "")), r.get("market", "")): r
               for r in recommendations}
    # The main board wins a collision: if the same player+market is on both,
    # the main row is the one carrying the staked bet's context.
    for r in (longshots or []):
        rec_idx.setdefault(
            (normalize_name(r.get("player", "")), r.get("market", "")), r)

    # THREE PLACES TO LOOK, IN DESCENDING ORDER OF WHAT THEY KNOW.
    #
    # Ethan, 2026-08-13, on a Live Now screenshot: "it says it couldnt map
    # the game AND its not showing the heashshots of the players." Both
    # symptoms, one cause — a row was placed on the field ONLY by an exact
    # (player, market) hit on tonight's board, and the face was taken from
    # that same row, so a miss cost the game AND the photo together.
    #
    # And the board is precisely the thing that does not survive first
    # pitch. A book pulls its pre-game pitcher markets when the game goes
    # live; that prop then has no row tonight, no matter how correctly it
    # was journaled two hours earlier. Every unmapped name in his
    # screenshot was a pitcher (strikeouts, outs) and every mapped one a
    # hitter on the home-run board, which is the fingerprint of market
    # availability rather than of name matching.
    #
    # The page's own footnote already promised the opposite behaviour — "a
    # bet stays here until it settles, even if the pick later drops off
    # Tonight's Picks because prices moved" — so this was the mapping
    # contradicting the design, not the design being unclear.
    #
    # 1. exact (player, market): the full context — team, opponent, leg,
    #    face, and the ONLY row allowed to name this bet's market.
    # 2. the same player on ANY market tonight: he is in a game and it is
    #    the same game whatever he is priced for.
    # 3. the identity map: the club he plays for, from the league's own
    #    roster feed. Needs no board at all.
    player_idx: dict[str, dict] = {}
    for r in list(recommendations) + list(longshots or []):
        player_idx.setdefault(normalize_name(r.get("player", "")), r)
    id_idx = {normalize_name(k): v for k, v in (identity or {}).items()}

    # TONIGHT'S OWN PROJECTIONS, per player per market. The live
    # probability is built from these rather than from a fresh model run,
    # so the number on the tracker and the number that priced the bet come
    # from one source. Both boards are read: a home-run long shot is not on
    # the main list, and its mean is exactly what its live probability
    # needs. The main board wins a collision, matching `rec_idx` above.
    rec_means: dict[str, dict] = {}
    for r in list(longshots or []) + list(recommendations):
        proj = r.get("projection")
        if proj is None:
            continue
        rec_means.setdefault(normalize_name(r.get("player", "")), {})[
            r.get("market", "")] = float(proj)

    def _game_for(team, opp=None, gn=0):
        matches = []
        for g in games:
            pair = {g.get("home"), g.get("away")}
            if team not in pair or (opp is not None and opp not in pair):
                continue
            if gn and g.get("game_number") and gn != g.get("game_number"):
                continue
            matches.append(g)
        # Doubleheader without an explicit leg (team-level bets): the LIVE
        # leg is the one being tracked; a final/scheduled sibling isn't.
        live = [g for g in matches
                if ((g.get("live") or {}).get("state")) == "live"]
        return (live or matches or [None])[0]

    def _face(b):
        """This player's photo, from whichever source still has one.

        Deliberately independent of whether the bet could be placed on a
        game: not knowing which field a man is on is no reason to stop
        knowing what he looks like, and the unmapped rows losing their
        faces is half of what Ethan reported.

        Returns "" for anything that is not a player prop. `player` holds
        a team ABBREVIATION on a moneyline and "AWAY@HOME" on a game
        total, so a name lookup there is a lookup for a player who does
        not exist — and any hit would be a collision, not a face.
        """
        m = b.get("market", "")
        if m in TEAM_MARKETS or m == "total":
            return ""
        n = normalize_name(b.get("player", ""))
        for src in (rec_idx.get((n, b.get("market", ""))),
                    player_idx.get(n), id_idx.get(n)):
            face = (src or {}).get("headshot") or ""
            if face:
                return face
        return ""

    def _unmapped(b, face=""):
        """An open bet the current board can't place — NEVER drop it: the
        section's count must always match the Record's, and a bet we can't
        map is a fact worth showing, not hiding."""
        return {
            "player": b.get("player"), "market": b.get("market", ""),
            "market_label": b.get("market", ""),
            "side": (b.get("side") or "OVER").upper(),
            "line": float(b.get("line") or 0),
            "odds": b.get("odds"), "stake_units": b.get("stake_units") or 0,
            "current": None, "status": "unmapped", "phase": "upcoming",
            # Present and empty, not absent. A bet we could not place on a
            # game has no live probability by definition, and every row
            # carrying the same keys is what stops a consumer from having
            # to know which shape it got.
            "live_prob": None, "live_market": None,
            "team": "", "headshot": face, "game": {},
            "category": b.get("category", "main"),
        }

    out = []
    for b in open_bets:
        market = b.get("market", "")
        rec = where = None
        if market in TEAM_MARKETS:
            g = _game_for(b.get("player"))
        elif market == "total":
            key = b.get("player", "")           # journaled as AWAY@HOME
            g = next((x for x in games
                      if f"{x.get('away', '')}@{x.get('home', '')}" == key), None)
        else:
            n = normalize_name(b.get("player", ""))
            rec = rec_idx.get((n, market))
            # `rec` stays EXACT-MARKET ONLY below this line. It is the row
            # that gets to say "Home Runs 0.5+", and a cross-market match
            # would relabel a strikeouts bet with a home-run market label —
            # trading an honest "unmapped" for a confident wrong one.
            # Placement is a different question, so it gets its own answer.
            where = rec or player_idx.get(n) or id_idx.get(n)
            if where is None:
                out.append(_unmapped(b, _face(b)))
                continue
            g = _game_for(where.get("team"), where.get("opponent"),
                          where.get("game_number") or 0)
        if not g:
            out.append(_unmapped(b, _face(b)))
            continue
        live = g.get("live") or {}
        state = live.get("state") or "scheduled"
        phase = state if state in ("live", "final") else "upcoming"

        current = None
        if market not in TEAM_MARKETS and market != "total":
            current = (progress.get(normalize_name(b.get("player", ""))) or {}) \
                .get(market)
        side = (b.get("side") or "OVER").upper()
        line = float(b.get("line") or 0)
        hs, as_ = live.get("home_score"), live.get("away_score")

        # Every open bet gets a phase and, where the numbers exist, a
        # verdict-in-waiting. FINAL games grade provisionally on the spot
        # (official settle still happens overnight from ingested results).
        status = "upcoming"
        if phase == "live":
            status = "tracking"
            if current is None and hs is not None and as_ is not None:
                # Team markets track from the live score, same as the books
                # do. Moneyline has no stat to bar — the score line says it.
                pick_home = b.get("player") == g.get("home")
                if market == "total":
                    current = float(hs) + float(as_)
                elif market == "team_total":
                    current = float(hs if pick_home else as_)
                elif market == "spread":
                    current = float(hs - as_) if pick_home else float(as_ - hs)
            # Early verdicts only where the number can't come back down:
            # player stats and run totals only ever go UP, so an over can
            # lock in and an under can die mid-game. A spread margin swings
            # both ways, so it tracks without ever locking.
            if current is not None and market not in ("spread", "moneyline"):
                if side == "OVER" and current > line:
                    status = "cleared"          # an over can lock in early…
                elif side == "UNDER" and current > line:
                    status = "busted"           # …and an under can die early
        elif phase == "final":
            actual = current
            if actual is None and hs is not None and as_ is not None:
                # Team markets grade from the final score.
                pick_home = b.get("player") == g.get("home")
                if market == "moneyline":
                    actual = 1.0 if ((hs > as_) == pick_home) else 0.0
                    side, line = "OVER", 0.5
                elif market == "total":
                    actual = float(hs) + float(as_)
                elif market == "spread":
                    actual = float(hs - as_) if pick_home else float(as_ - hs)
                elif market == "team_total":
                    actual = float(hs if pick_home else as_)
            if actual is None:
                status = "final_pending"        # no stat line available yet
            elif actual == line:
                status = "push_pending"
            else:
                won = (actual > line) == (side == "OVER")
                status = "won_pending" if won else "lost_pending"
                current = actual
        sweat: dict = {}
        live_prob = _live_prob(b, market, side, line, current, g,
                               live, progress, rec_means, pitching,
                               out=sweat)
        # A BET WITH NO CHANCES LEFT IS NOT STILL RUNNING. The status
        # buckets above only knew one way for a bet to die — the stat
        # passing the line the wrong way — so a starter pulled two
        # strikeouts short read "tracking · needs 2 more" for the rest of
        # the night. He is not getting them; there is nobody left for him
        # to face. Same for a hitter whose last turn through the order has
        # gone by. The probability already knows this, and it is the only
        # thing that does, so it is what says so.
        if status == "tracking" and live_prob == 0.0:
            status = "dead"
        out.append({
            "player": b.get("player"), "market": market,
            "market_label": (rec or {}).get("market_label")
                or {"moneyline": "Moneyline", "total": "Game Total",
                    "spread": "Run Line", "team_total": "Team Total"}
                    .get(market, market),
            "side": side, "line": line,
            "odds": b.get("odds"), "stake_units": b.get("stake_units") or 0,
            "current": current, "status": status, "phase": phase,
            # WHAT THE BET IS WORTH RIGHT NOW. Ethan, 2026-08-14: "Are we
            # able to track the win probability of bets we have made live
            # too?" Not from the book — props vanish from the board at
            # first pitch and cost per game to ask for — but from what the
            # player has banked against what he has left to bank it in.
            # None whenever any input is missing; see engine/mlb/liveprops.
            "live_prob": live_prob,
            # The sentence ingredients the sweat page needs beside the
            # number: how much opportunity is left ("~2 PA left"), and
            # for a pitcher whether he is still out there at all. Empty
            # when the probability itself was unreachable.
            "opp_left": sweat.get("opp_left"),
            "opp_unit": sweat.get("opp_unit"),
            "still_in": sweat.get("still_in"),
            # Pregame baseline, for the arrow: what the model thought at
            # journal time. Straight off the bet row; None on old rows.
            "pregame_prob": b.get("hit_prob"),
            # Where the market's own number sits right now, for the two
            # markets that carry a line. A fact, not a forecast — see
            # `_live_prob` on why these get no probability.
            "live_market": _live_market(market, g, live, b),
            # Which journal bucket this came from. The same player can hold a
            # bet in two buckets at once — a long shot and a stale-line flag
            # on the same homer — so name + market alone does not identify a
            # row, and anything reconciling this list against the journal
            # will silently mismatch without it.
            "category": b.get("category", "main"),
            "team": (where or {}).get("team", b.get("player", "")),
            # The face, for the tracker's identity column. Only a prop has
            # one — a team market's `player` field holds an ABBREVIATION,
            # and a game total's holds "AWAY@HOME" — which is why this asks
            # the sources rather than inventing a lookup for every row.
            "headshot": _face(b),
            "game": {"home": g.get("home"), "away": g.get("away"),
                     "game_number": g.get("game_number", 1),
                     "doubleheader": g.get("doubleheader", False),
                     "date": g.get("date", ""), "kickoff": g.get("kickoff", ""),
                     "state": state,
                     "period": live.get("period", ""),
                     "home_score": hs, "away_score": as_,
                     # At-bat / outs / runners strip, when the feed has it.
                     "situation": live.get("situation")},
        })
    # Live action first (good news leads), then finals awaiting the official
    # settle, then tonight's not-yet-started bets.
    order = {"cleared": 0, "tracking": 1, "busted": 2, "dead": 2,
             "won_pending": 3, "push_pending": 4, "lost_pending": 5,
             "final_pending": 6, "upcoming": 7, "unmapped": 8}
    out.sort(key=lambda r: (order.get(r["status"], 7), -(r["stake_units"] or 0)))
    return out


# --- the tracker for every board, not just baseball's -------------------------
#: The journal columns the tracker reads. `hit_prob` is the pre-game
#: number a row shows until a live one exists; `category` is what splits
#: the Live tab's two panels.
TRACKER_COLS = ("player, market, side, line, odds, stake_units, date, "
                "category, hit_prob")

#: 'likely' rides along since 2026-09-05 — Ethan: "the most likley bets
#: should also show in the live page ... one for edge bets, and one for
#: most likley bets." The watchlist ('longshot_watch') stays out: it is a
#: calibration sample, often 100+ names, and would bury the bets placed.
TRACKER_CATEGORIES = ("main", "longshot", "likely")


def shift_day(date: str, days: int) -> str:
    """An ISO date moved by ``days``; anything else comes back unchanged.

    NFL journals its card as a WEEK LABEL — '2026-W01' — because a slate
    there is seven days, not one (`ledger._hist_where`). There is no
    neighbouring day to a week, so the label is returned as it is and the
    caller asks for no neighbours. Date arithmetic rather than string
    arithmetic, for the reason `mlb_build._shift_day` was written: the
    31st plus one is the 1st of the next month.

    THE SHAPE IS CHECKED BEFORE THE PARSE. `date.fromisoformat` accepts
    an ISO week ('2026-W01' is the Monday of week 1) on Python 3.11+, so
    the label the NFL journals would have parsed, shifted to a Sunday,
    and asked the journal for a date no bet carries. The first run of
    the test caught it.
    """
    import datetime as _d
    import re
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date or "")):
        return date
    try:
        return (_d.date.fromisoformat(date) + _d.timedelta(days=days)).isoformat()
    except (TypeError, ValueError):
        return date


def open_bets_for(conn, sport: str, date: str) -> tuple[list[dict], list[dict]]:
    """``(today, near)`` — this sport's open journaled bets on the card,
    and on the neighbouring days.

    THE WINDOW IS THE LESSON FROM THE MLB TRACKER. A row is stamped with
    its GAME's date, so a late first pitch is filed under tomorrow in
    UTC; a query for today alone never sees it. Today's rows are shown
    mapped or not, so the section's count reconciles with the Record's;
    a neighbour's row is shown only if it lands on a game on this card.
    """
    where = ("status='open' AND sport=? AND category IN "
             + "(" + ",".join("?" * len(TRACKER_CATEGORIES)) + ")")
    args = (sport, *TRACKER_CATEGORIES)
    today = [dict(r) for r in conn.execute(
        f"SELECT {TRACKER_COLS} FROM bets WHERE {where} AND date=?",
        (*args, date))]
    near_dates = [d for d in (shift_day(date, -1), shift_day(date, 1))
                  if d != date]
    near: list[dict] = []
    if near_dates:
        marks = ",".join("?" * len(near_dates))
        near = [dict(r) for r in conn.execute(
            f"SELECT {TRACKER_COLS} FROM bets WHERE {where} "
            f"AND date IN ({marks})", (*args, *near_dates))]
    return today, near


#: The most live games one build will fetch a box score for — the same
#: budget `livescore_build.PLAYS_MAX_GAMES` keeps for the play feed, for
#: the same reason: a college Saturday can have thirty in progress and
#: this box has OOM-killed under less. Past the cap a bet keeps its row
#: and loses only its live number; the note says so.
PROGRESS_MAX_GAMES = 8


def espn_progress(league: str, games: list[dict]) -> tuple[dict, str]:
    """``({normalized player: {market: value}}, note)`` for every live
    game on a football or hoops board, from ESPN's game summary.

    THE SAME SHAPE `engine.mlb.livestats.parse_live_stats` HANDS THE MLB
    TRACKER, so `assemble_live_picks` reads a Kelce receiving line the
    way it reads a Judge hit line: `current` fills in, an over past its
    number reads "cleared", an under past it "busted".

    WHERE THE PAYLOAD COMES FROM, AND UNDER WHICH NAME. The fast
    scoreboard (`livescores.fetch_rows`, cached 30 s and shared with
    `livescore_build`) names each live game's ESPN event id in the
    board's own vocabulary, so a board game joins on `(away, home)`. The
    summary is then fetched through `espnplays.fetch_summary` — the
    play feed's fetch, cached 30 s under `espn_{league}_live_{event}`
    — and NOT through the league's own `fetch_boxscore`/`fetch_summary`,
    whose caches are a month long because a final never changes. A
    mid-game snapshot written under one of those names would be read
    back by the settlement ingest as the final, and grade every bet in
    that game against the third quarter.

    WHAT READS IT is the parser each league already trusts for its
    finals: `nflpreseason.parse_boxscore` (labels, not positions),
    `cfbdata.parse_summary` (which also derives `anytime_td`) and
    `espnhoops.parse_summary` (names, not positions). Nothing here
    parses a payload a second way.

    A GAME THAT FAILS COSTS ITS OWN NUMBERS AND NOTHING ELSE; the
    scoreboard failing costs every number, and the note says which.
    """
    from .sources.livescores import ESPN_SCOREBOARD, fetch_rows
    if league not in ESPN_SCOREBOARD:
        return {}, ""
    live = [g for g in games if (g.get("live") or {}).get("state") == "live"]
    if not live:
        return {}, ""
    try:
        ids = {(r["away"], r["home"]): r["event_id"]
               for r in fetch_rows(league, ttl=30)}
    except Exception as exc:                                  # noqa: BLE001
        return {}, f"live stats: scoreboard unreachable — {exc}"
    from .sources import espnplays
    out: dict[str, dict] = {}
    got = failed = missing = 0
    for g in live[:PROGRESS_MAX_GAMES]:
        eid = ids.get((g.get("away"), g.get("home")))
        if not eid:
            missing += 1
            continue
        try:
            payload = espnplays.fetch_summary(league, eid)
            for name, stats in _box_rows(league, payload, g):
                out.setdefault(normalize_name(name), {}).update(stats)
            got += 1
        except Exception:                                     # noqa: BLE001
            failed += 1
    skipped = max(0, len(live) - PROGRESS_MAX_GAMES)
    note = f"live stats: {got} of {len(live)} live game(s)"
    if failed:
        note += f", {failed} feed(s) unreachable"
    if missing:
        note += f", {missing} not on the scoreboard"
    if skipped:
        note += f", {skipped} past the {PROGRESS_MAX_GAMES}-game cap"
    return out, note


def _box_rows(league: str, payload: dict, game: dict):
    """``(player, {market: value})`` pairs from one summary, by league."""
    if league == "nfl":
        from .sources.nflpreseason import parse_boxscore
        rows = parse_boxscore(payload, {"home": game.get("home"),
                                        "away": game.get("away")})
        for r in rows:
            yield r["player"], {r["market"]: float(r["value"])}
        return
    if league == "cfb":
        from .sources.cfbdata import parse_summary
    else:
        from .sources.espnhoops import parse_summary
    for r in parse_summary(payload):
        yield r["player"], {k: float(v) for k, v in (r.get("stats") or {}).items()}


def attach_tracker(result: dict, sport: str, conn=None,
                   progress: dict | None = None,
                   identity: dict | None = None,
                   fetcher=None) -> str:
    """Put the open-bet tracker on a league board: ``live_picks`` and
    ``open_elsewhere``, or ``live_picks_error``. Returns a line for the
    build log, or "" when there was nothing to say.

    WHY THIS EXISTS. `mlb_build.py` has assembled the tracker inline
    since the Live tab shipped, boxscore progress and all; NFL, CFB, NBA
    and WNBA never built one, so `renderLivePicks` — which reads the
    VIEWED sport's board — told a reader "No open bets on today's card"
    on every football and hoops tab while the journal held open bets in
    that sport. Ethan asked for the Live tab to carry both the edge bets
    and the Most Likely bets; on four of five boards it carried neither.

    THE SAME ASSEMBLY, THE SAME ARITHMETIC. `assemble_live_picks` places a
    row by the board's recommendations and games — it was never
    baseball-specific, it was only ever called from one place. Team
    markets track from the live score it already reads; player props
    track from ``progress`` — fetched by `espn_progress` when the caller
    passes None, or handed in — and show the pre-game number when no
    live line exists (`current` stays None, which the page renders as
    "tracking"). ``fetcher`` replaces `espn_progress` for a test; it is
    never what decides whether a live number is shown. A progress fetch
    that fails costs the live numbers and not the tracker: the rows
    still ship, with the note saying why they have no `current`. The
    MLB block is left exactly as it
    is: it carries a boxscore fetch, the pitcher set and the identity
    map that this helper takes as arguments, and moving it would be a
    refactor wearing a fix's clothes.

    ``open_elsewhere`` is every open EDGE bet across every sport minus
    the edge rows shown here — the count the masthead prints, so the two
    reconcile (`mlb_build` learned that on 2026-08-09). Likely rows are
    on the tracker but not in that count, so they are not subtracted
    either.

    A FAILURE IS WRITTEN INTO THE BOARD, not only printed: the launcher
    swallows build output, and a tracker that died silently reads as a
    night with no bets.
    """
    try:
        from . import ledger as _ledger
        own = conn is None
        if own:
            conn = _ledger.connect()
        try:
            date = str(result.get("date") or "")
            today, near = open_bets_for(conn, sport, date)
            recs = result.get("recommendations") or []
            games = result.get("games") or []
            shots = result.get("long_shots") or []
            prog_note = ""
            if progress is None:
                try:
                    progress, prog_note = (fetcher or espn_progress)(sport, games)
                except Exception as exc:                      # noqa: BLE001
                    progress, prog_note = {}, f"live stats unavailable: {exc}"
            rows = assemble_live_picks(today, recs, games, progress, shots,
                                       identity)
            rows += [r for r in assemble_live_picks(near, recs, games,
                                                    progress, shots, identity)
                     if r["status"] != "unmapped"]
            result["live_picks"] = rows
            all_open = conn.execute(
                "SELECT COUNT(*) FROM bets WHERE status='open' "
                "AND category IN ('main','longshot') "
                "AND stake_units > 0").fetchone()[0]
            edge_shown = sum(1 for r in rows if r.get("category") != "likely")
            result["open_elsewhere"] = max(0, all_open - edge_shown)
        finally:
            if own:
                conn.close()
    except Exception as exc:                                  # noqa: BLE001
        result["live_picks_error"] = str(exc)
        return f"tracker error: {exc}"
    rows = result["live_picks"]
    if not rows:
        return ""
    n_live = sum(1 for r in rows if r["phase"] == "live")
    n_likely = sum(1 for r in rows if r.get("category") == "likely")
    note = (f"{len(rows)} on this card ({n_live} live"
            + (f", {n_likely} likely" if n_likely else "") + ")")
    if result["open_elsewhere"]:
        note += f", {result['open_elsewhere']} open on other boards"
    if prog_note:
        note += f"; {prog_note}"
    return note
