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
                            IMPLAUSIBLE_EDGE_REASON,
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


# --- the same fault on the main card --------------------------------------
def _pair():
    """The SAME prop evaluated twice: once at the book's real price, once
    with the book renamed "proxy" so the engine treats the line as its
    own invention. One prop, so nothing but the market can explain a
    difference between the two."""
    import copy
    from engine.data_loader import load_slate
    from engine.projection import build_projection
    from engine.betting import evaluate_prop
    sl = load_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    prop = sl.props[0]
    game, opp = sl.game_for(prop), sl.team(prop.opponent)
    real = evaluate_prop(prop, build_projection(prop, game, opp), game=game)
    fake = copy.deepcopy(prop)
    for ln in fake.lines:
        ln.book = "proxy"
    proxy = evaluate_prop(fake, build_projection(fake, game, opp), game=game)
    return real, proxy


def test_a_proxy_priced_row_reports_no_ev_not_a_fabricated_one():
    """FOUND SWEEPING FOR THE REST OF THE PUKA CARD'S CLASS, and it is
    the larger number of the two.

    `evaluate_prop` has always zeroed `edge` when no book posted a line —
    "don't report a number that reads as an edge". But `ev` and
    `net_edge` are computed from `best.odds`, which on a proxy row is the
    engine's own invented price, and they were left alone. So a card
    whose Edge cell correctly read "—" printed "EV / unit +13%" in the
    next cell along, off a price nobody offered.

    At a 59% model probability against a -110 proxy that is +12.6% a
    unit; at 62% against -115 it is +15.9%. Both larger than the +9% that
    got this looked at in the first place."""
    _real, proxy = _pair()
    assert proxy.has_market is False
    assert proxy.edge == 0.0, proxy.edge
    assert proxy.ev_per_unit == 0.0, proxy.ev_per_unit
    assert proxy.net_edge is None, proxy.net_edge


def test_a_real_price_still_reports_its_ev():
    """The gate must not silence a priced row — that is the same failure
    in the other direction and it would empty the metric."""
    real, _proxy = _pair()
    assert real.has_market is True
    assert real.ev_per_unit != 0.0
    assert real.net_edge is not None


def test_the_card_blanks_the_ev_cell_the_way_it_blanks_the_edge_cell():
    """Both guards live one line apart and only one of them existed."""
    src = _app()
    body = src[src.index("function cardHTML(r)"):]
    body = body[:body.index("\nfunction ")]
    metrics = body[body.index('<div class="metrics">'):body.index("${confMeter")]
    assert metrics.count('r.has_market === false ? "—"') == 2, metrics
    assert "EV / unit" in metrics and "Edge" in metrics


def test_ev_is_zeroed_rather_than_blanked_because_three_places_sort_on_it():
    """A None here is a NaN in a sort. The card decides what to SHOW; the
    engine still has to hand every consumer a number."""
    import inspect
    from engine import betting
    src = inspect.getsource(betting.evaluate_prop)
    assert "ev = 0.0" in src
    assert "net = None" in src


def test_a_real_line_the_model_disagrees_with_is_named_as_such():
    """St. Brown, 2026-09-02: FanDuel −114 on the card and the refusal
    said "line unavailable or price looks off". `credible` is False two
    ways, and they get two sentences now."""
    import inspect
    from engine import betting
    src = inspect.getsource(betting)
    assert "if not credible and not has_market:" in src
    assert "reasons.insert(0, IMPLAUSIBLE_EDGE_REASON)" in src
    assert "line unavailable" not in NO_CREDIBLE_EDGE_REASON
    neg = _neg_reason()
    assert neg.search(IMPLAUSIBLE_EDGE_REASON)
    assert IMPLAUSIBLE_EDGE_REASON in REFUSAL_REASONS


def test_a_script_bullet_against_the_side_taken_is_not_a_tick():
    """The engine signs the bullet; the page honours the sign over its
    keyword list — "underdog" in the middle of a bullet that ends "with
    this side" must not strike it through."""
    neg = _neg_reason()
    against = ("Game script: 7.0-pt favorite — projected leading script leans "
               "pass volume down (×0.97) — against this side")
    with_fav_under = ("Game script: 7.0-pt favorite — projected leading script "
                      "leans pass volume down (×0.97) — with this side")
    assert neg.search(against) and not neg.search(with_fav_under)
    js = _app()
    assert "function isNegReason(x)" in js
    assert "with this side" in js and "against this side" in js
    # every tick-or-cross decision goes through the signed door
    assert "NEG_REASON.test(" not in js.replace("return NEG_REASON.test(s);", "")


def test_the_grade_note_does_not_repeat_the_script_bullet():
    """One sentence per fact: with a numbered script bullet on the card,
    the grade's "leans against this side of the number" note stays off."""
    from engine.pipeline import run_slate
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = run_slate(os.path.join(here, "data", "sample_slate.json"))
    for r in out["recommendations"]:
        rs = r.get("reasons") or []
        if any(x.startswith("Game script:") for x in rs):
            assert not any(x.startswith("Game script leans") for x in rs), rs
        for x in rs:
            if x.startswith("Game script:") and ("volume up" in x or "volume down" in x):
                assert x.endswith("this side"), x


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
