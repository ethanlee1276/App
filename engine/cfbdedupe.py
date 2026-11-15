"""College football's stored games and stat lines, one game once (2026-11-14).

    python3 -m engine.cfbdedupe                 # what it would remove; writes nothing
    python3 -m engine.cfbdedupe --apply         # remove it
    python3 -m engine.cfbdedupe --season 2026   # one season (default: every season)

Ethan's catch-up run (step PU), 2026-11-14: Cooper Barkate's Miami games
were filed two and three times each. Each game had its official row
("401858249"), the same-night box score's provisional copy under the
schedule's key ("MIA@CLEM-box"), and sometimes another under ESPN's
("401858249-box"). The Notre Dame game also sat on two days (11-07 and
11-08). Across 2026, 53,072 of 107,233 college (player, market, opponent)
keys sat under two or more game ids.

Three writers made them, each fixed where it writes:
  * the same-night box settle never purged a college game's provisional
    rows: it looked for the official rows under the schedule's key, and
    the play file keys a game by ESPN's number (engine/boxsettle,
    `has_official_rows`, `purge_provisional`, now by the two teams);
  * it filed one copy for every games row of a game — its ESPN id and
    away@home, and a night game's Eastern and UTC days — now one;
  * the play file's join took whichever of a night game's two days came
    out last, so a later run filed the same game again under the other
    (engine/ingest.cfb_games_for, now the Eastern day always).

THIS REMOVES WHAT THEY LEFT. Stat lines: within one player's market against
one opponent, rows a day or less apart are one game. The official row is
kept (not a `-box` copy, ESPN's number before another key, the earlier day
first), and the rest go. Where a box copy's number differs from the kept
one, the count and a few examples are printed (Barkate at Notre Dame: 144
and 92). Barkate's copies were read mid-game, from the live board's cached
summary on a failed read (engine/boxsettle, step QQ). Most of the rest are
not: Ethan's run, 2026-11-14, found 4,406 in 2026, some of them above the
play file's number (A'Marion Peterson: 5 carries in the box, 4 in the play
file), which no mid-game copy can be. The two sources count differently, and
which one college grades on was the decision under RUN_NEXT 00e: the box
score, Ethan answered (step RB, engine/boxsettle.BOX_GRADES), from the copies
filed after 2026-11-14 on. The play file's row is kept here: the copies this
removes were filed before a box score had to be final to be filed, and some
were read mid-game. Games: one pair's rows a day or
less apart with the same final score are one game. The away@home row on the
earlier day is kept, it takes any line or note only the others carried,
and the rest go.

Why it matters beyond the reports: grading treats two rows of one game as a
doubleheader's two legs, and voids a bet whose two rows fall on either side
of its line once the day is final. Read-only without ``--apply``.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys

BOX = "-box"
#: Examples of a box copy that disagreed with the kept row, printed a season.
EXAMPLES = 8
#: Rows deleted per statement.
CHUNK = 400


def _day(p) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(str(p)[:10])
    except (TypeError, ValueError):
        return None


def _rank(row) -> tuple:
    """Smaller is kept: not a provisional copy, ESPN's number, earlier day."""
    gid = str(row["game_id"] or "")
    return (gid.endswith(BOX), not gid.isdigit(), str(row["period"] or ""), gid)


def clusters(rows) -> list:
    """Rows of one key, ordered by period, split where a gap passes a day."""
    out, cur, start = [], [], None
    for r in rows:
        d = _day(r["period"])
        if cur and (d is None or start is None or (d - start).days > 1):
            out.append(cur)
            cur = []
        if not cur:
            start = d
        cur.append(r)
    if cur:
        out.append(cur)
    return out


def plan_logs(conn, season: int) -> dict:
    """What would go from one season's stat lines: {"rows", "keys", "groups",
    "delete": [rowid…], "disagree", "examples"}. Streams the season."""
    q = ("SELECT rowid AS rid, period, game_id, player, team, opponent, market, value "
         "FROM player_game_logs WHERE sport='cfb' AND season=? "
         "ORDER BY player, team, opponent, market, period")
    res = {"rows": 0, "keys": 0, "groups": 0, "delete": [], "disagree": 0, "examples": []}
    key, buf = None, []

    def flush():
        if not buf:
            return
        res["keys"] += 1
        for group in clusters(buf):
            if len(group) < 2:
                continue
            res["groups"] += 1
            group = sorted(group, key=_rank)
            keep = group[0]
            res["delete"].extend(r["rid"] for r in group[1:])
            other = {float(r["value"]) for r in group[1:] if str(r["game_id"]).endswith(BOX)}
            if not str(keep["game_id"]).endswith(BOX) and other - {float(keep["value"])}:
                res["disagree"] += 1
                if len(res["examples"]) < EXAMPLES:
                    res["examples"].append(
                        f"{keep['player']} ({keep['team']} vs {keep['opponent']}) {keep['market']} "
                        f"{keep['period']}: kept {float(keep['value']):g}, box {sorted(other)}")

    for r in conn.execute(q, (int(season),)):
        res["rows"] += 1
        k = (r["player"], r["team"], r["opponent"], r["market"])
        if k != key:
            flush()
            key, buf = k, []
        buf.append(r)
    flush()
    return res


def plan_games(conn, season: int) -> dict:
    """What would go from one season's games rows: {"pairs", "delete": [rowid…],
    "fill": [(rowid, {col: value})]}."""
    q = ("SELECT rowid AS rid, period, game_id, home, away, home_score, away_score, spread, total, extra "
         "FROM games WHERE sport='cfb' AND season=? ORDER BY home, away, period")
    res = {"pairs": 0, "delete": [], "fill": []}
    key, buf = None, []

    def same_final(a, b):
        sa, sb = (a["home_score"], a["away_score"]), (b["home_score"], b["away_score"])
        return None in sa or None in sb or sa == sb

    def flush():
        for group in clusters(buf):
            if len(group) < 2:
                continue
            keep = sorted(group, key=lambda r: ("@" not in str(r["game_id"] or ""), str(r["period"] or "")))[0]
            dupes = [r for r in group if r is not keep and same_final(keep, r)]
            if not dupes:
                continue
            res["pairs"] += 1
            fill: dict = {}
            for col in ("home_score", "away_score", "spread", "total"):
                if keep[col] is None:
                    got = next((r[col] for r in dupes if r[col] is not None), None)
                    if got is not None:
                        fill[col] = got
            try:
                extra = json.loads(keep["extra"] or "{}") or {}
            except (ValueError, TypeError):
                extra = {}
            merged = dict(extra)
            for r in dupes:
                try:
                    for k, v in (json.loads(r["extra"] or "{}") or {}).items():
                        merged.setdefault(k, v)
                except (ValueError, TypeError):
                    continue
            if merged != extra:
                fill["extra"] = json.dumps(merged)
            if fill:
                res["fill"].append((keep["rid"], fill))
            res["delete"].extend(r["rid"] for r in dupes)

    for r in conn.execute(q, (int(season),)):
        k = (r["home"], r["away"])
        if k != key:
            flush()
            key, buf = k, []
        buf.append(r)
    flush()
    return res


def apply(conn, logs: dict, games: dict) -> int:
    """Remove the planned rows; returns rows removed."""
    n = 0
    for table, ids in (("player_game_logs", logs.get("delete") or []), ("games", games.get("delete") or [])):
        for i in range(0, len(ids), CHUNK):
            part = ids[i:i + CHUNK]
            cur = conn.execute(f"DELETE FROM {table} WHERE rowid IN ({','.join('?' * len(part))})", part)
            n += cur.rowcount or 0
    for rid, fill in games.get("fill") or []:
        cols = ", ".join(f"{c}=?" for c in fill)
        conn.execute(f"UPDATE games SET {cols} WHERE rowid=?", (*fill.values(), rid))
    conn.commit()
    return n


def seasons_of(conn) -> list:
    return [int(r[0]) for r in conn.execute(
        "SELECT DISTINCT season FROM player_game_logs WHERE sport='cfb' AND season IS NOT NULL "
        "ORDER BY season")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="College football's stored games and stat lines, one game once")
    ap.add_argument("--season", type=int, action="append", help="a season (repeatable); default every season")
    ap.add_argument("--apply", action="store_true", help="remove them (without it, nothing is written)")
    a = ap.parse_args(argv)
    from . import db
    conn = db.connect()
    removed = 0
    try:
        for season in (a.season or seasons_of(conn)):
            logs, games = plan_logs(conn, season), plan_games(conn, season)
            print(f"cfb {season}: {logs['rows']:,} stat rows, {logs['groups']:,} game(s) filed more than once, "
                  f"{len(logs['delete']):,} row(s) to remove; {logs['disagree']:,} where a box copy's number "
                  f"differs from the kept one; {games['pairs']:,} game(s) in the games table more than once, "
                  f"{len(games['delete']):,} row(s) to remove")
            for ex in logs["examples"]:
                print(f"    {ex}")
            if a.apply and (logs["delete"] or games["delete"]):
                removed += apply(conn, logs, games)
        if a.apply:
            try:
                from . import logcache
                logcache.forget("cfb")
            except Exception:                                 # noqa: BLE001
                pass
            print(f"removed {removed:,} row(s)")
        else:
            print("nothing written (add --apply to remove them)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
