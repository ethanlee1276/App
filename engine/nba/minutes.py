"""The minutes engine — build this first, every time.

~70% of prop outcome variance traces back to minutes played, so minutes
are modeled explicitly before any stat projection:

    ProjMIN = BaseMIN × M_blowout × M_rest (+ vacancy), capped

* BaseMIN weights the current role only: last 5 games ×0.50, games 6-10
  ×0.30, games 11-20 ×0.20.
* M_blowout is ASYMMETRIC: the favorite's starters lose more minutes than
  the dog's, because trailing teams keep starters in chasing the game —
  the underdog takes ~60% of the haircut.
* Vacancy minutes are capped: nobody projects more than +8 over their
  recent high. Coaches are more conservative than models.
* Every prop gets a Minutes Confidence Grade (A-D) that gates the stake:
  A full, B 0.75×, C 0.5×, D = no bet.

Blowout probability comes from the spread with margin ~ Normal(spread,
11.5) — a 12-point favorite blows the doors off ~30% of the time, and any
prop in a game with P(blowout) > 25% drops one full grade.
"""

from __future__ import annotations

import math

from ..hoops import NBA, LeagueTuning

BLOWOUT_STARTER = ((4.5, 1.00), (7.5, 0.98), (10.5, 0.95),
                   (13.5, 0.91), (float("inf"), 0.86))
BLOWOUT_BENCH = ((4.5, 1.00), (7.5, 1.02), (10.5, 1.06),
                 (13.5, 1.12), (float("inf"), 1.20))
DOG_HAIRCUT_SHARE = 0.6            # the dog takes ~60% of the starter haircut

REST_MULT = {"2plus": 1.01, "1day": 1.00, "b2b_home": 0.96,
             "b2b_road": 0.93, "b2b_road_30plus": 0.88,
             "3in4": 0.94, "4in6_road": 0.92}

VACANCY_CAP_OVER_HIGH = 8.0
MARGIN_SD = 11.5
BLOWOUT_MARGIN = 18.0
BLOWOUT_GRADE_DROP = 0.25          # P(blowout) above this drops one grade

GRADE_STAKE = {"A": 1.0, "B": 0.75, "C": 0.5, "D": 0.0}

#: HOW FAR A CLUB'S SPREADS RUN ABOUT ITS RESULTS, in points (2026-10-29;
#: see `context_norms`). Home and away alone swing a line about six points,
#: and the opponent moves it more; a starting value, not a fit.
SPREAD_SD = 6.0


def _recency(values: list, tune: LeagueTuning = NBA) -> float | None:
    """The nested-window weighted mean of a series aligned with his games,
    newest first: last 5, games 6-10, games 11-20, at `recency_weights`."""
    vals = list(values)[:20]
    w5, w10, w20 = (tune.recency_weights + (0.0, 0.0, 0.0))[:3]
    num = den = 0.0
    for chunk, w in ((vals[:5], w5), (vals[5:10], w10), (vals[10:20], w20)):
        if chunk and w:
            num += w * (sum(chunk) / len(chunk))
            den += w
    return num / den if den else None


def base_minutes(recent_minutes: list[float],
                 tune: LeagueTuning = NBA) -> float | None:
    """Weighted current-role minutes, most recent first. The caller feeds
    `role_minutes` — his minutes with an OLD early exit left out (below).

    The windows are NESTED — last 5, then games 6-10, then the rest. A spec
    that says "last 5 at 40% and last 10 at 30%" is describing overlapping
    windows, and weighting them literally would count the five most recent
    games twice, at 70%, which is not what anybody means by it.
    """
    if len(recent_minutes) < 3:
        return None
    mean = _recency(recent_minutes, tune)
    return round(mean, 2) if mean is not None else None


#: A GAME HE LEFT EARLY — under half of his usual minutes, for a player
#: whose usual is at least this. This docstring promised since the file
#: was written that "early-exit/blowout games" were excluded, and nothing
#: excluded them. MEASURED 2026-09-23 (engine/exitfit.py, 2022-2025 WNBA
#: and NBA box scores, the minutes base as built) before any was:
#:
#:     the next game's minutes     share ABOVE the base   mean miss
#:     WNBA  only older exits (n 2334)  kept .562  left out .494   +0.62 / -0.43
#:     NBA   only older exits (n 15646) kept .553  left out .493   +0.67 / -0.30
#:     WNBA  an exit in the last five  kept .456  left out .338   -1.09 / -3.52
#:     NBA   an exit in the last five  kept .491  left out .360   -0.23 / -3.07
#:
#: every season the same way. A RECENT early exit is information — he is
#: still limited — and stays, with every older one beside it; older exits,
#: when the last five are clean, only drag the base down and go.
EXIT_ROLE_MINUTES = 15.0


def role_minutes(minutes: list[float]) -> tuple[list[float], list[int]]:
    """``(minutes his role is read from, indexes left out)``, newest first."""
    from ..exitfit import keep_rule
    mins = [float(m) for m in (minutes or [])]
    keep = keep_rule(mins, EXIT_ROLE_MINUTES, "old")
    return [mins[i] for i in keep], [i for i in range(len(mins)) if i not in keep]


def blowout_mult(spread: float, is_starter: bool, is_favorite: bool,
                 tune: LeagueTuning = NBA) -> float:
    """Spread-driven minutes multiplier, asymmetric by side."""
    size = abs(spread)
    table = tune.blowout_starter if is_starter else tune.blowout_bench
    for cap, mult in table:
        if size <= cap:
            full = mult
            break
    if is_favorite:
        return full
    return round(1.0 + (full - 1.0) * tune.dog_haircut_share, 4)


def blowout_prob(spread: float, sd: float | None = None,
                 tune: LeagueTuning = NBA) -> float:
    """P(final margin ≥ blowout) with margin ~ Normal(|spread|, sd)."""
    sd = tune.margin_sd if sd is None else sd
    z = (tune.blowout_margin - abs(spread)) / sd
    return round(1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2))), 4)


def expected_blowout(margin_mean: float, is_starter: bool,
                     tune: LeagueTuning = NBA) -> float:
    """The blowout multiplier his club's games carried on average: their
    spreads ~ Normal(``margin_mean``, SPREAD_SD), each taken through
    `blowout_mult`, a favourite when the spread is his club's way."""
    n = 41
    total = weight = 0.0
    for i in range(n):
        z = -4.0 + 8.0 * i / (n - 1)
        w = math.exp(-0.5 * z * z)
        s = margin_mean + z * SPREAD_SD
        total += w * blowout_mult(s, is_starter, s > 0, tune)
        weight += w
    return total / weight


def context_norms(margins, rests, kept, is_starter: bool,
                  tune: LeagueTuning = NBA) -> tuple[float, float]:
    """``(blowout norm, rest norm)``: the minutes multipliers the games his
    base is read from carried, on the base's own weights.

    THE BASE ALREADY HOLDS THEM (Ethan, 2026-10-29: "almost ever nba most
    likely bet is an under bet so that seems wrong"). His minutes base is a
    weighted average of his recent games, and those games had their own
    spreads and their own back-to-backs; tonight's haircut was then laid on
    top of an average that had taken it already, and only ever downward:
    every blowout step is 1.00 or less, every rest step but one too. A good
    club's starters, favoured most nights, read about 7% light; an even
    club's about 2%; and on a board ranked by our chance at a number near
    −250, a few percent off the mean is the four points that seat the under
    every time. Divided by what his own games carried, the haircut keeps
    its shape (a bigger spread than usual still costs minutes, a rested
    night still adds) and averages one, so the projection averages his
    base — the level the replay the board is calibrated on reads it at.

    ``margins`` and ``rests`` are aligned with his minutes, newest first: his
    club's final margin in each game (positive when it won), and that
    game's rest category (`nba_build.schedule_density`'s names). ``kept`` is
    the indexes `role_minutes` kept. Either norm is 1.0 when fewer than
    three of the kept games carry its context (a replay, an old database),
    which is exactly the multiplier the board used before.
    """
    margins, rests = list(margins or []), list(rests or [])
    known_m = [float(margins[i]) for i in kept if i < len(margins) and margins[i] is not None]
    known_r = [tune.rest_mult.get(rests[i], 1.0) for i in kept if i < len(rests) and rests[i]]
    b_norm = r_norm = 1.0
    if len(known_m) >= 3:
        b_norm = expected_blowout(_recency(known_m, tune), is_starter, tune)
    if len(known_r) >= 3:
        r_norm = _recency(known_r, tune) or 1.0
    return round(b_norm, 4), round(r_norm, 4)


def project_minutes(base: float, spread: float, is_starter: bool,
                    is_favorite: bool, rest: str = "1day",
                    vacancy_minutes: float = 0.0,
                    recent_high: float | None = None,
                    tune: LeagueTuning = NBA,
                    blowout_norm: float = 1.0, rest_norm: float = 1.0) -> float:
    """Tonight's minutes: the base, tonight's blowout and rest multipliers
    each divided by what the base's own games carried (`context_norms`),
    and any vacancy minutes."""
    proj = base * blowout_mult(spread, is_starter, is_favorite, tune) / (blowout_norm or 1.0) \
        * tune.rest_mult.get(rest, 1.0) / (rest_norm or 1.0) + vacancy_minutes
    if recent_high is not None:
        proj = min(proj, recent_high + tune.vacancy_cap_over_high)
    # Nobody plays more minutes than the game has. Obvious, and the reason
    # it matters: the NBA cap applied to a 40-minute game would have let a
    # projection sail past regulation without anything objecting.
    return round(min(proj, float(tune.game_minutes)), 1)


def minutes_grade(is_starter: bool, spread: float, sample_games: int,
                  restriction: bool = False,
                  role_uncertain: bool = False,
                  tune: LeagueTuning = NBA) -> str:
    """A-D confidence grade. D means no bet, full stop."""
    if restriction:
        return "D"
    if not is_starter and sample_games < 10:
        return "D"
    grade = "A" if (is_starter and sample_games >= 3) else "B"
    if role_uncertain:
        grade = "C" if grade == "B" else "B"
    if blowout_prob(spread, tune=tune) > tune.blowout_grade_drop:
        grade = {"A": "B", "B": "C", "C": "D"}.get(grade, "D")
    return grade
