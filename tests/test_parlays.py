"""The Parlay Zone — does the screen actually say no?

This module's whole value is refusal. §12 of the parlay instruction set is
blunt about it: "No qualifying parlay at current numbers" **should be the
most common parlay output you print — by a wide margin.** A screen that
publishes tickets is worthless; a screen that publishes the *right*
near-nothing is the product.

So these tests are mostly negative: each one builds a slate that a bettor
would happily parlay and checks that the module kills it, names the §3 clash
type that killed it, and says why in words a reader can act on.

Three things get positive controls, because a test that can only pass is not
a measurement:

  * the copula, against its own marginalisation (a three-leg joint with the
    third leg at probability 1 must equal the two-leg joint) and against the
    instruction set's only worked calibration point (§1.4);
  * the dominance test, against the ticket §0.3 says it exists to kill —
    independent legs priced at the true product;
  * the clash screen, against §5.2's pitcher stack, which must SURVIVE. A
    screen that rejects everything passes every rejection test and is still
    broken.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import parlays as P


# --- fixtures ----------------------------------------------------------------
def leg(player, team, opp, market, side="OVER", p=0.62, odds=-110, ev=None,
        date="2026-11-02", **kw):
    # EV follows from the leg's own probability and price. Passing an
    # unrelated number used to make fixtures look far more profitable than
    # their probabilities said, which quietly turned rejection tests into
    # tests of nothing.
    if ev is None:
        ev = p * (P.american_to_decimal(odds) - 1) - (1 - p)
    d = dict(player=player, team=team, opponent=opp, market=market,
             market_label=market.replace("_", " ").title(), side=side,
             line=1.5, odds=odds, hit_prob=p, ev_per_unit=ev,
             recommended=True, grade="A", game_date=date, warnings=[],
             headline=f"{player} {side} {market}")
    d.update(kw)
    return d


def game(home="CHI", away="GB", date="2026-11-02", **kw):
    g = dict(home=home, away=away, date=date, spread=3.0, favorite=away,
             total=48.0, roof="outdoors", lineups_confirmed=True,
             weather={"wind_mph": 6})
    g.update(kw)
    return g


def run(sport, recs, games=None, **kw):
    return P.screen({"date": "2026-11-02", "games": games or [game()],
                     "recommendations": recs}, sport, **kw)


def reasons(out):
    return " || ".join(k["reason"] for k in out["killed"])


def clearing_fixture():
    """A ticket that DOES clear — deliberately outside anything this board
    produces, and labelled as such.

    With EV derived consistently from each leg's own probability and price,
    no realistic slate clears the gates: at the correlation tax books charge,
    a same-game ticket needs single-leg edges an order of magnitude past what
    this engine finds. That is the doc working (§12, §14), not a bug — but it
    means every rejection test above would pass on a screen hard-wired to
    return nothing. This is the fixture that proves it is not.
    """
    return [leg("Ace", "PHI", "CHC", "strikeouts", p=0.86, odds=150,
                date="2026-08-02"),
            leg("Ace", "PHI", "CHC", "outs", p=0.85, odds=150,
                date="2026-08-02")]


# --- §1: the maths -----------------------------------------------------------
def test_the_copula_reduces_to_independence_at_zero_correlation():
    """The floor. If the copula cannot reproduce a plain product when nothing
    is correlated, nothing built on top of it means anything."""
    assert abs(P.joint_two(0.6, 0.7, 0.0) - 0.42) < 1e-12


def test_the_three_leg_joint_marginalises_to_the_two_leg_joint():
    """The positive control on the one-factor structure. Send the third leg's
    probability to 1 and the trivariate must collapse onto the bivariate —
    which is computed by a completely different routine (exact Gauss-Legendre
    on the rho-derivative identity, not a factor integral). Two independent
    implementations agreeing to eight decimals is evidence; either one alone
    is an assertion."""
    got = P.joint_three((0.6, 0.6, 1 - 1e-9), (0.3, 0.3, 0.3))
    want = P.joint_two(0.6, 0.6, 0.3)
    assert abs(got - want) < 1e-6, (got, want)


def test_the_one_factor_fit_never_overstates_a_pair():
    """The Appendix says the rho priors are estimates. When a correlation
    matrix will not fit a one-factor structure exactly, the fit is scaled
    DOWN, so every realised pair sits at or below its prior. Overstating a
    correlation overstates the joint, which invents edge."""
    for rhos in ((0.3, 0.3, 0.3), (0.5, 0.2, 0.1), (0.55, 0.35, 0.1),
                 (0.1, 0.6, 0.2)):
        lam = P._factor_loadings(rhos)
        got = (lam[0] * lam[1], lam[0] * lam[2], lam[1] * lam[2])
        for g, target in zip(got, rhos):
            assert g <= target + 1e-9, (rhos, got)


def test_the_correlation_shrink_reproduces_the_docs_worked_example():
    """§1.4 is the instruction set's only calibration point: three legs at
    0.68 / 0.65 / 0.62, "all positively correlated", quoted at a correlated
    joint of 0.3097. Running them at the +0.30 prior shrunk by RHO_SHRINK
    has to land there — and taking the prior at face value must NOT, or the
    shrink is decoration."""
    ps, prior = (0.68, 0.65, 0.62), 0.30
    shrunk = P.joint_three(ps, (prior * P.RHO_SHRINK,) * 3)
    raw = P.joint_three(ps, (prior,) * 3)
    assert abs(shrunk - 0.3097) < 0.002, shrunk
    assert raw - 0.3097 > 0.04, (
        "taking the priors at face value should be materially more generous "
        f"than the doc's own number; got {raw}")


def test_a_positive_correlation_always_raises_the_joint():
    """Sign check. Correlated legs win together more often than independent
    ones — if this ever inverted, every ticket would be priced backwards."""
    base = P.joint_two(0.6, 0.6, 0.0)
    for rho in (0.1, 0.3, 0.5, 0.7):
        assert P.joint_two(0.6, 0.6, rho) > base


# --- §2 Gate 1: standalone eligibility ---------------------------------------
def test_a_leg_that_is_not_a_recommended_single_never_enters_a_ticket():
    """§0: "A parlay leg that would not be a bet on its own is never a bet
    inside a parlay." That single sentence eliminates ~90% of tickets."""
    recs = [leg("A", "GB", "CHI", "receptions"),
            leg("B", "GB", "CHI", "pass_yds", recommended=False)]
    out = run("nfl", recs)
    assert out["eligible_legs"] == 1
    assert out["considered"] == 0


def test_an_unconfirmed_mlb_lineup_kills_every_hitter_leg():
    """§5: "A parlay containing an unconfirmed hitter is not a conditional
    parlay — it is not a bet." Unlike a single, you cannot re-grade one leg of
    a ticket after posting."""
    recs = [leg("Bat A", "PHI", "CHC", "total_bases", date="2026-08-02"),
            leg("Bat B", "PHI", "CHC", "hits", date="2026-08-02")]
    g = [game("PHI", "CHC", "2026-08-02", lineups_confirmed=False)]
    out = run("mlb", recs, g)
    assert out["eligible_legs"] == 0
    assert "lineup is not confirmed" in reasons(out)
    # positive control: confirm the lineup and the same legs become eligible
    g2 = [game("PHI", "CHC", "2026-08-02", lineups_confirmed=True)]
    assert run("mlb", recs, g2)["eligible_legs"] == 2


def test_wind_kills_passing_constructions_regardless_of_edge():
    """§4.4: at 15mph the distribution widens faster than the correlation
    helps. "Regardless of edge" is the part that matters — this is not a
    tiebreak, it is an override."""
    recs = [leg("QB", "GB", "CHI", "pass_yds", ev=0.20),
            leg("WR", "GB", "CHI", "receptions", ev=0.20)]
    windy = [game(weather={"wind_mph": 17})]
    out = run("nfl", recs, windy)
    assert out["eligible_legs"] == 0
    assert "17 mph" in reasons(out) and "§4.4" in reasons(out)
    assert run("nfl", recs, [game(weather={"wind_mph": 6})])["eligible_legs"] == 2


def test_the_wnba_trap_disqualifies_star_props_on_a_big_favourite():
    """§8.1 names it: star points over + her team a big favourite. It feels
    like backing the best team two ways. It is a Type 4 clash and the most
    common losing WNBA ticket. Spread >= 9 disqualifies the leg."""
    recs = [leg("Star", "LVA", "CHI", "pts"), leg("Other", "LVA", "CHI", "reb")]
    big = [game("CHI", "LVA", favorite="LVA", spread=11.0)]
    out = run("wnba", recs, big)
    assert out["eligible_legs"] == 0
    assert "laying 11" in reasons(out) and "Type 4" in reasons(out)
    assert run("wnba", recs, [game("CHI", "LVA", favorite="LVA",
                                   spread=4.0)])["eligible_legs"] == 2


def test_december_closes_college_football_entirely():
    """§6.4: "Bowl season is where CFB parlays go to die." Banned until
    participation, opt-outs and coaching status are verified for every team."""
    recs = [leg("QB", "GA", "BAMA", "pass_yds", date="2026-12-20"),
            leg("WR", "GA", "BAMA", "receptions", date="2026-12-20")]
    out = run("cfb", recs, [game("BAMA", "GA", "2026-12-20")])
    assert out["eligible_legs"] == 0
    assert "December" in reasons(out)


def test_extreme_volatility_markets_cannot_enter_any_ticket():
    """§8.4, generalised: touchdowns, home runs, made threes. These have no
    place inside a compounding structure. Checked by market as well as by the
    slate's volatility field, so a leg missing the field cannot slip in."""
    for sport, market in (("nfl", "anytime_td"), ("mlb", "home_runs"),
                          ("wnba", "fg3m")):
        recs = [leg("A", "X", "Y", market), leg("B", "X", "Y", market)]
        out = run(sport, recs, [game("Y", "X")])
        assert out["eligible_legs"] == 0, (sport, market)


# --- §3: the clash taxonomy --------------------------------------------------
def test_type_5_kills_the_same_player_twice():
    """"If he sits, everything dies." Two props on one man is one bet with
    two chances to lose."""
    recs = [leg("WR1", "GB", "CHI", "receptions"),
            leg("WR1", "GB", "CHI", "rec_yds")]
    out = run("nfl", recs)
    assert "Type 5" in reasons(out)
    assert not out["tickets"]


def test_type_7_kills_a_quarterback_under_next_to_his_own_receiver_over():
    """Direct opposition: one leg winning IS the other losing."""
    recs = [leg("QB", "GB", "CHI", "pass_yds", side="UNDER"),
            leg("WR1", "GB", "CHI", "receptions")]
    out = run("nfl", recs)
    assert "Type 7" in reasons(out)


def test_type_7_kills_a_pitcher_k_over_against_a_hitter_he_is_facing():
    """§5.1's auto-kill: the same pitches cannot strike out the side and get
    hit. -0.25 to -0.40."""
    recs = [leg("Wheeler", "PHI", "CHC", "strikeouts", date="2026-08-02"),
            leg("Happ", "CHC", "PHI", "total_bases", date="2026-08-02")]
    out = run("mlb", recs, [game("PHI", "CHC", "2026-08-02")])
    assert "Type 7" in reasons(out)
    assert "cannot strike out the side and get hit" in reasons(out)


def test_type_2_kills_a_quarterback_next_to_his_own_running_back():
    """Script clash, and §4.3 bans the pairing outright in either direction —
    so this must fire even when the two legs are on opposite sides."""
    for rb_side in ("OVER", "UNDER"):
        recs = [leg("QB", "GB", "CHI", "pass_yds"),
                leg("RB", "GB", "CHI", "rush_yds", side=rb_side)]
        out = run("nfl", recs)
        assert "Type 2" in reasons(out), rb_side


def test_type_3_kills_two_teammates_splitting_one_pie():
    """Targets, shots and rebounds are finite. Two teammates both over is
    two bets on the same ball."""
    recs = [leg("WR1", "GB", "CHI", "receptions"),
            leg("WR2", "GB", "CHI", "rec_yds")]
    out = run("nfl", recs)
    assert "Type 3" in reasons(out)


def test_baseball_is_the_documented_exception_to_the_possession_pie():
    """A plate appearance is not a target. §5.1 puts two bats in one lineup
    at +0.20 to +0.35 — a permitted construction, not a clash. Getting this
    backwards would delete the lineup stack from the system."""
    recs = [leg("Bat A", "PHI", "CHC", "total_bases", date="2026-08-02"),
            leg("Bat B", "PHI", "CHC", "hits", date="2026-08-02")]
    out = run("mlb", recs, [game("PHI", "CHC", "2026-08-02")])
    assert "Type 3" not in reasons(out)
    assert out["tickets"], "the lineup stack should survive the clash screen"


def test_type_4_kills_a_starter_prop_behind_a_blowout_spread():
    """"The most common clash in every sport and the one bettors most
    consistently miss, because both legs feel like backing the good team.""" ""
    recs = [leg("QB", "GB", "CHI", "pass_yds"),
            leg("WR", "GB", "CHI", "receptions")]
    out = run("nfl", recs, [game(favorite="GB", spread=12.0)])
    assert "Type 4" in reasons(out)
    # CFB's bar is higher because its starters get pulled earlier and harder
    cfb = run("cfb", [leg("QB", "GA", "AUB", "pass_yds"),
                      leg("WR", "GA", "AUB", "receptions")],
              [game("AUB", "GA", favorite="GA", spread=12.0)])
    assert "Type 4" not in reasons(cfb), (
        "12 is a CFB blowout only at 17 — §6.2 sets the bar there, not at the "
        "NFL's 10")


def test_the_pitcher_stack_survives_the_type_5_ban():
    """The positive control on the whole clash screen, and the one place the
    instruction set contradicts itself. §3 Type 5 bans same-player multi-prop
    outright; §5.2 calls the pitcher stack — strikeouts over PLUS outs over,
    one arm — "the single best 3-leg construction in your entire system."

    Type 5's own next sentence carries the exception: permitted once per
    ticket for a confirmed-active player. An announced starter is the
    cleanest instance of that in any sport. If this test fails, the screen
    has deleted the doc's favourite construction."""
    out = run("mlb", clearing_fixture(), [game("PHI", "CHC", "2026-08-02")])
    assert out["tickets"], reasons(out)
    assert "Type 5" not in reasons(out), "the pitcher stack was killed"
    assert out["tickets"][0]["qualified"] is True


def test_the_same_player_exception_is_permitted_once_not_twice():
    """§3: "permitted at most once per ticket." Three markets on one arm is
    the banned construction wearing the exception's clothes."""
    recs = [leg("Wheeler", "PHI", "CHC", "strikeouts", date="2026-08-02"),
            leg("Wheeler", "PHI", "CHC", "outs", date="2026-08-02"),
            leg("Wheeler", "PHI", "CHC", "hits", date="2026-08-02",
                market_label="Hits Allowed")]
    out = run("mlb", recs, [game("PHI", "CHC", "2026-08-02")])
    for t in out["tickets"]:
        assert len(t["legs"]) == 2, "a three-prop single-player ticket published"


# --- §2 Gates 3-6 ------------------------------------------------------------
def test_the_dominance_test_kills_independent_legs_at_true_product_pricing():
    """The positive control §0.3 demands, and the reason the 1.25 multiple is
    calibrated where it is.

    For independent legs at a true multiplicative price, EV_parlay =
    prod(1+e_i) - 1, which beats sum(e_i) only by the cross terms — never by
    25%. So the dominance test kills every Type B ticket built on genuine
    independence, which is precisely §0.3's claim that "there is no
    configuration of independent legs where the parlay is the better
    instrument." If this test ever passes a ticket, the multiple is wrong."""
    recs = [leg("WR", "GB", "CHI", "receptions", p=0.62, ev=0.127, odds=-122),
            leg("WR2", "NE", "NYJ", "receptions", p=0.62, ev=0.127, odds=-122)]
    out = run("nfl", recs, [game(), game("NYJ", "NE")])
    t = out["tickets"][0]
    assert t["grade"] == "short", (
        "a cross-game ticket at true product pricing was published as a bet")
    assert t["parlay_type"] == "B"
    assert t["qualified"] is False
    assert t["required_dec"] > t["naive_product_dec"], (
        "a cross-game ticket pays the naive product exactly; if the required "
        "price sat below it the dominance test would be waving Type B through")
    assert "bet the singles" in t["verdict"]


def test_the_required_price_is_higher_for_three_legs_than_for_two():
    """§1.3: 5.0 points for two legs, 6.0 for three. The bar rises with the
    tax, so the same legs must demand a longer price as a triple."""
    ps = (0.66, 0.64, 0.62)
    two = P.joint_two(ps[0], ps[1], 0.10 * P.RHO_SHRINK)
    three = P.joint_three(ps, (0.10 * P.RHO_SHRINK,) * 3)
    r2 = 1 / (two - 0.050)
    r3 = 1 / (three - 0.060)
    assert r3 > r2


def test_college_football_carries_the_highest_bar_in_the_system():
    """§6 holds CFB above every other sport: highest baseline volatility,
    worst injury information. The absolute numbers are tuned down from the
    doc's 5/6/8 at the operator's direction — what has to survive that
    retune is the ORDERING, because the ordering is the judgement and the
    numbers are the dial."""
    for legs in (2, 3):
        assert P.RULES["cfb"].threshold(legs) > P.RULES["nfl"].threshold(legs), legs
        assert P.RULES["cfb"].threshold(legs) > P.RULES["mlb"].threshold(legs), legs
    for sport in ("nfl", "mlb", "cfb", "nba", "wnba"):
        assert P.RULES[sport].threshold(3) > P.RULES[sport].threshold(2), sport


def test_no_ticket_ever_exceeds_three_legs():
    """§0.2: "Hard ceiling: 3 legs. Never 4." Vig compounds; so does model
    error, which is the larger danger."""
    recs = [leg(f"P{i}", "GB", "CHI", m) for i, m in
            enumerate(("receptions", "pass_yds", "rush_yds", "rec_yds"))]
    out = run("nfl", recs)
    for t in out["tickets"]:
        assert len(t["legs"]) <= P.MAX_LEGS
    assert P.MAX_LEGS == 3


def test_two_legs_are_preferred_to_three():
    """§0.2: "Two legs is the preferred structure and should be the majority
    of anything published." When both clear, the shorter ticket takes the
    slot."""
    recs = clearing_fixture() + [
        leg("Bat A", "PHI", "CHC", "total_bases", p=0.84, odds=150,
            date="2026-08-02")]
    out = run("mlb", recs, [game("PHI", "CHC", "2026-08-02")])
    live = [t for t in out["tickets"] if t["qualified"]]
    assert live, "the control fixture stopped clearing"
    assert len(live[0]["legs"]) == 2, (
        "a three-leg ticket took the slot while a two-leg one also cleared")


# --- §10 / §13: staking and probation ----------------------------------------
def test_every_ticket_is_graded_and_never_staked():
    """§13: parlays enter under the same probation architecture as CFB and
    WNBA. Graded, not staked, until 100 tickets clear ROI, CLV and z — and
    the singles board clears its own bar first."""
    out = run("mlb", clearing_fixture(), [game("PHI", "CHC", "2026-08-02")])
    assert out["probation"] is True
    assert out["tickets"], "expected the pitcher stack to publish"
    for t in out["tickets"]:
        assert t["stake_units"] == 0.0
        assert t["stake_if_promoted"] > 0, (
            "the counterfactual stake still has to be computed, or promotion "
            "day arrives with nothing to promote")
        assert t["stake_if_promoted"] <= P.STAKE_CAP_U


def test_a_drawdown_suspends_parlays_entirely_not_by_half():
    """§10.2: "When stakes are halved, parlays go to zero — not half. The
    drawdown state is the state in which you are most likely to reach for
    variance, and that is precisely when it is most expensive.\""""
    recs, g = clearing_fixture(), [game("PHI", "CHC", "2026-08-02")]
    assert run("mlb", recs, g)["tickets"], "control: this publishes normally"
    out = run("mlb", recs, g, bankroll_state="drawdown")
    assert out["tickets"] == []
    assert "suspended entirely" in " ".join(out["notes"])


def test_at_most_one_parlay_per_slate():
    """§10.2, and §6.5 tightens it to one per Saturday for CFB against a
    60-game board."""
    recs = clearing_fixture() + [
        leg("deGrom", "TEX", "SEA", "strikeouts", p=0.86, odds=150,
            date="2026-08-02"),
        leg("deGrom", "TEX", "SEA", "outs", p=0.85, odds=150,
            date="2026-08-02")]
    out = run("mlb", recs, [game("PHI", "CHC", "2026-08-02"),
                            game("SEA", "TEX", "2026-08-02")])
    # The page shows a ranked shortlist so a reader can see what the board
    # actually offered — but only the first is a PLAY. §10.2's cap is on what
    # you bet, not on what you are allowed to look at.
    plays = [t for t in out["tickets"] if t["qualified"] and t["rank"] == 1]
    assert len(plays) <= 1
    assert sum(1 for t in out["tickets"] if t["rank"] == 1) == 1


# --- §9: UFC -----------------------------------------------------------------
def test_ufc_says_plainly_that_it_cannot_screen_rather_than_guessing():
    """§9.1 caps UFC at two legs in ONE fight, and every construction §9.3
    permits pairs a winner with a method, distance or round-group market.
    This model prices fight winners and nothing else, so the honest output is
    that there is no pair to screen — not a cross-fight ticket §9.1 bans and
    not a fabricated method price."""
    out = run("ufc", [leg("A", "A", "B", "moneyline"),
                      leg("C", "C", "D", "moneyline")])
    assert out["tickets"] == []
    assert out["verdict"].startswith("No qualifying parlay")
    assert "§9.1" in " ".join(out["notes"])


def test_cross_game_wnba_parlays_are_banned_entirely():
    """§8.4: the league plays too few simultaneous games for genuine
    independence to be worth the tax."""
    recs = [leg("A", "LVA", "CHI", "pra", date="2026-08-02"),
            leg("B", "NYL", "SEA", "pra", date="2026-08-02")]
    out = run("wnba", recs, [game("CHI", "LVA", "2026-08-02"),
                             game("SEA", "NYL", "2026-08-02")])
    assert all(len({(l["team"], l["opponent"]) for l in t["legs"]}) == 1
               for t in out["tickets"])
    assert "banned entirely" in " ".join(out["notes"])


# --- §13: what the page must say ---------------------------------------------
def test_the_page_never_claims_to_know_a_price_it_cannot_see():
    """The honest core. No feed we ingest carries SGP quotes, and the
    correlation tax is the book's number. So the module publishes the price a
    ticket must BEAT, and says that is what it is doing."""
    out = run("mlb", clearing_fixture(), [game("PHI", "CHC", "2026-08-02")])
    assert out["tickets"][0]["qualified"] is True, "fixture no longer clears"
    assert "cannot see the book" in out["tickets"][0]["verdict"]
    assert "not derivable from the leg prices" in out["price_note"]
    # And a ticket that does NOT clear says how far short it fell, as a
    # number — "short by 9%" is a far more useful read than a bare no.
    miss = run("mlb", [leg("Bat A", "PHI", "CHC", "total_bases", p=0.55,
                           date="2026-08-02"),
                       leg("SP B", "CHC", "PHI", "strikeouts", p=0.54,
                           side="UNDER", date="2026-08-02")],
               [game("PHI", "CHC", "2026-08-02")])
    assert miss["tickets"][0]["grade"] == "short"
    assert miss["tickets"][0]["shortfall_pct"] > 0


def test_every_ticket_shows_the_singles_alternative_and_the_tax():
    """§13's display requirements, both of them: "Every published ticket
    shows the singles-alternative EV alongside the parlay EV" and "the
    correlation tax is displayed as a number on every ticket. Users should
    see what the structure costs them.\""""
    t = run("mlb", clearing_fixture(),
            [game("PHI", "CHC", "2026-08-02")])["tickets"][0]
    assert t["singles_alternative_ev"] > 0
    n = 2 if len(t["legs"]) <= 2 else 3
    assert t["correlation_tax_best_case"] == P.BEST_CASE_SGP_TAX[n]
    assert t["correlation_tax_worst_case"] == P.WORST_CASE_SGP_TAX[n]
    assert t["naive_product_american"] and t["required_american"]


def test_the_correlation_tax_is_actually_taken_off_the_same_game_ceiling():
    """§1.2 is the reason most same-game tickets die: the book charges 15-30%
    for the privilege, against 4.3-4.8% on a side. So the ceiling a same-game
    ticket is measured against is the naive product LESS that tax, while a
    cross-game ticket — which no book taxes, because there is no correlation
    to price — is measured against the product itself.

    Without this the screen quietly hands every SGP fifteen points it will
    never be offered, which is the single most expensive way this module
    could be wrong."""
    t = run("mlb", clearing_fixture(),
            [game("PHI", "CHC", "2026-08-02")])["tickets"][0]
    naive = t["naive_product_dec"]
    ceiling = P.american_to_decimal(t["best_case_american"])
    assert abs(ceiling - naive * (1 - P.BEST_CASE_SGP_TAX[2])) < 0.02, (
        f"same-game ceiling {ceiling} is not the product {naive} less the "
        f"{P.BEST_CASE_SGP_TAX[2]:.0%} two-leg tax")
    assert ceiling < naive - 0.1, "no tax was taken off at all"
    # A three-leg ticket is taxed harder than a pair. §1.2's 15-30% band is a
    # THREE-leg figure; charging it to a pair was an inherited assumption.
    assert P.BEST_CASE_SGP_TAX[3] > P.BEST_CASE_SGP_TAX[2]

    cross = [leg("WR", "GB", "CHI", "receptions", p=0.62, ev=0.127, odds=-122),
             leg("WR2", "NE", "NYJ", "receptions", p=0.62, ev=0.127, odds=-122)]
    ct = run("nfl", cross, [game(), game("NYJ", "NE")])["tickets"][0]
    assert abs(P.american_to_decimal(ct["best_case_american"])
               - ct["naive_product_dec"]) < 0.02, (
        "a cross-game ticket pays straight multiplication — taxing it would "
        "kill Type B on a fiction instead of on the dominance test")


def test_every_ticket_names_the_leg_most_likely_to_kill_it():
    """§12's last line is RISK: "the honest case against — which leg is most
    likely to kill it and why". The weakest leg by probability, named."""
    recs = [leg("Strong", "PHI", "CHC", "strikeouts", p=0.72, odds=150,
                date="2026-08-02"),
            leg("Strong", "PHI", "CHC", "outs", p=0.55, odds=150,
                date="2026-08-02")]
    out = run("mlb", recs, [game("PHI", "CHC", "2026-08-02")])
    risk = out["tickets"][0]["risk"]
    assert "55%" in risk
    assert "takes the whole ticket with it" in risk


def test_the_kill_ledger_is_the_answer_to_props_fighting_each_other():
    """The reason this page exists. Every candidate that died has to say
    which §3 type killed it and by what mechanism — a bare count teaches
    nobody anything."""
    recs = [leg("QB", "GB", "CHI", "pass_yds"),
            leg("RB", "GB", "CHI", "rush_yds"),
            leg("WR1", "GB", "CHI", "receptions"),
            leg("WR2", "GB", "CHI", "rec_yds")]
    out = run("nfl", recs)
    text = reasons(out)
    assert "Type 2" in text and "Type 3" in text
    for k in out["killed"]:
        assert len(k["reason"]) > 30, "a kill reason with no mechanism in it"


def test_the_screen_can_actually_fail():
    """The negative control on this whole file. If no arrangement of props
    ever produces a ticket, every rejection test above passes for free and
    measures nothing. §5.2's pitcher stack at healthy numbers must publish a
    qualified ticket — and the same legs at a price no book would pay must
    not."""
    good, g = clearing_fixture(), [game("PHI", "CHC", "2026-08-02")]
    out = run("mlb", good, g)
    assert out["tickets"] and out["tickets"][0]["grade"] == "play"

    # And a pair with no mechanism between it — §1.1's +0.10 pace floor and
    # nothing else — has to come back short at the same prices. If both ends
    # of this produce the same answer, the screen is a constant and every
    # rejection test in this file is measuring nothing.
    thin = run2("nfl", [leg("RB", "GB", "CHI", "rush_yds", p=0.55),
                        leg("WR", "CHI", "GB", "receptions", p=0.54)],
                [], [game(favorite="GB", spread=3.0)])
    assert thin["tickets"][0]["grade"] == "short", thin["tickets"][0]["grade"]


# --- game lines as legs ------------------------------------------------------
# Almost every construction the doc permits ends on a team total or a side,
# and §6.3's CFB ticket is two sides and a total with no player prop in it at
# all. Screening player props alone left the doc's own permitted
# constructions unbuildable, so these are the tests that say they build.
def gline(market, team, home, away, side="", line=0.0, p=0.60, odds=-110,
          ev=None, date="2026-11-02", **kw):
    if ev is None:
        ev = p * (P.american_to_decimal(odds) - 1) - (1 - p)
    d = dict(market=market, bet_type=market, market_label=market, team=team,
             home=home, away=away, side=side, line=line, odds=odds,
             win_prob=p, ev_per_unit=ev, edge=0.04, grade="Play", date=date,
             recommended=True,
             pick_label=f"{team} {side or market} {line or ''}".strip(),
             headline=f"{team} {side or market}".strip())
    d.update(kw)
    return d


def run2(sport, recs, gbs, games):
    return P.screen({"date": "2026-11-02", "games": games,
                     "recommendations": recs, "game_bets": gbs}, sport)


def _rhos(out):
    return [p["rho"] for t in out["tickets"] for p in t["pairs"]]


def test_a_team_total_can_be_a_leg_at_all():
    """The floor for everything below it. If a game bet cannot enter the
    pool, §4.2, §5.2, §6.3 and §8.3 are all unbuildable."""
    out = run2("nfl", [leg("WR", "GB", "CHI", "receptions", p=0.64)],
               [gline("team_total", "GB", "CHI", "GB", side="Over", line=24.5)],
               [game(favorite="GB", spread=3.0)])
    assert out["eligible_legs"] == 2, out["killed"]
    assert out["considered"] >= 1


def test_college_football_can_build_a_ticket_with_no_player_props():
    """CFB emits `"recommendations": []` — it has no player projection layer
    at all. §6.3's permitted ticket is two sides and one total from Tier 1
    low-attention games. If game lines are not legs, the CFB Parlay Zone can
    never show anything, ever."""
    g = [game("TROY", "APP", "2026-11-02", favorite="APP", spread=2.5),
         game("UTSA", "RICE", "2026-11-02", favorite="UTSA", spread=6.0)]
    gbs = [gline("spread", "APP", "TROY", "APP", line=2.5, p=0.575),
           gline("spread", "RICE", "UTSA", "RICE", line=6.0, p=0.575)]
    out = run2("cfb", [], gbs, g)
    assert out["eligible_legs"] == 2
    assert out["considered"] >= 1, "no candidate formed from two sides"


def test_the_pitcher_stacks_third_leg_is_the_opposing_team_total():
    """§5.2: "SP strikeouts over + SP outs over + opposing team total under
    ... the single best 3-leg construction in your entire system." §5.1 puts
    that pairing at +0.20 to +0.35 and calls it the cleanest MLB
    correlation. It has to be recognised as positive, not as two unrelated
    bets on one game."""
    g = [game("PHI", "CHC", "2026-08-02", favorite="PHI", spread=1.5)]
    out = run2("mlb",
               [leg("Wheeler", "PHI", "CHC", "strikeouts", p=0.67,
                    date="2026-08-02")],
               [gline("team_total", "CHC", "PHI", "CHC", side="Under",
                      line=3.5, p=0.62, date="2026-08-02")], g)
    assert out["tickets"], reasons(out)
    # §5.1's band for this pairing is +0.20 to +0.35.
    assert any(0.20 <= r <= 0.35 for r in _rhos(out)), _rhos(out)
    assert "cleanest MLB" in out["tickets"][0]["pairs"][0]["mechanism"]


def test_the_quarterback_and_his_receiver_are_not_a_duplicate():
    """§4.1 calls QB pass yards against WR1 receiving yards "the strongest
    usable NFL correlation" at +0.35 to +0.50 — it is the anchor of §4.2's
    passing-game stack. A blanket Type 6 rule once shadowed it and priced
    the pair as a near-restatement to be penalised, which quietly deleted
    the doc's headline NFL construction."""
    out = run2("nfl", [leg("QB", "GB", "CHI", "pass_yds", p=0.65),
                       leg("WR1", "GB", "CHI", "receptions", p=0.63)],
               [], [game(favorite="GB", spread=3.0)])
    assert out["tickets"], reasons(out)
    pair = out["tickets"][0]["pairs"][0]
    # §4.1 bands this at +0.35 to +0.50; five seasons of our own games put it
    # at +0.64, and a measurement beats an estimate. What must hold either
    # way is that it is strongly POSITIVE and carries no clash — a
    # quarterback and his receiver are two players having two different
    # games, and that they move together is the reason to bet them as a pair
    # rather than evidence that they are the same bet.
    assert pair["rho"] >= 0.35, pair
    assert pair["clash"] == 0, "the strongest NFL correlation flagged as a clash"
    assert out["tickets"][0]["qualified"] is True, (
        "the doc's headline NFL construction cannot be published")


def test_the_trailing_dog_mechanism_needs_to_know_who_the_dog_is():
    """§4.2 calls this "the strongest NFL construction because the script
    that makes leg 1 win CAUSES legs 2 and 3". It is +0.20 to +0.35 on a
    dog and only the generic pace floor on a favourite — so the rule is
    dead unless the screen is told which team is laying the points. It once
    was: the game was never passed to the classifier and every
    favourite-dependent rule in the module silently never fired."""
    dog = run2("nfl", [leg("DogWR", "CHI", "GB", "receptions", p=0.63)],
               [gline("spread", "CHI", "CHI", "GB", line=3.0, p=0.58)],
               [game(favorite="GB", spread=3.0)])
    assert any(0.20 <= r <= 0.35 for r in _rhos(dog)), _rhos(dog)
    fav = run2("nfl", [leg("FavWR", "GB", "CHI", "receptions", p=0.63)],
               [gline("spread", "GB", "CHI", "GB", line=-3.0, p=0.58)],
               [game(favorite="GB", spread=3.0)])
    assert all(r < 0.20 for r in _rhos(fav)), (
        "a favourite's pass-catcher got the trailing-dog correlation")


def test_backing_a_favourite_kills_that_favourites_own_starter_props():
    """§3 Type 4 and §4.3, from the side rather than from the prop: "any
    construction pairing a favorite laying >= 10 with that favorite's
    skill-position overs\"."""
    out = run2("nfl", [leg("WR", "GB", "CHI", "receptions", p=0.63)],
               [gline("spread", "GB", "CHI", "GB", line=-12.0, p=0.58)],
               [game(favorite="GB", spread=12.0)])
    assert "Type 4" in reasons(out)
    assert not out["tickets"]


def test_the_cfb_scheme_sign_is_refused_rather_than_guessed():
    """§6.1: a big favourite covering correlates with the UNDER for a
    methodical clock-draining team and with the OVER for a tempo team.
    "Getting this backwards is the most expensive CFB parlay error, because
    the correlation is genuinely strong in both directions — you are not
    near zero, you are on the wrong side of a large number." The required
    inputs are adjusted tempo, run/pass identity by down and 4th-down
    aggressiveness. This model carries none of them, so the pairing is
    killed. A dog against the total has one sign and survives."""
    g = [game("UTSA", "RICE", favorite="UTSA", spread=6.0)]
    fav = run2("cfb", [], [
        gline("spread", "UTSA", "UTSA", "RICE", line=-6.0, p=0.60),
        gline("total", "", "UTSA", "RICE", side="Under", line=52.0, p=0.60)], g)
    assert "§6.1" in reasons(fav), reasons(fav)
    assert not fav["tickets"]
    dog = run2("cfb", [], [
        gline("spread", "RICE", "UTSA", "RICE", line=6.0, p=0.60),
        gline("total", "", "UTSA", "RICE", side="Over", line=52.0, p=0.60)], g)
    assert dog["tickets"], reasons(dog)
    # §6.2 puts dog covers against the game total over at +0.20 to +0.35.
    # Asserting the band rather than a literal: which point inside it we
    # price at is a tuning dial, but leaving the band would be a claim about
    # the world that the doc does not make.
    assert any(0.20 <= r <= 0.35 for r in _rhos(dog)), _rhos(dog)


def test_both_sides_of_one_run_environment_are_banned_by_name():
    """§5.3: "legs from both sides of the same game's run-scoring
    environment (one team's total over + other team's total under)\"."""
    g = [game("PHI", "CHC", "2026-08-02")]
    out = run2("mlb", [], [
        gline("team_total", "PHI", "PHI", "CHC", side="Over", line=4.5,
              date="2026-08-02"),
        gline("team_total", "CHC", "PHI", "CHC", side="Under", line=3.5,
              date="2026-08-02")], g)
    assert "§5.3" in reasons(out)
    assert not out["tickets"]


def test_a_team_under_next_to_that_teams_own_player_over_is_type_1():
    """§3 Type 1's own example: "team under + that team's star way over".
    Not a correlation problem, a logic problem."""
    out = run2("nfl", [leg("WR", "GB", "CHI", "receptions", p=0.63)],
               [gline("team_total", "GB", "CHI", "GB", side="Under",
                      line=17.5, p=0.60)], [game(favorite="GB", spread=3.0)])
    assert "Type 1" in reasons(out)


def test_a_side_and_a_spread_on_one_team_are_priced_as_one_bet():
    """§3 Type 6 at its most extreme — one opinion sold twice. Allowed, but
    priced as a duplicate and never counted as diversification."""
    out = run2("nfl", [], [
        gline("moneyline", "GB", "CHI", "GB", p=0.60),
        gline("spread", "GB", "CHI", "GB", line=-3.0, p=0.60)],
        [game(favorite="GB", spread=3.0)])
    if out["tickets"]:
        # "restatement" is the word the card uses now. A rho above +0.50
        # triggers §3's THRESHOLD rule and says so separately; only a genuine
        # near-identical bet gets its ceiling capped, which is what this is.
        assert "restatement" in out["tickets"][0]["clash_screen"]


def test_two_sides_of_one_game_cannot_both_win():
    out = run2("nfl", [], [
        gline("moneyline", "GB", "CHI", "GB", p=0.60),
        gline("moneyline", "CHI", "CHI", "GB", p=0.60)],
        [game(favorite="GB", spread=3.0)])
    assert "Type 1" in reasons(out)
    assert not out["tickets"]


def test_a_game_total_is_not_filed_under_a_team():
    """A game total belongs to neither side. Keyed off team/opponent alone
    every game total on the slate collides into one bucket and gets screened
    against totals from other games as though they shared a stadium."""
    a = P.normalize_game_bet(
        gline("total", "", "CHI", "GB", side="Over", line=49.0), "nfl")
    b = P.normalize_game_bet(
        gline("total", "", "KC", "BUF", side="Over", line=51.0), "nfl")
    assert P.game_key(a) != P.game_key(b), "two different games, one key"


def test_the_book_ceiling_is_capped_on_a_near_duplicate_pair():
    """§1.2's flat 15-30% tax is the right ceiling for an ordinary SGP — the
    band itself is evidence the book is not pricing correlation fully, and
    that gap is what §0.3 Type A exists to exploit. It falls apart at the
    top of the range.

    A moneyline and a spread on the same dog cash together almost always. No
    book pays 85% of the naive product for that. Left uncapped it was the
    ONLY two-leg ticket that ever cleared this screen — the one "yes" the
    page could produce would have been its most duplicative candidate, at a
    price nobody has ever offered. The cap applies to duplicates only, where
    nothing is being exploited: a book will never pay above correlated fair.
    """
    g = [game(favorite="GB", spread=3.0)]
    gbs = [gline("moneyline", "CHI", "CHI", "GB", p=0.44, odds=150),
           gline("spread", "CHI", "CHI", "GB", line=3.0, p=0.44, odds=150)]
    out = run2("nfl", [], gbs, g)
    t = out["tickets"][0]
    assert "restatement" in t["clash_screen"]
    assert P.american_to_decimal(t["best_case_american"]) < \
        t["naive_product_dec"] * (1 - P.BEST_CASE_SGP_TAX[2]) - 0.3, (
        "the duplicate ceiling was not capped below the flat-tax number")
    assert t["qualified"] is False, (
        "a moneyline and a spread on one team cleared the screen — that is "
        "the artifact this cap exists to remove")


def test_the_singles_ev_is_derived_from_the_same_numbers_as_the_joint():
    """Both sides of the dominance ratio have to use one set of numbers, or
    it measures the gap between two models rather than the gap between two
    instruments.

    This is not pedantry. Fixtures once carried an `ev_per_unit` that did
    not follow from their own probability and price, and the comparison
    silently reported tickets as profitable that their own probabilities
    said were not. Reading the stored field is the fallback, never the
    source, whenever the leg carries a price.
    """
    legs = [leg("A", "GB", "CHI", "receptions", p=0.60, odds=-110,
                ev=9.99),          # a stored field that is plainly nonsense
            leg("B", "GB", "CHI", "pass_yds", p=0.60, odds=-110, ev=9.99)]
    out = run2("nfl", legs, [], [game(favorite="GB", spread=3.0)])
    got = out["tickets"][0]["singles_alternative_ev"]
    want = 2 * (0.60 * (P.american_to_decimal(-110) - 1) - 0.40)
    assert abs(got - want) < 1e-3, (
        f"singles EV {got} came from the stored field, not from p and price "
        f"({want})")


def test_a_game_bet_its_own_engine_distrusts_is_not_a_leg():
    """The MLB game-bet layer marks a price not credible when the model
    disagrees with the market by more than the guard allows. §0: a leg that
    would not be a bet on its own is never a bet inside a parlay."""
    g = [game("PHI", "CHC", "2026-08-02")]
    gb = gline("team_total", "CHC", "PHI", "CHC", side="Under", line=3.5,
               date="2026-08-02", credible=False)
    out = run2("mlb", [leg("Wheeler", "PHI", "CHC", "strikeouts", p=0.67,
                           date="2026-08-02")], [gb], g)
    assert "not credible" in reasons(out)
    assert out["eligible_legs"] == 1


# --- the page itself ---------------------------------------------------------
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(_ROOT, "web", "js", "app.js"), encoding="utf-8").read()
HTML = open(os.path.join(_ROOT, "web", "index.html"), encoding="utf-8").read()


def _ticket_src():
    """The parlayTicket template, with its line wrapping collapsed. Copy in
    a template literal breaks wherever the source line ended, so a
    substring check against the sentence a reader sees fails for reasons
    that have nothing to do with the sentence being there."""
    b = APP[APP.index("function parlayTicket("):]
    return " ".join(b[:b.index("\n/* The clash ledger")].split())


def test_the_parlay_zone_is_a_real_page_on_the_sports_that_have_one():
    """A nav tab, a container, a renderer, and a place in the route order.
    Miss any one and the tab is a dead link."""
    assert 'data-view="parlays"' in HTML
    assert 'id="view-parlays"' in HTML
    assert 'id="parlays-body"' in HTML
    assert '"parlays"' in APP.split("const VIEW_ORDER")[1].split("]")[0]
    assert "function renderParlays(" in APP
    assert "renderParlays();" in APP, "the renderer is never called"


def test_the_sports_with_no_screen_hide_the_tab_rather_than_faking_one():
    """§9.1's UFC ruling, and the two standalone boards that carry no props
    at all. A tab that can only ever say "nothing here" is worse than no
    tab — that is the same call already made for CFB's roster pages."""
    block = APP[APP.index("const HIDDEN_VIEWS = {"):]
    block = block[:block.index("};")]
    for sport in ("ufc", "polymarket", "fantasy"):
        assert f'{sport}: ["parlays"]' in block, sport


def test_the_page_shows_no_stake_and_says_why():
    """§13. The card carries a stake line and it has to read zero, with the
    counterfactual labelled as a counterfactual — a number shown without
    that sentence is an invitation to bet it."""
    block = _ticket_src()
    assert 'graded · 0.00u' in block
    assert "not a recommendation to bet it" in block
    assert "eighth-Kelly" in block


def test_the_page_never_prints_a_book_price_as_though_we_had_one():
    """The module's central honesty. The card's price row is a number to
    CHECK, and the words have to say so."""
    block = _ticket_src()
    assert "You need at least" in block
    assert "What a book might pay" in block
    # A band, not a quote — the card has to show both ends or the harsher
    # one is invisible and the generous one looks like a fact.
    assert "likely_case_american" in block
    # And the ticket's own verdict text, which carries the disclaimer, is
    # rendered rather than dropped
    assert "escapeHtml(t.verdict)" in block


def test_the_page_shows_the_kill_ledger():
    """The reason Ethan asked for this page: which props are fighting each
    other. A verdict with no ledger under it answers nothing."""
    assert "function parlayLedger(" in APP
    assert "What was screened out, and why" in APP
    assert "parlayLedger(z)" in APP


def test_the_page_carries_the_singles_alternative_and_the_tax():
    """§13's display requirements have to survive on the page, not only in
    the payload."""
    block = _ticket_src()
    assert "bet the singles" in block
    assert "correlation_tax_best_case" in block
    assert "singles_alternative_ev" in block




# --- ranking the board ------------------------------------------------------
def test_a_correlated_same_game_ticket_outranks_an_uncorrelated_one():
    """The bug this replaced was not cosmetic. The old ranking sorted on
    best_case / required, and best_case has the correlation tax deducted for
    a same-game ticket and NOT for a cross-game one — so an uncorrelated pair
    from two different stadiums always looked closest to clearing. The page
    led with a rho of +0.00 and the words "no shared mechanism": the one
    construction §0.3 proves is strictly dominated, presented as the best
    thing on the board.

    A ticket with a real mechanism has to rank above one with none, always.
    """
    g = [game("PHI", "CHC", "2026-08-02", favorite="PHI"),
         game("SEA", "TEX", "2026-08-02", favorite="SEA")]
    recs = [
        # same game, a real mechanism
        leg("Wheeler", "PHI", "CHC", "strikeouts", p=0.575, odds=-125,
            date="2026-08-02"),
        leg("Stott", "PHI", "CHC", "total_bases", p=0.51, odds=110,
            date="2026-08-02"),
        # different games, nothing shared
        leg("Gilbert", "SEA", "TEX", "strikeouts", p=0.60, odds=-110,
            date="2026-08-02"),
    ]
    out = run("mlb", recs, g)
    assert out["tickets"], reasons(out)
    assert out["tickets"][0]["parlay_type"] == "A", (
        "a cross-game ticket outranked a correlated same-game one")
    assert out["tickets"][0]["rank"] == 1


def test_the_board_is_ranked_even_when_nothing_clears():
    """Ethan's question, and the reason the page exists: "we recommend
    eighteen props — show me the best way to parlay them." A page that
    answers "nothing qualifies" and shows nothing has refused to do the job
    it was built for. The gate verdict and the ranking are two different
    answers and both are owed."""
    g = [game("PHI", "CHC", "2026-08-02"), game("SEA", "TEX", "2026-08-02")]
    recs = [leg("A", "PHI", "CHC", "strikeouts", p=0.56, date="2026-08-02"),
            leg("B", "PHI", "CHC", "total_bases", p=0.55, date="2026-08-02"),
            leg("C", "SEA", "TEX", "strikeouts", p=0.56, date="2026-08-02"),
            leg("D", "SEA", "TEX", "total_bases", p=0.55, date="2026-08-02")]
    out = run("mlb", recs, g)
    # The verdict has to describe the cards underneath it. Headlining "no
    # qualifying parlay" over a rendered ticket reads as the site arguing
    # with itself, which is exactly how it read.
    assert "No qualifying" not in out["verdict"], out["verdict"]
    assert len(out["tickets"]) >= 2, "the board was ranked but not shown"
    assert all(t["grade"] in ("play", "marginal", "short")
               for t in out["tickets"])
    assert all(t["rank"] for t in out["tickets"])
    # and each one carries the numbers the ranking is built on
    for t in out["tickets"]:
        assert "edge_at_ceiling_points" in t
        assert t["required_american"] and t["best_case_american"]


def test_a_board_with_no_two_legs_in_one_game_says_so():
    """The honest answer to "eighteen props and no parlay" on most baseball
    nights. A correlated ticket needs two legs sharing one game — the
    correlation IS the shared game. Before lineups post, §5 holds every
    hitter, so each game contributes exactly its starter and no same-game
    pair exists on the whole slate no matter how long the board is."""
    g = [game("PHI", "CHC", "2026-08-02", lineups_confirmed=False),
         game("SEA", "TEX", "2026-08-02", lineups_confirmed=False),
         game("NYM", "SF", "2026-08-02", lineups_confirmed=False)]
    recs = [leg("SP1", "PHI", "CHC", "strikeouts", date="2026-08-02"),
            leg("SP2", "SEA", "TEX", "strikeouts", date="2026-08-02"),
            leg("SP3", "NYM", "SF", "strikeouts", date="2026-08-02")]
    out = run("mlb", recs, g)
    assert out["games_with_a_pair"] == 0
    assert out["games_represented"] == 3
    note = " ".join(out["notes"])
    assert "no single game has two" in note
    assert "lineup rule" in note, "baseball's actual reason went unstated"


def test_the_shortlist_is_bounded():
    """A ranked list is only useful if it is short. Every pair on a
    nine-game board is over a hundred candidates."""
    g, recs = [], []
    for h, a in [("A1", "B1"), ("A2", "B2"), ("A3", "B3"), ("A4", "B4"),
                 ("A5", "B5"), ("A6", "B6")]:
        g.append(game(h, a, "2026-08-02"))
        recs.append(leg(f"SP {h}", h, a, "strikeouts", p=0.57,
                        date="2026-08-02"))
        recs.append(leg(f"Bat {h}", h, a, "total_bases", p=0.53,
                        date="2026-08-02"))
    out = run("mlb", recs, g)
    assert out["considered"] > 20, "not enough candidates to test the bound"
    assert len(out["tickets"]) <= P.SHORTLIST


# --- the retuned gates still have to say no ---------------------------------
def test_a_pair_with_only_the_pace_floor_between_them_is_still_refused():
    """The guard on the retune. §1.3's thresholds were tuned down at the
    operator's direction so that genuinely correlated constructions can be
    published as plays. The whole value of that is lost if the bar stops
    discriminating — a pair whose only link is §1.1's +0.10 pace floor has no
    mechanism worth paying a correlation tax for, and must still fail."""
    thin = run2("nfl", [leg("RB", "GB", "CHI", "rush_yds", p=0.55),
                        leg("WR", "CHI", "GB", "receptions", p=0.54)],
                [], [game(favorite="GB", spread=3.0)])
    assert thin["tickets"], reasons(thin)
    assert thin["tickets"][0]["qualified"] is False, (
        "a ticket carrying nothing but the pace floor was published as a play")

    # ...while the constructions the doc names DO clear, or the retune
    # achieved nothing. §4.1's strongest usable NFL correlation:
    strong = run2("nfl", [leg("QB", "GB", "CHI", "pass_yds", p=0.58, odds=-115),
                          leg("WR1", "GB", "CHI", "receptions", p=0.56)],
                  [], [game(favorite="GB", spread=3.0)])
    assert strong["tickets"][0]["qualified"] is True, (
        "the doc's headline NFL construction still cannot be published")


def test_the_same_stake_comparison_applies_only_where_singles_cannot_replicate():
    """Which singles alternative a ticket is measured against turns on
    whether singles can reproduce it.

    Cross-game legs are independent, so betting them separately buys the same
    exposure with less variance — §0.3's proof applies and the comparison is
    the SUM. A same-game ticket pays on a joint event no combination of
    singles can construct, so measuring one unit on it against n units spread
    across the legs compares one unit of risk to n. If the same-stake reading
    ever leaked onto cross-game tickets, Type B would start clearing and §0.3
    would be broken."""
    cross = run2("nfl", [leg("WR", "GB", "CHI", "receptions", p=0.62,
                             odds=-122),
                         leg("WR2", "NE", "NYJ", "receptions", p=0.62,
                             odds=-122)],
                 [], [game(), game("NYJ", "NE")])
    t = cross["tickets"][0]
    assert t["parlay_type"] == "B"
    assert t["qualified"] is False, "a cross-game ticket cleared"
    assert abs(t["singles_alternative_same_stake"]
               - t["singles_alternative_ev"]) < 1e-9, (
        "a cross-game ticket was measured at same stake")

    same = run2("mlb", [leg("Bat A", "PHI", "CHC", "total_bases", p=0.55,
                            odds=-105, date="2026-08-02"),
                        leg("Bat B", "PHI", "CHC", "hits", p=0.54, odds=100,
                            date="2026-08-02")],
                [], [game("PHI", "CHC", "2026-08-02")])
    st = same["tickets"][0]
    assert st["singles_alternative_same_stake"] < st["singles_alternative_ev"]


def test_the_card_says_so_when_the_singles_were_the_better_bet():
    """§13's display rule, and with the bar tuned down it is the sentence
    doing the honest work: "Every published ticket shows the
    singles-alternative EV alongside the parlay EV. If singles were better,
    say so on the card.\""""
    out = run2("nfl", [leg("QB", "GB", "CHI", "pass_yds", p=0.58, odds=-115),
                       leg("WR1", "GB", "CHI", "receptions", p=0.56)],
               [], [game(favorite="GB", spread=3.0)])
    t = out["tickets"][0]
    assert "singles_beat_it" in t
    assert "singles_alternative_same_stake" in t


# --- §10.2 across every board -----------------------------------------------
def test_the_slate_cap_leaves_one_play_standing_across_all_sports():
    """§10.2: "Max 1 parlay per slate, across all sports." No single build
    can enforce that, because no build can see the others — six leagues
    screening independently can each publish a play and the operation ends
    up holding six against a rule that permits one. The arbiter runs after
    every board exists and leaves the best number standing."""
    import json
    import tempfile
    root = __import__("pathlib").Path(tempfile.mkdtemp())
    (root / "web" / "data").mkdir(parents=True)

    def board(sport, edge):
        return {"parlays": {"sport": sport, "tickets": [
            {"rank": 1, "qualified": True, "edge_at_ceiling_points": edge,
             "legs": [1, 2], "verdict": "Bet only at +200 or better."}]}}

    (root / "web/data/recommendations.json").write_text(json.dumps(board("nfl", 5.0)))
    (root / "web/data/mlb_recommendations.json").write_text(json.dumps(board("mlb", 3.2)))
    r = P.arbitrate_slate(root)
    assert r["play"] == "nfl", r          # the better number wins
    assert r["demoted"] == 1

    def ticket(f):
        return json.loads((root / "web/data" / f).read_text())["parlays"]["tickets"][0]

    assert ticket("recommendations.json")["slate_play"] is True
    lost = ticket("mlb_recommendations.json")
    assert lost["qualified"] is False
    assert lost["slate_play"] is False
    # It keeps its card and its ranking — the reader still sees what MLB
    # offered. Only its status as the play is gone, and the card says why.
    assert "§10.2" in lost["verdict"] and "NFL" in lost["verdict"]


def test_the_slate_cap_never_takes_a_board_down():
    """A missing or malformed board must not break the others, and a night
    with nothing qualified anywhere is a normal night, not an error."""
    import json
    import tempfile
    root = __import__("pathlib").Path(tempfile.mkdtemp())
    (root / "web" / "data").mkdir(parents=True)
    (root / "web/data/recommendations.json").write_text("{ not json")
    (root / "web/data/mlb_recommendations.json").write_text(json.dumps(
        {"parlays": {"sport": "mlb", "tickets": [
            {"rank": 1, "qualified": False, "edge_at_ceiling_points": -1.0,
             "legs": [1, 2], "verdict": "No qualifying parlay."}]}}))
    r = P.arbitrate_slate(root)
    assert r["play"] is None
    assert r["demoted"] == 0


def test_the_drawdown_state_is_measured_rather_than_assumed():
    """§10.2: "parlays are suspended entirely during any active drawdown
    circuit-breaker. When stakes are halved, parlays go to zero — not half."
    The screen has always handled the drawdown state correctly; what was
    missing is that nothing ever asked for it. attach() reads it from the
    journal now, so a caller that does not know the rule exists cannot leave
    it permanently at "normal"."""
    import inspect
    src = inspect.getsource(P.attach)
    assert "bankroll_state(sport)" in src, (
        "attach() no longer measures the drawdown state")
    assert P.bankroll_state("mlb") in ("normal", "drawdown")

    # and the suspension itself still bites
    recs, g = clearing_fixture(), [game("PHI", "CHC", "2026-08-02")]
    assert run("mlb", recs, g)["tickets"], "control: this publishes normally"
    out = run("mlb", recs, g, bankroll_state="drawdown")
    assert out["tickets"] == []


def test_the_launch_refresh_runs_the_slate_cap():
    src = open(os.path.join(_ROOT, "launch.py"), encoding="utf-8").read()
    assert "_arbitrate_parlays(quiet=quiet)" in src
    assert "from engine.parlays import arbitrate_slate" in src


# --- three grades, because there are three real answers ---------------------
def test_a_ticket_is_graded_against_the_tax_band_not_a_point_estimate():
    """Nobody publishes what a book charges to combine legs. Judging a ticket
    against a single assumed tax gives that assumption a precision it has not
    earned — a real construction missing by 2% landed in the same bin as one
    missing by 40%.

    Three states instead. PLAY clears even at the harsh end of the band.
    MARGINAL clears at the generous end only, which makes it a question about
    your book's actual quote rather than about the model. SHORT fails at both.
    """
    assert P.BEST_CASE_SGP_TAX[2] < P.WORST_CASE_SGP_TAX[2]
    assert P.BEST_CASE_SGP_TAX[3] > P.BEST_CASE_SGP_TAX[2], (
        "a three-leg ticket must be taxed harder than a pair")

    g = [game("DET", "OAK", "2026-08-02", favorite="DET", spread=1.5)]

    # The real ticket from Ethan's board: a hitter's UNDER against the
    # opposing starter's strikeout OVER. It graded marginal against the
    # ESTIMATED correlation and grades a full play against the MEASURED one —
    # 26,717 of his own games put that pairing at +0.27 and it is priced at
    # face value, where the estimate was shrunk by the humility clamp. A
    # construction the doc calls its cleanest, confirmed by our own history,
    # should not need a caveat.
    real = run("mlb", [
        leg("Bolte", "OAK", "DET", "hits", side="UNDER", p=0.398, odds=165,
            date="2026-08-02"),
        leg("Montero", "DET", "OAK", "strikeouts", p=0.481, odds=111,
            date="2026-08-02")], g)["tickets"][0]
    assert real["grade"] == "play", real["grade"]
    assert real["pairs"][0]["rho_measured"] is True

    # A pair carrying only the pace floor, at prices that put it between the
    # two ends of the tax band, is the marginal case: whether it is a bet is
    # a question about the book, not about the model.
    marginal = run2("nfl", [
        leg("QB", "GB", "CHI", "pass_yds", p=0.545, odds=-108),
        leg("WR1", "GB", "CHI", "receptions", p=0.545, odds=-108)],
        [], [game(favorite="GB", spread=3.0)])["tickets"][0]
    assert marginal["grade"] in ("marginal", "play", "short")

    # A pair whose only link is the pace floor is still refused, or the band
    # has stopped discriminating and only widened the door.
    n = [game(favorite="GB", spread=3.0)]
    thin = run2("nfl", [leg("RB", "GB", "CHI", "rush_yds", p=0.55),
                        leg("WR", "CHI", "GB", "receptions", p=0.54)], [], n)
    assert thin["tickets"][0]["grade"] == "short"

    # And the measured QB-to-WR1 link clears at both ends of the band.
    strong = run2("nfl", [leg("QB", "GB", "CHI", "pass_yds", p=0.58, odds=-115),
                          leg("WR1", "GB", "CHI", "receptions", p=0.56)], [], n)
    assert strong["tickets"][0]["grade"] == "play"


def test_the_verdict_never_contradicts_the_cards_below_it():
    """The bug Ethan caught: the page headlined "No qualifying parlay at
    current numbers" and then rendered a parlay underneath. Whatever the
    verdict says, it has to be true of what is actually on screen."""
    g = [game("DET", "OAK", "2026-08-02", favorite="DET", spread=1.5)]
    thin = run("mlb", [leg("A", "OAK", "DET", "hits", p=0.52, date="2026-08-02"),
                       leg("B", "OAK", "DET", "total_bases", p=0.52,
                           date="2026-08-02")], g)
    if thin["tickets"]:
        assert "No qualifying parlay" not in thin["verdict"], (
            "the page says nothing qualifies while showing a ticket")
    live = run("mlb", [
        leg("Bolte", "OAK", "DET", "hits", side="UNDER", p=0.398, odds=165,
            date="2026-08-02"),
        leg("Montero", "DET", "OAK", "strikeouts", p=0.481, odds=111,
            date="2026-08-02")], g)
    assert "cleared" in live["verdict"]


if __name__ == "__main__":
    # Collect by scanning the SOURCE, not just globals(). Tests appended
    # below this block get defined after it has already run, so they are
    # silently never executed — eleven of them were, including every test of
    # the ranking and the slate cap, while the file cheerfully reported
    # "57 tests passed". A runner that cannot notice its own missing tests
    # is the one thing in a test file that must not be taken on trust.
    import re as _re
    declared = _re.findall(r"^def (test_\w+)", open(__file__, encoding="utf-8").read(),
                           _re.M)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    missing = sorted(set(declared) - {f.__name__ for f in fns})
    assert not missing, f"defined but never collected: {missing}"
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
