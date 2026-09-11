"""WNBA: the same engine, a different league, and honest about the gap.

The Scalpy pipeline is not NBA-specific — minutes → distribution → clamp →
gate is basketball. What IS NBA-specific is a handful of constants baked
into it, and the whole point of this work was separating the two.

Two things need guarding, and the second is the one that matters.

**The NBA must not have moved.** Every WNBA change went through the shared
code, so the regression risk lands on a league that was working. NBA
defaults are asserted unchanged.

**The WNBA must not pretend to be calibrated.** Its tuning was fitted
against NBA results. Minutes-denominated values are scaled to a 40-minute
game — that is arithmetic — but MARGIN_SD, the blowout curves and the stat
spreads are borrowed, and a model that has never been graded against a
league does not get to bet it. So `calibrated=False` has to survive, and
it has to reach the payload, or the page cannot warn anybody.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import hoops
from engine.nba import minutes as M
from engine.nba import prob as P
from engine.nba.pipeline import run_nba_slate


# --- the NBA must be untouched ---------------------------------------------
def test_nba_defaults_did_not_move():
    assert hoops.NBA.game_minutes == 48
    assert hoops.NBA.calibrated is True
    assert hoops.NBA.probation is False
    # The functions still answer identically without a tuning argument.
    assert M.project_minutes(34, -6, True, True) == \
        M.project_minutes(34, -6, True, True, tune=hoops.NBA)
    assert P.p_over("pts", 22.5, 20.5) == P.p_over("pts", 22.5, 20.5, hoops.NBA)


def test_a_slate_with_no_tuning_is_still_an_nba_slate():
    out = run_nba_slate([])
    assert out["sport"] == "nba" and out["probation"] is False


# --- structural facts, not opinions ----------------------------------------
def test_the_wnba_game_is_forty_minutes():
    assert hoops.WNBA.game_minutes == 40
    assert hoops.WNBA.roster_size == 12
    assert hoops.WNBA.season_games == 44
    assert hoops.WNBA.personal_fouls == 5


def test_nobody_plays_more_minutes_than_the_game_has():
    """The bug this prevents: an NBA-sized projection in a 40-minute game."""
    assert M.project_minutes(46, 0, True, True, tune=hoops.WNBA) <= 40.0
    assert M.project_minutes(46, 0, True, True, tune=hoops.NBA) <= 48.0


def test_minutes_denominated_values_are_scaled_not_guessed():
    # 8 NBA minutes is a sixth of a game; the WNBA cap must stay a sixth.
    ratio = hoops.WNBA.vacancy_cap_over_high / hoops.NBA.vacancy_cap_over_high
    assert abs(ratio - 40 / 48) < 0.01


def test_the_fitted_constants_are_inherited_and_labelled():
    # These were fitted against NBA results and are NOT claimed as WNBA's.
    assert hoops.WNBA.margin_sd == hoops.NBA.margin_sd
    assert hoops.WNBA.sd_cv == hoops.NBA.sd_cv
    assert hoops.WNBA.blowout_starter == hoops.NBA.blowout_starter
    # …which is only acceptable because it says so, loudly.
    assert hoops.WNBA.calibrated is False
    assert hoops.WNBA.probation is True
    assert hoops.WNBA.inherited_from == "nba"
    assert "not yet fitted" in hoops.WNBA.note.lower()


def test_the_decision_rules_are_the_wnba_spec_s_own_not_inherited():
    """Inheriting a fitted constant is honest; inheriting a DECISION rule
    the spec explicitly rewrote is not. Tiers, bars, grade, stability
    filter and caps all belong to this league."""
    assert hoops.WNBA.market_tier and not hoops.NBA.market_tier
    assert hoops.WNBA.tier_min_edge and not hoops.NBA.tier_min_edge
    assert hoops.WNBA.grade_weights and not hoops.NBA.grade_weights
    assert hoops.WNBA.min_grade == 70 and hoops.NBA.min_grade is None
    assert hoops.WNBA.stability_max_cv and hoops.NBA.stability_max_cv is None
    # Tighter than the NFL/MLB slate cap, on purpose.
    assert (hoops.WNBA.cap_per_play, hoops.WNBA.cap_per_game,
            hoops.WNBA.cap_per_slate) == (0.02, 0.05, 0.12)


# --- the label has to reach the page ----------------------------------------
def test_probation_reaches_the_payload():
    out = run_nba_slate([], tune=hoops.WNBA)
    assert out["sport"] == "wnba"
    assert out["probation"] is True
    assert out["tuning"]["calibrated"] is False
    assert out["tuning"]["inherited_from"] == "nba"
    assert out["tuning"]["note"]


def test_a_prop_card_carries_its_league():
    prop = {"player": "Test Player", "team": "LVA", "opponent": "NYL",
            "market": "pts", "line": 17.5, "over_odds": -110,
            "under_odds": -110, "spread": -3.0, "is_starter": True,
            "minutes": [30.0] * 12, "values": [18.0] * 12}
    from engine.nba.pipeline import evaluate_prop
    card = evaluate_prop(prop, hoops.WNBA)
    assert card.get("league") == "wnba", "a card can't say which league it is"


def test_for_league_falls_back_rather_than_crashing():
    assert hoops.for_league("wnba") is hoops.WNBA
    assert hoops.for_league("nba") is hoops.NBA
    assert hoops.for_league("") is hoops.NBA
    assert hoops.for_league("quidditch") is hoops.NBA


# --- plumbing ---------------------------------------------------------------
def test_the_odds_adapter_knows_the_league():
    from engine.sources.oddsapi import SPORT_CONFIG, WNBA_TEAM_ABBR
    assert SPORT_CONFIG["wnba"]["sport_key"] == "basketball_wnba"
    # Expanded to 15 for 2026 (Golden State 2025, Toronto + Portland 2026).
    assert len(set(WNBA_TEAM_ABBR.values())) == 15
    # Same markets as the NBA — points/rebounds/assists/threes.
    assert SPORT_CONFIG["wnba"]["markets"] == SPORT_CONFIG["nba"]["markets"]


def test_the_server_serves_the_league():
    from server import LIVE_FILES
    assert LIVE_FILES["wnba"].name == "wnba.json"
    with open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "server.py"), encoding="utf-8") as fh:
        assert "/api/wnba/recommendations" in fh.read()


def test_the_data_source_points_at_the_wnba_cdn():
    from engine.sources import wnbadata, nbadata
    assert "cdn.wnba.com" in wnbadata.CDN
    # Same parsers, not copies — two boxscore parsers would drift, and the
    # first symptom would be a WNBA board quietly missing a stat.
    assert wnbadata.parse_boxscore is nbadata.parse_boxscore
    assert wnbadata.parse_schedule_day is nbadata.parse_schedule_day


def _read(*parts):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_the_page_is_wired_end_to_end():
    html = _read("web", "index.html")
    assert 'data-sport="wnba"' in html
    assert "teams_wnba.js" in html
    app = _read("web", "js", "app.js")
    assert '"/api/wnba/recommendations"' in app
    assert "WNBA_TEAMS" in app, "the WNBA board would draw NFL helmets"
    teams = _read("web", "js", "teams_wnba.js")
    assert teams.count('"primary"') == 15


def test_the_page_warns_that_it_is_on_probation():
    app = _read("web", "js", "app.js")
    assert "function renderProbation()" in app
    assert "renderProbation();" in app, "defined but never called"
    fn = app[app.index("function renderProbation()"):]
    fn = fn[:fn.index("\n}\n")]
    assert "d.probation" in fn
    assert "graded, not bet" in fn


def test_the_league_has_no_long_shot_board():
    # No WNBA equivalent of home runs / anytime touchdowns exists, so the
    # tab hides rather than rendering an empty page.
    app = _read("web", "js", "app.js")
    assert 'state.sport === "wnba"' in app.replace("'", '"')


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
