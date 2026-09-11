#!/usr/bin/env python3
"""Backfill player faces into `player_assets` from ids we already hold.

    python3 facesfill.py               # every sport, report what filled
    python3 facesfill.py --sport nfl   # one sport
    python3 facesfill.py --dry-run     # count what WOULD fill, write nothing

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
    _, after = _counts(conn, sport)
    return len(rows), before, after


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", default=str(db.DEFAULT_DB))
    p.add_argument("--sport", default="",
                   help="one of nfl, mlb, nba, wnba (default: all four)")
    p.add_argument("--season", type=int, default=None,
                   help="NFL roster season (default: this year, falling "
                        "back one)")
    p.add_argument("--dry-run", action="store_true",
                   help="report what would fill; write nothing")
    a = p.parse_args(argv)

    sports = [a.sport.lower()] if a.sport else ["nfl", "mlb", "nba", "wnba"]
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
