"""MLB end-to-end pipeline.

Emits the exact same JSON shape as the NFL pipeline (plus ``sport: "mlb"`` and
park context per game), so the web dashboard renders both sports through the
same components.
"""

from __future__ import annotations

from pathlib import Path

from ..rules import RuleConfig
from ..models import live_to_dict
from .data_loader import load_mlb_slate, MLBSlate
from .models import MARKET_LABELS
from .parks import get_park
from .projection import build_mlb_projection
from .betting import evaluate_mlb_prop
from .rules import apply_mlb_rules


def _avg(vals):
    return round(sum(vals) / len(vals), 2) if vals else None


def _rec_to_dict(rec, prop, decision, proj) -> dict:
    vals = [g.value for g in prop.logs]
    label = MARKET_LABELS.get(rec.market, rec.market)
    return {
        "player": rec.player, "team": rec.team, "opponent": rec.opponent,
        "market": rec.market, "market_label": label,
        "position": prop.position, "usage_role": prop.position,
        "headshot": prop.headshot,
        "side": rec.side, "book": rec.book, "line": rec.line, "odds": rec.odds,
        "projection": rec.projection, "proj_low": rec.proj_low, "proj_high": rec.proj_high,
        "hit_prob": rec.hit_prob, "fair_prob": rec.fair_prob,
        "edge": rec.edge, "ev_per_unit": rec.ev_per_unit,
        "confidence": rec.confidence, "stake_units": rec.stake_units,
        "grade": rec.grade, "trend": rec.trend,
        "trend_delta": round(proj.form.trend_delta, 2),
        "recommended": decision.recommend, "warnings": decision.warnings,
        "headline": f"{rec.player} {rec.side} {rec.line:g} {label}",
        "summary": (
            f"Model projects {rec.projection:g} "
            f"(range {rec.proj_low:g}–{rec.proj_high:g}) vs a line of {rec.line:g}, "
            f"a {rec.hit_prob:.0%} hit probability against the book's "
            f"{rec.fair_prob:.0%} — a {rec.edge:+.1%} edge. "
            f"Confidence {rec.confidence}/10 → {rec.grade}."
        ),
        "reasons": rec.reasons[:8],
        "all_lines": [
            {"book": ln.book, "line": ln.line, "over_odds": ln.over_odds}
            for ln in prop.lines
        ],
        "logs": [
            {"week": g.game, "opponent": g.opponent, "value": g.value, "home": g.home}
            for g in prop.logs
        ],
        "form": {
            "last1": _avg(vals[:1]), "last3": _avg(vals[:3]),
            "last5": _avg(vals[:5]), "last10": _avg(vals[:10]),
            "season": _avg(vals), "career": prop.career_avg,
            "vs_opponent": prop.vs_pitcher_avg,
        },
    }


def _game_to_dict(g) -> dict:
    park = get_park(g.park)
    w = g.weather
    return {
        "home": g.home, "away": g.away,
        "spread": 0.0, "favorite": "", "total": g.total,
        "roof": park.roof if not w.roof_closed else "closed",
        "surface": park.surface,
        "live": live_to_dict(g.live),
        "park_name": park.name,
        "factors": {"hr": park.hr_factor, "run": park.run_factor, "k": park.k_factor},
        "altitude_ft": park.altitude_ft,
        "lineups_confirmed": g.lineups_confirmed,
        "weather": {
            "dome": w.roof_closed or park.roof == "dome",
            "temp_f": w.temp_f, "wind_mph": w.wind_mph,
            "wind_dir": w.wind_dir_rel,       # "out" | "in" | "cross"
            "rain": w.precip_chance >= 0.5, "snow": False,
        },
    }


def run_mlb_slate(slate: MLBSlate | str | Path,
                  config: RuleConfig | None = None, model=None) -> dict:
    if not isinstance(slate, MLBSlate):
        slate = load_mlb_slate(slate)
    config = config or RuleConfig()

    results = []
    for prop in slate.props:
        game = slate.game_for(prop)
        proj = build_mlb_projection(prop, game, model=model)
        rec = evaluate_mlb_prop(prop, proj)
        decision = apply_mlb_rules(rec, prop, game, proj, config)
        d = _rec_to_dict(rec, prop, decision, proj)
        d["live"] = bool(game.live and game.live.state == "live")
        results.append(d)

    results.sort(key=lambda r: (r["recommended"], r["confidence"], r["edge"]),
                 reverse=True)
    recommended = [r for r in results if r["recommended"]]
    return {
        "date": slate.date,
        "sport": "mlb",
        "generated_from": "mlb-sample-slate",
        "model": "learned" if model is not None else "rules",
        "counts": {"props_analyzed": len(results), "recommended": len(recommended)},
        "config": {"min_confidence": config.min_confidence, "min_edge": config.min_edge},
        "games": [_game_to_dict(g) for g in slate.games],
        "recommendations": results,
    }
