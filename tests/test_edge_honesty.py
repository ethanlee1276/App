"""Two places where an absolute number lied about a relative one.

Both faults were found on the same evening, in the same journal, and they
are the same mistake wearing different clothes: a threshold or a headline
denominated in absolute probability points, applied across markets whose
base rates run from 12% to 60%.

**The Lab's ROI tile.** On a mixed basis it showed the BLENDED ROI. On the
real board total_bases blended to +2.7% — over a segment table reading
25,145 bets against a naive baseline and 277 against real book lines. The
blend is 99% naive by bet count, so the green +2.7% was the naive figure,
sitting above a subtitle about real closes and coloured like an edge over a
market. Strikeouts blended to +4.6% and was -0.3% on the 102 bets that met
a real price. The site's own basis_note says a naive-priced row "measures
predictive skill, not an edge over the market" — and the tile said
otherwise, louder.

**The loss miner's closure bar.** Five probability points. Home runs said
15% and hit 12% over 1,863 bets: three points, so it could never close —
but that is a fifth of the claim, at roughly z 3.6, and it had already
survived false-discovery control. Ten slices were found on the real
journal and NOT ONE could close, every one of them a low-probability
market missing by less than five points because its claims are barely
above five points to begin with. A loop that cannot act is decoration.

Run directly: `python3 tests/test_edge_honesty.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import losspatterns as lp                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(name: str) -> str:
    i = APP.index(f"function {name}(")
    j = APP.find("\nfunction ", i + 1)
    return APP[i:j if j > 0 else len(APP)]


# --- the closure bar --------------------------------------------------------
def test_a_low_probability_market_can_close_itself():
    """The real journal's home-run book: said 15%, hit 12%, n=1,863.

    Three points is a fifth of the claim. Under an absolute-only bar it
    was unreachable — which is why ten findings produced zero closures.
    """
    rel = (15.0 - 12.0) / 100.0 / 0.15
    assert rel >= lp.CLOSE_GAP_REL, rel
    assert (15.0 - 12.0) < lp.CLOSE_GAP_PTS, "fixture no longer tests the gap"


def test_the_absolute_bar_still_closes_a_high_probability_market():
    """The relative bar is an ADDITION. A 60% claim hitting 54% is six
    points and only a tenth of the claim — it must still close on points
    alone, or the fix has traded one blind spot for another."""
    pts, rel = 6.0, (6.0 / 100.0) / 0.60
    assert pts >= lp.CLOSE_GAP_PTS
    assert rel < lp.CLOSE_GAP_REL


def test_both_bars_are_read_and_a_pooled_slice_still_cannot_close():
    """Market-level slices convict; a sport-level slice pools every market
    and closing it would veto clean books. That guard predates this change
    and must survive it."""
    src = __import__("inspect").getsource(lp.mine) if hasattr(lp, "mine") else ""
    if not src:
        import inspect
        src = "".join(inspect.getsource(lp).split("\n")[400:470])
    assert "CLOSE_GAP_REL" in src
    assert 't["market"] is not None' in src


def test_a_closure_says_which_bar_it_crossed():
    """A slice that closes on three points needs to explain itself, or the
    reading contradicts the documented five-point rule."""
    import inspect
    src = inspect.getsource(lp)
    assert "of the claim" in src, (
        "the reading must name the relative bar when the absolute one was "
        "not the thing that fired"
    )


# --- the Lab's ROI tile -----------------------------------------------------
def test_the_mixed_basis_headline_is_the_book_priced_number():
    fn = _fn("labPropCard")
    assert "const bookSeg = (m.segments || {}).book" in fn
    assert "mixed && bookSeg ? bookSeg" in fn, (
        "a mixed-basis headline must be the book segment, not the blend — "
        "the blend is ~99% naive by bet count"
    )


def test_the_mixed_tile_is_labelled_for_what_it_measures():
    fn = _fn("labPropCard")
    assert 'mixed ? "ROI vs real closes" : "Backtest ROI"' in fn, (
        "the tile has to say the number is market-relative, because the "
        "subtitle alone was not enough to stop it reading as an edge"
    )


def test_a_thin_book_sample_is_not_coloured_like_a_result():
    """277 bets is under the noise floor. It must go grey and say so
    rather than borrow confidence from 25,145 naive-priced ones."""
    fn = _fn("labPropCard")
    assert "under ${LAB_ROI_MIN_BETS}, noise not a result" in fn
    assert "tone: (naive || thin)" in fn
    # `thin` must be measured on the HEADLINE's own sample, not the blend's.
    assert "const thin = (headline.n_bets || 0) < LAB_ROI_MIN_BETS" in fn


def test_the_naive_warning_survives():
    """The one honest thing the old tile did."""
    fn = _fn("labPropCard")
    assert "NOT an edge over a book" in fn


def test_a_market_with_no_real_close_says_so_rather_than_showing_the_blend():
    fn = _fn("labPropCard")
    assert "no bet met a real close" in fn


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
