"""Is tonight's "probable starter" actually an opener? — MLB §5's flag.

An opener throws the first inning and hands the ball over. An outs
projection of 16.5 for him is not optimistic, it is a category error, and
a K line priced off his season rate is priced off innings he will not
pitch. Detection is from his own recent starts — no role feed exists and
none is needed — read from the same cached game log velocity.py uses.

Run directly: `python3 tests/test_openers.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb import openers as op                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_innings_pitched_is_thirds_not_a_decimal():
    """"5.2" is 5 and TWO OUTS — 17 outs, not 15.6. Parsing it as a float
    makes every partial inning slightly wrong in a way that never looks
    wrong."""
    assert op._outs("5.2") == 17
    assert op._outs("1.0") == 3
    assert op._outs("0.2") == 2
    assert op._outs("6") == 18
    assert op._outs("") is None
    assert op._outs(None) is None


def test_an_opener_flags_and_a_starter_does_not():
    assert op.looks_like_opener([3, 4, 3, 5, 3]) is True
    assert op.looks_like_opener([18, 19, 16, 20, 17]) is False


def test_median_shrugs_off_one_bad_night_each_way():
    """A real starter with one injury exit must not flag, and an opener
    who was once left in must. The mean gets both wrong."""
    assert op.looks_like_opener([18, 19, 2, 17]) is False
    assert op.looks_like_opener([3, 4, 15, 3]) is True


def test_one_start_is_a_blowup_not_a_role():
    """None below the floor, and None is not False: an unknown role must
    not read as "confirmed starter" downstream."""
    assert op.looks_like_opener([2]) is None
    assert op.looks_like_opener([]) is None


def test_the_boundary_is_two_innings():
    assert op.looks_like_opener([6, 6, 6]) is True
    assert op.looks_like_opener([7, 7, 7]) is False


def test_relief_appearances_never_reach_the_verdict():
    """The question is what happens when he is handed the first inning —
    same `gamesStarted` rule as velocity.recent_start_pks."""
    src = open(os.path.join(ROOT, "engine", "mlb", "openers.py"),
               encoding="utf-8").read()
    assert "gamesStarted" in src


def test_a_feed_hiccup_is_not_a_role():
    op._MEMO.clear()
    # fetch_game_log will fail in the sandbox (no network) — the flag
    # must come back None, not raise, not False.
    assert op.opener_flag(999999999, 1999) is None
    op._MEMO.clear()


def test_the_opener_gate_refuses_both_sides():
    """A GATE as of 2026-08-10, Ethan-approved. This is a correctness
    refusal, not an edge play: the projection's central assumption — a
    starter's workload — is known false before the first pitch, which
    puts it in the same family as block_live_games and
    MAX_CREDIBLE_EDGE. Both sides are refused, because our number is
    equally invalid in both directions; "we cannot price this game" is a
    different statement from "the over is bad"."""
    src = open(os.path.join(ROOT, "engine", "mlb", "pipeline.py"),
               encoding="utf-8").read()
    i = src.index("OPENER — his recent starts")
    block = src[max(0, i - 1200):i]
    assert '"recommended"] = False' in block.replace("d[", '"')  \
        or 'd["recommended"] = False' in block
    assert 'd["grade"] = "Pass"' in block
    assert "BOTH SIDES" in block, "the both-sides reasoning must stay"


def test_the_gate_only_fires_on_a_confirmed_opener():
    """None (unknown role, thin sample, feed hiccup) must price normally.
    A gate that fires on ignorance would empty the board every April."""
    from engine.mlb import openers as _op
    assert _op.looks_like_opener([2]) is None
    assert _op.looks_like_opener([18, 17, 19]) is False
    # Only True gates; the pipeline tests `if _of(...)` so None and False
    # both fall through.
    src = open(os.path.join(ROOT, "engine", "mlb", "pipeline.py"),
               encoding="utf-8").read()
    assert "if _of(prop.person_id" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
