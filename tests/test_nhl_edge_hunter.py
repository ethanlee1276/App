"""Scalpy NHL — Edge Hunter 1.0: the NHL's Edge-bet model, never Most Likely's.

Ethan, 2026-10-03: "here is the model to use for nhl EDGE bets. this model
is not to be used for nhl most likely bets ... A bet only becomes an Edge
Play when both answers are yes: A. Is the price wrong? B. Are we confident
our estimate of the true probability is actually good?"

Checks, one rule each: the arithmetic (fair odds, EV per $1, tiers); each
market's own minimum edge (4 points is a moneyline play and an anytime-
goal pass); the false-edge filter — an unsettled goalie for a
goalie-dependent bet, one book on the number, the shot model and his own
record disagreeing, a tiny sample, an unstable role, an injury, and "only
the formula likes it"; Elite needs three reasons and a market that is not
high-variance; a high-variance play is staked as speculative; the board's
Edge picks are exactly Edge Hunter's plays and game lines follow it; two
plays on one game that argue opposite ways keep only the stronger; and
the Most Likely list is built as before, untouched by Edge Hunter.

Run directly: `python3 tests/test_nhl_edge_hunter.py`
"""
import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import nhl_build as B                                          # noqa: E402
from engine.nhl import edgehunter as EH                        # noqa: E402
T = importlib.import_module("test_nhl_board_builds")   # the board fixture, shared

LEAGUE = {"sv": 0.900}
TEAMS = {"EDM": {"sog_for": 33.0, "sog_against": 27.0}, "CGY": {"sog_for": 27.0, "sog_against": 34.0},
         "BOS": {"sog_for": 30.0, "sog_against": 30.0}}
CTX = {"EDM": {"starter": "Stuart Skinner", "starter_sure": True, "sv": 0.905, "starter_share": 0.9,
               "xg": 3.4, "b2b": False},
       "CGY": {"starter": "Dan Vladar", "starter_sure": True, "sv": 0.890, "raw_sv": 0.875,
               "starter_share": 0.8, "xg": 2.6, "b2b": True}}
QUOTES = [{"book": b, "line": 0.5, "over_odds": -120, "under_odds": 100} for b in ("DraftKings", "FanDuel", "BetMGM")]


def _skater(toi_now=20.0, toi_before=17.0, ppg=0.2, value=1.0, n=20):
    games = [{"date": f"2026-0{1 + i // 28}-{1 + i % 28:02d}", "toi": toi_now if i < 5 else toi_before,
              "ppg": ppg, "sog": 3.0} for i in range(n)]
    return {"position": "C", "games": games}, [value] * min(n, 12)


def _prop(market="points", edge=0.07, win=0.60, n=20, quotes=QUOTES, ctx=CTX, **kw):
    p, recent = _skater(n=n)
    proj = {"mean": 1.1, "toi": 20.0, "n": n, "recent": recent}
    return EH.assess_prop(market, "OVER", 0.5, win, win - edge, edge, -110, "DraftKings", True, proj, p,
                          "EDM", "CGY", ctx=ctx, teams=TEAMS, league=LEAGUE, quotes=quotes, **kw)


def test_the_arithmetic_ethan_wrote_down():
    assert EH.fair_odds(0.54) == -117 and EH.fair_odds(0.25) == 300
    assert abs(EH.ev_per_dollar(0.54, 110) - 0.134) < 1e-9
    assert [EH.classify(e) for e in (0.09, 0.06, 0.035, 0.02)] == ["Elite edge", "Strong edge", "Small edge", "Pass"]


def test_each_market_has_its_own_minimum():
    assert EH.MARKET_MIN_EDGE["moneyline"] == 0.03 and EH.MARKET_MIN_EDGE["anytime_goal"] == 0.08
    goal = _prop("anytime_goal", edge=0.04)
    assert not goal["play"] and any("under the 8%" in x for x in goal["passes"]), goal["passes"]


def test_a_real_edge_plays_with_its_reasons_and_its_stake():
    r = _prop("points", edge=0.07)
    assert r["play"], r["passes"]
    assert r["classification"] == "Strong edge" and r["support"] >= 2
    assert 0 < r["stake_units"] <= EH.STAKE_CAP["Strong edge"]
    assert r["why_market_wrong"] and r["fair_odds"] == EH.fair_odds(0.60)
    assert {c["key"] for c in r["components"]} >= {"discrepancy", "process", "goalie", "market"}
    assert "Vladar" in r["goalie"] and r["market_prob"] == 0.53
    vlad = next(c for c in r["components"] if c["key"] == "goalie")
    assert "runs cold" in vlad["note"], "a raw rate off his regressed one is the regression hunting ground"


def test_elite_needs_three_reasons_and_a_steady_market():
    sog = _prop("sog", edge=0.10)
    assert sog["play"] and sog["support"] >= 3 and sog["classification"] == "Elite edge", sog
    goal = _prop("anytime_goal", edge=0.10)
    assert goal["classification"] != "Elite edge", "a high-variance market is never Elite"
    if goal["play"]:
        assert goal["stake_units"] <= EH.SPECULATIVE_CAP


def test_the_false_edge_filter():
    unsettled = {**CTX, "CGY": {**CTX["CGY"], "starter_sure": False}}
    assert any("goalie is not settled" in x for x in _prop("points", ctx=unsettled)["passes"])
    assert not any("goalie" in x for x in _prop("sog", ctx=unsettled)["passes"]), "shots on goal do not turn on the goalie"
    assert any("only one book" in x for x in _prop(quotes=QUOTES[:1])["passes"])
    assert any("too small a sample" in x for x in _prop(n=6)["passes"])
    assert any("role or script" in x for x in _prop(scalpy_pass="ice time moved 40%")["passes"])
    assert any("Day-To-Day" in x for x in _prop(injury_status="Day-To-Day")["passes"])
    p, _ = _skater()
    proj = {"mean": 1.1, "toi": 20.0, "n": 20, "recent": [0.0] * 12}       # never cleared 0.5
    split = EH.assess_prop("points", "OVER", 0.5, 0.60, 0.53, 0.07, -110, "DK", True, proj, p, "EDM", "CGY",
                           ctx=CTX, teams=TEAMS, league=LEAGUE, quotes=QUOTES)
    assert any("models disagree" in x for x in split["passes"]), split["passes"]


def test_only_the_formula_liking_it_is_not_enough():
    flat = {"EDM": {"sog_for": 30.0, "sog_against": 30.0}, "CGY": {"sog_for": 30.0, "sog_against": 30.0}}
    p, recent = _skater(toi_now=17.0, ppg=0.0)
    proj = {"mean": 0.5, "toi": 17.0, "n": 20, "recent": recent}
    calm = {"EDM": {"starter_sure": True, "sv": 0.9}, "CGY": {"starter": "X", "starter_sure": True, "sv": 0.900}}
    r = EH.assess_prop("points", "OVER", 0.5, 0.60, 0.53, 0.07, -110, "DK", True, proj, p, "EDM", "CGY",
                       ctx=calm, teams=flat, league=LEAGUE, quotes=QUOTES[:2])
    assert not r["play"] and any("only the formula" in x for x in r["passes"]), r


def test_the_boards_edge_picks_are_edge_hunters_plays():
    out, _ = T._board()
    for r in out["recommendations"]:
        assert r["recommended"] == r["edge_hunter"]["play"], r["edge_hunter"]
        assert r["edge_hunter"]["model"] == EH.MODEL
    for b in out["game_bets"]:
        assert (b["grade"] != "Pass") == b["edge_hunter"]["play"]
    assert out["edge_model"] == EH.MODEL and out["edge_census"]["by_class"]


def test_most_likely_never_reads_edge_hunter():
    """The two models are never blended: the Most Likely list is the same
    whether Edge Hunter calls every prop a play or none of them."""
    import copy
    from engine import likely, rankfit
    out, _ = T._board()
    none = copy.deepcopy(out["recommendations"])
    for r in none:
        r["edge_hunter"] = {"play": False, "classification": "Pass", "edge_score": 0}
        r["recommended"] = False
    real = rankfit.rank_auc
    rankfit.rank_auc = lambda sport, market, store=None: 0.70
    try:
        a = likely.build(copy.deepcopy(out["recommendations"]), sport="nhl")
        b = likely.build(none, sport="nhl")
    finally:
        rankfit.rank_auc = real
    key = lambda rows: [(r["player"], r["market"], r["side"], r["line"], r.get("reserve")) for r in rows]  # noqa: E731
    assert a and key(a) == key(b)


def test_two_plays_that_argue_opposite_ways_keep_the_stronger():
    ml = {"bet_type": "moneyline", "team": "EDM", "edge_hunter": {"edge_score": 70, "edge": 0.05}}
    saves = {"market": "saves", "team": "CGY", "player": "Dan Vladar", "side": "UNDER",
             "edge_hunter": {"edge_score": 55, "edge": 0.06}}
    got = EH.contradictions([ml, saves])
    assert len(got) == 1 and got[0][0] is saves and got[0][1] is ml
    r = {"recommended": True, "grade": "Play", "stake_units": 0.5, "edge_hunter": {"play": True, "passes": []}}
    B._edge_pass(r, "contradicts a stronger edge")
    assert not r["recommended"] and r["stake_units"] == 0 and r["edge_hunter"]["classification"] == "Pass"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
