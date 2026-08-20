"""Projection assembly.

Combines the base form mean with the multiplicative adjustments from the
matchup, weather and injury modules to produce a final projected mean and a
standard deviation for the prop's market. Every contributing factor is kept so
the explanation and the UI can show the full chain of reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Prop, Game, Team
from . import chain
from .form import compute_form, FormResult, WINDOW_WEIGHTS
from .weather import evaluate_weather, WeatherEffect
from .injuries import evaluate_injuries, InjuryEffect
from .matchup import evaluate_matchup, MatchupEffect
from .statmath import clamp

# Realistic game-to-game variance floors, expressed as a coefficient of
# variation (std / mean) per market. Player game logs are often too smooth to
# capture true prop variance, so we never let the estimated std fall below
# these market-typical levels — this is what keeps hit probabilities honest.
CV_FLOOR = {
    "pass_yds": 0.16,
    "rush_yds": 0.42,
    "rec_yds": 0.48,
    "receptions": 0.34,
}

# Usage bridge: how many games of outcome logs it takes for observed form
# to carry as much weight as the measured volume role. At zero logs the
# measured role IS the baseline; by a full season, form outweighs it ~4:1.
# (The game-script tilt lives in engine.matchup, which already owned the
# spread and stands down when teamcontext measures pass rate for real.)
USAGE_PRIOR_GAMES = 4


@dataclass
class Projection:
    mean: float
    std: float
    form: FormResult
    matchup: MatchupEffect
    weather: WeatherEffect
    injury: InjuryEffect
    reasons: list[str] = field(default_factory=list)
    #: The arithmetic that produced `mean`, kept rather than discarded —
    #: base × a series of named multipliers. See engine/chain.py for why
    #: this is a checkable structure and not another sentence.
    chain: dict = field(default_factory=dict)


def build_projection(prop: Prop, game: Game, opponent_team: Team, model=None,
                     context: dict | None = None, sport: str = "nfl",
                     form_weights: dict | None = None,
                     player_mult: float | None = None,
                     usage: dict | None = None) -> Projection:
    """``context`` (NFL Phase 2) carries measured team tendency:
    ``{"profiles": {team: profile}, "league": {...}}`` from
    engine.teamcontext. Absent = the model prices exactly as before, which
    is what makes the whole layer A/B-testable against the backtest
    baseline instead of shipped on faith.

    ``sport`` keys the self-tuning stores. ``form_weights`` /
    ``player_mult`` are the fitters' explicit candidates and always beat
    the stores — a fitter must never read the store it is refitting
    (see engine/mlb/projection.py, the same contract).

    ``usage`` is this player's measured volume role for this market
    (engine.nflusage.volume_roles): recent opportunities per game and
    season per-opportunity efficiency. Live boards pass it; the backtest
    never does, so the fitted temperatures keep meaning what they meant
    and journalfit audits the live drift."""
    if form_weights is None:
        from .formfit import weights_for
        form_weights = weights_for(sport, prop.market)
    form = compute_form(prop.logs, prop.career_avg, prop.vs_opponent_avg,
                        weights=form_weights)

    matchup = evaluate_matchup(prop, opponent_team.defense, game,
                               measured_context=bool(context))
    weather = evaluate_weather(game.weather)
    injury = evaluate_injuries(prop, game.injuries)

    weather_mult = weather.multipliers.get(prop.market, 1.0)

    # Hand-tuned total multiplier, bounded so no single factor runs away with
    # the projection. Kept tight because sportsbook lines are efficient.
    rule_mult = clamp(
        matchup.multiplier * weather_mult * injury.multiplier,
        0.85, 1.18,
    )

    # Measured team tendency — pace, pass rate, offensive efficiency. Kept
    # OUTSIDE rule_mult's clamp on purpose: that clamp exists to stop the
    # hand-tuned factors compounding, and this is a different kind of
    # input with its own bound. Folding it in would make a fast, pass-heavy
    # offence indistinguishable from a merely favourable matchup.
    ctx_mult, ctx_reasons = 1.0, []
    if context:
        from .teamcontext import context_multiplier, drift_multiplier
        team = prop.team
        if context.get("mode") == "drift":
            ctx_mult, ctx_reasons = drift_multiplier(
                (context.get("profiles") or {}).get(team),
                (context.get("baseline") or {}).get(team), prop.market)
        else:
            ctx_mult, ctx_reasons = context_multiplier(
                (context.get("profiles") or {}).get(team),
                context.get("league") or {}, prop.market)

    reasons: list[str] = []

    # Usage bridge: blend the form mean against "recent volume × season
    # efficiency" by sample size — thin outcome logs lean on the measured
    # role, a full season of outcomes speaks for itself. Absent usage
    # (backtests, other sports, un-ingested players) leaves the baseline
    # exactly form.mean.
    mean_base = form.mean
    usage_why = ""
    if usage and usage.get("opp_per_game") and usage.get("eff"):
        est = float(usage["opp_per_game"]) * float(usage["eff"])
        if est > 0:
            w = form.sample_games / (form.sample_games + USAGE_PRIOR_GAMES)
            mean_base = w * form.mean + (1.0 - w) * est
            if form.mean > 0 and abs(mean_base / form.mean - 1.0) >= 0.02:
                per, unit = {
                    "targets": ("targets/gm", "per target"),
                    "carries": ("carries/gm", "per carry"),
                    "pass_att": ("att/gm", "per attempt"),
                }.get(usage.get("opp_market"), ("touches/gm", "per touch"))
                usage_why = (
                    f"{float(usage['opp_per_game']):.1f} {per} "
                    f"× {float(usage['eff']):.2f} {unit} — measured role says "
                    f"{est:.1f}, weighted {1.0 - w:.0%} against form")
                reasons.append(f"Usage bridge: {usage_why}")

    if model is not None and model.has(prop.market):
        # Learned magnitude replaces the hand-tuned matchup/weather multipliers
        # (including the matchup module's game-script tilt — the feature
        # vector already carries the spread); injuries stay on top (they're a
        # separate, sparse signal the model isn't trained on). The rule
        # modules still supply the reasons below.
        from .ml.features import extract_features, vectorize
        feat = vectorize(extract_features(prop, game, opponent_team.defense))
        learned = model.predict_multiplier(feat, prop.market)
        raw_mult = learned * injury.multiplier
        total_mult = clamp(raw_mult, 0.70, 1.40)
        mult_steps = [
            chain.step("learned", learned,
                       "Magnitude learned from settled results, which "
                       "replaces the hand-tuned matchup and weather dials."),
            chain.step("injury", injury.multiplier,
                       "; ".join(injury.reasons)),
            chain.cap_step(raw_mult, total_mult, 0.70, 1.40),
        ]
        reasons.append(f"Learned model adjustment ×{learned:.2f} (trained on historical data)")
    else:
        total_mult = rule_mult
        raw_mult = matchup.multiplier * weather_mult * injury.multiplier
        mult_steps = [
            chain.step("matchup", matchup.multiplier, "; ".join(matchup.reasons)),
            chain.step("weather", weather_mult, "; ".join(weather.reasons)),
            chain.step("injury", injury.multiplier, "; ".join(injury.reasons)),
            chain.cap_step(raw_mult, total_mult, 0.85, 1.18),
        ]

    # Recency shade: a sustained hot/cold streak pulls the projection toward
    # recent form (bounded in form.py), so the model stops leaning on stale
    # early-season numbers for a player who has cooled off.
    #
    # Player memory (engine/playerfit.py): the record's earned correction
    # for players the blend persistently misreads.
    if player_mult is None:
        from .playerfit import mult_for
        player_mult = mult_for(sport, prop.market, prop.player)
    mean = mean_base * total_mult * form.trend_mult * ctx_mult * player_mult

    # Uncertainty: never below the market-typical variance floor, and it grows
    # as we push further from the player's own baseline.
    cv_floor = CV_FLOOR.get(prop.market, 0.35) * max(mean_base, 1.0)
    base_std = max(form.std, cv_floor)
    adj_std = base_std * (1.0 + 0.5 * abs(total_mult - 1.0)
                          + 0.5 * abs(ctx_mult - 1.0))
    if form.sample_games < 4:
        adj_std *= 1.20

    if abs(player_mult - 1.0) >= 0.02:
        direction = "high" if player_mult < 1.0 else "low"
        reasons.append(f"Player memory: the record shows the blend runs "
                       f"{direction} on him — corrected ×{player_mult:.2f}")
    reasons += ctx_reasons
    reasons += matchup.reasons
    reasons += weather.reasons
    reasons += injury.reasons

    # Recent-form narrative — the cool-off case is tied to the actual shade.
    if form.trend == "up":
        reasons.append(f"Trending up — last 3 games {form.trend_delta:+.0f} vs prior form")
    elif form.trend == "down":
        reasons.append(
            f"Cooling off — last 3 games {form.trend_delta:+.0f} vs prior form "
            f"(projection shaded {form.trend_mult - 1:+.0%})"
        )

    # THE CHAIN, in the order the code multiplied it. The usage bridge is
    # recorded as a step rather than folded into the base so the reader can
    # see the form mean the player's own games earned before the measured
    # role pulled on it.
    steps = []
    if form.mean > 0:
        base_val, base_src = form.mean, "form"
        if abs(mean_base / form.mean - 1.0) > 1e-9:
            steps.append(chain.step("usage", mean_base / form.mean, usage_why))
    else:
        # A form mean of zero cannot be multiplied INTO anything, so the
        # blended number becomes the base and says so. Rare, but a chain
        # that silently starts from zero would claim the model projected
        # nothing and then arrive somewhere else.
        base_val = mean_base
        base_src = "usage" if mean_base != form.mean else "form"
    steps += mult_steps
    steps += [
        chain.step("trend", form.trend_mult,
                   f"Last 3 games {form.trend_delta:+.1f} against prior form."
                   if form.trend != "flat" else
                   "Recent games sit where the longer sample does."),
        chain.step("context", ctx_mult, "; ".join(ctx_reasons)),
        chain.step("player", player_mult,
                   "The record's own correction for players this blend "
                   "persistently misreads." if abs(player_mult - 1.0) >= 0.005
                   else "Nothing in the record says this blend misreads him."),
    ]
    return Projection(
        mean=mean,
        std=adj_std,
        form=form,
        matchup=matchup,
        weather=weather,
        injury=injury,
        reasons=reasons,
        chain=chain.build(base_val, base_src, steps, mean,
                          weights=dict(form_weights or WINDOW_WEIGHTS),
                          sample_games=form.sample_games,
                          shrunk_to=form.shrunk_to),
    )
