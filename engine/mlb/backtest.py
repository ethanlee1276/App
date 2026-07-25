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


def _norm_name(name: str) -> str:
    """Match the normalisation the odds feed uses, so harvested prices join to
    game logs (odds store "aaron judge"; logs keep "Aaron Judge")."""
    from ..sources.oddsapi import normalize_name
    return normalize_name(name)


def backtest_from_logs(entries: list[dict], market: str, min_history: int = 8,
                       limit: int = 40, config: RuleConfig | None = None,
                       model=None, real_lines: dict | None = None) -> BacktestReport:
    """``entries`` = [{"name", "values": [chronological per-game values],
    "dates": [matching game dates]}].

    Walk-forward: game i is projected from games [:i] (most recent ``limit``),
    then settled against ``values[i]``.

    ``real_lines`` maps ``(player, date)`` to a harvested book price. When a
    game has one, the model is priced against **the number a bettor could
    actually have taken** — which is the difference between "does this beat a
    trailing average?" and "would this have beaten the book?". Games without a
    harvested price fall back to the naive baseline, and ``used_real_lines`` on
    the report says how much of the result rests on real market data.
    """
    config = config or RuleConfig()
    game = _neutral_game()
    settled: list[SettledProp] = []
    real_lines = real_lines or {}
    real_used = 0

    for e in entries:
        vals = e.get("values", [])
        dates = e.get("dates", [])
        spot = e.get("spot", 3)
        for i in range(min_history, len(vals)):
            prior = vals[:i][::-1][:limit]          # most-recent-first, capped
            actual = float(vals[i])
            logs = [MLBGameLog(game=len(prior) - j, opponent="", value=float(v))
                    for j, v in enumerate(prior)]
            career = sum(vals[:i]) / i

            date = dates[i] if i < len(dates) else ""
            quote = real_lines.get((_norm_name(e["name"]), date))
            if quote:
                line = float(quote["line"])
                book_line = SportsbookLine(quote.get("book", "book"), line,
                                           int(quote.get("over_odds") or -110),
                                           int(quote.get("under_odds") or -110))
                real_used += 1
            else:
                line = _naive_line(prior[:10], market)
                book_line = SportsbookLine("proxy", line, -110, -110)

            prop = MLBProp(
                player=e["name"], team="HOME", opponent="AWAY", position="",
                market=market, logs=logs, career_avg=career, vs_pitcher_avg=None,
                lines=[book_line], lineup_spot=spot,
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
                side=rec.side, basis="book" if quote else "naive",
                grade=rec.grade,
            ))

    report = evaluate(settled)
    report.used_real_lines = real_used
    report.total_priced = len(settled)
    return report
