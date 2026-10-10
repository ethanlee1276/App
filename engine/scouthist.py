"""What football history proves about the scout's flags, and the board's use of it.

    sudo -u qellys python3 -m engine.scouthist            # replay 2021+, every league, save what is proven
    sudo -u qellys python3 -m engine.scouthist --dry-run
    sudo -u qellys python3 -m engine.scouthist --sport cfb --dry-run   # one league

COLLEGE (2026-10-09): the same replay over college's stored games, with
college's own thresholds (scout.LEAGUE) and its own store
(cfb_scout_history.json). The bar is the NFL's, unchanged. The dry run
also prints the share of each league's stored games every game-script
threshold catches, so the college numbers can be checked against the
NFL's on the box's own lines.

Ethan, 2026-10-04, after the five-season replay: Most Likely is "what we
think is going to happen based off all data we collect ... offense and
defense and game script and past picks wins and losses and who can
struggle and do good".

THE REPLAY (moved here from nflaudit.py, which still prints it): every
stored player-game (2021 through the current season) in HISTORY_MARKETS
with five earlier games — reaching back into last season when this one is
young, so the current season counts from its first weeks —
his last-five average as the line, each flag's side scored against the
same side in unflagged games. That is the football effect before any
model.

WHAT COUNTS AS PROVEN, written before the box ran this module:
  * the flag's side ran BELOW the same side in unflagged games by at
    least PROVEN_GAP in BOTH halves (halves = seasons, or the first and
    second nine weeks when only one season scores);
  * on at least PROVEN_N games in each half;
  * and the model does not already price the situation itself
    (MODEL_PRICES — counting it twice would be the error, not the fix).
The shift kept is the SMALLER of the two halves' gaps.

The first run (2026-10-04, 2021-2025) would prove: a player's first game
back after missing his team's last game — receiving yards, catches and
rushing yards overs 4-8 points under the usual rate, a touchdown 14%
against 21%; and pass-attempt unders in projected shootouts.

WHO COUNTS FOR "FIRST GAME BACK" (2026-10-10). The flag means his team
played its last game without him. In the stored logs that is also every
backup who simply did not get in, and a backup's return is not a game the
board bets: his line is the average of a couple of spot starts and some
mop-up work, and mop-up work is what comes next. College's first save
proved the flag on quarterback pass-attempt overs at -35% — a backup
effect, not a starter coming back from an injury. Ethan: "yes make that
fix." So a return is scored only for a REGULAR: in at least REGULAR_OF of
the five games his line is built from, he was among his team's top
REGULAR_TOP in that role's volume (the passer with the most attempts; the
two backs with the most carries; the three players with the most catches).
Only games IN THE RETURN'S SEASON AND FOR ITS TEAM count: the first version
also counted last season's, and college's QB number grew to -40% — a
quarterback who started last November and is a backup now (the transfer
portal, a lost job) "returned" in his first mop-up appearance against a
line built on last year's starts.
Decided from those earlier games only, never from the return game. A
part-timer's return is left out of the replay altogether — neither
flagged nor in the baseline — and the dry run prints how many of each.

WHAT THE BOARD DOES WITH IT (engine/likelyctx.apply): a pick carrying a
proven flag on that market and side is lowered by the shift — only ever
lowered, never below its price — and the card says why. Nothing is
removed. The record's own correction (likelyctx.fit) still runs; a pick
takes whichever lowers it more, never both.

Runs weekly as a detached child (engine/maintenance), so the store tracks
the history as seasons are added. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from collections import defaultdict
from pathlib import Path

from . import modelstate
from . import scout as SC
from .likelyctx import game_keys, history_index, log_game

HISTORY_MARKETS = ("rush_yds", "rec_yds", "receptions", "pass_yds", "rush_att", "pass_att", "anytime_td")
#: The bar, fixed before any box run of this module.
PROVEN_GAP = 0.03
PROVEN_N = 100
#: Flags whose situation the model already prices: wind (engine/weather's
#: measured passing cut), and a team's expected points (the touchdown
#: model scales by the book's implied total; low_total_over reads the same
#: number). History shows them large; applying them again would double them.
MODEL_PRICES = frozenset({"wind_pass_over", "low_implied_td", "low_total_over"})
#: A regular, for the first-game-back flag (2026-10-10): among his team's
#: top N in the role's volume in at least REGULAR_OF of his last five games.
REGULAR_TOP = {"pass": 1, "rush": 2, "catch": 3}
REGULAR_OF = 3
_VOLUME = {"pass_att": "pass", "rush_att": "rush", "receptions": "catch"}


def role_group(market: str, position) -> str | None:
    """Which volume makes him a regular for this market: a quarterback's
    rushing is his starting job; a back's catches are his backfield job.
    None (an anytime touchdown with no position) means any of the three."""
    pos = str(position or "").upper()
    if market in ("pass_att", "pass_yds"):
        return "pass"
    if market in ("rush_att", "rush_yds"):
        return "pass" if pos == "QB" else "rush"
    if market in ("receptions", "rec_yds"):
        return "rush" if pos in ("RB", "FB") else "catch"
    return {"QB": "pass", "RB": "rush", "FB": "rush", "WR": "catch", "TE": "catch"}.get(pos)


def team_leaders(series) -> dict:
    """{(team, game_id, group): the players among that team's top N in that
    game} — ties at the cut all count."""
    vol = defaultdict(dict)
    for (player, market), rows in series.items():
        grp = _VOLUME.get(market)
        if not grp:
            continue
        for _d, value, team, _pos, g, _season in rows:
            if value and value > 0:
                vol[(team, g["game_id"], grp)][player] = float(value)
    top = {}
    for key, by in vol.items():
        cut = sorted(by.values(), reverse=True)[:REGULAR_TOP[key[2]]][-1]
        top[key] = {p for p, v in by.items() if v >= cut}
    return top


def is_regular(player: str, window, group, leaders: dict, season=None, team=None) -> bool:
    """Was he a regular in these games (the five his line is built from)?
    Only games in ``season`` for ``team`` count when they are given: last
    season's starter on another depth chart is not this team's regular."""
    groups = (group,) if group else tuple(REGULAR_TOP)
    hits = sum(1 for _d, _v, t, _pos, g, s in window
               if (season is None or s == season) and (team is None or t == team)
               and any(player in leaders.get((t, g["game_id"], gr), ()) for gr in groups))
    return hits >= REGULAR_OF


def _week_no(period) -> int:
    try:
        return int(str(period).strip())
    except (TypeError, ValueError):
        return 0


def replay(hist, seasons=None, sport: str = "nfl") -> dict:
    """Every stored player-game in HISTORY_MARKETS with five earlier games
    (across seasons)
    that season: the line is his last-five average (0.5 for touchdowns),
    and each flag's side is scored against the same side in unflagged
    games of the same market. A negative gap that holds in both halves of
    the seasons is a football effect form alone does not carry."""
    games, by_team, _ = history_index(hist, set(), sport)
    by_key = game_keys(games)
    q = ("SELECT player, season, period, game_id, team, position, market, value FROM player_game_logs "
         f"WHERE sport=? AND market IN ({','.join('?' * len(HISTORY_MARKETS))})")
    args = [sport, *HISTORY_MARKETS]
    if seasons:
        q += f" AND season IN ({','.join('?' * len(seasons))})"
        args += list(seasons)
    series = defaultdict(list)
    played = defaultdict(set)
    for r in hist.execute(q, args):
        g = log_game(r, games, by_key)       # the ids differ ("LV-004" / "LV@KC")
        if g is None:
            continue
        # ACROSS SEASONS (2026-10-04, Ethan: "make sure ur using 2026 data
        # too"). Keyed per season, a game needed five earlier games THAT
        # season, so with four 2026 weeks played not one 2026 game counted.
        # His last-five now reaches back into last season, as the live model
        # carries a season over in its first weeks (engine/carry).
        series[(r["player"], r["market"])].append((g["_d"], r["value"], r["team"], r["position"], g,
                                                   r["season"]))
        played[(r["player"], r["season"])].add(g["game_id"])
    cells = defaultdict(lambda: defaultdict(lambda: [0, 0]))      # flag -> half -> [hits, n]
    base = defaultdict(lambda: defaultdict(lambda: [0, 0]))       # (market, side) -> half -> [hits, n]
    flagged_ms = defaultdict(set)
    # The seasons the replay can actually score (a game needs five earlier
    # ones, any season). With two or more, the halves are seasons; with
    # one — the 2026-10-03 run had only 2025 to score — they are its first
    # and second nine weeks, so "both halves" still means something.
    for rows in series.values():
        rows.sort(key=lambda x: x[0])
    all_seasons = sorted({row[5] for rows in series.values() for row in rows[5:]})
    leaders = team_leaders(series)
    back = {"kept": 0, "skipped": 0}
    by_season = len(all_seasons) >= 2
    mid = all_seasons[len(all_seasons) // 2] if by_season else "week 10"
    for (player, market), rows in series.items():
        for i in range(5, len(rows)):
            d, value, team, pos, g, season = rows[i]
            prior = [row[1] for row in rows[:i]][::-1]
            in_season = sum(1 for row in rows[:i] if row[5] == season)
            line = 0.5 if market == "anytime_td" else sum(prior[:5]) / 5
            if market != "anytime_td" and line <= 0:
                continue
            prev = [x for x in by_team.get(team, []) if x["_d"] < d and x.get("season") == season]
            missed = bool(prev) and prev[-1]["game_id"] not in played[(player, season)]
            if missed:
                if not is_regular(player, rows[i - 5:i], role_group(market, pos), leaders, season, team):
                    back["skipped"] += 1           # a part-timer's return: not a game the board bets
                    continue
                back["kept"] += 1
            roof = str(g.get("roof") or "").lower()
            half = (("early" if season < mid else "late") if by_season
                    else ("early" if _week_no(g.get("period")) < 10 else "late"))
            for side in (("YES",) if market == "anytime_td" else ("OVER", "UNDER")):
                s = SC.situation(market, side, line=line, position=pos, values=prior,
                                 game_spread=g.get("spread"), home=(team == g["home"]), total=g.get("total"),
                                 wind=g.get("wind"), outdoor=(None if not roof else roof in ("outdoors", "open")),
                                 weekday=None if g.get("_approx") else d.weekday(), games_season=in_season,
                                 missed_last=missed, league=sport)
                # The line IS his form here, so the two line flags cannot fire.
                fl = [f for f in SC.flags(s) if f not in ("line_above_form", "line_below_form")]
                hit = (value > line) if side in ("OVER", "YES") else (value < line)
                cell = base[(market, side)][half]
                cell[0] += hit
                cell[1] += 1
                for f in fl:
                    c = cells[(f, market, side)][half]
                    c[0] += hit
                    c[1] += 1
                    flagged_ms[f].add((market, side))
    out = {}
    for (f, market, side), halves in cells.items():
        res = {}
        for half in ("early", "late"):
            fh, fn = halves[half]
            bh, bn = base[(market, side)][half]
            if fn >= 30 and bn:
                res[half] = {"n": fn, "rate": fh / fn, "base": bh / bn, "gap": fh / fn - bh / bn}
        if res:
            out.setdefault(f, {})[f"{market} {side}"] = res
    return {"seasons": all_seasons, "split": mid, "flags": out, "first_game_back": back}


def proven(h: dict) -> dict:
    """{flag: {"MARKET SIDE": {"shift", "n", "gaps"}}} — the replay's
    findings that clear the bar above."""
    out: dict = {}
    for flag, cells in (h.get("flags") or {}).items():
        if flag in MODEL_PRICES:
            continue
        for ms, res in cells.items():
            if len(res) != 2:
                continue
            gaps = [r["gap"] for r in res.values()]
            ns = [r["n"] for r in res.values()]
            if all(g <= -PROVEN_GAP for g in gaps) and all(n >= PROVEN_N for n in ns):
                out.setdefault(flag, {})[ms] = {"shift": round(max(gaps), 4), "n": sum(ns),
                                                "gaps": [round(g, 4) for g in gaps]}
    return out


def _store(sport: str = "nfl") -> Path:
    """The NFL's store keeps its original name, so the box's file is read
    as it is; every other league has its own."""
    return Path(modelstate.path("scout_history.json" if sport == "nfl" else f"{sport}_scout_history.json"))


def load(path=None, sport: str = "nfl") -> dict:
    try:
        return json.loads(Path(path or _store(sport)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(found: dict, seasons, path=None, sport: str = "nfl") -> None:
    p = Path(path or _store(sport))
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps({"flags": found, "seasons": list(seasons),
                               "at": _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
                               .isoformat(timespec="seconds")}, indent=1), encoding="utf-8")
    tmp.replace(p)


def shift_for(codes, market: str, side: str, store: dict | None = None):
    """(the most negative proven shift among this pick's flags on its market
    and side, the flag) — or (0.0, None)."""
    flags = ((store if store is not None else load()).get("flags")) or {}
    s = str(side or "").upper()
    s = "YES" if s in ("YES", "OVER") and market == "anytime_td" else s
    best, who = 0.0, None
    for f in codes or []:
        cell = (flags.get(f) or {}).get(f"{market} {s}")
        if cell and cell["shift"] < best:
            best, who = cell["shift"], f
    return best, who


#: The game-script thresholds whose catch the dry run prints, per league.
SHARE_CHECKS = (("total >= SHOOTOUT_TOTAL", "total", "SHOOTOUT_TOTAL", 1),
                ("total <= LOW_TOTAL", "total", "LOW_TOTAL", -1),
                ("|spread| >= BIG_DOG", "abs_spread", "BIG_DOG", 1),
                ("|spread| >= BIG_FAV_PASS", "abs_spread", "BIG_FAV_PASS", 1),
                ("|spread| >= BLOWOUT", "abs_spread", "BLOWOUT", 1))


def threshold_shares(hist, sport: str) -> dict:
    """{check: (share of the league's stored games with a line it catches,
    games with a line)} — the check that college's thresholds catch about
    the share of college games the NFL's catch of NFL games."""
    rows = hist.execute("SELECT spread, total FROM games WHERE sport=? AND total IS NOT NULL "
                        "AND spread IS NOT NULL", (sport,)).fetchall()
    out = {}
    for label, field, name, sign in SHARE_CHECKS:
        cut = SC.threshold(name, sport)
        vals = [float(r["total"]) if field == "total" else abs(float(r["spread"])) for r in rows]
        hit = sum(1 for v in vals if (v >= cut if sign > 0 else v <= cut))
        out[f"{label.split()[0]} {label.split()[1]} {cut:g}"] = (hit / len(vals) if vals else None, len(vals))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.scouthist")
    ap.add_argument("--dry-run", action="store_true", help="replay and report, save nothing")
    ap.add_argument("--history-db", default="", help="history path (default data/history.db)")
    ap.add_argument("--sport", default="", help="one league (default: every league the scout reads)")
    a = ap.parse_args(argv)
    from . import db
    from .likelyctx import SPORTS, ro
    hist = ro(a.history_db or db.DEFAULT_DB)
    for sport in ([a.sport.lower()] if a.sport else list(SPORTS)):
        print(f"=== {sport.upper()}")
        if a.dry_run:
            for label, (share, n) in threshold_shares(hist, sport).items():
                print(f"  catches  {label:28} " + (f"{share:6.1%} of {n} games" if share is not None
                                                   else "no stored lines"))
        h = replay(hist, sport=sport)
        found = proven(h)
        print(f"seasons {h['seasons']} (halves split at {h['split']})")
        fb = h.get("first_game_back") or {}
        print(f"  first game back: {fb.get('kept', 0)} returns by regulars scored, "
              f"{fb.get('skipped', 0)} by part-timers left out")
        for flag, cells in found.items():
            for ms, c in cells.items():
                print(f"  PROVEN  {flag:20} {ms:18} shift {c['shift']:+.1%}  (halves {c['gaps']}, n {c['n']})")
        if not found:
            print("  nothing proven — the board's flags stay notes")
        if not a.dry_run:
            save(found, h["seasons"], sport=sport)
            print("saved; the board reads it on its next build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
