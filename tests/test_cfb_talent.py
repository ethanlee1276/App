"""The preseason prior: high-school recruiting, and where it stops.

A results-only rating in September is not neutral — with two games played
against opponents nobody has measured either, shrinking toward the league
mean asserts that an unproven Alabama and an unproven Kent State are both
average. The market does not believe that, and it will happily take money
from a model that does. So the load-bearing test here is the one showing
two teams with near-identical two-game records separating once recruiting
is priced.

The other half is where the prior is NOT allowed to go. It must decay to
almost nothing by November, it must never touch the offense/defense split
the totals model reads, and its slope must be fitted or labelled — a
talent-to-points coefficient is exactly the kind of number that looks
authoritative and is invented.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine.cfb import talent as T
from engine.sources import cfbd
from engine.teamrates import TeamRating

TALENT = {"BAMA": 980.0, "OSU": 975.0, "UGA": 960.0, "MICH": 930.0,
          "APP": 600.0, "TOL": 560.0, "BGSU": 520.0, "KENT": 480.0}


# --- the claim the module exists for ----------------------------------------
def test_two_unproven_teams_separate_once_recruiting_is_priced():
    ratings = {"BAMA": TeamRating(net=1.0, off=3.0, def_=2.0, games=2),
               "KENT": TeamRating(net=0.5, off=1.0, def_=0.5, games=2)}
    prior = T.talent_prior(TALENT)
    blended, _ = T.apply_prior(ratings, prior)
    results_gap = ratings["BAMA"].net - ratings["KENT"].net
    blended_gap = blended["BAMA"].net - blended["KENT"].net
    assert results_gap < 1.0, "two games say almost nothing — that's the premise"
    assert blended_gap > results_gap + 2.0, "the prior did no work"


def test_the_prior_decays_to_almost_nothing_by_november():
    assert T.prior_weight(0) == 1.0            # nothing has happened yet
    assert 0.20 <= T.prior_weight(2) <= 0.25
    assert T.prior_weight(10) <= T.PRIOR_FLOOR + 1e-9
    assert T.prior_weight(12) == T.prior_weight(10)
    # Monotone: evidence never makes the prior matter MORE.
    weights = [T.prior_weight(n) for n in range(1, 13)]
    assert weights == sorted(weights, reverse=True)


def test_returning_production_changes_the_decay_not_the_rating():
    """A talented team returning nobody is less predictable, not worse."""
    thin = T.prior_weight(4, returning=0.2)
    deep = T.prior_weight(4, returning=0.8)
    assert thin < T.prior_weight(4) < deep
    # …and it never flips the sign or runs away with the projection.
    assert 0.0 < thin < 1.0 and 0.0 < deep < 1.0


def test_the_prior_never_touches_the_totals_model():
    """A recruiting composite says a roster is good, not that it scores 34
    a game. Fabricating an offense/defense split would put an invented
    number into every total on the board."""
    ratings = {"BAMA": TeamRating(net=1.0, off=3.0, def_=2.0, games=2)}
    blended, _ = T.apply_prior(ratings, T.talent_prior(TALENT))
    assert blended["BAMA"].net != ratings["BAMA"].net
    assert blended["BAMA"].off == ratings["BAMA"].off
    assert blended["BAMA"].def_ == ratings["BAMA"].def_


def test_a_team_with_no_talent_row_keeps_its_own_rating():
    ratings = {"XYZ": TeamRating(net=2.0, off=1.0, def_=-1.0, games=6)}
    blended, report = T.apply_prior(ratings, T.talent_prior(TALENT))
    assert blended["XYZ"].net == 2.0
    assert report["results_only"] == 1


# --- the slope is measured, or it says so -----------------------------------
def test_an_unfitted_slope_says_it_is_a_prior():
    assert T.PRIOR_FIT.fitted is False
    assert "not a fit" in T.PRIOR_FIT.note
    small = T.fit_points_per_sd([(0.5, 3.0), (1.0, 6.0)])
    assert small.fitted is False and small.points_per_sd == T.PRIOR_POINTS_PER_SD


def test_a_real_sample_recovers_the_real_slope():
    pairs = [(z, z * 7.4) for z in [x / 20 - 1.5 for x in range(80)]]
    fit = T.fit_points_per_sd(pairs)
    assert fit.fitted is True
    assert abs(fit.points_per_sd - 7.4) < 0.2
    assert "team-seasons" in fit.note


def test_the_slope_has_no_intercept():
    """A zero talent z-score is a league-average roster and must predict a
    zero net margin — anything else lets the model claim the average team
    is above average.

    Two properties, and the second is the one worth having. Talent inputs
    are z-scores, so they are centred by construction: a constant offset in
    the outcome contributes nothing to a through-origin slope, and the
    slope comes back clean. And a league where talent explains nothing must
    produce a slope of ~0, not a coefficient borrowed from the mean.
    """
    # Symmetric about zero, which is what a z-score actually is — the
    # through-origin fit is unbiased precisely because talent_prior centres
    # its inputs before they ever reach here.
    z_grid = [x / 20 - 2.0 for x in range(81)]
    offset = T.fit_points_per_sd([(z, z * 5.0 + 9.0) for z in z_grid])
    assert offset.fitted and abs(offset.points_per_sd - 5.0) < 0.05

    flat = T.fit_points_per_sd([(z, 9.0) for z in z_grid])
    assert flat.fitted and abs(flat.points_per_sd) < 0.05


def test_team_seasons_come_from_our_own_results():
    conn = db.connect(":memory:")
    rows = [{"sport": "cfb", "season": 2025, "period": f"2025-09-{i+1:02d}",
             "game_id": str(i), "home": "BAMA", "away": "KENT",
             "home_score": 40.0, "away_score": 10.0} for i in range(10)]
    db.upsert_games(conn, rows)
    pairs = T.team_seasons_from_db(conn, {2025: TALENT})
    got = dict((round(z, 2), round(net, 1)) for z, net in pairs)
    assert len(pairs) == 2, "one row per team-season with enough games"
    assert 30.0 in got.values() and -30.0 in got.values()


def test_a_short_season_is_not_a_team_season():
    conn = db.connect(":memory:")
    db.upsert_games(conn, [{"sport": "cfb", "season": 2025, "period": "2025-09-01",
                            "game_id": "1", "home": "BAMA", "away": "KENT",
                            "home_score": 40.0, "away_score": 10.0}])
    assert T.team_seasons_from_db(conn, {2025: TALENT}) == []


# --- double counting --------------------------------------------------------
def test_the_blue_chip_ratio_is_not_a_second_helping_of_the_same_fact():
    """Blue-chip ratio IS the composite's own star ratings. Adding it as a
    separate term would price one fact twice; disagreeing with it should
    only reduce confidence."""
    # Enough teams for a z-score to mean anything — with two rows the
    # spread is undefined and every team scores zero.
    agreeing = {"BAMA": {"ratio": 0.85}, "OSU": {"ratio": 0.80},
                "UGA": {"ratio": 0.78}, "MICH": {"ratio": 0.60},
                "APP": {"ratio": 0.05}, "TOL": {"ratio": 0.03},
                "BGSU": {"ratio": 0.02}, "KENT": {"ratio": 0.01}}
    plain = T.talent_prior(TALENT)
    agree = T.talent_prior(TALENT, blue_chip=agreeing)
    assert agree["BAMA"] == plain["BAMA"], "agreement must not inflate"

    # A composite that says elite while the star ratings say bottom-tier
    # halves the claim rather than compounding it.
    flipped = {t: {"ratio": r["ratio"]} for t, r in
               zip(agreeing, reversed(list(agreeing.values())))}
    disagree = T.talent_prior(TALENT, blue_chip=flipped)
    assert abs(disagree["BAMA"]) < abs(plain["BAMA"])
    assert abs(disagree["BAMA"]) == abs(plain["BAMA"]) / 2


# --- the feed ---------------------------------------------------------------
def test_recruits_are_counted_by_star_rating_not_a_summary_field():
    rows = [{"committedTo": "Alabama", "stars": 5},
            {"committedTo": "Alabama", "stars": 4},
            {"committedTo": "Alabama", "stars": 3},
            {"committedTo": "Kent State", "stars": 2}]
    out = cfbd.parse_blue_chip(rows)
    assert out["Alabama"]["blue_chips"] == 2 and out["Alabama"]["recruits"] == 3
    assert out["Alabama"]["ratio"] == round(2 / 3, 4)
    assert out["Kent State"]["ratio"] == 0.0


def test_the_talent_parser_survives_a_missing_number():
    rows = [{"school": "Alabama", "talent": "980.5"},
            {"school": "Ghost", "talent": None},
            {"team": "Ohio State", "talent": 975}]
    out = cfbd.parse_talent(rows)
    assert out == {"Alabama": 980.5, "Ohio State": 975.0}


def test_returning_production_normalises_percentages():
    rows = [{"team": "Alabama", "percentPPA": 62.5},
            {"team": "Kent State", "percentPPA": 0.31}]
    out = cfbd.parse_returning(rows)
    assert out["Alabama"]["overall"] == 0.625
    assert out["Kent State"]["overall"] == 0.31


def test_the_portal_nets_out_both_directions():
    rows = [{"origin": "Kent State", "destination": "Alabama", "stars": 4},
            {"origin": "Alabama", "destination": "Toledo", "stars": 3}]
    out = cfbd.parse_portal(rows)
    assert out["Alabama"]["in"] == 1 and out["Alabama"]["out"] == 1
    assert out["Alabama"]["net_stars"] == 1.0
    assert out["Kent State"]["net_stars"] == -4.0


def test_no_key_degrades_honestly_instead_of_guessing():
    import os as _os
    saved = _os.environ.pop("CFBD_API_KEY", None)
    try:
        try:
            cfbd.get_api_key()
            raised = False
        except cfbd.CFBDUnavailable as exc:
            raised = True
            assert "collegefootballdata.com/key" in str(exc)
            assert "September" in str(exc), "say what the absence actually costs"
        assert raised or saved is not None
    finally:
        if saved is not None:
            _os.environ["CFBD_API_KEY"] = saved


def test_the_build_reaches_for_the_prior():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "cfb_build.py"), encoding="utf-8") as fh:
        src = fh.read()
    assert "def attach_talent(" in src
    assert "attach_talent(conn, ratings" in src, "defined but never called"



# --- the portal, wired last and nearly left dead -----------------------------
def test_the_portal_moves_the_prior_in_the_right_direction():
    """A recruiting composite describes the roster a team SIGNED, not the
    one it has after a dozen starters transfer out. `fetch_portal` and
    `parse_portal` were written and then never called by anything — the
    parser existed, the layer did not."""
    from engine.cfb import talent as T
    assert T.portal_shift({"net_stars": 10.0}) > 0
    assert T.portal_shift({"net_stars": -10.0}) < 0
    assert T.portal_shift({"net_stars": 0}) == 0
    assert T.portal_shift(None) == 0 and T.portal_shift({}) == 0


def test_the_portal_can_never_steer_the_prior_on_its_own():
    """Net portal stars is a noisy, incomplete count — not every move is
    graded, and a player's stars say little about what he became in three
    years of college. It nudges."""
    from engine.cfb import talent as T
    for extreme in (500.0, -500.0):
        assert abs(T.portal_shift({"net_stars": extreme})) <= T.PORTAL_CLAMP


def test_a_gutted_roster_rates_below_an_identical_one_that_kept_everybody():
    from dataclasses import dataclass
    from engine.cfb import talent as T

    @dataclass
    class R:
        net: float = 0.0
        off: float = 0.0
        def_: float = 0.0
        games: int = 1

    ratings = {"AAA": R(), "BBB": R()}
    prior = {"AAA": 8.0, "BBB": 8.0}
    portal = {"AAA": {"net_stars": -20.0}, "BBB": {"net_stars": 20.0}}
    blended, report = T.apply_prior(ratings, prior, None, portal)
    assert blended["AAA"].net < blended["BBB"].net
    assert report["portal_teams"] == 2
    # …and with no portal data at all, nothing moves.
    flat, rep2 = T.apply_prior(ratings, prior)
    assert flat["AAA"].net == flat["BBB"].net and rep2["portal_teams"] == 0


def test_the_build_actually_fetches_the_portal():
    """The gap this closes: the parser shipped, the fetch never ran."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "cfb_build.py"), encoding="utf-8").read()
    fn = src[src.index("def attach_talent("):src.index("def build_plays(")]
    assert "fetch_portal" in fn, "the portal is parsed but never fetched"
    assert "portal)" in fn, "the portal is fetched but never applied"


def test_the_page_says_which_inputs_actually_loaded():
    """A prior running on recruiting alone with the portal missing is a
    different number from a complete one, and nothing on the page could
    tell them apart."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(root, "web", "js", "app.js"), encoding="utf-8").read()
    assert "function renderTalent(" in js
    fn = js[js.index("function renderTalent("):js.index("function renderAll(")]
    for layer in ("recruiting", "blue-chip", "returning", "portal"):
        assert layer in fn, f"{layer} is not shown"
    assert "missing_layers" in fn
    assert 'state.sport !== "cfb"' in fn, "the panel would leak onto other sports"
    assert "renderTalent();" in js, "defined but never called"


def test_the_implementation_map_does_not_claim_a_built_layer_is_parked():
    """Prose rots. This one rotted for real: §6 read "📋 No free structured
    source" for weeks after `engine/cfb/talent.py` existed and was wired,
    which is exactly the failure `--coverage` was built to catch."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    doc = open(os.path.join(root, "docs", "CFB_MODEL.md"), encoding="utf-8").read()
    for line in doc.splitlines():
        if line.startswith("| §6 Recruiting"):
            assert "📋" not in line, "the doc still calls the talent layer parked"
            assert "✅" in line
            break
    else:
        raise AssertionError("the §6 row vanished from the implementation map")
    assert "It has no talent layer." not in doc

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
