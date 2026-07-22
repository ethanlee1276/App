"""End-to-end pipeline.

Given a slate, run every prop through projection -> betting model -> rules ->
explanation, and return ranked recommendations as plain dicts ready to be
serialised to JSON for the web UI or an API response.
"""

from __future__ import annotations

from pathlib import Path

from .data_loader import load_slate, Slate
from .models import MARKET_LABELS
from .projection import build_projection
from .betting import evaluate_prop
from .rules import apply_rules, RuleConfig
from .explain import headline, summary, bullet_reasons


def _rec_to_dict(rec, prop, decision) -> dict:
    return {
        "player": rec.player,
        "team": rec.team,
        "opponent": rec.opponent,
        "market": rec.market,
        "market_label": MARKET_LABELS.get(rec.market, rec.market),
        "position": prop.position,
        "side": rec.side,
        "book": rec.book,
        "line": rec.line,
        "odds": rec.odds,
        "projection": rec.projection,
        "proj_low": rec.proj_low,
        "proj_high": rec.proj_high,
        "hit_prob": rec.hit_prob,
        "fair_prob": rec.fair_prob,
        "edge": rec.edge,
        "ev_per_unit": rec.ev_per_unit,
        "confidence": rec.confidence,
        "stake_units": rec.stake_units,
        "grade": rec.grade,
        "trend": rec.trend,
        "recommended": decision.recommend,
        "warnings": decision.warnings,
        "headline": headline(rec),
        "summary": summary(rec),
        "reasons": bullet_reasons(rec),
        "all_lines": [
            {"book": ln.book, "line": ln.line, "over_odds": ln.over_odds}
            for ln in prop.lines
        ],
    }


def run_slate(slate: Slate | str | Path, config: RuleConfig | None = None,
              model=None) -> dict:
    if not isinstance(slate, Slate):
        slate = load_slate(slate)
    config = config or RuleConfig()

    results = []
    for prop in slate.props:
        game = slate.game_for(prop)
        opponent = slate.team(prop.opponent)
        proj = build_projection(prop, game, opponent, model=model)
        rec = evaluate_prop(prop, proj)
        decision = apply_rules(rec, prop, game, config)
        results.append(_rec_to_dict(rec, prop, decision))

    # Rank: recommended bets first, then by confidence, then by edge.
    results.sort(key=lambda r: (r["recommended"], r["confidence"], r["edge"]), reverse=True)

    recommended = [r for r in results if r["recommended"]]
    return {
        "date": slate.date,
        "generated_from": "sample-slate",
        "model": "learned" if model is not None else "rules",
        "counts": {
            "props_analyzed": len(results),
            "recommended": len(recommended),
        },
        "config": {
            "min_confidence": config.min_confidence,
            "min_edge": config.min_edge,
        },
        "games": [_game_to_dict(g) for g in slate.games],
        "recommendations": results,
    }


def _game_to_dict(g) -> dict:
    """Per-game context for the dashboard's stadium + weather visuals."""
    w = g.weather
    fav = g.home if g.spread < 0 else g.away
    return {
        "home": g.home,
        "away": g.away,
        "spread": g.spread,
        "favorite": fav,
        "total": g.total,
        "roof": g.roof,
        "surface": g.surface,
        "weather": {
            "dome": w.dome,
            "temp_f": w.temp_f,
            "wind_mph": w.wind_mph,
            "wind_dir": w.wind_dir,
            "rain": w.rain,
            "snow": w.snow,
        },
    }
