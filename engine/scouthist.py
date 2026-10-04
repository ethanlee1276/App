"""What football history proves about the scout's flags, and the board's use of it.

    sudo -u qellys python3 -m engine.scouthist            # replay 2021+, save what is proven
    sudo -u qellys python3 -m engine.scouthist --dry-run

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


def _week_no(period) -> int:
    try:
        return int(str(period).strip())
    except (TypeError, ValueError):
        return 0


def replay(hist, seasons=None) -> dict:
    """Every stored player-game in HISTORY_MARKETS with five earlier games
    (across seasons)
    that season: the line is his last-five average (0.5 for touchdowns),
    and each flag's side is scored against the same side in unflagged
    games of the same market. A negative gap that holds in both halves of
    the seasons is a football effect form alone does not carry."""
    games, by_team, _ = history_index(hist, set())
    by_key = game_keys(games)
    q = ("SELECT player, season, period, game_id, team, position, market, value FROM player_game_logs "
         f"WHERE sport='nfl' AND market IN ({','.join('?' * len(HISTORY_MARKETS))})")
    args = list(HISTORY_MARKETS)
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
            roof = str(g.get("roof") or "").lower()
            half = (("early" if season < mid else "late") if by_season
                    else ("early" if _week_no(g.get("period")) < 10 else "late"))
            for side in (("YES",) if market == "anytime_td" else ("OVER", "UNDER")):
                s = SC.situation(market, side, line=line, position=pos, values=prior,
                                 game_spread=g.get("spread"), home=(team == g["home"]), total=g.get("total"),
                                 wind=g.get("wind"), outdoor=(None if not roof else roof in ("outdoors", "open")),
                                 weekday=None if g.get("_approx") else d.weekday(), games_season=in_season,
                                 missed_last=missed)
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
    return {"seasons": all_seasons, "split": mid, "flags": out}


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


def _store() -> Path:
    return Path(modelstate.path("scout_history.json"))


def load(path=None) -> dict:
    try:
        return json.loads(Path(path or _store()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(found: dict, seasons, path=None) -> None:
    p = Path(path or _store())
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.scouthist")
    ap.add_argument("--dry-run", action="store_true", help="replay and report, save nothing")
    ap.add_argument("--history-db", default="", help="history path (default data/history.db)")
    a = ap.parse_args(argv)
    from . import db
    from .likelyctx import ro
    h = replay(ro(a.history_db or db.DEFAULT_DB))
    found = proven(h)
    print(f"seasons {h['seasons']} (halves split at {h['split']})")
    for flag, cells in found.items():
        for ms, c in cells.items():
            print(f"  PROVEN  {flag:20} {ms:18} shift {c['shift']:+.1%}  (halves {c['gaps']}, n {c['n']})")
    if not found:
        print("  nothing proven — the board's flags stay notes")
    if not a.dry_run:
        save(found, h["seasons"])
        print("saved; the board reads it on its next build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
