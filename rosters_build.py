#!/usr/bin/env python3
"""Per-sport roster payloads → web/data/rosters_<sport>.json.

Rosters used to be one page that only ever meant the NFL, sitting in the
tools menu next to Polymarket. That was wrong twice over: a roster belongs
to a league, and "who is on this team" is a question you ask *while*
looking at that league's board, not after navigating away from it. Each
sport now owns its own roster tab.

Where each sport's answer comes from:

* **NFL** — the published players file the fantasy layer already fetches,
  with real depth-chart order and injury status. Written by
  ``fantasy_build.py``, which has the blob in memory already.
* **MLB / NBA / WNBA** — our own ingested game logs. Who actually appeared
  for a team, how many times, and how recently. Not a copy of somebody's
  roster page: a record of who played, which is closer to the question a
  bettor is asking, and it refreshes with the same nightly ingest that
  feeds the models.
* **CFB** — nothing. 134 programs and no player-level feed, so the page
  says so instead of rendering an empty grid that looks like a bug.

Usage:
    python3 rosters_build.py                 # every sport we can build
    python3 rosters_build.py --sport mlb
"""

from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

from engine import rosters as _r
from engine.db import connect
from engine.seasons import season_of

# Sports built from our own game logs, and what to say when a sport has
# no roster source at all.
FROM_LOGS = ("mlb", "nba", "wnba")
NO_SOURCE = {
    "cfb": "College football has no free player-level roster feed, and 134 "
           "programs of guessed depth charts would be worse than none. The "
           "CFB model is a team model — it never needs a roster to price a "
           "game.",
    "ufc": "MMA has fighters, not rosters. Each fighter's measured record "
           "lives in his dossier on the UFC card itself.",
}

OUT_DIR = Path("web/data")


def payload_for(conn, sport: str, today: str | None = None) -> dict:
    day = today or datetime.date.today().isoformat()
    season = season_of(sport, day)
    feed_err = ""
    if sport == "mlb":
        # The league's own active rosters, one keyless request for all
        # thirty clubs, six-hour cache. The appearance-built page below
        # stays as the FALLBACK — it answered "who is on the team" with
        # "who has batted in our logs", which meant a trade-deadline
        # pitcher was invisible twice over: pitchers never bat (no pa
        # rows), and a new arrival has no appearances for his new club
        # until he plays AND we ingest it.
        try:
            from engine.mlb.sources.mlbstats import fetch_active_rosters
            feed = fetch_active_rosters()
            out = _r.mlb_feed_rosters(
                feed, _r.mlb_games_by_player(conn, seasons=[season]))
            if out["player_count"]:
                out.update({
                    "sport": sport, "season": season,
                    "generated_at": datetime.datetime.now()
                    .isoformat(timespec="seconds"),
                    "feed": "live", "source": "league",
                    "note": "",
                })
                return out
            feed_err = "the league feed returned no players"
        except Exception as exc:                   # noqa: BLE001
            # Fall back to appearances — but CARRY THE REASON. Swallowing
            # it here is how the page ran pitcher-less for days while the
            # build printed success: nothing anywhere said the feed had
            # failed, or why.
            feed_err = f"the league feed failed ({type(exc).__name__}: {exc})"
    # This season, falling back to last: in the first weeks of a year the
    # current season has barely any appearances on file, and an empty
    # roster page is worse than a slightly stale one that says its date.
    out = _r.from_game_logs(conn, sport, seasons=[season], today=day)
    used = season
    if out["player_count"] == 0:
        out = _r.from_game_logs(conn, sport, seasons=[season - 1], today=day)
        used = season - 1
    out.update({
        "sport": sport,
        "season": used,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "feed": "live" if out["player_count"] else "empty",
        "source": "appearances",
        # The command names the CURRENT season, not the one the fallback
        # happened to land on — telling somebody to ingest last year to fix
        # an empty page this year is advice that cannot work.
        "note": "" if out["player_count"] else (
            f"No {sport.upper()} game logs on file. Rosters here are built "
            f"from who actually appeared, so they fill in with the history "
            f"ingest: python3 ingest.py {sport} --seasons {season}"),
    })
    if out["player_count"] and used != season:
        out["note"] = (f"Showing the {used} season — no {season} appearances "
                       f"on file yet. It updates itself once games are played "
                       f"and ingested.")
    if feed_err:
        # Appearance mode has a known blind spot, and the page must own it:
        # pitchers never bat, so they are absent HERE, not from the team.
        out["note"] = (f"Built from appearances because {feed_err} — "
                       f"pitchers don't bat, so they are missing from this "
                       f"view until the league feed recovers. "
                       + (out["note"] or "")).strip()
    return out


def unavailable_payload(sport: str) -> dict:
    return {
        "sport": sport, "teams": {}, "team_count": 0, "player_count": 0,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "feed": "none", "source": "",
        "note": NO_SOURCE.get(sport, "No roster source for this sport."),
    }


def write(sport: str, out_dir: Path = OUT_DIR, today: str | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    if sport in NO_SOURCE:
        blob = unavailable_payload(sport)
    else:
        conn = connect()
        try:
            blob = payload_for(conn, sport, today)
        finally:
            conn.close()
    (out_dir / f"rosters_{sport}.json").write_text(json.dumps(blob, indent=2))
    return blob


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default="", help="one sport (default: all)")
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args()

    sports = [args.sport] if args.sport else list(FROM_LOGS) + list(NO_SOURCE)
    for sport in sports:
        blob = write(sport, Path(args.out))
        if blob["feed"] == "none":
            print(f"Rosters {sport.upper()}: no source — page explains why.")
        else:
            # Name the source the payload ACTUALLY used — "from appearances"
            # printed over a league-feed build hides the one fact this line
            # exists to report: whether the trade-deadline fix is live.
            print(f"Rosters {sport.upper()}: {blob['team_count']} teams, "
                  f"{blob['player_count']:,} players "
                  f"(season {blob.get('season')}, from {blob['source']})"
                  + (f" — {blob['note']}" if blob["note"] else ""))


if __name__ == "__main__":
    main()
