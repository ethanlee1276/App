#!/usr/bin/env python3
"""Live NFL, CFB, NBA and WNBA scores → web/data/live_{league}.json.

    python3 livescore_build.py
    python3 livescore_build.py --league cfb

THE GAP THIS CLOSES, named by `live_build.py`'s own docstring on the day
it shipped: "MLB, NFL, NBA, WNBA and CFB never got the same treatment."

That file exists because live MLB scores were read out of
`data/mlb_recommendations.json` — 8MB, 923 props, seven minutes thirty-nine
seconds to build — so a score that changes every pitch waited on the whole
model and the site showed games 8-15 minutes behind. Nothing was broken; it
was wired to the wrong file.

MLB got its own fast clock. The other four did not, and `app.js`'s
LIVE_FEEDS still points them at the model boards: NFL at
`data/recommendations.json`, CFB at `data/cfb.json`, NBA and WNBA at
theirs. Same bug, four leagues, still live. NFL is the worse of the two
footballs because it at least CALLS `livescores.attach_live` — inside
nfl_build, behind the whole board. College never called it at all, so its
live scores are whatever the last slate build happened to record.

WHAT THIS COSTS. One request per league per poll, cached 30 seconds by
`fetch_text`, and ZERO odds credits — ESPN's scoreboard is keyless. Four
requests where the alternative is four model builds.

WHAT THIS DELIBERATELY DOES NOT CARRY, copied from live_build.py because
the reasoning is the same: no props, no prices, no edges. Scores and game
state only. That keeps it cheap and keeps it out of the paywall's way — a
score is a public fact and `engine/gate.py` has no reason to redact one.
The odds grid and the live win-probability track still come from the model
board, where they belong and where their latency does not matter; the
front end MERGES the two rather than replacing one with the other.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import time as _time
from pathlib import Path

from engine.sources.fetch import DataUnavailable
from engine.sources.livescores import ESPN_SCOREBOARD, fetch_rows

#: Cached for the launcher's fast cadence. Shorter than this buys nothing
#: — `LIVE_FAST_S` is 12 seconds and the scoreboard does not move faster
#: than the clock on the screen.
TTL = 20

#: Plays on a card: about one drive's worth.
PLAYS_PER_GAME = 6

#: The most football games one pass will fetch a summary for. A college
#: Saturday can have thirty in progress at once, a summary is a few
#: hundred kilobytes, and this box OOM-killed seven test children on
#: 2026-09-04 with nothing else unusual running. Eight summaries every
#: thirty seconds is affordable; thirty is not. Past the cap a game keeps
#: its score and loses only its plays, and the note SAYS SO — an empty
#: strip because the budget ran out and one because the game has not
#: kicked off are different facts. Scoreboard order, which is kickoff
#: order: the earliest games are the ones deepest into their drives.
PLAYS_MAX_GAMES = 8

OUT = Path("web/data")

#: Where one game's WHOLE play-by-play lives: `web/data/pbp/{league}_
#: {event}.json`, one file per live game, written on the same pass that
#: puts the last six plays on the card. Ethan, 2026-09-05: "You should be
#: able to click on each live game and see a deeper play by play." The
#: card's strip stays six plays because the fast file is polled every
#: twelve seconds by every open tab; a game's full list — 392 plays on a
#: finished WNBA game — is fetched only by a reader who opened that game.
#: Free files, like the scoreboards: scores and plays are public facts,
#: nothing priced (engine/gate.FREE_DIRS).
PBP_DIR = OUT / "pbp"

#: A deep file outlives its game by this much and is then pruned. Long
#: enough that a final can still be read the morning after; short enough
#: that a season of games does not accumulate under web/.
PBP_MAX_AGE_S = 36 * 3600


def _row(r: dict) -> dict:
    """One game in the shape `app.js`'s fetchAllLive merge expects.

    `home` and `away` are the LEAGUE BOARD'S abbreviations, resolved by
    `livescores._side_key` — see its docstring for why that is the fussy
    part. The merge key is `away@home`, and a key that does not match
    does not error, it silently drops the card's lines and its chart.
    """
    st = r["live"]
    live = {
        "state": st.state,
        "home_score": st.home_score,
        "away_score": st.away_score,
        "period": st.period,
        "clock": st.clock,
        "detail": st.detail,
        "start_time": st.start_time,
    }
    # FOOTBALL ONLY, AND ONLY WHEN IT PARSED. `yard_line` and
    # `possession` are what the card art draws the ball with; basketball
    # payloads carry no situation block at all, and a football spot that
    # would not parse leaves them None. Writing the keys anyway would
    # hand the front end `null` to tell apart from "this sport has no
    # such thing", which are different facts.
    if st.yard_line is not None:
        live["yard_line"] = st.yard_line
    if st.possession:
        live["possession"] = st.possession
    out = {"event_id": r["event_id"], "home": r["home"], "away": r["away"],
           "home_name": r["home_name"], "away_name": r["away_name"],
           "live": live}
    # ESPN's own team ids, when the scoreboard gave them. A basketball
    # play names its team by id and nothing else, and these are how
    # `attach_plays` turns that id into the card's own `home`/`away` —
    # the verified route, since the summary's team dicts have not been
    # probed. Written only when present, for the reason `yard_line` is.
    if r.get("home_id"):
        out["home_id"] = r["home_id"]
    if r.get("away_id"):
        out["away_id"] = r["away_id"]
    return out


def build(league: str, pbp_dir: Path | None = None) -> dict:
    """`{"games": [...], "generated_at": ...}` — or an honest empty board.

    A feed that cannot be reached returns NO GAMES rather than raising,
    exactly as `live_build.build` does. This runs every few seconds beside
    a live site; one unreachable poll must not take the page down, and an
    empty scoreboard is a true statement about what we know right now.

    THE NOTE IS NOT DECORATION. An empty list with no note and an empty
    list because ESPN refused the request look identical to every reader
    downstream, and this repo has been bitten by that shape enough times
    to spell it out — see engine/census.py and the college board that
    "showed nothing on opening Saturday and both logs lied about it".
    """
    now = _dt.datetime.now().isoformat(timespec="seconds")
    try:
        rows = fetch_rows(league, ttl=TTL)
    except DataUnavailable as exc:
        return {"generated_at": now, "league": league, "games": [],
                "note": f"{league.upper()} scoreboard unreachable — {exc}"}
    except Exception as exc:                                 # noqa: BLE001
        return {"generated_at": now, "league": league, "games": [],
                "note": f"{league.upper()} scoreboard unreadable — "
                        f"{type(exc).__name__}: {exc}"}
    games = [_row(r) for r in rows]
    games.sort(key=lambda g: (g["live"]["start_time"] or "", g["event_id"]))
    out = {"generated_at": now, "league": league, "games": games}
    out["plays_note"] = attach_plays(games, league, pbp_dir=pbp_dir)
    return out


def attach_plays(games: list[dict], league: str,
                 pbp_dir: Path | None = None) -> str:
    """Put the last few plays — and, for football, the current drive —
    on every game IN PROGRESS. Returns a note for the log and the file.

    ONLY LIVE GAMES. Football reads the `drives` block the droplet probe
    saw on a live college game; basketball reads the `plays` list it saw
    on a finished WNBA game (`engine/sources/espnplays` carries both
    shapes and what each was seen on). A scheduled game has neither and
    a final is not what anybody is watching. A league in neither tuple
    is left alone and the note says so.

    THE SIDES OF A BASKETBALL PLAY COME FROM THE SCOREBOARD. A hoops
    play carries `team{id}` and nothing else; this game's `home_id` and
    `away_id` were read off the same scoreboard payload as its score, so
    the play's `team` is the card's own key by the same route rather
    than by a second reading of ESPN's abbreviations.

    A GAME THAT FAILS KEEPS ITS SCORE. Each summary is guarded on its own
    and the failures are counted rather than raised — one unreachable
    play feed must not cost the scoreboard the card, which is the more
    important product of this process.

    ``pbp_dir`` set: the same payload also becomes the game's deep file
    (`write_pbp`) — every play, football's grouped by drive — so the
    page a reader opens from the card costs no second fetch. A deep file
    that fails to write costs nothing but itself.
    """
    from engine.sources import espnplays
    if league in espnplays.FOOTBALL:
        noun = "drives"
    elif league in espnplays.HOOPS:
        noun = "plays"
    else:
        return f"{league}: no play-by-play source yet"
    live = [g for g in games if g["live"]["state"] == "live"]
    if not live:
        return f"no games in progress — no {noun} fetched"
    got = failed = deep = 0
    for g in live[:PLAYS_MAX_GAMES]:
        try:
            payload = espnplays.fetch_summary(league, g["event_id"])
            sides = {str(g.get("home_id") or ""): g["home"],
                     str(g.get("away_id") or ""): g["away"]}
            sides.pop("", None)
            if noun == "drives":
                g["plays"] = espnplays.football_plays(payload, league,
                                                      PLAYS_PER_GAME)
                drive = espnplays.current_drive(payload, league)
                if drive:
                    g["drive"] = drive
            else:
                g["plays"] = espnplays.hoops_plays(payload, league,
                                                   PLAYS_PER_GAME, sides=sides)
            got += 1
        except Exception:                                    # noqa: BLE001
            failed += 1                # the card keeps its score
            continue
        if pbp_dir is not None:
            try:
                write_pbp(league, g, payload, pbp_dir, sides=sides)
                deep += 1
            except Exception:                                # noqa: BLE001
                pass                       # the card keeps its plays
    skipped = max(0, len(live) - PLAYS_MAX_GAMES)
    note = f"{noun}: {got} of {len(live)} live game(s)"
    if failed:
        note += f", {failed} feed(s) unreachable"
    if skipped:
        note += (f", {skipped} past the {PLAYS_MAX_GAMES}-game cap "
                 f"(scores only)")
    if pbp_dir is not None and got:
        note += f", {deep} deep file(s)"
    return note


def pbp_doc(league: str, g: dict, payload: dict,
            sides: dict | None = None) -> dict:
    """One game's whole play-by-play as the page reads it.

    The card's own header fields ride along — sides in the board's
    vocabulary, names, the live state — so the page needs no second
    lookup to say whose game it is. Football carries `drives`, each with
    its plays, and the same plays flattened as `plays`; basketball has
    no drive and carries `plays` alone. Newest LAST throughout, as a
    play-by-play reads; the page decides what to show first.
    """
    from engine.sources import espnplays
    doc = {
        "league": league,
        "event_id": str(g.get("event_id") or ""),
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "home": g.get("home"), "away": g.get("away"),
        "home_name": g.get("home_name", ""), "away_name": g.get("away_name", ""),
        "live": g.get("live") or {},
    }
    if league in espnplays.FOOTBALL:
        drives = espnplays.football_drives(payload, league)
        doc["drives"] = drives
        doc["plays"] = [r for d in drives for r in d["plays"]]
    else:
        doc["plays"] = espnplays.hoops_plays(payload, league, 0, sides=sides)
    return doc


def write_pbp(league: str, g: dict, payload: dict, pbp_dir: Path,
              sides: dict | None = None) -> Path:
    """Write the deep file atomically; returns its path."""
    pbp_dir = Path(pbp_dir)
    pbp_dir.mkdir(parents=True, exist_ok=True)
    out = pbp_dir / f"{league}_{g['event_id']}.json"
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(pbp_doc(league, g, payload, sides=sides)))
    os.replace(tmp, out)
    return out


def prune_pbp(pbp_dir: Path, max_age_s: int = PBP_MAX_AGE_S,
              now: float | None = None) -> int:
    """Remove deep files older than ``max_age_s``; returns how many.

    Runs on the fast clock, so it must be cheap — one directory scan,
    no parsing — and must never raise into the scoreboard write.
    """
    pbp_dir = Path(pbp_dir)
    if not pbp_dir.is_dir():
        return 0
    now = _time.time() if now is None else now
    gone = 0
    for path in pbp_dir.glob("*.json"):
        try:
            if now - path.stat().st_mtime > max_age_s:
                path.unlink()
                gone += 1
        except OSError:
            continue
    return gone


def write(league: str, out_dir: Path = OUT) -> dict:
    pbp_dir = Path(out_dir) / "pbp"
    payload = build(league, pbp_dir=pbp_dir)
    try:
        prune_pbp(pbp_dir)
    except Exception:                                        # noqa: BLE001
        pass                          # the scoreboard write comes first
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"live_{league}.json"
    # Atomic replace — this runs on the launcher's fast clock while the
    # Live tab polls the same file; see memes_build for the lesson.
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1))
    os.replace(tmp, out)
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default="",
                    help="one of " + ", ".join(ESPN_SCOREBOARD))
    ap.add_argument("--out-dir", default=str(OUT))
    args = ap.parse_args()
    leagues = [args.league] if args.league else list(ESPN_SCOREBOARD)
    out_dir = Path(args.out_dir)
    total = live = 0
    for lg in leagues:
        # ONE LEAGUE'S FAILURE IS NOT FOUR. `build` already refuses to
        # raise on a bad feed; this catches the write itself, so a full
        # disk or a permission fault on one file still leaves the other
        # three boards refreshed.
        try:
            payload = write(lg, out_dir)
        except Exception as exc:                             # noqa: BLE001
            print(f"  ⚠️  {lg}: {type(exc).__name__}: {exc}")
            continue
        n = len(payload["games"])
        on = sum(1 for g in payload["games"]
                 if g["live"]["state"] == "live")
        total += n
        live += on
        note = payload.get("note")
        print(f"  {lg}: {n} game(s), {on} in progress"
              + (f" — {note}" if note else ""))
        if on and payload.get("plays_note"):
            print(f"      {payload['plays_note']}")
    print(f"live scores: {total} game(s) across {len(leagues)} league(s), "
          f"{live} in progress → {out_dir}/live_*.json")


if __name__ == "__main__":
    main()
