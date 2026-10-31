"""Every NBA alternate line meets the market, the one-way ones too
(engine/nba/pipeline.rung_probs; Ethan, 2026-10-29: "Ok keep going", after
"think like a pro sports better").

A ladder rung quoted both ways was always clamped toward its own de-vigged
price. A rung quoted one way only (the "15+ points" ladders) carried the
model's raw number, and Most Likely ranks by chance: a model running a
little low read every over on those ladders under the market's view, so
the floor turned them away and the unders took the seats; a model running
high would have seated them on numbers nothing had checked. What these
hold:

  * the main line's de-vigged price reads back as a mean on the stat's own
    curve (`prob.implied_mean`), the curve that prices every rung;
  * a one-way rung is clamped toward the market's number there, at the
    main line's weight, and killed past the same gap;
  * a number some book quotes both ways is read off that quote, whichever
    book came first; with no main price, the model's number, as before;
  * the board's rows hand the main line's price over.

Run directly: `python3 tests/test_every_nba_alternate_line_meets_the_market.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import hoops                                                    # noqa: E402
from engine.nba import pipeline as P                                        # noqa: E402
from engine.nba.prob import (CLAMP_KILL_DIFF, devig, humility_clamp,          # noqa: E402
                             implied_mean, p_over)

TUNE = hoops.NBA
STEADY = [30, 31, 29, 32, 30, 31, 30, 29, 31, 30]


def _ln(line, over, under=0, book="DraftKings"):
    return {"book": book, "line": line, "over_odds": over, "under_odds": under}


def test_the_main_price_reads_back_as_a_mean_on_our_own_curve():
    assert abs(implied_mean("pts", 22.5, 0.5) - 22.5) < 0.01, "an even price is the line itself"
    for stat, line, q in (("pts", 22.5, 0.60), ("pts", 22.5, 0.40), ("reb", 7.5, 0.55),
                          ("ast", 4.5, 0.45), ("fg3m", 2.5, 0.52), ("pra", 35.5, 0.58)):
        mean = implied_mean(stat, line, q)
        assert mean is not None, (stat, line, q)
        assert abs(p_over(stat, mean, line, TUNE) - q) < 0.002, (stat, line, q, mean)
    assert implied_mean("pts", 22.5, 0.65) > implied_mean("pts", 22.5, 0.55), "a dearer over, a higher mean"
    assert implied_mean("pts", 22.5, 0.995) is None and implied_mean("pts", 0, 0.5) is None


def test_a_one_way_rung_is_pulled_toward_the_market_at_the_main_lines_weight():
    proj, w = 20.0, 0.45
    mean = implied_mean("pts", 22.5, 0.5)
    got = P.rung_probs("pts", proj, [_ln(17.5, -250)], w, TUNE, main_line=22.5, main_over=0.5)
    p_model = p_over("pts", proj, 17.5, TUNE)
    p_mkt = p_over("pts", mean, 17.5, TUNE)
    assert p_mkt - p_model <= CLAMP_KILL_DIFF, "inside the clamp's tolerance, so priced"
    want, _ = humility_clamp(p_model, p_mkt, w)
    assert abs(got["17.5"] - round(want, 4)) < 1e-9, (got, want)
    assert p_model < got["17.5"] < p_mkt, "the market pulls a low model up toward it"
    # And a high model down: the same rung under a main line priced 40% over.
    low = implied_mean("pts", 22.5, 0.40)
    hi = P.rung_probs("pts", 23.0, [_ln(17.5, -250)], w, TUNE, main_line=22.5, main_over=0.40)
    assert p_over("pts", low, 17.5, TUNE) < hi["17.5"] < p_over("pts", 23.0, 17.5, TUNE), hi


def test_a_one_way_rung_far_from_the_market_is_left_out():
    # The model at 16 against a market that reads 22.5: the 17.5 rung is
    # 38% over to us and 77% to them. On a main line that is a kill; on a
    # rung it is no number, so the board cannot seat it.
    assert abs(p_over("pts", 16.0, 17.5, TUNE) - p_over("pts", implied_mean("pts", 22.5, 0.5), 17.5, TUNE)) \
        > CLAMP_KILL_DIFF
    assert P.rung_probs("pts", 16.0, [_ln(17.5, -250)], 0.45, TUNE, main_line=22.5, main_over=0.5) == {}


def test_a_two_way_quote_is_its_own_market_and_no_main_price_is_the_model():
    two = [_ln(17.5, -230, 180)]
    assert P.rung_probs("pts", 20.0, two, 0.45, TUNE, main_line=22.5, main_over=0.5) == \
        P.rung_probs("pts", 20.0, two, 0.45, TUNE), "a rung quoted both ways reads its own price"
    raw = P.rung_probs("pts", 20.0, [_ln(17.5, -250)], 0.45, TUNE)
    assert abs(raw["17.5"] - p_over("pts", 20.0, 17.5, TUNE)) < 1e-9, raw
    for bad in ((None, 0.5), (22.5, None), ("x", 0.5), (22.5, 0.999)):
        got = P.rung_probs("pts", 20.0, [_ln(17.5, -250)], 0.45, TUNE, main_line=bad[0], main_over=bad[1])
        assert got == raw, (bad, got)


def test_a_number_quoted_both_ways_anywhere_reads_that_quote():
    one_then_two = [_ln(17.5, -250), _ln(17.5, -230, 180, "FanDuel")]
    got = P.rung_probs("pts", 20.0, one_then_two, 0.45, TUNE, main_line=22.5, main_over=0.5)
    mkt, _ = devig(-230, 180)
    want, _ = humility_clamp(p_over("pts", 20.0, 17.5, TUNE), mkt, 0.45)
    assert abs(got["17.5"] - round(want, 4)) < 1e-9, (got, want)
    first = [_ln(17.5, -230, 180), _ln(17.5, -300, 240, "FanDuel")]
    assert P.rung_probs("pts", 20.0, first, 0.45, TUNE) == P.rung_probs("pts", 20.0, first[:1], 0.45, TUNE), \
        "two books both ways: the first, as it always read"


def test_the_board_hands_the_main_price_over():
    prop = {"player": "A Guard", "team": "BOS", "opponent": "NYK", "market": "pts", "line": 19.5,
            "over_odds": -110, "under_odds": -110, "spread": -3.0, "is_starter": True,
            "minutes": list(STEADY), "values": [round(m * 0.65, 1) for m in STEADY]}
    alts = [_ln(14.5, -400)]
    row = P.shared_recommendations([prop], {}, {}, tune=TUNE, alt_map={("A Guard", "pts"): alts})[0]
    q_over = row["fair_prob"] if row["side"] == "OVER" else 1.0 - row["fair_prob"]
    w = P.evaluate_prop(prop, TUNE)["w"]
    want = P.rung_probs("pts", float(row["projection"]), alts, w, TUNE, main_line=19.5, main_over=q_over)
    assert row["rung_probs"] == want, (row["rung_probs"], want)
    raw = P.rung_probs("pts", float(row["projection"]), alts, w, TUNE)
    assert row["rung_probs"] != raw, "the row's rung is clamped, not the raw model"


def test_the_lean_report_counts_the_one_way_rungs():
    import nbalean
    doc = {"recommendations": [
        {"player": "A", "market": "pts", "alt_lines": [_ln(14.5, -400), _ln(14.5, -380, 290, "FanDuel"),
                                                       _ln(17.5, -250), _ln(17.5, -240)]},
        {"player": "B", "market": "reb", "alt_lines": [_ln(5.5, -300), _ln("bad", -110)]}]}
    assert nbalean.ladder_shape(doc) == {"rungs": 3, "one_way": 2}
    assert nbalean.ladder_shape({}) == {"rungs": 0, "one_way": 0}


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
