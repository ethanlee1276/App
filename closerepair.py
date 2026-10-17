#!/usr/bin/env python3
"""Rebuild every settled NFL prop's closing line from PREGAME prices only.

    cd /srv/qellys && sudo -u qellys python3 closerepair.py            (dry run)
    cd /srv/qellys && sudo -u qellys python3 closerepair.py --apply    (writes)

Ethan, 2026-09-29, after the close check showed the NFL "closes" were
in-game lines (Barner receiving under 19.5 "closing" at 69.5 on a final of
69; Burrow 255.5 → 349.5): "Yes, repair the closes."

WHY THE STORED CLOSES ARE WRONG. The close is the last price before
kickoff, and the settler finds "before kickoff" by a start stamp on each
line snapshot. An NFL kickoff is a bare Eastern clock ("20:15"), which the
recorder refused to read, so no NFL snapshot was ever stamped, nothing was
ever cut as in-play, and on a staggered Sunday the last in-game re-price
became the close. Fixed going forward in engine/linemoves (a5342e72); this
fixes the settled rows.

HOW. Each settled NFL player-prop bet is placed on its game through our own
stat logs (the player's team that week) and the nflverse schedule (that
game's kickoff, Eastern). Then, from our line snapshots and any harvested
price, only quotes taken BEFORE that kickoff (and within a week of it) are
read:
  closing line  — the median line across books at the last pregame instant;
  closing price — for the bet's own side, at the bet's own line, the median
                  across books at the last pregame instant that quoted it.
A bet with no pregame quote at all gets NULL: a close known to have come
from the broken path is worse than none (the rule `repair_closing_odds`
already follows).

WHAT IT CHANGES. `closing_line` and `closing_odds` on settled NFL prop rows —
the numbers the Record page's closing-line value and the audits read. It
never touches a grade, a status, a stake or a P&L. The dry run lists every
change; --apply writes them in one transaction and saves every old value
to data/closerepair_<time>.json first, so it can be put back.
"""
from __future__ import annotations

import argparse
import bisect
import datetime as _dt
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.sources.oddsapi import normalize_name                   # noqa: E402

#: A quote this long before kickoff is not a close for that game.
WINDOW_S = 7 * 24 * 3600
SETTLED = ("won", "lost", "push")
GAME_MARKETS = ("moneyline", "total", "spread", "team_total")


def kickoff_epoch(gameday: str, gametime: str) -> float | None:
    from engine.linemoves import start_epoch
    return start_epoch(gametime, gameday, "America/New_York")


def schedule_kickoffs(rows) -> dict:
    """``{(season, week, team): kickoff epoch}`` from nflverse schedule rows."""
    out = {}
    for r in rows:
        try:
            season, week = int(r.get("season")), int(r.get("week"))
        except (TypeError, ValueError):
            continue
        k = kickoff_epoch(str(r.get("gameday") or ""), str(r.get("gametime") or ""))
        if k is None:
            continue
        for side in ("home_team", "away_team"):
            team = str(r.get(side) or "")
            if team:
                out[(season, week, team)] = k
    return out


def player_teams(hist_conn) -> dict:
    """``{(normalized player, season, week): team}`` from our NFL stat logs."""
    out = {}
    for r in hist_conn.execute(
            "SELECT DISTINCT player, season, period, team FROM player_game_logs WHERE sport='nfl'"):
        try:
            out[(normalize_name(r[0]), int(r[1]), int(r[2]))] = r[3]
        except (TypeError, ValueError):
            continue
    return out


def pregame_quotes(snapshots, harvested, wanted: dict) -> dict:
    """``{(normalized player, market): [(ts, line, over, under), ...]}``,
    only for the (player, market) pairs in ``wanted``, sorted by time.
    ``wanted`` maps each pair to the sorted kickoffs it needs; a quote is
    kept when it falls in the week before one of them."""
    out = defaultdict(list)

    def keep(who, market, ts, line, over, under):
        ks = wanted.get((who, market))
        if not ks:
            return
        i = bisect.bisect_right(ks, ts)          # first kickoff after ts
        if i < len(ks) and ks[i] - ts <= WINDOW_S:
            out[(who, market)].append((ts, line, over, under))

    for r in snapshots:
        try:
            keep(normalize_name(r["player"]), r["market"], float(r["ts"]),
                 float(r["line"]), r.get("over_odds"), r.get("under_odds"))
        except (KeyError, TypeError, ValueError):
            continue
    for r in harvested:
        try:
            ts = _dt.datetime.fromisoformat(str(r["taken_at"]).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=_dt.timezone.utc)
            keep(normalize_name(r["player"]), r["market"], ts.timestamp(),
                 float(r["line"]), r["over_odds"], r["under_odds"])
        except (KeyError, TypeError, ValueError):
            continue
    for v in out.values():
        v.sort(key=lambda q: q[0])
    return out


def _legal(p) -> int | None:
    try:
        p = int(p)
    except (TypeError, ValueError):
        return None
    return p if abs(p) >= 100 else None


def close_for(quotes, kickoff: float, line, side: str):
    """``(closing line, closing price)`` from the quotes before ``kickoff``."""
    pre = [q for q in quotes if kickoff - WINDOW_S <= q[0] < kickoff]
    if not pre:
        return None, None
    last = pre[-1][0]
    close_line = statistics.median(q[1] for q in pre if q[0] == last)
    close_odds = None
    try:
        want = round(float(line), 1)
    except (TypeError, ValueError):
        want = None
    at = [q for q in pre if want is not None and round(q[1], 1) == want]
    if at:
        t = at[-1][0]
        col = 3 if str(side or "OVER").upper() == "UNDER" else 2
        prices = [p for p in (_legal(q[col]) for q in at if q[0] == t) if p is not None]
        if prices:
            close_odds = int(round(statistics.median(prices)))
    return close_line, close_odds


def plan(conn, hist_conn, schedule_rows, snapshots, harvested) -> dict:
    """Every settled NFL prop, its stored close, and the pregame close."""
    import re
    week_re = re.compile(r"^(\d{4})-W(\d{1,2})$")
    kicks = schedule_kickoffs(schedule_rows)
    teams = player_teams(hist_conn)
    bets = conn.execute(
        "SELECT id, date, game_day, player, market, side, line, status, category, "
        "closing_line, closing_odds FROM bets WHERE sport='nfl' AND status IN (?,?,?) "
        "ORDER BY date, id", SETTLED).fetchall()
    placed, unplaced = [], []
    wanted = defaultdict(set)
    for b in bets:
        if b["market"] in GAME_MARKETS:
            continue
        m = week_re.match(str(b["date"] or ""))
        who = normalize_name(b["player"] or "")
        if not m:
            unplaced.append((b, "no week label"))
            continue
        season, week = int(m.group(1)), int(m.group(2))
        team = teams.get((who, season, week))
        k = kicks.get((season, week, team)) if team else None
        if k is None:
            unplaced.append((b, "no stat log for him that week" if not team else "no kickoff on the schedule"))
            continue
        placed.append((b, k))
        wanted[(who, b["market"])].add(k)
    wanted = {key: sorted(v) for key, v in wanted.items()}
    quotes = pregame_quotes(snapshots, harvested, wanted)
    changes, same = [], 0
    for b, k in placed:
        new_line, new_odds = close_for(quotes.get((normalize_name(b["player"]), b["market"]), []),
                                       k, b["line"], b["side"])
        old_line, old_odds = b["closing_line"], b["closing_odds"]
        if old_line == new_line and (old_odds == new_odds or (old_odds is not None and new_odds is not None
                                                               and int(old_odds) == int(new_odds))):
            same += 1
            continue
        changes.append({"id": b["id"], "date": b["date"], "category": b["category"],
                        "player": b["player"], "market": b["market"], "side": b["side"],
                        "line": b["line"], "status": b["status"],
                        "old_line": old_line, "new_line": new_line,
                        "old_odds": old_odds, "new_odds": new_odds})
    return {"examined": len(placed) + len(unplaced), "placed": len(placed), "same": same,
            "changes": changes, "unplaced": unplaced}


def _clv(line, close, side):
    if line is None or close is None:
        return None
    move = float(close) - float(line)
    return move if str(side or "OVER").upper() != "UNDER" else -move


def render(p: dict) -> str:
    out = ["CLOSE REPAIR — settled NFL props, closes rebuilt from pregame prices only",
           f"  {p['examined']} settled NFL props · {p['placed']} placed on their game · "
           f"{p['same']} already right · {len(p['changes'])} to change · "
           f"{len(p['unplaced'])} could not be placed (left as they are)", ""]
    before = defaultdict(lambda: [0, 0])
    after = defaultdict(lambda: [0, 0])
    for c in p["changes"]:
        won = c["status"] == "won"
        for bucket, close in ((before, c["old_line"]), (after, c["new_line"])):
            v = _clv(c["line"], close, c["side"])
            if v is not None and v < 0:
                bucket["lost the close"][0 if won else 1] += 1
    if p["changes"]:
        b, a = before["lost the close"], after["lost the close"]
        out.append(f"  among the changed rows, 'lost the close' goes from {b[0]}-{b[1]} to {a[0]}-{a[1]}")
        out.append("")
        out.append("  every change (line: old → new · price: old → new)")
    for c in p["changes"]:
        def f(x):
            return "—" if x is None else (f"{int(x):+d}" if isinstance(x, int) else f"{float(x):g}")
        out.append(f"    {str(c['date']):9} {str(c['category'])[:11]:11} {str(c['player'])[:22]:22} "
                   f"{str(c['market'])[:12]:12} {str(c['side'] or 'OVER'):5} {f(c['line']):>6}   "
                   f"line {f(c['old_line']):>6} → {f(c['new_line']):<6}  price {f(c['old_odds']):>5} → "
                   f"{f(c['new_odds']):<5} ({c['status']})")
    if p["unplaced"]:
        why = defaultdict(int)
        for _b, reason in p["unplaced"]:
            why[reason] += 1
        out.append("")
        out.append("  could not be placed on a game (left unchanged): "
                   + ", ".join(f"{n} {r}" for r, n in sorted(why.items())))
    return "\n".join(out)


def apply_changes(conn, changes: list, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    path = backup_dir / f"closerepair_{time.strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps([{"id": c["id"], "closing_line": c["old_line"],
                                 "closing_odds": c["old_odds"]} for c in changes]))
    from engine.ledger import audit_reason
    with audit_reason(conn, "closerepair"):
        with conn:
            for c in changes:
                conn.execute("UPDATE bets SET closing_line=?, closing_odds=? WHERE id=?",
                             (c["new_line"], c["new_odds"], c["id"]))
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    ap.add_argument("--db", help="the ledger (default data/ledger.db)")
    a = ap.parse_args(argv)
    from engine import db as hist_db
    from engine import ledger
    from engine.linemoves import stream_history
    from engine.sources.nflverse import load_schedules
    conn = ledger.connect(a.db) if a.db else ledger.connect()
    hconn = hist_db.connect()
    try:
        harvested = hconn.execute(
            "SELECT player, market, taken_at, line, over_odds, under_odds FROM odds_history "
            "WHERE sport='nfl'").fetchall()
    except Exception:                                         # noqa: BLE001
        harvested = []
    p = plan(conn, hconn, load_schedules(), stream_history(), harvested)
    print(render(p))
    if not a.apply:
        print("\n  DRY RUN — nothing written. Add --apply to write these changes.")
        return 0
    if not p["changes"]:
        print("\n  Nothing to write.")
        return 0
    path = apply_changes(conn, p["changes"], ROOT / "data")
    print(f"\n  WROTE {len(p['changes'])} closes. Old values saved to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
