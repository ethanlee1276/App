"""Two panels that answer "is this thing working?" before anything else.

Ethan, 2026-08-20: "Nobody visiting for the first time can tell in ten
seconds whether the model is good."

The cause was never a shortage of measurement — it was a surplus.
Calibration by market and horizon, CLV coverage, the hypothesis lab,
restated performance, blind-spot patterns: all honest, all already
computed, each on its own page answering its own narrow question. Nowhere
did the site simply say what happened.

So: five numbers and one picture on the Record page, four numbers and a
histogram on the meme record. Both read data that already existed; the
only engine change in either is the meme distribution, because a median
alone cannot show shape.

THE GATE IS THE POINT, and it is what separates this from a marketing
panel. A panel built to persuade is exactly the one that would turn a 1-0
record into "landed 100%". Both refuse below their sample threshold —
30 graded picks (engine/ledger.MIN_GRADED_FOR_SIGNAL) and 20 followable
calls — and say so instead.

EVERY SENTENCE IS DERIVED. "Claims 3.5 points more than it lands" is a
subtraction, not a phrase someone typed. Copy that is written by hand
drifts into optimism the numbers do not support; copy that is computed
cannot.

Measured on a populated fixture (247 graded, 40 meme calls):

    claimed 58.6%  landed 55.1%  CLV +0.34  net -4.12u
    "The model claims 3.5 points more than it lands, across 247 graded
     picks."
    "Of 40 calls we could follow, the median peaked +31.0% and ended
     -83.0% — giving back 114 points between its best moment and its
     last one. 3 went to zero and stayed there; they are counted here,
     not dropped."

Run directly: `python3 tests/test_verdict.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import memeledger as ml                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _fn(name):
    """The whole function, brace-matched.

    Slicing to the first `\n}\n` truncated `memeVerdictHTML` at a nested
    arrow function and reported half its body missing — a test failing on
    its own reader rather than on the code.
    """
    i = APP.index(f"function {name}(")
    j = APP.index("{", i)
    depth, k = 0, j
    while k < len(APP):
        if APP[k] == "{":
            depth += 1
        elif APP[k] == "}":
            depth -= 1
            if depth == 0:
                return APP[i:k + 1]
        k += 1
    raise AssertionError(f"unbalanced braces reading {name}")


# --- the sports verdict ----------------------------------------------------

def test_the_verdict_leads_the_record_page():
    """Below the fold it is another panel; above everything it is the
    answer. `receipts` is the page's first room."""
    assert "const receipts = verdict + edgePanel" in APP, \
        "the verdict no longer leads the Record page"


def test_it_refuses_a_verdict_on_a_thin_book():
    fn = _fn("recordVerdictHTML")
    assert "const thin = settled < need" in fn
    assert "Too early to call" in fn
    # and the reading must be gated on it, not printed anyway
    assert re.search(r"\$\{thin \?", fn), \
        "the thin branch no longer suppresses the verdict sentence"


def test_the_threshold_comes_from_the_engine_not_a_guess():
    """`min_graded` rides in the payload from MIN_GRADED_FOR_SIGNAL. A
    number retyped in the front end is a number that drifts."""
    fn = _fn("recordVerdictHTML")
    assert "src.min_graded" in fn, \
        "the gate no longer reads the engine's own threshold"
    led = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    assert "MIN_GRADED_FOR_SIGNAL = 30" in led


def test_claimed_and_landed_are_population_weighted():
    """An unweighted mean of bucket midpoints describes the BUCKETS, not
    the book: one 95% bucket holding two bets would count as much as a
    55% bucket holding four hundred."""
    fn = _fn("recordVerdictHTML")
    assert "b.predicted * b.n" in fn and "b.actual * b.n" in fn, \
        "claimed/landed stopped weighting by bucket population"
    assert "/ calN" in fn


def test_the_reading_is_computed_from_the_numbers_above_it():
    fn = _fn("recordVerdictHTML")
    for phrase in ("claims ${gap.toFixed(1)} points more than it",
                   "lands ${Math.abs(gap).toFixed(1)} points more than"):
        assert phrase in fn, f"the derived sentence changed shape: {phrase}"
    # both directions exist, so an under-claiming model is described too
    assert "under-confident" in fn


def test_an_over_claim_is_never_described_as_good_news():
    fn = _fn("recordVerdictHTML")
    flat = " ".join(fn.split())
    i = flat.index("claims ${gap.toFixed(1)} points more")
    assert "the thing to fix" in flat[i:i + 300], \
        "an over-claim lost its plain reading"


# --- the meme verdict ------------------------------------------------------

def test_the_distribution_buckets_are_wider_where_precision_is_useless():
    """A linear histogram over meme returns spends most of its bars on the
    stretch between "lost everything" and "lost most of it"."""
    assert ml.DIST_EDGES[0] == -0.80 and ml.DIST_EDGES[-1] == 10.0
    assert len(ml.DIST_LABELS) == len(ml.DIST_EDGES) + 1


def test_the_distribution_counts_every_call_it_is_given():
    vals = [-0.99, -0.9, -0.85, -0.4, -0.05, 0.3, 1.2, 4.0, 25.0]
    d = ml.distribution(vals)
    assert sum(b["n"] for b in d) == len(vals), \
        "a value fell between two buckets and was lost"
    assert d[0]["n"] == 3, "the ≤-80% bucket is not catching total losses"
    assert d[-1]["n"] == 1, "the open top bucket is not catching a 25x"


def test_a_missing_value_is_dropped_not_counted_as_zero():
    """A call with no price is not a call that went nowhere."""
    d = ml.distribution([None, None, 0.5])
    assert sum(b["n"] for b in d) == 1


def test_the_path_summary_carries_both_shapes():
    """Peak and last are different facts, which is the whole reason the
    ledger keeps a path at all."""
    src = open(os.path.join(ROOT, "engine", "memeledger.py"), encoding="utf-8").read()
    assert '"dist_peak": distribution(' in src
    assert '"dist_last": distribution(' in src


def test_the_meme_verdict_refuses_a_thin_book_too():
    fn = _fn("memeVerdictHTML")
    assert "MEME_MIN_CALLS" in fn and "Too early to call" in fn
    assert "const MEME_MIN_CALLS = 20;" in APP


def test_the_meme_verdict_counts_the_coins_that_vanished():
    """The survivorship bug this ledger was written to prevent, guarded at
    the display layer too: a record that drops its dead coins is a
    different record."""
    fn = _fn("memeVerdictHTML")
    assert "r.gone" in fn, "the gone count left the panel"
    # Whitespace-normalised: the phrase wraps across a source line inside
    # the template literal, so a raw substring search misses copy that is
    # plainly there. The claim is what matters, not where the line broke.
    flat = " ".join(fn.split())
    assert "counted here, not dropped" in flat, \
        "the record no longer says the dead coins are kept"


def test_the_meme_verdict_says_what_it_is_not():
    fn = _fn("memeVerdictHTML")
    flat = " ".join(fn.split())
    for phrase in ("not a return anyone", "slippage", "Most memecoins go to zero"):
        assert phrase in flat, f"the honesty note lost: {phrase}"


def test_both_panels_share_one_tile_style():
    """Two panels answering the same question should not look like two
    products. They share `.rv-tile`; only the grid track count differs."""
    fn = _fn("memeVerdictHTML")
    assert 'class="rv-tile' in fn
    assert ".md-tiles { grid-template-columns: repeat(4" in CSS
    assert ".rv-tiles {" in CSS


def test_the_panels_fold_to_two_columns_on_a_phone():
    """Five tiles across a 390px screen is unreadable."""
    i = CSS.index(".rv-tiles {")
    assert "repeat(5," in CSS[i:i + 200]
    phone = CSS[CSS.index("@media (max-width: 900px)", i):]
    assert "repeat(2, minmax(0, 1fr))" in phone[:900]


def test_a_full_season_record_does_not_wrap_its_own_number():
    """Measured at 1280px — the width the renders are drawn at — a record
    of "135-112-0" wrapped its last digit onto a line of its own. It only
    appears on a book with three-digit counts, which is why nothing caught
    it: the container's journal holds one bet.

    THE OBVIOUS FIX IS BANNED AND THIS IS THE SECOND TIME. `white-space:
    nowrap` on `.tile .v` was my first attempt; test_number_type failed it
    with a note saying it had already been tried, and that it turns a wrap
    into a clip — an unbreakable value ran 56px out of a 320px phone tile
    and lost its "pts" entirely. Two lines on a phone is fine; losing the
    unit is not.

    So the break is prevented in the STRING: U+2011 NON-BREAKING HYPHEN
    between the counts. It stops the score splitting and leaves the
    legitimate number/unit break alone."""
    assert ".rec-kpis .tile .v { white-space: nowrap; }" not in CSS, \
        "nowrap is back on the shared tile value — see test_number_type"
    assert "\\u2011${o.losses}\\u2011" in APP, \
        "the record's separators are breakable hyphens again"
    i = CSS.index(".rec-kpis .tile.lead .v {\n  font-size: clamp(")
    assert "clamp(var(--fs-2xl)" in CSS[i:i + 140], \
        "the lead number lost its floor and will overflow instead of wrapping"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print("all good" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
