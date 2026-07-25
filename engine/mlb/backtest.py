"""MLB walk-forward backtest.

The scoring core (`engine.backtest.evaluate`) is sport-agnostic — it takes
settled props with a projection, a hit probability and the actual result and
reports calibration (reliability bins, Brier, ECE), projection error and
betting ROI. This module produces those settled props for baseball by walking a
player's game log forward: for each game, project it from *prior* games only,
settle against what actually happened.

Because it needs only game logs (no live game context), it runs fully offline —
feed it logs from ``statslogs`` for a real backtest, or the sample slate's logs
for a quick demo. Projections here use a neutral game (generic park, neutral
weather), so this measures the **form model + probability calibration**;
park/weather/matchup/Statcast angles are validated on top with live context.
"""

from __future__ import annotations

from ..backtest import SettledProp, evaluate, BacktestReport
from ..models import SportsbookLine
from ..rules import RuleConfig
from .models import (
    MLBGame, MLBProp, MLBGameLog, HOME_RUNS,
)
from .projection import build_mlb_projection
from .betting import evaluate_mlb_prop
from .rules import apply_mlb_rules


def _neutral_game() -> MLBGame:
    return MLBGame(home="HOME", away="AWAY", park="generic")


def _round_half(x: float) -> float:
    return round(x * 2) / 2.0


def _naive_line(prior_recent: list[float], market: str) -> float:
    """A naive market line the model is measured against: the trailing average
    rounded to the nearest half, a touch under (books shade the over)."""
    if market == HOME_RUNS:
        return 0.5
    base = sum(prior_recent) / len(prior_recent)
    return max(0.5, _round_half(base) - 0.5)


def backtest_from_logs(entries: list[dict], market: str, min_history: int = 8,
                       limit: int = 15, config: RuleConfig | None = None,
                       model=None) -> BacktestReport:
    """``entries`` = [{"name", "values": [chronological per-game values]}].

    Walk-forward: game i is projected from games [:i] (most recent ``limit``),
    then settled against ``values[i]``.
    """
    config = config or RuleConfig()
    game = _neutral_game()
    settled: list[SettledProp] = []

    for e in entries:
        vals = e.get("values", [])
        spot = e.get("spot", 3)
        for i in range(min_history, len(vals)):
            prior = vals[:i][::-1][:limit]          # most-recent-first, capped
            actual = float(vals[i])
            logs = [MLBGameLog(game=len(prior) - j, opponent="", value=float(v))
                    for j, v in enumerate(prior)]
            career = sum(vals[:i]) / i
            line = _naive_line(prior[:10], market)
            prop = MLBProp(
                player=e["name"], team="HOME", opponent="AWAY", position="",
                market=market, logs=logs, career_avg=career, vs_pitcher_avg=None,
                lines=[SportsbookLine("proxy", line, -110, -110)], lineup_spot=spot,
            )
            proj = build_mlb_projection(prop, game, model=model)
            # The naive line above IS the baseline we're measuring against, so
            # the live "placeholder line" guard doesn't apply here.
            rec = evaluate_mlb_prop(prop, proj, allow_synthetic_line=True)
            decision = apply_mlb_rules(rec, prop, game, proj, config)
            settled.append(SettledProp(
                player=e["name"], market=market, line=line, odds=rec.odds,
                hit_prob=rec.hit_prob, projection=rec.projection, actual=actual,
                recommended=decision.recommend, stake_units=rec.stake_units,
            ))

    return evaluate(settled)
