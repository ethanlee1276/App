"""Recency + two-sided betting behavior.

Covers the model's ability to (a) MEASURE a cooling player, (b) recommend
the UNDER when that's where the value is, and (c) dock confidence for
betting against a player's trend. Shared helpers are exercised directly
since both the NFL and MLB betting layers route through them.

(a) USED TO SAY "shade a cooling player's projection down", and football
no longer does. `compute_form` still reports `trend_mult`; NFL stopped
multiplying by it on 2026-09-03 after engine/formcheck scored it for the
first time and it lost the within-week ordering in all four markets. The
observation is kept and the correction is retired — see
engine/projection.py, which carries the table. MLB still applies its own
and is deliberately untouched: that measurement is NFL logs only.

Run directly: `python3 tests/test_recency.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.form import compute_form
from engine.odds import best_under_line, best_over_line
from engine.betting import pick_side, _trend_alignment, evaluate_prop, temper_edge, MAX_CREDIBLE_EDGE
from engine.projection import build_projection
from engine.explain import headline
from engine.models import (
    SportsbookLine, GameLog, Prop, Game, Team, DefenseProfile, Weather, REC_YDS,
)


def approx(a, b, tol=1e-3):
    return abs(a - b) < tol


def _logs(vals):
    """Build game logs, most-recent-first (index 0 = latest game)."""
    return [GameLog(week=i, opponent="X", value=v, home=True) for i, v in enumerate(vals)]


# --- line shopping ---------------------------------------------------------

def test_best_under_line_shops_highest():
    lines = [
        SportsbookLine("A", 50.5, -110, -110),
        SportsbookLine("B", 52.5, -108, -112),  # highest line = best under cushion
        SportsbookLine("C", 51.5, -115, -105),
    ]
    best = best_under_line(lines)
    assert best.book == "B"
    assert best.line == 52.5


# --- two-sided selection ---------------------------------------------------

def test_pick_side_takes_under_when_projection_is_low():
    lines = [SportsbookLine("DK", 50.5, -110, -110)]   # fair ~0.5 / 0.5
    # p_over_at returns a low over probability -> the value is on the under.
    side, best, win, fair, edge = pick_side(lines, lambda ln: 0.20)
    assert side == "UNDER"
    assert approx(win, 0.80)          # 1 - 0.20
    assert edge > 0
    assert best.line == 50.5


def test_pick_side_takes_over_when_projection_is_high():
    lines = [SportsbookLine("DK", 50.5, -110, -110)]
    side, best, win, fair, edge = pick_side(lines, lambda ln: 0.75)
    assert side == "OVER"
    assert approx(win, 0.75)
    assert edge > 0


# --- recency shade (downward only) -----------------------------------------

def test_hot_streak_is_not_inflated():
    # Recent games far above the prior season -> trend up, but the projection
    # is deliberately NOT shaded up (chasing heat is a bettor trap).
    form = compute_form(_logs([120, 115, 110, 60, 62, 58, 64, 60, 59, 61]),
                        career_avg=70.0, vs_opponent_avg=None)
    assert form.trend == "up"
    assert form.trend_mult == 1.0


def test_a_cold_streak_is_still_measured_even_though_it_no_longer_shades():
    """`compute_form` is unchanged: it still spots the cool-off and still
    computes the shade. What changed is that football stopped multiplying
    by it. Keeping the measurement is the point — the card says "cooling
    off", `betting._trend_alignment` still docks confidence for fighting
    it, and the number itself is left alone."""
    form = compute_form(_logs([30, 28, 33, 90, 92, 88, 95, 91, 89, 93]),
                        career_avg=70.0, vs_opponent_avg=None)
    assert form.trend == "down"
    assert form.trend_mult < 1.0
    assert form.trend_mult >= 0.90        # bounded


def test_the_football_projection_does_not_apply_the_shade():
    """THE CHANGE, measured 2026-09-03. A cold player's projection is his
    form blend times the factors that were measured — matchup, weather,
    usage, the record's own player correction — and NOT times a recency
    multiplier that lost at ordering in every market it was scored on.

    Asserted through the CHAIN rather than the source line, because the
    chain is what has to multiply back out to the number that ships: a
    trend step of anything but 1.0 would mean the projection moved."""
    logs = _logs([30, 28, 33, 90, 92, 88, 95, 91, 89, 93])
    prop = Prop(player="Cold Wideout", team="AAA", opponent="BBB",
                position="WR", market=REC_YDS, logs=logs, career_avg=70.0,
                vs_opponent_avg=None,
                lines=[SportsbookLine("DK", 60.5, -110, -110)])
    game = Game(home="AAA", away="BBB", weather=Weather(dome=True))
    opp = Team(abbr="BBB", name="B Team", defense=DefenseProfile(team="BBB"))
    proj = build_projection(prop, game, opp)

    assert proj.form.trend == "down", "the fixture is not actually cooling"
    assert proj.form.trend_mult < 1.0, "so the shade would have bitten"
    steps = {s["key"]: s["mult"] for s in (proj.chain or {}).get("steps") or []}
    assert steps.get("trend") == 1.0, \
        f"the recency shade is being applied again (x{steps.get('trend')})"
    from engine import chain as _chain
    assert _chain.closes(proj.chain), "the chain stopped reaching its own answer"


def test_the_shade_is_still_applied_in_baseball():
    """NOT AN OVERSIGHT. The measurement that retired it ran on NFL game
    logs; baseball's own history has never been asked the same question,
    and removing a factor from a sport on another sport's evidence is
    exactly the kind of thing this repo does not do. When MLB is
    measured, this test is the one to come back to."""
    import inspect
    from engine.mlb import projection as mlb_projection
    src = inspect.getsource(mlb_projection)
    assert "trend_mult = form.trend_mult" in src
    assert "* trend_mult *" in src, \
        "MLB stopped applying its recency shade without its own measurement"


def test_the_measurement_that_retired_the_shade_is_written_down():
    """A live multiplier removed on the strength of a number keeps that
    number where the next person will look for it, or the next person
    puts it back."""
    import inspect
    from engine import projection as nfl_projection
    src = inspect.getsource(nfl_projection)
    for row in ("0.3261", "0.3113", "0.5518", "0.5460",
                "0.6491", "0.6430", "0.5501", "0.5456"):
        assert row in src, f"the formcheck table lost {row}"
    assert "MLB IS UNTOUCHED" in src, \
        "the scope of the measurement is no longer recorded beside it"


# --- trend-aware confidence ------------------------------------------------

def test_trend_alignment_rewards_riding_and_penalizes_fighting():
    assert _trend_alignment("OVER", "down") < 0      # fighting a cool-off
    assert _trend_alignment("UNDER", "down") > 0     # fading the fader
    assert _trend_alignment("OVER", "up") > 0        # riding a hot streak
    assert _trend_alignment("UNDER", "up") < 0
    assert _trend_alignment("OVER", "flat") == 0.0
    # Fighting the trend costs more than riding it earns (asymmetric, cautious).
    assert abs(_trend_alignment("OVER", "down")) > _trend_alignment("OVER", "up")


# --- end to end: hot early, cold late --------------------------------------

def test_fading_player_flips_to_under():
    # Elite early (100+), fell off a cliff late (28-40). logs are most-recent
    # first, so the top entries are the cold games. Book line still sits at the
    # hot-era number.
    logs = _logs([28, 34, 31, 40, 95, 110, 120, 105, 98, 102])
    prop = Prop(player="Fading Wideout", team="AAA", opponent="BBB", position="WR",
                market=REC_YDS, logs=logs, career_avg=78.0, vs_opponent_avg=None,
                lines=[SportsbookLine("DK", 74.5, -110, -110)])
    game = Game(home="AAA", away="BBB", weather=Weather(dome=True))
    opp = Team(abbr="BBB", name="B Team", defense=DefenseProfile(team="BBB"))

    proj = build_projection(prop, game, opp)
    rec = evaluate_prop(prop, proj)

    assert proj.form.trend == "down"
    assert proj.form.trend_mult < 1.0
    # NOT "shaded down" any more — the recency multiplier is retired (see
    # above). The point of this test was always the SIDE: a player whose
    # recent games sit far below a stale line is an under, and the blend
    # gets there on its own weighting without a correction on top.
    assert rec.side == "UNDER"                        # value is on the under
    assert rec.edge > 0
    assert "UNDER" in headline(rec)                   # headline reflects the side


def test_max_juice_filters_heavy_chalk():
    """Laying -700 for a small edge pays too little for the risk (and sits in the
    model's least reliable tail), so it must not be recommended."""
    from engine.rules import RuleConfig, apply_rules
    from engine.betting import Recommendation
    from engine.models import Game, Weather

    def rec_at(odds):
        return Recommendation(
            player="X", team="AAA", opponent="BBB", market=REC_YDS, side="OVER",
            book="DraftKings", line=50.5, odds=odds, projection=60.0,
            proj_low=40.0, proj_high=80.0, hit_prob=0.9, fair_prob=0.85,
            edge=0.05, ev_per_unit=0.02, confidence=8.0, stake_units=0.5,
            grade="Play",
        )

    prop = Prop(player="X", team="AAA", opponent="BBB", position="WR",
                market=REC_YDS, logs=_logs([60] * 6), career_avg=60.0,
                vs_opponent_avg=None, lines=[SportsbookLine("DK", 50.5, -700, 500)])
    game = Game(home="AAA", away="BBB", weather=Weather(dome=True))
    cfg = RuleConfig(min_confidence=6.0, min_edge=0.02, max_juice=-350)

    heavy = apply_rules(rec_at(-700), prop, game, cfg)
    assert heavy.recommend is False
    assert any("juice" in w.lower() for w in heavy.warnings)

    # A normal price with the same edge still gets through.
    assert apply_rules(rec_at(-150), prop, game, cfg).recommend is True


def test_temper_edge_shrinks_and_flags_bad_data():
    # The real Caminero case: model 0.75 vs a broken market price of 0.27.
    hit, edge, credible = temper_edge(0.75, 0.27, "Hard Rock")
    assert not credible                         # a 48% raw gap is bad data, not alpha
    # Margin rather than a bare comparison (see test_sidebias.py). The
    # point is that a 48-point raw gap is SHRUNK hard, so demanding a
    # tenth of it is a floor the real behaviour clears easily.
    assert abs(edge) < abs(0.75 - 0.27) * 0.9   # shrunk toward the market
    # A modest, believable edge on a real line survives (and is damped).
    hit, edge, credible = temper_edge(0.56, 0.50, "DraftKings")
    assert credible and 0 < edge < 0.06
    # A placeholder line is never credible.
    assert temper_edge(0.60, 0.50, "proxy")[2] is False


def test_live_games_are_never_recommended():
    """A pre-game model cannot price an in-play market. Backing a team down
    three in the bottom of the ninth at +1400 because the pre-game model still
    thinks they're live is exactly the failure this guard exists to stop."""
    from engine.rules import RuleConfig, apply_rules, game_has_started
    from engine.betting import Recommendation
    from engine.models import Game, Weather, LiveStatus

    rec = Recommendation(
        player="X", team="AAA", opponent="BBB", market=REC_YDS, side="OVER",
        book="DraftKings", line=50.5, odds=-110, projection=60.0,
        proj_low=40.0, proj_high=80.0, hit_prob=0.62, fair_prob=0.52,
        edge=0.10, ev_per_unit=0.05, confidence=9.0, stake_units=1.0,
        grade="Strong Play")
    prop = Prop(player="X", team="AAA", opponent="BBB", position="WR",
                market=REC_YDS, logs=_logs([60] * 6), career_avg=60.0,
                vs_opponent_avg=None, lines=[SportsbookLine("DK", 50.5, -110, -110)])
    cfg = RuleConfig(min_confidence=6.0, min_edge=0.02)

    pre = Game(home="AAA", away="BBB", weather=Weather(dome=True))
    assert apply_rules(rec, prop, pre, cfg).recommend is True

    for state in ("live", "final"):
        g = Game(home="AAA", away="BBB", weather=Weather(dome=True),
                 live=LiveStatus(state=state, home_score=1, away_score=4))
        assert game_has_started(g)
        d = apply_rules(rec, prop, g, cfg)
        assert d.recommend is False
        assert any("already started" in w for w in d.warnings)


def test_empirical_model_corrects_discrete_props():
    """A normal curve badly overstates a 0.5 line on a low-count stat, which was
    inflating every MLB edge. Blending the player's own log fixes it."""
    from engine.mlb.betting import empirical_prob_over
    from engine.statmath import prob_over

    hist = [0] * 16 + [1] * 12 + [2] * 8 + [4] * 4      # 40 games, mean 1.5
    true_rate = sum(1 for v in hist if v > 0.5) / len(hist)
    parametric = prob_over(0.5, 1.5, 1.125)
    blended = empirical_prob_over(hist, 0.5, parametric)

    assert parametric > 0.78                       # the old, overstated number
    # Margin rather than a bare comparison (see test_sidebias.py).
    # Measured: 0.028 against 0.213 — the blend is nearly eight times
    # closer to truth.
    assert abs(blended - true_rate) < abs(parametric - true_rate) * 0.9
    assert blended < parametric

    # Too short a log can't outvote the model — it falls straight through.
    assert empirical_prob_over([1, 0, 2], 0.5, parametric) == parametric



if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
