"""Tests for the NBA (Scalpy) engine — minutes, probability, discipline."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.nba.minutes import (
    base_minutes, blowout_mult, blowout_prob, project_minutes, minutes_grade,
)
from engine.nba.prob import (
    p_over, p_over_negbin, p_over_normal, devig_multiplicative, devig_power,
    market_hold, humility_clamp, approval_gate, break_even,
)
from engine.nba.pipeline import evaluate_prop, run_nba_slate


# --- minutes engine ---------------------------------------------------------
def test_base_minutes_weights_recent_role():
    # Last 5 at 34, games 6-10 at 30, 11-20 at 24 → 0.5/0.3/0.2 blend.
    mins = [34.0] * 5 + [30.0] * 5 + [24.0] * 10
    assert abs(base_minutes(mins) - (0.5 * 34 + 0.3 * 30 + 0.2 * 24)) < 1e-9
    assert base_minutes([30.0, 31.0]) is None       # thin sample


def test_blowout_asymmetry_favors_the_dog():
    # Spec: favorite's starters take the full haircut, dog ~60% of it.
    fav = blowout_mult(-12.0, is_starter=True, is_favorite=True)
    dog = blowout_mult(12.0, is_starter=True, is_favorite=False)
    assert fav == 0.91 and fav < dog < 1.0
    # Bench players GAIN minutes in blowouts.
    assert blowout_mult(-14.5, is_starter=False, is_favorite=True) == 1.20


def test_blowout_prob_matches_spec_table():
    # Spread 12 → ~30%; spread 3 → ~9% (margin ~ Normal(spread, 11.5)).
    assert abs(blowout_prob(12) - 0.30) < 0.02
    assert abs(blowout_prob(3) - 0.095) < 0.015


def test_vacancy_cap_and_rest():
    # +12 vacancy minutes wants 40; the cap holds it to recent high + 8.
    proj = project_minutes(28.0, 0.0, True, False, rest="1day",
                           vacancy_minutes=12.0, recent_high=30.0)
    assert proj == 38.0
    road_b2b = project_minutes(30.0, 0.0, True, False, rest="b2b_road")
    assert road_b2b == 27.9                        # ×0.93


def test_minutes_grades_gate_bets():
    assert minutes_grade(True, -3.0, 15) == "A"
    assert minutes_grade(True, -13.0, 15) == "B"   # blowout risk drops a grade
    assert minutes_grade(False, 0.0, 5) == "D"     # thin bench sample = no bet
    assert minutes_grade(True, 0.0, 15, restriction=True) == "D"


# --- probability layer ------------------------------------------------------
def test_negative_binomial_beats_poisson_in_the_tail():
    # Overdispersed rebounds: P(10-rpg guy grabs 15+) is materially larger
    # under NB than a normal approximation admits — that gap IS the edge.
    nb = p_over_negbin(10.0, 14.5, cv=0.40)
    normal = p_over_normal(10.0, 14.5, sd=0.40 * 10.0)
    assert nb > normal > 0
    # And the mean is still the mean: P(over mean-ish line) ≈ fair.
    assert 0.40 < p_over_negbin(10.0, 9.5, cv=0.40) < 0.60


def test_p_over_uses_exact_for_discrete():
    assert 0.0 < p_over("fg3m", 2.8, 3.5) < 0.5
    assert p_over("pts", 25.0, 24.5) > 0.5          # normal path


def test_power_devig_reprices_longshots():
    mult = devig_multiplicative(-480, 350)
    power = devig_power(-480, 350)
    # Power gives the favorite side MORE probability on skewed markets —
    # the 2-3 point difference that flips DD/alt-line bets.
    assert power[0] > mult[0]
    assert abs(sum(power) - 1.0) < 1e-6
    assert market_hold(-110, -110) > 0.045


def test_humility_clamp_and_kill_rule():
    p, note = humility_clamp(0.60, 0.55, w=0.28)
    assert abs(p - (0.28 * 0.60 + 0.72 * 0.55)) < 1e-9
    # 12+ point disagreement = an input is wrong, not a goldmine.
    killed, why = humility_clamp(0.70, 0.55)
    assert killed is None and "input is wrong" in why


def test_approval_gate_thresholds():
    # Clear pass: 57% final on -110 (be 52.4) with sane hold and grade A.
    assert approval_gate(0.57, -110, 0.045, "A") == []
    fails = approval_gate(0.54, -110, 0.045, "A")     # edge < 3 pts
    assert any("edge" in f for f in fails)
    assert any("−250" in f for f in approval_gate(0.80, -300, 0.045, "A"))
    assert any("hold" in f for f in approval_gate(0.60, -110, 0.12, "A"))
    assert any("grade D" in f for f in approval_gate(0.60, -110, 0.045, "D"))
    assert break_even(-110) == 0.5238


# --- pipeline discipline ----------------------------------------------------
def _prop(player="Guard One", stat="pts", line=22.5, over=-110, under=-110,
          mins=32.0, rate_val=24.0, games=15, **over_kw):
    d = {"player": player, "team": "BOS", "opponent": "NYK", "market": stat,
         "line": line, "over_odds": over, "under_odds": under, "book": "DK",
         "minutes": [mins] * games, "values": [rate_val] * games,
         "is_starter": True, "spread": -3.0, "is_favorite": True,
         "rest": "1day"}
    d.update(over_kw)
    return d


def test_pipeline_no_qualifying_is_a_correct_output():
    # A fair line on a fairly-priced market: clamp pulls p_final to the
    # market and the gate refuses. That's the doctrine working.
    r = run_nba_slate([_prop()])
    assert r["no_qualifying"] is True
    assert r["counts"]["picks"] == 0
    assert r["counts"]["near_misses"] >= 1
    assert r["near_misses"][0]["what_would_change"]


def test_pipeline_max_picks_and_per_game_cap():
    # Force qualifying picks: model far above a mispriced market but inside
    # the kill window, wide sample, plus-money price.
    props = []
    for i, (team, opp) in enumerate([("BOS", "NYK")] * 3 + [("LAL", "GSW")] * 3
                                    + [("MIA", "ORL")] * 3):
        # A modest, realistic mispricing: model ~53% on a +130 over whose
        # de-vig implies ~45% — inside the kill window, clears the gate.
        props.append(_prop(player=f"P{i}", line=22.5, over=130, under=-110,
                           rate_val=23.0, team=team, opponent=opp))
    r = run_nba_slate(props)
    assert 1 <= r["counts"]["picks"] <= 4             # slate cap binds
    by_game = {}
    for p in r["picks"]:
        k = tuple(sorted((p["team"], p["opponent"])))
        by_game[k] = by_game.get(k, 0) + 1
    assert all(v <= 2 for v in by_game.values())      # per-game cap


def test_pipeline_thin_sample_gets_heavier_clamp():
    r = evaluate_prop(_prop(games=6, line=22.5, over=130, under=-110,
                            rate_val=23.0))
    assert r["kind"] in ("pick", "near_miss")
    assert r["w"] == 0.15                             # thin-sample weight


def test_pipeline_kill_rule_refuses_fantasy_edges():
    # Model 20+ points above a liquid market = an input is wrong. No bet.
    r = evaluate_prop(_prop(line=19.5, over=115, under=-135, rate_val=24.0))
    assert r["kind"] == "skip" and "input is wrong" in r["why"]


def test_pipeline_skips_unusable():
    assert evaluate_prop(_prop(games=2))["kind"] == "skip"


# --- CDN parsers ------------------------------------------------------------
def test_nba_cdn_parsers():
    from engine.sources.nbadata import (parse_minutes, parse_schedule_day,
                                        parse_boxscore, log_rows)
    assert parse_minutes("PT31M30.00S") == 31.5
    assert parse_minutes("") == 0.0

    sched = {"leagueSchedule": {"gameDates": [{"games": [
        {"gameId": "0022500001", "gameDateEst": "2026-01-15T00:00:00Z",
         "gameStatus": 3, "gameDateTimeUTC": "2026-01-16T00:30:00Z",
         "homeTeam": {"teamTricode": "BOS", "score": 112},
         "awayTeam": {"teamTricode": "NYK", "score": 104}}]}]}}
    games = parse_schedule_day(sched, "2026-01-15")
    assert games[0]["home"] == "BOS" and games[0]["home_score"] == 112
    assert parse_schedule_day(sched, "2026-01-14") == []

    box = {"game": {
        "homeTeam": {"teamTricode": "BOS", "players": [
            {"name": "Jay Star", "starter": "1", "statistics": {
                "minutes": "PT36M00.00S", "points": 30, "reboundsTotal": 8,
                "assists": 5, "threePointersMade": 4}}]},
        "awayTeam": {"teamTricode": "NYK", "players": []}}}
    rows = parse_boxscore(box)
    assert rows[0]["min"] == 36.0 and rows[0]["starter"] is True
    logs = log_rows(rows, "2026-01-15", "0022500001")
    by_market = {r["market"]: r for r in logs}
    assert by_market["min"]["value"] == 36.0
    assert by_market["pts"]["position"] == "S"        # starter flag rides along
    assert by_market["fg3m"]["value"] == 4.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
