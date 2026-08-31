"""The MLB handicapping script, implemented where the boards are priced.

Ethan, 2026-08-31: "here is one for MLB i wanna implement for out bets.
we need to push this for the most likley bets like we did for nfl and
cfb." The audit found the engine already carried most of the script by
module name (lineup→PA, bullpen chain, arsenal, umpires, statcast,
lineup-timing); what was missing or wrong is what this file pins:

  * §2.1 — the market-sum devig for home run props, the exact mechanic
    the touchdown board runs, anchored on the game total (§1.2–1.3);
  * §5  — park HR factors split by batter handedness where the
    asymmetry is structural (six parks whose own prose described it);
  * §6  — a CONTINUOUS temperature ramp; the old steps left a 40°F
    dead zone where a 78°F night priced like a 52°F one;
  * §11 — thin platoon samples regress toward the LEAGUE platoon norm,
    not toward "no effect";
  * §16 — batter-vs-pitcher history is structurally excluded from the
    projection, not merely absent from tonight's feed.

Run directly: `python3 tests/test_mlb_script.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine.devig import (HR_DISTINCT, HR_PER_RUN,
                          expected_distinct_hr_hitters)
from engine.mlb import platoon
from engine.mlb.models import (HOME_RUNS, TOTAL_BASES, MLBWeather,
                               ParkProfile)
from engine.mlb.parks import PARKS, evaluate_park, hr_factor_for
from engine.mlb.weather import (TEMP_HR_PER_F, TEMP_NEUTRAL_F,
                                evaluate_weather)


# --- §1.2–1.3: the anchor ---------------------------------------------------
def test_the_game_total_prices_the_distinct_hr_hitters():
    """8.5 runs → 2.125 team HRs → ~2.02 distinct hitters. The script's
    own constants, stated as constants until our logs re-fit them."""
    got = expected_distinct_hr_hitters(8.5)
    assert abs(got - 8.5 * HR_PER_RUN * HR_DISTINCT) < 1e-9
    assert abs(got - 2.019) < 0.01
    assert expected_distinct_hr_hitters(0) == 0.0
    assert expected_distinct_hr_hitters(None) == 0.0


# --- §2.1: the market-sum devig, run on a stub board ------------------------
class _G:
    def __init__(self, total):
        self.total = total


def _menu(game, probs):
    """Candidates shaped like the HR pipeline's, one per listed hitter."""
    from engine.devig import american
    return [{"game": game, "odds": american(p), "book": "dk"}
            for p in probs]


def test_a_fat_menu_yields_a_measured_devig_and_a_thin_one_does_not():
    from engine.mlb.homeruns import hr_board_devigs
    fat = _G(9.2)          # → ~2.185 expected distinct HR hitters
    thin = _G(9.2)
    # Nine hitters summing to ~2.84 implied — a ~1.30 hold, the script's
    # "entirely typical" figure for this market.
    cands = _menu(fat, [0.42, 0.40, 0.38, 0.33, 0.30, 0.28, 0.26, 0.24,
                        0.22])
    cands += _menu(thin, [0.42, 0.40, 0.38])       # under MIN_PRICED
    got = hr_board_devigs(cands)
    assert id(fat) in got, "a nine-hitter menu is measurable"
    assert id(thin) not in got, "three quotes cannot claim a hold"
    # Devigging must LENGTHEN the price: fair < raw, in the right zip
    # code (raw 0.30 against a ~1.3x board lands in the low 20s).
    fair = got[id(fat)].fair(0.30)
    assert fair < 0.30
    assert 0.15 < fair < 0.27, fair


def test_the_scripts_worked_example_lands():
    """§2.1: raw sum 1.42 vs 1.09 expected → 1.30 hold; +320 (23.8%)
    devigs to ~18.3%. Run at game level with both menus identical."""
    from engine.devig import game_devig, PROPORTIONAL
    implied = [0.238, 0.20, 0.18, 0.16, 0.15, 0.14, 0.13, 0.12, 0.10]
    scale = 1.42 / sum(implied)
    implied = [p * scale for p in implied]
    dv = game_devig(implied, 1.09, method=PROPORTIONAL)
    assert dv is not None
    assert abs(dv.fair(0.238) - 0.183) < 0.005, dv.fair(0.238)


def test_both_hr_pricing_paths_carry_the_measured_hold():
    with open(os.path.join(ROOT, "engine", "mlb", "homeruns.py"),
              encoding="utf-8") as f:
        src = f.read()
    def body(name):
        at = src.index(f"def {name}")
        end = src.find("\ndef ", at + 1)
        return src[at:end if end != -1 else len(src)]
    for fn in ("build_hr_longshots", "hr_watchlist"):
        assert "devigs = hr_board_devigs(candidates)" in body(fn), fn
        assert "hold_override=devigs.get(id(game))" in body(fn), fn


def test_the_edge_board_prices_hr_with_the_same_measured_hold():
    """Ethan, 2026-08-31: 'the things we added ... should also be
    implemented for the edge bets.' The watchlist and long shots got the
    market-sum devig first; the edge board's evaluate_mlb_prop still
    priced one-sided HR quotes off the standing assumption — the same
    prop carrying two fair prices depending on the page, the exact
    failure devig_two_way's own docstring records. One measured Devig
    now rides every path."""
    with open(os.path.join(ROOT, "engine", "mlb", "betting.py"),
              encoding="utf-8") as f:
        bet = f.read()
    assert "hold_override=None) -> Recommendation" in bet
    assert "pick_side(prop.lines, p_over_at,\n" \
           "                                                    " \
           "hold=hold_override)" in bet
    with open(os.path.join(ROOT, "engine", "mlb", "pipeline.py"),
              encoding="utf-8") as f:
        pipe = f.read()
    assert "_hr_devigs = hr_board_devigs(_hr_cands)" in pipe
    assert "hold_override=(_hr_devigs.get(id(game))" in pipe


def test_devig_two_way_accepts_a_measured_devig_object():
    """A Devig carries how the overround is SHARED OUT, not just its
    size — flattening it to a float applies the wrong haircut at the
    ends of the board. One-sided overs go through dv.fair; a one-sided
    under (a shape the HR board never produces) falls back to the
    overall multiplier; a real two-way pair ignores it entirely."""
    from engine.devig import Devig
    from engine.odds import american_to_prob, devig_two_way
    dv = Devig.proportional(1.30)
    raw = american_to_prob(320)
    fair, _ = devig_two_way(320, 0, dv)
    assert abs(fair - raw / 1.30) < 1e-9, (fair, raw)
    assert fair < raw
    _, fair_u = devig_two_way(0, -150, dv)
    assert abs(fair_u - american_to_prob(-150) / 1.30) < 1e-9
    two_a, two_b = devig_two_way(-110, -110, dv)
    assert abs(two_a - 0.5) < 1e-9 and abs(two_b - 0.5) < 1e-9, \
        "a real pair needs no assumption, measured or otherwise"


# --- §5: park factors by hand -----------------------------------------------
def test_the_split_parks_price_each_hand_differently():
    yankee = PARKS["yankee"]
    lhb, word_l = hr_factor_for(yankee, "L")
    rhb, word_r = hr_factor_for(yankee, "R")
    assert lhb > yankee.hr_factor > rhb, "the short porch is a lefty park"
    assert word_l == "left-handed" and word_r == "right-handed"
    # Oracle is the mirror: it murders lefty power hardest.
    assert hr_factor_for(PARKS["oracle"], "L")[0] < \
        hr_factor_for(PARKS["oracle"], "R")[0]


def test_switch_hitters_and_unsplit_parks_get_the_blend():
    yankee = PARKS["yankee"]
    assert hr_factor_for(yankee, "S")[0] == yankee.hr_factor, \
        "a switch hitter's side depends on tonight's starter"
    assert hr_factor_for(yankee, "")[0] == yankee.hr_factor
    coors = PARKS["coors"]
    assert coors.hr_factor_lhb is None, "altitude has no handedness"
    assert hr_factor_for(coors, "L")[0] == coors.hr_factor


def test_every_split_recombines_to_its_blend_under_the_league_mix():
    """0.42·lhb + 0.58·rhb ≈ blended — a split pair that doesn't average
    back is two new numbers wearing one park's name."""
    for key, park in PARKS.items():
        if park.hr_factor_lhb is None:
            continue
        mixed = 0.42 * park.hr_factor_lhb + 0.58 * park.hr_factor_rhb
        assert abs(mixed - park.hr_factor) < 0.02, (key, mixed)


def test_evaluate_park_threads_the_hand():
    l_eff = evaluate_park(PARKS["yankee"], bats="L")
    r_eff = evaluate_park(PARKS["yankee"], bats="R")
    assert l_eff.multipliers[HOME_RUNS] > r_eff.multipliers[HOME_RUNS]
    assert any("left-handed" in r for r in l_eff.reasons)
    with open(os.path.join(ROOT, "engine", "mlb", "projection.py"),
              encoding="utf-8") as f:
        assert 'bats=getattr(prop, "bats", "")' in f.read()


# --- §6: the continuous temperature ramp ------------------------------------
def _hr_mult_at(temp, wind=0.0):
    w = MLBWeather(temp_f=temp, wind_mph=wind, wind_dir_rel="",
                   humidity=0.4, precip_chance=0.0, roof_closed=False)
    return evaluate_weather(w).multipliers[HOME_RUNS]


def test_the_dead_zone_is_gone_and_the_ramp_is_monotone():
    """78°F used to price exactly like 52°F (both fell between the
    steps). Now every reading between 40 and 100 moves the number, in
    the right direction, continuously."""
    assert _hr_mult_at(78.0) > 1.0, "warm night, dead zone before"
    assert _hr_mult_at(52.0) < 1.0, "April night, dead zone before"
    temps = [45.0, 52.0, 60.0, 70.0, 78.0, 85.0, 92.0]
    mults = [_hr_mult_at(t) for t in temps]
    assert all(a <= b for a, b in zip(mults, mults[1:])), mults
    assert abs(_hr_mult_at(70.0) - 1.0) < 1e-9, "70°F is the neutral point"


def test_the_endpoints_land_where_the_script_says():
    """§6: ~half a run between 60°F and 90°F, concentrated in HR rate —
    ~0.45%/°F. 90°F ≈ +9%, 45°F ≈ −11%, capped past the reference
    range."""
    assert abs(_hr_mult_at(90.0) - (1 + 20 * TEMP_HR_PER_F)) < 1e-9
    assert abs(_hr_mult_at(45.0) - (1 - 25 * TEMP_HR_PER_F)) < 1e-9
    assert _hr_mult_at(110.0) == _hr_mult_at(100.0), "clamped, not runaway"


def test_a_closed_roof_still_deletes_the_weather_module():
    w = MLBWeather(temp_f=95.0, wind_mph=20.0, wind_dir_rel="out",
                   humidity=0.8, precip_chance=0.0, roof_closed=True)
    assert evaluate_weather(w).multipliers[HOME_RUNS] == 1.0


def test_the_hr_models_own_weather_path_uses_the_same_ramp():
    """The HR model had a private two-step temperature function — the
    rules-enforced-on-one-path bug. One curve now, imported from the
    weather module."""
    with open(os.path.join(ROOT, "engine", "mlb", "homeruns.py"),
              encoding="utf-8") as f:
        src = f.read()
    assert "from .weather import TEMP_HR_PER_F, TEMP_NEUTRAL_F" in src
    assert "temp >= 85" not in src and "temp <= 50" not in src


# --- §11: platoon regression toward the league norm -------------------------
def test_the_league_norm_speaks_both_directions():
    assert platoon.league_norm("L", "R") == platoon.LEAGUE_ADV
    assert platoon.league_norm("R", "L") == platoon.LEAGUE_ADV
    assert platoon.league_norm("S", "R") == platoon.LEAGUE_ADV
    assert platoon.league_norm("R", "R") == platoon.LEAGUE_DIS
    assert platoon.league_norm("L", "L") == platoon.LEAGUE_DIS
    assert platoon.league_norm("R", "") == 1.0, "unknown hand claims nothing"


class _Prop:
    def __init__(self, player, bats):
        self.player, self.bats = player, bats
        self.position, self.market = "1B", "home_runs"
        self.opponent = "OPP"
        self.platoon_factor, self.platoon_note = 1.0, ""


class _Starter:
    def __init__(self, throws):
        self.throws, self.name = throws, "A Starter"


class _Slate:
    def __init__(self, props, throws):
        self.props = props
        self._game = type("G", (), {"pitchers": {"OPP": _Starter(throws)}})()

    def game_for(self, prop):
        return self._game


def test_a_thin_sample_keeps_most_of_the_league_edge():
    """Nine games vs lefties measuring dead-neutral used to ERASE the
    advantage a zero-game player kept via the generic bump — less data
    treated as more information. Now the unearned weight sits on the
    league norm: the thin factor lands near 1.04, and a big sample
    stays where it measured."""
    import re
    thin = _Prop("Thin Sample", "R")
    rich = _Prop("Rich Sample", "R")
    splits = {"home_runs": {
        "thin sample": {"L": 1.0, "R": 1.0, "nL": 9, "nR": 60},
        "rich sample": {"L": 1.0, "R": 1.0, "nL": 200, "nR": 200},
    }}
    from engine.sources.oddsapi import normalize_name
    key_t, key_r = normalize_name("Thin Sample"), normalize_name("Rich Sample")
    splits["home_runs"] = {key_t: splits["home_runs"]["thin sample"],
                           key_r: splits["home_runs"]["rich sample"]}
    platoon.attach_platoon(_Slate([thin, rich], "L"), splits)
    w_thin = 9 / (9 + platoon.SHRINK)
    want = 1.0 + (1 - w_thin) * (platoon.LEAGUE_ADV - 1.0)
    assert abs(thin.platoon_factor - round(want, 3)) < 1e-9, \
        thin.platoon_factor
    assert thin.platoon_factor > rich.platoon_factor >= 1.0
    w_rich = 200 / (200 + platoon.SHRINK)
    assert rich.platoon_factor <= round(
        1.0 + (1 - w_rich) * (platoon.LEAGUE_ADV - 1.0), 3) + 1e-9


def test_the_same_hand_matchup_regresses_downward():
    same = _Prop("Same Hand", "R")
    from engine.sources.oddsapi import normalize_name
    splits = {"home_runs": {normalize_name("Same Hand"):
                            {"L": 1.0, "R": 1.0, "nL": 60, "nR": 9}}}
    platoon.attach_platoon(_Slate([same], "R"), splits)
    assert same.platoon_factor < 1.0, "R vs R is a drag, not an absence"


def test_the_generic_bump_now_prices_the_disadvantage_too():
    with open(os.path.join(ROOT, "engine", "mlb", "matchup.py"),
              encoding="utf-8") as f:
        src = f.read()
    assert "league_norm(prop.bats, starter.throws)" in src
    assert '"edge" if norm > 1.0 else "disadvantage"' in src


# --- §16: batter-vs-pitcher stays off the number ----------------------------
def test_bvp_is_structurally_excluded_from_the_projection():
    """It was inert only because no live source emits vs_pitcher_avg.
    An accident is not a policy — the projection now passes None on
    purpose, and the value survives only as card context."""
    with open(os.path.join(ROOT, "engine", "mlb", "projection.py"),
              encoding="utf-8") as f:
        src = f.read()
    assert "compute_form(logs, prop.career_avg, None," in src
    assert "prop.vs_pitcher_avg" not in src
    with open(os.path.join(ROOT, "engine", "mlb", "pipeline.py"),
              encoding="utf-8") as f:
        assert '"vs_opponent": prop.vs_pitcher_avg' in f.read(), \
            "the card context must survive the exclusion"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
