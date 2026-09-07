"""The coherence triangle — the market-sum method where the identities are exact.

The UFC handicapping script (§0, §2): every market on a fight describes
the same event, so the menu must obey arithmetic — a fighter's win
probability IS the sum of her ways of winning, the distance probability
IS the sum of the decision shares, the ITD probability IS the sum of
the round hazards. Books post the families separately, hold them
differently, and routinely leave the set incoherent. "The coherence
triangle is this sport's market-sum method, and it is the strongest
version of that technique in any of your five sports, because here the
identities are exact."

THE MONEYLINE IS THE TRUTH. It takes the most handle and the most
respect, so when the identities break, the derivative market is the
error — the same rule that made the team total outrank the props in
all four team sports. Two consequences implemented here:

  * a method family's raw implied sum against the devigged moneyline
    IS that family's hold, and dividing through it recovers the book's
    true projection of each method — the number a model must beat;
  * a method bet is a HOW purchased on a WHO — and only worth buying
    when the sharp moneyline already endorses the who. A method pick on
    a fighter the devigged moneyline prices well below our number is a
    WHO disagreement wearing a method market's clothes, and the who
    belongs on the moneyline at tier-1 hold, not in a 25% overround.

THE HAZARD CURVE (§1.3, §6). Finish hazard is front-loaded: of fights
that end inside the distance, roughly half end in round one and the
share decays by round. The dossiers hold no finish times, so this is a
structural prior, labeled as one — good enough to derive E[minutes],
the "quiet workhorse of the entire prop menu", and NEVER used to price
the tier-3 round markets (`markets.implied_markets` still refuses
those, correctly). Two script-driven bends: the Cardio Split shifts
hazard late (the finish arrives when the tank empties), and the Sub
Hunt flattens it (submissions accumulate position first).

Standard library only.
"""

from __future__ import annotations

#: Method picks require the devigged moneyline within this many points
#: of our own number on the same fighter. Beyond it, the disagreement
#: is about WHO — a moneyline opinion mispriced into a 20-30% hold.
ML_AGREE_TOL = 0.12

#: §6 — the share of inside-the-distance finishes falling in each round,
#: front-loaded, by scheduled rounds. Structural priors from the script
#: ("~45-50% in round one, ~25% in two, ~15-20% in three"), normalized.
HAZARD_SHAPE = {
    3: (0.50, 0.28, 0.22),
    5: (0.42, 0.24, 0.16, 0.10, 0.08),
}
#: The two profile bends: "late" tilts hazard toward the final rounds
#: (Cardio Split), "flat" levels it (Sub Hunt). Applied as a blend.
TILT_BLEND = 0.45


def family_devig(implied: list[float], anchor_p: float):
    """``(hold multiplier, [true projections])`` for one market family.

    ``implied`` are the family's raw implied probabilities; ``anchor_p``
    is what the sharper market says the family must sum to (a fighter's
    devigged win probability for his method family; the devigged
    distance probability for the decision family). Proportional
    scaling — the script's §2.2 worked example, verbatim.
    """
    if not implied or not anchor_p or anchor_p <= 0:
        return None, []
    s = sum(p for p in implied if p and p > 0)
    if s <= 0:
        return None, []
    mult = s / float(anchor_p)
    if mult < 1.0:
        # A family summing UNDER its anchor is not a negative hold — it
        # is a stale or thin menu; scaling would inflate every fair.
        return None, []
    return round(mult, 4), [round(p / mult, 4) for p in implied]


def ml_agreement(our_p: float, devig_p: float) -> str:
    """'' when the moneyline endorses our who, else the refusal."""
    if our_p is None or devig_p is None:
        return ""
    gap = float(our_p) - float(devig_p)
    if gap <= ML_AGREE_TOL:
        return ""
    return (f"the moneyline prices this fighter {gap * 100:.0f} points "
            f"below our number — that is a WHO disagreement, and a who "
            f"belongs on the moneyline at tier-1 hold, not inside a "
            f"method market's overround")


def round_hazard(p_itd: float, rounds: int = 3, tilt: str | None = None):
    """Per-round finish probabilities summing to P(inside the distance)."""
    shape = HAZARD_SHAPE.get(int(rounds or 3), HAZARD_SHAPE[3])
    n = len(shape)
    if tilt == "late":
        bent = tuple(s * (1 - TILT_BLEND) + r * TILT_BLEND
                     for s, r in zip(shape, reversed(shape)))
    elif tilt == "flat":
        bent = tuple(s * (1 - TILT_BLEND) + (1.0 / n) * TILT_BLEND
                     for s in shape)
    else:
        bent = shape
    total = sum(bent)
    p = max(0.0, min(1.0, float(p_itd or 0.0)))
    return [round(p * s / total, 4) for s in bent]


def expected_minutes(p_itd: float, rounds: int = 3,
                     tilt: str | None = None) -> float:
    """§1.3: Σ P(finish in r) × midpoint(r) + P(distance) × full length."""
    hz = round_hazard(p_itd, rounds, tilt)
    full = 5.0 * len(hz)
    mins = sum(h * (5.0 * i + 2.5) for i, h in enumerate(hz))
    return round(mins + (1.0 - sum(hz)) * full, 1)


def hazard_tilt(a: dict, b: dict) -> str | None:
    """Which script bends this fight's hazard, from the archetypes.

    Cardio Split — a pace-pusher against a fader — moves the finish
    late; a submission hunter flattens the decay. Anything else keeps
    the front-loaded prior.
    """
    arch = {(a or {}).get("archetype", ""), (b or {}).get("archetype", "")}
    decay = max((a or {}).get("r3_decay", 0.0) or 0.0,
                (b or {}).get("r3_decay", 0.0) or 0.0)
    if "cardio_machine" in arch and ("front_runner" in arch or decay >= 0.30):
        return "late"
    if "submission" in arch or "grappler" in arch:
        return "flat"
    return None


def triangle_report(p_a_devig: float, p_distance_model: float,
                    props_implied: dict | None) -> list[str]:
    """Residual lines for the card — the identities, checked out loud.

    ``props_implied``: {family: [raw implied probs]} for whatever the
    feed carried; families absent from the menu produce no line rather
    than an invented one.
    """
    lines: list[str] = []
    for fam, anchor, label in (
            ("method_a", p_a_devig, "A's method family"),
            ("method_b", (1.0 - p_a_devig) if p_a_devig is not None else None,
             "B's method family"),
            ("distance", p_distance_model, "the decision family")):
        implied = (props_implied or {}).get(fam)
        if not implied or anchor is None:
            continue
        mult, _ = family_devig(implied, anchor)
        if mult:
            lines.append(f"{label} sums to {sum(implied):.0%} against a "
                         f"{anchor:.0%} anchor — {(mult - 1) * 100:.0f}% "
                         f"internal hold")
    return lines
