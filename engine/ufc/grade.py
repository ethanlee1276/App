"""§10's 0-100 grade and the tightest bankroll caps in the system.

The grade's weights say something specific about this sport. Data quality
carries 15% *because a great edge computed off four rounds of tape is not
a great bet*, and fight-week information carries another 15% because in a
sport with no injury report the thing you didn't hear is the thing that
beats you. Together that is 30% of the grade spent on "how much do we
actually know", which is more than any other model here spends — and
correctly so, given the samples.

The caps are the tightest anywhere in this system, and the reasoning is
structural rather than nervous. A fight is one coin flip with a hard edge:
there is no 600-plate-appearance regression to save a good process from a
bad night. Worse, a card's outcomes are not independent in the way they
look — a night of finishes or a night of robberies hits every position at
once. So: 1.5% on a fight, 2.5% on a fight once correlated positions are
counted together, 8% across the whole card.

Half Kelly is never used here. Quarter is the ceiling and an eighth is the
operating floor, because Kelly assumes the edge estimate is accurate and
this is the model in this repo whose edge estimate rests on the smallest
samples and the worst injury information.
"""

from __future__ import annotations

# §10 — the weights, summing to 100.
GRADE_WEIGHTS = {"edge": 40, "data_quality": 15, "camp_info": 15,
                 "style_clarity": 10, "environment": 10, "movement": 10}
MIN_GRADE = 70                     # "Below 70: no bet, no leans."

# A component we have no feed for scores ``None`` — UNOBSERVED, which is
# not the same as neutral. Scoring it 0.5 and then measuring the total
# against 100 taxes every fight for a gap that no fight can close: with
# no line-movement feed and no weigh-in, the best possible card in the
# world topped out around 90, so a "70 bar" was really a 77 bar and the
# board sat empty for a reason that had nothing to do with the fights.
#
# Instead the present components are renormalised to 100 — the grade
# answers "how good is this bet on the scorecard we can actually see".
# The honesty lives in COVERAGE instead: an incomplete scorecard is
# reported, and it cannot earn top marks.
MIN_COVERAGE = 0.60                # below this there is no grade to give
INCOMPLETE_CEILING = 89            # no A+ on a scorecard with holes

# §10 — fractional Kelly. Half is never used in MMA.
KELLY_FLOOR = 0.125                # an eighth
KELLY_CEILING = 0.25               # a quarter, and that is the ceiling

# §10 — bankroll caps as fractions of bankroll.
CAP_PER_FIGHT = 0.015
CAP_PER_FIGHT_CORRELATED = 0.025
CAP_PER_CARD = 0.08
DRAWDOWN_TRIGGER = 0.10

# A unit is 5% of bankroll everywhere in this repo, so a 1.5% cap is 0.30u.
UNITS_PER_BANKROLL = 20


def edge_score(edge: float, required: float) -> float:
    """Edge as 0-1 against THIS market's own bar."""
    if edge <= 0 or required <= 0:
        return 0.0
    if edge < required:
        return round(0.5 * edge / required, 4)
    return round(min(1.0, 0.5 + 0.5 * (edge - required) / (2 * required)), 4)


def data_quality(a: dict, b: dict) -> dict:
    """§10 — how much measured tape sits behind this fight.

    Scored off the thinner of the two corners, because a fight is priced
    on the pair: perfect data on one fighter and none on the other is not
    half a model, it is no model.
    """
    fa = int(a.get("ufc_fights", 0) or 0)
    fb = int(b.get("ufc_fights", 0) or 0)
    thin = min(fa, fb)
    # Full marks at 8 tracked fights each — roughly 20+ rounds a side,
    # which is about as much as this sport ever offers.
    score = max(0.0, min(1.0, thin / 8.0))
    return {"score": round(score, 3), "tracked_fights": thin,
            "note": f"{thin} tracked UFC fight(s) on the thinner corner"}


def camp_info(weigh_in: dict | None, a: dict, b: dict) -> dict:
    """§10/§7 — how much of fight week we can actually see.

    Weigh-ins are the one fight-week fact this system genuinely observes,
    so they carry the component. Everything else in §7 — camp footage,
    training reports, gym changes — has no structured source, and scoring
    it as present would be inventing the sport's signature edge rather
    than having it. That is why this component cannot reach 1.0: the cap
    is the honest statement that we are missing the layer the spec calls
    MMA's signature edge.
    """
    wi = weigh_in or {}
    states = [(wi.get(side) or {}).get("state") for side in ("a", "b")]
    made = sum(1 for s in states if s == "made")
    missed = sum(1 for s in states if s == "missed")
    short = bool(a.get("short_notice") or b.get("short_notice"))
    why = []

    if not made and not missed and not short:
        # Nothing about fight week is observable yet. That is a HOLE in the
        # scorecard, not a bad score — the fight is graded on the rest and
        # the coverage number says so. Docking every fight a fixed amount
        # for a weigh-in that has not happened yet meant the board stayed
        # empty until Friday no matter how good the fights were.
        return {"score": None, "why": ["weigh-in not recorded yet — this "
                                       "fight is graded without the "
                                       "fight-week component",
                                       "no camp-footage or training-report "
                                       "feed exists"]}

    score = 0.5 + 0.5 * (made / 2.0)
    if made == 2:
        why.append("both made weight")
    elif missed:
        why.append("a missed weight is recorded — a live negative, not a gap")
    else:
        why.append("weigh-in partially recorded")
    if short:
        score -= 0.2
        why.append("short-notice booking — no full camp to observe")
    why.append("no camp-footage or training-report feed exists")
    return {"score": round(max(0.0, min(1.0, score)), 3), "why": why}


def style_clarity(notes: list[str], a: dict, b: dict) -> dict:
    """§10 — does the matchup have a readable stylistic story?

    "No strong style read" is the honest majority case and scores as such.
    A named matrix entry is a real read; two fighters of the same archetype
    is a genuine coin flip and should not score as clarity.
    """
    text = " ".join(notes or []).lower()
    if "no strong style read" in text:
        return {"score": 0.4, "why": "no named style edge — a coin-flip look"}
    same = (a.get("archetype") and a.get("archetype") == b.get("archetype"))
    if same:
        return {"score": 0.45, "why": "mirror-image archetypes"}
    return {"score": 0.85, "why": "a named stylistic mismatch drives the read"}


def environment_score(shift: dict) -> dict:
    """§10 — do we know where this fight is happening?

    Knowing the venue is worth full marks whether or not it moves the
    number. An unknown venue is UNOBSERVED — it drops out of the grade
    rather than scoring badly, because a missing feed is not evidence
    against a bet and docking it would quietly sink every card until a
    source exists. Set the card's venue and this becomes a real component
    instead of a hole — see `launch.py --card-venue`.
    """
    cage = (shift or {}).get("cage") or {}
    alt = (shift or {}).get("altitude") or {}
    known = int(bool(cage.get("known"))) + int(bool(alt.get("known")))
    if not known:
        return {"score": None,
                "why": ["venue not set — cage size and altitude unchecked, "
                        "so this fight is graded without them"]}
    return {"score": round(0.5 + 0.25 * known, 3),
            "why": (shift or {}).get("why") or ["standard conditions"]}


def _clip(v):
    return None if v is None else max(0.0, min(1.0, float(v)))


def grade_detail(edge: float, required: float, data: float | None,
                 camp: float | None, style: float | None, env: float | None,
                 movement: float | None = None) -> dict:
    """The §10 grade, scored over the components we actually observed.

    ``None`` means "no feed for this" and drops the component from both
    the numerator and the denominator. ``coverage`` is the share of the
    weight that was observable, and it is reported rather than buried:
    a grade of 78 on 85% coverage is a different object from a 78 on all
    of it, and the page says so.

    Edge is never optional. If we cannot price the bet there is no bet.
    """
    parts = {
        "edge": edge_score(edge, required),
        "data_quality": _clip(data),
        "camp_info": _clip(camp),
        "style_clarity": _clip(style),
        "environment": _clip(env),
        "movement": _clip(movement),
    }
    present = {k: v for k, v in parts.items() if v is not None}
    total_w = sum(GRADE_WEIGHTS.values())
    have_w = sum(GRADE_WEIGHTS[k] for k in present)
    coverage = round(have_w / total_w, 4)
    missing = sorted(k for k in parts if parts[k] is None)

    if coverage < MIN_COVERAGE:
        return {"score": 0, "coverage": coverage, "missing": missing,
                "capped": False, "parts": parts,
                "why": (f"only {coverage:.0%} of the scorecard is observable "
                        f"— not enough to grade, let alone bet")}

    raw = sum(present[k] * GRADE_WEIGHTS[k] for k in present) / have_w * 100.0
    score = int(round(raw))
    capped = bool(missing) and score > INCOMPLETE_CEILING
    if capped:
        score = INCOMPLETE_CEILING
    return {"score": score, "coverage": coverage, "missing": missing,
            "capped": capped, "parts": parts,
            "why": ("graded on the full scorecard" if not missing else
                    f"graded on {coverage:.0%} of the scorecard — no feed for "
                    + ", ".join(m.replace("_", " ") for m in missing))}


def grade(edge: float, required: float, data: float | None,
          camp: float | None, style: float | None, env: float | None,
          movement: float | None = None) -> int:
    """The §10 unified 0-100 grade (see :func:`grade_detail`)."""
    return grade_detail(edge, required, data, camp, style, env,
                        movement)["score"]


def grade_label(score: int) -> str:
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= MIN_GRADE:
        return "B+"
    return "Pass"


def kelly_fraction(score: int) -> float:
    """Eighth to quarter Kelly, by grade. Half is never used in MMA."""
    if score >= 90:
        return KELLY_CEILING
    if score >= 80:
        return 0.1875
    return KELLY_FLOOR


def stake_fraction(p: float, odds: int, score: int,
                   drawdown: bool = False) -> float:
    """Fraction of bankroll, capped at 1.5% for a single fight."""
    b = (100.0 / abs(odds) if odds < 0 else odds / 100.0)
    if b <= 0:
        return 0.0
    full = (p * b - (1.0 - p)) / b
    if full <= 0:
        return 0.0
    stake = min(full * kelly_fraction(score), CAP_PER_FIGHT)
    # Halve AFTER the cap — halving first leaves any play whose raw Kelly
    # exceeded the ceiling sitting right back on the ceiling, so the
    # drawdown rule would do nothing precisely when it matters.
    if drawdown:
        stake *= 0.5
    return round(stake, 5)


def apply_card_caps(picks: list[dict]) -> list[dict]:
    """§10 — 2.5% per fight with correlation, 8% across the card.

    Applied in grade order so the cap costs the worst play that was going
    to be made rather than a random one, and correlated positions on one
    fight share a budget because they lose together.
    """
    out, per_fight, total = [], {}, 0.0
    for p in sorted(picks, key=lambda x: -x.get("grade", 0)):
        stake = p.get("stake_fraction", 0.0)
        key = p.get("fight", "")
        room_fight = max(0.0, CAP_PER_FIGHT_CORRELATED - per_fight.get(key, 0.0))
        room_card = max(0.0, CAP_PER_CARD - total)
        allowed = round(min(stake, room_fight, room_card), 5)
        if allowed <= 0:
            out.append({**p, "stake_fraction": 0.0, "capped": True,
                        "cap_note": "card or per-fight cap reached — no room"})
            continue
        per_fight[key] = per_fight.get(key, 0.0) + allowed
        total += allowed
        out.append({**p, "stake_fraction": allowed,
                    "capped": allowed < stake - 1e-9,
                    "cap_note": ("trimmed by the per-fight/card cap"
                                 if allowed < stake - 1e-9 else "")})
    return out


def units(fraction: float) -> float:
    return round((fraction or 0.0) * UNITS_PER_BANKROLL, 2)
