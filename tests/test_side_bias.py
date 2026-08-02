"""Is the model's disagreement with the market one-sided?

On Ethan's 591-prop card, all five of the biggest edges were UNDERs at
20-25%:

    Brandon Marsh UNDER 1.5 hits          edge 24.91%  ← too big to believe
    Brandon Marsh UNDER 1.5 total_bases   edge 24.53%  ← too big to believe
    David Fry UNDER 0.5 hits              edge 22.54%  ← too big to believe
    Jake Mangum UNDER 2.5 hits            edge 20.68%  ← too big to believe
    Ronald Acuña Jr. UNDER 1.5 hits       edge 20.27%  ← too big to believe

Five is not a sample, which is the whole reason this exists rather than a
conclusion in a chat message.

The distinction it draws needs opposite fixes. Symmetric disagreement means
a noisy model and a credibility ceiling doing its job. One-sided
disagreement means a BIASED model — systematically projecting low — where
every "edge too big to believe" is one error appearing hundreds of times.
A ceiling cannot fix that. It hides it, and hides it worst on exactly the
props where the error is biggest.

Both verdicts are exercised below. A measurement that can only return one
answer is not a measurement.
"""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()


def _block():
    i = SRC.index("def side_bias(")
    return SRC[i:SRC.index("def _settleable_days(")]


def _board(overs, unders, over_edge, under_edge, path):
    """A synthetic board with a known skew, written where the CLI reads."""
    recs = []
    for n, side, edge in ((overs, "OVER", over_edge),
                          (unders, "UNDER", under_edge)):
        for i in range(n):
            recs.append({"player": f"P{side}{i}", "market": "hits",
                         "side": side, "line": 1.5, "odds": -110,
                         "edge": edge, "tier": 1, "has_market": True})
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"sport": "mlb", "date": "2026-08-01",
                   "recommendations": recs}, fh)


def _run(overs, unders, over_edge, under_edge):
    """Run the real CLI against a synthetic board, then put the real one
    back — the launcher reads a fixed path."""
    real = os.path.join(ROOT, "web", "data", "mlb_recommendations.json")
    backup = None
    if os.path.exists(real):
        backup = tempfile.mktemp(suffix=".json")
        with open(real, encoding="utf-8") as fh:
            open(backup, "w", encoding="utf-8").write(fh.read())
    try:
        _board(overs, unders, over_edge, under_edge, real)
        p = subprocess.run([sys.executable, "launch.py", "--side-bias", "mlb"],
                           cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, p.stderr[-400:]
        return p.stdout
    finally:
        if backup:
            with open(backup, encoding="utf-8") as fh:
                open(real, "w", encoding="utf-8").write(fh.read())
            os.unlink(backup)


# --- the two verdicts -------------------------------------------------------
def test_a_one_sided_board_is_called_one_sided():
    """Unders all above the 5% ceiling, overs all below it."""
    out = _run(60, 60, over_edge=0.01, under_edge=0.09)
    assert "ONE-SIDED" in out
    assert "favours UNDER" in out
    assert "Fix the projection; do not loosen the ceiling." in out


def test_a_symmetric_board_is_not_called_biased():
    """The negative control. Without this passing, the test above is only
    evidence that the function can print the word ONE-SIDED."""
    out = _run(60, 60, over_edge=0.09, under_edge=0.09)
    assert "Symmetric" in out
    assert "ONE-SIDED" not in out


def test_the_skew_is_named_in_whichever_direction_it_runs():
    out = _run(60, 60, over_edge=0.09, under_edge=0.01)
    assert "favours OVER" in out


def test_a_thin_board_refuses_to_call_it():
    """7 props with a 0% / 80% split is not evidence of anything, and
    printing a verdict on it would be worse than printing nothing."""
    out = _run(3, 4, over_edge=0.01, under_edge=0.09)
    assert "Too few on one side to call" in out
    assert "ONE-SIDED" not in out and "Symmetric" not in out


def test_the_threshold_is_a_real_sample_on_both_sides():
    b = _block()
    assert 'o["n"] >= 30 and u["n"] >= 30' in b


# --- scope ------------------------------------------------------------------
def test_long_shots_are_excluded_like_everywhere_else():
    """They are their own board with their own model; mixing them in would
    measure two models at once."""
    b = _block()
    assert 'r.get("tier") != 3' in b
    assert '"home_runs", "anytime_td"' in b


def test_it_reads_the_same_ceiling_the_engine_applies():
    b = _block()
    assert "MAX_CREDIBLE_EDGE * MARKET_SHRINK" in b


def test_it_never_writes_anything():
    b = _block()
    for verb in ("open(", "write", "INSERT", "UPDATE"):
        assert verb not in b.replace(".read_text()", ""), \
            f"side_bias performs a {verb}"


def test_it_is_wired_to_a_flag_and_takes_a_sport():
    assert 'if "--side-bias" in argv:' in SRC
    assert "side_bias(who)" in SRC


def test_a_missing_board_is_a_message_not_a_traceback():
    b = _block()
    assert "except (OSError, ValueError):" in b


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
