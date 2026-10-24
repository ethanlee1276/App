"""Who refereed each game — a data source the site never read, kept for the day it can be tested.

Ethan, 2026-10-17: "new ways of gathering data". The game summary the
basketball ingest already downloads for every final names its officials
(`gameInfo.officials`). This keeps them, one row per official per game, so
the question refcheck.py answered for the NFL — does a crew's past predict
a game against the CLOSING total? (no, on 7,340 games) — can be asked of
the NBA and the WNBA once a season of their closing totals is stored
(engine/lineopen keeps them since September). Nothing here moves a number.

COST: none. `store` runs inside the ingest on the summary it has in hand;
`backfill` reads summaries already in the cache (any age — a final's
summary never changes) and never fetches.

Standard library only.
"""
from __future__ import annotations

import json
import os

#: The leagues whose ingest hands a summary over (engine/sources/espnhoops).
LEAGUES = ("nba", "wnba")


def parse(summary: dict) -> list[dict]:
    """``[{"name", "role"}]`` from a summary's officials, in their order.

    Read by key name and tolerant of either spelling ESPN uses for a name;
    an entry with no name is skipped, a missing list is an empty answer."""
    info = (summary or {}).get("gameInfo") or {}
    raw = info.get("officials") or (summary or {}).get("officials") or []
    out, seen = [], set()
    for o in raw if isinstance(raw, list) else []:
        if not isinstance(o, dict):
            continue
        name = str(o.get("fullName") or o.get("displayName") or o.get("name") or "").strip()
        if not name or len(name) > 60 or name in seen:
            continue
        pos = o.get("position") or {}
        role = str((pos.get("displayName") or pos.get("name")) if isinstance(pos, dict) else pos or "").strip()
        out.append({"name": name, "role": role[:30]})
        seen.add(name)
    return out


def store(conn, sport: str, game_id, date: str, officials: list[dict]) -> int:
    """Upsert one game's crew; the number of rows written."""
    rows = [(sport, str(game_id), str(date)[:10], o["name"], o.get("role", "")) for o in officials or []]
    if not rows:
        return 0
    conn.executemany("INSERT OR REPLACE INTO game_officials (sport, game_id, date, name, role) "
                     "VALUES (?, ?, ?, ?, ?)", rows)
    return len(rows)


def crew(conn, sport: str, game_id) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT name FROM game_officials WHERE sport=? AND game_id=? ORDER BY rowid",
        (sport, str(game_id)))]


def backfill(conn, league: str, cache_dir=None, limit: int | None = None) -> dict:
    """Officials for every stored final whose summary is already in the
    cache and whose crew is not stored yet. Never fetches."""
    from .sources.fetch import CACHE_DIR
    base = str(cache_dir or CACHE_DIR)
    have = {r[0] for r in conn.execute("SELECT DISTINCT game_id FROM game_officials WHERE sport=?", (league,))}
    todo = [(str(g), str(d)) for g, d in conn.execute(
        "SELECT game_id, date FROM games WHERE sport=? AND home_score IS NOT NULL", (league,))
            if str(g) not in have]
    if limit:
        todo = todo[:limit]
    games = rows = missing = 0
    for gid, date in todo:
        path = os.path.join(base, f"espn_{league}_box_{gid}.json")
        try:
            with open(path, encoding="utf-8") as fh:
                summary = json.load(fh)
        except (OSError, ValueError):
            missing += 1
            continue
        n = store(conn, league, gid, date, parse(summary))
        games += bool(n)
        rows += n
    conn.commit()
    return {"games": games, "rows": rows, "not_cached": missing, "todo": len(todo)}


def summary(conn, league: str, top: int = 10) -> dict:
    """How many games carry a crew, and the officials seen most."""
    n = conn.execute("SELECT COUNT(DISTINCT game_id) FROM game_officials WHERE sport=?", (league,)).fetchone()[0]
    most = conn.execute("SELECT name, COUNT(*) c FROM game_officials WHERE sport=? GROUP BY name "
                        "ORDER BY c DESC, name LIMIT ?", (league, top)).fetchall()
    return {"games": n, "most": [(r[0], r[1]) for r in most]}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Game officials: fill from the cached summaries, then count")
    ap.add_argument("--league", default="nba", choices=LEAGUES)
    ap.add_argument("--backfill", action="store_true", help="read crews out of summaries already cached")
    a = ap.parse_args(argv)
    from . import db
    conn = db.connect()
    if a.backfill:
        r = backfill(conn, a.league)
        print(f"  {a.league}: {r['games']:,} games given their crew ({r['rows']:,} rows); "
              f"{r['not_cached']:,} of {r['todo']:,} had no cached summary")
    s = summary(conn, a.league)
    print(f"  {a.league}: {s['games']:,} games carry their officials")
    for name, c in s["most"]:
        print(f"    {name:<28} {c:>4} games")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
