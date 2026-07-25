"""MLB end-to-end pipeline.

Emits the exact same JSON shape as the NFL pipeline (plus ``sport: "mlb"`` and
park context per game), so the web dashboard renders both sports through the
same components.
"""

from __future__ import annotations

from pathlib import Path

from ..rules import RuleConfig, game_has_started
from ..models import live_to_dict
from ..gamebets import (
    mlb_win_prob, price_moneyline, price_moneyline_sharp, moneyline_to_dict,
    LEAGUE_AVG_XERA,
    project_total, project_team_points, game_margin,
    price_total, price_total_sharp, price_team_total, price_spread,
    price_spread_sharp,
)
from .data_loader import load_mlb_slate, MLBSlate
from .models import MARKET_LABELS
from .parks import get_park
from .projection import build_mlb_projection
from .betting import evaluate_mlb_prop
from .rules import apply_mlb_rules


def _half(x: float) -> float:
    """Round to the nearest half-run (how books post totals)."""
    return round(x * 2) / 2


def _avg(vals):
    return round(sum(vals) / len(vals), 2) if vals else None


def _long_shots(slate) -> tuple[list[dict], list[dict]]:
    """Home-run board: (strict value picks, most-likely-tonight watchlist).

    Picks apply the odds window + edge bar; the watchlist ranks every
    real-priced HR over by model probability so the page always answers
    "who could go deep tonight" even when no price clears the value bar."""
    from .homeruns import build_hr_longshots, hr_watchlist
    from .models import HOME_RUNS

    candidates = []
    recent_by_player: dict[str, list] = {}
    for prop in slate.props:
        if prop.market != HOME_RUNS or not prop.lines:
            continue
        game = slate.game_for(prop)
        # ONLY the 0.5 line — "hits a homer". Mixing in 1.5-line prices
        # (2+ HR, e.g. +2000) against a 1+ HR probability manufactured
        # 400%+ fake EV.
        overs = [ln for ln in prop.lines if ln.line == 0.5 and ln.over_odds]
        if not overs:
            continue
        best = max(overs, key=lambda ln: ln.over_odds)
        recent_by_player[prop.player] = [g.value for g in prop.logs][:12]
        candidates.append({"prop": prop, "game": game, "odds": best.over_odds,
                           "book": best.book, "under_odds": best.under_odds})
    picks = [p.to_dict() for p in build_hr_longshots(candidates, limit=6,
                                                     per_team=2)]
    for d in picks:
        d["recent_values"] = recent_by_player.get(d.get("player", ""), [])
    return picks, hr_watchlist(candidates, limit=25)


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


# Measured against real closing moneylines (walk-forward over the harvested
# June–July closes): the ratings-only game model lost -12.4% over 179 bets
# (pitcher-aware -7.5%) with a Brier score worse than the home-field base
# rate — its disagreements with the book are its own error, not edge. So
# MODEL-driven moneyline picks are informational only and never recommended.
# The SHARP-ANCHOR path is different: when the sharp book's pair is quoted,
# a soft price beating its de-vigged fair value is +EV on the price alone
# (backtested +13.5% on the filtered close-vs-close sample) — those picks
# ARE recommendable, and the bet journal validates them forward.
MLB_ML_RECOMMENDATIONS = False


def _info_only(d: dict, why: str) -> dict:
    """Demote a game-bet card to market information: shown, never recommended."""
    d["recommended"] = False
    d["grade"] = "Pass"
    d["stake_units"] = 0.0
    d.setdefault("warnings", []).append(why)
    return d


_NO_ANCHOR = ("No sharp-anchor value at current prices, and the model alone "
              "hasn't beaten the close — info only")


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
            sharp_rec = None
            if g.sharp_home_ml and g.sharp_away_ml:
                sharp_rec = price_moneyline_sharp(
                    g.home, g.away, g.sharp_home_ml, g.sharp_away_ml,
                    g.home_ml, g.away_ml, win_prob_home=wp_home, context=ctx)
            if sharp_rec is not None:
                # Price disagreement vs the sharp book — recommendable.
                out.append(_finish_bet(moneyline_to_dict(sharp_rec), g, config))
            else:
                ml = _finish_bet(moneyline_to_dict(
                    price_moneyline(g.home, g.away, wp_home,
                                    g.home_ml, g.away_ml, ctx)), g, config)
                if not MLB_ML_RECOMMENDATIONS:
                    _info_only(ml, _NO_ANCHOR)
                out.append(ml)
        if has_rating:
            pt = project_total("mlb", g.home_off, g.home_def, g.away_off, g.away_def)
            tctx = [f"Scoring form: {g.home} off {g.home_off:+.2f} / def {g.home_def:+.2f}, "
                    f"{g.away} off {g.away_off:+.2f} / def {g.away_def:+.2f} (runs/game vs avg)"]
            # Totals: sharp-anchored when the sharp book quotes the SAME line;
            # otherwise the model card renders as information only — same
            # policy as moneylines, for the same measured reason.
            sharp_tot = None
            if (g.sharp_total and g.sharp_total == g.total
                    and g.sharp_total_over_odds and g.sharp_total_under_odds):
                sharp_tot = price_total_sharp(
                    g.home, g.away, g.total,
                    g.total_over_odds, g.total_under_odds,
                    g.sharp_total_over_odds, g.sharp_total_under_odds,
                    units="runs", context=tctx)
            if sharp_tot is not None:
                out.append(_finish_bet(sharp_tot, g, config))
            else:
                total = price_total("mlb", g.home, g.away, pt, g.total,
                                    g.total_over_odds, g.total_under_odds, "runs", tctx)
                out.append(_info_only(_finish_bet(total, g, config), _NO_ANCHOR))
            # Team totals — no sharp reference exists for them, so they are
            # always informational.
            ph = project_team_points("mlb", g.home_off, g.away_def)
            pa = project_team_points("mlb", g.away_off, g.home_def)
            tl = _half(g.total / 2)
            out.append(_info_only(_finish_bet(
                price_team_total("mlb", g.home, g.home, g.away, ph, tl,
                                 units="runs"), g, config), _NO_ANCHOR))
            out.append(_info_only(_finish_bet(
                price_team_total("mlb", g.away, g.home, g.away, pa, tl,
                                 units="runs"), g, config), _NO_ANCHOR))
            if g.spread:
                margin = game_margin("mlb", g.home_rating, g.away_rating)
                sctx = [f"Projected run margin {margin:+.2f} (home)"]
                sharp_sp = None
                if (g.sharp_spread and g.sharp_spread == g.spread
                        and g.sharp_spread_home_odds and g.sharp_spread_away_odds):
                    sharp_sp = price_spread_sharp(
                        g.home, g.away, g.spread,
                        g.spread_home_odds, g.spread_away_odds,
                        g.sharp_spread_home_odds, g.sharp_spread_away_odds,
                        context=sctx)
                if sharp_sp is not None:
                    out.append(_finish_bet(sharp_sp, g, config))
                else:
                    spread = price_spread("mlb", g.home, g.away, margin, g.spread,
                                          g.spread_home_odds, g.spread_away_odds, sctx)
                    out.append(_info_only(_finish_bet(spread, g, config), _NO_ANCHOR))
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
        "grade": rec.grade, "has_market": rec.has_market, "trend": rec.trend,
        "recent_values": vals[:12],
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
            {"book": ln.book, "line": ln.line, "over_odds": ln.over_odds, "under_odds": ln.under_odds}
            for ln in prop.lines
        ],
        "logs": [
            # Each MLB log row is one GAME (not a week); carry its real date
            # so the site can label it as such.
            {"week": g.game, "date": g.date, "opponent": g.opponent,
             "value": g.value, "home": g.home}
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
        "date": g.date, "kickoff": g.kickoff,
        "spread": g.spread, "favorite": "", "total": g.total,
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
        d["game_date"] = game.date
        d["game_kickoff"] = game.kickoff
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
        "long_shots": (_ls := _long_shots(slate))[0],
        "longshot_watch": _ls[1],
    }
