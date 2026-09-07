"""The Most Likely board judges a sharp-anchored prop on the model's number.

Ethan, 2026-09-07: "you said you did model work but i dont see any
changes for nfl in the edge bets or the most likley bets. it just shows
2 tight end reception props. there is no rushing props for running
backs or any recieving props for wr, that makes it feel like something
is off or irs broken."

It was broken, and by the sharp-anchor change itself. When the sharp
book quotes a prop two ways at the shopped line, `betting.evaluate_prop`
prices the card from that pair: `hit_prob` becomes the sharp book's
fair. A sharp line is hung where the sharp book thinks the coin is fair,
so that number is 50-53% for every prop it quotes — and `likely.from_prop`
read `hit_prob` against the 55% floor, refusing every anchored prop
before the model was consulted. What survived was whatever the sharp
book did NOT quote: two tight-end receptions rows.

Two fixes, pinned here:

  * the card's `raw_prob` is the MODEL's read of the side on an anchored
    card, not a second copy of the sharp fair (which also stops the
    calibration fitter learning the sharp book's calibration as ours);
  * the board judges an anchored row's floor on that number, shows the
    mixture as it always has, and keeps the sharp fair on the row.

Run directly: `python3 tests/test_likely_anchored_props.py`
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import likely as K                               # noqa: E402
from engine.betting import evaluate_prop                     # noqa: E402
from engine.models import SportsbookLine                     # noqa: E402
from engine.odds import devig_two_way                        # noqa: E402
from engine.statmath import prob_over                        # noqa: E402

#: The real fitted mixtures from 2026-08-30 (see tests/test_likely.py).
FITS = {
    "rush_yds": {"zero": [-0.04, 0.82], "sigma": 0.54},
    "rec_yds": {"zero": [-0.39, 0.61], "sigma": 0.60},
    "receptions": {"zero": [-0.82, 0.48], "sigma": 0.46},
}


def _always(_market):
    return True


def _row(**kw):
    """A published rush-yards row the way `pipeline._rec_to_dict` writes
    it. Projection 62 on a 45.5 line puts the mixture at 0.62 for
    rush_yds, and the 0.55 soft fair keeps that inside the credibility
    bar."""
    got = {"player": "A Back", "team": "DET", "opponent": "CHI",
           "market": "rush_yds", "market_label": "rush_yds", "side": "over",
           "line": 45.5, "book": "DK", "odds": -110, "has_market": True,
           "fair_prob": 0.55, "projection": 62.0, "ev_per_unit": 0.03,
           "reasons": ["because"], "recent_values": [40, 60, 55],
           "date": "2026-09-14",
           # The sharp book's fair at the line, and the model's read.
           "sharp_anchored": True, "sharp_fair": 0.515, "hit_prob": 0.515,
           "raw_prob": 0.64}
    got.update(kw)
    return got


def test_an_anchored_prop_is_judged_on_the_models_number_not_the_sharp_fair():
    census = {}
    row = K.from_prop(_row(), _always, fits=FITS, census=census)
    assert row is not None, census
    # The number shown is the mixture, as on every prop row; the sharp
    # fair travels with it so a reader can see both.
    assert row["prob_source"] == "mixture" and row["model_prob"] >= K.MIN_PROB
    assert row["sharp_anchored"] is True and row["sharp_fair"] == 0.515
    # The board's own raw number is the model's, not the sharp fair.
    assert row["raw_prob"] == 0.64 and row["engine_raw_prob"] == 0.64
    assert census == {}


def test_the_same_numbers_without_the_anchor_flag_are_under_the_floor():
    """The control: before the fix every anchored row took THIS path,
    because `hit_prob` was all `from_prop` read."""
    census = {}
    assert K.from_prop(_row(sharp_anchored=False), _always, fits=FITS,
                       census=census) is None
    assert census == {"under the likelihood floor": 1}


def test_an_anchored_prop_the_model_rates_low_is_still_refused():
    """The floor is not waived for anchored rows — it is asked of the
    model's number. A model at 50% on the side has nothing likely to
    say, whatever the sharp book thinks."""
    census = {}
    assert K.from_prop(_row(raw_prob=0.50), _always, fits=FITS,
                       census=census) is None
    assert census == {"under the likelihood floor": 1}
    # …and an anchored row with no model number recorded falls back to
    # `hit_prob` rather than crashing or passing for free.
    census = {}
    assert K.from_prop(_row(raw_prob=None), _always, fits=FITS,
                       census=census) is None
    assert census == {"under the likelihood floor": 1}


def _jacobs(soft, sharp):
    """The sample slate's Josh Jacobs rushing-yards prop, evaluated end
    to end with the soft field and the sharp pair supplied."""
    from engine.data_loader import load_slate
    from engine.projection import build_projection
    sl = load_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    prop = copy.deepcopy(sl.props[0])
    assert prop.player == "Josh Jacobs" and prop.market == "rush_yds"
    prop.lines = [SportsbookLine(b, l, o, u) for b, l, o, u in soft]
    prop.sharp_lines = [SportsbookLine(b, l, o, u) for b, l, o, u in sharp]
    game, opp = sl.game_for(prop), sl.team(prop.opponent)
    proj = build_projection(prop, game, opp)
    return evaluate_prop(prop, proj, game=game), prop, proj, game


def test_the_anchored_card_carries_the_models_read_as_raw_prob():
    rec, prop, proj, game = _jacobs(
        [("DraftKings", 90.5, 100, -125), ("FanDuel", 90.5, -108, -112)],
        [("Pinnacle", 90.5, -118, -104)])
    fair_over, _ = devig_two_way(-118, -104)
    assert rec.sharp_anchored is True and rec.side == "OVER"
    # hit_prob is the sharp fair, exactly as the anchor test pins…
    assert abs(rec.hit_prob - round(fair_over, 4)) < 1e-9
    # …and raw_prob is the MODEL's P(over 90.5) from its own projection.
    # The suite runs with an empty models sandbox, so no calibration
    # curve moves it and the normal tail is the whole number.
    model_over = prob_over(90.5, proj.mean, proj.std)
    assert abs(rec.raw_prob - model_over) < 1e-5, (rec.raw_prob, model_over)
    assert abs(rec.raw_prob - rec.hit_prob) > 0.01, "the two must be different numbers"
    # The under side: the model's number for the side taken.
    rec_u, _p, proj_u, _g = _jacobs([("DraftKings", 90.5, -130, 112)],
                                    [("Pinnacle", 90.5, -118, -104)])
    assert rec_u.sharp_anchored is True and rec_u.side == "UNDER"
    assert abs(rec_u.raw_prob - (1.0 - prob_over(90.5, proj_u.mean, proj_u.std))) < 1e-5
    # A card with no sharp pair is untouched: raw_prob is what it was.
    plain, _p, proj_p, _g = _jacobs([("DraftKings", 90.5, -110, -110)], [])
    assert plain.sharp_anchored is False
    assert abs(plain.raw_prob - (prob_over(90.5, proj_p.mean, proj_p.std)
                                 if plain.side == "OVER"
                                 else 1.0 - prob_over(90.5, proj_p.mean, proj_p.std))) < 1e-5


def test_the_board_row_built_from_the_card_reaches_the_shelf():
    """End to end: the card the evaluator writes, through the pipeline's
    row dict, into the board. Before the fix this row was refused."""
    from engine.pipeline import _rec_to_dict
    from engine.rules import apply_rules
    rec, prop, proj, game = _jacobs(
        [("DraftKings", 90.5, 100, -125), ("FanDuel", 90.5, -108, -112)],
        [("Pinnacle", 90.5, -118, -104)])
    d = _rec_to_dict(rec, prop, apply_rules(rec, prop, game), proj)
    assert d["sharp_anchored"] is True and d["hit_prob"] < K.MIN_PROB
    # The model side is well above the floor on this projection, and the
    # projection is used for the mixture, so the row survives — or is
    # refused only on grounds other than the floor.
    census = {}
    row = K.from_prop(d, _always, fits=FITS, census=census)
    assert "under the likelihood floor" not in census, census
    if row is not None:
        assert row["sharp_anchored"] is True and row["sharp_fair"] == rec.hit_prob


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
