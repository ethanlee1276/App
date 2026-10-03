#!/usr/bin/env python3
"""Build the NHL board: tonight's games → the hockey model → real prices.

    python3 nhl_build.py 2026-10-08 --odds --out web/data/nhl.json

Ethan, 2026-10-03: "We want every single feature we have for NFL and
college football and MLB for NHL as well. Then after that, start working on
the most likely bet model and the edge model for NHL."

Schedule from the NHL's own feed (engine/sources/nhldata); every skater
and goalie projected from our stored box scores (engine/nhl/model); prices
from The Odds API (icehockey_nhl — shots, points, assists, goals, blocked
shots, saves, the anytime goal scorer, and the ladders). The board speaks
the shared schema, so every shared page — Most Likely, Edge, the game
page, the record, the Live tab — reads it without a hockey branch:

  recommendations   every priced prop, our chance vs the de-vigged price
  game_bets         moneyline, puck line, total goals
  most_likely       likely.build over the props (rankfit opens each market)
  board_shelves     the one Most Likely board (engine/likelyboard)

A NEW LEAGUE IS ON PAPER (ledger.PAPER_SPORTS): every Edge pick is sized,
journaled and graded, and no dollar is staked until the record says so.
"""
from __future__ import annotations

import argparse
import datetime
import math
from pathlib import Path

from engine import gate
from engine.db import connect
from engine.nhl import model as M
from engine.sources.fetch import DataUnavailable

SPORT = "nhl"
#: A real Edge pick needs this much over the de-vigged price AFTER the
#: market haircut — the same bar the hoops boards started on.
EDGE_BAR = 0.03
#: A player is projected only if he dressed in one of his team's last this
#: many games — counted in the TEAM's games, not in days, so the summer
#: does not empty opening night (every last game is in April) while a man
#: out three weeks mid-season is still left off.
CURRENT_GAMES = 10


class _Game:
    def __init__(self, home, away, kickoff, home_name="", away_name=""):
        self.home, self.away, self.kickoff = home, away, kickoff
        self.home_name, self.away_name = home_name, away_name
        self.live = None
        self.spread = None
        self.home_ml = self.away_ml = 0
        self.total = None


class _Prop:
    def __init__(self, player, market, team=""):
        self.player, self.market, self.team = player, market, team
        self.lines = []


class _Slate:
    def __init__(self, games, props):
        self.games, self.props = games, props


# --- prices -----------------------------------------------------------------
def best_price(lines, one_sided_ok: bool = False):
    """(line, over_odds, under_odds, book) at the most-quoted number, best
    price each side among books a reader can bet. A one-sided quote (the
    anytime scorer often has no No) is allowed only where `one_sided_ok`."""
    from engine.odds import bettable_lines
    by: dict = {}
    for ln in lines or []:
        if ln.over_odds and (ln.under_odds or one_sided_ok):
            by.setdefault(float(ln.line), []).append(ln)
    if not by:
        return None
    line, quotes = max(by.items(), key=lambda kv: (len(kv[1]), -kv[0]))
    quotes = bettable_lines(quotes) or quotes
    over = max(quotes, key=lambda q: q.over_odds)
    unders = [q for q in quotes if q.under_odds]
    under = max(unders, key=lambda q: q.under_odds).under_odds if unders else None
    return line, int(over.over_odds), (int(under) if under else None), over.book


def _lines_dicts(lines) -> list[dict]:
    return [{"book": ln.book, "line": ln.line, "over_odds": ln.over_odds, "under_odds": ln.under_odds}
            for ln in lines or []]


def _p_over(proj: dict, market: str, line: float) -> float:
    if market in M.GOALIE_MARKETS:
        return M.goalie_prob(proj, line, "OVER")
    return M.skater_prob(proj, market, line, "OVER")


def rung_probs(proj: dict, market: str, alts) -> dict:
    """{"1.5": 0.71, ...}: our number at each rung of the ladder, shrunk
    toward that rung's own de-vigged price exactly as the main line is."""
    from engine.betting import temper_edge
    from engine.odds import devig_two_way
    out: dict = {}
    for ln in alts or []:
        key = f"{float(ln.line):g}"
        if key in out:
            continue
        raw = _p_over(proj, market, float(ln.line))
        if ln.over_odds and ln.under_odds:
            fair, _ = devig_two_way(int(ln.over_odds), int(ln.under_odds))
            raw = temper_edge(raw, fair, ln.book or "")[0]
        out[key] = round(raw, 4)
    return out


# --- one prop ---------------------------------------------------------------
def price_prop(prop, proj: dict, p: dict, opponent: str, assets: dict, date: str) -> dict | None:
    """The shared-schema recommendation for one priced prop, or None."""
    from engine.betting import _kelly_stake, temper_edge
    from engine.odds import devig_two_way, expected_value
    scorer = prop.market == "anytime_goal"
    got = best_price(prop.lines, one_sided_ok=scorer)
    if not got:
        return None
    line, over_odds, under_odds, book = got
    fair_over, fair_under = devig_two_way(over_odds, under_odds or 0)
    p_over = _p_over(proj, prop.market, line)
    sides = [("OVER", p_over, over_odds, fair_over)]
    if under_odds:
        sides.append(("UNDER", 1.0 - p_over, under_odds, fair_under))
    best = None
    for side, raw, odds, fair in sides:
        win, edge, credible = temper_edge(raw, fair, book or "")
        cand = (edge, side, raw, win, odds, fair, credible)
        if best is None or cand[0] > best[0]:
            best = cand
    edge, side, raw, win, odds, fair, credible = best
    ev = expected_value(win, odds)
    pick = bool(credible and edge >= EDGE_BAR and ev > 0)
    label = M.MARKET_LABELS.get(prop.market, prop.market)
    vals = [float(v) for v in proj.get("recent") or []]
    recent3 = sum(vals[:3]) / 3 if len(vals) >= 3 else None
    prior = (sum(vals[3:]) / len(vals[3:])) if len(vals) > 3 else None
    trend, delta = "flat", 0.0
    if recent3 is not None and prior:
        delta = round(recent3 - prior, 2)
        trend = "up" if delta / prior > 0.10 else "down" if delta / prior < -0.10 else "flat"
    sd = proj.get("sd") or math.sqrt(max(proj["mean"], 0.0) * proj.get("disp", 1.0))
    goalie = prop.market in M.GOALIE_MARKETS
    reasons = ([f"{proj['shots']:.1f} shots expected against × {proj['sv']:.3f} save rate → "
                f"{proj['mean']:.1f} saves"] if goalie else
               [f"{proj['toi']:.1f} min of ice time × {proj['rate60']:.2f} per 60 → "
                f"{proj['mean']:.2f} {label.lower()}"])
    if not goalie and abs(proj.get("opp", 1.0) - 1.0) >= 0.02:
        reasons.append(f"{opponent} allows {abs(proj['opp'] - 1):.0%} "
                       f"{'more' if proj['opp'] > 1 else 'less'} than an average team")
    if goalie:
        reasons.append("Probable starter — the goalie who started most of his team's recent games; "
                       "starters are not confirmed this early")
    games = p.get("games") or []
    warnings = [] if pick else ([] if credible else ["Our number disagrees with the market by more than we credit"])
    return {
        "player": prop.player, "team": prop.team, "opponent": opponent,
        "market": prop.market, "market_label": label,
        "position": p.get("position", ""), "usage_role": (f"{proj['toi']:.0f} min" if not goalie else "starter"),
        "headshot": (assets.get(prop.player) or {}).get("headshot", ""),
        "side": side, "book": book, "line": line, "odds": odds,
        "projection": round(proj["mean"], 2),
        "proj_low": round(max(0.0, proj["mean"] - sd), 1), "proj_high": round(proj["mean"] + sd, 1),
        "hit_prob": round(win, 4), "raw_prob": round(raw, 4), "fair_prob": round(fair, 4),
        "edge": round(edge, 4), "ev_per_unit": round(ev, 4),
        "confidence": (round(7.0 + min(max(edge, 0.0), 0.05) * 40, 1) if pick
                       else round(min(6.9, win * 10), 1)),
        "stake_units": round(_kelly_stake(win, odds), 2) if pick else 0.0,
        "grade": "Play" if pick else "Pass", "has_market": True,
        "recent_values": vals[:12], "trend": trend, "trend_delta": delta,
        "recommended": pick, "warnings": warnings,
        "headline": f"{prop.player} {side} {line:g} {label}",
        "summary": (f"Model {win:.0%} vs market {fair:.0%} after the market haircut — "
                    f"{edge:+.1%} at {odds:+d}."),
        "reasons": reasons,
        "all_lines": _lines_dicts(prop.lines),
        "alt_lines": _lines_dicts(getattr(prop, "alt_lines", None)),
        "alt_sharp_lines": _lines_dicts(getattr(prop, "alt_sharp_lines", None)),
        "rung_probs": rung_probs(proj, prop.market, getattr(prop, "alt_lines", None)),
        "logs": [{"week": i + 1, "date": g.get("date", ""), "opponent": g.get("opponent", ""),
                  "value": g.get("saves" if goalie else M._STAT.get(prop.market, prop.market), 0.0),
                  "home": g.get("home", 1)} for i, g in enumerate(games[:20])],
        "form": {"last1": vals[0] if vals else None,
                 "last3": recent3, "last5": (sum(vals[:5]) / 5 if len(vals) >= 5 else None),
                 "last10": (sum(vals[:10]) / 10 if len(vals) >= 10 else None),
                 "season": (sum(vals) / len(vals) if vals else None), "career": None, "vs_opponent": None},
        "game_date": date,
    }


# --- game lines ---------------------------------------------------------------
def game_bets(g, teams: dict) -> list[dict]:
    """Moneyline, puck line and total for one game with a real price."""
    from engine.gamebets import _game_bet, temper
    from engine.odds import devig_two_way
    lam = M.team_lambdas(teams, g.home, g.away)
    if not lam:
        return []
    probs = M.game_probs(*lam)
    out = []
    why = (f"Expected goals {g.home} {lam[0]:.2f} – {g.away} {lam[1]:.2f} (regulation), "
           f"from each side's recent goals for and against")
    if g.home_ml and g.away_ml:
        fh, fa = devig_two_way(int(g.home_ml), int(g.away_ml))
        best = None
        for team, raw, odds, fair, other in ((g.home, probs["home_ml"], g.home_ml, fh, g.away_ml),
                                             (g.away, probs["away_ml"], g.away_ml, fa, g.home_ml)):
            win, edge, cred = temper(raw, fair, SPORT, "moneyline")
            if best is None or edge > best[2]:
                best = (team, win, edge, cred, int(odds), fair, raw, int(other))
        team, win, edge, cred, odds, fair, raw, other = best
        card = _game_bet("moneyline", "Moneyline", g.home, g.away, win, fair, edge, odds,
                         pick_label=f"{team} ML", team=team, reasons=[why, "Overtime and the shootout included"],
                         headline=f"{team} Moneyline ({odds:+d})", credible=cred, other_odds=other, raw_win=raw)
        card.update(pick=team, pick_is_home=team == g.home, home_odds=int(g.home_ml), away_odds=int(g.away_ml))
        out.append(card)
    spread = getattr(g, "spread", None)
    sh, sa = getattr(g, "spread_home_odds", None), getattr(g, "spread_away_odds", None)
    if spread is not None and sh and sa and abs(abs(float(spread)) - 1.5) < 1e-9:
        fh, fa = devig_two_way(int(sh), int(sa))
        home_line = float(spread)
        p_home = probs["home_-1.5"] if home_line < 0 else probs["home_+1.5"]
        best = None
        for team, line, raw, odds, fair, other in ((g.home, home_line, p_home, sh, fh, sa),
                                                   (g.away, -home_line, 1.0 - p_home, sa, fa, sh)):
            win, edge, cred = temper(raw, fair, SPORT, "spread")
            if best is None or edge > best[3]:
                best = (team, line, win, edge, cred, int(odds), fair, raw, int(other))
        team, line, win, edge, cred, odds, fair, raw, other = best
        out.append(_game_bet("spread", "Puck line", g.home, g.away, win, fair, edge, odds,
                             pick_label=f"{team} {line:+g}", team=team, line=line,
                             reasons=[why, "The puck line is settled on the final score, overtime included"],
                             headline=f"{team} {line:+g}", credible=cred, other_odds=other, raw_win=raw))
    tot = getattr(g, "total", None)
    to, tu = getattr(g, "total_over_odds", None), getattr(g, "total_under_odds", None)
    if tot is not None and to and tu:
        fo, fu = devig_two_way(int(to), int(tu))
        p_over = M.total_over(probs, float(tot))
        best = None
        for side, raw, odds, fair, other in (("Over", p_over, to, fo, tu), ("Under", 1.0 - p_over, tu, fu, to)):
            win, edge, cred = temper(raw, fair, SPORT, "total")
            if best is None or edge > best[2]:
                best = (side, win, edge, cred, int(odds), fair, raw, int(other))
        side, win, edge, cred, odds, fair, raw, other = best
        exp = lam[0] + lam[1] + probs["tie"]
        out.append(_game_bet("total", "Total goals", g.home, g.away, win, fair, edge, odds,
                             pick_label=f"{side} {float(tot):g}", side=side, line=float(tot),
                             reasons=[f"Model expects {exp:.2f} goals (a shootout counts as one) vs the "
                                      f"{float(tot):g} total", why],
                             headline=f"{side} {float(tot):g} goals", credible=cred, other_odds=other,
                             raw_win=raw))
    for c in out:
        for attr in ("home_ml_book", "away_ml_book", "home_spread_book", "away_spread_book",
                     "total_over_book", "total_under_book"):
            if getattr(g, attr, None):
                c[attr] = getattr(g, attr)
    return out


# --- the slate ----------------------------------------------------------------
def current_players(players: dict, date: str) -> dict:
    """The players who dressed in one of their team's last CURRENT_GAMES
    games before ``date`` — see CURRENT_GAMES for why games, not days."""
    team_days: dict = {}
    for p in players.values():
        for g in p.get("games") or []:
            if g["date"] < date:
                team_days.setdefault(g.get("team") or p["team"], set()).add(g["date"])
    cutoff = {t: sorted(d, reverse=True)[:CURRENT_GAMES][-1] for t, d in team_days.items() if d}
    out = {}
    for name, p in players.items():
        last = next((g["date"] for g in p.get("games") or [] if g["date"] < date), None)
        if last and p["team"] in cutoff and last >= cutoff[p["team"]]:
            out[name] = p
    return out


def build_slate(games: list[dict], players: dict, date: str) -> _Slate:
    """Every current skater in every market, and each team's probable
    starter in saves — the props the odds pull can land on."""
    slate = _Slate([_Game(g["home"], g["away"], g.get("start", ""), g.get("home_name", ""),
                          g.get("away_name", "")) for g in games], [])
    teams = {t for g in games for t in (g["home"], g["away"])}
    live = current_players(players, date)
    for name, p in live.items():
        if p["team"] not in teams or p["position"] == "G":
            continue
        for market in M.SKATER_MARKETS:
            slate.props.append(_Prop(name, market, p["team"]))
    for team in sorted(teams):
        g = M.probable_starter(live, team)
        if g:
            slate.props.append(_Prop(g, "saves", team))
    return slate


def price_slate(slate: _Slate, games: list[dict], players: dict, league: dict, teams: dict,
                assets: dict, date: str) -> tuple[list[dict], dict]:
    """(recommendations, census) for every prop with a real price."""
    opp_of = {}
    for g in games:
        opp_of[g["home"]], opp_of[g["away"]] = g["away"], g["home"]
    census = {"no_real_price": 0, "no_history": 0}
    recs = []
    for prop in slate.props:
        if not prop.lines:
            census["no_real_price"] += 1
            continue
        p = players.get(prop.player)
        opp = opp_of.get(prop.team, "")
        if prop.market in M.GOALIE_MARKETS:
            proj = M.goalie_projection(p, league, teams, prop.team, opp) if p else None
        else:
            proj = M.skater_projection(p, prop.market, league, teams, opp) if p else None
        if proj is None:
            census["no_history"] += 1
            continue
        r = price_prop(prop, proj, p, opp, assets, date)
        if r is None:
            census["no_real_price"] += 1
            continue
        recs.append(r)
    recs.sort(key=lambda x: (x["recommended"], x["confidence"], x["edge"]), reverse=True)
    return recs, census


def _live_block(g: dict) -> dict | None:
    if g.get("final"):
        return {"state": "final", "home_score": g.get("home_score"), "away_score": g.get("away_score"),
                "detail": "final" + (f" ({g['ended_in']})" if g.get("ended_in") in ("OT", "SO") else "")}
    if g.get("live"):
        return {"state": "live", "home_score": g.get("live_home_score"), "away_score": g.get("live_away_score"),
                "detail": g.get("clock") or "in progress"}
    return None


def empty_board(date: str) -> dict:
    return {"generated_at": datetime.datetime.now().isoformat(timespec="seconds"), "date": date,
            "sport": SPORT, "generated_from": "live-nhl", "probation": True,
            "tuning": {"calibrated": False, "inherited_from": None,
                       "note": "A new league: every Edge pick is journaled on paper until its record earns money."},
            "recommendations": [], "game_bets": [], "long_shots": [], "longshot_watch": [],
            "most_likely": [], "board_shelves": [],
            "market_scan": {"stale": [], "arbs": [], "middles": [], "low_holds": [], "longshots": []},
            "counts": {"props_analyzed": 0, "recommended": 0}, "games": []}


def build(date: str, games: list[dict], conn, attach_odds=None) -> tuple[dict, _Slate | None]:
    """The board for one date. ``attach_odds(slate)`` lands the prices (the
    Odds API in production, fixture lines in the tests); None = no prices."""
    from engine.db import player_assets
    from engine.seasons import recent_seasons
    out = empty_board(date)
    out["games"] = [{"home": g["home"], "away": g["away"], "date": date, "kickoff": g.get("start", ""),
                     "live": _live_block(g)} for g in games]
    if not games:
        return out, None
    seasons = recent_seasons(SPORT, date)
    players = M.player_games(conn, seasons=seasons)
    teams = M.team_profiles(conn, seasons=seasons)
    league = M.league_rates(players)
    slate = build_slate(games, players, date)
    if not slate.props:
        out["history_gap"] = {"teams": sorted({t for g in games for t in (g["home"], g["away"])}),
                              "players_found": len(players), "seasons": seasons}
    odds_note = "no odds requested"
    if attach_odds is not None:
        odds_note = attach_odds(slate) or "odds attached"
    recs, census = price_slate(slate, games, players, league, teams, player_assets(conn, SPORT), date)
    bets = []
    for g in slate.games:
        bets.extend(game_bets(g, teams))
    by_pair = {(g.home, g.away): g for g in slate.games}
    for gd in out["games"]:
        g = by_pair.get((gd["home"], gd["away"]))
        if g is not None:
            gd.update(spread=g.spread, total=g.total, home_ml=g.home_ml or None, away_ml=g.away_ml or None)
    from engine.marketscan import scan_recommendations
    out.update(status="slate", recommendations=recs, game_bets=bets, gate_census=census,
               odds_note=odds_note, market_scan=scan_recommendations(recs))
    out["counts"] = {"props_built": len(slate.props), "props_analyzed": len(recs),
                     "recommended": sum(1 for r in recs if r["recommended"]),
                     "game_bets": sum(1 for b in bets if b.get("grade") != "Pass")}
    return out, slate


def attach_most_likely(out: dict, out_path: str, date: str) -> None:
    """likely.build over the props, then the one board — the same calls
    every other league makes, so the same bars apply."""
    from engine import boards as _boards, potd as _potd_keys
    from engine.likely import build as likely_build, previous_board
    census, kinds, turn = {}, {}, {}
    out[_potd_keys.POOL_KEY] = cut = []
    out["most_likely"] = likely_build(out.get("recommendations") or [], sport=SPORT, census=census,
                                      census_by_kind=kinds, cut=cut,
                                      previous=previous_board(out_path, date), turnover=turn)
    if not out["most_likely"]:
        from engine.rankfit import load as rank_store
        if not any(k.startswith(f"{SPORT}:") for k in rank_store()):
            census["no market measured to rank yet — run rankfit for nhl"] = 1
    out.update(likely_turnover=turn, likely_census=census, likely_census_by_kind=kinds,
               board_guide=_boards.guide(SPORT), board_shelves=_boards.shelves(SPORT, out["most_likely"]))
    from engine import likelyboard
    print(f"  {likelyboard.attach(out, SPORT)}")


def journal(out: dict, date: str) -> None:
    """Edge picks (on paper — ledger.PAPER_SPORTS), the Most Likely list,
    the one board and the Pick of the Day; then settle from history."""
    from engine import ledger, likelyboard
    lconn = ledger.connect()
    picks = [r for r in out.get("recommendations") or [] if r.get("recommended")]
    picks += [b for b in out.get("game_bets") or [] if b.get("grade") not in (None, "Pass")]
    n = ledger.log_recommendations(lconn, {"sport": SPORT, "date": date, "games": out.get("games"),
                                           "recommendations": picks}) if picks else 0
    ml = ledger.log_most_likely(lconn, {"sport": SPORT, "date": date, "games": out.get("games"),
                                        "most_likely": out.get("most_likely") or []})
    lb = likelyboard.journal(lconn, out, SPORT, date)
    potd = ledger.log_pick_of_the_day(lconn, out.get("pick_of_the_day") or {})
    settled = ledger.settle_and_export(lconn, connect(), sport=SPORT, logged=n)
    print(f"Journal: {n} NHL Edge pick(s) on paper, {ml} Most Likely, {lb} board row(s)"
          f"{', Pick of the Day' if potd else ''}; {settled} settled.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the NHL board.")
    ap.add_argument("date", nargs="?", default=datetime.date.today().isoformat(),
                    help="slate date, YYYY-MM-DD (default today)")
    ap.add_argument("--odds", action="store_true", help="buy fresh odds for this slate (spends API credits)")
    ap.add_argument("--cached-odds", action="store_true", help="use the odds already on disk — no purchase")
    ap.add_argument("--out", default="web/data/nhl.json", help="where the public board is written")
    ap.add_argument("--no-journal", action="store_true", help="build and publish without journaling")
    args = ap.parse_args()

    from engine.sources import nhldata
    try:
        games = nhldata.schedule_day(args.date)
    except DataUnavailable as exc:
        out = empty_board(args.date)
        out.update(status="unreachable", note=str(exc))
        gate.publish(out, Path(args.out))
        print(f"NHL {args.date}: schedule unreachable — {exc}")
        return
    pre = [g for g in games if g.get("type") == 1]
    games = [g for g in games if g.get("type") in nhldata.KEEP_TYPES]

    attach = None
    if args.odds or args.cached_odds:
        def attach(slate):
            from engine.sources import oddsapi
            try:
                res = oddsapi.apply_odds_to_slate(slate, sport=SPORT,
                                                  cache_only=args.cached_odds and not args.odds)
            except oddsapi.OddsAPIError as exc:
                return f"odds unavailable: {exc}"
            note = (f"matched {res.matched} props + {res.scorers_matched} scorer quotes across "
                    f"{res.events_used} events" + (" (cached)" if res.from_cache else ""))
            if res.dropped_events:
                note += f"; {len(res.dropped_events)} event(s) could not be placed"
                for d in res.dropped_events:
                    print(f"    dropped {d['away']} @ {d['home']} — {d['reason']}")
            return note

    conn = connect()
    out, slate = build(args.date, games, conn, attach_odds=attach)
    if not games:
        out.update(status="no games today",
                   note=("Preseason games only — no picks until the regular season."
                         if pre else "No NHL games on this date."))
    if out.get("history_gap"):
        print("⚠️  NHL games on the schedule and no players with stored games for tonight's teams.\n"
              "    Fix: python3 ingest.py nhl --seasons 2023-2025")
    if games:
        try:
            attach_most_likely(out, args.out, args.date)
        except Exception as exc:                            # noqa: BLE001
            print(f"⚠️  Most Likely skipped: {exc}")
    # The shared after-hooks, as every other build runs them; each one is
    # its own try so one failing never costs the board.
    for label, fn in (
            ("open-bet tracker", lambda: __import__("engine.livepicks", fromlist=["x"]).attach_tracker(out, SPORT)),
            ("exchange fair", lambda: __import__("engine.exchangefair", fromlist=["x"]).attach_to_board(out, SPORT)),
            ("crowd prices", lambda: __import__("engine.crowd", fromlist=["x"]).attach_to_board(out, SPORT)),
            ("opening lines", lambda: __import__("engine.lineopen", fromlist=["x"]).attach_to_board(out, SPORT)),
            ("pick of the day", lambda: __import__("engine.potd", fromlist=["x"]).attach(out, SPORT))):
        try:
            msg = fn()
            if msg:
                print(f"  {label}: {msg}")
        except Exception as exc:                            # noqa: BLE001
            print(f"⚠️  {label} skipped: {exc}")
    if games and not args.no_journal:
        try:
            journal(out, args.date)
        except Exception as exc:                            # noqa: BLE001
            print(f"⚠️  NHL journal skipped: {exc}")
    try:
        from engine import ledger
        out["pick_of_the_day"] = ledger.relock_potd(out.get("pick_of_the_day") or {}, out.get("most_likely") or [])
    except Exception as exc:                                # noqa: BLE001
        print(f"⚠️  Pick of the Day relock skipped: {exc}")
    try:
        from engine import freshness
        freshness.stamp_board(out, SPORT)
    except Exception as exc:                                # noqa: BLE001
        print(f"⚠️  freshness stamp skipped: {exc}")
    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    gate.publish(out, p)
    try:
        from engine import lightboard
        _, full = gate.publish(lightboard.light(out, SPORT), lightboard.light_path(p))
        print(lightboard.report(gate.board_source(p), full))
    except Exception as exc:                                # noqa: BLE001
        print(f"⚠️  Light board skipped: {exc}")
    c = out["counts"]
    # THE ODDS LINE, ALWAYS. A board with no prices looks the same whether
    # no book had posted yet or the pull never happened (a hand run without
    # /etc/qellys/env has no key) — the first hand build on the box said
    # "0 priced props" and nothing about why.
    if games:
        print(f"  Odds: {out.get('odds_note') or 'none'} · {c.get('props_built', 0)} props built from history")
    print(f"NHL {args.date}: {len(games)} game(s), {c.get('props_analyzed', 0)} priced props → "
          f"{c.get('recommended', 0)} Edge pick(s), {c.get('game_bets', 0)} game bet(s), "
          f"{len(out.get('most_likely') or [])} Most Likely. Wrote {args.out}")


if __name__ == "__main__":
    main()
