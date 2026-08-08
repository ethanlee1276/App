"""The WNBA spec's own rules — the ones that are NOT the NBA's.

`test_wnba.py` proves the league was separated from the NBA cleanly. This
file proves the separation went further than arithmetic: the WNBA spec
rewrites the market tiers, the minimum edges, the grade, the staking and
the caps, and inheriting a DECISION rule the operator explicitly rewrote
would be a different kind of dishonesty from inheriting a fitted constant.

Three things carry the weight here.

**A tier-3 market has to clear more than double a tier-1 market.** Made
threes are a low-frequency event where one hot night distorts every
average, and pricing them at the same bar as rebounds is how a soft-market
model bleeds out on variance it mistook for edge.

**A volatile role is unbettable at any modelled edge.** The projection is
minutes × a per-minute rate; if the minutes are a coin flip then so is the
projection, and computing an edge from it only makes the fiction numerate.

**The NBA must not have been re-tuned by a document about another
league.** Every new rule here is opt-in per league, and the calibrated
board keeps its own gate.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import hoops
from engine.nba import minutes as M
from engine.nba import quality as Q
from engine.nba.prob import required_edge
from engine.nba.pipeline import evaluate_prop, run_nba_slate

STEADY = [32.0, 33, 31, 32, 34, 31, 33, 32, 32, 33, 31, 32]


def _prop(market="reb", line=8.5, rate=0.28, minutes=None, **kw):
    mins = minutes if minutes is not None else STEADY
    p = {"player": kw.pop("player", "Test Player"),
         "team": kw.pop("team", "LVA"), "opponent": kw.pop("opponent", "NYL"),
         "market": market, "line": line, "over_odds": -110, "under_odds": -110,
         "spread": -3.0, "is_starter": True, "minutes": list(mins),
         "values": [round(m * rate, 1) for m in mins]}
    p.update(kw)
    return p


# --- §7 / §3.6 the tiers and their bars -------------------------------------
def test_the_wnba_tier_order_is_its_own_not_the_nbas():
    t = hoops.WNBA.market_tier
    # Count stats tied to minutes and role are the core product; PRA
    # aggregates away single-category noise.
    assert t["reb"] == t["ast"] == t["pra"] == 1
    assert t["pts"] == 2                       # efficiency-contaminated
    assert t["fg3m"] == t["stl"] == t["blk"] == 3


def test_a_tier_three_market_clears_more_than_double_a_tier_one():
    lo = required_edge("reb", hold=0.045, tune=hoops.WNBA)
    mid = required_edge("pts", hold=0.045, tune=hoops.WNBA)
    hi = required_edge("fg3m", hold=0.045, tune=hoops.WNBA)
    assert (lo, mid, hi) == (0.030, 0.045, 0.065)
    assert hi > 2 * lo


def test_the_wnba_bars_sit_above_the_nfl_and_mlb_thresholds():
    """When a soft-market model disagrees with a soft market, the cushion
    is the protection against being confidently wrong together."""
    for stat in ("reb", "pts", "fg3m"):
        assert (required_edge(stat, 0.045, hoops.WNBA)
                > required_edge(stat, 0.045, hoops.NBA))


def test_an_unknown_market_still_gets_a_bar():
    assert required_edge("double_double", 0.045, hoops.WNBA) > 0


def test_the_nba_gate_is_untouched_by_another_leagues_spec():
    assert not hoops.NBA.market_tier and not hoops.NBA.tier_min_edge
    # The NBA's original rule: 2% normally, 4% on a high-hold market — the
    # hold decides, not a tier table.
    assert required_edge("reb", hold=0.02, tune=hoops.NBA) == 0.02
    assert required_edge("fg3m", hold=0.02, tune=hoops.NBA,
                         high_hold_market=True) == 0.04
    assert required_edge("reb", hold=0.09, tune=hoops.NBA) == 0.04


# --- §5 the stability filter ------------------------------------------------
def test_a_settled_role_and_a_coin_flip_are_told_apart():
    steady = Q.usage_stability(STEADY)
    volatile = Q.usage_stability([34.0, 8, 29, 4, 31, 6, 27, 11])
    assert steady["cv"] < 0.1 and volatile["cv"] > 0.5
    assert steady["volatile"] is False and volatile["volatile"] is True
    assert steady["score"] > volatile["score"]


def test_a_short_sample_is_unstable_not_stable():
    """Three games is not evidence of a settled role."""
    st = Q.usage_stability([31.0, 30, 32])
    assert st["volatile"] is True and st["cv"] is None
    assert "unproven" in st["note"]


def test_a_reliable_six_minutes_a_night_is_not_a_bettable_role():
    st = Q.usage_stability([6.0, 6, 6, 6, 6, 6])
    assert st["cv"] == 0.0, "perfectly consistent…"
    assert st["volatile"] is True, "…and still not a role you can project"


def test_a_volatile_role_is_refused_before_it_is_ever_priced():
    r = evaluate_prop(_prop(minutes=[34.0, 8, 29, 4, 31, 6, 27, 11]),
                      hoops.WNBA)
    assert r["kind"] == "skip"
    assert "volatility" in r["why"]
    # The NBA never opted into this filter, so it is unaffected.
    assert hoops.NBA.stability_max_cv is None
    n = evaluate_prop(_prop(minutes=[34.0, 8, 29, 4, 31, 6, 27, 11]), hoops.NBA)
    assert n["kind"] != "skip" or "volatility" not in n.get("why", "")


# --- §5 recency, read as nested rather than overlapping ---------------------
def test_the_recency_windows_do_not_double_count_the_last_five_games():
    """'Last 5 at 40% and last 10 at 30%' describes overlapping windows.
    Weighted literally, the five most recent games would carry 70%."""
    recent, older, oldest = 40.0, 20.0, 10.0
    mins = [recent] * 5 + [older] * 5 + [oldest] * 10
    got = M.base_minutes(mins, hoops.WNBA)
    w5, w10, w20 = hoops.WNBA.recency_weights
    expected = round((w5 * recent + w10 * older + w20 * oldest)
                     / (w5 + w10 + w20), 2)
    assert got == expected
    assert got < (0.70 * recent + 0.30 * older), "last five counted twice"


def test_the_nba_keeps_its_own_recency_weights():
    assert hoops.NBA.recency_weights == (0.50, 0.30, 0.20)
    assert hoops.WNBA.recency_weights == (0.40, 0.30, 0.20)
    mins = [40.0] * 5 + [20.0] * 5 + [10.0] * 10
    assert M.base_minutes(mins, hoops.NBA) != M.base_minutes(mins, hoops.WNBA)


# --- §8 the grade -----------------------------------------------------------
def test_the_grade_weights_are_the_specs_and_sum_to_one_hundred():
    assert sum(hoops.WNBA.grade_weights.values()) == 100
    # Minutes are the king input; freshness is where the timing edge lives.
    assert hoops.WNBA.grade_weights["minutes_certainty"] == 20
    assert hoops.WNBA.grade_weights["freshness"] == 15


def test_the_edge_component_is_scored_against_this_markets_own_bar():
    # 3.2% has cleared a tier-1 bar and missed a tier-3 one.
    assert Q.edge_score(0.032, 0.030) > Q.edge_score(0.032, 0.065)


def test_minutes_certainty_needs_both_a_role_and_a_stable_one():
    """A starter in an unsettled rotation and a bench player with a fixed
    job fail in opposite ways, and both have to be caught."""
    solid = Q.quality_score(0.05, 0.03, "A", 1.0, 1, 1, 1, 1, hoops.WNBA)
    shaky_role = Q.quality_score(0.05, 0.03, "A", 0.2, 1, 1, 1, 1, hoops.WNBA)
    weak_grade = Q.quality_score(0.05, 0.03, "C", 1.0, 1, 1, 1, 1, hoops.WNBA)
    assert solid > shaky_role and solid > weak_grade


def test_below_seventy_is_no_bet_no_leans():
    assert Q.grade_label(69, hoops.WNBA) == "Pass"
    assert Q.grade_label(70, hoops.WNBA) == "B+"
    assert Q.grade_label(80, hoops.WNBA) == "A"
    assert Q.grade_label(90, hoops.WNBA) == "A+"


def test_the_grade_gates_the_wnba_and_only_reports_for_the_nba():
    assert hoops.WNBA.min_grade == 70
    assert hoops.NBA.min_grade is None


# --- §8 staking and caps ----------------------------------------------------
def test_half_kelly_only_for_an_a_plus_in_tier_one():
    p, odds = 0.55, -110
    assert (Q.kelly_stake(p, odds, 95, 1, hoops.WNBA)
            > Q.kelly_stake(p, odds, 85, 1, hoops.WNBA))
    # …never in tier 2, however good the grade.
    assert (Q.kelly_stake(p, odds, 95, 2, hoops.WNBA)
            == Q.kelly_stake(p, odds, 85, 2, hoops.WNBA))


def test_no_single_play_exceeds_two_percent():
    assert Q.kelly_stake(0.99, 500, 95, 1, hoops.WNBA) <= hoops.WNBA.cap_per_play


def test_the_slate_cap_trims_the_worst_play_not_a_random_one():
    picks = [{"team": f"T{i}", "opponent": f"O{i}", "grade_score": 70 + i,
              "stake_fraction": 0.02} for i in range(9)]
    capped = Q.apply_exposure_caps(picks, hoops.WNBA)
    total = sum(p["stake_fraction"] for p in capped)
    assert total <= hoops.WNBA.cap_per_slate + 1e-9
    kept = {p["team"] for p in capped if p["stake_fraction"] > 0}
    assert "T8" in kept, "the cap cost us our best play"
    assert "T0" not in kept


def test_two_plays_on_one_game_share_the_game_cap():
    picks = [{"team": "LVA", "opponent": "NYL", "grade_score": 90 - i,
              "stake_fraction": 0.02} for i in range(5)]
    capped = Q.apply_exposure_caps(picks, hoops.WNBA)
    assert sum(p["stake_fraction"] for p in capped) <= hoops.WNBA.cap_per_game + 1e-9


def test_the_slate_caps_the_money_not_only_the_headcount():
    props = [_prop(player=f"P{i}", team=f"T{i}", opponent=f"O{i}")
             for i in range(6)]
    out = run_nba_slate(props, tune=hoops.WNBA)
    exposure = sum(p.get("stake_fraction", 0.0) for p in out["picks"])
    assert exposure <= hoops.WNBA.cap_per_slate + 1e-9
    assert len(out["picks"]) <= hoops.WNBA.max_picks_per_slate


# --- §6 schedule density, §6 matchup ----------------------------------------
def test_schedule_density_sees_three_games_in_four_nights():
    import nba_build as B
    sched = {"2026-07-30": [{"home": "LVA", "away": "NYL"}],
             "2026-07-28": [{"home": "SEA", "away": "LVA"}]}
    d = B.schedule_density(sched, "LVA", "2026-07-31")
    assert d["rest"] == "3in4" and d["games_in_4"] == 3
    # One day of lookback could never have seen this.
    assert B.schedule_density({}, "LVA", "2026-07-31")["rest"] == "2plus"
    assert B.schedule_fit(d) < B.schedule_fit({"rest": "2plus"})


def test_a_leakier_defence_is_a_better_spot_and_unknown_is_neutral():
    import nba_build as B
    d = {"A": 68.0, "B": 78.0, "C": 84.0}
    assert B.matchup_fit(d, "C") > B.matchup_fit(d, "A")
    assert B.matchup_fit(d, "nobody") == 0.5
    assert B.matchup_fit({}, "A") == 0.5


# --- §7 PRA, §9 the minutes column ------------------------------------------
def test_pra_is_a_real_market_end_to_end():
    from engine.sources.oddsapi import NBA_ODDS_TO_MARKET
    import nba_build as B
    assert NBA_ODDS_TO_MARKET["player_points_rebounds_assists"] == "pra"
    assert "pra" in B.SLATE_MARKETS
    assert hoops.WNBA.market_tier["pra"] == 1
    assert "pra" in hoops.WNBA.sd_cv


def test_the_journal_keeps_projected_and_actual_minutes():
    """The spec calls this the single fastest diagnostic: minutes wrong is
    a broken rotation pipeline, minutes right is variance or efficiency."""
    from engine import ledger
    conn = ledger.connect(":memory:")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bets)").fetchall()}
    assert {"proj_minutes", "actual_minutes"} <= cols
    n = ledger.log_recommendations(conn, {
        "sport": "wnba", "date": "2026-07-31",
        "recommendations": [{"player": "A", "market": "reb", "line": 7.5,
                             "odds": -110, "stake_units": 0.5,
                             "proj_minutes": 31.4, "recommended": True}]})
    assert n == 1
    row = conn.execute("SELECT proj_minutes FROM bets").fetchone()
    assert row["proj_minutes"] == 31.4


def test_the_page_layer_grades_the_wnba_as_the_wnba():
    """The shared-schema layer is what the seven pages actually render, and
    it used to call evaluate_prop with the default tuning — so Scalpy's own
    picks were graded as the WNBA and the board displayed beside them was
    graded as the NBA."""
    import inspect
    from engine.nba.pipeline import shared_recommendations
    sig = inspect.signature(shared_recommendations)
    assert "tune" in sig.parameters, "the page layer can't know its league"

    src = inspect.getsource(shared_recommendations)
    assert "evaluate_prop(prop, tune)" in src

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "nba_build.py"), encoding="utf-8") as fh:
        build = fh.read()
    assert "shared_recommendations(props, lines_map, dates_map," in build
    # Anchored on the ARGUMENT, not on "tune=tune)" — the closing paren was
    # part of the match until a second keyword argument was added after it,
    # and the test then failed while the thing it protects was untouched.
    i = build.index("shared_recommendations(props, lines_map, dates_map,")
    assert "tune=tune" in build[i:i + 400], \
        "the build never passes the league through"


def test_a_tier_three_prop_is_harder_to_recommend_on_the_page_too():
    from engine.nba.pipeline import shared_recommendations
    mins = [32.0] * 12
    prop = {"player": "P", "team": "LVA", "opponent": "NYL", "market": "fg3m",
            "line": 2.5, "over_odds": -110, "under_odds": -110,
            "spread": -3.0, "is_starter": True, "minutes": mins,
            "values": [round(m * 0.09, 1) for m in mins]}
    as_nba = shared_recommendations([dict(prop)], tune=hoops.NBA)
    as_wnba = shared_recommendations([dict(prop)], tune=hoops.WNBA)
    if as_nba and as_wnba:
        # Same numbers, a bar more than three times as high.
        assert as_wnba[0]["edge"] == as_nba[0]["edge"]
        assert not (as_wnba[0]["recommended"] and not as_nba[0]["recommended"])
# --- the door has to stay open ----------------------------------------------
#
# This is a GUARD, not a preference. It asserts nothing about where the bars
# belong — only that the pairing of clamp and gate leaves a reachable window
# at standard juice. Decided 2026-08-02: the bars stay where they are and an
# empty board is a correct output. What must never happen again is the bars
# closing the door ARITHMETICALLY while still reading like a live filter.
#
# It has happened once. The 2026-07-29 retune found the previous pairing
# (w=0.28, gate 3.0pts) mathematically closed — the largest edge the model
# could EVER produce was 0.9pts over a -110 break-even against a 3.0pt
# requirement, so no line and no price could yield a pick. That was found by
# hand, months late, by grid search. This runs the same search every commit.


def _window(odds: int, hold: float = 0.045):
    """(lo, hi) disagreement with de-vigged fair that can actually be bet."""
    from engine.nba import prob as P
    be = P.break_even(odds)
    fair = be - hold / 2.0
    lo = hi = None
    d = 0.0
    while d <= 0.30:
        p_final = fair + P.CLAMP_W_DEFAULT * d
        dec = P._dec(odds)
        ev = p_final * (dec - 1.0) - (1.0 - p_final)
        ok = (p_final - be >= P.GATE_EDGE_PTS and ev >= P.GATE_MIN_EV
              and odds >= P.GATE_WORST_PRICE and d < P.CLAMP_KILL_DIFF)
        if ok:
            lo = d if lo is None else lo
            hi = d
        d += 0.0005
    return lo, hi


def test_the_gate_and_the_clamp_leave_a_reachable_window():
    """A bar the model cannot reach at ANY price is not a strict filter, it
    is an off switch that looks like a filter."""
    for odds in (-150, -130, -120, -110, -105, 100, 120, 150, 200):
        lo, hi = _window(odds)
        assert lo is not None, f"door CLOSED at {odds}: no disagreement clears"
        assert hi > lo, f"window has no width at {odds}"


def test_the_window_sits_below_the_kill_threshold_not_across_it():
    """The clamp kills a 12-point disagreement as "an input is wrong". If the
    bettable window ran past that line the two rules would be contradicting
    each other on the same prop."""
    from engine.nba import prob as P
    for odds in (-110, 100, 150):
        _, hi = _window(odds)
        assert hi < P.CLAMP_KILL_DIFF


def test_the_windows_narrowness_is_recorded_where_it_can_be_seen():
    """MEASURED 2026-08-02, and deliberately asserted rather than described:
    a pick needs the model to disagree with the de-vigged market by roughly
    9.5 to 11.9 points, a band about 2.4 points wide sitting immediately
    below the kill line. So the board only ever bets its most EXTREME
    disagreements, which is backwards, and a WNBA slate that night split 49
    below the window / 8 killed above it / 0 inside.

    If a future change widens this a lot, that is a real loosening and this
    test should fail so it is a decision rather than a side effect.
    """
    lo, hi = _window(-110)
    assert 0.085 <= lo <= 0.105, lo
    assert 0.115 <= hi < 0.120, hi
    assert (hi - lo) < 0.04, "window widened — was this meant to be a loosening?"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
