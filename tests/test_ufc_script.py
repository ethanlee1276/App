"""The UFC handicapping script — the triangle, the hazard, the priors.

Ethan, 2026-09-01: "here is the same thing for ufc so we can get better
with that as well and try to find better picks." The audit found the
engine already carried the spine: the six-outcome vector with the 88%
win cap, division base rates, method markets priced off the vector,
cage/altitude/judging, weigh-in enforcement, layoff tracking, and the
within-fight incoherence checks. What was missing is what this pins:

  * §2  — the coherence triangle's machinery: family devig against the
    moneyline anchor (the sport's market-sum method, "the strongest
    version of that technique" because the identities are exact), and
    the §8 gate — a method bet is a HOW purchased on a WHO the sharp
    moneyline already endorses;
  * §1.3/§6 — expected duration from the front-loaded round-hazard
    prior, bent by the Cardio Split and Sub Hunt profiles, published on
    the card and never used to price the tier-3 round markets;
  * §5  — short notice reaches the WIN PROBABILITY, not just the
    data-quality clamp;
  * §4  — the age cliff is asymmetric: an older opponent's chin raises
    the KO share, which is the mechanism behind the aging-slugger ITD
    structure.

Run directly: `python3 tests/test_ufc_script.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine.ufc.triangle import (expected_minutes, family_devig, hazard_tilt,
                                 ml_agreement, round_hazard)


# --- §2.2: the script's worked example, verbatim ---------------------------
def test_the_worked_example_lands_on_the_scripts_numbers():
    """A at -200/B at +170 devigs to ~64.5%; the method family's raw sum
    of 78.6% against it is a ~22% internal hold, and +150 KO scales from
    40.0% to a true book projection of ~32.8%."""
    from engine.nba.prob import devig
    p_a, _ = devig(-200, 170)
    assert abs(p_a - 0.645) < 0.01, p_a
    mult, fair = family_devig([0.400, 0.286, 0.100], p_a)
    assert mult and abs(mult - 0.786 / p_a) < 0.02, mult
    assert abs(fair[0] - 0.328) < 0.01, fair
    assert abs(fair[1] - 0.235) < 0.01, fair
    assert abs(fair[2] - 0.082) < 0.01, fair


def test_a_family_summing_under_its_anchor_is_stale_not_generous():
    mult, fair = family_devig([0.20, 0.15], 0.645)
    assert mult is None and fair == []
    assert family_devig([], 0.645) == (None, [])
    assert family_devig([0.4], 0.0) == (None, [])


# --- §8: the who/how gate ---------------------------------------------------
def test_a_method_bet_needs_the_moneylines_endorsement():
    assert ml_agreement(0.60, 0.55) == "", "close enough — the how is live"
    why = ml_agreement(0.62, 0.40)
    assert "WHO" in why and "moneyline" in why
    assert ml_agreement(0.40, 0.62) == "", \
        "our number BELOW the market's is humility, not a disagreement"


def test_a_gated_method_row_never_becomes_the_best_market():
    from engine.ufc.markets import best_market
    ml = {"market": "moneyline", "priced": True, "edge": 0.05,
          "required_edge": 0.04, "market_tier": 1}
    method = {"market": "method", "priced": True, "edge": 0.15,
              "required_edge": 0.05, "market_tier": 2,
              "gate": "the moneyline prices this fighter 20 points below"}
    got = best_market([ml, method])
    assert got is ml, "the fat gated edge must not win"
    method2 = dict(method)
    method2.pop("gate")
    assert best_market([ml, method2]) is method2, \
        "ungated, the bigger cleared edge wins as before"


def test_the_model_wires_the_gate_onto_method_rows():
    with open(os.path.join(ROOT, "engine", "ufc", "model.py"),
              encoding="utf-8") as f:
        src = f.read()
    assert 'c["gate"] = why' in src
    assert "ml_agreement(p_model, mkt_a)" in src
    assert "ml_agreement(1.0 - p_model, mkt_b)" in src


# --- §1.3/§6: hazard and expected duration ----------------------------------
def test_hazard_is_front_loaded_and_sums_to_itd():
    hz = round_hazard(0.44, 3)
    assert abs(sum(hz) - 0.44) < 1e-6
    assert hz[0] > hz[1] > hz[2], hz
    assert len(round_hazard(0.5, 5)) == 5


def test_the_scripts_duration_example_reproduces():
    """§1.3: P(R1)=.22, P(R2)=.13, P(R3)=.09, distance .56 → 11.1
    minutes. Our front-loaded prior at the same 44% ITD lands within a
    tenth of the script's own hand-built hazard."""
    got = expected_minutes(0.44, 3)
    assert abs(got - 11.1) < 0.15, got


def test_the_profile_bends_move_the_hazard_the_right_way():
    base = round_hazard(0.5, 3)
    late = round_hazard(0.5, 3, "late")
    flat = round_hazard(0.5, 3, "flat")
    assert late[-1] > base[-1] and late[0] < base[0], (base, late)
    assert (base[0] - base[-1]) - (flat[0] - flat[-1]) > 0.02, (base, flat)
    assert abs(sum(late) - 0.5) < 1e-6 and abs(sum(flat) - 0.5) < 1e-6
    # A longer expected fight when the finish equity moves late.
    assert expected_minutes(0.5, 3, "late") > expected_minutes(0.5, 3)


def test_the_tilt_reads_the_fights_own_profile():
    assert hazard_tilt({"archetype": "cardio_machine"},
                       {"archetype": "front_runner"}) == "late"
    assert hazard_tilt({"archetype": "grappler"},
                       {"archetype": "striker"}) == "flat"
    assert hazard_tilt({"archetype": "striker"},
                       {"archetype": "striker"}) is None


def test_the_card_carries_the_duration_read_but_never_prices_rounds():
    with open(os.path.join(ROOT, "engine", "ufc", "model.py"),
              encoding="utf-8") as f:
        src = f.read()
    assert '"e_minutes": _e_min' in src
    assert '"scheduled_rounds": _rounds' in src
    with open(os.path.join(ROOT, "engine", "ufc", "markets.py"),
              encoding="utf-8") as f:
        mk = f.read()
    at = mk.index("def implied_markets")
    body = mk[at:mk.index("\ndef ", at + 10)]
    assert '"round"' not in body, \
        "tier-3 round markets stay unpriced — the hazard is context"


# --- §5: short notice reaches the number ------------------------------------
def _fighter(name, **kw):
    base = {"name": name, "age": 29, "archetype": "striker", "slpm": 4.0,
            "sapm": 3.5, "td_per15": 1.0, "td_acc": 0.4, "tdd": 0.6,
            "ctrl_per15": 2.0, "ko_losses": 0, "ko_losses_last3": 0,
            "r3_decay": 0.15, "red_flags": [], "ufc_fights": 8,
            "kd_per100": 1.0, "sub_att_per15": 0.5, "times_finished": 1,
            "fights": 12}
    base.update(kw)
    return base


def test_short_notice_costs_the_replacement_win_probability():
    from engine.ufc.model import win_probability
    a, b = _fighter("A"), _fighter("B")
    p_even, _ = win_probability(a, b)
    p_vs_short, notes = win_probability(a, _fighter("B", short_notice=True))
    assert p_vs_short > p_even, (p_even, p_vs_short)
    assert any("short notice" in n for n in notes)
    p_short_self, _ = win_probability(_fighter("A", short_notice=True), b)
    assert p_short_self < p_even


# --- §4: the asymmetric age cliff -------------------------------------------
def test_an_older_opponents_chin_raises_the_ko_share():
    from engine.ufc.model import method_conditionals
    young = method_conditionals(_fighter("A"), _fighter("B", age=28),
                                "lightweight")
    old = method_conditionals(_fighter("A"), _fighter("B", age=38),
                              "lightweight")
    assert old["ko"] > young["ko"], (young["ko"], old["ko"])
    same_age_conditional_sums = sum(old.values())
    assert abs(same_age_conditional_sums - 1.0) < 1e-6, \
        "the conditional must still normalize"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
