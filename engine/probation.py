"""Journaled and graded, never staked — enforced, not just announced.

Four places in this codebase promise it in almost the same words:

    engine/cfb/ratings.py   "puts the whole CFB board on probation:
                             journaled and graded, never staked"
    engine/hoops.py         "True when picks must be journaled and graded
                             but NOT bet"
    engine/coverage.py      "on probation — journaled and graded, not staked"
    web/js/app.js           "is on probation — graded, not bet"

Measured 2026-08-27: NOTHING READ THE FLAG. `engine.cfb.pipeline
.evaluate_play` runs Kelly and writes `stake_fraction` without ever
consulting it, so an uncalibrated CFB board graded a play A+ and sized
it at 2% of bankroll while the page above it displayed the banner saying
it was not being bet. The flag was a label in four files and an
enforcement in none.

That is the same failure as a fabricated number, wearing the opposite
costume: instead of showing something that is not real, it does
something it says it is not doing. A reader who trusts the banner is
being told the wrong thing about their own money.

WHAT PROBATION IS FOR. It is not "this pick is bad" — a probation board
still grades, still ranks, still publishes, and its record is still kept.
It is "we have not yet measured the thing that decides how much to bet."
Two different measurements can be missing:

  * the VARIANCE — how far from our number games actually land. Without
    it every stake is Kelly on a made-up spread. This is the one
    `CFBRatings.fitted` tracks.
  * the MARKET HAIRCUT — how much of a disagreement with the closing
    number has ever held up. `engine.gamecal` measures it; on the one
    sport where it has been checked, the standing guess was roughly
    sixteen times too generous.

ONLY THE FIRST BLOCKS A STAKE, and the split is deliberate. An unfitted
variance means the stake is Kelly on a number nobody measured — there is
no defensible size, so the size is zero and the number it WOULD have
been rides alongside, the same shape the conditional plays already use
(`stake_if_confirmed`) and for the same reason: the card can say what
the measurement is worth without pretending it is a bet.

An unmeasured haircut is a different and weaker claim. It says the size
rests on a guess, not that the guess is wrong — and the evidence that it
is too generous comes from ONE sport. `engine.gamebets._sd` refuses to
price a league through another league's variance, and silencing a league
on another league's fit would be that same borrowing with the sign
flipped. So it is an ADVISORY: it goes on the board and into the health
check, where a reader can see the size rests on something unmeasured,
and it lifts itself the moment that sport's own closes have accrued.

Standard library only.
"""

from __future__ import annotations

#: What the card carries instead of a stake while a board is unstaked.
CARRY_KEY = "stake_if_measured"

#: Set on every gated card so a renderer, the journal and the exports can
#: all tell an unstaked play from one that was merely sized small.
FLAG_KEY = "on_probation"
WHY_KEY = "probation_reasons"


def variance_reason(fitted, games=0) -> str | None:
    """Why an unfitted variance blocks a stake, or None when it is fitted."""
    if fitted:
        return None
    n = int(games or 0)
    return (f"the spread of results is a prior, not a fit — {n} graded "
            f"game(s) in this database, so any stake would be Kelly on a "
            f"number nobody measured")


def haircut_reason(sport: str, market: str = "spread") -> str | None:
    """Why this sport's haircut is still a guess, or None once measured.

    An ADVISORY, not a block — see the module docstring for the split.

    Never raises and never borrows: a sport with no fit of its own gets
    the reason, not another league's number. `engine.gamebets._sd`
    refuses to price one sport through another's variance for exactly
    this reason, and a haircut is the same kind of claim.
    """
    if not sport:
        return None
    try:
        from .gamecal import measured
        if measured(sport, market) is not None:
            return None
    except Exception:                                     # noqa: BLE001
        # A broken fitter costs the advisory, never the board. Saying
        # nothing is the safe direction here precisely because this does
        # not gate a stake: the alternative would be a warning on every
        # card the moment an unrelated module raised.
        return None
    return (f"how much of a disagreement with the closing number holds up "
            f"has never been measured for {sport} — the standing figure is "
            f"a guess, and on the one sport where it was checked it was "
            f"far too generous")


def reasons(fitted=True, games=0) -> list[str]:
    """Every reason this board must NOT STAKE. Empty means stake away.

    Blocking reasons only — see the module docstring for why an
    unmeasured haircut is an advisory rather than one of these.
    """
    v = variance_reason(fitted, games)
    return [v] if v else []


def advisories(sport: str = "", markets=("spread", "total")) -> list[str]:
    """Things a reader should know that do not block a stake.

    ONE line for the board, not one per market: "spread and total and
    moneyline are each unmeasured" is the same sentence three times.
    """
    if not sport:
        return []
    unmeasured = [m for m in markets if haircut_reason(sport, m)]
    if len(unmeasured) < len(markets):
        return []                  # at least one market has a real fit
    line = haircut_reason(sport, markets[0])
    return [line] if line else []


def unstake(cards: list[dict], why: list[str],
            stake_keys=("stake_fraction",)) -> list[dict]:
    """Zero every stake, carrying what each would have been.

    ``stake_keys`` takes ALL of a card's size fields in one pass — some
    boards carry both a bankroll fraction and a unit count, and zeroing
    them in two calls would have the second overwrite the first's record
    of what the size would have been. The carried values land under
    ``stake_if_measured`` keyed the same way: ``stake_fraction`` becomes
    ``stake_if_measured``, and any other key ``stake_if_measured_<key>``.

    Returns the cards unchanged when there is nothing to enforce, so a
    calibrated board pays nothing for this living on its path.
    """
    if not why:
        return cards
    if isinstance(stake_keys, str):
        stake_keys = (stake_keys,)
    out = []
    for card in cards:
        gated = {**card, FLAG_KEY: True, WHY_KEY: list(why)}
        for key in stake_keys:
            staked = float(card.get(key) or 0.0)
            gated[key] = 0.0
            # Only carry a number when there was one. A card that was
            # never sized must not sprout a "would have been 0.0".
            if staked > 0:
                carry = (CARRY_KEY if key == "stake_fraction"
                         else f"{CARRY_KEY}_{key}")
                gated[carry] = staked
        out.append(gated)
    return out


def note(why: list[str]) -> str:
    """One line for the board explaining the stake gate, or ``""``."""
    if not why:
        return ""
    return ("Graded and journaled, not staked: " + "; ".join(why)
            + ". The record still counts — only the size is withheld, and "
              "it returns on its own the moment the measurement exists.")


def advisory_note(lines: list[str]) -> str:
    """One line for the board about what the size rests on, or ``""``."""
    if not lines:
        return ""
    return ("Sized on an unmeasured haircut: " + "; ".join(lines)
            + ". These plays are staked; the number behind the size is the "
              "standing estimate until this sport's own closing lines have "
              "accrued.")
