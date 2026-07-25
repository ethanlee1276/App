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
from .rules import apply_rules, RuleConfig, game_has_started
from .explain import headline, summary, bullet_reasons
from .gamebets import (
    nfl_win_prob, price_moneyline, moneyline_to_dict,
    project_total, project_team_points, game_margin,
    price_total, price_team_total, price_spread,
)


def _half(x: float) -> float:
    """Round to the nearest half-point (how books post totals)."""
    return round(x * 2) / 2


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
            {"book": ln.book, "line": ln.line, "over_odds": ln.over_odds, "under_odds": ln.under_odds}
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


def _opportunity_shares(slate) -> dict:
    """Each player's share of his team's skill-position workload.

    Derived from the volume markets already on the slate (rush yards for backs,
    receptions/receiving yards for pass catchers) — a usable stand-in for the
    touch/target share the touchdown model wants, since play-by-play isn't
    ingested.
    """
    from .models import RUSH_YDS, REC_YDS, RECEPTIONS

    def _mean(prop):
        vals = [g.value for g in prop.logs]
        return sum(vals) / len(vals) if vals else 0.0

    volume: dict[tuple[str, str], float] = {}
    for prop in slate.props:
        if prop.market not in (RUSH_YDS, REC_YDS, RECEPTIONS):
            continue
        # Receptions and receiving yards describe the same role; keep the larger
        # signal rather than double-counting a pass catcher.
        key = (prop.team, prop.player)
        volume[key] = max(volume.get(key, 0.0), _mean(prop))

    team_totals: dict[str, float] = {}
    for (team, _player), v in volume.items():
        team_totals[team] = team_totals.get(team, 0.0) + v
    return {key: (v / team_totals[key[0]] if team_totals.get(key[0]) else 0.0)
            for key, v in volume.items()}


def _long_shots(slate) -> list[dict]:
    """Anytime-touchdown picks — the NFL long-shot board (see engine.touchdowns)."""
    from .models import ANYTIME_TD
    from .touchdowns import build_td_longshots

    shares = _opportunity_shares(slate)
    candidates = []
    for prop in slate.props:
        if prop.market != ANYTIME_TD or not prop.lines:
            continue
        best = max(prop.lines, key=lambda ln: ln.over_odds)
        candidates.append({
            "prop": prop, "game": slate.game_for(prop),
            "opponent": slate.team(prop.opponent),
            "opportunity_share": shares.get((prop.team, prop.player), 0.15),
            "odds": best.over_odds, "book": best.book,
            "under_odds": best.under_odds,
        })
    return [p.to_dict() for p in build_td_longshots(candidates)]


def _finish_bet(d: dict, g, config: RuleConfig) -> dict:
    started = game_has_started(g)
    d["recommended"] = (d["grade"] != "Pass"
                        and d["confidence"] >= config.min_confidence
                        and d["edge"] >= config.min_edge
                        and d["odds"] >= config.max_juice
                        and not (config.block_live_games and started))
    if started:
        d.setdefault("warnings", []).append(
            "Game already started — pre-game model cannot price an in-play market")
    d["live"] = bool(g.live and g.live.state == "live")
    d["date"] = g.date
    d["kickoff"] = g.kickoff
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
            # Team totals — each team's own points, line split from total ± spread.
            ph = project_team_points("nfl", g.home_off, g.away_def)
            pa = project_team_points("nfl", g.away_off, g.home_def)
            hl, al = _half((g.total - g.spread) / 2), _half((g.total + g.spread) / 2)
            out.append(_finish_bet(price_team_total("nfl", g.home, g.home, g.away, ph, hl,
                                                    units="points"), g, config))
            out.append(_finish_bet(price_team_total("nfl", g.away, g.home, g.away, pa, al,
                                                    units="points"), g, config))
            if g.spread:
                margin = game_margin("nfl", g.home_rating, g.away_rating)
                sctx = [f"Projected margin {margin:+.1f} pts (home)"]
                spread = price_spread("nfl", g.home, g.away, margin, g.spread,
                                      g.spread_home_odds, g.spread_away_odds, sctx)
                out.append(_finish_bet(spread, g, config))
    out.sort(key=lambda r: (r["recommended"], r["confidence"], r["edge"]), reverse=True)
    return out


def run_slate(slate: Slate | str | Path, config: RuleConfig | None = None,
              model=None, allow_synthetic_line: bool = False) -> dict:
    """``allow_synthetic_line`` is for the backtest harness, which prices
    against a naive baseline line on purpose (see engine.betting.temper_edge)."""
    if not isinstance(slate, Slate):
        slate = load_slate(slate)
    config = config or RuleConfig()

    results = []
    for prop in slate.props:
        game = slate.game_for(prop)
        opponent = slate.team(prop.opponent)
        proj = build_projection(prop, game, opponent, model=model)
        rec = evaluate_prop(prop, proj, allow_synthetic_line=allow_synthetic_line)
        decision = apply_rules(rec, prop, game, config)
        d = _rec_to_dict(rec, prop, decision, proj)
        d["live"] = bool(game.live and game.live.state == "live")
        d["game_date"] = game.date
        d["game_kickoff"] = game.kickoff
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
        "long_shots": _long_shots(slate),
    }


def _game_to_dict(g) -> dict:
    """Per-game context for the dashboard's stadium + weather visuals."""
    w = g.weather
    fav = g.home if g.spread < 0 else g.away
    return {
        "home": g.home,
        "away": g.away,
        "date": g.date,
        "kickoff": g.kickoff,
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
