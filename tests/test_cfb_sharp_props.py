"""College props price the sharp book's pair first, as the NFL's do.

Ethan, 2026-09-07: "make sure you do the same exact work to make CFB
just as good."

The evaluator is shared — college props arrive through
`pipeline.price_props` and `betting.evaluate_prop`, the same step the
NFL uses — so the sharp path shipped for the NFL's props
(tests/test_prop_sharp_anchor.py) was college's the moment the pair
reached the prop. It did not: college buys its player markets per
event through `cfb_build.attach_player_quotes`, which read the shopped
field and dropped the sharp book with it, and `engine.cfb.props.
attach_lines` had no second dict to carry. Both carry it now, and the
touchdown board needs nothing: its fair has always been the median
de-vigged price across every book that quoted the player, the sharp
one included (`engine.devig.board_fair`).

Run directly: `python3 tests/test_cfb_sharp_props.py`
"""

import copy
import datetime as dt
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import cfb_build as B                                        # noqa: E402
from engine.cfb import props as P                            # noqa: E402
from engine.models import SportsbookLine                     # noqa: E402
from engine.sources import oddsapi as O                      # noqa: E402


def _payload():
    def book(key, title, over, under):
        return {"key": key, "title": title, "markets": [
            {"key": "player_rush_yds", "outcomes": [
                {"name": "Over", "description": "Runner A", "point": 75.5, "price": over},
                {"name": "Under", "description": "Runner A", "point": 75.5, "price": under}]}]}
    return {"bookmakers": [book("draftkings", "DraftKings", -110, -110),
                           book("pinnacle", "Pinnacle", -118, -104)]}


def _pull(sharp):
    now = dt.datetime(2026, 9, 12, 12, 0, tzinfo=dt.timezone.utc)
    games = [{"game_id": "g0", "home": "TOL", "away": "BGSU", "kickoff": "2026-09-12T20:00Z",
              "home_conference": "MAC", "away_conference": "MAC"}]
    priced = {"g0": {"event_id": "e0", "spread": (-3.0, -110, -110), "total": (50.5, -110, -110)}}
    real = O.fetch_event_odds
    O.fetch_event_odds = lambda *a, **k: (_payload(), O.Quota())
    try:
        return B.attach_player_quotes(games, priced, cache_only=True, now=now, cap=1,
                                      **({"sharp": sharp} if sharp is not None else {}))
    finally:
        O.fetch_event_odds = real


def test_the_pull_fills_the_sharp_pair_apart_from_the_shopped_field():
    sharp: dict = {}
    _scorers, lines, _note, _age = _pull(sharp)
    key = ("runner a", "rush_yds")
    assert [ln.book for ln in lines[key]] == ["DraftKings"], lines
    assert [(ln.book, ln.line, ln.over_odds, ln.under_odds) for ln in sharp[key]] == \
        [("Pinnacle", 75.5, -118, -104)], sharp
    # Without the out-parameter the pull is what it was: the same four
    # values back, the sharp book dropped with the field as before.
    _scorers, lines2, _note, _age = _pull(None)
    assert [ln.book for ln in lines2[key]] == ["DraftKings"]


def _slate_with(player, market, lines, sharp):
    from engine.data_loader import load_slate
    sl = load_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    prop = copy.deepcopy(sl.props[0])
    prop.player, prop.market = player, market
    prop.lines = [SportsbookLine("proxy", 70.5, -110, -110)]
    prop.sharp_lines = []

    class _Slate:
        props = [prop]
    return _Slate(), prop


def test_attach_lines_puts_the_pair_on_a_matched_prop_only():
    key = ("runner a", "rush_yds")
    lines = {key: [SportsbookLine("DraftKings", 75.5, -110, -110)]}
    sharp = {key: [SportsbookLine("Pinnacle", 75.5, -118, -104)]}
    slate, prop = _slate_with("Runner A", "rush_yds", lines, sharp)
    assert P.attach_lines(slate, lines, sharp=sharp) == (1, 1)
    assert [ln.book for ln in prop.lines] == ["DraftKings"]
    assert [ln.book for ln in prop.sharp_lines] == ["Pinnacle"]
    # No sharp dict: the field attaches and the pair stays empty.
    slate, prop = _slate_with("Runner A", "rush_yds", lines, sharp)
    assert P.attach_lines(slate, lines) == (1, 1) and prop.sharp_lines == []
    # A prop the books never quoted keeps its proxy and gets no pair,
    # even when the sharp book (oddly) quoted it.
    slate, prop = _slate_with("Runner B", "rush_yds", lines, sharp)
    sharp_b = {("runner b", "rush_yds"): [SportsbookLine("Pinnacle", 60.5, -118, -104)]}
    assert P.attach_lines(slate, lines, sharp=sharp_b) == (0, 1)
    assert prop.lines[0].book == "proxy" and prop.sharp_lines == []


def test_a_college_prop_with_the_pair_prices_sharp_first_through_the_shared_evaluator():
    from engine.data_loader import load_slate
    from engine.projection import build_projection
    from engine.betting import evaluate_prop
    from engine.odds import devig_two_way
    sl = load_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    prop = copy.deepcopy(sl.props[0])
    prop.lines = [SportsbookLine("DraftKings", 90.5, 100, -125)]
    prop.sharp_lines = [SportsbookLine("Pinnacle", 90.5, -118, -104)]
    game, opp = sl.game_for(prop), sl.team(prop.opponent)
    rec = evaluate_prop(prop, build_projection(prop, game, opp), game=game, sport="cfb")
    fair_over, _ = devig_two_way(-118, -104)
    assert rec.sharp_anchored is True and abs(rec.hit_prob - round(fair_over, 4)) < 1e-9
    assert rec.reasons[0].startswith("Sharp anchor"), rec.reasons[0]


def test_the_build_threads_the_pair_from_the_pull_to_the_props():
    src = inspect.getsource(B.main)
    assert "sharp_prop_lines: dict = {}" in src
    i = src.index("attach_player_quotes(games, priced, cache_only=not args.odds")
    assert "sharp=sharp_prop_lines" in src[i:i + 200], src[i:i + 200]
    j = src.index("_cfbprops.attach_lines(_prop_slate, prop_lines")
    assert "sharp=sharp_prop_lines" in src[j:j + 150], src[j:j + 150]
    # The touchdown board's fair already reads every book, the sharp one
    # included — nothing to add there.
    from engine import devig
    assert "MEDIAN" in inspect.getsource(devig.board_fair).upper()


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
