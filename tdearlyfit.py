#!/usr/bin/env python3
"""Are our September touchdown chances too low? — the early weeks, graded.

    python3 tdearlyfit.py                 # 2022-2025, the box's database
    python3 tdearlyfit.py --db path/to/history.db

Ethan, 2026-09-27, with the other model's touchdown reports for Jets @
Lions and Chargers @ Bills. Our goal-line facts matched its to the carry
(Gibbs 11 red-zone carries, 5 inside the 5; St. Brown 6 red-zone targets,
3 inside the 10), and our chances still came in 3-16 points under both it
and the market: Allen 42% (it said ~58%, the book 57%), Hall 42% (56-60%),
Hampton 45% (~56%), St. Brown 52% (60-63%).

engine/tdbacktest never grades weeks 1-3: its replay needs three earlier
weeks of the same season (MIN_PRIOR_WEEKS), so the whole September the
live board leans on — this season's two games, last season carried in to
TD_CARRY_GAMES — has never been checked. This replays exactly that: weeks
2-4 of each season, the touchdown history this season's games plus last
season's most recent (to TD_CARRY_GAMES), the red-zone and opportunity
share from this season's games so far, and the lines' implied total —
then sets what the chain claimed against what happened, by band, beside
weeks 5+ from the ordinary replay for reference.

Reads only; writes nothing.
"""
from __future__ import annotations

import argparse
import sys

from engine import tdbacktest as B
from engine.fantasy import _short_key
from engine.models import ANYTIME_TD, Game, GameLog, Prop, Weather
from engine.sources.nflverse import TD_CARRY_GAMES
from engine.touchdowns import RedZoneUsage, td_probability

WEEKS = (2, 3, 4)
BANDS = ((0.0, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 1.01))


def _wk(p) -> int:
    try:
        return int(str(p).lstrip("0") or 0)
    except ValueError:
        return 0


def early_rows(conn, seasons) -> list:
    """[(season, week, player, prob, scored)] for weeks 2-4, built the way
    the live September board builds them."""
    rows = conn.execute(
        "SELECT season, period, player, team, opponent, position, market, value "
        "FROM player_game_logs WHERE sport='nfl' AND market IN "
        "('anytime_td','targets','carries','rz_tgt','rz_car','i5_car','xfp')").fetchall()
    form: dict = {}
    for r in rows:
        key = (r["season"], _short_key(r["player"], r["team"]))
        wk = form.setdefault(key, {}).setdefault(_wk(r["period"]), {})
        wk[r["market"]] = float(r["value"] or 0.0)
        if r["position"]:
            wk["_pos"] = r["position"]
        if r["opponent"]:
            wk["_opp"] = r["opponent"]
        wk.setdefault("_name", r["player"])
    games: dict = {}
    for g in conn.execute("SELECT season, period, home, away, spread, total FROM games "
                          "WHERE sport='nfl' AND total IS NOT NULL"):
        games[(g["season"], _wk(g["period"]), g["home"])] = (g["total"], g["spread"], True)
        games[(g["season"], _wk(g["period"]), g["away"])] = (g["total"], g["spread"], False)
    team_week: dict = {}
    for (season, short), weeks in form.items():
        for w, m in weeks.items():
            t = team_week.setdefault((season, w, short[2]), {"opp": 0.0, "xfp": 0.0})
            t["opp"] += m.get("targets", 0.0) + m.get("carries", 0.0)
            t["xfp"] += m.get("xfp", 0.0)
    out = []
    for (season, short), weeks in form.items():
        if season not in seasons:
            continue
        team = short[2]
        last = form.get((season - 1, short)) or {}
        for wk in WEEKS:
            marks = weeks.get(wk)
            if not marks or "anytime_td" not in marks:
                continue
            prior = [w for w in sorted(weeks) if w < wk]
            if not prior:
                continue
            game = games.get((season, wk, team))
            if not game:
                continue
            total, spread, is_home = game
            implied = B.implied_total(total, spread, is_home)
            if implied is None:
                continue
            n = len(prior)

            def avg(m):
                return sum(weeks[w].get(m, 0.0) for w in prior) / n
            opp_own = avg("targets") + avg("carries")
            team_opp = sum(team_week.get((season, w, team), {}).get("opp", 0.0) for w in prior) / n
            share = opp_own / team_opp if team_opp > 0 else 0.0
            rz_tgt, i5 = avg("rz_tgt"), avg("i5_car")
            rz_car = max(avg("rz_car"), i5)
            rz_share = min((rz_tgt + rz_car) / max(team_opp * 0.12, 0.1), 1.0) if team_opp > 0 else 0.0
            rz = RedZoneUsage(carries_inside_5=i5, carries_inside_10=rz_car, targets_inside_10=rz_tgt,
                              rz_touch_share=round(rz_share, 3), measured=bool(rz_tgt or rz_car), games=n)
            # THE LIVE CARRY: this season's games, then last season's most
            # recent, to TD_CARRY_GAMES (engine/sources/nflverse).
            vals = [weeks[w].get("anytime_td", 0.0) for w in reversed(prior)]
            vals += [last[w].get("anytime_td", 0.0) for w in sorted(last, reverse=True)
                     if "anytime_td" in last[w]][:max(0, TD_CARRY_GAMES - len(vals))]
            logs = [GameLog(week=i, opponent="", value=v) for i, v in enumerate(vals)]
            prop = Prop(player=marks.get("_name", short[1]), team=team, opponent=marks.get("_opp", ""),
                        position=marks.get("_pos", ""), market=ANYTIME_TD, logs=logs, career_avg=0.0,
                        vs_opponent_avg=None, lines=[])
            gm = Game(home=team if is_home else marks.get("_opp", ""),
                      away=marks.get("_opp", "") if is_home else team,
                      weather=Weather(dome=True, measured=True), total=float(total), spread=float(spread))
            own_xfp = avg("xfp")
            team_xfp = sum(team_week.get((season, w, team), {}).get("xfp", 0.0) for w in prior) / n
            xfp = {"xfp_share": own_xfp / team_xfp} if team_xfp > 0 and own_xfp > 0 else None
            prob, _ = td_probability(prop, gm, B._neutral_opponent(marks.get("_opp", "") or "OPP"),
                                     share, red_zone=rz, xfp=xfp)
            out.append((season, wk, prop.player, float(prob), 1 if marks.get("anytime_td", 0.0) > 0 else 0))
    return out


def bands(pairs) -> list:
    out = []
    for lo, hi in BANDS:
        b = [(p, y) for p, y in pairs if lo <= p < hi]
        if len(b) >= 30:
            out.append((lo, hi, len(b), sum(p for p, _ in b) / len(b), sum(y for _, y in b) / len(b)))
    return out


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=None)
    ap.add_argument("--seasons", default="2022-2025")
    a = ap.parse_args(argv)
    lo, _, hi = a.seasons.partition("-")
    seasons = set(range(int(lo), int(hi or lo) + 1))
    from engine.db import connect
    conn = connect(a.db) if a.db else connect()
    early = early_rows(conn, seasons)
    later: list = []
    B.run(conn, "nfl", collect=later.append)
    later = [(r["prob"], r["scored"]) for r in later if r["season"] in seasons]
    for label, pairs in (("weeks 2-4, as the live board builds them", [(p, y) for *_x, p, y in early]),
                         ("weeks 5+, the ordinary replay", later)):
        if not pairs:
            print(f"\n{label}: no rows")
            continue
        claim = sum(p for p, _ in pairs) / len(pairs)
        hit = sum(y for _, y in pairs) / len(pairs)
        print(f"\n{label}: {len(pairs):,} player-weeks — claimed {claim:.1%}, scored {hit:.1%} "
              f"({(hit - claim) * 100:+.1f} pts)")
        for lo_, hi_, n, c, h in bands(pairs):
            print(f"   {lo_:.0%}-{min(hi_, 1):.0%}   n {n:<5} claimed {c:.1%}  scored {h:.1%}  ({(h - c) * 100:+.1f})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
