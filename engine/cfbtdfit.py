"""Grade and fit the COLLEGE touchdown model on our own four seasons.

`engine.tdbacktest` did this for the NFL on 2026-08-27 and found a model
that had never been measured. College could not be measured at all that
day, for a blunt reason: the database held TEN CFB player rows. With
`engine.sources.cfbstats` ingesting play-level production and
`engine.sources.cfblines` attaching a closing spread and total to all
3,132 ingested games, the college model can finally be asked the same
question — and asked it about the chain it actually runs.

WHAT THIS REPLAYS. The live board prices

    rate = team TDs (from the book's implied total)
           × the player's scoring role
           × defense × game script × weather

and every term but the last is here. The implied team total and the game
script come from the game's own closing numbers. The opponent's scoring
generosity is recomputed from games ALREADY PLAYED (`defense_to_date`) —
`cfb.tds.defense_multiplier` reads a whole season, which is right on a
live board and leaks in a replay of a finished one. Weather is the one
term held neutral: our kickoff forecasts start the day we ask for them
and there is no historical sky to replay.

THE FIRST ANSWER THIS GAVE WAS WRONG, AND THE FEED WAS WHY. Run against
the raw ingest, the replay reported a model over-confident by nine to
eleven points through the bands the picks live in, and the obvious ship
was a correction pulling every college longshot DOWN. It was an
artifact. Weeks 9 through 16 of the 2025 file are missing their
touchdowns — week 9 has the scoring plays with nobody named on them, the
rest are missing the plays — so a third of the held-out season recorded
every scorer as having scored nothing. `cfbstats.week_modes` now audits
each week against the points its games actually produced. On clean data
the sign REVERSES: the model is conservative exactly where the longshots
are.

WHAT IT FOUND, over 29,047 graded player-games (chosen on 2022-23,
scored on 2024-25):

  * The blend the college board shipped — the player's own touchdown
    rate weighted `games/10` and capped at 0.70 — had never once
    engaged, because there were no logs for it to read, and the guess
    was so far past the useful range that it scored WORSE than
    switching the history off. Fitted: `games/20` capped at 0.20.
  * The position the model priced off was INFERRED from the usage mix
    and wrong for 7,835 player-games. Fixing the label while keeping
    anchors tuned against the wrong label made the model worse; the two
    only pay together. See `cfb.tds.POSITION_TD_SHARE`.
  * Red-zone role earns a small place in the share after all — see
    `ROLE_FEATURES` for the measurement that first said no and the one
    that reversed it.
  * The model is CONSERVATIVE where it matters. Held out, the 0-10%
    band claimed 7.3% and landed 11.5%; the 10-18% band claimed 14.1%
    and landed 17.5%. Those are the +200 to +900 quotes the college
    longshot board exists to find, and the model was talking itself out
    of them.

AND ONE THING IT REFUSED TO IMPROVE. `fit_all` re-fits every constant
jointly, and asked to beat the numbers above it chose a slightly
different corner of the same region — red zone 0.15, anchors 0.30 /
0.18 / 0.14 / 0.26 — worth 0.0002 of TRAINING Brier and 0.0001 of
held-out LOSS (0.18158 against the shipped 0.18150). So nothing moved.
A fitter that only ever ratchets is not measuring anything.

The conservative bands are what `fit_calibration` acts on. That fit is a
PRIOR and says so: `engine.journalfit` refits `cfb:anytime_td` from
actually-settled picks once 200 of them exist, and replaces this one.
"""

from __future__ import annotations

import math

from .cfb.tds import (POSITION_TD_SHARE, POSITION_TYPICAL_SHARE,
                      CFB_AVG_TEAM_OFF_TDS, CFB_AVG_TEAM_POINTS,
                      MIN_DEFENSE_GAMES, RZ_SHARE_WEIGHT, TD_HISTORY_GAMES,
                      TD_HISTORY_MAX_WEIGHT, implied_total_for, role_of,
                      script_multiplier)
from .statmath import clamp
from .tdbacktest import TDBacktest

#: Games a player must already have this season before he can be graded.
#: Below three the "own touchdown rate" the fit is about is one or two
#: Saturdays of noise.
MIN_PRIOR_GAMES = 3

#: The markets the replay reads. Deliberately the box-score four plus the
#: outcome — the red-zone markets `engine.sources.cfbstats` also ingests
#: are measured below and did not earn a place in the model; see
#: `ROLE_FEATURES`.
MARKETS = ("anytime_td", "carries", "receptions", "rush_yds", "rec_yds",
           "rz_car", "rz_rec")

#: Player-games behind a college touchdown calibration before it may be
#: adopted. Same floor as the NFL's, and for the same reason:
#: `calibrate.fit` runs its own bake-off on a held-out slice, so this is
#: only the point below which the split itself is noise.
MIN_FIT_PAIRS = 2_000

#: Seasons the fit trains on, and the ones it is scored on. Held out by
#: SEASON rather than at random: two rows from the same player-season
#: share his form window, so a random split leaks him across the fence.
TRAIN_SEASONS = (2022, 2023)
TEST_SEASONS = (2024, 2025)

#: The grid `fit_blend` searches. `games` is the denominator that decides
#: how fast a player's own scoring record takes over from his role share;
#: `weight` is the ceiling it may take.
BLEND_GAMES = (3.0, 5.0, 7.0, 10.0, 14.0, 20.0, 25.0, 30.0)
#: 0.0 is in the grid ON PURPOSE. A family whose smallest member still
#: does the thing cannot report that the thing is not worth doing, and
#: an argmin pinned to a grid edge is usually a question the grid was
#: not allowed to answer.
BLEND_WEIGHTS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)

#: What the college board carried BEFORE this fit — a guess, copied
#: across from the NFL model's own pre-measurement guess. Frozen here so
#: `fit_blend` can always report what the change bought, rather than
#: comparing the fitted setting with itself the moment it is installed.
PREVIOUS_BLEND = (10.0, 0.70)

#: MEASURED TWICE, AND THE SECOND ANSWER WAS THE OPPOSITE OF THE FIRST.
#: `engine.sources.cfbstats` ingests red-zone carries, inside-the-five
#: carries and red-zone receptions, and the working assumption was that
#: college's yardage-share proxy — which `engine.cfb.tds` caps hard
#: precisely because it overstates concentration — would fall to them
#: the way the NFL model leans on red-zone role.
#:
#: The first measurement said no: inside the model's own multiplicative
#: share term, red zone bought one ten-thousandth of held-out Brier and
#: was left out. That measurement was made on the ROLE chain — game
#: script and implied total held at 1.0, because college had no
#: historical betting lines yet — and on data still carrying a third of
#: a poisoned 2025 season.
#:
#: Re-run on the real chain and clean data, the same grid picks an
#: interior 0.10, and three independent frames agree on the direction:
#:
#:     training seasons     0.18574 at zero → 0.18564 at 0.10 → 0.18592 at 0.20
#:     held out             0.18179 at zero → 0.18150 at 0.10
#:     free logistic        yardage 0.55887 → yardage + red zone 0.55603
#:
#: It is a small term and `cfb.tds.RZ_SHARE_WEIGHT` is deliberately a
#: small weight. What it is not is zero — and the earlier zero was
#: measured on a chain the board does not run.
ROLE_FEATURES = ("yardage share", "red-zone share", "own touchdown rate")


class Sample:
    """One graded player-game: what we knew going in, and what happened."""

    __slots__ = ("season", "period", "position", "share", "rz_share",
                 "td_mean", "games", "team", "opponent", "is_home",
                 "spread", "total", "team_tds", "script", "scored")

    def __init__(self, season, position, share, td_mean, games, scored,
                 period="", team="", opponent="", is_home=True,
                 spread=None, total=None, rz_share=None):
        self.season = season
        self.position = position
        self.share = share
        #: The player's share of his team's RED-ZONE touches over the
        #: same prior games. None means "no separate red-zone read", and
        #: it resolves to the YARDAGE share rather than to zero — so
        #: blending it in is a no-op on a board built from a feed that
        #: cannot see field position, rather than a silent haircut on
        #: everybody. The default is None for the same reason: a caller
        #: who does not know about the red zone must not accidentally
        #: assert that this player never goes near it.
        self.rz_share = share if rz_share is None else rz_share
        self.td_mean = td_mean
        self.games = games
        self.scored = scored
        #: The kickoff date. Carried for ONE reason: `calibrate.bake_off`
        #: holds out "the later part of the sample", which is only a
        #: held-out slice if the sample is in time order. Built the
        #: obvious way — a loop over players, each walked forward — these
        #: pairs come out grouped by PLAYER, and the judge would be
        #: scoring a fitted correction on an arbitrary subset of college
        #: football rather than on its future. `run` sorts on this.
        self.period = period
        self.team = team
        self.opponent = opponent
        #: The game's own closing numbers, which is what turns this from
        #: a replay of the ROLE into a replay of the chain. Until
        #: `engine.sources.cfblines` landed there was no historical
        #: college spread or total in the database at all, and the
        #: implied team total and the game script had to be held neutral.
        self.is_home = is_home
        self.spread = spread
        self.total = total
        #: The two terms of that chain which depend only on the GAME and
        #: the position, never on a fitted parameter. Derived once here
        #: because `fit_all` calls `probability` a few million times, and
        #: re-deriving an implied total inside that loop was most of the
        #: cost of a joint fit.
        self.team_tds = CFB_AVG_TEAM_OFF_TDS
        self.script = 1.0
        if spread is not None and total is not None:
            implied = implied_total_for(spread, total, is_home)
            if implied is not None:
                self.team_tds = max(0.0, implied) * (CFB_AVG_TEAM_OFF_TDS
                                                     / CFB_AVG_TEAM_POINTS)
            self.script = script_multiplier(spread, is_home, position)[0]


def samples(conn, seasons=None, min_prior: int = MIN_PRIOR_GAMES) -> list:
    """Walk every ingested college player-season forward, one game at a time.

    Season-to-date form, which is what `engine.cfb.tds.usage_table`
    averages on the live board — not a rolling window. Grading a model
    on a form window it does not use measures a model nobody runs.
    """
    where = "WHERE sport='cfb' AND market IN (%s)" % ",".join("?" * len(MARKETS))
    args = list(MARKETS)
    if seasons:
        where += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += [int(s) for s in seasons]
    form: dict = {}
    #: The roster position, which the live board now prices off
    #: (`engine.cfb.tds.role_of`). Replaying without it would grade a
    #: model nobody runs — and it is not a small difference: the usage
    #: inference disagrees with the roster on 7,835 of 28,141 graded
    #: player-games.
    positions: dict = {}
    for r in conn.execute(
            "SELECT season, period, player, team, position, market, value "
            "FROM player_game_logs " + where, args):
        key = (r["season"], r["team"], r["player"])
        form.setdefault(key, {}).setdefault(r["period"], {})[r["market"]] = \
            float(r["value"] or 0.0)
        if r["position"]:
            positions.setdefault(key, r["position"])

    lines, opponents = _game_lines(conn, seasons)
    team_game: dict = {}
    for (season, team, _player), weeks in form.items():
        for period, marks in weeks.items():
            bucket = team_game.setdefault((season, period, team), {})
            for market in MARKETS:
                bucket[market] = bucket.get(market, 0.0) + marks.get(market, 0.0)

    out = []
    for (season, team, player), weeks in form.items():
        ordered = sorted(weeks)
        for index, period in enumerate(ordered):
            prior = ordered[:index]
            if len(prior) < min_prior:
                continue
            n = len(prior)
            own = {m: sum(weeks[w].get(m, 0.0) for w in prior) / n
                   for m in MARKETS}
            team_vol = sum(
                team_game.get((season, w, team), {}).get(m, 0.0)
                for w in prior for m in ("rush_yds", "rec_yds")) / n
            volume = own["rush_yds"] + own["rec_yds"]
            team_rz = sum(
                team_game.get((season, w, team), {}).get(m, 0.0)
                for w in prior for m in ("rz_car", "rz_rec")) / n
            own_rz = own["rz_car"] + own["rz_rec"]
            usage = {"player": player, "carries": own["carries"],
                     "receptions": own["receptions"],
                     "rush_yds": own["rush_yds"], "rec_yds": own["rec_yds"],
                     "games": n,
                     "position": positions.get((season, team, player), "")}
            quote = lines.get((season, period, team))
            out.append(Sample(
                season=season, position=role_of(usage),
                share=clamp(volume / team_vol, 0.0, 1.0) if team_vol > 0 else 0.0,
                td_mean=own["anytime_td"], games=n, period=period,
                team=team, opponent=opponents.get((season, period, team), ""),
                is_home=bool(quote[2]) if quote else True,
                rz_share=(clamp(own_rz / team_rz, 0.0, 1.0)
                          if team_rz > 0 else None),
                spread=quote[0] if quote else None,
                total=quote[1] if quote else None,
                scored=1 if weeks[period].get("anytime_td", 0.0) > 0 else 0))
    return out


def _game_lines(conn, seasons=None) -> tuple:
    """``({(season, date, team): (home spread, total, is_home)}, opponents)``.

    The closing numbers `engine.sources.cfblines` attached to every
    ingested college game, keyed the way a player row can find them. The
    spread stays the HOME team's number whichever side is asking —
    `cfb.tds.implied_total_for` wants it that way and flips it itself.
    """
    where = "WHERE sport='cfb' AND total IS NOT NULL AND spread IS NOT NULL"
    args: list = []
    if seasons:
        where += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args = [int(s) for s in seasons]
    lines: dict = {}
    opponents: dict = {}
    for r in conn.execute(
            "SELECT season, period, home, away, spread, total "
            "FROM games " + where, args):
        key = (r["season"], r["period"])
        lines[key + (r["home"],)] = (r["spread"], r["total"], True)
        lines[key + (r["away"],)] = (r["spread"], r["total"], False)
        opponents[key + (r["home"],)] = r["away"]
        opponents[key + (r["away"],)] = r["home"]
    return lines, opponents


def defense_to_date(conn, seasons=None) -> dict:
    """``{(season, date, team): (points allowed per game, games)}`` — BEFORE.

    `engine.cfb.tds.defense_multiplier` reads a team's whole season,
    which is right on a live board (the season so far is all there is)
    and leaks in a replay of a finished one. This is the same quantity
    computed strictly from games already played, so the multiplier the
    grade uses is the multiplier the board would have had.
    """
    where = "WHERE sport='cfb' AND home_score IS NOT NULL"
    args: list = []
    if seasons:
        where += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args = [int(s) for s in seasons]
    played: dict = {}
    for r in conn.execute(
            "SELECT season, period, home, away, home_score, away_score "
            "FROM games " + where + " ORDER BY period", args):
        played.setdefault((r["season"], r["home"]), []).append(
            (r["period"], float(r["away_score"])))
        played.setdefault((r["season"], r["away"]), []).append(
            (r["period"], float(r["home_score"])))
    out: dict = {}
    for (season, team), games in played.items():
        games.sort()
        total = 0.0
        for index, (period, allowed) in enumerate(games):
            if index:
                out[(season, period, team)] = (total / index, index)
            total += allowed
    return out


def defense_multiplier(allowed, played: int) -> float:
    """Always 1.0, mirroring `cfb.tds.defense_multiplier`.

    Kept as a function rather than deleted because this module exists to
    replay THE BOARD'S OWN CHAIN — grading a model nobody runs is the
    mistake it was written to avoid — and because the fitted blend it
    produces was chosen with the old multiplier in the chain, partly
    compensating for it. Re-run the blend fit before trusting it again.

    The measurement is in `cfb.tds.defense_multiplier`: over 3,920
    walk-forward games, the implied total alone scored chi-square 3.0
    against 181.8 for the total times this term, because the book set
    that total knowing how good the defence was.
    """
    return 1.0


def role_share(sample: Sample, anchors: dict | None = None,
               rz_weight: float | None = None) -> float:
    """The position-scaled yardage share, exactly as the board builds it.

    ``rz_weight`` blends the player's red-zone touch share into the
    yardage share; left as None it takes the board's own
    `cfb.tds.RZ_SHARE_WEIGHT`, so the replay grades the model that
    ships. Pass a number to re-check the fit that chose it.
    """
    position = sample.position
    rz_weight = RZ_SHARE_WEIGHT if rz_weight is None else rz_weight
    table = anchors or POSITION_TD_SHARE
    share = ((1.0 - rz_weight) * sample.share
             + rz_weight * sample.rz_share) if rz_weight else sample.share
    base = table[position] * clamp(
        share / POSITION_TYPICAL_SHARE[position], 0.15, 1.8)
    return clamp(base, 0.01, 0.45)


def blended(sample: Sample, games_scale: float, max_weight: float,
            anchors: dict | None = None,
            rz_weight: float | None = None) -> float:
    """The role share with the player's own scoring record blended in."""
    base = role_share(sample, anchors, rz_weight)
    if sample.games < MIN_PRIOR_GAMES:
        return base
    weight = clamp(sample.games / games_scale, 0.0, max_weight)
    history = clamp(sample.td_mean / CFB_AVG_TEAM_OFF_TDS, 0.0, 0.45)
    return clamp(weight * history + (1 - weight) * base, 0.01, 0.45)


#: Rate bounds, straight from `cfb.tds.build_cfb_td_longshots`.
MIN_RATE, MAX_RATE = 0.005, 1.05


def probability(base: float, sample: Sample | None = None,
                defense: float = 1.0) -> float:
    """P(scores at least one) — the board's own chain, weather aside.

    Team touchdowns come from the game's implied total when the closing
    numbers are there and from the FBS average when they are not; the
    game script and the opponent's scoring generosity multiply it
    exactly as `cfb.tds.build_cfb_td_longshots` does. Weather is the one
    term held neutral: our kickoff forecasts start the day we ask for
    them, and there is no historical sky to replay.
    """
    team_tds = sample.team_tds if sample is not None else CFB_AVG_TEAM_OFF_TDS
    script = sample.script if sample is not None else 1.0
    rate = clamp(team_tds * base * script * defense, MIN_RATE, MAX_RATE)
    return 1.0 - math.exp(-rate)


def brier(rows: list, games_scale: float, max_weight: float,
          history: bool = True, defense: dict | None = None,
          anchors: dict | None = None,
          rz_weight: float | None = None) -> float:
    if not rows:
        return 0.0
    total = 0.0
    for s in rows:
        base = (blended(s, games_scale, max_weight, anchors, rz_weight)
                if history else role_share(s, anchors, rz_weight))
        total += (probability(base, s, _defense_for(defense, s))
                  - s.scored) ** 2
    return total / len(rows)


def _defense_for(table: dict | None, sample: Sample) -> float:
    if not table or not sample.opponent:
        return 1.0
    seen = table.get((sample.season, sample.period, sample.opponent))
    return defense_multiplier(*seen) if seen else 1.0


def fit_blend(rows: list, defense: dict | None = None) -> dict:
    """Choose the blend on the training seasons; report it on the held-out.

    The choice is made on TRAIN and never revisited — the held-out number
    is a report, not a second grid to pick from. That is the whole
    difference between a measurement and a story.
    """
    train = [s for s in rows if s.season in TRAIN_SEASONS]
    test = [s for s in rows if s.season in TEST_SEASONS]
    if not train or not test:
        return {"chosen": None, "train": len(train), "test": len(test)}
    best = None
    for games_scale in BLEND_GAMES:
        for max_weight in BLEND_WEIGHTS:
            score = brier(train, games_scale, max_weight,
                          defense=defense)
            if best is None or score < best[0]:
                best = (score, games_scale, max_weight)
    _score, games_scale, max_weight = best
    return {
        "chosen": (games_scale, max_weight),
        "train": len(train), "test": len(test),
        "train_brier": round(best[0], 5),
        "held_out": round(brier(test, games_scale, max_weight,
                                defense=defense), 5),
        "held_out_previous": round(brier(test, *PREVIOUS_BLEND,
                                         defense=defense), 5),
        "held_out_no_history": round(
            brier(test, games_scale, max_weight, history=False,
                  defense=defense), 5),
    }


#: The grid `fit_anchors` searches for each position's touchdown share.
#: Coarse on purpose: these are anchors a player's volume scales, and a
#: third decimal place on one would be fitting the sample.
ANCHOR_GRID = tuple(round(0.04 + 0.01 * i, 2) for i in range(38))

#: Passes of coordinate descent. Four is well past the point the values
#: stop moving; the loop exits early when they do.
ANCHOR_PASSES = 6


def fit_anchors(rows: list, defense: dict | None = None,
                games_scale: float = 20.0, max_weight: float = 0.20,
                rz_weight: float | None = None,
                anchors: dict | None = None) -> dict:
    """Each position's touchdown anchor, fitted on the training seasons.

    `cfb.tds.POSITION_TD_SHARE` was four reasoned guesses, and could not
    be anything else while the position itself was inferred from the
    usage mix. With a roster position on every row it can be measured —
    coordinate descent on 2022-23, reported on 2024-25, one position at
    a time because the four barely interact (a tight end's anchor moves
    tight ends).
    """
    train = [s for s in rows if s.season in TRAIN_SEASONS]
    if not train:
        return {}
    anchors = dict(anchors or POSITION_TD_SHARE)
    for _ in range(ANCHOR_PASSES):
        moved = False
        for position in sorted(anchors):
            best = (brier(train, games_scale, max_weight, defense=defense,
                          anchors=anchors, rz_weight=rz_weight),
                    anchors[position])
            for value in ANCHOR_GRID:
                anchors[position] = value
                score = brier(train, games_scale, max_weight,
                              defense=defense, anchors=anchors,
                              rz_weight=rz_weight)
                if score < best[0]:
                    best = (score, value)
            if best[1] != anchors[position]:
                moved = True
            anchors[position] = best[1]
        if not moved:
            break
    return anchors


#: Red-zone weights `fit_all` searches. See `cfb.tds.RZ_SHARE_WEIGHT`.
RZ_WEIGHTS = (0.0, 0.05, 0.10, 0.15, 0.20)


def fit_all(rows: list, defense: dict | None = None,
            rounds: int = 3) -> dict:
    """Every fitted constant at once, chosen on the training seasons.

    WHY THIS IS ONE FUNCTION AND NOT THREE. The blend, the position
    anchors and the red-zone weight all move the same number, so fitting
    them one at a time and installing each result makes the next fit
    answer a question about a model that no longer exists. Doing that by
    hand, the anchors and the blend chased each other across three
    passes and never sat still.

    So: for each red-zone weight, coordinate-descend the anchors and the
    blend together until they stop moving, and keep the combination with
    the best TRAINING Brier. The held-out seasons are scored once, at
    the end, and never consulted while choosing.

    Returns the chosen constants, the training score that chose them and
    the held-out score that reports them.
    """
    train = [s for s in rows if s.season in TRAIN_SEASONS]
    test = [s for s in rows if s.season in TEST_SEASONS]
    if not train or not test:
        return {"chosen": None, "train": len(train), "test": len(test)}

    best = None
    for rz_weight in RZ_WEIGHTS:
        anchors = dict(POSITION_TD_SHARE)
        blend = (float(TD_HISTORY_GAMES), float(TD_HISTORY_MAX_WEIGHT))
        for _ in range(rounds):
            anchors = fit_anchors(rows, defense=defense,
                                  games_scale=blend[0], max_weight=blend[1],
                                  rz_weight=rz_weight, anchors=anchors)
            blend = _best_blend(train, defense, anchors, rz_weight)
        score = brier(train, blend[0], blend[1], defense=defense,
                      anchors=anchors, rz_weight=rz_weight)
        if best is None or score < best[0]:
            best = (score, rz_weight, anchors, blend)

    score, rz_weight, anchors, blend = best
    return {
        "chosen": {"rz_weight": rz_weight, "anchors": anchors,
                   "games_scale": blend[0], "max_weight": blend[1]},
        "train": len(train), "test": len(test),
        "train_brier": round(score, 5),
        "held_out": round(brier(test, blend[0], blend[1], defense=defense,
                                anchors=anchors, rz_weight=rz_weight), 5),
        "held_out_shipped": round(brier(test, TD_HISTORY_GAMES,
                                        TD_HISTORY_MAX_WEIGHT,
                                        defense=defense), 5),
        "held_out_no_history": round(
            brier(test, blend[0], blend[1], history=False, defense=defense,
                  anchors=anchors, rz_weight=rz_weight), 5),
    }


def _best_blend(train: list, defense, anchors, rz_weight) -> tuple:
    """Note that ``games_scale`` stops meaning anything once the cap is
    low: with a ceiling of 0.1 and a three-game minimum sample, every
    scale from 3 upward gives the same weight to every graded row, so
    the grid is flat in that dimension and the argmin picks arbitrarily.
    Read a chosen scale as "the ramp is inert", not as a finding."""
    best = None
    for games_scale in BLEND_GAMES:
        for max_weight in BLEND_WEIGHTS:
            score = brier(train, games_scale, max_weight, defense=defense,
                          anchors=anchors, rz_weight=rz_weight)
            if best is None or score < best[0]:
                best = (score, games_scale, max_weight)
    return (best[1], best[2])


def run(conn, seasons=None, games_scale: float | None = None,
        max_weight: float | None = None) -> TDBacktest:
    """Replay the college touchdown model and grade what it claimed."""
    from .cfb.tds import TD_HISTORY_GAMES, TD_HISTORY_MAX_WEIGHT
    games_scale = TD_HISTORY_GAMES if games_scale is None else games_scale
    max_weight = (TD_HISTORY_MAX_WEIGHT if max_weight is None else max_weight)
    report = TDBacktest(label="CFB")
    rows = sorted(samples(conn, seasons=seasons),
                  key=lambda s: (s.season, s.period))
    defense = defense_to_date(conn, seasons)
    for s in rows:
        report.add(probability(blended(s, games_scale, max_weight), s,
                               _defense_for(defense, s)), s.scored)
    return report.finish()


def fit_calibration(conn, seasons=None, path=None):
    """Fit and persist a PRIOR correction for ``cfb:anytime_td``.

    A prior, and labelled one. It is measured — 28,141 graded college
    player-games, held out by season — but measured on the role chain
    with the market's own inputs held neutral, because the mirror
    carries no historical betting lines. `engine.journalfit` refits this
    key from settled picks once 200 exist, on the real chain, and that
    fit replaces this one.

    Fitted 2026-08-27: T=1.24, bias -0.120, which lifts a modelled 8% to
    11.0% and 12% to 15.1% and leaves everything above a third alone.
    `calibrate.bake_off` adopted it over doing nothing by 0.00027 of
    held-out Brier, which is thin — but the band table it is correcting
    is not: 7.3% claimed against 11.5% landed is the college longshot
    board arguing itself out of the picks it exists to find.
    """
    from . import calibrate
    report = run(conn, seasons=seasons)
    if len(report.pairs) < MIN_FIT_PAIRS:
        return None, report
    fit = calibrate.fit(report.pairs, sport="cfb", market="anytime_td")
    fit.basis = calibrate.BASIS_HISTORY
    import datetime as _dt
    fit.fitted_at = _dt.date.today().isoformat()
    calibrate.save({"cfb:anytime_td": fit}, path or calibrate.DEFAULT_PATH)
    calibrate.reset_cache()
    return fit, report


__all__ = ["MIN_PRIOR_GAMES", "MIN_FIT_PAIRS", "MARKETS", "BLEND_GAMES",
           "BLEND_WEIGHTS", "PREVIOUS_BLEND", "TRAIN_SEASONS", "TEST_SEASONS", "ROLE_FEATURES",
           "MIN_RATE", "MAX_RATE", "Sample", "samples", "role_share", "blended",
           "probability", "brier", "fit_blend", "run", "fit_calibration",
           "defense_to_date", "defense_multiplier", "fit_anchors", "fit_all",
           "ANCHOR_GRID", "RZ_WEIGHTS"]
