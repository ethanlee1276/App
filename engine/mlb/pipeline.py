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


#: How many rows the Long Shots board carries, total. Value picks first,
#: topped up from the most-likely ranking. Three is the whole board — the
#: page used to print every real-priced home run on the slate below the
#: picks, which is two hundred names most nights.
LONGSHOT_BOARD = 3


def _long_shots(slate) -> tuple[list[dict], list[dict], dict, list[dict]]:
    """Home-run board: (value picks, top-up watchlist, diagnosis, full pool).

    Picks apply the odds window + edge bar; the watchlist ranks every
    real-priced HR over by model probability so the page always answers
    "who could go deep tonight" even when no price clears the value bar.

    The fourth return is the UNTRIMMED pool, for the market scanner only.
    It is deliberately not the same list the site or the journal sees.

    The diagnosis counts survivors at each gate of the funnel — lineups →
    0.5-line quote → real book → believable plus-money price — so an empty
    board can say exactly WHY it's empty instead of leaving a blank page to
    be debugged by screenshot."""
    from .homeruns import build_hr_longshots, hr_watchlist
    from .models import HOME_RUNS

    diag = {"hr_props": 0, "posted_half": 0, "real_priced": 0, "plus_money": 0}
    candidates = []
    recent_by_player: dict[str, list] = {}
    for prop in slate.props:
        if prop.market != HOME_RUNS:
            continue
        diag["hr_props"] += 1
        if not prop.lines:
            continue
        game = slate.game_for(prop)
        # ONLY the 0.5 line — "hits a homer". Mixing in 1.5-line prices
        # (2+ HR, e.g. +2000) against a 1+ HR probability manufactured
        # 400%+ fake EV.
        overs = [ln for ln in prop.lines if ln.line == 0.5 and ln.over_odds]
        if not overs:
            continue
        diag["posted_half"] += 1
        best = max(overs, key=lambda ln: ln.over_odds)
        if (best.book or "").lower() != "proxy":
            diag["real_priced"] += 1
            if 100 < int(best.over_odds) <= 1500:
                diag["plus_money"] += 1
        recent_by_player[prop.player] = [g.value for g in prop.logs][:12]
        candidates.append({"prop": prop, "game": game, "odds": best.over_odds,
                           "book": best.book, "under_odds": best.under_odds})
    # Top THREE picks — the same three the Recommended page features.
    picks = [p.to_dict() for p in build_hr_longshots(candidates, limit=3,
                                                     per_team=2)]
    # hr_env and the batting slot ride on every long-shot row — this is
    # the exact board the park, wind and lineup dimensions exist to
    # explain.
    env_by_player = {c["prop"].player: _env_of(c["game"])
                     for c in candidates}
    slot_by_player = {c["prop"].player: int(c["prop"].lineup_spot or 0)
                      for c in candidates}
    for d in picks:
        d["recent_values"] = recent_by_player.get(d.get("player", ""), [])
        d.update(env_by_player.get(d.get("player", ""), {}))
        d["lineup_slot"] = slot_by_player.get(d.get("player", ""))
    # The watchlist is computed in full and TRIMMED before it leaves here.
    #
    # It used to ship unlimited, on the reasoning that every real-priced
    # home run belongs on the Long Shots page. In practice that is a wall of
    # two hundred names a night, and it was being journaled too: a couple
    # hundred rows an evening in a bucket nobody reads, which is most of the
    # journal by volume and all of the noise in it. The board shows three.
    #
    # The full list stays alive inside this function because the market
    # scanner reads it — a scanner reporting "no plus-money props" while the
    # site carries +400 home runs is contradicting itself, and that is a
    # different page answering a different question.
    watch_all = hr_watchlist(candidates, limit=None)
    watch = watch_all
    # Stamp lineup state on every row. The board may SHOW a projected
    # hitter (with the caveat), but the journal must not BET him: on rest
    # days a third of projected names never start, and each one becomes a
    # permanently unsettleable row. Measured on 2026-07-26: 31 of 58
    # journaled long shots were projected players who sat.
    confirmed = {c["prop"].player: bool(getattr(c["game"], "lineups_confirmed", True))
                 for c in candidates}
    for d in picks + watch_all:
        d["lineup_confirmed"] = confirmed.get(d.get("player", ""), True)
        if "park_hr" not in d:
            d.update(env_by_player.get(d.get("player", ""), {}))
        if "lineup_slot" not in d:
            d["lineup_slot"] = slot_by_player.get(d.get("player", ""))
    # Trim to what tops the board up to three. Zero picks means three from
    # the most-likely ranking; three picks means none. Either way the page
    # is three rows, which is what "the top three long shots" means.
    have = {d.get("player") for d in picks}
    watch = [w for w in watch_all
             if w.get("player") not in have][:max(0, LONGSHOT_BOARD - len(picks))]
    return picks, watch, diag, watch_all


def _finish_bet(d: dict, g, config: RuleConfig) -> dict:
    started = game_has_started(g)
    # No Leans (docs §10): a lean is a bet that failed the filter published
    # anyway. Lean-graded game bets still render, but never as picks.
    d["recommended"] = (d["grade"] not in ("Pass", "Lean")
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
    if getattr(g, "doubleheader", False):
        # The journal stamps this as the bet's leg — the settler grades a
        # DH team bet against ITS game, not a coin-flip choice of two.
        d["doubleheader"] = True
        d["game_number"] = g.game_number
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


def _market_scan(results: list[dict], long_shots: list[dict] | None = None) -> dict:
    """Cross-book arbitrage / middle / low-hold / stale-line scan."""
    from ..marketscan import scan_recommendations, stale_quotes, longshot_warnings
    out = scan_recommendations(results)
    # The one section backed by a measured CLV result rather than by
    # structure alone — see marketscan.stale_quotes.
    out["stale"] = stale_quotes(results)
    # Avoidance rule, measured not assumed — see longshot_warnings. The
    # home-run board is exactly the population the rule exists for, so it
    # feeds in alongside the main props — a scanner that said "no
    # plus-money props" while the Long Shots page carried +400s was
    # contradicting its own site.
    quotes = list(results)
    seen = set()          # a pick can also sit on the watchlist — one row each
    for r in long_shots or []:
        key = (r.get("player"), r.get("odds"))
        if key in seen:
            continue
        seen.add(key)
        quotes.append({**r, "market_label": r.get("market_label", "Home Runs"),
                       "line": r.get("line", 0.5)})
    out["longshots"] = longshot_warnings(quotes)
    return out


def _env_of(game) -> dict:
    """The hr_env measurements at pick time: park HR index, signed wind
    toward center field (+out/−in, None indoors), roof state. Journaled on
    every MLB bet so the miner can slice "wind out at a boosting park"
    under the same false-discovery control as everything else — the
    hypothesis lab's top watchlist idea, made measurable."""
    park = get_park(game.park)
    w = game.weather
    roofed = bool(w.roof_closed) or park.roof == "dome"
    wo = (None if roofed
          else 0.0 if w.wind_dir_rel == "cross"
          else round(w.wind_mph, 1) if w.wind_dir_rel == "out"
          else round(-w.wind_mph, 1))
    return {"park_hr": park.hr_factor, "wind_out": wo, "roofed": roofed}


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
        # §9/§10 — the unified 0–100 grade, market tier and volatility.
        "quality": rec.quality, "tier": rec.tier, "volatility": rec.volatility,
        "recent_values": vals[:12],
        "trend_delta": round(proj.form.trend_delta, 2),
        "recommended": decision.recommend, "warnings": decision.warnings,
        "headline": f"{rec.player} {rec.side} {rec.line:g} {label}",
        "summary": (
            f"Model projects {rec.projection:g} "
            f"(range {rec.proj_low:g}–{rec.proj_high:g}) vs a line of {rec.line:g}, "
            f"a {rec.hit_prob:.0%} hit probability against the book's "
            f"{rec.fair_prob:.0%} — a {rec.edge:+.1%} edge. "
            f"Quality {rec.quality}/100 (Tier {rec.tier}, {rec.volatility}) → {rec.grade}."
        ),
        "reasons": rec.reasons[:8],
        "all_lines": [
            {"book": ln.book, "line": ln.line, "over_odds": ln.over_odds, "under_odds": ln.under_odds}
            for ln in prop.lines
        ],
        "logs": [
            # Each MLB log row is one GAME (not a week); carry its real date
            # so the site can label it as such.
            #
            # `park` is the CONDITIONS column the past-performance table asks
            # for (redesign spec §6.4: "add the conditions column — WIND for
            # NFL, PARK for MLB"). It needs no new data source: a log already
            # records the opponent and whether the player was home, and those
            # two facts name the venue exactly. The HR factor rides along
            # because "Coors" only means something if you know it plays +22%.
            {**_log_park(prop, g),
             "week": g.game, "date": g.date, "opponent": g.opponent,
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


def _conditions(g, park, results: list[dict] | None) -> dict:
    """Did this park's conditions actually MOVE a number tonight?

    The NFL half of this lives in engine/pipeline.py and the reasoning is
    the same — see the long note there. Here the model is the PARK rather
    than the weather: `evaluate_park` returns per-market multipliers, and a
    park is material when one of the markets it moves is a market someone
    priced at this game tonight.

    Coors is not "material" on a card where the only priced prop is
    strikeouts and the altitude never touched the number. That distinction
    is the whole point of §5.1 — an amber stroke is a claim, and a claim
    that is always true says nothing.
    """
    from .parks import evaluate_park
    from .homeruns import park_weather_multiplier

    eff = evaluate_park(park)
    moved = {m for m, mult in eff.multipliers.items() if abs(mult - 1.0) > 1e-9}
    priced = {r.get("market") for r in (results or [])
              if r.get("team") in (g.home, g.away)
              or r.get("opponent") in (g.home, g.away)}
    hit = sorted(moved & priced) if priced else sorted(moved)

    """Wind and temperature are NOT in evaluate_park — that function only
    knows the building. The home-run model is where a ballpark's weather
    actually gets priced, so ask it, and take its sentences.

    This matters at Wrigley specifically. Its park factors (hr 1.04, run
    1.02) sit under evaluate_park's own thresholds, so the park moves
    nothing — but 16mph blowing OUT is the most famous wind effect in
    baseball, and the park's own profile text says to check the wind before
    anything else there. The first version of this flagged that game
    material with an EMPTY reason list, which is precisely the failure §5.1
    forbids: an amber stroke that encodes nothing."""
    hr_mult, hr_reasons, _caveats = park_weather_multiplier(g)
    weather_moved = abs(hr_mult - park.hr_factor) > 1e-9

    w = g.weather
    roofed = bool(w.roof_closed or park.roof == "dome")
    why = list(eff.reasons)
    # WEATHER sentences only. The two functions overlap on the park itself,
    # and exact-match dedupe is not enough because they word it differently:
    # Coors came out saying "boosts home runs (+22% vs average)" AND "plays
    # big for home runs (+22% HR factor)", and named its altitude twice.
    _WEATHER = ("wind", "°f", "roof", "air")
    why += [r for r in hr_reasons
            if any(k in r.lower() for k in _WEATHER)
            and "altitude" not in r.lower()
            and r not in why]
    return {
        "material": bool(hit) or roofed or weather_moved,
        "markets_moved": hit,
        "roofed": roofed,
        "why": why,
    }


def _log_park(prop, log) -> dict:
    """The ballpark a past game was played in, plus how it plays.

    Returns {} when the team is unknown, so the column is OMITTED rather than
    rendered as a row of em dashes — a blank column is worse than no column,
    because it looks like the data is missing rather than not applicable."""
    from .parks import park_of_game

    park = park_of_game(getattr(prop, "team", "") or "",
                        getattr(log, "opponent", "") or "",
                        bool(getattr(log, "home", True)))
    if park is None:
        return {}
    return {"park": park.name, "park_hr": round(park.hr_factor, 2)}


def _game_to_dict(g, results: list[dict] | None = None) -> dict:
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
        # Reference detail for the game page — dimensions, walls, and what
        # the park is known for. Display only; the factors above are what
        # the model actually prices with.
        "park": {
            "key": park.key, "name": park.name, "team": park.team,
            "lf_ft": park.lf_ft, "cf_ft": park.cf_ft, "rf_ft": park.rf_ft,
            "lf_wall_ft": park.lf_wall_ft, "rf_wall_ft": park.rf_wall_ft,
            "capacity": park.capacity, "opened": park.opened,
            "altitude_ft": park.altitude_ft, "roof": park.roof,
            "surface": park.surface, "plays": park.plays,
        },
        "lineups_confirmed": g.lineups_confirmed,
        # The probable starters, for the ballpark card — the first thing a
        # bettor asks about a game the model already knows the answer to.
        # Display fields only; the matchup math consumes g.pitchers itself.
        "pitchers": {
            side: {"name": getattr(p, "name", ""),
                   "throws": getattr(p, "throws", ""),
                   "xera": getattr(p, "xera", None),
                   "k_rate": getattr(p, "k_rate", None)}
            for side, p in (("home", g.pitchers.get(g.home)),
                            ("away", g.pitchers.get(g.away)))
            if p is not None and getattr(p, "name", "")
        },
        # Real moneyline prices ride along (0 = not offered): the team-form
        # sampler journals the hot side at the price someone could bet.
        "home_ml": g.home_ml, "away_ml": g.away_ml,
        "game_number": getattr(g, "game_number", 1),
        "doubleheader": getattr(g, "doubleheader", False),
        "weather": {
            "dome": w.roof_closed or park.roof == "dome",
            "temp_f": w.temp_f, "wind_mph": w.wind_mph,
            "wind_dir": w.wind_dir_rel,       # "out" | "in" | "cross"
            "rain": w.precip_chance >= 0.5, "snow": False,
        },
        # §5.1's encoding contract, computed rather than assumed.
        "conditions": _conditions(g, park, results),
    }


# "Should we be looser?" is an empirical question, not a debate. These
# margins define "missed by a hair": edge at least this fraction of the
# tier's bar, or quality at least this close to 70 — everything else
# (real price, credibility, calibration) already passed. The sampler
# journals these nightly at a flat paper stake; if the bucket PROFITS
# over 100+ graded, the real gates loosen. If it burns, they've earned
# their strictness. Same promotion bar as every other probation signal.
NEAR_EDGE_FRACTION = 0.70
NEAR_QUALITY_FLOOR = 58.0


def _is_priced_out(r: dict) -> bool:
    """Graded, but Kelly sized it at zero — the read was good and the price
    was not. Distinct from a Pass (the read itself failed) and from a
    near-miss (the edge fell short of the tier bar)."""
    # The key must be PRESENT. A dict that simply carries no stake_units
    # has not been sized at all, and treating "absent" as "Kelly refused"
    # swallowed every ordinary near-miss into this bucket — the existing
    # near-miss test caught it. Priced out means the sizer ran and returned
    # nothing, not that nobody asked it.
    if "stake_units" not in r:
        return False
    return (r.get("grade") not in (None, "", "Pass")
            and float(r.get("stake_units") or 0) <= 0)


def priced_out(recommendations: list[dict]) -> list[dict]:
    """Tonight's picks the model liked and Kelly refused."""
    return [r for r in recommendations
            if _is_priced_out(r) and r.get("has_market") is not False]


def near_misses(recommendations: list[dict], limit: int = 10) -> list[dict]:
    """The props just UNDER the bar tonight — the ones a looser model
    would have picked. Real-priced, credible, calibration-open Tier 1/2
    only; each row says which gate stopped it and by how much."""
    from ..calibrate import is_reliable
    from .quality import TIER_MIN_EDGE
    out = []
    for r in recommendations:
        if r.get("recommended") or r.get("has_market") is False:
            continue
        # A priced-out pick is a different population: it CLEARED the edge
        # bar and lost to the vig, where a near-miss fell short of the bar
        # itself. Mixing them makes the "should the gates be looser?" answer
        # a blend of two unrelated questions, and double-journals the row.
        if _is_priced_out(r):
            continue
        tier = r.get("tier", 2)
        if tier == 3 or r.get("market") == "home_runs":
            continue                      # the Long Shots board owns those
        if not is_reliable("mlb", r.get("market", "")):
            continue
        edge, quality = float(r.get("edge") or 0), float(r.get("quality") or 0)
        bar = TIER_MIN_EDGE.get(tier, 0.030)
        if edge < NEAR_EDGE_FRACTION * bar or quality < NEAR_QUALITY_FLOOR:
            continue
        if edge >= bar and quality >= 70:
            continue                      # died at a structural gate — not
                                          # a candidate for "looser bars"
        misses = []
        if edge < bar:
            misses.append(f"edge {edge:.1%} vs {bar:.1%} bar")
        if quality < 70:
            misses.append(f"quality {quality:.0f}/70")
        out.append({
            "player": r.get("player"), "team": r.get("team"),
            "market": r.get("market"), "market_label": r.get("market_label"),
            "side": r.get("side"), "line": r.get("line"),
            "odds": r.get("odds"), "book": r.get("book"),
            "edge": round(edge, 4), "quality": quality, "tier": tier,
            "hit_prob": r.get("hit_prob"), "grade": r.get("grade"),
            "missed_by": " · ".join(misses),
        })
    # Closest to the bar first — the best case looser gates could make.
    out.sort(key=lambda x: -(x["edge"] * (x["quality"] / 100.0)))
    return out[:limit]


def gate_census(recommendations: list[dict]) -> dict:
    """Where did the slate's props die? One count per first-failing gate, so
    "878 analyzed → 1 recommended" is a funnel you can read instead of a
    number you have to trust. Tune thresholds against THIS, not vibes."""
    from ..betting import favourite_surcharge, MAX_CREDIBLE_EDGE
    from ..odds import american_to_prob
    from ..calibrate import is_reliable
    from .quality import TIER_SHRINK, TIER_MIN_EDGE
    census = {"recommended": 0, "no_real_price": 0, "longshot_board": 0,
              "credibility": 0, "calibration": 0, "tier_edge_bar": 0,
              "price_net": 0, "quality_under_70": 0, "held_by_rules": 0}
    closed_markets: set = set()
    for r in recommendations:
        if r.get("recommended"):
            census["recommended"] += 1
            continue
        if r.get("has_market") is False:
            census["no_real_price"] += 1
            # WHICH markets go unpriced matters: books post a total-bases
            # line for most starters but strikeouts only for the two
            # pitchers, so a big count here is usually the shape of the
            # books' menu, not a broken join. Named, it's checkable.
            census.setdefault("no_price_markets", {})
            lbl = r.get("market_label") or r.get("market", "?")
            census["no_price_markets"][lbl] = \
                census["no_price_markets"].get(lbl, 0) + 1
            continue
        # Tier 3 (home runs) is quarantined on the Long Shots board BY
        # DESIGN — counting those deaths under "calibration" made 197
        # working-as-intended props read as a broken model.
        if r.get("tier", 2) == 3 or r.get("market") == "home_runs":
            census["longshot_board"] += 1
            continue
        if not is_reliable("mlb", r.get("market", "")):
            census["calibration"] += 1
            closed_markets.add(r.get("market_label") or r.get("market", ""))
            continue
        tier = r.get("tier", 2)
        shrink = TIER_SHRINK.get(tier, 0.45)
        raw = (r.get("edge") or 0) / shrink if shrink else 0
        if abs(raw) > MAX_CREDIBLE_EDGE:
            census["credibility"] += 1
            continue
        if (r.get("edge") or 0) < TIER_MIN_EDGE.get(tier, 0.03):
            census["tier_edge_bar"] += 1
            continue
        net = (r.get("hit_prob") or 0) - american_to_prob(r.get("odds") or -110)
        if net <= favourite_surcharge(r.get("odds") or -110):
            census["price_net"] += 1
            continue
        if (r.get("quality") or 0) < 70:
            census["quality_under_70"] += 1
            continue
        census["held_by_rules"] += 1     # lineups, IL, live game, juice, sliders
    if closed_markets:
        # NAME the closed markets — 197 props dying to "calibration" is a
        # mystery; "Total Bases closed until the fit comes off its boundary"
        # is a diagnosis.
        census["calibration_markets"] = sorted(closed_markets)
    return census


def run_mlb_slate(slate: MLBSlate | str | Path,
                  config: RuleConfig | None = None, model=None,
                  il_map: dict | None = None) -> dict:
    """``il_map`` (engine.mlb.transactions.il_status) marks players on the
    injured list — never a pick, whatever the projected lineup says — and
    recent activations, whose form window predates the injury."""
    from ..sources.oddsapi import normalize_name
    from .models import HITS, TOTAL_BASES, HOME_RUNS
    from .transactions import just_returned
    if not isinstance(slate, MLBSlate):
        slate = load_mlb_slate(slate)
    config = config or RuleConfig()
    il_map = il_map or {}

    il_on_slate: set = set()
    results = []
    # Two phases, because coherence is a property of a PLAYER, not a prop:
    # build every projection first, force each batter's hits/total-bases/HR
    # trio into the box real baseball allows (the reconcile gate measured
    # ~40 impossible trios a night when each market projected alone), and
    # only then evaluate — so the prices, the cards and the game sim all
    # read the same, possible, numbers.
    built = []
    trio: dict = {}
    for prop in slate.props:
        game = slate.game_for(prop)
        proj = build_mlb_projection(prop, game, model=model)
        built.append((prop, game, proj))
        if prop.market in (HITS, TOTAL_BASES, HOME_RUNS):
            key = (normalize_name(prop.player),
                   getattr(game, "game_number", 1))
            trio.setdefault(key, {})[prop.market] = proj
    from .projection import reconcile_triple
    for markets in trio.values():
        if not all(m in markets for m in (HITS, TOTAL_BASES, HOME_RUNS)):
            continue
        h, t, r = markets[HITS], markets[TOTAL_BASES], markets[HOME_RUNS]
        hr_new, tb_new, note = reconcile_triple(h.mean, t.mean, r.mean)
        if not note:
            continue
        if abs(hr_new - r.mean) > 1e-9:
            r.mean = round(hr_new, 4)
            r.reasons.append(f"Coherence: {note}")
        if abs(tb_new - t.mean) > 1e-9:
            t.mean = round(tb_new, 4)
            t.reasons.append(f"Coherence: {note}")
    for prop, game, proj in built:
        rec = evaluate_mlb_prop(prop, proj, game=game)
        decision = apply_mlb_rules(rec, prop, game, proj, config)
        d = _rec_to_dict(rec, prop, decision, proj)
        il = il_map.get(normalize_name(prop.player))
        if il and il.get("on_il"):
            # A projected lineup can't know he's hurt; the wire does.
            d["recommended"] = False
            d["warnings"] = list(d.get("warnings") or []) + [
                f"On the injured list (since {il.get('date', '?')}) — "
                f"never a pick until activated"]
            il_on_slate.add(prop.player)
        elif il and just_returned(il, slate.date):
            d["warnings"] = list(d.get("warnings") or []) + [
                f"Activated from the IL on {il.get('date', '?')} — recent "
                f"form predates the injury; treat the sample with care"]
        d["live"] = bool(game.live and game.live.state == "live")
        d["game_date"] = game.date
        d["game_kickoff"] = game.kickoff
        d.update(_env_of(game))
        # Bullpen workload at pick time, both sides. The opposing pen's
        # tiredness already MOVES hitter numbers and the own pen's now
        # moves the starter's length — but neither was ever journaled, so
        # nothing could measure whether those multipliers are right. Now
        # the miner can band and convict them like any other dimension.
        _pen = game.bullpen_fatigue or {}
        d["pen_own"] = _pen.get(prop.team)
        d["pen_opp"] = _pen.get(prop.opponent)
        # lineup_status: the batting slot and its certainty at pick time —
        # the PA half of a batter prop. A pitcher prop has no slot, and
        # NULL says so honestly.
        from .models import PITCHER_MARKETS
        if prop.market not in PITCHER_MARKETS:
            d["lineup_slot"] = int(prop.lineup_spot or 0)
            d["lineup_confirmed"] = bool(
                getattr(game, "lineups_confirmed", True))
        if getattr(game, "doubleheader", False):
            # Say WHICH game of the doubleheader this prop is for — on the
            # card, in the headline, everywhere.
            d["game_number"] = game.game_number
            d["doubleheader"] = True
            d["headline"] += f" (DH Game {game.game_number})"
        results.append(d)

    results.sort(key=lambda r: (r["recommended"], r["confidence"], r["edge"]),
                 reverse=True)

    game_bets = _game_bets(slate.games, config)

    # §9/§10 — correlation flags, incoherent-pair rejection, exposure caps.
    # Runs AFTER ranking and BEFORE counts, so a rejected pick never counts
    # as recommended and capped stakes are what the page (and journal) see.
    from ..correlation import flag_mlb_correlations, apply_exposure_caps
    corr = flag_mlb_correlations(results)
    corr["cap_notes"] = apply_exposure_caps(results, game_bets)

    recommended = [r for r in results if r["recommended"]]

    ls_picks, ls_watch, ls_diag, ls_pool = _long_shots(slate)
    if il_on_slate:
        # The HR board runs on the same projected lineups — an IL'd hitter
        # must not sit on a "most likely tonight" list.
        ls_picks = [p for p in ls_picks if p.get("player") not in il_on_slate]
        ls_watch = [w for w in ls_watch if w.get("player") not in il_on_slate]
        ls_pool = [w for w in ls_pool if w.get("player") not in il_on_slate]
    # The Long Shots page and the Recommended page show the SAME three, and
    # there is no fourth. Value picks first, topped up from the most-likely
    # ranking; stamped here so both pages agree on which three.
    from .models import HOME_RUNS as _HR
    featured = [d.get("player") for d in ls_picks + ls_watch][:LONGSHOT_BOARD]
    for r in results:
        if r["market"] == _HR:
            r["hr_featured"] = r["player"] in featured

    out = {
        "date": slate.date,
        "sport": "mlb",
        "generated_from": "mlb-sample-slate",
        "model": "learned" if model is not None else "rules",
        "counts": {"props_analyzed": len(results), "recommended": len(recommended)},
        "gate_census": gate_census(results),
        "near_miss": near_misses(results),
        "priced_out": priced_out(results),
        "config": {"min_confidence": config.min_confidence, "min_edge": config.min_edge},
        "games": [_game_to_dict(g, results) for g in slate.games],
        "recommendations": results,
        "game_bets": game_bets,
        "correlation": corr,
        "long_shots": ls_picks,
        "longshot_watch": ls_watch,
        "longshot_diag": ls_diag,
        # Who on this slate is on the IL right now — the site's receipts
        # for why a familiar name is missing from every list tonight.
        "injured_list": sorted(il_on_slate),
        # The scanner gets the FULL pool, not the trimmed board: a scanner
        # reporting "no plus-money props" while the site carries +400 home
        # runs would be contradicting its own page.
        "market_scan": _market_scan(results, ls_picks + ls_pool),
    }
    # The outside view: what similar past spots actually did, counted off
    # the ingested logs with no distribution assumed. Evidence and a
    # divergence warning only — never a price input (see engine/comps.py).
    from ..pipeline import _attach_comps
    out["comps"] = _attach_comps(results, "mlb")
    # §14, and §5's lineup rule is enforced inside the screen: a hitter leg
    # is ineligible until the card is posted.
    from ..parlays import attach
    return attach(out, "mlb")
