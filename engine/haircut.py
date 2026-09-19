#!/usr/bin/env python3
"""How much of the model's claimed edge actually survives? Measured.

    python3 -m engine.haircut --sport cfb
    python3 -m engine.haircut --sport nfl

THE NUMBER THIS ANSWERS IS A GUESS EVERYWHERE ELSE. `cfb.model.HAIRCUT`
shrinks every raw edge before it is compared to the bet bar — 50% for a
marquee game, 35% standard, 25% low — on the reasoning that a model
disagreeing with a sharp market is mostly wrong. That reasoning is
sound and the NUMBERS were never measured. They have been the binding
constraint on the college board ever since.

MEASURED 2026-09-19 ON THE DROPLET'S OWN BOARD, which is what sent this
module: 54 priced college markets, 0 recommended. Twelve refused by the
Group-of-Five rule; the other 42 all failed the edge bar, and not
narrowly — median post-haircut edge +0.4%, best +2.8% against a 3.0%
bar, and the marquee tier needs an 8.0% RAW disagreement to clear its
own (50% haircut, then a 4.0% bar). The question "is 35% the right
number" stopped being academic.

WHAT SURVIVAL MEANS, because the ratio is easy to misread. For a set of
games the model liked:

    claimed  = mean(p_model - p_market)     what the model said it had
    landed   = win rate - mean(p_market)    what the market's own number
                                            was actually short by
    survival = landed / claimed

Survival of 1.0 means the model's disagreement was entirely real and no
haircut is warranted. Survival of 0.0 means the disagreement carried no
information and the correct haircut is 100%. The shipped 35% standard
haircut is a claim that survival is 0.65.

NEGATIVE SURVIVAL IS A REAL ANSWER and the most likely one: it means
the games the model liked did WORSE than the market priced them, so the
disagreement is not merely noise but actively wrong, and no haircut
short of refusing the bet is enough.

WHY THE RATIO IS NOT THE HEADLINE. It divides one noisy number by
another, and when `claimed` is small the quotient explodes without
meaning anything. So the bands are reported on the CLAIM, the headline
is restricted to claims big enough to be worth betting, and every
survival figure carries a bootstrap interval. A band whose interval
spans 0.0 has not measured a haircut; it has measured nothing, and says
so rather than printing a number somebody will paste into a constant.

THE WALK IS NOT A NEW ONE. `gamerank.measure_cfb` / `measure_nfl`
already replay the production ratings date by date from games strictly
before each date, and already hand every quoted game to a `keep`
callback with the model's raw home probability beside both closing
prices (`gamerank._quoted`). A second replay would be a second set of
answers to the same question — the failure this repo keeps paying for.
This reads that one.

NOT THE WHOLE BOARD. The walk covers MONEYLINES: the market where the
model has a measured ranking (cfb 0.752, nfl 0.641) and the only one
whose raw claim the walk keeps. Spreads and totals rank at a coin flip
either way, so there is no claimed edge there worth asking about.

MEASURED 2026-09-19, CFB, 2,729 quoted games:

    claims of 2% or more    claimed +12.53%   landed -0.06%
                            survival -0%  →  implied haircut 100%
                            95% on landed [-1.75%, +1.56%]  spans zero

     0%- 2%  n=  255  claimed  +0.97%  landed +5.04%   spans zero
     2%- 4%  n=  241  claimed  +2.93%  landed -0.36%   spans zero
     4%- 8%  n=  553  claimed  +6.08%  landed +0.64%   spans zero
     8%+     n= 1680  claimed +16.03%  landed -0.25%   spans zero

THE ANSWER IS THAT THE CLAIM IS WORTH NOTHING. The college model's own
pre-shrink rating disagrees with the close by twelve points of
probability on the games it likes, and that disagreement predicts
nothing: every band's landed edge is inside noise of zero, including
the 1,680 games where the model claimed sixteen points. The shipped
haircuts assume survival of 50-75%. Measured, it is 0%.

AND THE HAIRCUT IS THEREFORE NOT THE LEVER, which is the finding that
matters. `gamebets` already SHRINKS the model's claim toward the market
before the pipeline sees it — the pre-shrink number rides along as
`engine_raw_prob` and the shrunk one becomes `p_model`. On the college
board of 2026-09-19 that left post-shrink edges with a median of +0.4%
against a 3.0% bar, which is why nothing is ever bet. The tier haircut
then takes 35% of an edge that was already ~0. Tuning it up or down
moves nothing, because the real shrink is upstream and the measurement
above says that shrink is right.

TWO THINGS THIS DOES NOT CLAIM, stated so the number is not overread:

  * The side taken is the one the model likes MORE, which is a max over
    two options, so `claimed` is biased upward by construction. A model
    with no information would show exactly this shape — positive claimed,
    zero landed. That is the finding, not a flaw in it; but it means
    `claimed` is not "the model's edge", it is "the model's
    disagreement", and only `landed` is a claim about money.
  * `gamerank.measure_cfb` is a FLOOR on the production model — the
    recruiting prior blended in before week four and the FCS exclusion
    are not replayed. This measures that walk's claim, not the board's
    exactly.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, field

#: Claim sizes to report separately, as (low, high) in probability
#: points. The top band is the one that matters: those are the games
#: that would be bet if anything were.
BANDS = ((0.00, 0.02), (0.02, 0.04), (0.04, 0.08), (0.08, 1.00))

#: The headline is taken over claims at or above this, because a claim
#: smaller than the smallest bet bar in the league is not a claim the
#: board would ever act on — and including it drags a ratio around
#: without changing any decision.
HEADLINE_MIN_CLAIM = 0.02

#: Bootstrap resamples for every interval printed. By GAME, because a
#: game is the independent unit: one match contributes one row here.
RESAMPLES = 2000
SEED = 3


@dataclass
class Band:
    lo: float
    hi: float
    n: int = 0
    claimed: float = 0.0
    landed: float = 0.0
    survival: float | None = None
    ci: tuple | None = None

    @property
    def meaningless(self) -> bool:
        """Does this band's interval span "no edge at all"?"""
        return not self.ci or (self.ci[0] <= 0.0 <= self.ci[1])


@dataclass
class Haircut:
    sport: str
    games: int = 0                 # quoted, scored, non-tie, rated
    liked: int = 0                 # …where the model disagreed upward
    claimed: float | None = None
    landed: float | None = None
    survival: float | None = None
    ci: tuple | None = None
    bands: list = field(default_factory=list)
    note: str = ""


def _rows(conn, sport: str) -> list[dict]:
    """Every quoted, scored game off the production walk."""
    from . import gamerank
    out: list = []
    if sport == "nfl":
        gamerank.measure_nfl(conn, keep=out.append)
    elif sport == "cfb":
        gamerank.prepare(conn, "cfb")
        gamerank.measure_cfb(conn, keep=out.append)
    return out


def claims(rows, sport: str) -> list[tuple]:
    """``[(claimed_edge, market_prob, won)]`` on the side the model liked.

    THE SIDE IS THE MODEL'S, NOT THE FAVOURITE'S. `measure_raw_bar` next
    door takes the market's favourite, because it is asking about the
    market's number. This is asking about the MODEL's disagreement, so
    it takes whichever side the model rates above the market — which is
    exactly what `cfb.pipeline.evaluate_play` prices.

    CALIBRATED FIRST, for the same reason: the shipped haircut is
    applied to the edge AFTER `calibrate.calibrated` has corrected the
    model's claim, so measuring the raw claim would be measuring a
    number the board never uses.
    """
    from .calibrate import calibrated
    from .odds import devig_two_way
    out = []
    for g in rows:
        try:
            fh, fa = devig_two_way(int(g["home_ml"]), int(g["away_ml"]))
            ph = float(calibrated(sport, "moneyline", float(g["raw_home"])))
        except Exception:                                     # noqa: BLE001
            continue
        pa = 1.0 - ph
        if ph - fh >= pa - fa:
            claim, mkt, won = ph - fh, fh, bool(g["home_won"])
        else:
            claim, mkt, won = pa - fa, fa, not bool(g["home_won"])
        out.append((float(claim), float(mkt), bool(won)))
    return out


def _survival(sample) -> tuple[float, float, float | None]:
    """``(claimed, landed, survival)`` for one set of rows."""
    if not sample:
        return 0.0, 0.0, None
    n = len(sample)
    claimed = sum(c for c, _m, _w in sample) / n
    landed = sum(1 for _c, _m, w in sample if w) / n - \
        sum(m for _c, m, _w in sample) / n
    return claimed, landed, (landed / claimed if claimed > 1e-9 else None)


def _ci(sample, rng) -> tuple | None:
    """95% bootstrap interval on the LANDED edge.

    ON LANDED, NOT ON THE RATIO. A ratio whose denominator is itself
    resampled produces intervals that are wide, skewed and hard to read,
    and the decision this informs is "did the model's disagreement land
    anything at all" — which is a question about the numerator. The
    survival figure is then honest about resting on it: a landed
    interval spanning zero means no haircut has been measured.
    """
    if len(sample) < 30:
        return None
    vals = []
    for _ in range(RESAMPLES):
        pick = [sample[rng.randrange(len(sample))] for _ in range(len(sample))]
        _c, landed, _s = _survival(pick)
        vals.append(landed)
    vals.sort()
    return (vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals))])


def measure(conn, sport: str = "cfb") -> Haircut:
    """Walk the sport's history and report what its claimed edge landed."""
    r = Haircut(sport=sport)
    if sport not in ("cfb", "nfl"):
        r.note = "only the football walks keep the model's raw claim"
        return r
    rows = _rows(conn, sport)
    r.games = len(rows)
    sample = [t for t in claims(rows, sport) if t[0] > 0]
    r.liked = len(sample)
    if not sample:
        r.note = "the walk produced no game the model rated above the close"
        return r
    rng = random.Random(SEED)
    head = [t for t in sample if t[0] >= HEADLINE_MIN_CLAIM]
    r.claimed, r.landed, r.survival = _survival(head)
    r.ci = _ci(head, rng)
    for lo, hi in BANDS:
        b = Band(lo=lo, hi=hi)
        part = [t for t in sample if lo <= t[0] < hi]
        b.n = len(part)
        b.claimed, b.landed, b.survival = _survival(part)
        b.ci = _ci(part, rng)
        r.bands.append(b)
    return r


def lines(r: Haircut) -> list[str]:
    """The report, in the vocabulary `gamerank.raw_bar_lines` uses."""
    pc = lambda v: "   —  " if v is None else f"{v:+6.2%}"     # noqa: E731
    out = [f"edge survival · {r.sport.upper()} moneylines · "
           f"{r.games:,} quoted games"]
    if r.note:
        out.append(f"  {r.note}")
        return out
    out.append(f"  the model rated above the close in {r.liked:,} of them")
    out.append("")
    out.append(f"  HEADLINE, claims of {HEADLINE_MIN_CLAIM:.0%} or more "
               f"(the only ones the board would act on):")
    out.append(f"    claimed {pc(r.claimed)}   landed {pc(r.landed)}")
    if r.survival is None:
        out.append("    survival: no claim to divide by")
    else:
        out.append(f"    survival {r.survival:+.0%}  "
                   f"→ the haircut this implies is {1 - r.survival:.0%}")
    if r.ci:
        out.append(f"    95% on landed: [{r.ci[0]:+.2%}, {r.ci[1]:+.2%}]"
                   + ("   ← SPANS ZERO: no edge measured here"
                      if r.ci[0] <= 0 <= r.ci[1] else ""))
    out.append("")
    out.append("  by size of the claim:")
    for b in r.bands:
        tail = ""
        if b.n < 30:
            tail = "  (too few to bootstrap)"
        elif b.meaningless:
            tail = "  ← spans zero"
        surv = "   —  " if b.survival is None else f"{b.survival:+6.0%}"
        out.append(f"    {b.lo:.0%}-{min(b.hi, 1.0):.0%}  n={b.n:5d}  "
                   f"claimed {pc(b.claimed)}  landed {pc(b.landed)}  "
                   f"survival {surv}{tail}")
    out.append("")
    out.append("  SHIPPED HAIRCUTS, for comparison — each is a claim that")
    out.append("  survival equals one minus it:")
    from .cfb.model import HAIRCUT
    for tier, cut in sorted(HAIRCUT.items(), key=lambda kv: -kv[1]):
        out.append(f"    {tier:9s} {cut:.0%} haircut  ⇒ assumes survival "
                   f"{1 - cut:.0%}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sport", default="cfb", choices=("cfb", "nfl"))
    ap.add_argument("--db", default=None, help="path to history.db")
    a = ap.parse_args()
    from . import db as _db
    conn = _db.connect(a.db) if a.db else _db.connect()
    try:
        for ln in lines(measure(conn, a.sport)):
            print(ln)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
