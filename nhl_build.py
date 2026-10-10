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
#: The least edge any NHL market accepts (a moneyline's minimum). Each
#: market's own, higher bar is Edge Hunter's (edgehunter.MARKET_MIN_EDGE),
#: and Edge Hunter decides every Edge play since 2026-10-03.
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
def price_prop(prop, proj: dict, p: dict, opponent: str, assets: dict, date: str,
               ctx: dict | None = None, teams: dict | None = None, league: dict | None = None) -> dict | None:
    """The shared-schema recommendation for one priced prop, or None.

    WHETHER IT IS AN EDGE PLAY is Scalpy NHL — Edge Hunter 1.0's call
    (engine/nhl/edgehunter.py): the per-market edge minimum, positive EV,
    and the false-edge filter. Its verdict rides on the row as
    ``edge_hunter``; Win-First's grade rides beside it, never blended."""
    from engine.nhl import edgehunter as EH
    from engine.betting import temper_edge
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
    games = p.get("games") or []
    me, them = (ctx or {}).get(prop.team) or {}, (ctx or {}).get(opponent) or {}
    flags, passes = [], []
    # THE SCALPY READ, in its output order: goalie impact, ice time, game
    # script, then the risk factors.
    if goalie:
        src = me.get("starter_source") or "recent starts"
        if src == "recent starts":
            reasons.append(f"Probable starter: {me.get('starter_share', 0):.0%} of {prop.team}'s last "
                           f"{M.STARTER_WINDOW} starts — not confirmed yet")
        else:
            reasons.append(f"Starter {'confirmed' if src == 'confirmed' else 'named probable'} by {prop.team} (ESPN)")
    elif them.get("starter"):
        sv = them.get("sv")
        if them.get("starter_sure") and sv is not None:
            gsax = them.get("gsax")
            reasons.append(f"Goalie impact: faces {them['starter']} (.{round(sv * 1000):03d} save rate, "
                           f"regressed over his recent seasons"
                           + (f"; {gsax:+.1f} goals saved above expected lately" if gsax is not None else "")
                           + ")")
        else:
            flags.append("opposing starter unsure")
            reasons.append(f"Goalie impact: {opponent}'s starter is not settled — read from the team's "
                           f"goals allowed instead")
    if not goalie:
        swing = proj.get("toi_swing") or 0.0
        dressed = sum(1 for g in games if g.get("date") in (me.get("last10") or ()))
        reasons.append(f"Ice time: {proj['toi']:.1f} min a game"
                       + (" — steady" if swing < 0.10 else f" — moved {swing:.0%} lately"))
        if me.get("last10") and dressed < M.ROLE_MIN_GAMES:
            passes.append(f"dressed in only {dressed} of {prop.team}'s last 10 games")
        elif swing > M.ROLE_SWING:
            passes.append(f"ice time moved {swing:.0%} over his last 5 games")
        if proj.get("sh") is not None:
            toward = (f"what his shots were worth ({proj['xsh']:.1%})" if proj.get("xsh") is not None
                      else "the league rate")
            reasons.append(f"Finishing regressed: {proj['sh']:.1%} shooting, pulled toward {toward} "
                           f"— volume over finishing")
        pr = proj.get("pp_row")
        if pr and pr.get("unit"):
            ratio = M.opp_pp_ratio(teams or {}, opponent)
            reasons.append(f"Power play: unit {pr['unit']} — {pr['pp_points']} power-play point(s) in "
                           f"{prop.team}'s last {pr.get('team_games') or 20} games"
                           + (f"; {opponent} concedes {abs(ratio - 1):.0%} "
                              f"{'more' if ratio > 1 else 'fewer'} power-play chances than average"
                              if ratio is not None and abs(ratio - 1) >= 0.05 else ""))
        xp = proj.get("xg_player")
        if xp and xp.get("iff"):
            luck = xp["goals"] - xp["ixg"]
            reasons.append(f"Shot quality: {xp['ixg']:.1f} expected goals on {xp['iff']} unblocked attempts "
                           f"over his last {xp['games']} games, {xp['goals']} scored"
                           + (f" — running {'hot' if luck > 0 else 'cold'} by {abs(luck):.1f}"
                              if abs(luck) >= M.LUCK_GOALS else ""))
    if me.get("xg") is not None and them.get("xg") is not None:
        reasons.append(f"Game script: {prop.team} {me['xg']:.2f} – {opponent} {them['xg']:.2f} expected "
                       f"regulation goals")
        if goalie and them["xg"] - me["xg"] >= 1.0:
            passes.append("blowout risk — a lopsided game can pull the goalie or change the script")
    if me.get("b2b"):
        flags.append("second night of a back-to-back")
    if them.get("b2b"):
        reasons.append(f"{opponent} is on the second night of a back-to-back")
    if flags or passes:
        reasons.append("Risk factors: " + "; ".join(flags + passes))
    eh = EH.assess_prop(prop.market, side, line, win, fair, edge, odds, book, credible, proj, p,
                        prop.team, opponent, ctx=ctx, teams=teams, league=league,
                        quotes=_lines_dicts(prop.lines), scalpy_pass="; ".join(passes))
    pick = eh["play"]
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
        "stake_units": eh["stake_units"] if pick else 0.0,
        "grade": "Play" if pick else "Pass", "has_market": True,
        "recent_values": vals[:12], "trend": trend, "trend_delta": delta,
        "recommended": pick, "warnings": warnings,
        "headline": f"{prop.player} {side} {line:g} {label}",
        "summary": (f"Model {win:.0%} vs market {fair:.0%} after the market haircut — "
                    f"{edge:+.1%} at {odds:+d}, fair {EH.fair_odds(win) or 0:+d}. "
                    f"Edge Hunter: {eh['classification']} (score {eh['edge_score']})."),
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
        # SCALPY NHL 1.0 — the win-first grade, the prop's tier, the risk
        # flags that keep it out of A+, and the reason a prop is passed.
        "scalpy_grade": M.scalpy_grade(win, flags + passes) if not passes else "Pass",
        "prop_tier": M.PROP_TIER.get(prop.market),
        "scalpy_flags": flags,
        "scalpy_pass": "; ".join(passes),
        # SCALPY NHL — EDGE HUNTER 1.0: the Edge board's verdict.
        "edge_hunter": eh,
    }


# --- game lines ---------------------------------------------------------------
def game_bets(g, teams: dict, ctx: dict | None = None, league: dict | None = None) -> list[dict]:
    """Moneyline, puck line and total for one game with a real price.

    SCALPY's game order: the starting goalies first — each side's expected
    goals moves by how tonight's confirmed-probable starter compares with
    the team's goaltending as a whole (a backup in net is more goals) —
    then rest (the back-to-back factor in the team lambdas)."""
    from engine.gamebets import _game_bet, temper
    from engine.odds import devig_two_way
    ctx = ctx or {}
    hc, ac = ctx.get(g.home) or {}, ctx.get(g.away) or {}
    if hc.get("xg") is not None and ac.get("xg") is not None:
        lam = [hc["xg"], ac["xg"]]
    else:
        lam = M.team_lambdas(teams, g.home, g.away)
        if not lam:
            return []
        lam = list(lam)
    goalie_note = []
    for i, side in ((1, hc), (0, ac)):          # the home goalie faces the away goals, and back
        if side.get("starter_sure") and side.get("gskill") and side.get("team_gskill"):
            f = side["gskill"] / side["team_gskill"]          # against chances, when the xG model has them
        elif side.get("starter_sure") and side.get("sv") is not None and side.get("team_sv") is not None:
            f = (1 - side["sv"]) / max(1 - side["team_sv"], 1e-6)
        else:
            f = None
        if f is not None:
            f = max(1 - M.GOALIE_CAP, min(1 + M.GOALIE_CAP, f))
            lam[i] *= f
            if abs(f - 1) >= 0.03:
                goalie_note.append(f"{side['starter']} in net moves the other side's goals {f - 1:+.0%}")
    lam = tuple(lam)
    probs = M.game_probs(*lam)
    out = []
    why = (f"Expected goals {g.home} {lam[0]:.2f} – {g.away} {lam[1]:.2f} (regulation), "
           f"from each side's goals"
           + (" and expected goals" if (teams.get(g.home) or {}).get("xgf") is not None else "")
           + " for and against" + ("; " + "; ".join(goalie_note) if goalie_note else ""))
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
    from engine.nhl import edgehunter as EH
    for c in out:
        for attr in ("home_ml_book", "away_ml_book", "home_spread_book", "away_spread_book",
                     "total_over_book", "total_under_book"):
            if getattr(g, attr, None):
                c[attr] = getattr(g, attr)
        # EDGE HUNTER decides whether a game line is an Edge play, and its
        # quarter-Kelly stake by tier.
        eh = EH.assess_game(c, g.home, g.away, ctx, teams, league)
        side = ("home" if c.get("team") == g.home else "away") if c["bet_type"] != "total" else \
            ("over" if str(c.get("side")).lower() == "over" else "under")
        kind = {"moneyline": "ml", "spread": "spread", "total": "total"}[c["bet_type"]]
        eh["best_book"] = c.get(f"{side}_{kind}_book") or c.get(f"total_{side}_book") or ""
        c["edge_hunter"] = eh
        if not eh["play"]:
            c["grade"], c["stake_units"] = "Pass", 0.0
        else:
            c["stake_units"] = eh["stake_units"]
    return out


# --- the slate ----------------------------------------------------------------
def current_players(players: dict, date: str, rosters: dict | None = None) -> dict:
    """The players who dressed in one of their team's last CURRENT_GAMES
    games before ``date`` — see CURRENT_GAMES for why games, not days.

    ``rosters`` ({player: team}, the nightly roster pull) puts a traded
    player on his NEW team before he has played for it, and leaves off a
    player no current roster carries (sent down, released, retired) — but
    only for a club whose roster was actually read, so a failed pull costs
    nothing."""
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
    if rosters:
        listed = set(rosters.values())
        for name in list(out):
            team = rosters.get(name)
            if team and team != out[name]["team"]:
                out[name] = {**out[name], "team": team, "traded_from": out[name]["team"]}
            elif not team and out[name]["team"] in listed:
                del out[name]
    return out


def build_slate(games: list[dict], players: dict, date: str, rosters: dict | None = None) -> _Slate:
    """Every current skater in every market, and each team's probable
    starter in saves — the props the odds pull can land on."""
    slate = _Slate([_Game(g["home"], g["away"], g.get("start", ""), g.get("home_name", ""),
                          g.get("away_name", "")) for g in games], [])
    teams = {t for g in games for t in (g["home"], g["away"])}
    live = current_players(players, date, rosters)
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


def scalpy_context(games: list[dict], players: dict, league: dict, teams: dict, date: str,
                   xs: dict | None = None, starters: dict | None = None) -> dict:
    """SCALPY NHL 1.0's per-team read, in its order of importance: the
    starting goalie first (who, how sure, how good), then rest, then the
    expected game. {team: {...}}.

    ``xs`` is engine.nhl.xg.board_summaries: with it each starter also
    carries goals saved above expected ("gsax") and his skill against
    chances ("gskill", goals allowed ÷ expected, regressed), beside the
    team's pooled goaltending ("team_gskill").

    ``starters`` is engine.sources.nhlstarters.tonight — the goalie each
    team has announced, as ESPN carries it. A named goalie we know on that
    team replaces the ten-game guess: "confirmed" settles him outright, a
    plain probable unless he started last night. ``starter_source`` says
    which ("confirmed", "probable", or "recent starts")."""
    from engine.nhl import xg as X
    from engine.sources.oddsapi import normalize_name
    goalies_by_key = {(normalize_name(n), p["team"]): n for n, p in players.items() if p["position"] == "G"}
    import datetime as _dt
    try:
        yday = (_dt.date.fromisoformat(date) - _dt.timedelta(days=1)).isoformat()
    except ValueError:
        yday = ""
    played_yday: set = set()
    started_yday: set = set()
    team_days: dict = {}
    for name, p in players.items():
        for g in p.get("games") or []:
            if g["date"] < date:
                team_days.setdefault(p["team"], set()).add(g["date"])
            if g["date"] == yday:
                played_yday.add(p["team"])
                if p["position"] == "G" and g.get("started"):
                    started_yday.add(name)
    ctx: dict = {}
    for g in games:
        for team, opp, home in ((g["home"], g["away"], True), (g["away"], g["home"], False)):
            starter = M.probable_starter(players, team)
            b2b = team in played_yday
            named = (starters or {}).get(team) or {}
            known = goalies_by_key.get((normalize_name(named.get("name") or ""), team))
            if known:
                starter, source = known, named.get("status") or "probable"
            else:
                source = "recent starts"
            share = M.starter_share(players, team, starter) if starter else 0.0
            # THE BACK-TO-BACK GOALIE RULE: the man who started last night
            # rarely starts tonight, so "probable" is not probable at all —
            # unless his team has confirmed him.
            if source == "confirmed":
                sure = True
            elif source == "probable":
                sure = not (b2b and starter in started_yday)
            else:
                sure = bool(starter) and share >= M.STARTER_SHARE and not (b2b and starter in started_yday)
            ctx[team] = {"opponent": opp, "home": home, "starter": starter, "starter_share": round(share, 2),
                         "starter_sure": sure, "starter_source": source, "b2b": b2b,
                         "sv": M.regressed_sv(players.get(starter), league) if starter else None,
                         "raw_sv": M.raw_sv(players.get(starter)) if starter else None,
                         "team_sv": M.team_sv(players, team, league),
                         "last10": set(sorted(team_days.get(team, ()), reverse=True)[:10])}
            gk = ((xs or {}).get("goalies") or {})
            if starter and starter in gk:
                ctx[team].update(gsax=gk[starter]["gsax"], gskill=M.goalie_skill(gk[starter]),
                                 team_gskill=M.goalie_skill(X.team_goalie_pool(gk, players, team)))
    for g in games:
        lam = M.team_lambdas(teams, g["home"], g["away"],
                             rested={t: not ctx[t]["b2b"] for t in (g["home"], g["away"])})
        if lam:
            ctx[g["home"]]["xg"], ctx[g["away"]]["xg"] = lam[0], lam[1]
    return ctx


def price_slate(slate: _Slate, games: list[dict], players: dict, league: dict, teams: dict,
                assets: dict, date: str, ctx: dict | None = None, xs: dict | None = None) -> tuple[list[dict], dict]:
    """(recommendations, census) for every prop with a real price. ``xs``
    = engine.nhl.xg.board_summaries (shot quality), None without it."""
    ctx = ctx if ctx is not None else scalpy_context(games, players, league, teams, date, xs=xs)
    xplayers = (xs or {}).get("players") or {}
    pp_teams = (xs or {}).get("pp") or {}
    opp_of = {}
    for g in games:
        opp_of[g["home"]], opp_of[g["away"]] = g["away"], g["home"]
    census = {"no_real_price": 0, "no_history": 0, "starter_unconfirmed": 0}
    recs = []
    for prop in slate.props:
        if not prop.lines:
            census["no_real_price"] += 1
            continue
        p = players.get(prop.player)
        opp = opp_of.get(prop.team, "")
        me, them = ctx.get(prop.team) or {}, ctx.get(opp) or {}
        if prop.market in M.GOALIE_MARKETS:
            # "Unknown starting goalie — no goalie-dependent bet."
            if not me.get("starter_sure") or me.get("starter") != prop.player:
                census["starter_unconfirmed"] += 1
                continue
            proj = M.goalie_projection(p, league, teams, prop.team, opp) if p else None
        else:
            sure = them.get("starter_sure")
            opp_sv = them.get("sv") if sure else None
            pp = ((pp_teams.get(prop.team) or {}).get("players") or {}).get(prop.player)
            proj = M.skater_projection(p, prop.market, league, teams, opp, opp_sv=opp_sv,
                                       xp=xplayers.get(prop.player),
                                       opp_skill=them.get("gskill") if sure else None, pp=pp) if p else None
            if proj is not None and prop.player in xplayers:
                proj["xg_player"] = xplayers[prop.player]
            if proj is not None and pp:
                proj["pp_row"] = dict(pp, team_games=(pp_teams.get(prop.team) or {}).get("games"))
        if proj is None:
            census["no_history"] += 1
            continue
        r = price_prop(prop, proj, p, opp, assets, date, ctx=ctx, teams=teams, league=league)
        if r is None:
            census["no_real_price"] += 1
            continue
        recs.append(r)
    recs.sort(key=lambda x: (x["recommended"], (x.get("edge_hunter") or {}).get("edge_score", 0),
                             x["edge"]), reverse=True)
    return recs, census


def _live_block(g: dict) -> dict | None:
    if g.get("final"):
        return {"state": "final", "home_score": g.get("home_score"), "away_score": g.get("away_score"),
                "detail": "final" + (f" ({g['ended_in']})" if g.get("ended_in") in ("OT", "SO") else "")}
    if g.get("live"):
        return {"state": "live", "home_score": g.get("live_home_score"), "away_score": g.get("live_away_score"),
                "detail": g.get("clock") or "in progress"}
    return None


#: ESPN statuses that mean he is not playing tonight; anything else listed
#: (day-to-day) holds his picks until the lineup says otherwise.
OUT_STATUSES = ("out", "injured reserve", "ir", "long term injured reserve", "ltir", "suspended",
                "injured reserve-long term")


def nhl_injuries(fetch=None) -> dict:
    """{player: {"status", "team", "injury"}} from ESPN's NHL board, the
    newest filing per player and no cleared-to-play notices; {} when the
    feed cannot be read (a gap on our side, never a claim of health)."""
    from engine.sources import espninjuries as E
    from engine.sources.oddsapi import NHL_TEAM_ABBR
    try:
        rows = E.parse_injuries((fetch or (lambda: E.fetch_injuries("nhl")))())
    except Exception:                                    # noqa: BLE001
        return {}
    rows = E.drop_stale_returns(E.current_rows(rows))
    out = {}
    for r in rows:
        if E.is_return(r):
            continue
        out[r["player"]] = {"status": r.get("status") or "", "injury": r.get("injury") or "",
                            "team": NHL_TEAM_ABBR.get(r.get("team") or "", r.get("team") or "")}
    return out


def empty_board(date: str) -> dict:
    return {"generated_at": datetime.datetime.now().isoformat(timespec="seconds"), "date": date,
            "sport": SPORT, "generated_from": "live-nhl", "probation": True,
            "tuning": {"calibrated": False, "inherited_from": None,
                       "note": "A new league: every Edge pick is journaled on paper until its record earns money."},
            "recommendations": [], "game_bets": [], "long_shots": [], "longshot_watch": [],
            "most_likely": [], "board_shelves": [],
            "market_scan": {"stale": [], "arbs": [], "middles": [], "low_holds": [], "longshots": []},
            "counts": {"props_analyzed": 0, "recommended": 0}, "games": []}


#: Newest games read per team for its lines, and where they are kept for
#: the team pages (public: who plays with whom is a fact, not a pick).
LINES_GAMES = 2
LINES_FILE = Path("web/data/nhl_lines.json")


def team_lines(conn, teams, players: dict, fetch=None) -> dict:
    """{team: engine.nhl.lines.build(...)} from each team's LINES_GAMES
    newest finals' shift charts (the league's stats host, keyless, cached a
    month per game). A team whose charts will not load is left out — the
    board reads as it did without lines."""
    import json as _json
    from engine.nhl import lines as LN
    from engine.sources import nhlshifts
    from engine.sources.fetch import DataUnavailable as _DU
    fetch = fetch or nhlshifts.fetch_shifts
    positions = {n: p.get("position") or "" for n, p in players.items()}
    out = {}
    for team in sorted(teams):
        rows = conn.execute(
            "SELECT extra FROM games WHERE sport='nhl' AND home_score IS NOT NULL AND (home=? OR away=?) "
            "ORDER BY date DESC, period DESC LIMIT ?", (team, team, LINES_GAMES)).fetchall()
        charts = []
        for (extra,) in rows:
            try:
                gid = int((_json.loads(extra or "{}")).get("nhl_id") or 0)
            except (ValueError, TypeError):
                gid = 0
            if not gid:
                continue
            try:
                got = nhlshifts.parse_shifts(fetch(gid)).get(team)
            except _DU:
                got = None
            if got:
                charts.append(got)
        if charts:
            out[team] = LN.build(charts, positions)
    return out


def save_lines(lines: dict, path: Path = LINES_FILE, date: str = "") -> None:
    """Merge tonight's teams into the kept file, so every club the board
    has seen keeps its newest lines for its team page."""
    import json as _json
    import os as _os
    try:
        kept = _json.loads(path.read_text())
    except (OSError, ValueError):
        kept = {}
    teams = kept.get("teams") or {}
    for t, v in lines.items():
        teams[t] = dict(v, as_of=date)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(_json.dumps({"teams": teams}))
    _os.replace(tmp, path)


def build(date: str, games: list[dict], conn, attach_odds=None, injuries: dict | None = None,
          starters: dict | None = None, lines: dict | None = None) -> tuple[dict, _Slate | None]:
    """The board for one date. ``attach_odds(slate)`` lands the prices (the
    Odds API in production, fixture lines in the tests); None = no prices.
    ``starters`` = announced goalies (engine/sources/nhlstarters); None
    reads ESPN, {} uses the ten-game guess alone. ``lines`` = {team:
    engine.nhl.lines result}; None reads the shift charts, {} none."""
    from engine.db import player_assets
    from engine.seasons import recent_seasons
    out = empty_board(date)
    out["games"] = [{"home": g["home"], "away": g["away"], "date": date, "kickoff": g.get("start", ""),
                     "live": _live_block(g)} for g in games]
    if not games:
        return out, None
    seasons = recent_seasons(SPORT, date)
    players = M.player_games(conn, seasons=seasons)
    # THE INJURY REPORT FIRST (ESPN's NHL board): a man ruled out has no
    # prop, no read and cannot be the probable starter; a day-to-day man
    # keeps his number and his picks are held (likely.admissible).
    injuries = nhl_injuries() if injuries is None else injuries
    ruled_out = {n for n, i in injuries.items() if str(i.get("status") or "").strip().lower() in OUT_STATUSES}
    players = {n: p for n, p in players.items() if n not in ruled_out}
    teams = M.team_profiles(conn, seasons=seasons)
    league = M.league_rates(players)
    from engine.sources import nhldata
    rosters = nhldata.load_rosters()
    slate = build_slate(games, players, date, rosters)
    if not slate.props:
        out["history_gap"] = {"teams": sorted({t for g in games for t in (g["home"], g["away"])}),
                              "players_found": len(players), "seasons": seasons}
    odds_note = "no odds requested"
    if attach_odds is not None:
        odds_note = attach_odds(slate) or "odds attached"
    # SHOT QUALITY (engine/nhl/xg.py): our expected goals from the stored
    # play-by-play — None until `ingest.py nhl --shots` has run and a model
    # is fitted, and then every number below reads as it did without it.
    from engine.nhl import xg as X
    xs = X.board_summaries(conn, seasons=seasons, window=M.RECENT_GAMES)
    M.attach_xg(teams, (xs or {}).get("teams"))
    out["shot_quality"] = bool(xs)
    if starters is None:
        from engine.sources import nhlstarters
        starters = nhlstarters.tonight(date)
    out["starters_announced"] = len(starters)
    ctx = scalpy_context(games, players, league, teams, date, xs=xs, starters=starters)
    assets = player_assets(conn, SPORT)
    recs, census = price_slate(slate, games, players, league, teams, assets, date, ctx=ctx, xs=xs)
    # LINE COMBINATIONS (engine/nhl/lines): who each skater plays with, off
    # the shift charts of his team's newest games. A row says it, and a
    # ticket of two linemates reads their shared ice (engine/parlays).
    from engine.nhl import lines as LN
    if lines is None:
        try:
            lines = team_lines(conn, {t for g in games for t in (g["home"], g["away"])}, players)
        except Exception as exc:                            # noqa: BLE001
            print(f"⚠️  lines skipped: {exc}")
            lines = {}
    out["lines"] = lines
    for r in recs:
        slot = LN.slot_of(lines.get(r["team"]) or {}, r["player"])
        if slot:
            r["line"] = slot
            r["line_unit"] = f"{r['team']}-{slot['unit']}"
            r.setdefault("reasons", []).append(
                f"Line: {slot['unit']} with {' and '.join(slot['mates'])} "
                f"({slot['together']:.0%} of their ice together lately)")
    for r in recs:
        inj = injuries.get(r["player"])
        if inj and r["player"] not in ruled_out:
            r["injury_status"] = inj["status"]
            r.setdefault("warnings", []).append(f"Listed {inj['status']} — held until the lineup confirms")
            _edge_pass(r, f"listed {inj['status']} — lineup uncertain")
    # EVERY BOOK TOOK HIM DOWN (engine/pricedplayers, the NFL's Zay Flowers
    # rule): priced in an earlier pull, on no book now, before puck drop.
    from engine.sources.oddsapi import normalize_name
    pulled = {normalize_name(n) for g in slate.games for n in (getattr(g, "pulled_players", None) or [])}
    pulled_names = {n for n in players if normalize_name(n) in pulled}
    from engine.nhl import scan as S
    sc = S.scan(games, players, teams, ctx, league, assets=assets,
                key_players={r["player"] for r in recs}, out_players=pulled_names,
                xg_players=(xs or {}).get("players"), pp=(xs or {}).get("pp"))
    for rd in (x for v in sc["reads"].values() for x in v.get("players") or []):
        slot = LN.slot_of(lines.get(rd.get("team")) or {}, rd.get("player") or "")
        if slot:
            rd["line"] = slot
            rd.setdefault("notes", []).append(f"Line {slot['unit']} with {' and '.join(slot['mates'])}")
    out["scan_reads"] = sc["reads"]
    inj_by_team: dict = {}
    for n, i in injuries.items():
        inj_by_team.setdefault(i.get("team") or "", []).append({"player": n, "status": i["status"],
                                                                "injury": i.get("injury") or ""})
    bets = []
    for g in slate.games:
        bets.extend(game_bets(g, teams, ctx, league))
    by_pair = {(g.home, g.away): g for g in slate.games}
    for gd in out["games"]:
        g = by_pair.get((gd["home"], gd["away"]))
        if g is not None:
            gd.update(spread=g.spread, total=g.total, home_ml=g.home_ml or None, away_ml=g.away_ml or None)
        t = sc["tapes"].get(f"{gd['away']}@{gd['home']}")
        if t:
            for team in (gd["away"], gd["home"]):
                t["sides"][team]["injuries"] = inj_by_team.get(team, [])
            t["pulled"] = sorted(n for n in pulled_names if (players.get(n) or {}).get("team") in (gd["home"], gd["away"]))
            gd["nhl_tape"] = t
    # THE CORRELATION ENGINE: two Edge plays on one game that argue
    # opposite ways — the weaker one is passed.
    from engine.nhl import edgehunter as EH
    for gm in slate.games:
        here = [r for r in recs if r["recommended"] and r["team"] in (gm.home, gm.away)]
        here += [b for b in bets if b.get("grade") != "Pass" and b.get("home") == gm.home]
        for weak, _strong, why in EH.contradictions(here):
            _edge_pass(weak, f"contradicts a stronger edge on this game: {why}")
    out["edge_model"] = EH.MODEL
    out["edge_census"] = _edge_census(recs + bets)
    from engine.marketscan import scan_recommendations
    out.update(status="slate", recommendations=recs, game_bets=bets, gate_census=census,
               odds_note=odds_note, market_scan=scan_recommendations(recs))
    out["counts"] = {"props_built": len(slate.props), "props_analyzed": len(recs),
                     "recommended": sum(1 for r in recs if r["recommended"]),
                     "game_bets": sum(1 for b in bets if b.get("grade") != "Pass")}
    return out, slate


def _edge_pass(r: dict, why: str) -> None:
    """Take a row off the Edge board after pricing (an injury designation, a
    contradiction), saying why on its Edge Hunter verdict."""
    eh = r.get("edge_hunter")
    if eh is not None:
        eh["passes"] = list(eh.get("passes") or []) + [why]
        eh.update(play=False, classification="Pass", stake_units=0.0, main_risk=why)
    if "recommended" in r:
        r["recommended"] = False
    r["grade"], r["stake_units"] = "Pass", 0.0


def _edge_census(rows: list[dict]) -> dict:
    """{classification: n} plus the commonest reasons a priced bet was not
    an Edge play — printed by the build and kept on the board."""
    by, why = {}, {}
    for r in rows:
        eh = r.get("edge_hunter") or {}
        by[eh.get("classification", "unassessed")] = by.get(eh.get("classification", "unassessed"), 0) + 1
        for p in (eh.get("passes") or [])[:1]:
            key = p.split(" — ")[0].split(":")[0]
            why[key] = why.get(key, 0) + 1
    return {"by_class": by, "top_passes": dict(sorted(why.items(), key=lambda kv: -kv[1])[:6])}


def attach_most_likely(out: dict, out_path: str, date: str) -> None:
    """likely.build over the props, then the one board — the same calls
    every other league makes, so the same bars apply."""
    from engine import boards as _boards, potd as _potd_keys
    from engine.likely import build as likely_build, previous_board
    census, kinds, turn = {}, {}, {}
    out[_potd_keys.POOL_KEY] = cut = []
    recs = out.get("recommendations") or []
    # SCALPY'S NO-BET CONDITIONS keep a prop off this list (an unstable
    # role, a blowout risk on saves); the Edge board still prices it.
    passed = [r for r in recs if r.get("scalpy_pass")]
    if passed:
        census[f"Scalpy pass — {len(passed)} prop(s): unstable role or blowout risk"] = len(passed)
    from engine.gamescan import leans_from_reads, stamp_picks
    lean_report: dict = {}
    out["most_likely"] = likely_build([r for r in recs if not r.get("scalpy_pass")], sport=SPORT,
                                      census=census, census_by_kind=kinds, cut=cut,
                                      previous=previous_board(out_path, date), turnover=turn,
                                      leans=leans_from_reads(out.get("scan_reads") or {}),
                                      lean_report=lean_report)
    if out.get("scan_reads"):
        stamp_picks(out["scan_reads"], lean_report, board=out["most_likely"])
    by_key = {(r["player"], r["market"]): r for r in recs}
    for row in out["most_likely"]:
        src = by_key.get((row.get("player"), row.get("market"))) or {}
        flags = list(src.get("scalpy_flags") or [])
        row["scalpy_flags"] = flags
        row["scalpy_grade"] = M.scalpy_grade(float(row.get("model_prob") or 0.0), flags)
        row["prop_tier"] = M.PROP_TIER.get(row.get("market"))
    if not out["most_likely"]:
        from engine.rankfit import load as rank_store
        if not any(k.startswith(f"{SPORT}:") for k in rank_store()):
            census["no market measured to rank yet — run rankfit for nhl"] = 1
    out.update(likely_turnover=turn, likely_census=census, likely_census_by_kind=kinds,
               board_guide=_boards.guide(SPORT), board_shelves=_boards.shelves(SPORT, out["most_likely"]))
    from engine import likelyboard
    print(f"  {likelyboard.attach(out, SPORT)}")
    # THE PARLAY ZONE, TWO LEGS (engine/parlays RULES["nhl"]): screened
    # over the board that just cleared the singles gates, as every sport's.
    from engine.parlays import attach as _parlays
    _parlays(out, SPORT)


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
    ap.add_argument("--live-lines", action="store_true",
                    help="pull the live market for in-progress games (three credits, the launcher's call)")
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
    if out.get("lines"):
        try:
            save_lines(out["lines"], date=args.date)
            print(f"  Lines: {len(out['lines'])} team(s) read off their newest shift charts")
        except OSError as exc:
            print(f"⚠️  lines file skipped: {exc}")
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
    # THE LIVE LINE (engine/livelines), as the hoops boards carry it: the
    # pull is three credits for the whole slate and only on the launcher's
    # say-so (--live-lines, its own lane behind football) or a full odds
    # run; charting from the history on disk is free and runs every build.
    try:
        from engine import livelines as _ll
        from engine.sources.oddsapi import NHL_TEAM_ABBR
        _live_games = [g for g in out.get("games") or [] if (g.get("live") or {}).get("state") == "live"]
        if _live_games and (args.odds or args.live_lines):
            _n, _note = _ll.pull_and_record(SPORT, NHL_TEAM_ABBR)
            if _n:
                print(f"  Live line: {_note}")
        _midnight = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        _tracked = _ll.attach(out.get("games") or [], SPORT, since=_midnight)
        if _tracked:
            print(f"  Live line: charting {_tracked} game(s)")
    except Exception as exc:                                # noqa: BLE001
        print(f"⚠️  live line tracking unavailable: {exc}")
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
        rs = out.get("recommendations") or []
        print(f"  Starting goalies: {out.get('starters_announced', 0)} of {2 * len(games)} named by their teams "
              f"(ESPN); the rest read from recent starts")
        print("  Shot quality: " + (
            f"on — {sum(1 for r in rs if any('Shot quality' in x for x in r.get('reasons') or []))} of "
            f"{len(rs)} priced rows read their shooter's expected goals"
            if out.get("shot_quality") else "off — no fitted model yet (python3 ingest.py nhl --shots)"))
        ec = out.get("edge_census") or {}
        if ec.get("by_class"):
            print(f"  {out.get('edge_model')}: " + ", ".join(f"{k} {v}" for k, v in ec["by_class"].items())
                  + ("; most passed for: " + ", ".join(f"{k} ({v})" for k, v in ec["top_passes"].items())
                     if ec.get("top_passes") else ""))
    print(f"NHL {args.date}: {len(games)} game(s), {c.get('props_analyzed', 0)} priced props → "
          f"{c.get('recommended', 0)} Edge pick(s), {c.get('game_bets', 0)} game bet(s), "
          f"{len(out.get('most_likely') or [])} Most Likely. Wrote {args.out}")


if __name__ == "__main__":
    main()
