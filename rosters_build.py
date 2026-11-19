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
import os
from pathlib import Path

from engine import rosters as _r
from engine.db import connect
from engine.seasons import season_of

# Every sport this script can build, and what to say when a sport has no
# roster source at all. MLB, both colleges and the LIVE_FEEDS leagues reach
# a published roster first and fall back to appearances (basketball counts
# a minute played, so anyone who got off the bench is on that page).
FROM_LOGS = ("mlb", "nba", "wnba", "cfb", "nhl", "cbb")
#: A league as the page names it, where that is not its code in capitals
#: (the strip's NCAAB; web/js/app.js LEAGUE_LABEL).
LEAGUE_NAME = {"cbb": "NCAAB"}

#: The league's current roster first (2026-10-03, Ethan: "make sure we're
#: pulling all live data for NHL, like all live rosters and injuries ... I
#: want every single sport to have the same thing"): the NHL's own feed
#: for hockey, ESPN's per-club rosters for basketball. Appearances stay the
#: fallback and still fill the games column.
LIVE_FEEDS = ("nhl", "nba", "wnba")
#: A man counts as appearing in a game through these markets.
GAME_MARKETS = {"nhl": ("toi",), "nba": ("min",), "wnba": ("min",), "cbb": ("min",)}
NO_SOURCE = {
    "ufc": "MMA has fighters, not rosters. Each fighter's measured record "
           "lives in a dossier on the UFC card itself.",
}

#: What an appearance-built page cannot see, per sport. Said out loud on
#: the page whenever the feed fails and the fallback runs.
BLIND_SPOT = {
    "mlb": "every pitcher, because pitchers don't bat and an appearance "
           "here is a plate appearance,",
    "cfb": "every lineman, defender, kicker and backup, because an "
           "appearance here is a carry, a catch or a pass,",
    "cbb": "every walk-on who has not played a minute,",
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
    if sport == "cbb":
        # COLLEGE BASKETBALL'S PUBLISHED ROSTERS (2026-11-19). Ethan, asked
        # whether college players should show their real positions: "I would
        # assume so. Yeah." This page and the player search were built from
        # appearances, so a school's roster was whoever had played and every
        # position was the box score's starter or bench mark: the search
        # called both Boozers "S". ESPN publishes each school's roster (guard,
        # forward, center, number, height) on the host the scoreboards come
        # from, read by the ids those scoreboards taught us (cbbteams.load_ids):
        # one request a school on a day's cache, CBB_ROSTER_NEW of them a
        # build, so a cold morning never holds the roster step past its three
        # minutes. A school not read yet keeps its appearance rows.
        try:
            feed, missed = _cbb_feed()
            if feed:
                games = _r.games_by_player(conn, sport, GAME_MARKETS[sport], seasons=[season, season - 1])
                out = _r.feed_rosters(sport, feed, games, faces=_r._faces(conn, sport),
                                      injuries=_injury_board(sport), today=day)
                base = _r.from_game_logs(conn, sport, seasons=[season], today=day)
                for code, team in (base.get("teams") or {}).items():
                    out["teams"].setdefault(code, team)
                out["team_count"] = len(out["teams"])
                out["player_count"] = sum(t["count"] for t in out["teams"].values())
                out.update({
                    "sport": sport, "season": season,
                    "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                    "feed": "live", "source": "roster",
                    # The schools still on appearances say so as a count, not
                    # as a page of names: most are waiting on the next build.
                    "rosters_read": len(feed),
                    "note": "" if not missed else (
                        f"{len(missed)} school roster{'s' if len(missed) != 1 else ''} not read yet show who has "
                        f"played, without positions, until the next build reads them."),
                })
                return out
            feed_err = "no school roster would load"
        except Exception as exc:                   # noqa: BLE001
            feed_err = f"the roster feed failed ({type(exc).__name__}: {exc})"
    if sport in LIVE_FEEDS:
        try:
            feed, missed = _league_feed(sport)
            injuries = _injury_board(sport)
            games = _r.games_by_player(conn, sport, GAME_MARKETS[sport],
                                       seasons=[season, season - 1])
            out = _r.feed_rosters(sport, feed, games, faces=_r._faces(conn, sport),
                                  injuries=injuries, today=day)
            if out["player_count"]:
                out.update({
                    "sport": sport, "season": season,
                    "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                    "feed": "live", "source": "league" if sport == "nhl" else "roster",
                    "note": "" if not missed else (
                        f"{len(missed)} club rosters would not load and are missing "
                        f"from this page: {', '.join(sorted(missed))}"),
                })
                return out
            feed_err = "the roster feed returned no players"
        except Exception as exc:                   # noqa: BLE001
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
            f"No {LEAGUE_NAME.get(sport, sport.upper())} game logs on file. Rosters here are built "
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


#: College basketball's rosters: read once a day a school, and at most this
#: many schools asked for afresh a build (the rest from the day's cache, or
#: the next build half an hour on): 365 at once would hold the roster step,
#: every league's, past its three minutes.
CBB_ROSTER_TTL = 24 * 3600
CBB_ROSTER_NEW = 60


def _cbb_feed(ids: dict | None = None, budget: int = CBB_ROSTER_NEW, fetch=None) -> tuple[dict, list]:
    """``({school code: [people]}, [codes not read this build])`` from ESPN's
    rosters, by the Division I ids the scoreboards have named. A school whose
    file is past its day and over this build's budget is read from the file
    it has (a roster changes slowly); one never read waits for the next."""
    import time as _time
    from engine import cbbteams
    from engine.sources import espnrosters
    from engine.sources.fetch import DEFAULT_AGENT, DataUnavailable, _cache_path, fetch_json
    if ids is None:
        ids = {code: eid for eid, code in cbbteams.load_ids().items() if code and eid}
    get = fetch or (lambda url, name: fetch_json(url, name, ttl=CBB_ROSTER_TTL, user_agent=DEFAULT_AGENT))
    left = [int(budget)]

    def one(url, name):
        path = _cache_path(name)
        if path.exists() and _time.time() - path.stat().st_mtime < CBB_ROSTER_TTL:
            return get(url, name)
        if left[0] > 0:
            left[0] -= 1
            return get(url, name)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                pass
        raise DataUnavailable(f"{name} waits for the next build")
    return espnrosters.fetch_league("cbb", team_ids=ids, fetch=one)


def _league_feed(sport: str) -> tuple[dict, list]:
    """``({team: [people]}, [teams that would not load])`` — the league's
    own current rosters, normalised to one person shape."""
    if sport == "nhl":
        from engine.sources import nhldata
        feed, missed = nhldata.fetch_league_rosters()
        return ({t: [dict(p, player=p["name"]) for p in people] for t, people in feed.items()},
                missed)
    from engine.sources import espnrosters
    return espnrosters.fetch_league(sport)


def _injury_board(sport: str) -> dict:
    """``{player: {status, injury}}`` off the injury board this site already
    publishes (web/data/injuries.json), or {} — a roster never waits on it."""
    try:
        blob = json.loads((OUT_DIR / "injuries.json").read_text())
    except (OSError, ValueError):
        return {}
    return {r["player"]: {"status": r.get("status") or "", "injury": r.get("injury") or ""}
            for r in ((blob.get("sports") or {}).get(sport) or [])
            if isinstance(r, dict) and r.get("player")}


#: The leagues whose roster rows carry a field only when it says something
#: (2026-11-03). College's file held 41,878 players across 492 schools at
#: 13.3 MB, most of every row an empty status, a false flag or a null; the
#: Rosters page and the player search parse all of it on the phone, and
#: since 3 November a free account opens it too. Without the empties it is
#: about 5.6 MB. Every reader takes a missing field as empty: the page
#: tests flags by truth and numbers with `!= null`, and the Python readers
#: use `.get` (tests/test_the_college_rosters_are_slim.py holds both).
SLIM_SPORTS = ("cfb", "cbb")

#: Kept on every row, empty or not: who, where, and what position.
ALWAYS_KEPT = ("player", "team", "position")


def _empty(v) -> bool:
    """None, False or "" — never a 0, which is a value (a jersey, a rookie's
    years of experience)."""
    return v is None or v is False or (isinstance(v, str) and v == "")


def slim_rows(blob: dict) -> dict:
    """Each player row without its empty fields, and without a depth-chart
    position that only repeats his position. In place; returns ``blob``."""
    for team in (blob.get("teams") or {}).values():
        if not isinstance(team, dict):
            continue
        rows = []
        for p in team.get("players") or []:
            if isinstance(p, dict):
                p = {k: v for k, v in p.items() if k in ALWAYS_KEPT or not _empty(v)}
                if p.get("depth_pos") == p.get("position"):
                    p.pop("depth_pos", None)
            rows.append(p)
        team["players"] = rows
    return blob


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
    if sport in SLIM_SPORTS:
        slim_rows(blob)
    # Atomic (audit F-12): a poll mid-write must never read half a file.
    dest = out_dir / f"rosters_{sport}.json"
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    # COMPACT (the speed pass, 2026-10-09): the college file was 22.6 MB,
    # two spaces of indentation on every line of it. Readers parse it the
    # same; the phone downloads and parses roughly 40% less.
    tmp.write_text(json.dumps(blob, separators=(",", ":")))
    os.replace(tmp, dest)
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
