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


def usage_table(conn, season: int | None = None,
                force: bool = False) -> tuple[int, dict]:
    """``(season_used, {team: {norm_name: usage}})`` from ingested logs.

    ``usage`` = {player, carries, receptions, rush_yds, rec_yds, games}
    (per-game means; games = distinct box scores). Falls back to the
    NEWEST season holding CFB logs, because in August the current season
    has none — the caller states the fallback on every pick it feeds.
    """
    from ..sources.oddsapi import normalize_name
    # `force` reads the season asked for however thin it is — the only
    # caller is `merged_usage`, which wants THIS season's partial logs
    # precisely so it can weight them by how few games they are. Without
    # it the thin-season guard below would hand back last season twice
    # and the blend would blend a table with itself.
    if not force and (season is None
                      or _players_logged(conn, season) < MIN_SEASON_PLAYERS):
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


#: Games of current-season play before a player's own logs outweigh his
#: prior season, in `merged_usage`. Fitted over 20,916 college
#: player-week states, walked forward: predicting the rest of a player's
#: season from what was known at that point, k = 3 is the best ranking
#: and k = 4 to 6 the best absolute error, so the ranking end is taken.
#:
#: THE RULE THIS REPLACES WAS ALL-OR-NOTHING. `usage_table` serves the
#: current season once MIN_SEASON_PLAYERS are logged and the previous one
#: before that — for EVERYBODY AT ONCE. A player with no prior season is
#: therefore invisible until the whole table flips, which is most of
#: September, and a returner is served a stale season while this one is
#: already informative.
#:
#: Head to head on the rows the old rule can price at all:
#:
#:     rule                      rank    MAE
#:     all-or-nothing           0.344  0.2863
#:     blend, k = 3             0.365  0.2593
#:
#: and it prices 5,327 further states — a quarter of the board — that the
#: old rule cannot answer, 2,868 of them first-year players. On those the
#: blend ranks 0.120 against 0.000 for pricing them at a league rate.
#:
#: The NFL side has had this since it shipped (`projection.
#: USAGE_PRIOR_GAMES = 4`); college never got it, which is why the
#: freshman hole read as a missing recruiting feed rather than as a
#: missing blend.
USAGE_PRIOR_GAMES = 3


def merged_usage(conn, season: int) -> tuple[int, dict, dict]:
    """``(season_used, {team: {name: usage}}, {(team, name): provenance})``.

    Per player, not per table: whatever he has shown THIS season, shrunk
    toward what he did LAST season by how many games he has actually
    played. A first-year player has no prior season, so his own games
    carry their own weight from the first one — which is the whole point,
    since he is otherwise not on the board at all.

    Provenance travels with it because the card has to say which it is.
    """
    from ..sources.oddsapi import normalize_name          # noqa: F401
    _prior_season, prior = usage_table(conn, season)
    current: dict = {}
    if season and _players_logged(conn, season) > 0:
        _cs, current = usage_table(conn, season, force=True)
    if not current:
        return _prior_season, prior, {}

    fields = ("carries", "receptions", "rush_yds", "rec_yds",
              "rz_car", "rz_rec")
    out: dict = {}
    why: dict = {}
    for team, players in current.items():
        for name, cur in players.items():
            old = (prior.get(team) or {}).get(name)
            games = int(cur.get("games") or 0)
            if not old or _prior_season == season:
                # Nothing to blend toward — his own games ARE the read.
                out.setdefault(team, {})[name] = dict(cur)
                why[(team, name)] = ("own", games, 0)
                continue
            w = games / (games + USAGE_PRIOR_GAMES) if games else 0.0
            merged = dict(cur)
            for f in fields:
                merged[f] = w * float(cur.get(f) or 0.0)                     + (1.0 - w) * float(old.get(f) or 0.0)
            merged["games"] = games + int(old.get("games") or 0)
            merged["position"] = cur.get("position") or old.get("position", "")
            out.setdefault(team, {})[name] = merged
            why[(team, name)] = ("blend", games, int(old.get("games") or 0))

    # Anyone with a prior season and no game yet keeps his old row, which
    # is exactly what the old rule gave him and no worse.
    for team, players in prior.items():
        for name, old in players.items():
            if name in (out.get(team) or {}):
                continue
            out.setdefault(team, {})[name] = dict(old)
            why[(team, name)] = ("prior", 0, int(old.get("games") or 0))
    return season, out, why


def _usage_quality(prov) -> float:
    """How much of a role's evidence is this season's, as a data-quality
    weight. Mirrors the two numbers the board used before the blend —
    0.80 for a role built on the current season, 0.72 for one built on
    last — and puts a thinner number on the case the old rule could not
    represent at all: a first-year player with a game or two and nothing
    behind him."""
    if not prov:
        return 0.72
    kind, games, _prior = prov
    if kind == "prior":
        return 0.72
    if kind == "own":
        # His own games are all there is. Two of them is not a season.
        return 0.80 if games >= 4 else max(0.55, 0.55 + 0.0625 * games)
    return 0.72 + 0.08 * (games / (games + USAGE_PRIOR_GAMES))


def usage_reason(prov) -> str:
    """One sentence naming which season a role was actually built from."""
    if not prov:
        return ""
    kind, games, prior_games = prov
    if kind == "own":
        return (f"Role from his own {games} game"
                f"{'s' if games != 1 else ''} this season")
    if kind == "prior":
        return (f"Role from last season's {prior_games} game"
                f"{'s' if prior_games != 1 else ''} — none logged yet "
                f"this year")
    w = games / (games + USAGE_PRIOR_GAMES) if games else 0.0
    return (f"Role {w:.0%} from his {games} game"
            f"{'s' if games != 1 else ''} this season, the rest from last")


def teams_by_name(conn, season: int) -> dict:
    """``{normalised name: {teams}}`` for one season's logged players.

    THE TRANSFER PROBLEM, WHICH IS A COLLEGE PROBLEM. `usage_table` keys
    a player by (team, name), and the board finds him by asking which of
    the two teams in the game has him. A player who changed schools over
    the summer is under neither, so he is dropped as "no usage" even
    though a full season of his production is sitting in the logs under
    his old team.

    Measured over the population a book actually quotes — players with 20
    or more touches the following season:

                       found   transferred   no prior season
        2023 -> 2024   55.1%      19.9%          25.0%
        2024 -> 2025   52.9%      25.2%          21.9%

    A quarter of the quoted board, invisible. On 2026-08-29 the college
    build dropped 53 of 84 quoted players for want of usage, and this is
    about half of that. The NFL hit the same thing far more mildly and
    fixed it the same way (`engine.nflusage.season_teams`); the portal
    makes it several times larger here.
    """
    from ..sources.oddsapi import normalize_name
    out: dict = {}
    for r in conn.execute(
            "SELECT DISTINCT team, player FROM player_game_logs "
            "WHERE sport='cfb' AND season=? AND market IN "
            "('carries','receptions','rush_yds','rec_yds')", (int(season),)):
        out.setdefault(normalize_name(r["player"]), set()).add(r["team"])
    return out


def rosters_for(teams, season: int) -> dict:
    """``{normalised name: team}`` for the teams on this slate, this season.

    WEEK ONE IS THE ONLY WEEK THIS MATTERS and it is the week it matters
    most. `teams_by_name` reads the current season's own logs, which are
    empty until somebody plays — so in week one a transfer cannot be
    placed at all and is dropped. ESPN publishes the current roster keyed
    by the same team id `games` already stores, so the join is exact.

    Never raises and never blocks a board: a team whose roster will not
    load is simply absent, and those players fall back to being dropped,
    which is what happened before this existed.
    """
    from ..sources.cfbdata import fetch_team_roster, parse_team_roster
    out: dict = {}
    for team in dict.fromkeys(t for t in teams if t):
        try:
            got = parse_team_roster(fetch_team_roster(team))
        except Exception:                                     # noqa: BLE001
            continue
        for norm in got:
            # A name on two rosters is a name we cannot place, so it goes
            # on neither rather than on whichever loaded first.
            out[norm] = "" if norm in out and out[norm] != team else team
    return {k: v for k, v in out.items() if v}


def resolve_side(norm: str, home: str, away: str, usage: dict,
                 current: dict | None = None) -> tuple[str, str]:
    """``(side he plays for, team his usage is filed under)``, or ``("","")``.

    Two different teams, and conflating them is the whole bug. The SIDE
    decides his implied total and his game script; the USAGE TEAM is
    wherever last season's production happens to be filed.

    A player found under one of the two teams gives the same answer for
    both, which is every non-transfer. For a transfer, the side comes
    from the CURRENT season's logs — once he has played a game, ESPN's
    box score files him under his new school — and the usage still comes
    from the old one.

    ``current`` is `teams_by_name` for the season being played. It is
    empty in week one, when nobody has played yet, and this returns
    nothing rather than guessing: putting a back on the wrong side of a
    30-point spread is worse than leaving him off the board.
    """
    for t in (home, away):
        if norm in (usage.get(t) or {}):
            return t, t
    now = (current or {}).get(norm)
    if not now:
        return "", ""
    side = next((t for t in (home, away) if t in now), "")
    if not side:
        return "", ""                    # quoted here, logged elsewhere
    # He is on this team NOW; find where his usage actually lives.
    for team, players in usage.items():
        if norm in players:
            return side, team
    return "", ""


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


#: Game script's effect on a player's SHARE of his team's touchdowns,
#: fitted over 4,123 lead-back and 4,105 top-receiver games (2022-25).
#:
#: THE OLD FORM WAS MONOTONE AND THAT IS THE BUG. It read
#: `1 + 0.005 x lead` for a back, so the bigger the favourite the more
#: touchdown equity it handed him, all the way to a +12% clamp. The
#: handbook calls the opposite "the single most common way college
#: football prop bettors lose bets they handicapped correctly", and the
#: logs agree: a lead back's share of his team's touchdowns RISES to
#: about a two-touchdown favourite and falls away after, because past
#: that margin the starters come out. Measured share, by margin:
#:
#:     favoured by   0-7   7-14  14-21  21-28   28+
#:     lead back    0.250  0.234  0.236  0.251  0.201
#:     old model    1.018  1.052  1.087  1.120  1.120
#:
#: The underdog end was worse and it is the end nobody was watching: a
#: back on a 14-point-plus underdog scored 0.10-0.18 of his team's
#: touchdowns against the old model's 0.88-0.93 multiplier, roughly
#: twice what the data supports.
#:
#: Both curves are quadratics in the lead, normalised to 1.0 at a
#: pick'em. Chosen by LEAVE-ONE-SEASON-OUT: fitted on three seasons and
#: scored on the fourth, summed over four held-out seasons, the quadratic
#: beat the old form in EVERY one --
#:
#:     lead back      fitted 36.6   old 51.0   no script term 69.9
#:     top receiver   fitted 35.0   old 45.1   no script term 54.9
#:
#: (chi-square of band means against realised, so it measures the thing a
#: multiplier is for: systematic bias in an expectation. Per-game squared
#: error cannot see this at all -- one player's share of one game is so
#: noisy that a 20% systematic shift sits inside it, which is why the
#: first pass through this looked like a tie.)
#:
#: RE-CHECKED AND LEFT ALONE, 2026-08-30, after a measurement that looked
#: like it condemned the receiver curve and did not.
#:
#: Scoring the whole WR+TE GROUP's share of its team's touchdowns by
#: weighted squared error, the shipped receiver curve was WORSE THAN
#: HAVING NO SCRIPT TERM AT ALL in three of four held-out seasons
#: (0.08845 against 0.08820), and a two-sided linear form beat both.
#: That is a real result and it is about a different population.
#:
#: Re-run on the population the curve is FOR -- the lead receiver, who is
#: the one the book actually quotes -- with the objective it was fitted
#: under, the shipped form wins by a distance:
#:
#:     summed held-out chi-square   no script   SHIPPED   two-sided
#:     CFB lead receiver               56.4       32.6       39.1
#:     CFB lead back                  100.2       74.1       76.7
#:     NFL lead receiver                26.7       25.8       28.8
#:     NFL lead back                    41.9       39.3       44.7
#:
#: Both readings are true at once, and together they say something the
#: curve alone does not: a heavy favourite's WR1 loses share TO HIS OWN
#: BACKUPS. The group keeps its touchdowns, the starter stops getting
#: them. That is the starters-come-out effect showing up on the passing
#: side, and it is why the group-level number cannot see the curve.
#:
#: PINNED BECAUSE OF HOW CLOSE THIS CAME. The group measurement was run
#: first and read as a refutation; acting on it would have deleted a term
#: worth 24 chi-square points on the priced population to fix a bias in
#: players nobody prices. Same error as the pick-bar reading earlier this
#: month -- measure the population the model is applied to, or the number
#: is about something else.
RB_SCRIPT = (0.007047, -0.0002404)
WR_SCRIPT = (-0.007889, 0.00008716)

#: Beyond this the fit is extrapolating rather than measuring, so the
#: lead is held at the edge. College spreads reach 45 and a quadratic
#: taken that far outside its data goes somewhere silly.
SCRIPT_LEAD_CAP = 35.0

#: Where the curves actually run inside that range. Kept as an explicit
#: floor and ceiling so a re-fit cannot quietly widen the effect.
RB_SCRIPT_CLAMP = (0.55, 1.10)
WR_SCRIPT_CLAMP = (0.80, 1.35)


def script_multiplier(spread_home, is_home: bool, pos: str
                      ) -> tuple[float, list[str]]:
    """Game script's effect on a player's share of his team's TDs.

    Not the team's scoring — that is already in the implied total. This
    is only how the equity divides once the team scores, which is the one
    thing a spread says about a player that the total does not.
    """
    if spread_home is None:
        return 1.0, []
    lead = -float(spread_home) if is_home else float(spread_home)
    lead = clamp(lead, -SCRIPT_LEAD_CAP, SCRIPT_LEAD_CAP)
    if pos == "RB":
        b, c = RB_SCRIPT
        mult = clamp(1.0 + b * lead + c * lead * lead, *RB_SCRIPT_CLAMP)
    elif pos in ("WR", "TE"):
        b, c = WR_SCRIPT
        mult = clamp(1.0 + b * lead + c * lead * lead, *WR_SCRIPT_CLAMP)
    else:
        return 1.0, []
    reasons = []
    if abs(lead) >= 6.0 and abs(mult - 1.0) >= 0.02:
        side = "favoured" if lead > 0 else "underdog"
        # SAY WHICH SIDE OF THE HUMP, because "-9% for a 30-point
        # favourite" reads as a mistake without it.
        why = ""
        if pos == "RB" and lead >= 21:
            why = " — starters come out once a game is decided"
        elif pos == "RB" and lead <= -14:
            why = " — a buried back gets carries, not goal-line work"
        elif pos in ("WR", "TE") and lead <= -14:
            why = " — trailing teams throw"
        elif pos in ("WR", "TE") and lead >= 21:
            why = " — a team this far ahead stops throwing"
        reasons.append(f"Game script: {side} by {abs(lead):.0f} — "
                       f"{(mult - 1) * 100:+.0f}% of his team's TD equity "
                       f"for a {pos}{why}")
    return mult, reasons


def defense_multiplier(conn, opponent: str, season: int
                       ) -> tuple[float, list[str]]:
    """Always 1.0, with the opponent's scoring record as context.

    THE MARKET'S TOTAL ALREADY PRICES THE DEFENCE, and multiplying by our
    own read of it counted the same thing twice. This used to return
    points allowed against the FBS average, up to +/-20%, and
    `build_cfb_td_longshots` multiplied it onto a team-touchdown estimate
    that comes FROM the implied total — a number the book set knowing
    exactly how good that defence is.

    Measured over 3,920 walk-forward games, predicting the opponent's
    offensive touchdowns, scored across bands of the old multiplier:

        implied total alone                 chi-square    3.0
        implied total x defence multiplier  chi-square  181.8

    At the ends it was not subtle. A stingy defence (multiplier at or
    below 0.90) drew a prediction of 2.22 touchdowns against a realised
    2.59, and a generous one 4.13 against 3.56 — sixteen to nineteen per
    cent out, in opposite directions, on more than half the board.

    Leave-one-season-out settles the size: summed over four held-out
    seasons, keeping it scores 196.1, dropping it 13.1, and the
    best-fitting partial weight (0.04 to 0.14) scores 14.6 — no better
    than zero. There is nothing left in this signal once the total is in,
    so it is worth exactly nothing and is applied as nothing.

    CONFIRMED A THIRD TIME, BETWEEN GAMES, 2026-08-30. The player-level
    AUC test could not settle this: the spread and the total are CONSTANT
    inside a game, so they never separate two players on the same team,
    and that measurement understates them by construction. Their real job
    is scaling a whole team's expected touchdowns, which only shows up
    between games. So it was measured there — one row per team-game,
    predicting the offensive touchdowns the team's skill players actually
    scored, leave-one-season-out:

        held-out RMSE               NFL (2,820)   CFB (5,398)
        nothing but the mean           1.3763        1.8186
        implied total                  1.2721        1.5391
        implied total + spread         1.2722        1.5392
        implied total + opp defence    1.2722        1.5374

    The implied total is the entire team-level signal. The spread adds
    nothing, which is arithmetic — implied = (total - spread) / 2 already
    contains it, and its raw correlation with touchdowns (-0.314 NFL,
    -0.480 CFB) is the implied total wearing a different hat. The
    opponent's own touchdowns-allowed history adds nothing either: dead
    flat in the NFL (raw correlation +0.038) and a tenth of a per cent in
    college, from a term with four seasons behind it.

    What this does NOT say is that game script does not matter. Script
    does not change how many touchdowns a team scores; it changes who
    scores them, which is a within-team question this test cannot see and
    `script_multiplier` answers separately.

    The RECORD is still returned as a reason, because a reader deserves
    to know what the opponent has been conceding. It is disclosure, not a
    factor, and the sentence says so — a number that moves the card
    without moving the price is the bug this file keeps finding.
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
    pa = float(row["pa"])
    if abs(pa - CFB_AVG_TEAM_POINTS) < 4.0:
        return 1.0, []                   # nothing worth saying
    side = "concedes" if pa > CFB_AVG_TEAM_POINTS else "allows only"
    return 1.0, [f"{opponent} {side} {pa:.0f} a game over {n} result(s) "
                 f"against an FBS average of {CFB_AVG_TEAM_POINTS:.0f} — "
                 f"context only, since the game total already prices it"]


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
    from ..odds import american_to_decimal, american_to_prob
    usage_season, usage, usage_why = merged_usage(conn, season)
    # Where each player is filed THIS season, so a transfer can be found
    # under the school his production is filed at. Empty in week one and
    # fills in as games are played — see `resolve_side`.
    current: dict = {}
    # ALWAYS BUILT NOW, and that is a change `merged_usage` forced. The
    # old guard was `if usage_season != season` — fine when the table was
    # all-or-nothing, because a table already on this season had every
    # player filed under the right school. The merged table reports the
    # CURRENT season whenever a single game has been played, so that
    # guard would switch the transfer bridge off in week two and leave it
    # off, which is the half of the college board it exists to recover.
    # Who has played THIS season, which is empty in week one...
    current = teams_by_name(conn, season)
    # ...and the published rosters, which are not. Logs win where both
    # speak: a box score is what happened, a roster is a plan.
    slate = [t for g in (games or []) for t in (g.get("home"), g.get("away"))]
    for norm, team in rosters_for(slate, season).items():
        current.setdefault(norm, set()).add(team)
    census = {"quoted_players": 0, "no_usage": 0, "outside_window": 0,
              "priced": 0, "transfers": 0, "usage_season": usage_season}
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
            side, usage_team = resolve_side(norm, home, away, usage, current)
            if side and usage_team != side:
                census["transfers"] += 1
            if not side:
                census["no_usage"] += 1
                continue
            u = usage[usage_team][norm]
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
            # HIS OLD TEAM'S volume, not his new one's. The share is a
            # statement about the season the numbers came from — dividing
            # last year's touches by this year's roster would compare two
            # different teams and call it a role.
            team_u = usage.get(usage_team) or {}
            vol = u["rush_yds"] + u["rec_yds"]
            team_vol = sum(p["rush_yds"] + p["rec_yds"]
                           for p in team_u.values()) or 1.0
            share = clamp(vol / team_vol, 0.0, 1.0)
            # RED-ZONE TOUCHES, at a small fitted weight. A team with no
            # red-zone rows at all — a board built from a box-score feed
            # that cannot see field position — falls back to the yardage
            # share, so the blend is a no-op rather than a silent
            # haircut on everybody. See RZ_SHARE_WEIGHT.
            # EVERY player on the team, quarterbacks included, and that
            # is load-bearing rather than incidental. College offences
            # give the quarterback the majority of inside-3 carries far
            # more often than NFL ones do, and the handbook makes it a
            # hard rule: "before you bet any running back's touchdown
            # prop, pull the team's quarterback share of inside-5 rush
            # attempts. If it's above 40%, the running back's touchdown
            # ceiling is structurally capped."
            #
            # THE RULE AS WRITTEN IS NOT IN THIS DATA, and the mechanism
            # is already here. Over 2,203 lead-back games with the prior
            # inside-5 split logged, the handbook's 40% line separates
            # almost nothing — 0.250 of his team's touchdowns below it
            # against 0.238 above, z = +0.74. There IS a decline from 0%
            # to 40% (0.266 down to 0.217), and it reverses in the
            # thinnest band above 55%.
            #
            # More to the point, adding quarterback inside-5 share as a
            # SEPARATE term on top of this denominator made the fit worse
            # in every held-out season (chi-square 24.7 to 31.1) with a
            # coefficient of the wrong sign. A quarterback who takes
            # goal-line carries is already in `team_rz`, so he already
            # dilutes the back's share; a second term double-counts him.
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
            # 1.0 by measurement, not by omission — see defense_multiplier.
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
            # WHICH SEASON THIS ROLE CAME FROM, per player rather than
            # per board. `merged_usage` shrinks a man's own games toward
            # his prior season by how many he has played, so two players
            # on the same card can legitimately be reading different
            # evidence — a returner four games in, and a freshman with
            # nothing but those four games.
            prov = usage_why.get((usage_team, norm))
            said = usage_reason(prov)
            if said:
                reasons.append(said)
            caveats = ["College feeds carry no red-zone or snap data — "
                       "opportunity is inferred from yardage share alone"]
            if prov and prov[0] == "prior":
                caveats.append(
                    "Role built from last season’s logs (he has not "
                    "played yet this year) — returning production is "
                    "real evidence, a changed role is invisible to it")
            elif prov and prov[0] == "own" and prov[1] < 3:
                caveats.append(
                    f"No prior season anywhere — this is {prov[1]} game"
                    f"{'s' if prov[1] != 1 else ''} of evidence and "
                    f"nothing behind it")
            elif not prov and usage_season and usage_season != season:
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
                        "book_prob": round(american_to_prob(odds), 4),
                        "vig": round(wvig, 4), "vig_source": wsrc,
                        "vig_listed": wlisted,
                        "ev_per_unit": round(wev, 4),
                        "primary_reason": reasons[1],
                        # THE WHOLE CHAIN — implied total, share of the
                        # team's touchdowns, game script, everything the
                        # value picks already carried. This list answers
                        # "who is most likely to score", which is what
                        # the model is measurably good at (AUC 0.675 over
                        # 29,047 graded college player-games, stable
                        # across four seasons) where its claimed edge
                        # against the market tests as noise. Shipping the
                        # honest product with one sentence of reasoning
                        # had it backwards.
                        "reasons": reasons,
                        "caveats": caveats,
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
                # PER PLAYER, NOT PER BOARD, and this had to move with
                # `merged_usage` or it would have quietly become a lie:
                # the merged table reports the CURRENT season, so the old
                # test would have called a role built entirely from last
                # year's logs full-quality. A man with no prior season
                # and two games is thinner still, and says so.
                data_quality=_usage_quality(usage_why.get((usage_team, norm))),
                hold_override=fairs.get(norm))
            if pick:
                pick.game_date = g.get("date", "")
                pick.game_kickoff = g.get("kickoff", "")
                census["priced"] += 1
                # Ethan, 2026-09-02: "1. No" to betting Group of Five at
                # all. The pick is still built and explained — it lands
                # on the watch with the rest — but it never grades as a
                # bet in a game where neither side is a power program.
                from .model import (BET_GROUP_OF_FIVE, is_group_of_five,
                                    NOT_A_POWER_GAME)
                if not BET_GROUP_OF_FIVE and is_group_of_five(g):
                    pick.grade = "Pass"
                    pick.stake_units = 0.0
                    pick.caveats = list(pick.caveats) + [NOT_A_POWER_GAME]
                    census["group_of_five"] = census.get("group_of_five", 0) + 1
                picks.append(pick)
    chosen = select(picks, per_key_cap=per_game,
                    key=lambda p: tuple(sorted((p.team, p.opponent))),
                    limit=limit)
    rows = [p.to_dict() for p in chosen]
    have = {r.get("player") for r in rows}
    watch_rows.sort(key=lambda r: -r["model_prob"])
    watch = [w for w in watch_rows if w["player"] not in have][:CFB_WATCH_LIMIT]
    return rows, census, watch
