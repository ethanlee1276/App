"""CFB anytime-touchdown long shots.

Ethan, 2026-08-25: "fix the odds range for long shot picks for nfl and
CFB... we should be using the game script and all the other stats and
data to determine who will score a touchdown."

THE SAME DISCIPLINE AS THE NFL BOOK (engine/touchdowns.py), rebuilt on
what college actually gives us:

    expected TDs = team implied total × (league TDs ÷ league points)
                 × player's share of team volume, against his position's
                   baseline share of team touchdowns
                 × game script (the spread, priced per position)
                 × opponent's scoring generosity (points allowed per
                   game vs the FBS average — no per-position defense
                   profiles exist here)
                 × weather (our own kickoff forecast layer)

then P(scores) = 1 − e^(−rate), priced against the book's Yes quote
through the same tempering, market-shrink and credibility guards every
long shot passes (engine/longshots.build_pick).

WHAT THIS MODEL LEANS ON AND SAYS SO. The opportunity signal is each
player's share of his team's rushing + receiving yards, and the
strongest single thing we know about him is his own scoring rate; the
two are blended on a fitted weight (`TD_HISTORY_GAMES`). Early in a
season those logs are LAST season's: returning production is a real
predictor and a transfer is invisible to it, so every pick built off a
prior season carries the caveat by name. No logs at all for a quoted
player means no pick — a price with no opportunity evidence behind it is
a lottery ticket, and the strategy's first rule is that we do not sell
those.

WHY IT IS NOT THE NFL MODEL, MEASURED RATHER THAN ASSERTED. This file
used to say college had no play-by-play in our feeds and therefore no
red-zone splits. It has both now: `engine.sources.cfbstats` ingests
play-level college production off the sportsdataverse mirror, red-zone
and inside-the-five carries included. The obvious next step was to lean
on them the way `engine.touchdowns` leans on red-zone role. Measured
(`engine.cfbtdfit.ROLE_FEATURES`), red-zone role does carry information
the yardage share does not — but inside THIS model's share term, where
a share is divided by its position's typical share and clamped, adding
it at the weight the training grid picked moved held-out Brier by one
ten-thousandth. So the share stays as it was, the blend and the
position anchors are fitted instead, and the red-zone markets stay
ingested and shown on player pages rather than priced on a gain that
cannot be told from noise.
"""

from __future__ import annotations

from ..longshots import (CFB_TD_ODDS, prob_at_least_one, in_odds_window,
                         build_pick, select)
from ..sources.oddsapi import best_scorer_price
from ..statmath import clamp

# FBS scoring baselines, MEASURED rather than recalled. Both numbers here
# were 8-12% high: over 6,266 scored team-games the mean is 26.70 points,
# and over 5,420 logged team-games it is 3.03 offensive touchdowns, not
# 28.8 and 3.4. College does score more than the NFL and kick fewer field
# goals per possession; it scores less than these constants claimed.
CFB_AVG_TEAM_POINTS = 26.70
CFB_AVG_TEAM_OFF_TDS = 3.03

#: Offensive touchdowns per point of a team's IMPLIED total. Its own
#: constant rather than the ratio of the two averages above, because it
#: converts a market number and they describe realised ones — the market's
#: mean implied total runs 26.41 against a realised 26.88, and folding
#: that half-point into the conversion is what makes it unbiased.
#:
#: Fitted over 4,594 team-games (2022-24) and checked on 826 held out
#: (2025), where it beat the 0.1181 this file used to derive from the two
#: averages by a paired t of -2.08. Small — 0.007 touchdowns — but it is
#: free, and the de-vig depends on this being unbiased rather than close:
#: an expectation's systematic error does not average away across a
#: board, it compounds into the hold.
#:
#: The CFB handbook's (total - 4.5) / 7.1 is measurably steeper than the
#: data: it runs 0.2-0.3 touchdowns high from 24 points up, which
#: over-states distinct scorers, which under-states the hold and inflates
#: every edge. At the level of a single game nothing separates the forms
#: (all sit at 1.20 MAE against 1.20 of game-to-game noise); the bias only
#: matters where it is used, which is an expectation.
CFB_TD_PER_POINT = 0.1145

#: Share of a team's offensive TDs a TYPICAL STARTER at the position
#: takes — the anchor a player's volume scales, not a position group's
#: whole-room total. The first cut used group totals (RB room 0.36, WR
#: room 0.24), which handed every individual starter his entire
#: position room's touchdown equity: the model priced a 65% WR1 the
#: books had at 43%, and the credibility guard rightly refused the
#: whole board. The second cut was four reasoned guesses.
#:
#: FITTED 2026-08-27, once there was a position to fit against. These
#: numbers only mean anything if the label is real, and until
#: `engine.sources.cfbstats` joined the mirror's roster file there was
#: no position in a college box score at all — `role_of` inferred RB or
#: WR from the usage mix and was wrong for 7,835 of 28,141 graded
#: player-games, 3,432 tight ends read as receivers and 3,798
#: quarterbacks as backs or receivers.
#:
#: Coordinate descent on 2022-23, scored on 2024-25 (`engine.cfbtdfit`).
#: The first pass ran before college had any historical betting lines,
#: so the replay held the implied team total and the game script neutral;
#: the second ran on the real chain once `engine.sources.cfblines`
#: attached closing numbers to all 3,132 ingested games:
#:
#:     inferred labels, guessed anchors      held-out Brier 0.18477
#:     roster labels,   guessed anchors                     0.18526
#:     roster labels,   fitted anchors                      0.18434
#:     …the same, replayed against the real lines             0.18273
#:     roster labels,   REFITTED on that chain               0.18193
#:
#: The second row is the one worth reading. Correcting the label while
#: keeping anchors that had been tuned AGAINST the wrong label made the
#: model worse — a real tight end priced off a number built for misfiled
#: receivers. The two changes only pay together, which is why neither
#: shipped alone. The last row says the same thing about the chain: an
#: anchor fitted with the game script held at 1.0 is not the anchor that
#: belongs beside a game script.
#:
#: What moved from the original guesses: quarterbacks 0.16 → 0.29
#: (college lets them run, and the guess was an NFL instinct), tight
#: ends 0.08 → 0.13, backs 0.26 → 0.33, receivers 0.15 → 0.17.
#:
#: `cfbtdfit.fit_all` then re-fitted all of it jointly, blend and
#: red-zone weight included, and landed on a neighbouring corner worth
#: 0.0002 of training Brier and 0.0001 of held-out LOSS. So these stayed
#: as they are. A fitter that only ever ratchets is not measuring.
POSITION_TD_SHARE = {"RB": 0.33, "WR": 0.17, "TE": 0.13, "QB": 0.29}

#: Volume share a typical starter at the position commands, so a role is
#: scaled rather than floored (same reasoning as the NFL table).
POSITION_TYPICAL_SHARE = {"RB": 0.32, "WR": 0.20, "TE": 0.10, "QB": 0.25}

#: Touches per game a typical starter at each position sees — the
#: confidence discount's denominator. One flat 16 shortchanged every
#: receiver: a 6-catch WR1 is a full-volume starter, not 38% of one.
OPP_TARGET = {"RB": 15.0, "WR": 6.0, "TE": 5.0, "QB": 10.0}

#: Fewer sampled games than this and the opponent's points-allowed says
#: nothing — early-season schedules are cupcakes and body bags.
MIN_DEFENSE_GAMES = 3

#: HOW FAST A PLAYER'S OWN SCORING RECORD TAKES OVER FROM HIS ROLE, and
#: how far it may go. Both were guesses — `games / 10` capped at 0.70,
#: carried across from the NFL model's own pre-measurement guess — and
#: neither had ever once run, because the database held ten CFB player
#: rows and the blend only engages above three logged games.
#:
#: Fitted on 2026-08-27 by `engine.cfbtdfit` over 28,916 graded college
#: player-games: chosen on 2022-23, scored on 2024-25, replaying the
#: board's real chain — the game's own closing total and spread drive
#: the implied team total and the script, and the opponent's scoring
#: generosity is recomputed from games already played. Held-out Brier:
#:
#:     role share alone, no history      0.18310
#:     the guessed games/10 cap 0.70     0.18371
#:     the fitted games/20 cap 0.20      0.18192
#:
#: An interior minimum, with zero in the grid: the training surface runs
#: 0.18640 at cap 0.0, bottoms at 0.18578, and is back to 0.18621 by
#: cap 0.4.
#: So the player's own scoring rate IS worth something on top of his
#: role — about a fifth of the number at most — and the old guess of
#: seventy percent after ten games was so far past the useful range that
#: it scored worse than switching the history off.
TD_HISTORY_GAMES = 20.0
TD_HISTORY_MAX_WEIGHT = 0.20

#: HOW MUCH OF THE OPPORTUNITY SHARE IS RED-ZONE TOUCHES rather than
#: yardage. Zero until 2026-08-27, because college football had no
#: play-by-play in our feeds and there was no red-zone anything to
#: weigh; `engine.sources.cfbstats` now ingests carries and receptions
#: inside the twenty on the same cuts the NFL model reads.
#:
#: The first measurement said no. Replayed on the ROLE chain alone —
#: game script and implied total held neutral, because college had no
#: historical betting lines yet, and a third of the 2025 season quietly
#: missing its touchdowns — a red-zone term bought one ten-thousandth of
#: held-out Brier and was left out. With the feed's broken weeks caught
#: (`cfbstats.week_modes`) and the board's own closing numbers driving
#: the chain (`engine.sources.cfblines`), the same grid says something
#: different, and says it three ways: an interior minimum on the
#: training seasons (0.18574 at zero, 0.18564 at 0.10, 0.18592 by 0.20),
#: the same shape held out (0.18179 → 0.18150), and a free logistic that
#: ranks yardage-plus-red-zone above yardage alone (log loss 0.55887 →
#: 0.55603).
#:
#: It is still a small term and it is deliberately a SMALL WEIGHT. What
#: it is not is zero, and the earlier zero was measured on a chain the
#: board does not run.
RZ_SHARE_WEIGHT = 0.10


#: Distinct players a season must have logged before it is preferred
#: over the newest season that has any. A single Saturday of FBS is
#: thousands; anything under a few hundred is a partial ingest or a
#: fixture, and letting it win would hand the board one team's worth of
#: usage and hide four ingested seasons behind it. Deliberately NOT a
#: judgement about whether two weeks of this season beat all of last —
#: that is a real modelling question and this is not an answer to it.
MIN_SEASON_PLAYERS = 200


def _players_logged(conn, season) -> int:
    row = conn.execute(
        "SELECT COUNT(DISTINCT player) FROM player_game_logs "
        "WHERE sport='cfb' AND season=?", (season,)).fetchone()
    return int(row[0] or 0) if row else 0


def usage_table(conn, season: int | None = None) -> tuple[int, dict]:
    """``(season_used, {team: {norm_name: usage}})`` from ingested logs.

    ``usage`` = {player, carries, receptions, rush_yds, rec_yds, games}
    (per-game means; games = distinct box scores). Falls back to the
    NEWEST season holding CFB logs, because in August the current season
    has none — the caller states the fallback on every pick it feeds.
    """
    from ..sources.oddsapi import normalize_name
    if season is None or _players_logged(conn, season) < MIN_SEASON_PLAYERS:
        # The newest season that is actually a season. MAX(season) alone
        # returns the thin one we just rejected, which is how four
        # ingested seasons ended up hidden behind four fixture rows — so
        # the last resort is the season with the MOST logged players
        # (newest wins ties), never simply the newest.
        row = conn.execute(
            "SELECT season FROM player_game_logs WHERE sport='cfb' "
            "GROUP BY season HAVING COUNT(DISTINCT player) >= ? "
            "ORDER BY season DESC LIMIT 1", (MIN_SEASON_PLAYERS,)).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT season FROM player_game_logs WHERE sport='cfb' "
                "GROUP BY season ORDER BY COUNT(DISTINCT player) DESC, "
                "season DESC LIMIT 1").fetchone()
        season = int(row[0]) if row and row[0] is not None else 0
    if not season:
        return 0, {}
    out: dict = {}
    for r in conn.execute(
            "SELECT team, player, position, market, AVG(value) AS mean, "
            "COUNT(DISTINCT game_id) AS games FROM player_game_logs "
            "WHERE sport='cfb' AND season=? "
            "AND market IN ('carries','receptions','rush_yds','rec_yds',"
            "'anytime_td','rz_car','rz_rec') "
            "GROUP BY team, player, market", (season,)):
        t = out.setdefault(r["team"], {})
        u = t.setdefault(normalize_name(r["player"]),
                         {"player": r["player"], "carries": 0.0,
                          "receptions": 0.0, "rush_yds": 0.0, "rec_yds": 0.0,
                          "rz_car": 0.0, "rz_rec": 0.0,
                          "games": 0, "position": ""})
        u[r["market"]] = float(r["mean"] or 0.0)
        u["games"] = max(u["games"], int(r["games"] or 0))
        # A blank never overwrites a known position: the ESPN box ingest
        # stores none, the mirror's roster join does, and the same
        # player can arrive from both.
        u["position"] = u["position"] or (r["position"] or "").strip().upper()
    return season, out


#: A roster position, folded onto the four the model prices. Anything
#: else — a punter who took a fake, a lineman on a tackle-eligible — is
#: not in the table and falls through to the usage mix, which is the
#: right answer for a player being priced on what he actually did.
ROSTER_ROLES = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE"}


def role_of(u: dict) -> str:
    """RB / WR / TE / QB — the roster's answer if we have one, else the mix.

    College BOX SCORES carry no position, which is why this used to be
    pure inference off carries-vs-catches. The mirror's roster file does
    carry one (`engine.sources.cfbstats.parse_rosters`), and the
    inference was wrong for 28% of graded player-games: 4,430 tight ends
    read as wide receivers, 4,835 quarterbacks as backs or receivers.

    It is shipped as a LABEL fix and measured as one. Held-out Brier
    over 2024-25 moved 0.15104 → 0.15098 — which is nothing. The
    position table's four values sit close together and the fitted
    history blend absorbs most of what is left, so correcting the label
    did not make the model better. It stops the board calling a tight
    end a wide receiver on a public page, and that is the whole claim.

    Without a roster position the old inference stands, unchanged: a
    heavy runner who also catches is a back, and QB is never guessed —
    mislabelling a dual-threat quarterback as a back overstates his
    baseline less than the reverse.
    """
    seen = ROSTER_ROLES.get(str(u.get("position") or "").strip().upper())
    if seen:
        return seen
    if u["carries"] >= 2.0 and u["carries"] >= u["receptions"] * 1.5:
        return "RB"
    return "WR"


def implied_total_for(spread_home, total, is_home: bool) -> float | None:
    """The team's implied points from the board's own numbers."""
    if spread_home is None or total is None:
        return None
    half = float(total) / 2.0
    return half - float(spread_home) / 2.0 if is_home \
        else half + float(spread_home) / 2.0


def script_multiplier(spread_home, is_home: bool, pos: str
                      ) -> tuple[float, list[str]]:
    """Game script, CFB-flavoured: same mechanism as the NFL's
    (engine/touchdowns.script_td_multiplier), half the slope — a 20-point
    college spread is an ordinary Saturday, not a two-touchdown NFL
    outlier, so per-point it carries less information."""
    if spread_home is None:
        return 1.0, []
    lead = -float(spread_home) if is_home else float(spread_home)
    if pos == "RB":
        mult = clamp(1.0 + 0.005 * lead, 0.88, 1.12)
    elif pos in ("WR", "TE"):
        mult = clamp(1.0 - 0.002 * lead, 0.95, 1.05)
    else:
        return 1.0, []
    reasons = []
    if abs(lead) >= 6.0 and abs(mult - 1.0) >= 0.02:
        side = "favoured" if lead > 0 else "underdog"
        reasons.append(f"Game script: {side} by {abs(lead):.0f} — "
                       f"{(mult - 1) * 100:+.0f}% TD equity for a {pos}")
    return mult, reasons


def defense_multiplier(conn, opponent: str, season: int
                       ) -> tuple[float, list[str]]:
    """Opponent's scoring generosity from its own results.

    Points allowed per game against the FBS average, shrunk toward 1.0
    by sample and clamped. Not a per-position read — college gives us no
    coverage splits — and it says nothing until MIN_DEFENSE_GAMES real
    results exist, because two cupcakes prove only the schedule.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS n, "
        "AVG(CASE WHEN home=? THEN away_score ELSE home_score END) AS pa "
        "FROM games WHERE sport='cfb' AND season=? AND (home=? OR away=?) "
        "AND home_score IS NOT NULL",
        (opponent, season, opponent, opponent)).fetchone()
    n = int(row["n"] or 0)
    if n < MIN_DEFENSE_GAMES or row["pa"] is None:
        return 1.0, []
    raw = float(row["pa"]) / CFB_AVG_TEAM_POINTS
    w = clamp(n / 8.0, 0.0, 1.0)
    mult = clamp(1.0 + w * (raw - 1.0), 0.85, 1.20)
    reasons = []
    if mult >= 1.06:
        reasons.append(f"{opponent} concedes {float(row['pa']):.0f} a game "
                       f"— {(mult - 1) * 100:+.0f}% vs FBS average")
    elif mult <= 0.94:
        reasons.append(f"{opponent} allows {float(row['pa']):.0f} a game "
                       f"— {(mult - 1) * 100:+.0f}% vs FBS average")
    return mult, reasons


def weather_multiplier(weather: dict | None, pos: str
                       ) -> tuple[float, list[str]]:
    """Same thresholds as the NFL's, read off our own forecast layer."""
    w = weather or {}
    if w.get("dome"):
        return 1.0, ["Indoors — weather is not a factor"]
    mult, reasons = 1.0, []
    wind = float(w.get("wind_mph") or 0)
    temp = w.get("temp_f")
    if wind >= 20 and pos in ("WR", "TE", "QB"):
        mult *= 0.93
        reasons.append(f"Wind {wind:.0f} mph — passing touchdowns suppressed")
    if float(w.get("precip_chance") or 0) >= 0.6:
        mult *= 0.97
        reasons.append("Rain likely — modest drag on the passing game")
    if temp is not None and float(temp) <= 20:
        mult *= 0.96
        reasons.append(f"{float(temp):.0f}°F — cold suppresses scoring")
    return mult, reasons


#: Watch-list price sanity — same reasoning as the NFL's TD_WATCH_ODDS:
#: wider than the value window on the juiced side by design.
CFB_WATCH_ODDS = (-400, 1500)
CFB_WATCH_LIMIT = 5


def game_fairs(player_quotes: dict, spread_home, total) -> dict:
    """``{normalised player: FairQuote}`` for one game, or ``{}``.

    COLLEGE IS WHERE THIS MATTERS MOST. The handbook puts anytime-TD hold
    at 28-40% in power conferences and 35-50% in the Group of Five,
    against the 6% `longshots.ONE_SIDED_HOLD` assumes — so a +250 the
    board shows is a +390 shot the book is pricing, and the gap is not a
    correction to the edge, it IS the edge. Every input is already here:
    the game's own quoted scorers, and its spread and total.

    Measured WITHIN ONE BOOK. `best_scorer_price` takes each player's
    best price across books, and summing those sums a line no book
    offers — best price is the lowest implied probability, so the sum
    comes in low and the hold with it, which inflates every edge. One
    book's board sets the margin and supplies the price to de-vig; the
    pick is still graded against the best price anyone offers.

    Empty when the market is too thin to measure, which is common in
    college and is exactly when a guess would be most dangerous — a
    Group of Five game with four listed players says nothing about its
    own hold, and the caller falls back to the standing assumption.
    """
    from ..devig import expected_distinct_scorers, board_fair
    from ..odds import american_to_prob
    if spread_home is None or not total:
        return {}
    by_book: dict = {}
    for norm, quotes in (player_quotes or {}).items():
        for q in quotes or []:
            book = (q.get("book") or "").lower()
            try:
                odds = int(q.get("yes_odds"))
            except (TypeError, ValueError):
                continue
            if book and odds:
                by_book.setdefault(book, {})[norm] = american_to_prob(odds)
    home_t = implied_total_for(spread_home, total, True)
    away_t = implied_total_for(spread_home, total, False)
    if home_t is None or away_t is None:
        return {}
    scorers = expected_distinct_scorers(
        max(0.0, home_t) * CFB_TD_PER_POINT,
        max(0.0, away_t) * CFB_TD_PER_POINT)
    return board_fair(by_book, scorers)


def build_cfb_td_longshots(conn, games: list[dict], quotes_by_game: dict,
                           season: int, limit: int = 6,
                           per_game: int = 2
                           ) -> tuple[list[dict], dict, list[dict]]:
    """``(picks, census, watch)`` — the board rows, what was skipped and
    why, and the most-likely-scorers list.

    The WATCH carries every modelled player at a sane real price ranked
    by probability, window be damned — the -260 bell cow whose script
    says goal-line volume belongs on the page even when his price holds
    no value (see touchdowns.td_watchlist for the ask, verbatim). Price
    and EV ride along honestly; nothing in it is journaled.

    ``games`` are the payload's game dicts (spread/total/kickoff/weather
    already stamped); ``quotes_by_game`` maps the game's index in that
    list to ``{norm_name: [quote dicts]}`` from parse_event_scorers.
    """
    from ..odds import american_to_decimal
    usage_season, usage = usage_table(conn, season)
    census = {"quoted_players": 0, "no_usage": 0, "outside_window": 0,
              "priced": 0, "usage_season": usage_season}
    picks = []
    watch_rows = []
    for gi, player_quotes in (quotes_by_game or {}).items():
        try:
            g = games[int(gi)]
        except (IndexError, ValueError, TypeError):
            continue
        home, away = g.get("home", ""), g.get("away", "")
        spread_home, total = g.get("spread"), g.get("total")
        # ONCE PER GAME, BEFORE EITHER LIST. Both the watch and the picks
        # have to price against the same book, and the only way to
        # guarantee that is to measure the hold before either of them
        # exists rather than inside each branch.
        fairs = game_fairs(player_quotes, spread_home, total)
        for norm, quotes in (player_quotes or {}).items():
            census["quoted_players"] += 1
            side = next((t for t in (home, away)
                         if norm in (usage.get(t) or {})), "")
            if not side:
                census["no_usage"] += 1
                continue
            u = usage[side][norm]
            best = best_scorer_price(quotes)
            if best is None:
                continue
            odds = int(best["yes_odds"])
            is_home = side == home
            opp = away if is_home else home
            implied = implied_total_for(spread_home, total, is_home)
            if implied is None:
                continue               # no game price = no script, no read
            team_tds = max(0.0, implied) * CFB_TD_PER_POINT
            pos = role_of(u)
            team_u = usage.get(side) or {}
            vol = u["rush_yds"] + u["rec_yds"]
            team_vol = sum(p["rush_yds"] + p["rec_yds"]
                           for p in team_u.values()) or 1.0
            share = clamp(vol / team_vol, 0.0, 1.0)
            # RED-ZONE TOUCHES, at a small fitted weight. A team with no
            # red-zone rows at all — a board built from a box-score feed
            # that cannot see field position — falls back to the yardage
            # share, so the blend is a no-op rather than a silent
            # haircut on everybody. See RZ_SHARE_WEIGHT.
            team_rz = sum(p["rz_car"] + p["rz_rec"] for p in team_u.values())
            rz_share = (clamp((u["rz_car"] + u["rz_rec"]) / team_rz, 0.0, 1.0)
                        if team_rz > 0 else share)
            share = (1.0 - RZ_SHARE_WEIGHT) * share \
                + RZ_SHARE_WEIGHT * rz_share
            base = POSITION_TD_SHARE[pos] * clamp(
                share / POSITION_TYPICAL_SHARE[pos], 0.15, 1.8)
            # Tighter caps than the NFL's, on purpose. The yardage-share
            # proxy overstates concentration — a thin ingested roster
            # makes every listed player look like a bell cow — and the
            # first dry run priced an 88% scorer at +125, which the
            # credibility guard rightly refused wholesale. A college
            # team's stud tops out near 45% of its TDs, and a rate of
            # 1.05 caps P(scores) at ~65% — the -200 window floor stops
            # quoting anyone the books believe in harder than that
            # anyway.
            base = clamp(base, 0.01, 0.45)
            # MEASURED touchdowns beat the proxy where they exist, blended
            # by sample exactly as the NFL model blends its TD history: a
            # player's own scoring rate is evidence about HIM, where the
            # yardage share only describes his workload. The box ingest
            # derives `anytime_td` per game (engine/sources/cfbdata), so
            # this engages as seasons re-ingest and sharpens all year.
            td_mean = u.get("anytime_td")
            td_reason = []
            if td_mean is not None and u["games"] >= 3:
                w = clamp(u["games"] / TD_HISTORY_GAMES, 0.0,
                          TD_HISTORY_MAX_WEIGHT)
                hist_share = clamp(td_mean / CFB_AVG_TEAM_OFF_TDS, 0.0, 0.45)
                base = clamp(w * hist_share + (1 - w) * base, 0.01, 0.45)
                td_reason = [f"Scores {td_mean:.2f} TD/game over "
                             f"{u['games']} logged game(s) — measured, "
                             f"blended with the role share"]
            d_mult, d_reasons = defense_multiplier(conn, opp, season)
            s_mult, s_reasons = script_multiplier(spread_home, is_home, pos)
            w_mult, w_reasons = weather_multiplier(g.get("weather"), pos)
            rate = clamp(team_tds * base * d_mult * s_mult * w_mult,
                         0.005, 1.05)
            prob = prob_at_least_one(rate)
            reasons = [
                f"Team implied total {implied:.1f} → {team_tds:.2f} "
                f"expected offensive TDs",
                f"{share:.0%} of {side}’s rushing + receiving yards "
                f"({u['games']} game sample) — read as a {pos} role",
            ] + td_reason + d_reasons + s_reasons + w_reasons
            caveats = ["College feeds carry no red-zone or snap data — "
                       "opportunity is inferred from yardage share alone"]
            if usage_season and usage_season != season:
                caveats.append(
                    f"Role built from {usage_season} logs (this season’s "
                    f"boxes aren’t in yet) — returning production is real "
                    f"evidence, a transfer is invisible to it")
            if u["games"] < 4:
                caveats.append(f"Thin sample ({u['games']} game(s) logged)")

            # The most-likely list first, because it takes everyone at a
            # sane real price — the value window below decides only what
            # may become a PICK. Same tempering the picks get, so the
            # two lists cannot disagree about the same player.
            if in_odds_window(odds, CFB_WATCH_ODDS):
                from ..longshots import calibrated_prob
                from ..longshots import vig_of
                wp, wimp = calibrated_prob("cfb", "anytime_td", prob, odds,
                                           best.get("no_odds"),
                                           hold_override=fairs.get(norm))
                wvig, wsrc, wlisted = vig_of(fairs.get(norm), "cfb",
                                             "anytime_td",
                                             best.get("no_odds"))
                wev = wp * american_to_decimal(odds) - 1.0
                if wev <= 0.60:        # a broken price is not a likelihood
                    watch_rows.append({
                        "player": u["player"], "team": side,
                        "opponent": opp, "book": best.get("book", ""),
                        "odds": odds,
                        "model_prob": round(wp, 4),
                        "implied_prob": round(wimp, 4),
                        "vig": round(wvig, 4), "vig_source": wsrc,
                        "vig_listed": wlisted,
                        "ev_per_unit": round(wev, 4),
                        "primary_reason": reasons[1],
                        "caveats": caveats[:1],
                        "game_date": g.get("date", ""),
                        "kickoff": g.get("kickoff", ""),
                    })

            if not in_odds_window(odds, CFB_TD_ODDS):
                census["outside_window"] += 1
                continue
            pick = build_pick(
                player=u["player"], team=side, opponent=opp,
                market="anytime_td", label="Anytime TD",
                book=best.get("book", ""), odds=odds,
                model_prob=prob, under_odds=best.get("no_odds"),
                opportunities=u["carries"] + u["receptions"],
                opp_target=OPP_TARGET.get(pos, 12.0),
                primary_reason=reasons[0], reasons=reasons, caveats=caveats,
                sport="cfb",
                data_quality=0.8 if usage_season == season else 0.72,
                hold_override=fairs.get(norm))
            if pick:
                pick.game_date = g.get("date", "")
                pick.game_kickoff = g.get("kickoff", "")
                census["priced"] += 1
                picks.append(pick)
    chosen = select(picks, per_key_cap=per_game,
                    key=lambda p: tuple(sorted((p.team, p.opponent))),
                    limit=limit)
    rows = [p.to_dict() for p in chosen]
    have = {r.get("player") for r in rows}
    watch_rows.sort(key=lambda r: -r["model_prob"])
    watch = [w for w in watch_rows if w["player"] not in have][:CFB_WATCH_LIMIT]
    return rows, census, watch
