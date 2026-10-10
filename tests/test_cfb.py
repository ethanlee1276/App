"""College football — attention is the axis, and the refusals are refusals.

The spec's central claim is that CFB softness is a function of the
spotlight: ~134 teams play 60+ games most Saturdays, and no book prices a
Wednesday MAC game the way it prices Ohio State – Michigan. Everything
distinctive follows from that, so the load-bearing test is the one that
shows the SAME model probability being a pass in a marquee game and a bet
in a low-attention one. If that ever stops being true, the module has
become NFL-with-different-teams and the edge is gone.

The other half is the two refusals (§2.3, §2.4). An unconfirmed
quarterback and an unverified December roster withhold a play rather than
shading it, because the starter-to-backup gap is worth 4–7+ points and a
bowl roster can be gutted between the last game and kickoff. A model that
priced those anyway would be confidently wrong in exactly the way the spec
spends its strictest section warning about.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.cfb import model as M
from engine.cfb.pipeline import evaluate_play, run_cfb_slate, devig


def _game(**kw):
    g = {"home": "HOME", "away": "AWAY", "game_id": "g1",
         "home_conference": "SEC", "away_conference": "Big Ten",
         "weekday": "Saturday", "qb_confirmed": True,
         "participation_verified": True, "weather_checked": True,
         "kickoff": "2026-10-10T20:00:00Z", "spread": -7}
    g.update(kw)
    return g


def _play(game, p_model=0.58, **kw):
    return {"game": game, "market": "side", "selection": "HOME -7",
            "line": -7, "odds": -110, "opposing_odds": -110,
            "p_model": p_model, "book": "DraftKings",
            "information_certainty": kw.pop("info", 0.9),
            "attention_fit": 0.8, "situational_fit": 0.7,
            "matchup_fit": 0.8, "environment_fit": 0.8, **kw}


# --- §8/§3.5 the axis -------------------------------------------------------
def test_attention_tiers_read_the_spotlight_not_the_quality():
    assert M.attention_tier(_game(home_rank=4)) == M.MARQUEE
    assert M.attention_tier(_game(home_conference="SEC",
                                  away_conference="Big 12")) == M.STANDARD
    assert M.attention_tier(_game(home_conference="MAC", away_conference="MAC",
                                  weekday="Wednesday")) == M.LOW
    assert M.attention_tier(_game(home_conference="Sun Belt",
                                  away_conference="C-USA")) == M.LOW
    # A power team hosting a G5 body-bag game is still watched.
    assert M.attention_tier(_game(home_conference="SEC",
                                  away_conference="MAC")) == M.STANDARD


def test_unknown_conferences_do_not_get_claimed_as_soft():
    """Missing data must not be read as 'nobody is watching this'."""
    assert M.attention_tier({"weekday": "Saturday"}) == M.STANDARD


def test_a_weeknight_game_between_ranked_teams_is_still_marquee():
    assert M.attention_tier(_game(weekday="Thursday", home_rank=2,
                                  away_rank=9)) == M.MARQUEE


def test_the_haircut_is_a_dial_not_a_constant():
    # §3.5 — half the edge is assumed error where the market is sharp.
    assert M.haircut_edge(0.10, M.MARQUEE) == 0.05
    assert M.haircut_edge(0.10, M.LOW) > M.haircut_edge(0.10, M.STANDARD)
    assert M.haircut_edge(0.10, M.STANDARD) > M.haircut_edge(0.10, M.MARQUEE)


def test_the_same_edge_is_a_pass_in_a_marquee_game_and_a_bet_in_a_mac_game():
    """The claim the whole module exists to implement.

    The MAC host takes a Big 12 visitor since 2026-09-02: a game with no
    power-conference side is not bet at all (Ethan: "No" to Group of
    Five), and a Wednesday game with one is still the low-attention tier
    this thesis is about."""
    marquee = evaluate_play(_play(_game(home_rank=4)))
    mac = evaluate_play(_play(_game(home_conference="MAC",
                                    away_conference="Big 12",
                                    weekday="Wednesday")))
    assert marquee["p_model"] == mac["p_model"], "the model saw the same thing"
    assert marquee["kind"] == "pass"
    assert mac["kind"] == "play"
    assert mac["edge"] > marquee["edge"], "the haircut did the work"


def test_props_clear_a_prop_bar_at_every_attention_tier():
    # §3.6 — thin CFB prop menus carry heavy vig wherever they are.
    for tier in (M.MARQUEE, M.STANDARD, M.LOW):
        assert M.min_edge_for(tier, "prop") == M.MIN_EDGE_PROP


# --- §2 the refusals --------------------------------------------------------
def test_an_unconfirmed_quarterback_withholds_the_play():
    r = evaluate_play(_play(_game(qb_confirmed=False), p_model=0.75))
    assert r["kind"] == "hold", "a huge edge must not override the QB gate"
    assert "unconfirmed" in r["why"]
    assert r.get("stake_fraction") is None


def test_december_needs_participation_verified():
    dec = _game(kickoff="2026-12-30T20:00:00Z", participation_verified=False)
    assert evaluate_play(_play(dec, p_model=0.75))["kind"] == "hold"
    ok = _game(kickoff="2026-12-30T20:00:00Z", participation_verified=True)
    assert evaluate_play(_play(ok, p_model=0.62))["kind"] == "play"


def test_the_december_window_covers_january_bowls():
    assert M.december_window("2026-12-28T20:00:00Z")
    assert M.december_window("2027-01-09T20:00:00Z")
    assert not M.december_window("2026-11-28T20:00:00Z")
    assert not M.december_window("")


# --- §9 grade and stake -----------------------------------------------------
def test_the_grade_measures_edge_against_this_tiers_own_bar():
    # 2.6% has cleared a MAC bar and missed a marquee one; they must not
    # score the same.
    lo = M.grade(M.GradeInput(0.026, M.LOW, 1, 1, 1, 1, 1))
    hi = M.grade(M.GradeInput(0.026, M.MARQUEE, 1, 1, 1, 1, 1))
    assert lo > hi


def test_grade_weights_sum_to_one_hundred():
    assert sum(M.GRADE_WEIGHTS.values()) == 100
    perfect = M.grade(M.GradeInput(0.20, M.LOW, 1, 1, 1, 1, 1))
    assert perfect == 100


def test_below_seventy_is_no_bet_no_leans():
    assert M.grade_label(69) == "Pass"
    assert M.grade_label(70) == "B+"
    assert M.grade_label(80) == "A"
    assert M.grade_label(90) == "A+"
    # A power visitor since 2026-09-02: a game with no power-conference
    # side is refused earlier, by decision (Ethan: "No" to Group of Five),
    # and this pins the grade floor, not that rule.
    thin = evaluate_play(_play(_game(home_conference="Sun Belt",
                                     away_conference="SEC"), info=0.05))
    assert thin["kind"] == "pass" and "no leans" in thin["why"], thin["why"]


def test_half_kelly_only_for_an_a_plus_in_a_tier_one_spot():
    # 0.55, not 0.60: above ~0.562 the quarter-Kelly stake already exceeds
    # the 2% per-play cap, so both grades land on the ceiling and the
    # provision is invisible. The interesting range is below the cap.
    p, odds = 0.55, -110
    assert M.kelly_stake(p, odds, M.LOW, 95) > M.kelly_stake(p, odds, M.LOW, 85)
    # …and never in a marquee game, however good the grade.
    assert M.kelly_stake(p, odds, M.MARQUEE, 95) == M.kelly_stake(p, odds, M.MARQUEE, 85)


def test_a_drawdown_halves_the_stake():
    a = M.kelly_stake(0.60, -110, M.LOW, 85)
    b = M.kelly_stake(0.60, -110, M.LOW, 85, drawdown=True)
    assert abs(b - a / 2) < 1e-6 or b == round(a / 2, 5)


def test_no_play_exceeds_two_percent():
    assert M.kelly_stake(0.99, 500, M.LOW, 95) <= M.CAP_PER_PLAY


def test_the_slate_cap_trims_the_worst_play_not_a_random_one():
    """§9 — the structural defence against betting eight pretty-good
    numbers on a 60-game Saturday."""
    plays = [{"game_id": f"g{i}", "grade": 70 + i, "stake_fraction": 0.02}
             for i in range(10)]
    capped = M.apply_caps(plays)
    total = sum(p["stake_fraction"] for p in capped)
    assert total <= M.CAP_PER_SLATE + 1e-9
    kept = [p["game_id"] for p in capped if p["stake_fraction"] > 0]
    dropped = [p["game_id"] for p in capped if p["stake_fraction"] <= 0]
    best, worst = max(plays, key=lambda p: p["grade"]), min(plays, key=lambda p: p["grade"])
    assert best["game_id"] in kept
    assert worst["game_id"] in dropped, "the cap cost us our best play"


def test_correlated_plays_on_one_game_share_the_game_cap():
    plays = [{"game_id": "same", "grade": 90 - i, "stake_fraction": 0.02}
             for i in range(5)]
    capped = M.apply_caps(plays)
    assert sum(p["stake_fraction"] for p in capped) <= M.CAP_PER_GAME + 1e-9


# --- §8 volatility, §3.2 devig ---------------------------------------------
def test_volatility_widens_for_the_things_that_actually_widen_it():
    from engine.cfb.pipeline import volatility
    calm = volatility(_game(), M.MARQUEE, [])
    rivalry = volatility(_game(), M.LOW, ["rivalry"])
    assert M.VOLATILITY.index(rivalry) > M.VOLATILITY.index(calm)


def test_devig_is_multiplicative_and_sums_to_one():
    a, b = devig(-110, -110)
    assert abs(a - 0.5) < 1e-9 and abs(a + b - 1.0) < 1e-9
    a, b = devig(-200, +170)
    assert abs(a + b - 1.0) < 1e-4 and a > b


# --- §11 the output ---------------------------------------------------------
def test_a_slate_with_nothing_says_so():
    out = run_cfb_slate([])
    assert out["no_qualifying"] is True and out["plays"] == []
    assert out["sport"] == "cfb"


def test_a_published_play_carries_its_conditions_and_tier():
    # A Wednesday MAC game is still the LOW-attention tier this pins; since
    # 2026-09-02 a game with no power-conference side is not bet at all
    # (Ethan: "No" to Group of Five), so the visitor is a Big 12 team here.
    out = run_cfb_slate([_play(_game(home_conference="MAC",
                                     away_conference="Big 12",
                                     weekday="Wednesday"))])
    p = out["plays"][0]
    for key in ("attention_tier", "volatility", "grade", "grade_label",
                "edge", "edge_raw", "required_edge", "p_market", "conditions",
                "stake_fraction", "break_even"):
        assert key in p, f"published play is missing {key}"
    assert p["conditions"]["qb_confirmed"] is True


def test_the_shared_stores_are_asked_about_spread_not_side():
    """Two self-tuning gates were dead for the CFB spread, under a comment
    saying they were "in parity with every engine".

    This module calls the market "side" (§3's word). Everything it shares
    a store with calls it "spread": `ledger.log_recommendations` writes
    that for a game bet, so `journalfit` fits `cfb:spread`,
    `losspatterns` mines closures keyed "spread", and `gamecal` measures
    the haircut under it. Asking `calibrate` and `losspatterns` about
    "side" therefore looked up a key nothing writes — a fitted correction
    written and never read, and a boundary fit that could never close the
    market it was fitted on. Both failed open, which is why it looked
    fine. "total" and "moneyline" are spelled the same both sides, so
    this is the spread and only the spread.
    """
    from engine.cfb import pipeline as P

    assert P.store_key("side") == "spread"
    for same in ("total", "moneyline", "team_total", "prop"):
        assert P.store_key(same) == same, same

    import inspect
    src = inspect.getsource(P.evaluate_play)
    for call in ('calibrated("cfb", store_key(market)',
                 'is_reliable("cfb", store_key(market))',
                 'lp_veto("cfb", store_key(market)'):
        assert call in src, f"{call} is not asking the store's own name"
    assert 'calibrated("cfb", market' not in src
    assert 'is_reliable("cfb", market)' not in src


def test_the_card_and_the_ledger_agree_on_the_market_name():
    """One map, and it is the one the gates read. `cfb_build` kept its own
    `BET_TYPES` copy of it while the pipeline had none."""
    import cfb_build

    assert not hasattr(cfb_build, "BET_TYPES"), \
        "the second copy of the market map is back"
    assert cfb_build._store_key("side") == "spread"


def test_a_priced_game_the_model_never_saw_says_so():
    """`build_plays` refuses BEFORE `evaluate_play`, so a game dropped
    there reaches no gate, lands in no pass list, and appears in no
    `gate_census`. The build log then prints "11 game(s), 9 priced ->
    0 play(s)" — the same sentence it prints when every market was priced
    and every gate refused it. Opposite diagnoses, one sentence.

    THE ONE THAT BITES is the ratings guard, in the first weeks of a
    season. `compute_team_ratings` is called with `exclude_prefix="espn:"`
    so an FCS buy game cannot own its host's rating — correct, and its
    unwritten consequence is that the FCS side is then in no ratings map
    at all, so the whole priced game is dropped. In week one or two that
    can be most of the card.
    """
    import cfb_build as CB
    from engine.cfb import ratings as CR
    from engine.teamrates import TeamRating

    def _game(i, home, away):
        return {"game_id": f"g{i}", "home": home, "away": away,
                "home_conference": "MAC", "away_conference": "MAC",
                "home_rank": None, "away_rank": None, "weekday": "Thursday",
                "kickoff": "2026-09-03T23:00Z", "date": "2026-09-03",
                "neutral_site": False, "label": f"{away} @ {home}",
                "state": "scheduled", "qb_confirmed": False,
                "participation_verified": False, "weather_checked": False,
                "indoor": False}

    lines = {"moneyline": (-160, 140), "spread": (-3.5, -110, -110),
             "total": (52.5, -110, -110), "books": {}}
    # One FBS-vs-FBS game, two buy games, one game the book never priced.
    card = [("TOL", "BGSU"), ("KSU", "espn:2678"), ("USF", "espn:2413"),
            ("NEB", "IOWA")]
    games = [_game(i, h, a) for i, (h, a) in enumerate(card)]
    priced = {f"g{i}": dict(lines) for i in range(3)}
    ratings = {}
    for h, a in card:
        ratings[h] = TeamRating(net=3.0, off=2.0, def_=-1.0, games=13)
        if not a.startswith("espn:"):
            ratings[a] = TeamRating(net=0.0, off=0.5, def_=0.5, games=13)

    census: dict = {}
    plays = CB.build_plays(games, priced, ratings, CR.PRIOR, {}, {},
                           census=census)
    assert len(plays) == 3, "only the FBS-vs-FBS game should price"
    assert census == {
        "with a side that has no team rating (usually a non-FBS visitor)": 2,
        "with no book lines": 1}, census
    # Every game on the card is accounted for: priced into markets, or
    # counted with a reason.
    assert len({p["game"]["game_id"] for p in plays}) + sum(census.values()) \
        == len(games)


def test_the_census_is_optional_so_every_caller_still_works():
    """It is an out-parameter, not a return-shape change — the same idiom
    `likely.build` uses, and the reason no existing caller had to move."""
    import inspect
    import cfb_build as CB

    sig = inspect.signature(CB.build_plays)
    assert sig.parameters["census"].default is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
