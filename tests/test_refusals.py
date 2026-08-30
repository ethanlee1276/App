"""A card that refuses to stake must not advertise EV, or wear a tick.

REPORTED FROM A LIVE CARD, 2026-08-30. Puka Nacua OVER 90.5 receiving
yards said, in this order:

    ✓ No credible market edge — line unavailable or price looks off
    ✓ This market's calibration fit hit the edge of its search range —
      the model can't price it reliably, so nothing here is bettable
      until it's fixed
    ✓ Dome game — no weather impact
    ⚠ No bettable price here — ... so we don't stake it
      +9% EV at this price

Four statements that nothing here is bettable, and then a green EV
number as the last thing on the card. Two failures, and they have
different shapes.

THE EV LINE was ungated: `evTxt` rendered whenever `ev_per_unit` was not
null. Worse than a contradiction — the EV is computed against the fair
price the card has just called unusable, so the number is downstream of
the fault it sits under. It is also the line a reader acts on.

THE TICKS are the older failure and the one this codebase keeps making.
`NEG_REASON` in web/js/app.js decides whether a bullet renders green or
struck through, and it does it by matching a hand-kept list of twenty-odd
keywords. Neither refusal string contained one, so both rendered as
points in the pick's FAVOUR. A rule announced in prose and enforced by an
enumeration that new copy silently fails.

So the strings are named constants now, and this file asserts every one
of them is classified as a refusal. Adding a new one without teaching the
front end about it fails the suite instead of shipping as an
endorsement.

Run directly: `python3 tests/test_refusals.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.betting import (NO_CREDIBLE_EDGE_REASON,     # noqa: E402
                            REFUSAL_REASONS,
                            UNRELIABLE_CALIBRATION_REASON)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "web", "js", "app.js")


def _app():
    with open(APP, encoding="utf-8") as fh:
        return fh.read()


def _neg_reason():
    """The front end's refusal detector, compiled in Python.

    Read out of app.js rather than restated here: a copy would pass this
    file while the shipped page kept the old list, which is the failure
    being tested for one layer up."""
    src = _app()
    m = re.search(r"const NEG_REASON = new RegExp\(\s*\[(.*?)\]\.join",
                  src, re.S)
    assert m, "NEG_REASON is no longer an array literal — update this reader"
    body = re.sub(r"//.*", "", m.group(1))
    items = re.findall(r'"((?:[^"\\\\]|\\\\.)*)"', body)
    assert len(items) > 10, items
    return re.compile("|".join(items), re.I)


# --- every refusal is classified as one -----------------------------------
def test_every_refusal_reason_renders_as_a_negative():
    """THE GUARD THAT MAKES THE REST OF THIS UNNECESSARY TO REMEMBER."""
    neg = _neg_reason()
    for reason in REFUSAL_REASONS:
        assert neg.search(reason), (
            "this reason refuses the bet and web/js/app.js would render it "
            "as a green tick — add a phrase from it to NEG_REASON:\n  "
            + reason)


def test_the_two_that_were_actually_shipping_green():
    """Named individually so a regression names itself rather than
    pointing at a tuple."""
    neg = _neg_reason()
    assert neg.search(NO_CREDIBLE_EDGE_REASON)
    assert neg.search(UNRELIABLE_CALIBRATION_REASON)


def test_a_supporting_reason_is_not_swept_up_as_a_refusal():
    """The other direction, or the detector could pass by calling
    everything negative."""
    neg = _neg_reason()
    for good in ("Dome game — no weather impact on the passing game",
                 "Trending up — last 3 games +11 vs prior form",
                 "Red-zone touch share ~60% (1.4 expected chances)",
                 "Team implied total 24.8 → 2.63 expected offensive TDs"):
        assert not neg.search(good), good


def test_the_engine_inserts_the_named_constants_not_loose_literals():
    """A literal at the insert site is invisible to anything asking "is
    this a refusal". Both boards go through the same two names."""
    import inspect
    from engine import betting
    from engine.mlb import betting as mlb
    for mod in (betting, mlb):
        src = inspect.getsource(mod)
        assert "reasons.insert(0, UNRELIABLE_CALIBRATION_REASON)" in src, \
            mod.__name__
        assert "reasons.insert(0, NO_CREDIBLE_EDGE_REASON)" in src, \
            mod.__name__
    # The literal survives exactly once, as the constant's own definition.
    assert inspect.getsource(betting).count('"No credible market edge') == 1
    assert '"No credible market edge' not in inspect.getsource(mlb), \
        "the MLB board kept its own copy of the string"


def test_no_other_module_reinvents_a_refusal_literal():
    """A third copy could drift in wording while claiming to say the same
    thing, and the front end would then have to know about all three."""
    import pathlib
    hits = []
    for p in pathlib.Path(os.path.join(ROOT, "engine")).rglob("*.py"):
        t = p.read_text(encoding="utf-8")
        for m in re.finditer(r"reasons\.insert\(0,\s*\"", t):
            hits.append(str(p.relative_to(ROOT)))
    assert not hits, f"refusal literals reintroduced in {sorted(set(hits))}"


# --- the EV line ----------------------------------------------------------
def test_the_ev_line_is_gated_on_being_bettable():
    src = _app()
    assert "(r.ev_per_unit == null || !r.bettable) ? \"\"" in src, \
        "a card that refuses to stake can advertise EV again"


def test_the_ev_line_still_shows_on_a_card_that_does_stake():
    """The gate must not silence a real price — that is the same failure
    in the other direction, and it would empty the page's only mention of
    what a row is worth."""
    src = _app()
    body = src[src.index("function likelyCard(r)"):]
    body = body[:body.index("\nfunction ")]
    assert "% EV at this price" in body
    assert "r.ev_per_unit == null" in body, \
        "a missing EV must still render nothing rather than 0%"


def test_the_refusal_is_said_once_not_twice():
    """The warning block states the calibration refusal in the page's own
    voice. Repeating the engine's version as a bullet said it twice and
    pushed a real reason off the five-bullet list."""
    src = _app()
    body = src[src.index("function likelyCard(r)"):]
    body = body[:body.index("\nfunction ")]
    assert "r.bettable || !/nothing here is bettable/i.test(x)" in body
    # And the warning block itself is still there to carry the fact.
    assert "No bettable price here" in body


def test_the_filter_leaves_a_bettable_cards_reasons_alone():
    src = _app()
    body = src[src.index("function likelyCard(r)"):]
    body = body[:body.index("\nfunction ")]
    # `r.bettable ||` comes FIRST, so a bettable row never reaches the
    # regex and keeps every reason the engine gave it. Written the other
    # way round the filter would still work but would be one short-circuit
    # away from silently dropping a real bullet.
    cond = body[body.index(".filter((x) =>"):body.index(".slice(0, 5)")]
    assert cond.index("r.bettable") < cond.index("nothing here is bettable")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
