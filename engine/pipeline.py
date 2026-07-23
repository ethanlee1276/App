"""End-to-end pipeline.

Given a slate, run every prop through projection -> betting model -> rules ->
explanation, and return ranked recommendations as plain dicts ready to be
serialised to JSON for the web UI or an API response.
"""

from __future__ import annotations

from pathlib import Path

from .data_loader import load_slate, Slate
from .models import MARKET_LABELS, live_to_dict
from .projection import build_projection
from .betting import evaluate_prop
from .rules import apply_rules, RuleConfig
from .explain import headline, summary, bullet_reasons
from .gamebets import (
    nfl_win_prob, price_moneyline, moneyline_to_dict,
    project_total, game_margin, price_total, price_spread,
)


def _avg(vals: list[float]):
    return round(sum(vals) / len(vals), 1) if vals else None


def _rec_to_dict(rec, prop, decision, proj) -> dict:
    vals = [g.value for g in prop.logs]
    return {
        "player": rec.player,
        "team": rec.team,
        "opponent": rec.opponent,
        "market": rec.market,
        "market_label": MARKET_LABELS.get(rec.market, rec.market),
        "position": prop.position,
        "usage_role": prop.usage_role,
        "headshot": prop.headshot,
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
        "trend_delta": round(proj.form.trend_delta, 1),
        "recommended": decision.recommend,
        "warnings": decision.warnings,
        "headline": headline(rec),
        "summary": summary(rec),
        "reasons": bullet_reasons(rec),
        "all_lines": [
            {"book": ln.book, "line": ln.line, "over_odds": ln.over_odds}
            for ln in prop.lines
        ],
        # Per-player history for the Players & Trending pages.
        "logs": [
            {"week": g.week, "opponent": g.opponent, "value": g.value, "home": g.home}
            for g in prop.logs
        ],
        "form": {
            "last1": _avg(vals[:1]),
            "last3": _avg(vals[:3]),
            "last5": _avg(vals[:5]),
            "last10": _avg(vals[:10]),
            "season": _avg(vals),
            "career": prop.career_avg,
            "vs_opponent": prop.vs_opponent_avg,
        },
    }


def _finish_bet(d: dict, g, config: RuleConfig) -> dict:
    d["recommended"] = (d["grade"] != "Pass"
                        and d["confidence"] >= config.min_confidence
                        and d["edge"] >= config.min_edge)
    d["live"] = bool(g.live and g.live.state == "live")
    return d


def _game_bets(games, config: RuleConfig) -> list[dict]:
    """Price moneyline, total and spread for every game with team ratings."""
    out = []
    for g in games:
        has_rating = any((g.home_rating, g.away_rating,
                          g.home_off, g.home_def, g.away_off, g.away_def))
        if g.home_ml and g.away_ml:
            wp_home = nfl_win_prob(g.home_rating, g.away_rating)
            ctx = [f"Power rating: {g.home} {g.home_rating:+.1f} vs {g.away} "
                   f"{g.away_rating:+.1f} net pts/game (incl. home field)"]
            ml = moneyline_to_dict(price_moneyline(g.home, g.away, wp_home,
                                                   g.home_ml, g.away_ml, ctx))
            out.append(_finish_bet(ml, g, config))
        if has_rating:
            pt = project_total("nfl", g.home_off, g.home_def, g.away_off, g.away_def)
            tctx = [f"Scoring form: {g.home} off {g.home_off:+.1f} / def {g.home_def:+.1f}, "
                    f"{g.away} off {g.away_off:+.1f} / def {g.away_def:+.1f} (pts/game vs avg)"]
            total = price_total("nfl", g.home, g.away, pt, g.total,
                                g.total_over_odds, g.total_under_odds, "points", tctx)
            out.append(_finish_bet(total, g, config))
            if g.spread:
                margin = game_margin("nfl", g.home_rating, g.away_rating)
                sctx = [f"Projected margin {margin:+.1f} pts (home)"]
                spread = price_spread("nfl", g.home, g.away, margin, g.spread,
                                      g.spread_home_odds, g.spread_away_odds, sctx)
                out.append(_finish_bet(spread, g, config))
    out.sort(key=lambda r: (r["recommended"], r["confidence"], r["edge"]), reverse=True)
    return out


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
        d = _rec_to_dict(rec, prop, decision, proj)
        d["live"] = bool(game.live and game.live.state == "live")
        results.append(d)

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
        "game_bets": _game_bets(slate.games, config),
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
        "live": live_to_dict(g.live),
        "weather": {
            "dome": w.dome,
            "temp_f": w.temp_f,
            "wind_mph": w.wind_mph,
            "wind_dir": w.wind_dir,
            "rain": w.rain,
            "snow": w.snow,
        },
    }
