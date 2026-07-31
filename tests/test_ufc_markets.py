"""The UFC spec's §3.8, §8 and §10 — the three things that were missing.

The model already produced a full six-outcome distribution for every
fight. It then threw all of it away and bet the moneyline, which is the
one number the book actually thought about. §3.8 says books derive method
props lazily off the moneyline and that translating the distribution into
the right market is where a large share of MMA profit lives — so the
load-bearing test here is the one where the moneyline has no edge, the
method prop has a large one, and the model takes the prop.

Two supporting ideas, both easy to get wrong in the flattering direction:

**Environment reshapes HOW a fight ends, never who wins.** A 25-foot cage
raises finishes; if that adjustment could also move a fighter's win
probability, a venue lookup would be manufacturing moneyline edges out of
architecture.

**Missing feeds score neutral, not bad.** There is no camp-report feed and
usually no venue, and scoring absence as evidence against a bet would sink
every card. But the fight-week component still cannot reach full marks,
because pretending we have MMA's signature edge would be worse.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ufc import environment as E
from engine.ufc import grade as G
from engine.ufc import markets as M
from engine.ufc.model import evaluate_fight, run_card

MADE = {"state": "made"}


def _d(name, edge=0.0, arch="pressure", **kw):
    d = {"name": name, "division": "heavyweight", "ufc_fights": 12,
         "fights": 20, "age": 29, "archetype": arch,
         "slpm": 5.5 + edge, "sapm": 3.0 - edge, "str_def": .60,
         "td_per15": 1.0, "tdd": .75, "td_acc": .45, "sub_att_per15": 0.3,
         "ctrl_per15": 60, "kd_per100": 2.6, "ko_losses": 0,
         "ko_losses_last3": 0, "times_finished": 0, "r3_decay": 0.0,
         "red_flags": []}
    d.update(kw)
    return d


def _puncher_vs_chinny():
    a = _d("Alpha", 1.0, "counter")
    b = _d("Beta", 0.0, "wild_aggressor", ko_losses=2, ko_losses_last3=1,
           times_finished=4)
    return a, b


def _prices(**kw):
    p = {"fighter_a": "Alpha", "fighter_b": "Beta",
         "a_odds": -155, "b_odds": 130, "book": "DraftKings",
         "venue": "T-Mobile Arena", "city": "Las Vegas",
         "weigh_in": {"a": MADE, "b": MADE}}
    p.update(kw)
    return p


# --- §3.8 the translation step ----------------------------------------------
def test_the_model_bets_the_method_prop_when_the_moneyline_has_no_edge():
    """The claim the whole module exists for."""
    a, b = _puncher_vs_chinny()
    r = evaluate_fight(a, b, _prices(props={"Alpha by KO/TKO": 190}),
                       "heavyweight", 0)
    assert r["kind"] == "pick"
    assert r["market"] == "method"
    assert r["selection"] == "Alpha by KO/TKO"
    ml = next(c for c in r["market_board"]
              if c["market"] == "moneyline" and c["selection"] == "Alpha")
    assert ml["edge"] < ml["required_edge"], "the moneyline was bettable too"
    assert r["best_market"]["edge"] > r["best_market"]["required_edge"]


def test_without_the_prop_price_the_same_fight_is_a_pass():
    """Same fight, same distribution — the ONLY difference is whether the
    method market was priced. If this still bet the moneyline, §3.8 would
    be decoration."""
    a, b = _puncher_vs_chinny()
    r = evaluate_fight(a, b, _prices(), "heavyweight", 0)
    assert r["kind"] == "pass"


def test_markets_are_compared_against_their_own_bars_not_raw_edges():
    """A +6% method prop needing 5% beats a +5.5% moneyline needing 4%…
    no it doesn't, and that is the point: comparing raw edges across tiers
    would push money into the highest-vig markets on the board."""
    cards = [
        {"market": "moneyline", "priced": True, "edge": 0.055,
         "required_edge": 0.04},
        {"market": "method", "priced": True, "edge": 0.060,
         "required_edge": 0.05},
    ]
    assert M.best_market(cards)["market"] == "moneyline"


def test_an_unpriced_market_publishes_a_fair_number_to_shop():
    a, b = _puncher_vs_chinny()
    r = evaluate_fight(a, b, _prices(), "heavyweight", 0)
    unpriced = [c for c in r["market_board"] if not c.get("priced")]
    assert unpriced, "the board should carry markets our feed didn't price"
    for c in unpriced:
        assert c["fair_odds"] and c["edge"] is None
        assert "shop" in c["note"]


def test_fair_odds_round_trip_through_break_even():
    for p in (0.25, 0.4, 0.5, 0.66, 0.8):
        assert abs(M.break_even(M.fair_odds(p)) - p) < 0.005


def test_thin_data_raises_the_moneyline_bar_not_the_prop_bar():
    """§3.6 — a prelim line is softer, and so is our data. The second half
    is why the bar goes up."""
    assert M.min_edge_for("moneyline", thin_data=True) == 0.060
    assert M.min_edge_for("moneyline", thin_data=False) == 0.040
    assert M.min_edge_for("method", thin_data=True) == 0.050
    assert M.thin_data_fight(_d("A", ufc_fights=2), _d("B")) is True
    assert M.thin_data_fight(_d("A", short_notice=True), _d("B")) is True
    assert M.thin_data_fight(_d("A"), _d("B")) is False


def test_there_is_no_low_volatility_mma_bet():
    """§10's honest calibration: a -600 favourite still gets knocked out."""
    assert "LOW" not in set(M.VOLATILITY.values())
    assert M.VOLATILITY["moneyline"] == "MEDIUM"
    assert M.VOLATILITY["method"] == "HIGH"
    assert M.VOLATILITY["exact_round"] == "EXTREME"


def test_round_markets_are_absent_rather_than_invented():
    """Pricing an exact round needs a finish-time hazard the dossiers have
    no data for. An invented shape in the highest-vig market on the board
    is the worst possible place for one."""
    joint = {"a_ko": .3, "a_sub": .1, "a_dec": .2,
             "b_ko": .1, "b_sub": .1, "b_dec": .2, "distance": .4}
    got = {row["market"] for row in M.implied_markets(joint, "A", "B")}
    assert got == {"moneyline", "distance", "method", "fighter_finish"}


# --- §8 the environment layer -----------------------------------------------
def test_the_small_cage_is_read_from_the_venue():
    assert E.cage_size("UFC Apex")["small"] is True
    assert E.cage_size("UFC APEX, Las Vegas")["feet"] == 25.0
    assert E.cage_size("T-Mobile Arena")["small"] is False
    # An unknown venue is unknown, not standard.
    assert E.cage_size("")["known"] is False


def test_altitude_is_known_or_unknown_never_assumed_to_be_low():
    """Guessing 'sea level' for an unrecognised city would silently drop
    the adjustment exactly when a new venue at elevation appears."""
    assert E.altitude("Mexico City")["meaningful"] is True
    assert E.altitude("Las Vegas")["meaningful"] is False
    unknown = E.altitude("Some New Arena, Nowhere")
    assert unknown["known"] is False and unknown["meaningful"] is False


def test_the_environment_changes_how_a_fight_ends_not_who_wins():
    """If a venue could move a win probability, a cage-size lookup would
    be manufacturing moneyline edges out of architecture."""
    joint = {"a_ko": .30, "a_sub": .10, "a_dec": .25,
             "b_ko": .10, "b_sub": .05, "b_dec": .20, "distance": .45}
    shift = E.distribution_shift("UFC Apex", "Las Vegas")
    out = E.apply_to_joint(joint, shift)
    for who in ("a", "b"):
        before = sum(joint[f"{who}_{m}"] for m in ("ko", "sub", "dec"))
        after = sum(out[f"{who}_{m}"] for m in ("ko", "sub", "dec"))
        assert abs(before - after) < 1e-6, "the cage moved a win probability"
    assert out["distance"] < joint["distance"], "small cage should finish more"
    assert abs(sum(out[f"{w}_{m}"] for w in "ab"
                   for m in ("ko", "sub", "dec")) - 1.0) < 1e-6


def test_the_environment_shift_is_bounded():
    big = E.distribution_shift("UFC Apex", "Mexico City")
    assert big["finish_lift"] <= E.MAX_ENV_SHIFT
    assert big["fitted"] is False, "a documented prior must say it is one"
    assert len(big["why"]) == 2


def test_an_unknown_venue_changes_nothing():
    joint = {"a_ko": .3, "a_sub": .1, "a_dec": .2,
             "b_ko": .1, "b_sub": .1, "b_dec": .2, "distance": .4}
    out = E.apply_to_joint(joint, E.distribution_shift("", ""))
    assert out == joint


def test_a_close_decision_on_the_road_is_haircut_not_hoped_for():
    volume = _d("Volume", arch="volume_striker")
    home = E.judging_read(volume, on_the_road=False)
    road = E.judging_read(volume, on_the_road=True)
    assert road["decision_haircut"] > home["decision_haircut"] > 0
    # Control time is visible to judges, so a wrestler is scored kindly.
    wrestler = E.judging_read(_d("Grinder", arch="wrestler"), on_the_road=True)
    assert wrestler["decision_haircut"] < road["decision_haircut"]


def test_the_card_venue_is_recorded_per_event():
    import tempfile
    from pathlib import Path
    p = Path(tempfile.mkdtemp()) / "cards.json"
    E.record_card("2026-08-15", "UFC Apex", "Las Vegas", path=p)
    store = E.load_cards(p)
    assert E.card_for("2026-08-15", store)["venue"] == "UFC Apex"
    assert E.card_for("2026-09-01", store) == {"venue": "", "city": ""}


# --- §10 the grade and the caps ---------------------------------------------
def test_the_grade_weights_are_the_specs_and_sum_to_one_hundred():
    assert sum(G.GRADE_WEIGHTS.values()) == 100
    # 30% of the grade asks how much we actually know — more than any other
    # model here spends, and correct given the samples.
    assert G.GRADE_WEIGHTS["data_quality"] + G.GRADE_WEIGHTS["camp_info"] == 30


def test_data_quality_is_scored_off_the_thinner_corner():
    """Perfect data on one fighter and none on the other is not half a
    model, it is no model."""
    assert G.data_quality(_d("A", ufc_fights=20),
                          _d("B", ufc_fights=1))["score"] < 0.2
    assert G.data_quality(_d("A", ufc_fights=10),
                          _d("B", ufc_fights=8))["score"] == 1.0


def test_fight_week_information_can_never_reach_full_marks():
    """Weigh-ins are the one fight-week fact we observe. Scoring a clean
    scale as complete knowledge would be claiming MMA's signature edge
    without having it."""
    best = G.camp_info({"a": MADE, "b": MADE}, _d("A"), _d("B"))
    assert best["score"] < 1.0
    assert any("no camp-footage" in w for w in best["why"])
    none = G.camp_info(None, _d("A"), _d("B"))
    assert none["score"] < best["score"]


def test_a_missing_venue_scores_neutral_rather_than_bad():
    """A missing feed is not evidence against a bet."""
    unknown = G.environment_score(E.distribution_shift("", ""))
    known = G.environment_score(E.distribution_shift("UFC Apex", "Las Vegas"))
    assert unknown["score"] == 0.5
    assert known["score"] > unknown["score"]


def test_half_kelly_is_never_used_in_mma():
    for score in (70, 80, 89, 90, 100):
        assert G.kelly_fraction(score) <= G.KELLY_CEILING == 0.25
    assert G.kelly_fraction(70) == G.KELLY_FLOOR


def test_no_single_fight_exceeds_one_and_a_half_percent():
    assert G.stake_fraction(0.95, 500, 95) <= G.CAP_PER_FIGHT


def test_a_drawdown_halves_the_stake_after_the_cap_not_before():
    """Halving first leaves any play whose raw Kelly exceeded the ceiling
    sitting right back on it, so the rule would do nothing precisely when
    it matters."""
    a = G.stake_fraction(0.95, 500, 95)
    b = G.stake_fraction(0.95, 500, 95, drawdown=True)
    assert abs(b - a / 2) < 1e-9


def test_the_card_cap_is_the_tightest_in_the_system():
    picks = [{"fight": f"F{i}", "grade": 70 + i, "stake_fraction": 0.015}
             for i in range(9)]
    capped = G.apply_card_caps(picks)
    assert sum(p["stake_fraction"] for p in capped) <= G.CAP_PER_CARD + 1e-9
    kept = [p["fight"] for p in capped if p["stake_fraction"] > 0]
    assert "F8" in kept and "F0" not in kept, "the cap cost us our best play"


def test_correlated_positions_on_one_fight_share_a_budget():
    picks = [{"fight": "same", "grade": 90 - i, "stake_fraction": 0.015}
             for i in range(4)]
    capped = G.apply_card_caps(picks)
    total = sum(p["stake_fraction"] for p in capped)
    assert total <= G.CAP_PER_FIGHT_CORRELATED + 1e-9
    assert total > G.CAP_PER_FIGHT, "correlated room should exceed one bet"


def test_below_seventy_is_no_bet_no_leans():
    assert G.grade_label(69) == "Pass"
    assert G.grade_label(70) == "B+"
    assert G.grade_label(90) == "A+"


# --- §9 correlation ---------------------------------------------------------
def test_a_night_of_underdogs_is_flagged_as_one_bet_on_chaos():
    picks = [{"fight": f"F{i}", "odds": 250, "market": "moneyline",
              "selection": f"Dog {i}"} for i in range(3)]
    flags = M.correlation_flags(picks)
    assert any("one bet on a night of upsets" in f for f in flags)


def test_incoherent_pairings_are_named():
    dist = {"fight": "A vs B", "market": "distance",
            "selection": "Goes the distance"}
    ko = {"fight": "A vs B", "market": "method", "selection": "A by KO/TKO"}
    assert M.incoherent(dist, ko)
    assert not M.incoherent(dist, {**ko, "fight": "C vs D"})


def test_the_card_reports_its_own_exposure():
    a, b = _puncher_vs_chinny()
    out = run_card([{"a": a, "b": b, "division": "heavyweight",
                     "prices": _prices(props={"Alpha by KO/TKO": 190})}])
    assert out["exposure"] <= G.CAP_PER_CARD
    assert out["card_cap"] == G.CAP_PER_CARD
    assert "correlation_flags" in out


# --- the "why is the card empty?" diagnostic --------------------------------
def test_the_launcher_can_explain_an_empty_card():
    """"No qualifying plays" is a valid output, but valid is not the same
    as understood — and the first guess is always the weigh-ins, which are
    usually not the culprit."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "launch.py"), encoding="utf-8").read()
    assert "def why_ufc(" in src
    assert '"--why-ufc" in argv' in src, "defined but never dispatched"
    fn = src[src.index("def why_ufc("):src.index("def why_empty(")]
    # It must name every pass reason the model can emit, or a card will be
    # explained with a bare reason code.
    for code in ("no_dossier", "no_data", "no_price", "clamp_kill", "gate",
                 "card_cap"):
        assert code in fn, f"why-ufc cannot explain a {code} pass"
    # And it must say the thing Ethan actually asked.
    assert "Unrecorded does NOT block a bet" in fn


def test_an_unrecorded_weigh_in_does_not_block_a_bet():
    """Only a MISSED weight is a red flag. If an unrecorded one gated the
    fight, every card would be empty until fight-day morning."""
    from engine.ufc import weighin
    assert weighin.red_flags("Nobody Recorded", {}) == []
    a, b = _puncher_vs_chinny()
    r = evaluate_fight(a, b, _prices(weigh_in=None,
                                     props={"Alpha by KO/TKO": 190}),
                       "heavyweight", 0)
    assert r["kind"] == "pick", "an unrecorded weigh-in blocked a real edge"


def test_recording_the_weigh_ins_helps_but_is_not_the_gate():
    """It is worth grade points — about 5 of 100 — and that is all."""
    a, b = _puncher_vs_chinny()
    blank = evaluate_fight(a, b, _prices(weigh_in=None,
                                         props={"Alpha by KO/TKO": 190}),
                           "heavyweight", 0)
    made = evaluate_fight(a, b, _prices(props={"Alpha by KO/TKO": 190}),
                          "heavyweight", 0)
    assert made["grade_score"] > blank["grade_score"]
    assert made["grade_score"] - blank["grade_score"] <= 8


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
