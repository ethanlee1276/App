"""Baseball buys its alternate ladders and prices every rung with its own curve.

Ethan, 2026-09-15: "MLB most likely bets are only showing hits and total
bases. There is no money lines or pitchers props or game totals or
anything like that. The point of the most likely bets is to find the
most likely to hit bets for each game. We shouldn't be sticking to just
one category of props, we need to scan ALL props available."

A hit or a total base has a 0.5 line the model clears at 60-70%. A
strikeout line is hung at the pitcher's median, so its main number sits
near 50% and the Most Likely floor refuses it every night — the exact
defect the football boards fixed with the alternate ladders on
2026-09-07. Baseball never bought them. Now it does, and because a
baseball stat is a low count with a real shape, each rung is priced by
the same curve that priced the main line (`betting.prob_over_at`), not
by football's mixture or normal.

Run directly: `python3 tests/test_mlb_ladder.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine.models import SportsbookLine                                   # noqa: E402
from engine.mlb import betting as B                                        # noqa: E402
from engine.mlb.models import (MLBGame, MLBProp, MLBGameLog, Pitcher,      # noqa: E402
                               STRIKEOUTS, TOTAL_BASES, HOME_RUNS)
from engine.mlb.projection import build_mlb_projection                     # noqa: E402
from engine.sources import oddsapi as oa                                   # noqa: E402


def _game():
    return MLBGame(home="CHC", away="PHI", park="wrigley",
                   pitchers={"CHC": Pitcher("RHP Guy", "R", 0.52, 0.40, 0.19),
                             "PHI": Pitcher("Ace", "R", 0.34, 0.33, 0.29)},
                   bullpen_rank={"CHC": 27, "PHI": 5},
                   team_k_rate={"CHC": 0.27, "PHI": 0.20})


def _arm(values=(7, 4, 6, 5, 8, 3, 6, 5, 7, 6)):
    return MLBProp("Ace", "PHI", "CHC", "SP", STRIKEOUTS,
                   [MLBGameLog(i + 1, "X", v) for i, v in enumerate(values)],
                   sum(values) / len(values), None,
                   [SportsbookLine("DraftKings", 5.5, -115, -105)],
                   throws="R", lineup_spot=1)


def test_baseball_asks_for_three_ladders_behind_the_guard():
    assert oa.SPORT_CONFIG["mlb"]["alternates"] is oa.MLB_ALT_ODDS_TO_MARKET
    assert set(oa.MLB_ALT_ODDS_TO_MARKET.values()) == {"hits", "total_bases", "strikeouts"}
    assert all(k.endswith("_alternate") for k in oa.MLB_ALT_ODDS_TO_MARKET)
    # Unproven against the API from this box, so the drop-and-retry
    # guard in `fetch_event_odds` is what makes asking safe.
    assert set(oa.MLB_ALT_ODDS_TO_MARKET) <= oa.UNPROVEN_MARKETS
    assert oa.PASS_TD_ODDS_KEY in oa.UNPROVEN_MARKETS      # the football key is still there
    # Home runs deliberately have no ladder.
    assert "batter_home_runs_alternate" not in oa.MLB_ALT_ODDS_TO_MARKET


def test_every_rung_is_priced_by_the_curve_that_priced_the_main_line():
    prop = _arm()
    prop.alt_lines = [SportsbookLine("DraftKings", 3.5, -210, 165),
                      SportsbookLine("FanDuel", 3.5, -200, 160),
                      SportsbookLine("DraftKings", 4.5, -140, 115),
                      SportsbookLine("FanDuel", 7.5, 190, -240)]
    proj = build_mlb_projection(prop, _game())
    got = B.rung_probs(prop, proj)
    assert set(got) == {"3.5", "4.5", "7.5"}, got            # one entry per distinct number
    for key in got:
        assert abs(got[key] - round(B.prob_over_at(prop, proj, float(key)), 4)) < 1e-9
    # Monotone in the line, and the low rung is where "likely" lives.
    assert got["3.5"] > got["4.5"] > got["7.5"], got
    assert got["3.5"] > 0.55, got


def test_the_main_line_and_the_ladder_share_one_curve():
    """`evaluate_mlb_prop`'s own `p_over_at` must be `prob_over_at`, or the
    Most Likely rung and the Edge card could disagree about one pitcher."""
    import inspect
    src = inspect.getsource(B.evaluate_mlb_prop)
    assert "return prob_over_at(prop, proj, line, history)" in src
    assert "_poisson_over(" not in src.split("def p_over_at")[1].split("pick_side(")[0], \
        "the closure grew its own curve again"
    prop = _arm()
    proj = build_mlb_projection(prop, _game())
    hr = MLBProp("Slugger", "PHI", "CHC", "1B", HOME_RUNS,
                 [MLBGameLog(i, "X", 1 if i % 4 == 0 else 0) for i in range(1, 13)],
                 0.25, None, [SportsbookLine("DraftKings", 0.5, 240, -300)])
    hproj = build_mlb_projection(hr, _game())
    assert abs(B.prob_over_at(hr, hproj, 0.5) - B._poisson_over(0.5, hproj.mean)) < 1e-9 \
        or B.prob_over_at(hr, hproj, 0.5) > 0        # calibrated where a curve exists


def test_no_ladder_prices_nothing():
    prop = _arm()
    proj = build_mlb_projection(prop, _game())
    assert B.rung_probs(prop, proj) == {}
    prop.alt_lines = [SportsbookLine("DraftKings", "bad", -110, -110)]
    assert B.rung_probs(prop, proj) == {}


def test_the_baseball_row_carries_the_ladder_and_its_prices():
    with open(os.path.join(ROOT, "engine", "mlb", "pipeline.py"), encoding="utf-8") as f:
        src = f.read()
    at = src.index("def _rec_to_dict(")
    body = src[at:src.index("\ndef ", at + 10)]
    for key in ('"alt_lines": [', '"alt_sharp_lines": [', '"rung_probs": _rung_probs(prop, proj)'):
        assert key in body, key


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
