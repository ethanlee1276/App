"""League tuning for the basketball engine — one model, two leagues.

The Scalpy pipeline (minutes → distribution → clamp → gate) is not
NBA-specific. What is NBA-specific is a handful of numbers baked into it,
and shipping a WNBA page meant separating the two.

Two kinds of constant live here, and the difference matters more than any
individual value:

**Structural facts.** A WNBA game is 40 minutes, not 48; rosters are 12,
not 15; the season is 44 games, not 82. These are not opinions, and
anything denominated in minutes has to be scaled or it is simply wrong —
a vacancy cap of "8 minutes over his recent high" means something
different in a game that is a sixth shorter.

**Tuning.** MARGIN_SD, the blowout curves, the shot-distribution CVs, the
gate thresholds. Every one of these was fitted against NBA results. I have
no WNBA sample to fit them against, so WNBA inherits them — and says so.
``calibrated=False`` is not decoration: the pipeline routes an uncalibrated
league's picks into a probation bucket that grades but does not bet, on
the same promotion bar the long-shot watchlist and the Polymarket flow
model already use. A model that has never been graded against a league
does not get to bet that league on the strength of borrowed numbers.

Guessing at "WNBA-ish" values would have been worse than inheriting: it
would look tailored while being invented, and nothing downstream could
tell the difference.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class LeagueTuning:
    key: str
    name: str
    # --- structural: facts about the sport ---------------------------------
    game_minutes: int = 48
    roster_size: int = 15
    season_games: int = 82
    personal_fouls: int = 6
    # --- tuning: fitted numbers ---------------------------------------------
    margin_sd: float = 11.5
    blowout_margin: float = 18.0
    blowout_grade_drop: float = 0.25
    vacancy_cap_over_high: float = 8.0
    dog_haircut_share: float = 0.6
    blowout_starter: tuple = ((4.5, 1.00), (7.5, 0.98), (10.5, 0.95),
                              (13.5, 0.91), (float("inf"), 0.86))
    blowout_bench: tuple = ((4.5, 1.00), (7.5, 1.02), (10.5, 1.06),
                            (13.5, 1.12), (float("inf"), 1.20))
    rest_mult: dict = field(default_factory=lambda: {
        "2plus": 1.01, "1day": 1.00, "b2b_home": 0.96, "b2b_road": 0.93,
        "b2b_road_30plus": 0.88, "3in4": 0.94, "4in6_road": 0.92})
    sd_cv: dict = field(default_factory=lambda: {
        "pts": 0.30, "reb": 0.40, "ast": 0.43, "pra": 0.24,
        # The two-stat combos (2026-10-13, see COMBOS): starting values
        # only — `hoops_fit` measures every one from the league's own logs
        # at build time. Worked the way PRA's 0.24 works out: a 15-6-4 line
        # at the single-stat CVs above, parts correlated 0.2, gives PRA
        # 0.247, P+R 0.26, P+A 0.27 and R+A 0.32.
        "pts_reb": 0.26, "pts_ast": 0.27, "reb_ast": 0.32,
        "fg3m": 0.55, "stl": 0.70, "blk": 0.80,
        # Turnovers (2026-10-14, see COUNTS): a starting value, measured by
        # `hoops_fit` like the rest. A count close to Poisson, at the mean
        # of a typical line (about three, where a Poisson CV is 0.58),
        # a little overdispersed. Steals and blocks sit below their
        # Poisson CVs; the pricer never prices a count tighter than
        # Poisson (`prob.p_over_negbin`), so a low one costs nothing.
        "tov": 0.60})
    # THE SPREAD THAT FOLLOWS THE PROJECTION (2026-11-04, the NBA lab):
    # variance = a × mean^c per stat, so a 5-point bench line and a
    # 28-point star line no longer share one width (one CV per stat made
    # the star's too wide and the bench's too narrow). Measured on two
    # full seasons of the league's play-by-play, fit on 2024-25 and judged
    # on 2025-26 (15+ minute projections, lines from half the projection
    # to one and a half times it): Brier 0.8-2.1% better in every market
    # below, and the overs on lines well under a player — Most Likely's
    # bets — said within a point of how often they hit (PRA 80.3% said,
    # 80.3% happened), where the CV fitted the box's way said 3-6 points
    # under. Threes stay on their CV (no better there). Replayed through the
    # board's own pricer at the CVs `hoops_fit` fits from those seasons
    # (nbalabcheck.py): Brier on those overs lower in all seven markets, and
    # the overs it called 80% or more hit within 3 points of that in all
    # seven, where the fitted CV's 82% points overs hit 60%. Read only when
    # QB_NBA_SPREAD=1 (`prob.spread_on`): the board's stored calibration
    # curves were fit on the CV spread, so the switch goes on with a refit.
    sd_power: dict = field(default_factory=dict)
    max_picks_per_slate: int = 4
    max_picks_per_game: int = 2
    thin_sample: int = 10
    # Nested minutes windows, most recent first: last 5 · games 6-10 · the
    # rest of the season. Nested, NOT overlapping — "last 5 at 40% and last
    # 10 at 30%" reads as overlapping windows, and implementing it that way
    # would count the last five games twice at 70%.
    recency_weights: tuple = (0.50, 0.30, 0.20)
    # His projected minutes by his role (his newest game's: started or came
    # off the bench), after every haircut: 1.0 = the base as read. See the
    # NBA's measured values below.
    role_minutes_mult: dict = field(default_factory=lambda: {"starter": 1.0, "bench": 1.0})
    # THE ROTATION'S NEWS (engine/nba/minutes: `role_jump`, `back_multiplier`,
    # `return_minutes`). Off by default — every value below leaves the
    # minutes exactly as read; the NBA's measured ones are set on it.
    #   A ROLE THAT JUST JUMPED: his newest three games' minutes at least
    #   ``role_jump_ratio`` x the seven before them move his base
    #   ``role_jump_weight`` of the way to the newest three.
    role_jump_ratio: float = 0.0
    role_jump_weight: float = 0.0
    #   HIS FIRST GAME BACK: tonight's minutes x the multiplier for how many
    #   of his club's games in a row he missed before it, ((most missed,
    #   multiplier), ...) in order; and his SECOND game back after missing
    #   two or more.
    back_mult: tuple = ()
    second_back_mult: float = 1.0
    #   A REGULAR'S RETURN: the share of a returning regular's usual minutes
    #   his teammates give back, split by their own base minutes.
    return_share: float = 0.0
    #   THE STARTING FIVE'S NEWS (engine/nba/starters): minutes for each of
    #   the six terms the role he is moving to tonight reads as, before the
    #   tip. Empty leaves the minutes exactly as read.
    starter_news: dict = field(default_factory=dict)
    # --- market structure ----------------------------------------------------
    # Which markets are worth betting, and how hard each has to clear.
    # Empty tier map = this league gates on points-edge alone (the NBA's
    # original behaviour), so adding tiers to one league can't silently
    # re-tune the other.
    market_tier: dict = field(default_factory=dict)
    tier_min_edge: dict = field(default_factory=dict)
    # --- §8 the unified grade ------------------------------------------------
    grade_weights: dict = field(default_factory=dict)
    min_grade: int | None = None       # None = the grade is reported, not gating
    # Week-to-week coefficient of variation in minutes above which a role is
    # a coin flip and the projection is fiction. None = filter off.
    stability_max_cv: float | None = None
    # --- §8 bankroll caps, as fractions of bankroll --------------------------
    cap_per_play: float = 0.03
    cap_per_game: float = 0.06
    cap_per_slate: float = 0.15
    # --- provenance ---------------------------------------------------------
    calibrated: bool = True
    inherited_from: str = ""
    note: str = ""

    @property
    def probation(self) -> bool:
        """True when picks must be journaled and graded but NOT bet.

        `calibrated` below is a literal in this file, which meant the
        coverage page's "grades accumulate automatically; the bar lifts
        itself" was never true — the bar was a `False` only a human
        editing this module could flip. `engine.promotion` holds the
        recorded promotions now, so a league that has earned its way off
        probation can actually receive it, and a demotion takes effect
        the moment it is written rather than at the next deploy.

        The literal still stands as the FLOOR: a league marked
        `calibrated=True` in source is off probation regardless, because
        that is the NBA, whose numbers were fitted against its own
        results before any of this existed.
        """
        if self.calibrated:
            return False
        try:
            from .promotion import promoted
            return not promoted(self.key)
        except Exception:                                 # noqa: BLE001
            # Unreadable state withholds risk rather than taking it.
            return True


#: THE TWO-STAT COMBOS, and the columns each adds up (Ethan's call,
#: 2026-10-13, runbook H: "Also add both from my calls, the CFB and nba
#: things"). Like PRA they need no new feed: every part is a column the
#: NBA ingest already stores, so the history, the price and the grade all
#: read the same numbers. The NBA only — each one is another market on
#: every event the odds pull buys (`oddsbudget.EVENT_CREDITS`), and the
#: call was for the NBA's.
COMBOS = {"pts_reb": ("pts", "reb"), "pts_ast": ("pts", "ast"), "reb_ast": ("reb", "ast")}

#: STEALS, BLOCKS AND TURNOVERS (Ethan, 2026-10-14: "Do 1-7 and the ones
#: we download but don't use"). Both NBA ingests have stored them since
#: 2026-10-13 (`nbadata.NBA_MARKETS`, `espnhoops.STAT_MAP`), and no board
#: priced them. The NBA only, as the combos: each is another market on
#: every event the odds pull buys, and the WNBA's season is over.
COUNTS = ("stl", "blk", "tov")

#: The summed markets and their parts: PRA, and the NBA's two-stat combos.
SUMS = {"pra": ("pts", "reb", "ast"), **COMBOS}


def carried(games, stat: str) -> int:
    """How many of ``games`` — newest first, each a ``{market: value}``
    dict — lead the list carrying ``stat``.

    A MISSING ROW IS NOT A ZERO. A game ingested before 2026-10-13 has no
    steals, blocks or turnovers row at all, and reading it as a night
    with none would price every player's under at a certainty. So a count
    reads only the run of his newest games whose box stored it, and the
    run is a prefix of the same list his minutes, dates and opponents are
    read from, so the n-th value still lines up with the n-th game."""
    n = 0
    for g in games:
        if not isinstance(g, dict) or stat not in g:
            break
        n += 1
    return n

#: THE STARTING FIVE'S NEWS (engine/nba/starters, measured 2026-11-04): the
#: minutes each term adds to his projection, fitted on the lab's two seasons
#: beside a level the calibration owns (docs/NBA_LAB.md, "Who starts
#: tonight"). A man who came off the bench in his newest game:
#:   ``bench_after_starts`` x the share of his last ten he started (his base
#:   still carries a fill-in's minutes), ``bench_one_out`` when one of his
#:   club's last starting five is ruled out tonight and ``bench_two_out``
#:   more when two or more are.
#: A man who started his newest game:
#:   ``start_after_bench`` x the share of his last ten he did NOT start (a
#:   new starter plays more than a base made partly of bench games),
#:   ``start_one_back`` when a regular who started before he sat returns
#:   tonight, and ``fill_in_one_back`` x that same share on top: the fill-in
#:   is the one who goes back to the bench.
STARTER_NEWS_NBA = {"bench_after_starts": -3.83, "bench_one_out": 0.89, "bench_two_out": 1.41,
                    "start_after_bench": 1.22, "start_one_back": 0.58, "fill_in_one_back": -3.19}

NBA = LeagueTuning(
    key="nba", name="NBA",
    game_minutes=48, roster_size=15, season_games=82, personal_fouls=6,
    calibrated=True,
    # (a, c) in variance = a × mean^c, from the lab (see `sd_power`).
    sd_power={"pts": (7.318, 0.698), "reb": (1.679, 0.914), "ast": (1.508, 0.897),
              "pra": (13.328, 0.548), "pts_reb": (10.487, 0.607),
              "pts_ast": (8.548, 0.651), "reb_ast": (2.768, 0.760)},
    # THE MINUTES MODEL, MEASURED (2026-11-04, docs/NBA_LAB.md). The values
    # above in the class were a written spec's, never fitted. On two full
    # seasons through the board's own minutes code (every player-game with
    # 15+ minutes a game), fitted on 2024-25 and judged on 2025-26:
    #
    #   * REST. A man who suits up on a back-to-back or a third game in four
    #     nights plays about his usual minutes (0.99-1.03 of them), not the
    #     spec's 0.92-0.96: the board was projecting those nights 2-8% light,
    #     on a third of the schedule, which leans every pick to the under.
    #     After a long break (no game in six days) he plays about 4% fewer.
    #   * BLOWOUTS, from his minutes by his club's FINAL margin, read through
    #     the board's own margin ~ Normal(spread, 11.5): a favourite's
    #     starters lose 1% at a 6-point spread and 5% at 15, not the spec's
    #     2% and 14%; rotation bench players gain nothing (the spec gave
    #     them up to +20%). The underdog's share of the haircut measured
    #     0.58-0.70: the 0.6 stands.
    #   * THE BASE weights his newest games more: last five 0.60, games 6-10
    #     0.25, the rest 0.15 (0.50/0.30/0.20 before).
    #   * A BENCH PLAYER'S recent minutes overstate his next game's by about
    #     2%, every season (he was picked out by a good stretch): x0.98.
    #
    # Minutes error 6.404 -> 6.209 (-3.0%) on the season they never saw;
    # points -0.8%, rebounds -0.8%, assists -0.7%, PRA -1.3%. The numbers
    # here are refitted on both seasons.
    rest_mult={"2plus": 0.96, "1day": 1.00, "b2b_home": 0.99, "b2b_road": 0.99,
               "b2b_road_30plus": 0.99, "3in4": 1.01, "4in6_road": 1.00},
    blowout_starter=((4.5, 1.00), (7.5, 0.99), (10.5, 0.98), (13.5, 0.97),
                     (float("inf"), 0.95)),
    blowout_bench=((4.5, 1.00), (7.5, 1.00), (10.5, 1.00), (13.5, 1.00),
                   (float("inf"), 0.99)),
    recency_weights=(0.60, 0.25, 0.15),
    role_minutes_mult={"starter": 1.00, "bench": 0.98},
    # THE ROTATION'S NEWS, MEASURED (2026-11-04, docs/NBA_LAB.md, "The
    # scout"). Each rule's bar was written before its run: fitted on one
    # season beside a level factor (the calibration corrects the board's
    # overall level; a rule must not take credit for it), judged on the
    # other, both ways, and kept only if the squared error of minutes AND
    # points fell in the games it touches in BOTH held-out seasons:
    #
    #   * HIS FIRST GAME BACK. He plays fewer minutes than his old role
    #     reads, more so the longer he was out: 1 game missed x0.96, 2-4
    #     x0.92, 5 or more x0.84 (minutes error -1% to -35% in those
    #     games, points -0.5% to -8.6%). His second game back after two or
    #     more missed: x0.96 (-0.3% / -2.6%, points -0.4% / -0.7%), x0.97
    #     since the starting five's news (below) took over part of it: a
    #     second game back is often a role change too. nbarules.py's own
    #     measure of the haircut's points gain at 0.96 fell to +0.29% /
    #     -0.02% with the vacancy off (a failed bar by a hair); refitted
    #     beside it on a grid, 0.97 took the most off in both seasons with
    #     the vacancy on (+0.53% / +0.31%) and was within 0.07% of the best
    #     with it off (+0.35% / +0.15%).
    #   * A ROLE THAT JUST JUMPED (newest three games 20%+ above the seven
    #     before): the jump mostly holds, so the base moves 40% of the way
    #     to the newest three (minutes -7.0% / -4.8%, points -1.6% / -1.7%).
    #     A role that just DROPPED did not pass (it hurt 2024-25): no rule;
    #     the scout's card warns on overs after a drop instead
    #     (engine/nba/scout: they hit 4-5% under what we said).
    #   * A REGULAR'S RETURN (24+ minutes a game, back from missing his
    #     club's last two or more): his teammates give back a quarter of
    #     his usual minutes, by their base minutes (minutes -1.2% / -2.4%,
    #     points -1.0% / -0.5%).
    #
    # Together, on each season with the values fitted on the other:
    # minutes error 6.17 -> 6.09 and 6.20 -> 6.11 over every priced game;
    # points 0.6% closer, PRA 0.9-1.0%; Brier at a half-point line 0.2280 ->
    # 0.2272 and 0.2279 -> 0.2270.
    role_jump_ratio=1.20, role_jump_weight=0.40,
    back_mult=((1, 0.96), (4, 0.92), (float("inf"), 0.84)),
    second_back_mult=0.97,
    return_share=0.25,
    # THE STARTING FIVE'S NEWS, MEASURED (2026-11-04, docs/NBA_LAB.md, "Who
    # starts tonight"; engine/nba/starters says what each term reads). One
    # game in eleven a man does the other thing from his newest game — the
    # bench man starts, the starter comes off the bench — and those games
    # carry a sixth of the board's squared minutes error. What the board
    # knows before the tip (the injury report on his club's last starting
    # five, the returning regulars, his own starts) took, with these fitted
    # on the other season: minutes error 1.7% / 1.3% and points 0.34% /
    # 0.35% over every priced game, in both held-out seasons (3.4% / 2.3%
    # and 1.0% / 0.8% in the games it moves). Refitted on both.
    starter_news=STARTER_NEWS_NBA,
)

# 40 minutes, not 48 — so every minutes-denominated number is scaled by
# 40/48. That is arithmetic, not a guess: a cap of "8 minutes above his
# recent high" is a sixth of an NBA game and must stay a sixth of a WNBA
# one. The blowout MARGIN is left alone deliberately: it is a points
# threshold, and while WNBA teams score ~72% of an NBA team's total, I have
# no WNBA blowout sample to say whether the rotation response starts at the
# same margin. Inheriting a number and admitting it beats inventing one.
# Since 2026-11-04 the minutes numbers it inherits (rest, blowout, the bench
# correction) are the NBA's MEASURED ones, not the spec's; its recency
# weights stay its own spec's.
_MIN_SCALE = 40 / 48

# §7 — the WNBA's own beatability order, which is NOT the NBA's. Count
# stats tied tightly to minutes and role are tier 1 and PRA aggregates away
# single-category noise; points are efficiency-contaminated; made threes
# are low-frequency events where one hot night distorts every average.
WNBA_TIERS = {"reb": 1, "ast": 1, "pra": 1, "pts": 2, "fg3m": 3,
              "stl": 3, "blk": 3}
# §3.6 — minimum edge AFTER the haircut. Deliberately above the NFL/MLB
# thresholds: when a soft-market model disagrees with a soft market, the
# extra cushion is the protection against being confidently wrong together.
WNBA_TIER_MIN_EDGE = {1: 0.030, 2: 0.045, 3: 0.065}
# §8 — the unified 0-100 grade. Minutes/role certainty is 20% because
# minutes are the king input, and freshness is 15% because a stale injury
# report is how this league beats you.
WNBA_GRADE_WEIGHTS = {"edge": 40, "minutes_certainty": 20, "freshness": 15,
                      "movement": 10, "matchup": 10, "schedule": 5}

WNBA = replace(
    NBA,
    key="wnba", name="WNBA",
    game_minutes=40,
    roster_size=12,
    season_games=44,
    personal_fouls=5,
    vacancy_cap_over_high=round(NBA.vacancy_cap_over_high * _MIN_SCALE, 2),
    # MEASURED ON THE WNBA'S OWN SEASONS (2026-11-05, docs/WNBA_LAB.md):
    # six regular seasons (2021-2026) of the league's public box scores
    # replayed through the board's own projection (engine/nba/pipeline.
    # project, nbarules' rows), every one out of sample for values fitted on
    # the NBA, each on its own season-wide level (the calibration owns the
    # level). Three of the NBA's measured pieces made minutes AND points
    # better in all six seasons, each on top of the one before:
    #   * THE STARTING FIVE'S NEWS (STARTER_NEWS_NBA, in minutes as fitted;
    #     scaled to a 40-minute game it read worse in every season);
    #   * HIS FIRST GAME BACK (the NBA's table);
    #   * THE BASE READ OFF HIS NEWEST GAMES HARDER: the NBA's measured
    #     0.60/0.25/0.15 (the spec's §5 0.40/0.30/0.20 read him slow).
    # Together: minutes error 2.6-3.3% lower in every season, points
    # 0.2-0.5%. The rest stay off: a role that jumped made points worse in
    # 2026 (and in 2021 on top of the three); the second game back and a
    # regular's return went both ways season to season. The switches are
    # the NBA's (engine/nba/switches: "rotation", "starters").
    recency_weights=(0.60, 0.25, 0.15),
    role_jump_ratio=0.0, role_jump_weight=0.0, back_mult=NBA.back_mult, second_back_mult=1.0,
    return_share=0.0,
    starter_news=STARTER_NEWS_NBA,
    market_tier=WNBA_TIERS,
    tier_min_edge=WNBA_TIER_MIN_EDGE,
    grade_weights=WNBA_GRADE_WEIGHTS,
    min_grade=70,                      # "Below 70: no bet, no leans."
    stability_max_cv=0.35,
    # §8 — tighter than the NFL/MLB slate cap, because WNBA limits are lower
    # and re-betting a moved line is harder: a soft market punishes
    # over-concentration with worse fills, not just variance.
    cap_per_play=0.02, cap_per_game=0.05, cap_per_slate=0.12,
    calibrated=False,
    # THE SPREAD THAT FOLLOWS THE PROJECTION, MEASURED ON THE WNBA'S OWN
    # SEASONS (2026-11-05, docs/WNBA_LAB.md). Every regular-season
    # player-game 2021-2026 (wehoop box scores, 122,600 stat-games) through
    # the board's own projection at this tuning; variance around it by
    # decile of the projection, fitted on one season and judged on the next,
    # against the CV the box's own fit sets (`hoops_fit`'s rule on the same
    # season). On over lines at 0.5 to 1.5 of his projection the Brier was
    # lower in every one of the five judged seasons in all seven markets
    # below: points 1.1-1.9%, rebounds 0.5-1.7%, assists 1.1-2.3%, PRA
    # 1.3-2.4%, the two-stat combos 0.9-2.3%. The overs it called 80% or
    # more hit within a few points of that; the CV's few such calls on
    # points hit 69-80% in seasons it said 81%. Threes stay on their CV
    # (better in three seasons of five, worse in two), as the NBA's do.
    # The values are the fit on all six seasons. Read only when the
    # spread's switch is on (`prob.spread_on`, engine/nba/switches): the
    # NBA's verdict throws it after the NBA's refit, and the weekly refit
    # fits the WNBA after the NBA, so its calibration is refitted on this
    # spread in the same round. `nbalabcheck.py --league wnba` reads it on
    # the box's own WNBA games.
    sd_power={"pts": (5.927, 0.735), "reb": (1.407, 0.987), "ast": (1.447, 0.845),
              "pra": (8.429, 0.650), "pts_reb": (6.847, 0.711),
              "pts_ast": (6.308, 0.711), "reb_ast": (2.114, 0.833)},
    inherited_from="nba",
    note=("Market tiers, tier minimums, the 0-100 grade, the role-stability "
          "filter and the bankroll caps are the WNBA spec's own. What is "
          "still inherited from the NBA are the fitted numbers — margin SD, "
          "blowout curves, stat spreads — which are not yet fitted to WNBA "
          "results. Picks are journaled and graded on probation; they do "
          "not count as bets until the bucket clears the promotion bar."),
)

# MEN'S COLLEGE BASKETBALL (2026-11-13, Ethan: "we need to add college
# basketball ... look at all the tools and resources and data points we use
# for NBA, and obviously put that towards college basketball").
#
# THE STRUCTURAL FACTS are the NCAA's: two 20-minute halves (40 minutes, so
# every minutes-denominated number is scaled as the WNBA's is), five fouls
# and out, a 13-to-15-man roster, about thirty-one games before the
# conference tournaments.
#
# THE MARKET STRUCTURE is the WNBA spec's, for the WNBA spec's reason: a soft
# market with low limits, where a model that disagrees with the book needs
# the bigger cushion — counting stats tied to minutes first (rebounds,
# assists, PRA), points second, threes last; the 0-100 grade gating at 70; the
# role-stability filter; the tighter bankroll caps. The books post college
# player props on the ranked teams and the power conferences, not on every
# game (`cbbteams.priority`).
#
# THE FITTED NUMBERS start as the WNBA's (a 40-minute game measured on its own
# seasons — the nearest measured basketball), until the college lab measures
# college's own (docs/CBB_LAB.md); `hoops_fit` swaps in what the league's own
# stored results can measure at every build, as it does for the WNBA.
#
# ON PROBATION: picks are journaled and graded, not staked, until the league's
# own record clears the promotion bar (`engine.promotion`) — the rule the
# WNBA and the NHL came in under.
CBB = replace(
    WNBA,
    key="cbb", name="NCAAB",
    game_minutes=40,
    roster_size=15,
    season_games=31,
    personal_fouls=5,
    calibrated=False,
    inherited_from="wnba",
    note=("College basketball runs the NBA's engine on a 40-minute game: the "
          "minutes model, the shooting and rate reads, the matchup scan and "
          "the market's own price. Its fitted numbers start from the WNBA's "
          "(the nearest 40-minute game measured on its own seasons) until "
          "college's own seasons measure them. Picks are journaled and graded "
          "on probation; they do not count as bets until the league's record "
          "clears the promotion bar."),
)

LEAGUES = {"nba": NBA, "wnba": WNBA, "cbb": CBB}


def for_league(key: str) -> LeagueTuning:
    return LEAGUES.get((key or "nba").lower(), NBA)
