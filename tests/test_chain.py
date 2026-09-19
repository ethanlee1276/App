"""The arithmetic that produced a projection, kept instead of discarded.

Ethan, 2026-08-20: "A public 'how this model thinks' page for one pick —
projection, form blend, which rungs adjusted it, gate conditions, comps."

All four already existed and none of them reached a screen. Every
projection on this site is one number times a short series of named
multipliers; engine/projection.py computed them, used them and dropped
them, so a card could state 106.7 rushing yards and could not show where
106.7 came from. The gate ledger had the same shape inverted — a rule
wrote a warning when it FAILED and left nothing behind when it passed, so
"no warnings" and "cleared six conditions" rendered identically and only
one of those is a statement. And the comps have been attached to every
recommendation since they shipped, read by nothing.

WHAT THIS FILE ACTUALLY DEFENDS is that the displayed derivation is the
performed one. A waterfall is persuasive furniture: rows, arrows, a
running total, an answer. It is also the easiest thing on a site to get
subtly wrong — drop a factor from the display, or add one the code does
not apply, and it still looks like arithmetic. So every chain is
multiplied back out and compared with the mean that shipped, across every
prop of both sample slates. If base × Π(steps) is not the projection, the
build fails here rather than the page lying quietly.

FLAT STEPS ARE KEPT. A weather multiplier of exactly 1.00 is a finding —
the model looked and the weather changed nothing — and it is also what
makes the product exact. The page collapses them into a count; the data
keeps every one.

CLAMPS ARE STEPS. Both sports bound the combined hand-tuned factors, and
when that bound bites the sub-factors stop multiplying to the total.
Recording the difference as its own row is the only representation that
is both exact and honest: a model refusing to let three inputs compound
is part of how it thinks.

Run directly: `python3 tests/test_chain.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import chain                                     # noqa: E402
from engine.rules import RuleConfig, apply_rules             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()

_SLATES = {}


def _nfl():
    if "nfl" not in _SLATES:
        from engine import pipeline
        _SLATES["nfl"] = pipeline.run_slate(
            os.path.join(ROOT, "data", "sample_slate.json"))
    return _SLATES["nfl"]


def _mlb():
    if "mlb" not in _SLATES:
        from engine.mlb import pipeline as mp
        _SLATES["mlb"] = mp.run_mlb_slate(
            os.path.join(ROOT, "data", "mlb_sample_slate.json"))
    return _SLATES["mlb"]


# ------------------------------------------------- the chain reaches its own answer

def test_every_nfl_chain_multiplies_back_to_the_projection():
    recs = _nfl()["recommendations"]
    assert recs, "the sample slate produced nothing to check"
    for r in recs:
        c = r.get("chain") or {}
        assert c, f"{r['player']} {r['market']} shipped with no chain"
        assert chain.closes(c), (
            f"{r['player']} {r['market']}: the steps multiply to "
            f"{chain.product(c):.4f} but the projection shipped as {c['mean']}")


def test_every_mlb_chain_multiplies_back_to_the_projection():
    recs = _mlb()["recommendations"]
    assert recs, "the sample slate produced nothing to check"
    for r in recs:
        c = r.get("chain") or {}
        assert c, f"{r['player']} {r['market']} shipped with no chain"
        assert chain.closes(c), (
            f"{r['player']} {r['market']}: the steps multiply to "
            f"{chain.product(c):.4f} but the projection shipped as {c['mean']}")


def test_a_dropped_factor_is_caught():
    """The failure this whole file exists for: a display that omits one
    multiplier still renders as a tidy waterfall."""
    c = _nfl()["recommendations"][0]["chain"]
    moved = [i for i, s in enumerate(c["steps"])
             if abs(s["mult"] - 1) >= 0.02]
    assert moved, "no step on this pick moved enough to make the test real"
    broken = {**c, "steps": [s for i, s in enumerate(c["steps"])
                             if i != moved[0]]}
    assert not chain.closes(broken), \
        "a chain missing a real factor still passed the arithmetic check"


def test_an_invented_factor_is_caught():
    c = _nfl()["recommendations"][0]["chain"]
    broken = {**c, "steps": list(c["steps"]) + [chain.step("player", 1.15)]}
    assert not chain.closes(broken)


# ------------------------------------------------- what the chain contains

def test_flat_factors_are_kept_not_filtered():
    """The model looking at the weather and finding nothing is a finding,
    and dropping those rows would also break the product."""
    seen = False
    for r in _nfl()["recommendations"] + _mlb()["recommendations"]:
        for s in (r.get("chain") or {}).get("steps", []):
            if abs(s["mult"] - 1.0) < 1e-9:
                seen = True
    assert seen, ("not one flat step survived into a payload — either the "
                  "sample slates changed or flat factors are being filtered")


def test_the_clamp_is_a_step_and_only_when_it_bites():
    assert chain.cap_step(1.25, 1.18, 0.85, 1.18) is not None
    assert chain.cap_step(1.10, 1.10, 0.85, 1.18) is None, \
        "a clamp that did nothing was still reported as having acted"
    s = chain.cap_step(1.25, 1.18, 0.85, 1.18)
    assert abs(s["mult"] - 1.18 / 1.25) < 1e-9
    assert "1.25" in s["why"], "the cap does not say what it capped"


def test_the_base_carries_the_form_blend_it_used():
    """"Which rungs adjusted it" is only answerable if the reader can see
    the rung the number started on."""
    c = _nfl()["recommendations"][0]["chain"]
    w = c["base"]["weights"]
    assert w and abs(sum(w.values()) - 1.0) < 0.02, w
    assert c["base"]["sample_games"] >= 0
    assert c["base"]["label"], "the base has no name"


def test_the_mlb_rate_base_says_what_the_blend_would_have_said():
    """Rare events do not use the recency blend, because "last1" on a home
    run is literally 0 or 1. Showing the blend's answer beside the rate's
    is how a reader sees why."""
    rare = [r for r in _mlb()["recommendations"]
            if (r.get("chain") or {}).get("base", {}).get("source") == "rate"]
    assert rare, "no rare-event market in the sample slate"
    b = rare[0]["chain"]["base"]
    assert b.get("form_mean") is not None, \
        "the rate base no longer reports the blend it replaced"


# ------------------------------------------------- the gate ledger

def test_every_rule_leaves_a_trace_whether_it_passed_or_failed():
    """A rule that only speaks when it blocks cannot be shown to have run.
    Absence is not evidence."""
    for r in _nfl()["recommendations"]:
        assert r.get("checks"), f"{r['player']} shipped with no gate ledger"
    for r in _mlb()["recommendations"]:
        assert r.get("checks"), f"{r['player']} shipped with no gate ledger"


def test_a_failing_rule_flips_its_own_check():
    """Built by tightening the bar under a pick that cleared the real one,
    so the pass and the fail come from the same pick."""
    from engine.data_loader import load_slate
    from engine.projection import build_projection
    from engine.betting import evaluate_prop
    sl = load_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    prop = sl.props[0]
    game, opp = sl.game_for(prop), sl.team(prop.opponent)
    rec = evaluate_prop(prop, build_projection(prop, game, opp), game=game)
    loose = apply_rules(rec, prop, game, RuleConfig(min_edge=-1.0))
    tight = apply_rules(rec, prop, game, RuleConfig(min_edge=0.99))
    by_key = {c["key"]: c for c in loose.checks}
    assert by_key["edge"]["passed"] is True
    tk = {c["key"]: c for c in tight.checks}
    assert tk["edge"]["passed"] is False, "an unmet bar still reported a pass"
    assert tk["edge"]["value"] == by_key["edge"]["value"], \
        "the reported value changed with the threshold — it is the pick's own"
    assert "0.99" in tk["edge"]["limit"] or "99" in tk["edge"]["limit"]


def test_a_rule_that_cannot_apply_is_not_reported_as_weighed():
    """The deep-ball wind block cannot bite a rushing prop, and printing it
    on one would claim a condition was considered that was not."""
    from engine.data_loader import load_slate
    from engine.projection import build_projection
    from engine.betting import evaluate_prop
    sl = load_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    rush = [p for p in sl.props if p.market == "rush_yds"]
    passing = [p for p in sl.props if p.market in ("pass_yds", "rec_yds")]
    assert rush and passing, "sample slate has no market pair to compare"
    for prop, want in ((rush[0], False), (passing[0], True)):
        game, opp = sl.game_for(prop), sl.team(prop.opponent)
        rec = evaluate_prop(prop, build_projection(prop, game, opp), game=game)
        keys = {c["key"] for c in apply_rules(rec, prop, game).checks}
        assert ("wind" in keys) is want, (prop.market, keys)


# ------------------------------------------------- the page

def test_the_prop_page_carries_all_three_sections():
    i = APP.index("function renderPropPage(")
    body = APP[i:APP.index("\nfunction openGame(", i)]
    for want in ("chainHTML(r)", "checksHTML(r)", "compsHTML(r)"):
        assert want in body, f"the prop page no longer renders {want}"


def test_each_section_draws_nothing_without_its_data():
    """A slate built before any of this existed must render exactly as it
    did — an empty box is a worse answer than no box."""
    for fn in ("chainHTML", "checksHTML", "compsHTML"):
        i = APP.index(f"function {fn}(")
        head = APP[i:i + 320]
        assert 'return ""' in head, \
            f"{fn} no longer degrades to silence on a payload without it"


def test_the_comps_are_read_from_the_side_we_hold():
    """The stored rate is always the OVER's. Quoting it under an under pick
    prints the report exactly upside down."""
    i = APP.index("function compsHTML(")
    body = APP[i:APP.index("\n}\n", i)]
    assert "side_rate" in body
    assert "1 - Number(c.hit_rate)" in body, \
        "the fallback no longer takes the complement for an under"


def test_the_direction_is_derived_from_the_multiplier():
    """A stored sentence can drift away from the number it describes; a
    computed one cannot."""
    i = APP.index("function chainStepRow(")
    body = APP[i:APP.index("\n}\n", i)]
    assert 'm > 1 ? "raised" : "cut"' in body, \
        "the step's direction is no longer read off its own multiplier"


def test_the_page_refuses_to_draw_a_chain_that_does_not_close():
    i = APP.index("function chainHTML(")
    body = APP[i:APP.index("\n}\n", i)]
    assert "chainCloses(c)" in body
    flat = " ".join(APP.split())
    assert "do not multiply back to the projection" in flat, \
        "the refusal no longer tells the reader why the breakdown is missing"


def test_the_sections_are_styled():
    for sel in (".ch-row", ".ch-bar", ".ck-row", ".cp-bar"):
        assert f"{sel} " in CSS or f"{sel}," in CSS or f"{sel}{{" in CSS, sel


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    # run_tests.py counts a file's tests by reading "N tests passed" off
    # this line. "all good" matches nothing, so this file scored zero and
    # was still drawn green — say the number instead.
    print(f"\n{ran} tests passed." if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
