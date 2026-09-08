"""Every credibility refusal on the likelihood board names its own number.

Ethan, 2026-09-08, pasting the NFL census off the droplet:

    {'under the likelihood floor': 212,
     'heavier than -250 — chalk, not a pick': 4,
     'listed QUESTIONABLE — held until inactives confirm': 1,
     'disagrees with the market by more than we credit': 58,
     'the model and the market disagree by more than we credit': 40,
     'no real book price': 48}

Two lines, ninety-eight rows, and the same words in a different order.
They were never the same test — one asks whether the number the board
SHOWS is near the book, the other asks the engine's question of the
engine's RAW claim before the market shrink (`engine_credible`, the
Gelof guard) — but nothing in either sentence said so. A census exists
to answer one question, WHICH bar emptied the board, and on the two
biggest buckets after the floor it could not.

Three questions are asked of three probabilities, and each refusal now
names the one it judged:

  * the SHOWN probability — what the card prints, after the shrink or
    after the mixture recomputed it;
  * the model's OWN READ — carried on a row that RANKS on a market
    number, where the model's `win_prob` is still the card;
  * the RAW claim, before the shrink, which is the only place a
    disagreement between ten and twenty points is still visible.

Run directly: `python3 tests/test_census_labels.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import likely as K                                  # noqa: E402

SHOWN = "the shown probability disagrees with the market by more than we credit"
READ = "the model's own read disagrees with the market by more than we credit"
RAW = "the raw model claim, before the shrink, disagrees with the market by more than we credit"


def _row(**kw):
    row = {"market": "moneyline", "side": "home", "odds": -110,
           "book": "FanDuel", "model_prob": 0.62, "implied_prob": 0.60,
           "fair_prob": 0.60, "engine_raw_prob": 0.62}
    row.update(kw)
    return row


# --- the three questions, each answered in its own words ---------------------
def test_the_shown_probability_is_refused_under_its_own_name():
    """The number the card prints, twenty points off the book."""
    assert K.admissible(_row(model_prob=0.85, implied_prob=0.60,
                             engine_raw_prob=0.85)) == SHOWN


def test_a_market_ranked_rows_own_read_is_refused_under_its_own_name():
    """The row sorts on the market's fair; the model's read is still the
    card, and a card twenty points off the book is our error wherever
    the row was sorted."""
    got = K.admissible(_row(prob_source="market", win_prob=0.85,
                            model_prob=0.61, implied_prob=0.60,
                            engine_raw_prob=0.61))
    assert got == READ, got


def test_the_raw_claim_before_the_shrink_is_refused_under_its_own_name():
    """The Gelof row: 73% shown is what 96% becomes after being shrunk
    toward a market number that cannot be a real price. The shown gap is
    ten points; the raw gap is thirty-three."""
    got = K.admissible({"model_prob": 0.73, "side": "under", "odds": -200,
                        "book": "theScore Bet", "implied_prob": 0.63,
                        "engine_raw_prob": 0.963, "fair_prob": 0.63})
    assert got == RAW, got


def test_a_credible_row_is_refused_by_none_of_them():
    """`admissible` answers with the reason it refused, and "" when it
    did not — so an admissible row is the empty string, not True."""
    assert K.admissible(_row()) == ""


# --- what the census can print, read as a whole ------------------------------
def _labels():
    """Every refusal string the module can put in the census."""
    src = open(os.path.join(ROOT, "engine", "likely.py"), encoding="utf-8").read()
    out = set()
    for m in re.finditer(r'_refuse\(census,\s*"([^"]+)"', src):
        out.add(m.group(1))
    # `admissible` returns its reason as a plain string; `build` censuses it.
    body = src[src.index("def admissible("):src.index("\ndef ", src.index("def admissible(") + 10)]
    for m in re.finditer(r'^\s+return (?:f?)"([^"]+)"', body, re.M):
        out.add(m.group(1))
    return out


def test_every_disagreement_label_says_which_number_disagreed():
    """The defect itself: two labels that a reader cannot tell apart.
    Each one names the probability it judged, so the census answers the
    question it exists for."""
    said = {lab for lab in _labels() if "disagree" in lab}
    assert len(said) >= 3, said
    for lab in said:
        assert re.search(r"\bshown\b|\bown read\b|\braw\b", lab), \
            f"a disagreement refusal that does not say which number: {lab!r}"
    # And the pair that read alike is gone in both directions.
    assert "disagrees with the market by more than we credit" not in said
    assert "the model and the market disagree by more than we credit" not in said


def test_no_two_refusals_share_a_label():
    labels = list(_labels())
    assert len(labels) == len(set(labels))
    assert {SHOWN, READ, RAW} <= set(labels), sorted(labels)


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
