"""ratecheck: is a pitcher prop a total, or a rate times a length?

A strikeout prop is two predictions wearing one number — stuff (K per out,
a property of the pitcher) and length (outs recorded, a manager's
decision). engine/mlb/projection.py blends past TOTALS, so the volatile
term is hidden inside the stable-looking one and nothing in that path
knows how long tonight's start is expected to be.

The obvious response is to project rate × length instead. These tests pin
why that is not the finding it sounds like, and what the actual decision
number is.

If both terms are noise around a pitcher's own means, estimating them
apart buys NOTHING: E[r]·E[L] is E[r]·E[L] either way, and tonight's
draw is irreducible. Decomposition only pays if tonight's LENGTH can be
predicted better than his average — which is a claim about having
information the average lacks, not about arithmetic.

So the number that decides whether any leash model is worth building is
the ORACLE: the same rate blend times the length the start actually ran.
It cheats on purpose, and it bounds what a perfect bullpen model could
ever be worth. Small headroom means the error is in the rate and a leash
model is work spent on the wrong half.

Run directly: `python3 tests/test_ratecheck.py`
"""

import io
import contextlib
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ratecheck as rc                                        # noqa: E402


def synth(rate_cv, len_cv, n_pitchers=40, starts=25, seed=5):
    """Pitcher starts with controllable rate and length volatility.

    r and L are drawn ONCE per start, so the strikeouts and the outs come
    from the same start — drawing them twice makes the oracle read a
    length that never produced those strikeouts, and silently inverts the
    whole measurement.
    """
    rnd = random.Random(seed)
    out = {}
    for p in range(n_pitchers):
        base_r, base_l = rnd.uniform(0.20, 0.42), rnd.uniform(15, 20)
        rows = []
        for g in range(starts):
            r = max(0.05, rnd.gauss(base_r, base_r * rate_cv))
            length = max(3.0, rnd.gauss(base_l, base_l * len_cv))
            rows.append((g, round(r * length), round(length)))
        out[f"P{p}"] = rows
    return out


def _run(starts, market="strikeouts"):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc.report(starts, market)
    return " ".join(buf.getvalue().split())


# --- the oracle, which is the point ------------------------------------------
def test_the_oracle_finds_headroom_when_length_is_the_volatile_term():
    """A perfect length prediction is worth a great deal here, so a leash
    model would be worth building IF the leash can be predicted."""
    w = rc.walk(synth(rate_cv=0.12, len_cv=0.35))
    assert w["headroom"] > 0.5, w
    assert w["mae_oracle"] < w["mae_direct"]


def test_the_oracle_finds_none_when_the_error_is_in_the_rate():
    """The answer that saves the work: if stuff is what swings, a bullpen
    model cannot pay for itself however good the story sounds."""
    w = rc.walk(synth(rate_cv=0.35, len_cv=0.08))
    assert w["headroom"] < 0.10, w
    out = _run(synth(rate_cv=0.35, len_cv=0.08))
    assert "oracle barely beats" in out
    assert "work spent on the wrong half" in out


def test_decomposing_on_past_length_buys_nothing_by_itself():
    """The result that stops the obvious rewrite. If length is noise around
    a pitcher's own mean, estimating it separately does not predict it —
    E[r]·E[L] is the same number either way, and the value of the idea is
    entirely in conditioning length on TONIGHT, not in the arithmetic."""
    for rate_cv, len_cv in ((0.12, 0.35), (0.35, 0.08)):
        w = rc.walk(synth(rate_cv, len_cv))
        assert abs(w["gain"]) < 0.05, (rate_cv, len_cv, w["gain"])
        # …even where the oracle says the headroom is enormous.
    w = rc.walk(synth(0.12, 0.35))
    assert w["headroom"] > 0.5 and abs(w["gain"]) < 0.05


# --- where the variance lives ------------------------------------------------
def test_stability_separates_stuff_from_the_manager():
    s = rc.stability(synth(rate_cv=0.10, len_cv=0.40))
    assert s["length"] > s["rate"]
    out = _run(synth(rate_cv=0.10, len_cv=0.40))
    assert "Length swings more than rate" in out

    s = rc.stability(synth(rate_cv=0.40, len_cv=0.08))
    assert s["rate"] > s["length"]
    out = _run(synth(rate_cv=0.40, len_cv=0.08))
    assert "argument AGAINST bothering to separate" in out


# --- the joins and the guards ------------------------------------------------
def test_the_two_stats_come_from_the_same_start():
    """Joined on game_id, not two averages that never met. A rate built
    from one game's strikeouts and another's outs is not a rate."""
    import inspect
    src = inspect.getsource(rc.load_starts)
    assert "a.game_id = b.game_id" in src
    assert "a.player = b.player" in src


def test_a_start_with_no_outs_is_not_a_rate():
    starts = {"P": [(i, 3.0, 0.0) for i in range(20)]}
    w = rc.walk(starts)
    assert w["n"] == 0, "a divide-by-zero start was scored"


def test_a_thin_log_is_scored_for_neither_method():
    w = rc.walk(synth(0.2, 0.2, n_pitchers=5, starts=4))
    assert w["n"] == 0


def test_an_empty_history_says_what_is_missing():
    out = _run({})
    assert "No pitcher starts found" in out
    assert "'outs' market" in out, "no pointer to why the join came back empty"


def test_it_never_edits_the_projection():
    """Measure, report, let a person decide — the same rule guardfit lives
    under. A tool that rewrote a projection path on its own findings would
    be the one thing this must not be."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "ratecheck.py"), encoding="utf-8").read()
    assert "write_text" not in src
    assert "MLB_WINDOW_WEIGHTS =" not in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
