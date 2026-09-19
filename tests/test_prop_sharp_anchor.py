"""Player props price a sharp book's pair first, where one exists.

Ethan, 2026-09-07: "I want all of that tuned in exactly how you just
did" — props and touchdown props along with the game markets.

The game markets on every board price a soft book's number against
the sharp book's de-vigged pair and stake that disagreement; the model
card is information. The player props had no sharp path at all:
`oddsapi.parse_event_lines` dropped the sharp book on purpose — nobody
here can bet it — and nothing read the pair it dropped. Now
`parse_event_sharp_lines` reads it, the pair rides on
`Prop.sharp_lines`, and `betting.evaluate_prop` prices the shopped soft
quote against the sharp pair AT THE SAME LINE when there is one. Where
the sharp book quoted nothing, the model card prices as it always has.

Run directly: `python3 tests/test_prop_sharp_anchor.py`
"""

import copy
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.betting import evaluate_prop, sharp_anchor_for, Recommendation  # noqa: E402
from engine.gamebets import SHARP_MIN_EV, SHARP_SUSPECT_EV, SHARP_MAX_EV  # noqa: E402
from engine.models import SportsbookLine                     # noqa: E402
from engine.odds import american_to_prob, devig_two_way      # noqa: E402
from engine.quality import tier_min_edge                      # noqa: E402
from engine.sources import oddsapi                            # noqa: E402


def _event():
    def book(key, title, over, under, point=90.5):
        return {"key": key, "title": title, "markets": [
            {"key": "player_rush_yds", "outcomes": [
                {"name": "Over", "description": "Josh Jacobs", "point": point, "price": over},
                {"name": "Under", "description": "Josh Jacobs", "point": point, "price": under}]}]}
    return {"id": "e1", "home_team": "Green Bay Packers", "away_team": "Chicago Bears",
            "bookmakers": [book("draftkings", "DraftKings", -110, -110),
                           book("fanduel", "FanDuel", -105, -115),
                           book("pinnacle", "Pinnacle", -118, -104)]}


# --- the parser --------------------------------------------------------------
def test_the_sharp_pair_is_read_apart_from_the_shopped_field():
    key = ("josh jacobs", "rush_yds")
    soft = oddsapi.parse_event_lines(_event())
    sharp = oddsapi.parse_event_sharp_lines(_event())
    assert {ln.book for ln in soft[key]} == {"DraftKings", "FanDuel"}, soft
    assert [(ln.book, ln.line, ln.over_odds, ln.under_odds) for ln in sharp[key]] == \
        [("Pinnacle", 90.5, -118, -104)], sharp
    # No sharp book in the payload: an empty index, not a missing key error.
    ev = _event(); ev["bookmakers"] = ev["bookmakers"][:2]
    assert oddsapi.parse_event_sharp_lines(ev) == {}


def test_the_attach_step_carries_the_pair_onto_the_prop():
    src = inspect.getsource(oddsapi.apply_odds_to_slate)
    assert "parse_event_sharp_lines(payload, cfg[\"markets\"])" in src
    assert "sharp_index.setdefault(k, []).extend(lines)" in src
    assert "prop.sharp_lines = list(sharp_index.get(" in src
    # …and only beside real lines: a prop with no soft quote has nothing
    # to price against the pair.
    i = src.index("prop.lines = lines")
    assert "prop.sharp_lines" in src[i:i + 300]


# --- the anchor --------------------------------------------------------------
def _lines(*quotes):
    return [SportsbookLine(b, l, o, u) for b, l, o, u in quotes]


def test_the_anchor_needs_the_same_line_and_a_soft_quote_inside_the_bands():
    sharp = _lines(("Pinnacle", 90.5, -118, -104))
    fair_over, fair_under = devig_two_way(-118, -104)
    # DraftKings pays even money on the over the sharp book makes 51.5%:
    # +3.0% EV, the over, at DraftKings.
    got = sharp_anchor_for(_lines(("DraftKings", 90.5, 100, -125),
                                  ("FanDuel", 90.5, -108, -112)), sharp, 90.5)
    side, book, odds, fair, ev = got
    assert (side, book, odds) == ("OVER", "DraftKings", 100)
    assert abs(fair - fair_over) < 1e-9 and abs(ev - (fair_over * 2.0 - 1.0)) < 1e-9
    assert SHARP_MIN_EV <= ev <= SHARP_SUSPECT_EV
    # The under side when that is where the soft book is generous: the
    # sharp book makes the under 48.5%, and +112 on it is +2.8% EV.
    got = sharp_anchor_for(_lines(("DraftKings", 90.5, -130, 112)), sharp, 90.5)
    assert got[0] == "UNDER" and got[2] == 112 and abs(got[3] - fair_under) < 1e-9
    assert SHARP_MIN_EV <= got[4] <= SHARP_SUSPECT_EV
    # A different line is no comparison at all.
    assert sharp_anchor_for(_lines(("DraftKings", 90.5, 100, -125)), sharp, 91.5) is None
    assert sharp_anchor_for(_lines(("DraftKings", 91.5, 100, -125)), sharp, 91.5) is None
    # Under the floor: nothing to take.
    assert sharp_anchor_for(_lines(("DraftKings", 90.5, -108, -112)), sharp, 90.5) is None
    # Past the ceiling: a broken price, not a bet.
    assert sharp_anchor_for(_lines(("DraftKings", 90.5, 140, -170)), sharp, 90.5) is None
    assert fair_over * 2.4 - 1.0 > SHARP_MAX_EV
    # A one-sided soft market can still anchor its one side.
    got = sharp_anchor_for(_lines(("DraftKings", 90.5, 100, 0)), sharp, 90.5)
    assert got is not None and got[0] == "OVER"
    # A one-sided SHARP quote cannot de-vig and anchors nothing.
    assert sharp_anchor_for(_lines(("DraftKings", 90.5, 100, -125)),
                            _lines(("Pinnacle", 90.5, -118, 0)), 90.5) is None
    # No sharp pair at all.
    assert sharp_anchor_for(_lines(("DraftKings", 90.5, 100, -125)), [], 90.5) is None


# --- the evaluator -----------------------------------------------------------
def _jacobs(soft, sharp):
    """The sample slate's first prop — Josh Jacobs rushing yards — with
    the soft field and the sharp pair supplied, evaluated end to end."""
    from engine.data_loader import load_slate
    from engine.projection import build_projection
    sl = load_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    prop = copy.deepcopy(sl.props[0])
    assert prop.player == "Josh Jacobs" and prop.market == "rush_yds"
    prop.lines = _lines(*soft)
    prop.sharp_lines = _lines(*sharp)
    game, opp = sl.game_for(prop), sl.team(prop.opponent)
    proj = build_projection(prop, game, opp)
    return evaluate_prop(prop, proj, game=game), prop, proj, game


def test_without_a_sharp_pair_the_model_card_is_exactly_what_it_was():
    rec, *_ = _jacobs([("DraftKings", 90.5, -110, -110), ("FanDuel", 90.5, -105, -115)], [])
    assert rec.sharp_anchored is False and rec.sharp_fair is None
    assert not any(r.startswith("Sharp anchor") for r in rec.reasons)
    # A sharp pair at ANOTHER line changes nothing either.
    rec2, *_ = _jacobs([("DraftKings", 90.5, -110, -110), ("FanDuel", 90.5, -105, -115)],
                       [("Pinnacle", 91.5, -118, -104)])
    assert rec2.sharp_anchored is False
    assert (rec2.side, rec2.book, rec2.odds, rec2.hit_prob, rec2.edge, rec2.grade) == \
        (rec.side, rec.book, rec.odds, rec.hit_prob, rec.edge, rec.grade)


def test_a_sharp_pair_at_the_shopped_line_prices_the_card():
    rec, prop, proj, game = _jacobs([("DraftKings", 90.5, 100, -125), ("FanDuel", 90.5, -108, -112)],
                                    [("Pinnacle", 90.5, -118, -104)])
    fair_over, _ = devig_two_way(-118, -104)
    assert rec.sharp_anchored is True
    assert (rec.side, rec.book, rec.odds, rec.line) == ("OVER", "DraftKings", 100, 90.5)
    # Probability is the sharp fair; "fair" is the soft price's implied;
    # the edge is the distance between them.
    assert abs(rec.hit_prob - round(fair_over, 4)) < 1e-9 and rec.sharp_fair == rec.hit_prob
    assert abs(rec.fair_prob - round(american_to_prob(100), 4)) < 1e-9
    assert abs(rec.edge - round(fair_over - american_to_prob(100), 4)) < 1e-9
    assert rec.reasons[0].startswith("Sharp anchor: this price implies 50%"), rec.reasons[0]
    assert rec.reasons[1].startswith("Model context: rates the over at"), rec.reasons[1]
    # Three points of edge is under Tier 2's bar: shown, not staked.
    assert rec.edge < tier_min_edge("rush_yds") and rec.grade == "Pass"
    # The board row carries the flags, and says the sharp book quoted it.
    from engine.pipeline import _rec_to_dict
    from engine.rules import apply_rules
    d = _rec_to_dict(rec, prop, apply_rules(rec, prop, game), proj)
    assert d["sharp_anchored"] is True and d["sharp_fair"] == rec.hit_prob and d["sharp_quoted"] is True


def test_a_wide_enough_gap_on_a_favourite_is_a_pick_and_a_suspect_one_is_refused():
    """The same window as the game cards. Tier 2 needs 3.0 points of edge
    and the grade's edge points fill at 4.5; a sharp fair of 70% on the
    over against a soft −190 is 4.5 points and +6.9% EV — inside the
    7% suspect line — and the card stakes. Push the soft price to +115
    against a coin-flip fair and the gap is +10.7% EV: shown, refused."""
    picks = {}
    for soft in (-200, -190, -180, -170):
        rec, *_ = _jacobs([("DraftKings", 90.5, soft, 150)], [("Pinnacle", 90.5, -280, 215)])
        picks[soft] = (rec.sharp_anchored, rec.grade, round(rec.edge, 3), round(rec.ev_per_unit, 3))
    assert any(g != "Pass" for _a, g, _e, _v in picks.values()), picks
    assert all(a for a, *_ in picks.values()), picks
    rec, *_ = _jacobs([("DraftKings", 90.5, 115, -145)], [("Pinnacle", 90.5, -118, -104)])
    assert rec.sharp_anchored is True and rec.grade == "Pass" and rec.stake_units == 0.0
    assert rec.reasons[0].startswith("Gap too large to trust"), rec.reasons[0]
    assert rec.ev_per_unit > SHARP_SUSPECT_EV


def test_nothing_model_side_touches_a_sharp_card():
    """No haircut, no selection shrink, no calibration gate, no
    mis-posted-quote check against our own distribution — there is no
    model opinion in the number to correct."""
    src = inspect.getsource(evaluate_prop)
    assert "calibration_ok = anchored or is_reliable(sport, prop.market)" in src
    i = src.index("if anchored:")
    j = src.index("else:", i)
    assert "temper_edge(" not in src[i:j] and "apply_selection(" not in src[i:j]
    assert "temper_edge(" in src[j:j + 400] and "apply_selection(" in src[j:j + 400]
    assert "or anchored\n" in src.split("prices_line = (")[1][:200]
    # The dataclass carries the two fields with quiet defaults.
    r = Recommendation.__dataclass_fields__
    assert r["sharp_anchored"].default is False and r["sharp_fair"].default is None


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
