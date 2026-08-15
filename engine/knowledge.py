"""Which TIER of knowledge each reason on a card comes from.

NFL_MODEL §2.3, quoted in full because the whole design follows from it:

    Label your knowledge tiers in every output: (a) verified current data —
    retrieved and timestamped today; (b) stable historical data — career
    splits, scheme history, things that don't move; (c) your own inference.
    The reader must always be able to see which is which, **because the fix
    for a bad bet depends on which tier failed.**

That last clause is the point, and it is a debugging argument rather than a
presentation one. A pick that lost because tonight's usage number was stale
needs a feed fix. One that lost because a 1,499-spot historical comp did not
repeat needs nothing — that is variance doing what variance does. One that
lost because the model's own game-script inference was wrong is the only one
of the three that means the MODEL is wrong. Today all three render as
identical grey sentences, so a post-mortem cannot tell them apart.

CLASSIFIED BY PREFIX, FROM A REGISTRY, AND NEVER GUESSED
--------------------------------------------------------
Reasons are plain strings written by a dozen modules, so there is no field
to read. What they do have is a consistent opening label — "Usage bridge:",
"Comps:", "Cooling off —" — and those labels are enumerable: 38 distinct
ones across the live NFL and MLB boards on 2026-08-09, which is how this
registry was built. Measured, not imagined.

**An unregistered reason gets NO tier**, and that is the important rule. A
classifier that guesses would put a confident (a) on a sentence it has never
seen, and a label that is sometimes wrong is worse than no label — the
reader cannot tell which ones to trust, so none of them can be trusted. A
missing label says "nobody has classified this yet", which is true and
harmless. `unregistered()` lists them so the registry can be extended
deliberately.

NOTHING HERE PRICES ANYTHING. It reads the finished reason strings and
returns a letter. `docs/THE_INFORMATION_TEST.md` is why that matters: the
claimed edge carries no information (AUC 0.479), so every new signal lands
as evidence until something moves that number, and a labelling layer must
not be the exception that quietly slips into a grade.
"""

from __future__ import annotations

import re

#: The three tiers, in the spec's own words. The key is what goes on the
#: card; the blurb is what the `why?` chip explains.
TIERS = {
    "measured": (
        "measured",
        "verified current data — retrieved and timestamped for this slate"),
    "historical": (
        "historical",
        "stable historical data — career splits, park factors, scheme "
        "history: things that do not move week to week"),
    "inference": (
        "inference",
        "the model's own reasoning on top of the data — the tier that "
        "means the MODEL was wrong when it fails"),
}

#: prefix (lowercased, matched at the start of the reason) → tier.
#:
#: Built by counting every distinct reason opening on the live boards
#: rather than by imagining what they might say. Where a label was
#: genuinely ambiguous it went to `inference`, because over-claiming
#: freshness is the failure that matters: a reader who thinks a number was
#: retrieved today will not go looking for a stale feed.
PREFIXES: tuple[tuple[str, str], ...] = (
    # (a) verified current data — this slate's retrieved numbers
    ("usage bridge", "measured"),
    ("cooling off", "measured"),
    ("trending up", "measured"),
    ("hot bat", "measured"),
    # Four the doctor caught unlabelled on 2026-08-10 (75.7% coverage on
    # the live board). All computed from this slate's retrieved data.
    ("opposing starter not confirmed", "measured"),
    ("high humidity", "measured"),
    ("hot stretch", "measured"),
    ("opposing bullpen worked", "measured"),
    ("volatile week-to-week role", "measured"),
    ("elite csw%", "measured"),
    ("elite swing-and-miss", "measured"),
    ("opposing bullpen ranks", "measured"),
    ("batting ", "measured"),
    ("wind blowing", "measured"),
    ("roof closed", "measured"),
    ("hot (", "measured"),
    ("dome game", "measured"),
    ("neutral site", "measured"),
    ("high game total", "measured"),
    ("low game total", "measured"),
    ("slg ", "measured"),
    ("xslg ", "measured"),
    # Statcast season leaderboards: retrieved for this slate and current
    # to the season, so (a) rather than (b) — they move every week.
    ("elite barrel rate", "measured"),
    ("hard-hit rate", "measured"),
    # Three the doctor caught on Ethan's live board, 2026-08-15 (75.7%
    # coverage). Each classified by reading what writes it, per the rule
    # at the top of this file — a guessed tier is worse than none.
    #
    # `engine/mlb/platoon.py` — THIS season's official SLG split vs LHP or
    # RHP, pulled from the MLB Stats API for this slate and quoted with
    # its own PA count. Same argument as the Statcast lines above: it
    # moves through the season, so (a). NOT the same thing as "platoon
    # edge" below, which is the handedness matchup itself and genuinely
    # does not move.
    ("official season split", "measured"),
    # `engine/linemoves.py` — movement measured between our own stored
    # snapshots and now. A retrieved, timestamped fact about the market.
    ("market moving toward", "measured"),
    # `engine/mlb/streaks.py` — the exact mirror of "hot stretch" above,
    # written by the same function from the same last-N game logs.
    ("cold stretch", "measured"),

    # (b) stable historical data — things that do not move
    ("comps", "historical"),
    ("altitude", "historical"),
    ("platoon edge", "historical"),
    ("coors field", "historical"),
    ("loandepot park", "historical"),

    # (c) the model's own inference
    ("no credible market edge", "inference"),
    ("game script", "inference"),
    ("matchup adjustment", "inference"),
    ("model sides", "inference"),
    ("platoon/arsenal matchup", "inference"),
    ("park/weather/umpire environment", "inference"),
    ("tough draw", "inference"),
    # The model's own arithmetic about its own bar, and its own stance on
    # an unresolved input (§2.4's conditional projections). Neither is a
    # fact about the world, which is what makes them (c).
    ("edge +", "inference"),
    ("edge -", "inference"),
    ("conditional until", "inference"),
    # `engine/mlb/pipeline.py` — reconcile_triple nudging our OWN hits,
    # total-bases and home-run projections until they stop contradicting
    # each other. No new fact about the world enters: it is the model's
    # arithmetic about the model's numbers, which is the same argument
    # that puts "edge +" here.
    ("coherence", "inference"),
)

#: A park name we do not hold is still a park. These catch the shapes the
#: prefix list cannot enumerate — every stadium, every pitcher — without
#: reaching for a general-purpose keyword guess.
PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\bpark (?:suppresses|elevates|plays|boosts)\b", re.I),
     "historical"),
    (re.compile(r"\ballows \.\d+ slg to (?:righties|lefties)\b", re.I),
     "historical"),
    (re.compile(r"\bstrikes out \d+% of the time\b", re.I), "measured"),
    (re.compile(r"\bpoints the other way\b", re.I), "inference"),
)


def tier_of(reason: str) -> str | None:
    """Which tier this reason's knowledge came from, or None if unknown.

    None is a real answer and the safe one. See the module docstring: a
    label that is sometimes wrong poisons the labels that are right.
    """
    if not reason:
        return None
    s = str(reason).strip().lower()
    for prefix, tier in PREFIXES:
        if s.startswith(prefix):
            return tier
    for pat, tier in PATTERNS:
        if pat.search(s):
            return tier
    return None


def tag(reasons) -> list[dict]:
    """`[{text, tier}]` for a card's reason list, tier possibly None."""
    return [{"text": r, "tier": tier_of(r)} for r in (reasons or [])]


def mix(reasons) -> dict:
    """How many of a card's reasons come from each tier.

    The summary the §2.3 argument actually wants: a pick standing on three
    inferences and no measurement is a different object from one standing
    on three measurements, and the count says so at a glance.
    """
    out: dict = {}
    for r in (reasons or []):
        out[tier_of(r) or "unlabelled"] = out.get(tier_of(r) or "unlabelled",
                                                  0) + 1
    return out


def unregistered(all_reasons) -> list[str]:
    """Distinct reason openings no rule covers, commonest first.

    The maintenance hook. New reasons appear whenever a module is added,
    and without this the registry silently falls behind while the cards
    quietly stop being labelled.
    """
    seen: dict = {}
    for r in (all_reasons or []):
        if tier_of(r) is not None:
            continue
        head = re.split(r"[:—]", str(r), 1)[0].strip()
        if head:
            seen[head] = seen.get(head, 0) + 1
    return [k for k, _ in sorted(seen.items(), key=lambda kv: -kv[1])]


def stamp(result: dict) -> int:
    """Write `reason_tiers` beside `reasons` on every card in a slate.

    STAMPED IN THE BUILD, NOT CLASSIFIED IN THE BROWSER, because the
    registry must have exactly one home. A mirrored copy in JavaScript
    would be correct on the day it was written and wrong the first time a
    module adds a reason — and it would be wrong silently, on the side
    nobody runs tests against.

    A parallel list rather than a rewrite of `reasons`: every existing
    reader of that field keeps working, and `docs/inventory-baseline.json`
    does not see a shape change on 1,600 strings.

    Returns how many reasons carried a tier, so a build can print it and a
    slate that stops being labelled is visible the day it happens.
    """
    n = 0
    for key in ("recommendations", "long_shots", "longshot_watch",
                "game_bets", "near_misses"):
        for card in (result.get(key) or []):
            if not isinstance(card, dict):
                continue
            rs = card.get("reasons")
            if not rs:
                continue
            tiers = [tier_of(r) for r in rs]
            card["reason_tiers"] = tiers
            n += sum(1 for t in tiers if t)
    return n
