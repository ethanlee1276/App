"""MLB end-to-end pipeline.

Emits the exact same JSON shape as the NFL pipeline (plus ``sport: "mlb"`` and
park context per game), so the web dashboard renders both sports through the
same components.
"""

from __future__ import annotations

from pathlib import Path

from ..rules import RuleConfig
from ..models import live_to_dict
from ..gamebets import (
    mlb_win_prob, price_moneyline, moneyline_to_dict, LEAGUE_AVG_XERA,
    project_total, game_margin, price_total, price_spread,
)
from .data_loader import load_mlb_slate, MLBSlate
from .models import MARKET_LABELS
from .parks import get_park
from .projection import build_mlb_projection
from .betting import evaluate_mlb_prop
from .rules import apply_mlb_rules


def _avg(vals):
    return round(sum(vals) / len(vals), 2) if vals else None


def _finish_bet(d: dict, g, config: RuleConfig) -> dict:
    d["recommended"] = (d["grade"] != "Pass"
                        and d["confidence"] >= config.min_confidence
                        and d["edge"] >= config.min_edge)
    d["live"] = bool(g.live and g.live.state == "live")
    return d


def _game_bets(games, config: RuleConfig) -> list[dict]:
    """Price moneyline, total (O/U) and run line from team ratings + starters."""
    out = []
    for g in games:
        has_rating = any((g.home_rating, g.away_rating,
                          g.home_off, g.home_def, g.away_off, g.away_def))
        home_p = g.pitchers.get(g.home)
        away_p = g.pitchers.get(g.away)
        home_xera = home_p.xera if home_p else LEAGUE_AVG_XERA
        away_xera = away_p.xera if away_p else LEAGUE_AVG_XERA
        if g.home_ml and g.away_ml:
            wp_home = mlb_win_prob(g.home_rating, g.away_rating, home_xera, away_xera)
            ctx = [f"Run rating: {g.home} {g.home_rating:+.2f} vs {g.away} "
                   f"{g.away_rating:+.2f} run diff/game"]
            if home_p and away_p:
                ctx.append(f"Starters: {home_p.name} ({home_xera:.2f} xERA) vs "
                           f"{away_p.name} ({away_xera:.2f} xERA)")
            ml = moneyline_to_dict(price_moneyline(g.home, g.away, wp_home,
                                                   g.home_ml, g.away_ml, ctx))
            out.append(_finish_bet(ml, g, config))
        if has_rating:
            pt = project_total("mlb", g.home_off, g.home_def, g.away_off, g.away_def)
            tctx = [f"Scoring form: {g.home} off {g.home_off:+.2f} / def {g.home_def:+.2f}, "
                    f"{g.away} off {g.away_off:+.2f} / def {g.away_def:+.2f} (runs/game vs avg)"]
            total = price_total("mlb", g.home, g.away, pt, g.total,
                                g.total_over_odds, g.total_under_odds, "runs", tctx)
            out.append(_finish_bet(total, g, config))
            if g.spread:
                margin = game_margin("mlb", g.home_rating, g.away_rating)
                sctx = [f"Projected run margin {margin:+.2f} (home)"]
                spread = price_spread("mlb", g.home, g.away, margin, g.spread,
                                      g.spread_home_odds, g.spread_away_odds, sctx)
                out.append(_finish_bet(spread, g, config))
    out.sort(key=lambda r: (r["recommended"], r["confidence"], r["edge"]), reverse=True)
    return out


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
        "game_bets": _game_bets(slate.games, config),
    }
