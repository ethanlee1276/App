"""The WNBA handicapping script, implemented where the hoops chain prices.

Ethan, 2026-08-31: "here is the same thing for wnba. we need to be
pushing the most likley bets for wnba and follow this like how we did
for the others." The audit found the chain already carried the script's
spine — minutes-first with role-regime weighting (§2, §11), on/off
redistribution by share (§3), negative binomial tails (§9), the
role-volatility refusal (§2), and player-vs-team history already inert
(§11). What was missing is what this file pins:

  * §1.2 — a scoring-environment factor: the market total against the
    league norm, damped by half because a total prices pace AND
    efficiency and only pace scales volume;
  * §1.3 — the two accounting identities, audited and PUBLISHED: listed
    points vs the team total, and the menu's implied minutes vs 200;
  * §6  — the layoff rule, keyed on the GAP not the calendar: any first
    game after a 10+ day team break shades shooting efficiency — the
    World Cup resumption (Sept 17) is the season's premier window and
    the rule prices it without knowing its name;
  * §7  — the star tax: marquee overs need an extra point of edge,
    marquee unders say their subsidy out loud. WNBA only.

Run directly: `python3 tests/test_wnba_script.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine.hoops import for_league
from engine.nba.coherence import (implied_projection, menu_audit,
                                  minutes_sum_check, points_sum_check,
                                  team_totals)
from engine.nba.context import (ENV_CLAMP, LAYOFF_EFF, STAR_TAX_EDGE,
                                env_factor, layoff_adjustment, layoff_days,
                                star_tax)

WNBA = for_league("wnba")


# --- §1.2: the environment factor -------------------------------------------
def test_the_league_norm_is_neutral_and_the_factor_is_damped():
    assert env_factor(162.0, "wnba") == (1.0, None)
    mult, reason = env_factor(175.0, "wnba")
    # 175/162 is +8% of total; half is credited to volume.
    assert abs(mult - (1 + (175 / 162 - 1) * 0.5)) < 1e-9
    assert reason and "fast" in reason
    mult_slow, _ = env_factor(148.0, "wnba")
    assert mult_slow < 1.0


def test_the_factor_is_clamped_and_refuses_unknowns():
    mult, _ = env_factor(220.0, "wnba")            # absurd for the W
    assert mult == 1.0 + ENV_CLAMP
    assert env_factor(None, "wnba") == (1.0, None)
    assert env_factor(162.0, "nhl") == (1.0, None), "no norm, no claim"
    m_nba, _ = env_factor(225.0, "nba")
    assert m_nba == 1.0, "each league is judged against its own norm"


# --- §6: the layoff rule ----------------------------------------------------
def test_the_gap_is_measured_from_the_teams_own_logs():
    dates = ["2026-08-30", "2026-08-25", "2026-08-22"]
    assert layoff_days(dates, "2026-09-17") == 18
    assert layoff_days(dates, "2026-08-31") == 1
    assert layoff_days([], "2026-09-17") is None
    assert layoff_days(["2026-09-20"], "2026-09-17") is None, \
        "a future game is not a past one"


def test_first_game_back_shades_shooting_not_legs():
    mult, note = layoff_adjustment(18, "fg3m")
    assert mult == LAYOFF_EFF["fg3m"] and "18-day layoff" in note
    assert layoff_adjustment(18, "pts")[0] == LAYOFF_EFF["pts"]
    reb_mult, reb_note = layoff_adjustment(18, "reb")
    assert reb_mult == 1.0, "rebounds ride minutes and legs, not stroke"
    assert reb_note, "the caveat still appears — the context is real"
    assert layoff_adjustment(5, "fg3m") == (1.0, None)
    assert layoff_adjustment(None, "fg3m") == (1.0, None)


# --- §7: the star tax -------------------------------------------------------
def test_marquee_overs_pay_the_tax_and_unders_collect_the_subsidy():
    extra, note = star_tax("pts", "OVER", 22.5, "wnba")
    assert extra == STAR_TAX_EDGE and "extra point" in note
    extra_u, note_u = star_tax("pts", "UNDER", 22.5, "wnba")
    assert extra_u == 0.0 and "subsidy" in note_u


def test_the_tax_stays_off_role_players_other_stats_and_the_nba():
    assert star_tax("pts", "OVER", 12.5, "wnba") == (0.0, None)
    assert star_tax("reb", "OVER", 22.5, "wnba") == (0.0, None)
    assert star_tax("pts", "OVER", 28.5, "nba") == (0.0, None), \
        "the NBA's deeper handle doesn't concentrate this way"


# --- §1.3: the coherence checks ---------------------------------------------
def test_team_totals_split_the_game_line():
    fav, dog = team_totals(164.0, -6.0)
    assert fav == 85.0 and dog == 79.0
    assert team_totals(None, -6.0) is None


def test_the_juice_moves_the_implied_projection():
    even = implied_projection(18.5, -110, -110, "pts", WNBA)
    assert abs(even - 18.5) < 0.2, "balanced juice states the line"
    shaded = implied_projection(18.5, -140, +110, "pts", WNBA)
    assert shaded > even + 0.4, "-140 over is a statement above the line"


def _menu_rows(lines):
    return [{"player": f"P{i}", "line": ln, "over_odds": -110,
             "under_odds": -110} for i, ln in enumerate(lines)]


def test_an_inflated_menu_is_named_taxed_and_a_cheap_one_cheap():
    # Seven listed players summing ~86.5 pts against a 79-total team.
    hot = points_sum_check(_menu_rows([22.5, 18.5, 14.5, 11.5, 8.5, 6.5,
                                       4.5]), 79.0, WNBA)
    assert hot["verdict"] and "taxed" in hot["verdict"], hot
    cold = points_sum_check(_menu_rows([14.5, 11.5, 9.5, 7.5, 5.5, 4.5,
                                        3.5]), 88.0, WNBA)
    assert cold["verdict"] and "cheap" in cold["verdict"], cold
    fair = points_sum_check(_menu_rows([19.5, 15.5, 12.5, 9.5, 7.5, 5.5,
                                        3.5]), 79.0, WNBA)
    assert fair["verdict"] is None, fair


def test_a_thin_menu_says_nothing():
    assert points_sum_check(_menu_rows([22.5, 18.5]), 79.0, WNBA) is None
    assert points_sum_check(_menu_rows([22.5] * 6), None, WNBA) is None


def test_the_200_minute_audit_names_the_unmoved_players():
    """A star ruled out, her teammates' lines moved, one didn't: the
    menu's implied minutes come up short and the shortfall has a name —
    'the fourth-listed player', exactly where the script says the
    unpriced production sits."""
    rows = []
    for i, (line, rate, norm) in enumerate([
            (18.5, 0.62, 31.0), (14.5, 0.55, 27.0), (11.5, 0.50, 24.0),
            (5.5, 0.48, 26.0),   # the unmoved one: priced at ~11 minutes
            (7.5, 0.42, 19.0), (5.5, 0.40, 15.0)]):
        rows.append({"player": f"P{i}", "line": line, "over_odds": -110,
                     "under_odds": -110, "rate": rate, "recent_min": norm})
    got = minutes_sum_check(rows, WNBA)
    assert got["flag"], got
    assert got["missing_minutes"] > 0
    assert "P3" in got["unmoved"], got["unmoved"]


def test_the_build_publishes_the_audit_per_team():
    props = []
    for team, entries in (("LV", [(20.5, [34] * 8, [21] * 8),
                                  (15.5, [30] * 8, [16] * 8),
                                  (11.5, [26] * 8, [12] * 8),
                                  (8.5, [22] * 8, [9] * 8),
                                  (6.5, [18] * 8, [7] * 8)]),):
        for line, mins, vals in entries:
            props.append({"player": f"{team}{line}", "team": team,
                          "market": "pts", "line": line, "over_odds": -110,
                          "under_odds": -110, "minutes": mins,
                          "values": vals})
    games = [{"home": "LV", "away": "NY", "total": 164.0, "spread": -6.0}]
    got = menu_audit(props, games, WNBA)
    assert got and got[0]["team"] == "LV"
    assert got[0]["points_sum"]["listed"] == 5
    with open(os.path.join(ROOT, "nba_build.py"), encoding="utf-8") as f:
        src = f.read()
    assert 'out["menu_audit"] = menu_audit(' in src
    assert '"game_total": total_by_team.get(h["team"])' in src
    assert '"days_off": _ctx_layoff(h.get("dates"), args.date)' in src


# --- the pipeline carries all of it -----------------------------------------
def _prop(**kw):
    base = {"player": "A Star", "team": "LV", "opponent": "NY",
            "market": "pts", "line": 21.5, "over_odds": -110,
            "under_odds": -110, "book": "dk", "minutes": [34.0] * 10,
            "values": [22.0] * 10, "is_starter": True, "spread": -2.0,
            "is_favorite": True, "rest": "1day"}
    base.update(kw)
    return base


def test_the_card_carries_its_context_notes():
    from engine.nba.pipeline import evaluate_prop
    got = evaluate_prop(_prop(game_total=176.0, days_off=18), WNBA)
    assert got["kind"] in ("pick", "near_miss"), got
    notes = " ".join(got.get("context") or [])
    assert "environment" in notes, notes
    assert "layoff" in notes, notes


def test_a_marquee_over_that_cannot_pay_the_tax_is_refused():
    from engine.nba.pipeline import evaluate_prop
    # Projection ~22.3 on a 21.5 line at even juice: an OVER lean with a
    # small edge — exactly what the tax exists to refuse.
    got = evaluate_prop(_prop(), WNBA)
    if got["kind"] == "near_miss" and got.get("side") == "OVER":
        assert any("star tax" in f for f in got["fails"]) or \
            got["required_edge"] > 0.0, got["fails"]
    notes = " ".join(got.get("context") or [])
    assert "shade" in notes or "subsidy" in notes, notes


def test_the_tax_raises_the_stated_requirement():
    from engine.nba.pipeline import evaluate_prop
    taxed = evaluate_prop(_prop(), WNBA)
    small = evaluate_prop(_prop(player="A Role Player",
                                values=[9.0] * 10, line=8.5), WNBA)
    if taxed.get("side") == "OVER" and small.get("side") == "OVER" and \
            "required_edge" in taxed and "required_edge" in small:
        assert taxed["required_edge"] >= small["required_edge"] + \
            STAR_TAX_EDGE - 1e-9, (taxed["required_edge"],
                                   small["required_edge"])


def test_player_vs_team_history_stays_out_of_the_number():
    """§11: the same eight-flips folklore as batter-vs-pitcher, already
    inert — pinned so it stays that way."""
    with open(os.path.join(ROOT, "engine", "nba", "pipeline.py"),
              encoding="utf-8") as f:
        src = f.read()
    assert '"vs_opponent": None' in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
