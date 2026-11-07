#!/usr/bin/env python3
"""Backfill player faces into `player_assets` from ids we already hold.

    python3 facesfill.py               # every sport, report what filled
    python3 facesfill.py --sport nfl   # one sport (cfb: the charts' players)
    python3 facesfill.py --dry-run     # count what WOULD fill, write nothing
    python3 facesfill.py --check       # the charts' players with a face (read-only)

WHY INGEST CANNOT DO THIS. The photo URL is captured DURING ingest, and
ingest skips days it has already stored — that is what makes a six-season
backfill affordable. But it also means a player whose days were all stored
BEFORE faces existed can never pick one up: Ethan re-ran every ingest on
2026-08-18 and the WNBA count sat at 171/183 before and after, because not
one already-stored day was re-read. The fix is not to re-read seasons of
box scores for twelve faces; it is to fill from identifiers already in
hand, which is what this does:

* **NFL** — nflverse's roster file ships `headshot_url` per player (2,816
  of 2,930 on the 2026 roster). TAKEN, not guessed. This is also the sport
  where the gap bites hardest: the fantasy player profile reads
  `player_assets` for its face and NOTHING has ever written NFL rows to
  that table — the hoops ingest is its only writer.
* **MLB** — the league's active rosters carry a Stats API `person_id`, and
  the headshot URL is constructed from it (mlbstats.HEADSHOT — the same
  deliberate, probed pattern every MLB prop card has drawn with since the
  splits work).
* **NBA / WNBA** — rows already in `player_assets` that carry an
  `espn_id` but no photo get ESPN's by-id headshot path (probed by
  `assets.py`). Constructed, so it can be wrong — and a wrong image URL
  degrades to the initials chip the card is drawing today, not to a wrong
  face: the `<img>` removes itself on error. Rows that already have a
  photo are not touched.
* **The carry and route charts (NFL, college)** — Ethan, 2026-10-13:
  "Make sure we are showing headshots in this new page." The chart names
  a player the way its play file does, and every row carries the
  league's own id. A chart player with no face under that spelling gets
  one JOINED ON THE ID: the NFL roster file's photo for his gsis id
  (`nflverse.headshots_by_id`, the newest season he is on first), and in
  college ESPN's by-id path, which is the URL the college roster file
  itself hands over for every athlete (30,072 of 30,072 rows in 2025's).
  Only a name with no photo is touched, and a name shared by two ids is
  skipped — initials beat somebody else's face. Measured on this
  checkout's chart tables: 637 of 685 NFL chart players had a face by
  name from the 2026 roster; by id over the chart's seasons, 685.

Never fatal, feed by feed: no roster file means that sport reports zero
and the others still fill. Re-running is safe — `upsert_player_assets`
keys on (sport, player) and an empty value never clobbers a stored one.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from engine import db

#: ESPN's by-id headshot path for the hoops leagues — the pattern
#: `assets.py --probe` checks. Only used for rows that have no photo at
#: all, so a miss changes nothing on the card.
ESPN_HEADSHOT = "https://a.espncdn.com/i/headshots/{league}/players/full/{pid}.png"

#: The chart tables, and the leagues each one draws (engine/chartfill).
CHART_TABLES = {"nfl": ("carries", "targets"), "cfb": ("carries",)}


def _counts(conn, sport: str) -> tuple[int, int]:
    """(rows, rows with a photo) for one sport — the before/after number."""
    try:
        r = conn.execute(
            "SELECT COUNT(*), SUM(COALESCE(headshot,'') != '') "
            "FROM player_assets WHERE sport=?", (sport,)).fetchone()
        return int(r[0] or 0), int(r[1] or 0)
    except Exception:                                         # noqa: BLE001
        return 0, 0


def nfl_rows(season: int | None = None) -> list[dict]:
    """Every roster player with a face, in `player_assets` row shape.

    ``season`` defaults to the current year, falling back one year when
    that roster file is not published yet — in February the coming
    season's roster does not exist and last season's faces are the same
    people."""
    from engine.sources.nflverse import headshot_map
    year = season or dt.date.today().year
    faces = headshot_map(year) or (headshot_map(year - 1) if season is None
                                   else {})
    today = dt.date.today().isoformat()
    return [{"sport": "nfl", "player": name, "espn_id": "",
             "headshot": url, "seen": today}
            for name, url in faces.items() if url]


def mlb_rows() -> list[dict]:
    """Every active-roster player, face constructed from his person_id."""
    from engine.mlb.sources.mlbstats import fetch_active_rosters, headshot_url
    try:
        rosters = fetch_active_rosters() or {}
    except Exception:                                         # noqa: BLE001
        return []
    today = dt.date.today().isoformat()
    rows = []
    for players in rosters.values():
        for p in players or []:
            name, url = p.get("name") or "", headshot_url(p.get("person_id"))
            if name and url:
                rows.append({"sport": "mlb", "player": name,
                             "espn_id": str(p.get("person_id") or ""),
                             "headshot": url, "seen": today})
    return rows


def hoops_rows(conn, league: str) -> list[dict]:
    """Faceless rows that carry an espn_id, filled by ESPN's by-id path.

    Only the gap is touched: a photo the box score handed us is a TAKEN
    URL and strictly better than a constructed one, so it stays."""
    try:
        stored = conn.execute(
            "SELECT player, espn_id FROM player_assets WHERE sport=? "
            "AND COALESCE(espn_id,'') != '' AND COALESCE(headshot,'') = ''",
            (league,)).fetchall()
    except Exception:                                         # noqa: BLE001
        return []
    today = dt.date.today().isoformat()
    return [{"sport": league, "player": r[0], "espn_id": r[1],
             "headshot": ESPN_HEADSHOT.format(league=league, pid=r[1]),
             "seen": today}
            for r in stored]


def _faced(conn, sport: str) -> set:
    """Normalised names that already have a photo in `player_assets`."""
    from engine.rosters import _norm_key
    try:
        return {_norm_key(r[0]) for r in conn.execute(
            "SELECT player FROM player_assets WHERE sport=? "
            "AND COALESCE(headshot,'') != ''", (sport,))}
    except Exception:                                         # noqa: BLE001
        return set()


def chart_rows(conn, sport: str, have: set | None = None,
               by_id=None) -> list[dict]:
    """A face for every carry or route chart player who has none, joined
    on the league's id (see the header).

    ``have``: normalised names already faced beyond what the table holds
    (a dry run's roster rows). ``by_id(season)`` -> ``{gsis_id: url}``, the
    NFL's roster faces; `nflverse.headshots_by_id` unless a test hands one
    in. College needs no file: the id is the path."""
    from engine.rosters import _norm_key
    tables = CHART_TABLES.get(sport)
    if not tables:
        return []
    seen: dict = {}
    try:
        for t in tables:
            for name, pid, season in conn.execute(
                    f"SELECT player, player_id, MAX(season) FROM {t} WHERE sport=? "
                    f"AND COALESCE(player_id,'') != '' GROUP BY player, player_id", (sport,)):
                ids = seen.setdefault(name, {})
                ids[pid] = max(int(season or 0), ids.get(pid, 0))
    except Exception:                                         # noqa: BLE001
        return []                      # a database with no chart tables yet
    faced = _faced(conn, sport) | set(have or ())
    # One id per name, or nothing: two men sharing a spelling would get
    # one of their faces at random.
    want = {n: next(iter(ids.items())) for n, ids in seen.items()
            if n and len(ids) == 1 and _norm_key(n) not in faced}
    if not want:
        return []
    if sport == "cfb":
        def face(pid, _season):
            return ESPN_HEADSHOT.format(league="college-football", pid=pid)
    else:
        if by_id is None:
            from engine.sources.nflverse import headshots_by_id as by_id
        newest = max(s for ids in seen.values() for s in ids.values())
        files: dict = {}

        def face(pid, season):
            # This season's file first — a photo is retaken every summer —
            # then the last season he played and the one before it.
            for s in dict.fromkeys((newest, season, season - 1)):
                if s not in files:
                    files[s] = by_id(s) or {}
                if files[s].get(pid):
                    return files[s][pid]
            return ""
    today = dt.date.today().isoformat()
    rows = []
    for name, (pid, season) in sorted(want.items()):
        url = face(pid, season)
        if url:
            rows.append({"sport": sport, "player": name,
                         "espn_id": pid if sport == "cfb" else "",
                         "headshot": url, "seen": today})
    return rows


def chart_coverage(conn, sport: str) -> tuple[int, int, list]:
    """(chart players with a face, chart players, the names without one) —
    read the way the chart reads it (statlogs.face). Read-only."""
    from engine import statlogs
    names: set = set()
    try:
        for t in CHART_TABLES.get(sport, ()):
            names |= {r[0] for r in conn.execute(
                f"SELECT DISTINCT player FROM {t} WHERE sport=?", (sport,)) if r[0]}
    except Exception:                                         # noqa: BLE001
        return 0, 0, []
    miss = sorted(n for n in names if not statlogs.face(conn, sport, n))
    return len(names) - len(miss), len(names), miss


def fill(conn, sport: str, dry_run: bool = False,
         season: int | None = None) -> tuple[int, int, int]:
    """Backfill one sport; returns (candidates, photos before, after)."""
    if sport == "nfl":
        rows = nfl_rows(season)
    elif sport == "mlb":
        rows = mlb_rows()
    elif sport in ("nba", "wnba"):
        rows = hoops_rows(conn, sport)
    else:
        rows = []
    _, before = _counts(conn, sport)
    if rows and not dry_run:
        db.upsert_player_assets(conn, rows)
        conn.commit()
    # The charts' players second, so a face the roster just wrote is
    # never written twice under another spelling.
    from engine.rosters import _norm_key
    extra = chart_rows(conn, sport, have={_norm_key(r["player"]) for r in rows}
                       if dry_run else None)
    if extra and not dry_run:
        db.upsert_player_assets(conn, extra)
        conn.commit()
    _, after = _counts(conn, sport)
    return len(rows) + len(extra), before, after


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", default=str(db.DEFAULT_DB))
    p.add_argument("--sport", default="",
                   help="one of nfl, mlb, nba, wnba, cfb (default: all five)")
    p.add_argument("--season", type=int, default=None,
                   help="NFL roster season (default: this year, falling "
                        "back one)")
    p.add_argument("--dry-run", action="store_true",
                   help="report what would fill; write nothing")
    p.add_argument("--check", action="store_true",
                   help="how many carry and route chart players have a face "
                        "(read-only)")
    a = p.parse_args(argv)

    if a.check:
        conn = db.connect(a.db)
        for sport in CHART_TABLES:
            have, total, miss = chart_coverage(conn, sport)
            print(f"  {sport.upper():<5} {have} of {total} chart players have a "
                  f"face" + (f"; none for: {', '.join(miss[:10])}" if miss else ""))
        return 0

    sports = [a.sport.lower()] if a.sport else ["nfl", "mlb", "nba", "wnba", "cfb"]
    conn = db.connect(a.db)
    print("faces backfill — filling player_assets from ids already in hand"
          + ("  (DRY RUN)" if a.dry_run else ""))
    for sport in sports:
        n, before, after = fill(conn, sport, dry_run=a.dry_run,
                                season=a.season)
        total, _ = _counts(conn, sport)
        if a.dry_run:
            print(f"  {sport.upper():<5} {n} candidate face(s); "
                  f"{before} of {total} rows currently have one")
        else:
            print(f"  {sport.upper():<5} {n} candidate face(s); photos "
                  f"{before} -> {after}"
                  + ("" if n else "   (no source answered — see the header)"))
    print("\nDone. The board reads these on the next build; nothing else "
          "to run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
