"""Cage size, altitude and the scorecards — §8's underpriced layer.

Three facts about where a fight happens change its distribution, and none
of them is priced quickly:

**Cage size is a fact, not a read.** The promotion's own facility uses a
25-foot cage; arena events use 30. Less space means fewer places to
retreat to, so pressure fighters and wrestlers benefit, out-fighters
suffer, and finishes go up. This is knowable from the venue name before a
single stat is consulted, which is exactly why it is worth having.

**Altitude taxes cardio.** Mexico City sits above 7,000 feet and Denver
above 5,000. The tax lands hardest on high-output pressure fighters and on
anyone who cut hard, and it pushes finishes later — a cardio collapse in
rounds two and three rather than a first-round knockout.

**Judges reward what they can see.** The unified criteria emphasise
damage, but in practice control time and forward pressure score heavily
and volume without damage scores inconsistently. A fighter whose path is
"land more, damage less" — leg kicks, jabs, range volume — wins decisions
less often than his statistics suggest. On the road, in front of local
judges, that path deserves a haircut rather than a hope.

**On the size of these adjustments.** They are bounded, documented priors,
not fits. Nothing here has been measured against our own graded results,
so every effect is small, every one is capped, and the module reports what
it did in plain language on the card. The UFC board already journals into
its own probation bucket rather than the headline record, which is the
right home for a layer this young. When there are enough graded fights to
fit these, they should be fitted — and until then a modest documented
nudge is more honest than either a confident coefficient or pretending the
cage is the same size everywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

# Where the card is, recorded once per event. The odds feed carries no
# venue, and this is one fact per card rather than one per fight — the
# same bargain as weigh-ins, and cheaper.
STORE_FILE = Path("data") / "ufc_cards.json"


def load_cards(path: Path | str | None = None) -> dict:
    try:
        return json.loads(Path(path or STORE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def record_card(event_date: str, venue: str = "", city: str = "",
                path: Path | str | None = None) -> dict:
    p = Path(path or STORE_FILE)
    store = load_cards(p)
    rec = {"venue": venue.strip(), "city": city.strip()}
    store[event_date] = rec
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, indent=2, sort_keys=True))
    return rec


def card_for(event_date: str, store: dict) -> dict:
    return store.get(event_date) or {"venue": "", "city": ""}


# --- cage size --------------------------------------------------------------
SMALL_CAGE_FT = 25.0
STANDARD_CAGE_FT = 30.0

# Venues known to use the small cage. The promotion's own facility is the
# one that matters — it hosts most non-arena events.
SMALL_CAGE_VENUES = ("apex", "ufc apex", "ufc performance institute")


def cage_size(venue: str) -> dict:
    """Feet across, and whether we actually know."""
    v = (venue or "").strip().lower()
    if not v:
        return {"feet": None, "small": None, "known": False,
                "note": "venue not known — cage size not applied"}
    small = any(k in v for k in SMALL_CAGE_VENUES)
    return {"feet": SMALL_CAGE_FT if small else STANDARD_CAGE_FT,
            "small": small, "known": True,
            "note": ("25-foot cage — less room to retreat, so pressure and "
                     "wrestling gain and finishes rise"
                     if small else "30-foot arena cage — standard geometry")}


# --- altitude ---------------------------------------------------------------
# Feet above sea level for the cities that actually matter. Anything not
# listed is treated as unknown rather than as sea level: guessing "low"
# for an unrecognised city would silently drop the adjustment exactly when
# a new venue at elevation appears.
ALTITUDE_FT = {
    "mexico city": 7350, "ciudad de mexico": 7350,
    "denver": 5280, "salt lake city": 4226, "albuquerque": 5312,
    "calgary": 3438, "johannesburg": 5751, "bogota": 8660,
    "las vegas": 2001, "phoenix": 1086, "abu dhabi": 89,
}
ALTITUDE_MEANINGFUL_FT = 3000


def altitude(city: str) -> dict:
    c = (city or "").strip().lower()
    for name, feet in ALTITUDE_FT.items():
        if name in c:
            return {"feet": feet, "known": True,
                    "meaningful": feet >= ALTITUDE_MEANINGFUL_FT,
                    "note": (f"{feet:,} ft — a real cardio tax on the "
                             f"unacclimated, pushing finishes later"
                             if feet >= ALTITUDE_MEANINGFUL_FT
                             else f"{feet:,} ft — no meaningful cardio tax")}
    return {"feet": None, "known": False, "meaningful": False,
            "note": "venue city not recognised — altitude not applied"}


# --- how they move the distribution -----------------------------------------
# Bounded, documented priors. Each is a RELATIVE shift on the finish share
# of the distribution, and the total is capped so no stack of environment
# reads can rewrite a fight.
SMALL_CAGE_FINISH_LIFT = 0.10      # +10% relative to the finish probability
ALTITUDE_FINISH_LIFT = 0.06        # cardio breaks fights late
MAX_ENV_SHIFT = 0.15               # nothing here may move it more than this


def distribution_shift(venue: str, city: str) -> dict:
    """Relative lift to the finish probability, with its reasons."""
    cage = cage_size(venue)
    alt = altitude(city)
    lift, why = 0.0, []
    if cage["known"] and cage["small"]:
        lift += SMALL_CAGE_FINISH_LIFT
        why.append("small cage (+finishes)")
    if alt["meaningful"]:
        lift += ALTITUDE_FINISH_LIFT
        why.append(f"altitude {alt['feet']:,} ft (+late finishes)")
    lift = max(-MAX_ENV_SHIFT, min(MAX_ENV_SHIFT, lift))
    # The venue and city travel with the reading. Both were already the
    # INPUTS to every number in here, and leaving them out meant the card
    # could state the cage size and the cardio tax without ever naming the
    # building they came from — and meant the Overhead, which draws that
    # building, had nothing to label it with.
    return {"venue": venue, "city": city,
            "finish_lift": round(lift, 4), "cage": cage, "altitude": alt,
            "why": why,
            "fitted": False,
            "note": ("Environment adjustments are documented priors, not "
                     "fits — bounded on purpose and reported here so they "
                     "can be argued with.")}


def apply_to_joint(joint: dict, shift: dict) -> dict:
    """Re-shape the six-outcome joint by the environment's finish lift.

    Decisions lose what finishes gain, per fighter, and each fighter's
    total win probability is preserved exactly — the cage changes HOW a
    fight ends, not who wins it. That constraint is the whole reason this
    is safe to apply: a bounded reshaping cannot manufacture a moneyline
    edge out of a venue.
    """
    lift = float(shift.get("finish_lift") or 0.0)
    if not lift:
        return dict(joint)
    out = dict(joint)
    for who in ("a", "b"):
        ko, sub, dec = (joint[f"{who}_ko"], joint[f"{who}_sub"],
                        joint[f"{who}_dec"])
        total = ko + sub + dec
        if total <= 0:
            continue
        finish = ko + sub
        new_finish = min(total, finish * (1.0 + lift))
        gained = new_finish - finish
        scale = (new_finish / finish) if finish > 0 else 1.0
        out[f"{who}_ko"] = round(ko * scale, 4)
        out[f"{who}_sub"] = round(sub * scale, 4)
        out[f"{who}_dec"] = round(max(0.0, dec - gained), 4)
    out["distance"] = round(out["a_dec"] + out["b_dec"], 4)
    return out


# --- §8 judging -------------------------------------------------------------
# What the criteria reward in practice: damage, then control and forward
# pressure. Volume without damage is the path judges score least reliably.
LOW_DAMAGE_ARCHETYPES = ("point_striker", "volume_striker", "counter")
DECISION_HAIRCUT_ROAD = 0.12       # relative, applied to the decision path
DECISION_HAIRCUT_STYLE = 0.08


def judging_read(fighter: dict, on_the_road: bool = False) -> dict:
    """How well this fighter's offence actually scores.

    §8's practical rule, as arithmetic: if the only path is a close
    decision away from home, haircut that path rather than hoping.
    """
    arch = (fighter.get("archetype") or "").lower()
    cut, why = 0.0, []
    if arch in LOW_DAMAGE_ARCHETYPES:
        cut += DECISION_HAIRCUT_STYLE
        why.append("volume-over-damage offence scores inconsistently")
    if on_the_road:
        cut += DECISION_HAIRCUT_ROAD
        why.append("close decision on the road in front of local judges")
    # A control wrestler is the other side of the same coin: judges reward
    # what they can see, and control is visible.
    if arch == "wrestler" and cut > 0:
        cut = max(0.0, cut - DECISION_HAIRCUT_STYLE)
        why.append("control time is visible to judges and scores well")
    return {"decision_haircut": round(min(0.25, cut), 4), "why": why}
