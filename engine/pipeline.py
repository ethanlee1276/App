"""End-to-end pipeline.

Given a slate, run every prop through projection -> betting model -> rules ->
explanation, and return ranked recommendations as plain dicts ready to be
serialised to JSON for the web UI or an API response.
"""

from __future__ import annotations

from pathlib import Path

from .data_loader import load_slate, Slate
from .models import (MARKET_LABELS, live_to_dict, PASS_YDS, REC_YDS,
                     RECEPTIONS, ANYTIME_TD)
from . import statlogs
from .projection import build_projection
from .betting import evaluate_prop
from .rules import apply_rules, RuleConfig, game_has_started
from .explain import headline, summary, bullet_reasons
from .stadiums import stadium_to_dict
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
        # The claim BEFORE the shrink toward the market — what the fitter
        # learns on, never the shrunk number (see engine/backtest.py's
        # pairs comment). Not the model's uncorrected claim: live, the
        # calibration temperature has already been applied by the time
        # pick_side sees it, which is why the journal stores the
        # correction beside this number (engine/ledger.py) so
        # calibrate.undo_temperature can strip it back off.
        "raw_prob": rec.raw_prob,
        # The field's fair at pick time, beside the book we shopped
        # to. Evidence only; nothing prices from it yet.
        "fair_consensus": rec.fair_consensus,
        "consensus_books": rec.consensus_books,
        "fair_prob": rec.fair_prob,
        "edge": rec.edge,
        # The margin over the PRICE, and the rule that set the stake —
        # the two numbers that make a board of stakes readable.
        "net_edge": rec.net_edge,
        "stake_basis": rec.stake_basis,
        "ev_per_unit": rec.ev_per_unit,
        "confidence": rec.confidence,
        "stake_units": rec.stake_units,
        "grade": rec.grade, "has_market": rec.has_market,
        # §10/§8 — the unified 0–100 grade, market tier and volatility.
        "quality": rec.quality, "tier": rec.tier, "volatility": rec.volatility,
        "recent_values": vals[:12],
        "trend": rec.trend,
        "trend_delta": round(proj.form.trend_delta, 1),
        "recommended": decision.recommend,
        "warnings": decision.warnings,
        # HOW THIS NUMBER WAS BUILT, and what it had to clear. Both were
        # computed on every pick this site has ever made and both were
        # thrown away at the end of the function that computed them —
        # which left the card able to state a projection and unable to
        # show its arithmetic. See engine/chain.py.
        "chain": proj.chain,
        "checks": decision.checks,
        "headline": headline(rec),
        "summary": summary(rec),
        "reasons": bullet_reasons(rec),
        "all_lines": [
            {"book": ln.book, "line": ln.line, "over_odds": ln.over_odds, "under_odds": ln.under_odds}
            for ln in prop.lines
        ],
        # Per-player history for the Players & Trending pages.
        "logs": [
            {**_log_wind(prop, g),
             "week": g.week, "opponent": g.opponent,
             "value": g.value, "home": g.home}
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


# The slate's own date, set once per build. A game log carries a week
# number but not a year, so the season has to come from the board it is
# being rendered for.
_SLATE_DATE: dict[str, str] = {}


def nfl_season_of(date_str: str | None) -> int:
    """The SEASON a date belongs to, which is not its calendar year.

    An NFL season spans the new year: week 18 of the 2025 season is played
    in January 2026, and the playoffs run to February. Keying on the
    calendar year sent every January game looking in a season the database
    had not started yet — the first version of the conditions column came
    back empty for exactly this reason, on a slate dated 2026-01-04 whose
    games are all stored under 2025.

    March is the cut: the league year opens in mid-March, so anything before
    it still belongs to the season that started the previous autumn.
    """
    import datetime as _dt
    if date_str:
        try:
            d = _dt.date.fromisoformat(str(date_str)[:10])
        except ValueError:
            d = _dt.date.today()
    else:
        d = _dt.date.today()
    return d.year - 1 if d.month < 3 else d.year


def _wind_index(season: int | None = None) -> dict[str, float]:
    """Per-game wind for one NFL season, loaded once.

    Cached on the function because a slate builds a few hundred prop rows and
    each one walks a dozen logs — that is thousands of lookups against the
    same ~190-row table. Returns {} when there is no history database, which
    is the normal state of a fresh clone, and the conditions column is then
    omitted rather than rendered blank.
    """
    season = season or nfl_season_of(None)
    cache = _wind_index.__dict__.setdefault("_cache", {})
    if season in cache:
        return cache[season]
    try:
        from .db import connect, nfl_game_winds
        with connect() as conn:
            cache[season] = nfl_game_winds(conn, season)
    except Exception:
        # A missing or unreadable database must never take a slate down; a
        # board with no wind column is a board, a board that fails to build
        # is nothing.
        cache[season] = {}
    return cache[season]


def _log_wind(prop, log) -> dict:
    """Wind for one past game, or {} if it is not known.

    The player feed does not say which side was home — nflverse weekly rows
    carry no home flag, and GameLog defaults it to True — so rather than
    trust that, try BOTH orderings of the matchup. Only one of "A@B" and
    "B@A" is a real game, so the ambiguity resolves itself and the column
    stops depending on a field that is not actually populated.
    """
    team = (getattr(prop, "team", "") or "").upper()
    opp = (getattr(log, "opponent", "") or "").upper()
    if not team or not opp:
        return {}
    idx = _wind_index(nfl_season_of(getattr(log, "date", None)
                                    or _SLATE_DATE.get("date")))
    for gid in (f"{opp}@{team}", f"{team}@{opp}"):
        if gid in idx:
            return {"wind": round(idx[gid])}
    return {}


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


def _long_shots(slate, usage: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Anytime-touchdown board: ``(value picks, most-likely watchlist)``.

    The picks apply the odds window and the edge bar; the watchlist ranks
    every quoted scorer by model probability with NO window — the -260
    bell cow the script loves shows up there with his price and EV shown
    honestly, never journaled (see touchdowns.td_watchlist for Ethan's
    ask and why the value bar itself did not move).

    ``usage`` optionally carries MEASURED roles from ingested logs
    (engine.nflusage): per-player red-zone usage — the model's own docs
    call it the single best TD predictor it couldn't see — and snap
    shares. Without it the model infers from volume, exactly as before."""
    from .models import ANYTIME_TD
    from .touchdowns import build_td_longshots, td_watchlist
    from .fantasy import _short_key

    usage = usage or {}
    rz_map = usage.get("red_zone") or {}
    snap_map = usage.get("snap") or {}
    shares = _opportunity_shares(slate)
    candidates = []
    for prop in slate.props:
        if prop.market != ANYTIME_TD or not prop.lines:
            continue
        best = max(prop.lines, key=lambda ln: ln.over_odds)
        key = _short_key(prop.player, prop.team)
        candidates.append({
            "prop": prop, "game": slate.game_for(prop),
            "opponent": slate.team(prop.opponent),
            "opportunity_share": shares.get((prop.team, prop.player), 0.15),
            "odds": best.over_odds, "book": best.book,
            "under_odds": best.under_odds,
            "red_zone": rz_map.get(key),
            "snap_share": snap_map.get(key),
        })
    picks = [p.to_dict() for p in build_td_longshots(candidates)]
    # The most-likely list dedupes against the picks but is NOT a
    # top-up: MLB trims its watch to fill a three-row board, and that
    # exact semantics would hide the near-lock precisely on the weeks
    # the value board is full — the shape of the complaint that built
    # this. Football always shows its most likely scorers.
    have = {p.get("player") for p in picks}
    watch = [w for w in td_watchlist(candidates)
             if w.get("player") not in have]
    return picks, watch


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
    # Schedule fatigue, for the side the bet is actually about. A short week
    # or a body clock three hours out is a spread's business at least as
    # much as a prop's, so a game bet that journals NULL leaves the miner
    # half-blind on the market where rest is most often the story.
    #
    # ONLY WHEN THERE IS ONE SUBJECT. `team` is the side the bet is on for
    # moneylines, spreads and team totals, and is empty string for a GAME
    # total — which is about both teams and belongs to neither. Filling
    # that in with the home side's rest would put two different meanings in
    # one column, and a dimension that means different things in different
    # rows is worse than one that is absent: the miner would convict on a
    # pocket that does not exist.
    d["rest_days"] = d["body_clock"] = None
    subject = (d.get("team") or "").strip()
    if subject:
        try:
            from .fatigue import state_for as _fatigue_state
            _st = _fatigue_state(g, subject) or {}
            d["rest_days"] = _st.get("rest_days")
            d["body_clock"] = _st.get("body_clock")
        except Exception:                                     # noqa: BLE001
            pass
    # §6's coverage tell: how much ZONE the defence this player faces
    # plays, from participation data for games already played.
    #
    # A PROJECTION, and it has to be. Tonight's coverage is a fact about a
    # game that has not happened; what lands on the row is what that
    # defence HAS been doing, which is knowable when the bet is placed.
    # Journaling the actual would be journaling the future — the same
    # mistake `tto_proj` exists to avoid.
    #
    # NULL when unmeasured, and unmeasured is the normal case early: Week
    # 1 has no season-to-date behind it, and a season's file is only
    # published as the weeks are played. `coverage_band` returns None for
    # NULL rather than "balanced", so an unmeasured pick never pools with
    # a genuinely balanced defence.
    d["opp_zone_rate"] = _opp_zone_rate(g, d)
    return d


#: (season, opponent) → zone rate. A season's participation file is ~49 MB
#: and every prop on the slate asks the same question about the same dozen
#: defences, so the answer is computed once per opponent per build.
_ZONE_CACHE: dict = {}


def _season_of(g) -> int | None:
    """The nflverse SEASON a game belongs to, from its date.

    `Game` has no `season` field — it carries `date`, `week`, `home` and
    `away` — and the first cut of `_opp_zone_rate` read
    `getattr(g, "season", None)`. That returns None on every game ever
    built, so the whole coverage dimension was silently inert: journaled
    as NULL, banded as None, mined as nothing. Exactly the failure
    `engine/datause.py` exists to catch, and exactly the one it cannot —
    that auditor checks whether a symbol is MENTIONED, not whether it ever
    produces a value.

    A season runs September to February, so January and February belong to
    the PREVIOUS season's year, which is how nflverse keys its files. A
    naive `date[:4]` would ask for a 2027 participation file during the
    2026 playoffs and get a 404 that reads as "no data".
    """
    d = str(getattr(g, "date", "") or "")
    try:
        year, month = int(d[:4]), int(d[5:7])
    except (TypeError, ValueError):
        return None
    return year if month >= 3 else year - 1


def _opp_zone_rate(g, d):
    """The opposing defence's zone rate, or None when we cannot say.

    Degrades to None on every failure path on purpose. A missing feed, a
    season not yet published, a team code the file does not carry — all of
    them mean "not measured", and none of them should take down a board
    build over a dimension that prices nothing.
    """
    opp = (d.get("opponent") or "").strip().upper()
    season = _season_of(g)
    if not opp or not season:
        return None
    key = (season, opp)
    if key in _ZONE_CACHE:
        return _ZONE_CACHE[key]
    rate = None
    try:
        from .sources.nflpart import coverage_rates, load_participation
        rows = load_participation(int(season))
        c = coverage_rates(rows, opp)
        # The floor is not decoration. A defence with 40 labelled snaps
        # has played about a game and a half, and its zone rate is a
        # statement about two afternoons.
        if c["n_labelled"] >= 200:
            rate = c["zone_rate"]
    except Exception:                                         # noqa: BLE001
        rate = None
    _ZONE_CACHE[key] = rate
    return rate


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
              model=None, allow_synthetic_line: bool = False,
              nfl_usage: dict | None = None, team_context: dict | None = None,
              team_notes: dict | None = None) -> dict:
    """``allow_synthetic_line`` is for the backtest harness, which prices
    against a naive baseline line on purpose (see engine.betting.temper_edge).
    ``nfl_usage`` carries measured red-zone/snap/volume roles
    (engine.nflusage); the volume map feeds each prop's usage bridge.
    ``team_notes`` maps team → a one-line QB-dependency warning
    (engine.sources.depthcharts.qb_dependency), stamped on that team's
    pass-catcher props — a warning the human weighs, never a gate."""
    if not isinstance(slate, Slate):
        slate = load_slate(slate)
    config = config or RuleConfig()
    # Set before the prop rows are built: _log_wind needs the season, a game
    # log carries a week but not a year, and January belongs to last season.
    _SLATE_DATE["date"] = str(getattr(slate, "date", "") or "")

    from .fantasy import _short_key
    vol_map = (nfl_usage or {}).get("volume") or {}

    results = []
    for prop in slate.props:
        # Scorer props belong to the long-shot pipeline below. The yardage
        # path would run a normal distribution over touchdown counts and
        # publish the nonsense as a recommendation — Poisson-shaped
        # markets get the Poisson model (engine/touchdowns.py) or nothing.
        if prop.market == ANYTIME_TD:
            continue
        game = slate.game_for(prop)
        opponent = slate.team(prop.opponent)
        u = None
        if vol_map:
            u = (vol_map.get(_short_key(prop.player, prop.team)) or {}) \
                .get(prop.market)
        proj = build_projection(prop, game, opponent, model=model,
                                context=team_context, usage=u)
        rec = evaluate_prop(prop, proj, allow_synthetic_line=allow_synthetic_line,
                            game=game)
        decision = apply_rules(rec, prop, game, config)
        d = _rec_to_dict(rec, prop, decision, proj)
        if team_notes and prop.market in (PASS_YDS, REC_YDS, RECEPTIONS):
            note = team_notes.get(prop.team)
            if note:
                d["warnings"] = list(d["warnings"] or []) + [note]
        d["live"] = bool(game.live and game.live.state == "live")
        d["game_date"] = game.date
        d["game_kickoff"] = game.kickoff
        # The environment dimension, football flavor: wind is MAGNITUDE
        # here (no center field to blow out of — speed is what leans on
        # the passing and kicking game) plus the dome flag. Journaled so
        # the miner can slice "howling wind" pass-yards overs the same
        # way it slices baseball's wind-out homers; the sport key keeps
        # the two vocabularies from ever pooling.
        w = game.weather
        d["roofed"] = bool(w.dome)
        d["wind_out"] = None if w.dome else round(float(w.wind_mph or 0), 1)
        # The schedule-fatigue dimension: days of rest, and how far the
        # visitor's body clock is from kickoff.
        #
        # THESE WERE COMPUTED AND THROWN AWAY. `betting.py` already derives
        # both to feed the loss-pattern veto (it has done since the fatigue
        # work shipped) but never put them on the record, so
        # `ledger.log_recommendations`' `r.get("rest_days")` wrote NULL on
        # every pick ever journaled. The doctor reports it plainly —
        # "always-NULL: rest_days, body_clock" — which is two of nine
        # mineable dimensions permanently empty.
        #
        # That made the fatigue rung a closed loop with no input: the miner
        # could REFUSE a pick on a short-week pattern, but could never
        # CONVICT one, because no settled bet carried the dimension to
        # learn from. It was applying rules it had no way to discover.
        #
        # Derived here rather than passed down from `betting.py` so the
        # value lands on the record whatever the veto does with it — a
        # dimension that only gets journaled when a gate happens to fire is
        # a biased sample of exactly the thing being measured.
        try:
            from .fatigue import state_for as _fatigue_state
            _st = _fatigue_state(game, prop.team) or {}
            d["rest_days"] = _st.get("rest_days")
            d["body_clock"] = _st.get("body_clock")
        except Exception:                                     # noqa: BLE001
            # A fatigue hiccup must never cost the pick itself; the
            # dimension going missing is recoverable, a lost board is not.
            d["rest_days"] = d["body_clock"] = None
        results.append(d)

    # Rank: recommended bets first, then by confidence, then by edge.
    results.sort(key=lambda r: (r["recommended"], r["confidence"], r["edge"]), reverse=True)

    game_bets = _game_bets(slate.games, config)

    # §9/§10 — correlation flags, incoherent-pair rejection, exposure caps.
    # Runs AFTER ranking and BEFORE counts, so a rejected pick never counts
    # as recommended and capped stakes are what the page (and journal) see.
    from .correlation import flag_correlations, apply_exposure_caps
    corr = flag_correlations(results)
    corr["cap_notes"] = apply_exposure_caps(results, game_bets)

    recommended = [r for r in results if r["recommended"]]
    ls, ls_watch = _long_shots(slate, nfl_usage)
    out = {
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
        "games": [_game_to_dict(g, results) for g in slate.games],
        "recommendations": results,
        # Every ingested market for tonight's players, not just the one
        # each prop priced — the Players page's market chips
        # (engine/statlogs.py; empty on machines without the history DB).
        "player_stats": statlogs.for_board(results, "nfl"),
        "game_bets": game_bets,
        "long_shots": ls,
        "longshot_watch": ls_watch,
        "market_scan": _market_scan(results, ls),
        "correlation": corr,
    }
    # End-of-year incentive money: a hand-curated table of contract
    # thresholds, measured against our own ingested season logs. It ships
    # the tracker to the board and appends the angle to matching prop
    # cards — a reason the human weighs, never a probability. Its own
    # guard: a missing history DB (CI, fresh clone) costs the section,
    # never the slate.
    try:
        from . import incentives
        from .db import connect as _hist_connect
        _hc = _hist_connect()
        try:
            inc = incentives.report(_hc)
        finally:
            _hc.close()
        incentives.decorate(results, inc.get("entries") or [])
        out["incentives"] = inc
    except Exception:                              # noqa: BLE001
        out["incentives"] = {"entries": [], "note": ""}
    # The playoff picture — the incentive tracker's mirror. Clinched
    # teams rest, eliminated teams shut down, and an ANNOUNCED rest flips
    # matching props to Pass before the journal or the parlay screen can
    # touch them. Computed statuses only ever warn; the certainty rules
    # are tiebreaker-free by construction (engine/restwatch.py).
    try:
        from . import restwatch
        from .db import connect as _hist_connect2
        _hc2 = _hist_connect2()
        try:
            pic = restwatch.picture(_hc2)
        finally:
            _hc2.close()
        restwatch.decorate(results, pic)
        out["playoff_picture"] = pic
    except Exception:                              # noqa: BLE001
        out["playoff_picture"] = {"teams": {}, "active": False, "note": ""}
    # Schedule fatigue: short weeks, byes and the body clock. §7's open
    # item — the data was always in the schedule feed and nothing read
    # it. Evidence and a journaled dimension, never a price (see
    # engine/fatigue.py for why that order is deliberate).
    from . import fatigue as _fatigue
    out["fatigue"] = _fatigue.decorate(results, slate.games)
    # The outside view: what similar past spots actually did, counted off
    # the ingested logs with no distribution assumed. Evidence and a
    # divergence warning only — never a price input (see engine/comps.py).
    out["comps"] = _attach_comps(results, "nfl")
    # §14: the parlay screen runs last, over the board that just cleared the
    # singles gates — never over candidates it invented for itself.
    from .parlays import attach
    return attach(out, "nfl")


def _attach_comps(results: list[dict], sport: str) -> dict:
    """Decorate a board with historical comps. Own connection, own guard:
    a missing history DB (CI, a fresh clone) costs the section, never the
    slate — the same contract the incentive and rest blocks keep."""
    try:
        from . import comps
        from .db import connect as _hist_connect
        conn = _hist_connect()
        try:
            return comps.decorate(results, conn, sport)
        finally:
            conn.close()
    except Exception:                              # noqa: BLE001
        return {"matched": 0, "diverged": 0, "markets": []}


def _market_scan(results: list[dict], long_shots: list[dict] | None = None) -> dict:
    """Cross-book arbitrage / middle / low-hold / stale-line scan."""
    from .marketscan import scan_recommendations, stale_quotes, longshot_warnings
    out = scan_recommendations(results)
    out["stale"] = stale_quotes(results)
    # Avoidance rule, measured not assumed — see longshot_warnings. The
    # anytime-TD board feeds in alongside the main props: it is exactly
    # the plus-money population the rule was measured on.
    quotes = list(results)
    seen = set()          # a pick can also sit on the watchlist — one row each
    for r in long_shots or []:
        key = (r.get("player"), r.get("odds"))
        if key in seen:
            continue
        seen.add(key)
        quotes.append({**r, "market_label": r.get("market_label", "Anytime TD"),
                       "line": r.get("line", 0.5)})
    out["longshots"] = longshot_warnings(quotes)
    return out


def _conditions(g, results: list[dict] | None) -> dict:
    """Did this venue's conditions actually MOVE a number tonight?

    The redesign spec (§5.1) makes this the rule that separates a venue mark
    from clip-art: *"A venue mark never renders without encoding something.
    Amber stroke = that condition is material to tonight's plays. Never
    applied decoratively."* §5.3 says the flag is "computed upstream by the
    model — true when the condition actually moved the number for at least
    one play at that venue."

    So it is computed here, from the model, rather than guessed from a
    threshold. The prototype used `wind >= 8mph or altitude >= 3000ft or any
    roof`, which is a different claim: it says the condition is BIG, not that
    it did anything. A 10mph wind at a venue whose only priced market is
    rushing yards moves nothing, and the mark should be dim.

    The test is: some market with a priced prop at this game has a weather
    multiplier that is not 1.0. `evaluate_weather` already returns exactly
    those multipliers, so this reads the model's own answer instead of
    re-deriving one that could drift from it.
    """
    from .weather import evaluate_weather

    eff = evaluate_weather(g.weather)
    moved = {m for m, mult in eff.multipliers.items() if abs(mult - 1.0) > 1e-9}
    # Markets actually on the board for this game. A condition that only
    # touches markets nobody priced tonight did not move a number tonight.
    priced = {r.get("market") for r in (results or [])
              if r.get("team") in (g.home, g.away)
              or r.get("opponent") in (g.home, g.away)}
    hit = sorted(moved & priced) if priced else sorted(moved)
    # A roof is material on its own terms: the ABSENCE of weather is
    # information, and evaluate_weather returns early with flat multipliers
    # for a dome precisely because nothing else applies.
    roofed = bool(g.weather.dome) or (g.roof or "").lower() in ("dome", "closed")
    return {
        "material": bool(hit) or roofed,
        "markets_moved": hit,
        "roofed": roofed,
        # The model's own sentences, so the mark and the card cannot disagree.
        "why": list(eff.reasons),
    }


def _game_to_dict(g, results: list[dict] | None = None) -> dict:
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
        # Real book moneylines when an odds pull attached them (0 = not
        # offered) — the MLB payload has always shipped these, and the
        # Kalshi divergence read joins on them venue-vs-venue.
        "home_ml": g.home_ml, "away_ml": g.away_ml,
        # Venue reference for the game page. Unlike MLB parks this is
        # context, not an input — see engine/stadiums.py for why.
        "stadium": stadium_to_dict(g.home),
        "live": live_to_dict(g.live),
        "weather": {
            "dome": w.dome,
            "temp_f": w.temp_f,
            "wind_mph": w.wind_mph,
            "wind_dir": w.wind_dir,
            "rain": w.rain,
            "snow": w.snow,
        },
        # §5.1's encoding contract, computed rather than assumed.
        "conditions": _conditions(g, results),
    }
