#!/usr/bin/env python3
"""Live MLB scores → web/data/live_mlb.json, on a clock of their own.

    python3 live_build.py
    python3 live_build.py --date 2026-08-16

THE BUG THIS FIXES, measured on the live droplet 2026-08-16.

`web/js/app.js` read live MLB scores out of `data/mlb_recommendations.json`,
which is the full model board: 8MB, 923 props, and **7 minutes 39 seconds**
to build. A score that changes every pitch was therefore trapped behind
every prop repricing, and the site showed games 8-15 minutes behind — which
during a game in progress reads as "the scores are broken".

Nothing was broken. It was wired to the wrong file.

The scoreboard itself is nearly free: `live.fetch_live()` is ONE request to
the schedule endpoint with the linescore hydrated, cached for 30 seconds.
The seven and a half minutes is entirely the model. So this writes the
scoreboard on its own fast clock and leaves the board on its own slow one.

THE UFC PAGE ALREADY DID THIS, and its own docstring names the trap:
"Tying them together would mean either a stale diagram or a card rebuilt
200 times a night." `ufc_live_build.py` is the file this one copies. MLB,
NFL, NBA, WNBA and CFB never got the same treatment; MLB is the one with
games every night, so it is the one that showed.

WHAT THIS DELIBERATELY DOES NOT CARRY. No props, no prices, no edges, no
recommendations — scores and game state only. That keeps it cheap, and it
keeps it OUT of the paywall's way: a score is a public fact, and
engine/gate.py has no reason to redact one. `game_bets` still come from the
model board, where they belong and where their latency does not matter.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
from pathlib import Path

from engine.mlb.sources.live import (STATS_BASE, TEAM_ID_ABBR,  # noqa: E402
                                     _get_json, parse_live)
from engine.sources.fetch import DataUnavailable

OUT = Path("web/data/live_mlb.json")

#: How many plays ride on a card. Six is about one full time through the
#: order's worth of outcomes — enough to read the inning, small enough
#: that the file the page polls every thirty seconds stays kilobytes.
PLAYS_PER_GAME = 6

#: The most games this will fetch plays for in one pass. A play-by-play
#: payload measured 640 KB, and this box is one vCPU that has OOM-crashed
#: once. A fifteen-game slate is a full night; past that the extra games
#: keep their scores and lose only their plays, and the log SAYS SO — an
#: empty play list because we ran out of budget and one because the game
#: has not thrown a pitch are different facts.
PLAYS_MAX_GAMES = 15


def _row(pk: int, st) -> dict:
    """One game, in the shape web/js/app.js already renders.

    `home`/`away` come back from the key rather than the status object,
    because LiveStatus carries the STATE of a game and not its identity —
    and inventing a field on it here would put the same fact in two places.
    """
    return {
        "game_pk": pk,
        "live": {
            "state": st.state,
            "home_score": st.home_score,
            "away_score": st.away_score,
            "period": st.period,
            "outs": st.outs,
            "bases": st.bases,
            "balls": st.balls,
            "strikes": st.strikes,
            "start_time": st.start_time,
        },
    }


def build(date: str, pbp_dir: Path | None = None) -> dict:
    """`{"games": [...], "generated_at": ...}` — or an honest empty board.

    A feed that cannot be reached returns NO GAMES rather than raising.
    This runs every few seconds beside a live site; one unreachable poll
    must not take the page down, and an empty scoreboard is a true
    statement about what we know right now.

    HOME AND AWAY COME FROM THE SCHEDULE, NOT FROM parse_live's KEYS.
    parse_live indexes by an UNORDERED frozenset of the two abbreviations,
    so which side is home is genuinely not recoverable from a key — the
    first draft of this file sorted them alphabetically, which would have
    swapped the two teams on roughly half the cards. A scoreboard that
    reverses a score is worse than one that is late, so the raw payload
    (where `teams.home` and `teams.away` are explicit) is read directly and
    parse_live is used only for the STATE it already knows how to derive.
    """
    now = _dt.datetime.now().isoformat(timespec="seconds")
    try:
        raw = _get_json(
            f"{STATS_BASE}/schedule?sportId=1&date={date}&hydrate=linescore",
            f"mlb_live_{date}.json", ttl=30)
    except DataUnavailable as exc:
        return {"generated_at": now, "date": date, "games": [],
                "note": f"MLB scoreboard unreachable — {exc}"}

    board = parse_live(raw)
    games = []
    for day in raw.get("dates", []):
        for g in day.get("games", []):
            pk = g.get("gamePk")
            st = board.get(int(pk)) if pk else None
            if not st:
                continue
            teams = g.get("teams", {})
            home = teams.get("home", {}).get("team", {})
            away = teams.get("away", {}).get("team", {})
            home_ab = TEAM_ID_ABBR.get(home.get("id"), home.get("abbreviation", ""))
            away_ab = TEAM_ID_ABBR.get(away.get("id"), away.get("abbreviation", ""))
            if not home_ab or not away_ab:
                continue
            row = _row(int(pk), st)
            row["home"], row["away"] = home_ab, away_ab
            games.append(row)
    games.sort(key=lambda r: (r["live"]["start_time"] or "", r["game_pk"]))
    out = {"generated_at": now, "date": date, "games": games}
    out["plays_note"] = attach_plays(games, pbp_dir=pbp_dir)
    return out


def attach_plays(games: list[dict], pbp_dir: Path | None = None) -> str:
    """Put the last few at-bats on every game IN PROGRESS. Returns a note.

    ONLY LIVE GAMES, which is what keeps this affordable: a scheduled
    game has no plays and a finished one is not what anybody is watching.
    `engine/mlb/sources/pbp.py` has fetched this endpoint since the
    pitch-level work went in — on a seven-day cache, for modelling. This
    is the same call on a thirty-second one, under its own cache name so
    a half-played payload can never be served to the velocity parsers as
    a finished game.

    A GAME THAT FAILS KEEPS ITS SCORE. One unreachable play feed must not
    cost the scoreboard the card, so each game is guarded on its own and
    the failures are counted rather than raised.
    """
    live = [g for g in games if g["live"]["state"] == "live"]
    if not live:
        return "no games in progress — no plays fetched"
    from engine.mlb.sources.pbp import fetch_live_playbyplay, recent_plays
    got = failed = deep = 0
    for g in live[:PLAYS_MAX_GAMES]:
        try:
            payload = fetch_live_playbyplay(g["game_pk"])
            g["plays"] = recent_plays(payload, PLAYS_PER_GAME)
            got += 1
        except Exception:                                    # noqa: BLE001
            failed += 1                # the card keeps its score
            continue
        # THE DEEP FILE, from the payload already in hand (Ethan,
        # 2026-09-05: "click on each live game and see a deeper play by
        # play"). Every completed at-bat, newest last, under
        # `pbp/mlb_{game_pk}.json` beside the scoreboard — the same
        # shape and directory livescore_build writes for the other four
        # leagues, so the page reads one layout. A write that fails
        # costs nothing but itself.
        if pbp_dir is not None:
            try:
                write_pbp(g, payload, recent_plays(payload, 0), pbp_dir)
                deep += 1
            except Exception:                                # noqa: BLE001
                pass
    skipped = max(0, len(live) - PLAYS_MAX_GAMES)
    note = f"plays: {got} of {len(live)} live game(s)"
    if failed:
        note += f", {failed} feed(s) unreachable"
    if skipped:
        note += (f", {skipped} past the {PLAYS_MAX_GAMES}-game cap "
                 f"(scores only)")
    if pbp_dir is not None and got:
        note += f", {deep} deep file(s)"
    return note


def write_pbp(g: dict, payload: dict, plays: list[dict], pbp_dir: Path) -> Path:
    """One MLB game's whole play-by-play, atomically, as the page reads it.

    The header rides along from the fast row — sides, live state — so
    the page needs no second lookup. Composed from `recent_plays`' rows
    and never from a play's `description`, the same posture the card's
    strip takes.
    """
    from engine.mlb.sources.pbp import current_at_bat, game_events
    pbp_dir = Path(pbp_dir)
    pbp_dir.mkdir(parents=True, exist_ok=True)
    out = pbp_dir / f"mlb_{g['game_pk']}.json"
    doc = {
        "league": "mlb",
        "event_id": str(g["game_pk"]),
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "home": g.get("home"), "away": g.get("away"),
        "home_name": g.get("home_name", ""), "away_name": g.get("away_name", ""),
        "live": g.get("live") or {},
        "plays": plays,
        # THE RENDER'S RAIL (2026-09-05): every pitch and every at-bat in
        # order, with the batted-ball data the park animation draws from
        # and the at-bat in progress. `plays` above stays the card's own
        # at-bat list, so the page can read either.
        "events": game_events(payload),
        "current": current_at_bat(payload),
    }
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc))
    os.replace(tmp, out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    date = args.date or _dt.date.today().isoformat()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Deep files beside the scoreboard, pruned on the same clock — one
    # directory for every league (livescore_build.PBP_DIR is the same
    # `pbp/` under web/data), so the page has one place to look.
    pbp_dir = out.parent / "pbp"
    payload = build(date, pbp_dir=pbp_dir)
    try:
        from livescore_build import prune_pbp
        prune_pbp(pbp_dir)
    except Exception:                                        # noqa: BLE001
        pass                          # the scoreboard write comes first
    # Atomic replace — this runs on the launcher's fast clock while the
    # Live tab polls the same file; see memes_build for the lesson.
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1))
    os.replace(tmp, out)
    live = sum(1 for g in payload["games"] if g["live"]["state"] == "live")
    print(f"live scores: {len(payload['games'])} game(s), {live} in progress "
          f"→ {out}")
    if payload.get("plays_note"):
        print(f"  {payload['plays_note']}")
    # THE SWEAT RIDES THE SAME CLOCK. The per-bet live probabilities have
    # existed since mid-August — inside the 8-minute board build, which
    # is the exact latency this file was created to fix for scores.
    # Guarded so a sweat failure can never take the scoreboard with it:
    # scores are the more important product of this process.
    try:
        from engine import sweat
        sweat.build(today=args.date or None, quiet=False)
    except Exception as exc:                              # noqa: BLE001
        print(f"  sweat: skipped — {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
