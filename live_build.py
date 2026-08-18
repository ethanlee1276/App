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


def build(date: str) -> dict:
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
    return {"generated_at": now, "date": date, "games": games}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    date = args.date or _dt.date.today().isoformat()
    payload = build(date)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replace — this runs on the launcher's fast clock while the
    # Live tab polls the same file; see memes_build for the lesson.
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1))
    os.replace(tmp, out)
    live = sum(1 for g in payload["games"] if g["live"]["state"] == "live")
    print(f"live scores: {len(payload['games'])} game(s), {live} in progress "
          f"→ {out}")


if __name__ == "__main__":
    main()
