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

# FBS scoring baselines. ~28.8 points and ~3.4 offensive touchdowns per
# team-game is the modern FBS average — college scores more than the
# NFL and kicks fewer field goals per possession.
CFB_AVG_TEAM_POINTS = 28.8
CFB_AVG_TEAM_OFF_TDS = 3.4

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
#: Coordinate descent on 2022-23, scored on 2024-25 (`engine.cfbtdfit`):
#:
#:     inferred labels, guessed anchors     held-out Brier 0.18477
#:     roster labels,   guessed anchors                    0.18526
#:     roster labels,   FITTED anchors                     0.18434
#:
#: (measured before the blend was refitted, so all three carry the old
#: games/20 cap 0.40; the comparison between them is the point)
#:
#: The middle row is the one worth reading. Correcting the label while
#: keeping anchors that had been tuned AGAINST the wrong label made the
#: model worse — a real tight end priced off a number built for
#: misfiled receivers. The two changes only pay together, which is why
#: neither shipped alone.
#:
#: What moved: quarterbacks from 0.16 to 0.25 (college lets them run,
#: and the guess was an NFL instinct), tight ends from 0.08 to 0.11,
#: backs from 0.26 to 0.28. Receivers did not move at all.
POSITION_TD_SHARE = {"RB": 0.28, "WR": 0.15, "TE": 0.11, "QB": 0.25}

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
#: Fitted on 2026-08-27 by `engine.cfbtdfit` over 28,141 graded college
#: player-games: chosen on 2022-23, scored on 2024-25. The record wants
#: the history to come on more slowly and stop lower. Held-out Brier:
#:
#:     role share alone, no history      0.18657
#:     the guessed games/10 cap 0.70     0.18593
#:     the fitted games/25 cap 0.30      0.18446
#:
#: The training surface is FLAT across games/20-30 and every cap from
#: 0.2 to 0.7 — 0.18977 to 0.18997 — so this is a plateau, not a peak,
#: and the argmin was taken rather than argued for. What the plateau
#: does say clearly is that the old guess sat well outside it: half a
#: season of a player's own touchdown rate is worth about 30% of the
#: number, not 70% after ten games.
TD_HISTORY_GAMES = 25.0
TD_HISTORY_MAX_WEIGHT = 0.30


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
            "'anytime_td') "
            "GROUP BY team, player, market", (season,)):
        t = out.setdefault(r["team"], {})
        u = t.setdefault(normalize_name(r["player"]),
                         {"player": r["player"], "carries": 0.0,
                          "receptions": 0.0, "rush_yds": 0.0, "rec_yds": 0.0,
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
            team_tds = max(0.0, implied) * (CFB_AVG_TEAM_OFF_TDS
                                            / CFB_AVG_TEAM_POINTS)
            pos = role_of(u)
            team_u = usage.get(side) or {}
            vol = u["rush_yds"] + u["rec_yds"]
            team_vol = sum(p["rush_yds"] + p["rec_yds"]
                           for p in team_u.values()) or 1.0
            share = clamp(vol / team_vol, 0.0, 1.0)
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
                wp, wimp = calibrated_prob("cfb", "anytime_td", prob, odds,
                                           best.get("no_odds"))
                wev = wp * american_to_decimal(odds) - 1.0
                if wev <= 0.60:        # a broken price is not a likelihood
                    watch_rows.append({
                        "player": u["player"], "team": side,
                        "opponent": opp, "book": best.get("book", ""),
                        "odds": odds,
                        "model_prob": round(wp, 4),
                        "implied_prob": round(wimp, 4),
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
                data_quality=0.8 if usage_season == season else 0.72)
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
