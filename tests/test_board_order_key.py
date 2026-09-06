"""What the Best Bets board sorts on, and why it stopped being the edge.

Ethan, 2026-09-06: "Point Best Bets at what the model demonstrably does.
It ranks probability about as well as the market and finds no edge."

THE MEASUREMENT BEHIND IT. `stakecheck --info` over 931 settled bets:

    model hit_prob   AUC 0.589
    market implied   AUC 0.589
    claimed edge     AUC 0.471

The claimed edge ranks WORSE THAN A COIN FLIP, and it was the board's
third sort term. The two numbers that do rank are indistinguishable from
each other.

THE CAVEAT, RECORDED BECAUSE IT CUTS AGAINST THE CHANGE. `stakecheck
--select` measured the same pool ordered three ways and found prob and
market agree on 94% of the top quarter. Ordering by probability is very
nearly ordering by PRICE — it shortens the average price rather than
adding information. Ethan chose it with that stated, and it is switchable
(`QB_BOARD_ORDER=edge`) precisely so the claim gets re-measured against a
real record rather than argued from a backtest.

THE BUG THIS ALMOST SHIPPED WITH, which is the reason for the second test
below. A prop carries `hit_prob`; a moneyline, spread or total carries
`win_prob`. A sort reading only `hit_prob` hands every game bet 0.0 and
sinks the whole Game Lines section to the bottom — no error, no warning,
just the board silently reordered wrong.

Run directly: `python3 tests/test_board_order_key.py`
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import pipeline as P                    # noqa: E402
from engine.mlb import pipeline as MP               # noqa: E402


def _prop(**kw):
    base = {"recommended": True, "confidence": 0.7, "edge": 0.05,
            "hit_prob": 0.55}
    return {**base, **kw}


def _game(**kw):
    """A game bet: win_prob, and NO hit_prob at all."""
    base = {"recommended": True, "confidence": 0.7, "edge": 0.05,
            "win_prob": 0.55}
    return {**base, **kw}


def test_the_default_is_probability():
    assert P.BOARD_ORDER == "prob", (
        "Ethan's call 2026-09-06: probability is the default, edge stays "
        "one env flag away")


def test_probability_decides_between_two_equal_picks():
    """The whole change, in one assertion: same tier, same confidence,
    the higher probability goes first even though its edge is lower."""
    lo_edge_hi_prob = _prop(edge=0.02, hit_prob=0.66)
    hi_edge_lo_prob = _prop(edge=0.09, hit_prob=0.51)
    ranked = sorted([hi_edge_lo_prob, lo_edge_hi_prob],
                    key=P.order_key, reverse=True)
    assert ranked[0] is lo_edge_hi_prob, "the board still ranks on edge"


def test_a_game_bet_is_ranked_on_its_own_probability_field():
    """THE TRAP. Game bets carry `win_prob`, never `hit_prob`. Read only
    the prop key and every moneyline, spread and total gets 0.0 and falls
    below every prop on the board."""
    strong_game = _game(win_prob=0.70)
    weak_prop = _prop(hit_prob=0.52)
    ranked = sorted([weak_prop, strong_game], key=P.order_key, reverse=True)
    assert ranked[0] is strong_game, (
        "a 70% game bet ranked below a 52% prop — win_prob is being read "
        "as 0.0 and the Game Lines section has sunk to the bottom")
    # And the key must not raise on a row carrying neither.
    assert P.order_key({"recommended": True, "confidence": 0.5})[2] == 0.0


def test_confidence_still_outranks_the_probability():
    """Ethan's call: only the THIRD term moved. A higher-confidence pick
    stays above a likelier one, so any change in the board is
    attributable to the key rather than to two changes at once."""
    sure = _prop(confidence=0.9, hit_prob=0.51)
    likely = _prop(confidence=0.4, hit_prob=0.80)
    ranked = sorted([likely, sure], key=P.order_key, reverse=True)
    assert ranked[0] is sure


def test_recommended_still_leads():
    """A non-recommended row never outranks a recommended one, however
    likely it looks."""
    shown = _prop(recommended=True, hit_prob=0.40)
    hidden = _prop(recommended=False, hit_prob=0.95)
    ranked = sorted([hidden, shown], key=P.order_key, reverse=True)
    assert ranked[0] is shown


def test_the_flag_puts_the_edge_back():
    """Switchable was the point: the old ordering has to be reachable
    without a revert, or `--select`'s two arms cannot be compared on a
    live board.

    Asked for by ARGUMENT rather than by reloading the module. The first
    version of this test reloaded `engine.pipeline`, which rebinds
    `order_key` to a new function object while `engine.mlb.pipeline`
    holds the old one — breaking the one-definition guarantee the test
    below asserts, and failing it. The parameter exists so this can be
    checked without disturbing anything.
    """
    lo_edge_hi_prob = _prop(edge=0.02, hit_prob=0.66)
    hi_edge_lo_prob = _prop(edge=0.09, hit_prob=0.51)
    ranked = sorted([lo_edge_hi_prob, hi_edge_lo_prob],
                    key=lambda r: P.order_key(r, "edge"), reverse=True)
    assert ranked[0] is hi_edge_lo_prob
    # and the default arm still ranks the other way round
    ranked = sorted([hi_edge_lo_prob, lo_edge_hi_prob],
                    key=lambda r: P.order_key(r, "prob"), reverse=True)
    assert ranked[0] is lo_edge_hi_prob


def test_the_env_var_is_what_sets_the_default():
    """The flag has to actually be wired to the environment, not just to
    a constant somebody edits."""
    src = open(os.path.join(ROOT, "engine", "pipeline.py"),
               encoding="utf-8").read()
    assert 'os.environ.get("QB_BOARD_ORDER", "prob")' in src


def test_both_pipelines_read_one_definition():
    """THE DRIFT GUARD. This tuple was hand-copied into four places. If
    the MLB board stops importing the football board's key, the two can
    disagree about what 'best' means and nothing will say so."""
    assert MP._order_key is P.order_key


def test_the_near_miss_list_was_left_alone():
    """`engine/mlb/pipeline.py` also sorts the priced-out list by
    `edge * quality` — 'closest to the bar first'. That is a different
    question (what nearly qualified) and must NOT be swept into this
    change."""
    src = open(os.path.join(ROOT, "engine", "mlb", "pipeline.py"),
               encoding="utf-8").read()
    assert 'x["edge"] * (x["quality"] / 100.0)' in src


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails
          else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
