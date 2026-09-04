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
from pathlib import Path

from engine.sources.fetch import DataUnavailable
from engine.sources.livescores import ESPN_SCOREBOARD, fetch_rows

#: Cached for the launcher's fast cadence. Shorter than this buys nothing
#: — `LIVE_FAST_S` is 12 seconds and the scoreboard does not move faster
#: than the clock on the screen.
TTL = 20

OUT = Path("web/data")


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
    return {"event_id": r["event_id"], "home": r["home"], "away": r["away"],
            "home_name": r["home_name"], "away_name": r["away_name"],
            "live": live}


def build(league: str) -> dict:
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
    return {"generated_at": now, "league": league, "games": games}


def write(league: str, out_dir: Path = OUT) -> dict:
    payload = build(league)
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
    print(f"live scores: {total} game(s) across {len(leagues)} league(s), "
          f"{live} in progress → {out_dir}/live_*.json")


if __name__ == "__main__":
    main()
