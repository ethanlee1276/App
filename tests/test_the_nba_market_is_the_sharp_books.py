"""The NBA board's market is the sharp book's price when it quoted the prop
(engine/nba/prob.sharp_fair; Ethan, 2026-10-29: "think like a pro sports
better ... use the data and resources we have").

The football boards price a prop against the sharp book first
(`betting.sharp_anchor_for`). The NBA build pulled the same book's quotes
(`oddsapi.SHARP_BOOKS`) and dropped them, so its humility clamp leaned on
the other books' best two prices: a pair no single book offers, and the
one most moved by whichever book is slowest. What these hold:

  * the sharp book's two-way quote at the line, vig out, is the market;
    a quote at a nearby number is read across through the stat's own
    curve, and one too far away, one-sided or holding too much is not
    read at all;
  * the side, the clamp and the edge are read against it, while the price
    taken is still the other books' best; the card says which market it
    trusted and what the other books said;
  * on a ladder, the sharp book's own two-way rung is the market for that
    rung;
  * the build hands the sharp quotes over.

Run directly: `python3 tests/test_the_nba_market_is_the_sharp_books.py`
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import hoops                                                    # noqa: E402
from engine.nba import pipeline as P                                        # noqa: E402
from engine.nba.prob import (SHARP_SHIFT_DEFAULT, SHARP_SHIFT_MAX, devig,     # noqa: E402
                             humility_clamp, implied_mean, p_over, sharp_fair)

TUNE = hoops.NBA
STEADY = [30, 31, 29, 32, 30, 31, 30, 29, 31, 30]


def _ln(line, over, under=0, book="Pinnacle"):
    return {"book": book, "line": line, "over_odds": over, "under_odds": under}


def _prop(**kw):
    p = {"player": "A Guard", "team": "BOS", "opponent": "NYK", "market": "pts", "line": 19.5,
         "over_odds": -110, "under_odds": -110, "book": "DraftKings", "spread": -3.0,
         "is_starter": True, "minutes": list(STEADY), "values": [round(m * 0.65, 1) for m in STEADY]}
    p.update(kw)
    return p


def test_the_quote_at_the_line_is_the_market():
    p, at, book = sharp_fair("pts", 22.5, [_ln(22.5, -125, 105)])
    assert abs(p - round(devig(-125, 105)[0], 4)) < 1e-9 and at == 22.5 and book == "Pinnacle"
    # The same number wins over a nearer-looking one elsewhere.
    assert sharp_fair("pts", 22.5, [_ln(23.5, -110, -110), _ln(22.5, -125, 105)])[1] == 22.5


def test_a_nearby_number_is_read_across_through_the_curve():
    q = devig(-110, -110)[0]
    p, at, _book = sharp_fair("pts", 22.5, [_ln(23.5, -110, -110)])
    want = p_over("pts", implied_mean("pts", 23.5, q), 22.5, TUNE)
    assert at == 23.5 and abs(p - round(want, 4)) < 1e-9, (p, want)
    assert p > q, "a lower number is likelier to be cleared"
    far = SHARP_SHIFT_MAX["pts"] + 0.5
    assert sharp_fair("pts", 22.5, [_ln(22.5 + far, -110, -110)]) is None, "too far to read across"
    assert sharp_fair("reb", 7.5, [_ln(7.5 + SHARP_SHIFT_DEFAULT + 1.0, -110, -110)]) is None
    assert sharp_fair("reb", 7.5, [_ln(8.5, -110, -110)]) is not None


def test_a_quote_that_is_no_market_is_not_read():
    for bad in ([_ln(22.5, -110)],                  # one side only
                [_ln(22.5, -150, -150)],            # holding 20%
                [_ln(22.5, 120, 110)],              # holding less than nothing
                [_ln(22.5, 50, -110)],              # not a price
                [_ln("x", -110, -110)], [], None):
        assert sharp_fair("pts", 22.5, bad) is None, bad


def test_the_card_reads_the_sharp_book_and_shops_the_others():
    soft = P.evaluate_prop(_prop(), TUNE)
    assert soft["market_source"] == "books" and not soft["anchor_note"]
    assert abs(soft["p_market"] - 0.5) < 1e-9
    sharp = P.evaluate_prop(_prop(sharp_lines=[_ln(19.5, -118, -102)]), TUNE)
    fair_over = devig(-118, -102)[0]
    assert sharp["market_source"] == "sharp", sharp
    want = fair_over if sharp["side"] == "OVER" else 1.0 - fair_over
    assert abs(sharp["p_market"] - round(want, 4)) < 1e-4, (sharp["p_market"], want)
    assert sharp["odds"] == -110 and sharp["book"] == "DraftKings", "the price taken is still the shop's"
    assert "Pinnacle's price, vig out" in sharp["anchor_note"] and "50%" in sharp["anchor_note"], \
        sharp["anchor_note"]
    p_final, _ = humility_clamp(sharp["p_model"], sharp["p_market"], sharp["w"])
    assert abs(sharp["p_final"] - p_final) < 1e-9, "clamped toward the sharp book's number"


def test_the_side_is_chosen_against_the_sharp_book():
    soft = P.evaluate_prop(_prop(), TUNE)
    p_model_over = soft["p_model"] if soft["side"] == "OVER" else 1.0 - soft["p_model"]
    # A sharp price a little above the model's over: the model now sees
    # the under as the better side, as a pro reading that price would.
    q = min(0.9, p_model_over + 0.06)
    over = int(round(-100 * q / (1 - q))) if q > 0.5 else int(round(100 * (1 - q) / q))
    under = int(round(100 * q / (1 - q))) if q > 0.5 else int(round(-100 * (1 - q) / q))
    got = P.evaluate_prop(_prop(sharp_lines=[_ln(19.5, over - 5, under - 5)]), TUNE)
    assert got.get("side") == "UNDER", (got.get("side"), got.get("p_market"), p_model_over, over, under)


def test_the_sharp_rung_is_the_rungs_market():
    soft_rung = [_ln(17.5, -230, 180, "DraftKings")]
    sharp_rung = [_ln(17.5, -200, 165)]
    got = P.rung_probs("pts", 20.0, soft_rung, 0.45, TUNE, sharp_alts=sharp_rung)
    want, _ = humility_clamp(p_over("pts", 20.0, 17.5, TUNE), devig(-200, 165)[0], 0.45)
    assert abs(got["17.5"] - round(want, 4)) < 1e-9, (got, want)
    assert got != P.rung_probs("pts", 20.0, soft_rung, 0.45, TUNE)
    # A sharp quote at another number does not price this rung.
    assert P.rung_probs("pts", 20.0, soft_rung, 0.45, TUNE, sharp_alts=[_ln(18.5, -200, 165)]) == \
        P.rung_probs("pts", 20.0, soft_rung, 0.45, TUNE)


def test_the_row_says_which_market_it_trusted():
    rows = P.shared_recommendations([_prop(sharp_lines=[_ln(19.5, -118, -102)])], {}, {}, tune=TUNE)
    r = rows[0]
    assert r["market_source"] == "sharp", r
    assert any("Pinnacle's price, vig out" in x for x in r["reasons"]), r["reasons"]
    assert abs(r["books_fair"] - 0.5) < 1e-9, "what the other books said, for the side"
    plain = P.shared_recommendations([_prop()], {}, {}, tune=TUNE)[0]
    assert plain["market_source"] == "books" and not any("vig out" in x for x in plain["reasons"])


def test_the_lean_report_counts_the_props_the_sharp_book_priced():
    import nbalean
    doc = {"recommendations": [
        {"fair_prob": 0.52, "books_fair": 0.50, "market_source": "sharp"},
        {"fair_prob": 0.47, "books_fair": 0.50, "market_source": "sharp"},
        {"fair_prob": 0.50, "books_fair": 0.50, "market_source": "books"},
        {"fair_prob": None}]}
    got = nbalean.anchors(doc)
    assert got["props"] == 3 and got["sharp"] == 2 and abs(got["gap"] - 0.025) < 1e-9, got
    assert got["value"] == 0
    assert nbalean.anchors({}) == {"props": 0, "sharp": 0, "gap": None, "value": 0}


def test_the_build_hands_the_sharp_quotes_over():
    src = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    at = src.index('"sharp_lines": [{"book": ln.book, "line": ln.line,')
    assert 'getattr(prop, "sharp_lines", None)' in src[at:at + 300]
    pipe = (ROOT / "engine" / "nba" / "pipeline.py").read_text(encoding="utf-8")
    assert 'sharp_alts=(alt_sharp_map or {}).get((r["player"], r["market"]), [])' in pipe


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
