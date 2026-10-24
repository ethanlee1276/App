"""NHL parlays: two legs, one game, hockey's own correlations.

Ethan, 2026-10-03: "do all of them" — the parlay 2-leg mode among them.
Checks, one rule each: the screen caps hockey tickets at two legs and the
higher 2.5-point bar; a reader's own hockey slip stops at two (and nobody
else's changes); one goal is several points, so teammates' scoring overs
move together instead of being killed as a shared pie; a goalie's saves
over pairs with the shooters he faces, and pulls against their goals; the
anytime scorer stays out of compounding tickets; the NHL board runs the
screen.

Run directly: `python3 tests/test_nhl_parlays.py`
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import parlays as P                                   # noqa: E402

DAY = "2025-10-30"


def leg(player, market, team, opp, side="OVER", **k):
    return dict(player=player, market=market, team=team, opponent=opp, side=side, game_date=DAY, **k)


def test_two_legs_at_the_higher_bar():
    r = P.RULES["nhl"]
    assert r.max_legs == 2 and r.slip_legs == 2 and r.threshold(2) == 0.025


def test_a_hockey_slip_stops_at_two_and_nobody_elses_changes():
    three = [leg(f"P{i}", "sog", "EDM", "CGY") for i in range(3)]
    out = P.check_ticket("nhl", three)
    assert out["ok"] is False and "2 legs is the ceiling" in out["reason"]
    assert P.check_ticket("ufc", [{"player": f"F{i}", "market": "moneyline"} for i in range(3)])["reason"] != \
        "2 legs is the ceiling"
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "const SLIP_MAX_BY_SPORT = { nhl: 2 };" in js and "SLIP_MAX_BY_SPORT[state.sport] || SLIP_MAX" in js


def test_one_goal_is_several_points_so_teammates_scoring_moves_together():
    r = P.relate("nhl", leg("McDavid", "points", "EDM", "CGY"), leg("Draisaitl", "points", "EDM", "CGY"))
    assert r.verdict == "ok" and r.rho > 0.15, r
    nba = P.relate("nba", leg("A", "pts", "LAL", "BOS"), leg("B", "pts", "LAL", "BOS"))
    assert nba.verdict == "kill", "basketball's shared pie is unchanged"


def test_the_goalie_pairs_with_the_shooters_he_faces():
    g = leg("Wolf", "saves", "CGY", "EDM")
    shots = P.relate("nhl", g, leg("McDavid", "sog", "EDM", "CGY"))
    goals = P.relate("nhl", g, leg("McDavid", "points", "EDM", "CGY"))
    assert shots.rho >= 0.25 and shots.verdict == "ok"
    assert goals.rho < 0, "a goal is a shot he did not save"


def test_the_anytime_scorer_is_not_a_compounding_leg_and_the_board_runs_the_screen():
    assert {"goals", "anytime_goal"} <= P.EXTREME_MARKETS
    src = open(os.path.join(ROOT, "nhl_build.py"), encoding="utf-8").read()
    assert "_parlays(out, SPORT)" in src
    slate = {"recommendations": [
        dict(leg("McDavid", "points", "EDM", "CGY"), line=1.5, odds=120, hit_prob=0.5, edge=0.05,
             recommended=True, grade="Play", book="fd", volatility="MED"),
        dict(leg("Draisaitl", "points", "EDM", "CGY"), line=1.5, odds=130, hit_prob=0.48, edge=0.05,
             recommended=True, grade="Play", book="fd", volatility="MED")], "game_bets": [], "games": []}
    out = P.attach(slate, "nhl", state="normal")
    assert out["parlays"]["sport"] == "nhl" and "tickets" in out["parlays"]
    assert all(len(t.get("legs") or []) <= 2 for t in out["parlays"]["tickets"])


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
