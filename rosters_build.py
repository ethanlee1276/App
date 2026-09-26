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
* **CFB** — ESPN's published per-school roster, one keyless request per
  team on a day's cache, since 2026-09-19. It was built from appearances
  too, and for college that was badly wrong: the appearance markets are
  ``pass_yds``, ``carries`` and ``receptions``, so a page claiming to be
  a roster listed only the men who touched the ball. Appearances remain
  the fallback and still fill the games column.

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

# Every sport this script can build, and what to say when a sport has no
# roster source at all. MLB and CFB reach a published roster first and
# fall back to appearances; NBA and WNBA are appearance-built outright,
# where it costs far less — basketball counts a minute played, so anyone
# who got off the bench is on the page.
FROM_LOGS = ("mlb", "nba", "wnba", "cfb")
NO_SOURCE = {
    "ufc": "MMA has fighters, not rosters. Each fighter's measured record "
           "lives in his dossier on the UFC card itself.",
}

#: What an appearance-built page cannot see, per sport. Said out loud on
#: the page whenever the feed fails and the fallback runs.
BLIND_SPOT = {
    "mlb": "every pitcher, because pitchers don't bat and an appearance "
           "here is a plate appearance,",
    "cfb": "every lineman, defender, kicker and backup, because an "
           "appearance here is a carry, a catch or a pass,",
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
                feed, _r.mlb_games_by_player(conn, seasons=[season]),
                # Faces the ingest already stored, joined on the normalised
                # name — see engine/rosters._faces for why the exact string
                # is the wrong key.
                faces=_r._faces(conn, "mlb"))
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
    if sport == "cfb":
        # ESPN's published rosters, one keyless request per school on a
        # day's cache — and the slate has already paid for most of them.
        #
        # Ethan, 2026-09-19: "a lot of CFB player dont show up in the
        # player search." The appearance list below answers "who is on
        # this team" with "who produced a counted stat in a game we
        # ingested", and for college that is pass_yds, carries and
        # receptions ONLY. Every lineman, defender, kicker and backup was
        # missing — from this page, and from the player search, which
        # reads the same population. 5,522 names on this box against a
        # league of roughly fifteen thousand.
        try:
            from engine.sources import cfbdata
            ids = {ab: t.get("id") for ab, t in
                   cfbdata.parse_teams(cfbdata.fetch_teams()).items()}
            feed, missed = cfbdata.fetch_people(ids)
            out = _r.cfb_feed_rosters(
                feed, _r.cfb_games_by_player(conn, seasons=[season]),
                faces=_r._faces(conn, "cfb"))
            if out["player_count"]:
                out.update({
                    "sport": sport, "season": season,
                    "generated_at": datetime.datetime.now()
                    .isoformat(timespec="seconds"),
                    "feed": "live", "source": "roster",
                    # A build that published 110 of 134 schools looks
                    # exactly like one that published them all, so the
                    # shortfall is on the page rather than in a log line
                    # nobody reads.
                    "note": "" if not missed else (
                        f"{len(missed)} school rosters would not load and "
                        f"are missing from this page: "
                        f"{', '.join(sorted(missed)[:12])}"
                        + (" …" if len(missed) > 12 else "")),
                })
                return out
            feed_err = "no school roster would load"
        except Exception as exc:                   # noqa: BLE001
            # Same rule as the baseball path above: fall back, carry the
            # reason. A silent fall-back here would put the page straight
            # back into the state Ethan reported and say nothing.
            feed_err = f"the roster feed failed ({type(exc).__name__}: {exc})"
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
        # Appearance mode has a known blind spot, and the page must own
        # it: these men are absent HERE, not from the team. The sentence
        # is per sport because the blind spots are different ones, and
        # telling a college reader that pitchers do not bat would be a
        # confident explanation of the wrong absence.
        out["note"] = (f"Built from appearances because {feed_err} — "
                       f"{BLIND_SPOT.get(sport, 'anyone who has not played')} "
                       f"is missing from this view until the feed recovers. "
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
    # THE COLLEGE LOGOS NEED AN ID THE ROSTER PAGE DID NOT HAVE. ESPN keys
    # its 134 schools numerically, so `logoUrl` draws a college mark only
    # when the team record carries an `id` — and the front end reads
    # college team records off the BOARD payload (`_cfbTeams`), which a
    # reader who opens Rosters first has never loaded. Every college
    # roster header therefore drew the monogram. Ethan, 2026-09-14: "We
    # should be showing your team logos on the team roster." The same
    # cached teams feed the board uses rides here, keyed by abbreviation,
    # so the page can draw the mark from its own payload. Absent on a
    # feed failure, and the page falls back to exactly what it drew before.
    if sport == "cfb":
        try:
            from engine.sources import cfbdata
            blob["team_meta"] = cfbdata.parse_teams(cfbdata.fetch_teams())
        except Exception:                                     # noqa: BLE001
            blob["team_meta"] = {}
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
