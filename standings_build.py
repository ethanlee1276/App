#!/usr/bin/env python3
"""Per-sport standings + postseason bracket → web/data/standings_<sport>.json.

Both come out of the games table this site already fills, so they cannot
disagree with the boards beside them: a record here and a record on a
matchup card are the same rows counted twice.

Two things are kept separate on purpose. The STANDINGS are regular season
only — counting playoff results there showed a 14-3 team as 17-4 and gave
almost every club a losing streak, because the last thing most teams do is
lose a playoff game. The BRACKET is postseason only, drawn from games that
were actually played, and it stays empty until they are.

Usage:
    python3 standings_build.py
    python3 standings_build.py --sport nba --season 2025
"""

from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

from engine import playoffs, standings
from engine.db import connect
from engine.seasons import season_of

SPORTS = ("nfl", "mlb", "nba", "wnba", "cfb")
OUT_DIR = Path("web/data")


def cfb_conferences() -> dict:
    """``{team: conference}`` from the college slate the site just built.

    134 programs realigning every summer is not a static fact, so it is
    read from the payload rather than kept in a table that is wrong by
    September. A missing slate simply means no conference grouping — the
    standings still render, under one heading.
    """
    p = OUT_DIR / "cfb_recommendations.json"
    try:
        blob = json.loads(p.read_text())
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    for g in blob.get("games") or []:
        for side in ("home", "away"):
            team = g.get(side)
            conf = g.get(f"{side}_conference") or g.get(f"{side}_conf")
            if team and conf:
                out[team] = conf
    return out


def build(sport: str, season: int | None = None,
          today: str | None = None) -> dict:
    day = today or datetime.date.today().isoformat()
    season = season if season is not None else season_of(sport, day)
    conn = connect()
    try:
        confs = cfb_conferences() if sport == "cfb" else None
        table = standings.compute(conn, sport, season=season, today=day,
                                  conferences=confs)
        bracket = playoffs.bracket(conn, sport, season=season, today=day)
    finally:
        conn.close()

    teams = sum(len(g["teams"]) for g in table["groups"])
    table["bracket"] = bracket
    # A projected seeding is worth showing and worth labelling. It is not
    # the bracket — it is what the bracket WOULD be, and the page has to
    # be able to tell the two apart at a glance.
    table["projected_seeds"] = (
        [] if bracket["started"] or not teams
        else standings.conference_seeds(table))
    table["team_count"] = teams
    table["note"] = "" if teams else _empty_note(sport, season, day)
    return table


def _empty_note(sport: str, season: int, day: str) -> str:
    """Why the table is empty — and only offer an ingest that can work.

    "Run the ingest" is the wrong advice for a season nobody has played
    yet. It would download nothing, exit clean, and leave you assuming
    something is broken.
    """
    from engine.seasons import window
    try:
        start, _end = window(sport, season)
    except ValueError:
        start = ""
    if start and day < start:
        return (f"The {season} {sport.upper()} season has not started yet — "
                f"first games {start}. Standings count our own results, so "
                f"this table fills itself in as the season is played.")
    return (f"No finished {sport.upper()} games on file for {season}. "
            f"Standings are counted from our own results: "
            f"python3 ingest.py {sport} --seasons {season}")


def write(sport: str, out_dir: Path = OUT_DIR, season: int | None = None,
          today: str | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    blob = build(sport, season, today)
    (out_dir / f"standings_{sport}.json").write_text(json.dumps(blob, indent=2))
    return blob


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default="", help="one sport (default: all)")
    ap.add_argument("--season", type=int, default=None)
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args()

    for sport in ([args.sport] if args.sport else SPORTS):
        b = write(sport, Path(args.out), args.season)
        bits = [f"{b['team_count']} teams", f"{b['games_counted']} games",
                f"season {b['season']}"]
        if b["bracket"]["started"]:
            bits.append(f"bracket: {len(b['bracket']['rounds'])} round(s)")
        print(f"Standings {sport.upper()}: " + ", ".join(bits)
              + (f" — {b['note']}" if b["note"] else ""))


if __name__ == "__main__":
    main()
