"""The arithmetic that produced a projection, kept instead of discarded.

Ethan, 2026-08-20: "A public 'how this model thinks' page for one pick —
projection, form blend, which rungs adjusted it, gate conditions, comps."

Every projection on this site is one number times a short series of named
multipliers. `engine/projection.py` computes them, uses them and drops
them on the floor; only the product survives into the payload. So the
card can say "we project 78.4 receiving yards" and cannot say where 78.4
came from — which is the one question a reader who is being asked to
trust a model should be able to ask.

WHY A CHAIN AND NOT A PARAGRAPH. The `reasons` list already narrates some
of this, and prose is exactly the wrong medium for it: a sentence can
round, omit a factor, or survive a code change that altered the number it
describes. A chain is checkable. `product()` multiplies it back out, and
`tests/test_chain.py` fails the build if base × Π(steps) is not the mean
that shipped — so the page cannot show a derivation the model did not
perform, and a factor cannot be quietly dropped from the display without
the arithmetic stopping short of the answer.

FLAT STEPS ARE KEPT, NOT FILTERED. A weather multiplier of exactly 1.00
is a real finding — the model looked and the weather changed nothing —
and it is also what keeps the product exact. The front end collapses them
behind a count; the data keeps them all.

CLAMPS ARE STEPS. Both sports bound the combined hand-tuned factors
(`clamp(matchup * weather * injury, 0.85, 1.18)`), and when that bound
bites, the sub-factors no longer multiply to the total. Recording the
difference as its own step is the only representation that is both exact
and honest: the model refusing to let three factors compound is a real
part of how it thinks, and hiding it would leave a chain that does not
reach its own answer.
"""

from __future__ import annotations

#: How the reader sees each factor. Keys are stable; labels are copy.
STEP_LABELS = {
    "usage": "Usage bridge",
    "matchup": "Matchup",
    "weather": "Weather",
    "injury": "Injuries around him",
    "learned": "Learned model",
    "cap": "Combined-factor cap",
    "trend": "Recent-form shade",
    "context": "Team tendency",
    "player": "Player memory",
    "park": "Ballpark",
    "statcast": "Contact quality",
    "ump": "Plate umpire",
    "rare": "Rare-event damping",
}

#: Where the multiplying starts.
BASE_LABELS = {
    "form": "Form blend",
    "usage": "Form blend + measured role",
    "rate": "Rate model",
}

#: Below this a step is reported as having left the number alone. Display
#: only — the value is still carried and still multiplied.
FLAT = 0.005


def step(key: str, mult, why: str = "") -> dict:
    """One named factor. `mult` of 1.0 is kept, not dropped — see module
    docstring."""
    return {"key": key, "label": STEP_LABELS.get(key, key),
            "mult": round(float(mult), 4), "why": why or ""}


def cap_step(raw: float, capped: float, lo: float, hi: float) -> dict | None:
    """The difference a clamp made, or None when it did not bite."""
    if raw <= 0 or abs(capped / raw - 1.0) < 1e-9:
        return None
    return step("cap", capped / raw,
                f"The combined factors came to ×{raw:.2f}; the model caps "
                f"them at ×{lo:g}–×{hi:g} so no three inputs can compound "
                f"into a number the market has never been that wrong about.")


def build(base_value, base_source: str, steps: list, mean,
          **base_meta) -> dict:
    """The finished chain. `base_meta` rides along on the base — the form
    weights, the sample size, whatever the reader needs to judge where the
    starting number came from."""
    return {
        "base": {"value": round(float(base_value), 4),
                 "source": base_source,
                 "label": BASE_LABELS.get(base_source, base_source),
                 **base_meta},
        "steps": [s for s in steps if s],
        "mean": round(float(mean), 4),
    }


def product(chain: dict) -> float:
    """Base times every step — what the chain claims the answer is."""
    out = float((chain.get("base") or {}).get("value") or 0.0)
    for s in chain.get("steps") or []:
        out *= float(s.get("mult", 1.0))
    return out


def closes(chain: dict, tol: float = 0.01) -> bool:
    """Does the chain reach the number that shipped?

    The tolerance is relative and generous on purpose: the steps are
    rounded to four places for the payload, so an exact equality would
    fail on rounding rather than on a missing factor. A dropped or
    mis-signed factor moves the product far more than 1%.
    """
    want = float(chain.get("mean") or 0.0)
    if want == 0:
        return abs(product(chain)) < 1e-6
    return abs(product(chain) / want - 1.0) <= tol
