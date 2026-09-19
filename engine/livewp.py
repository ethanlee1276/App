"""Live win probability from the score, the clock and the pregame line.

docs/IDEAS.md filed this under "ideas that need data we do not have" on
2026-08-20: *"In-game live win probability. Needs play-by-play at a
latency we do not have."* That was true when it was written and stopped
being true three weeks later — #136 put fast live scores on NFL, CFB,
NBA and WNBA, #137 put MLB play-by-play on the same clock, #138 landed
football drives and basketball plays off verified ESPN shapes. The
blocker was retired by other work and the entry outlived it.

WHAT THIS IS, SAID PLAINLY, because the name oversells it everywhere
else it appears. This is a MARGIN model on a clock:

    remaining margin change ~ Normal(mu, sd)
        mu = the pregame expected home margin × the fraction of the game
             still to play — a team favoured by 6 is expected to earn
             that six evenly, so with a quarter left it is owed 1.5
        sd = the sport's final-margin SD × sqrt(fraction left) — variance
             accumulates linearly in time, so its square root does
    P(home wins) = Φ((margin now + mu) / sd)

The SD is `gamebets.MARGIN_SD`, the same number the pregame moneyline is
priced from. That is the point: this is the game model looking at the
same distribution from later in the evening, not a second opinion with
its own constants to drift.

WHAT IT CANNOT SEE, and the reason every row says so. It has no
possession, no down, no distance, no timeouts. Three points up with the
ball and forty seconds left is a win; three points up having just
punted is a coin flip; this model prints the same number for both. That
error is negligible in the first three quarters and dominates at the
very end, so `possession_blind` marks the window where a reader should
not trust the last digit — the site does not get to print a number this
confident without saying where it goes wrong.

NOT A PRICE. Nothing bets off this and nothing journals it. It is a
reading of a game in progress for the page that is already showing the
plays, and the moment it becomes an input to a stake it needs the
measurement against real in-game closes that it has never had. See
docs/THE_INFORMATION_TEST.md — the same bar every other new input met.
"""

from __future__ import annotations

from .gamebets import MARGIN_SD, _sd
from .statmath import normal_cdf

#: Regulation length in seconds, per sport. A game that runs past this
#: (overtime) is handled by the clock hitting zero, not by extending it:
#: overtime is a fresh coin flip the margin model has no claim on.
#:
#: THE CLOCK IS NOT THE PERMISSION. Basketball is listed because 2880
#: seconds is simply true, and it is still refused: `gamebets.MARGIN_SD`
#: has a measured final-margin SD for football and baseball and none for
#: the hoops boards, and `_sd` raises rather than borrow another
#: league's variance. That refusal is the right one and this module does
#: not route around it — a live panel is not a licence to invent a
#: number the pregame model would not print. Measure the SD and NBA
#: turns on with no change here.
REGULATION_S = {"nfl": 3600, "cfb": 3600, "nba": 2880, "wnba": 2400}

#: Inside this many seconds, with the margin inside one score, possession
#: decides more than anything this model can see. Not a refusal — the
#: number is still the best available and an absent panel helps nobody —
#: but the row says so and the page can caveat it.
#:
#: Five minutes and one score is deliberately generous. The failure is
#: not gradual: it arrives the moment the trailing team's only path is
#: "get the ball back", which is a possession fact, not a margin one.
BLIND_S = 300
BLIND_MARGIN = {"nfl": 8, "cfb": 8, "nba": 6, "wnba": 6}


#: How many periods a regulation game has, and how long each runs.
#: Derived from REGULATION_S rather than repeated, so the two cannot
#: disagree about how long a game is.
PERIODS = {"nfl": 4, "cfb": 4, "nba": 4, "wnba": 4}


def seconds_left(sport: str, period, clock) -> float | None:
    """Seconds left in REGULATION, from a period number and a game clock.

    Returns None when the answer is not a number this model can use, and
    that is a real answer rather than a failure:

      * OVERTIME. Past regulation the margin model has no claim at all —
        overtime is a fresh coin flip with its own rules, and pretending
        the clock ran to zero would print a certainty on a tied game.
      * A clock the feed did not give, or gave in a shape we have not
        verified. Guessing "0:00" from an empty string would turn every
        pre-game card into a final.

    The caller shows nothing rather than something wrong. `livescores`
    hands this straight through from ESPN, so the shapes are theirs.
    """
    key = str(sport or "").lower()
    periods = PERIODS.get(key)
    total = REGULATION_S.get(key)
    if not periods or not total:
        return None
    try:
        per = int(period)
    except (TypeError, ValueError):
        return None
    if per < 1 or per > periods:
        return None                    # pre-game, or overtime — see above
    per_len = total / periods
    text = str(clock or "").strip()
    if not text:
        return None
    try:
        if ":" in text:
            mins, _, secs = text.partition(":")
            left_in_period = int(mins or 0) * 60 + float(secs or 0)
        else:
            left_in_period = float(text)
    except ValueError:
        return None
    if left_in_period < 0 or left_in_period > per_len:
        return None                    # not a clock for this sport
    return left_in_period + (periods - per) * per_len


def win_prob(sport: str, margin: float, seconds_left: float,
             pregame_margin: float = 0.0,
             regulation_s: float | None = None) -> float:
    """P(home team wins), from the home margin now and the clock.

    `margin` is the HOME team's current lead in points (negative when
    trailing). `pregame_margin` is how many points the home side was
    expected to win by before kickoff — positive for a home favourite.
    Callers convert their own spread sign; this function will not guess,
    because a sign convention read wrong is a probability printed
    backwards and it looks entirely plausible.
    """
    total = float(regulation_s if regulation_s is not None
                  else REGULATION_S.get(str(sport or "").lower(), 3600))
    left = max(0.0, min(float(seconds_left), total))
    if total <= 0 or left <= 0:
        # FINAL. No distribution left to integrate: the margin IS the
        # result. A tie at zero is not a 50/50 guess about the game — it
        # is a game going to overtime, which this model does not price,
        # and 0.5 is the honest statement of that rather than a claim.
        return 1.0 if margin > 0 else (0.0 if margin < 0 else 0.5)
    frac = left / total
    sd = _sd(MARGIN_SD, str(sport or "").lower(), "margin SD") * (frac ** 0.5)
    if sd <= 0:
        return 1.0 if margin > 0 else (0.0 if margin < 0 else 0.5)
    expected = float(margin) + float(pregame_margin) * frac
    # NOT clamped to the pricing floors. `gamebets` holds its win
    # probabilities inside [0.01, 0.99] because a price built on a
    # certainty is a price that cannot be wrong and that is never true
    # before kickoff. Late in a blowout it IS true, and printing 99% on
    # a four-score lead with a minute left would be the model refusing to
    # read a scoreboard.
    return max(0.001, min(0.999, normal_cdf(expected / sd)))


def possession_blind(sport: str, margin: float, seconds_left: float) -> bool:
    """Is the game inside the window this model demonstrably misreads?"""
    one_score = BLIND_MARGIN.get(str(sport or "").lower(), 8)
    return bool(seconds_left is not None
                and 0 < float(seconds_left) <= BLIND_S
                and abs(float(margin)) <= one_score)


def reading(sport: str, home: str, away: str, margin: float,
            seconds_left: float, pregame_margin: float = 0.0,
            regulation_s: float | None = None) -> dict:
    """The whole row a page needs: both sides, the basis, the caveat.

    BOTH SIDES, because a panel that prints only the favourite makes the
    reader do the subtraction and gets it wrong on a pick'em. And the
    basis in words, because "win probability" on a sports site is assumed
    to mean a fitted play-by-play model and this one is not that.
    """
    p = win_prob(sport, margin, seconds_left, pregame_margin, regulation_s)
    blind = possession_blind(sport, margin, seconds_left)
    return {
        "home": home, "away": away,
        "home_win_prob": round(p, 4),
        "away_win_prob": round(1.0 - p, 4),
        "leader": home if p >= 0.5 else away,
        "margin": round(float(margin), 1),
        "seconds_left": None if seconds_left is None else int(seconds_left),
        "basis": "score and clock against the pregame line",
        "possession_blind": blind,
        "caveat": ("Inside the last five minutes of a one-score game this "
                   "reads the scoreboard but not the ball — possession "
                   "decides more here than the margin does."
                   if blind else ""),
    }
