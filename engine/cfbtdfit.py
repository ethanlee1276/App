"""Grade and fit the COLLEGE touchdown model on our own four seasons.

`engine.tdbacktest` did this for the NFL on 2026-08-27 and found a model
that had never been measured. College could not be measured at all that
day, for a blunt reason: the database held TEN CFB player rows. With
`engine.sources.cfbstats` ingesting play-level production off the
sportsdataverse mirror it holds 232,913, and the college model can
finally be asked the same question.

WHAT THIS GRADES, AND WHAT IT DELIBERATELY DOES NOT. The live board
prices

    rate = team TDs (from the book's implied total)
           × the player's scoring role
           × defense × game script × weather

and this replays the ROLE, with the three multipliers held at their
neutral value and team TDs at the FBS average. That is not a shortcut,
it is the only honest option: the mirror carries scores and Elo, not
betting lines (see `engine.sources.cfbfastr`), so there is no historical
implied total to drive the first term and no historical spread to drive
the script. The three multipliers are mean-1 adjustments by
construction, so holding them neutral grades exactly the component the
parameters below live in — and nothing else is claimed for it.

THE FIRST ANSWER THIS GAVE WAS WRONG, AND THE FEED WAS WHY. Run against
the raw ingest, the replay reported a model over-confident by nine to
eleven points through the bands the picks live in, and the obvious ship
was a correction pulling every college longshot DOWN. It was an
artifact. Weeks 10-16 of the 2025 file are missing their scoring plays
entirely — 1.5 touchdowns a game where every other week in four seasons
has six — so a third of the held-out season recorded every scorer as
having scored nothing. `cfbstats.MIN_TD_COVERAGE` now audits each week's
touchdowns against the points its games actually produced and drops the
ones the feed did not deliver. On clean data the sign REVERSES: the
model is conservative exactly where the longshots are.

WHAT IT FOUND, over 28,141 graded player-games (chosen on 2022-23,
scored on 2024-25):

  * The blend the college board shipped — the player's own touchdown
    rate weighted `games/10` and capped at 0.70 — was better than the
    role share alone (held-out Brier 0.18593 vs 0.18657) and had never
    once engaged, because there were no logs for it to read. Fitted, it
    wants to come on more slowly and stop lower: `games/25` capped at
    0.30, held out at 0.18446.
  * The position the model priced off was INFERRED from the usage mix,
    and wrong for 7,835 of those player-games. Fixing the label while
    keeping anchors tuned against the wrong label made the model worse;
    fixing both together is what pays. See `cfb.tds.POSITION_TD_SHARE`.
  * The model is CONSERVATIVE where it matters. Held out, the 0-10%
    band claimed 7.5% and landed 13.4%; the 10-18% band claimed 14.0%
    and landed 18.1%. Those are the +200 to +900 quotes the college
    longshot board exists to find, and the model was talking itself out
    of them.

The third finding is what `fit_calibration` acts on. It is a PRIOR and
it says so: `engine.journalfit` refits `cfb:anytime_td` from
actually-settled picks once 200 of them exist, on the real chain with
the book's own numbers, and that fit replaces this one.
"""

from __future__ import annotations

import math

from .cfb.tds import (POSITION_TD_SHARE, POSITION_TYPICAL_SHARE,
                      CFB_AVG_TEAM_OFF_TDS, role_of)
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
MARKETS = ("anytime_td", "carries", "receptions", "rush_yds", "rec_yds")

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
BLEND_WEIGHTS = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)

#: What the college board carried BEFORE this fit — a guess, copied
#: across from the NFL model's own pre-measurement guess. Frozen here so
#: `fit_blend` can always report what the change bought, rather than
#: comparing the fitted setting with itself the moment it is installed.
PREVIOUS_BLEND = (10.0, 0.70)

#: MEASURED, AND THE ANSWER WAS NOT WORTH A TERM.
#: `engine.sources.cfbstats` ingests red-zone carries, inside-the-five
#: carries and red-zone receptions, and the working assumption was that
#: college's yardage-share proxy — which `engine.cfb.tds` caps hard
#: precisely because it overstates concentration — would fall to them
#: the way the NFL model leans on red-zone role. Held out over 2024-25,
#: single-feature logistic on the prior six games:
#:
#:     yardage share      log loss 0.55812     <- what the model uses
#:     touch share                 0.56290
#:     red-zone share              0.56711
#:     own TD rate                 0.56183
#:     yardage + red-zone          0.55531
#:
#: So red-zone role does carry information the yardage share does not —
#: in a logistic that is free to re-weight it. Inside the model's OWN
#: multiplicative share term, where a share is divided by its position's
#: typical share and clamped to [0.15, 1.8], blending red zone in at the
#: weight the training grid picked (0.1) moved held-out Brier from
#: 0.18446 to 0.18435. One ten-thousandth is not a term. The college
#: model keeps the share it had, the blend and the position anchors are
#: fitted instead, and the red-zone markets stay ingested and shown on
#: player pages rather than priced on a gain that cannot be told from
#: noise.
ROLE_FEATURES = ("yardage share", "own touchdown rate")


class Sample:
    """One graded player-game: what we knew going in, and what happened."""

    __slots__ = ("season", "period", "position", "share", "td_mean",
                 "games", "scored")

    def __init__(self, season, position, share, td_mean, games, scored,
                 period=""):
        self.season = season
        #: The kickoff date. Carried for ONE reason: `calibrate.bake_off`
        #: holds out "the later part of the sample", which is only a
        #: held-out slice if the sample is in time order. Built the
        #: obvious way — a loop over players, each walked forward — these
        #: pairs come out grouped by PLAYER, and the judge would be
        #: scoring a fitted correction on an arbitrary subset of college
        #: football rather than on its future. `run` sorts on this.
        self.period = period
        self.position = position
        self.share = share
        self.td_mean = td_mean
        self.games = games
        self.scored = scored


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
            usage = {"player": player, "carries": own["carries"],
                     "receptions": own["receptions"],
                     "rush_yds": own["rush_yds"], "rec_yds": own["rec_yds"],
                     "games": n,
                     "position": positions.get((season, team, player), "")}
            out.append(Sample(
                season=season, position=role_of(usage),
                share=clamp(volume / team_vol, 0.0, 1.0) if team_vol > 0 else 0.0,
                td_mean=own["anytime_td"], games=n, period=period,
                scored=1 if weeks[period].get("anytime_td", 0.0) > 0 else 0))
    return out


def role_share(sample: Sample) -> float:
    """The position-scaled yardage share, exactly as the board builds it."""
    position = sample.position
    base = POSITION_TD_SHARE[position] * clamp(
        sample.share / POSITION_TYPICAL_SHARE[position], 0.15, 1.8)
    return clamp(base, 0.01, 0.45)


def blended(sample: Sample, games_scale: float, max_weight: float) -> float:
    """The role share with the player's own scoring record blended in."""
    base = role_share(sample)
    if sample.games < MIN_PRIOR_GAMES:
        return base
    weight = clamp(sample.games / games_scale, 0.0, max_weight)
    history = clamp(sample.td_mean / CFB_AVG_TEAM_OFF_TDS, 0.0, 0.45)
    return clamp(weight * history + (1 - weight) * base, 0.01, 0.45)


def probability(base: float) -> float:
    """P(scores at least one), at a neutral team total and multipliers."""
    return 1.0 - math.exp(-CFB_AVG_TEAM_OFF_TDS * base)


def brier(rows: list, games_scale: float, max_weight: float,
          history: bool = True) -> float:
    if not rows:
        return 0.0
    total = 0.0
    for s in rows:
        base = blended(s, games_scale, max_weight) if history else role_share(s)
        total += (probability(base) - s.scored) ** 2
    return total / len(rows)


def fit_blend(rows: list) -> dict:
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
            score = brier(train, games_scale, max_weight)
            if best is None or score < best[0]:
                best = (score, games_scale, max_weight)
    _score, games_scale, max_weight = best
    return {
        "chosen": (games_scale, max_weight),
        "train": len(train), "test": len(test),
        "train_brier": round(best[0], 5),
        "held_out": round(brier(test, games_scale, max_weight), 5),
        "held_out_previous": round(brier(test, *PREVIOUS_BLEND), 5),
        "held_out_no_history": round(
            brier(test, games_scale, max_weight, history=False), 5),
    }


def run(conn, seasons=None, games_scale: float | None = None,
        max_weight: float | None = None) -> TDBacktest:
    """Replay the college touchdown model and grade what it claimed."""
    from .cfb.tds import TD_HISTORY_GAMES, TD_HISTORY_MAX_WEIGHT
    games_scale = TD_HISTORY_GAMES if games_scale is None else games_scale
    max_weight = (TD_HISTORY_MAX_WEIGHT if max_weight is None else max_weight)
    report = TDBacktest(label="CFB")
    rows = sorted(samples(conn, seasons=seasons),
                  key=lambda s: (s.season, s.period))
    for s in rows:
        report.add(probability(blended(s, games_scale, max_weight)), s.scored)
    return report.finish()


def fit_calibration(conn, seasons=None, path=None):
    """Fit and persist a PRIOR correction for ``cfb:anytime_td``.

    A prior, and labelled one. It is measured — 28,141 graded college
    player-games, held out by season — but measured on the role chain
    with the market's own inputs held neutral, because the mirror
    carries no historical betting lines. `engine.journalfit` refits this
    key from settled picks once 200 exist, on the real chain, and that
    fit replaces this one.

    Fitted 2026-08-27: T=1.2, bias -0.100, which lifts a modelled 8% to
    10.6% and 12% to 14.7% and leaves everything above a third alone.
    `calibrate.bake_off` adopted it over doing nothing by 0.00012 of
    held-out Brier, which is thin — but the band table it is correcting
    is not: 7.5% claimed against 13.4% landed is the college longshot
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
           "Sample", "samples", "role_share", "blended", "probability",
           "brier", "fit_blend", "run", "fit_calibration"]
