#!/usr/bin/env python3
"""What is actually inside an ESPN game summary — run this before parsing one.

    python3 espnprobe.py --league cfb
    python3 espnprobe.py --league nfl --event 401772936
    python3 espnprobe.py --league nba --dump /tmp/nba_summary.json

WHY THIS EXISTS. Ethan, 2026-09-04, asked for live play-by-play across
every sport. MLB was already possible — `engine/mlb/sources/pbp.py` has
fetched statsapi's playByPlay for a year and the repo carries a real
fixture of it. The other four leagues would come from ESPN's
`summary?event=` endpoint, which this repo already FETCHES (see
`sources.nflpreseason.fetch_boxscore` and `sources.espnhoops.
fetch_summary`) and has never looked inside beyond the box score.

Nothing in the repo records the shape of its plays. Writing a parser
against a remembered shape is how `g["home_id"]` and `g["away_id"]` —
two fields that do not exist — reached a college headshot cut on
2026-09-04, and how `nfl_build.py --odds` got recommended to a droplet
that requires two positional arguments. So: look first, parse second.

WHAT IT PRINTS, and what it deliberately does not. Key names, container
types, list lengths, and numeric or boolean sample values. NEVER the
text of a play. ESPN's written account of a game is theirs — the same
position the injuries page's news section settled on, and the same one
`engine/mlb/sources/pbp.recent_plays` takes by composing its sentence
from `event`, `batter` and `rbi` rather than copying `description`. A
string's LENGTH is enough to tell a parser-writer that a field is prose.

`--dump` writes the raw payload to a path you choose, for the case where
the structure alone is not enough. That file is ESPN's content: it is a
working note, not something to publish.
"""

from __future__ import annotations

import argparse
import json
import sys

#: The summary endpoint per league, beside the scoreboards in
#: `sources.livescores.ESPN_SCOREBOARD`. Same hosts, same paths, one
#: segment different — kept here rather than imported so this script
#: stays runnable on a box where the engine will not import.
SUMMARY = {
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary",
    "cfb": ("https://site.api.espn.com/apis/site/v2/sports/football/"
            "college-football/summary"),
    "nba": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary",
    "wnba": "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary",
}

#: The blocks a play-by-play could plausibly live under. Reported
#: present-or-absent at the top so the answer is the first thing on the
#: screen rather than something to hunt for in a tree.
WANTED = ("drives", "plays", "scoringPlays", "winprobability",
          "competitions", "header", "boxscore")


def describe(value, depth: int = 0, max_depth: int = 3,
             list_sample: int = 1) -> list[str]:
    """The SHAPE of a payload as indented lines: keys, types, lengths.

    A string is reported as `str(len)` and never by its content — see the
    module docstring. Numbers and booleans print their value, because a
    parser-writer needs to know that `period` is 2 and not "2nd".
    """
    pad = "  " * depth
    out: list[str] = []
    if isinstance(value, dict):
        if depth >= max_depth:
            return [f"{pad}{{...{len(value)} keys: "
                    f"{', '.join(sorted(value)[:8])}}}"]
        for k in sorted(value):
            v = value[k]
            if isinstance(v, dict):
                out.append(f"{pad}{k}: dict({len(v)})")
                out += describe(v, depth + 1, max_depth, list_sample)
            elif isinstance(v, list):
                out.append(f"{pad}{k}: list({len(v)})")
                for item in v[:list_sample]:
                    out += describe(item, depth + 1, max_depth, list_sample)
            else:
                out.append(f"{pad}{k}: {_scalar(v)}")
    elif isinstance(value, list):
        out.append(f"{pad}list({len(value)})")
        for item in value[:list_sample]:
            out += describe(item, depth + 1, max_depth, list_sample)
    else:
        out.append(f"{pad}{_scalar(value)}")
    return out


def _scalar(v) -> str:
    if isinstance(v, str):
        return f"str({len(v)})"        # never the text itself
    if v is None:
        return "None"
    if isinstance(v, bool):
        return f"bool={v}"
    return f"{type(v).__name__}={v}"


def _get(url: str) -> dict:
    """GET JSON with NO User-Agent header, and that is the whole point.

    The first cut sent "Mozilla/5.0 (qellys probe)" and ESPN answered 403
    on all four leagues from the droplet — the exact trap
    `engine/sources/fetch.py` documents beside DEFAULT_AGENT: "Some hosts
    reject an unfamiliar User-Agent outright... Measured 2026-08-08:
    User-Agent: qellys-book/0.1 -> HTTP 403; urllib's default -> 200."
    Every working ESPN call in this repo sends no header and lets urllib
    identify itself. Not a disguise; the custom string was simply
    unfamiliar enough to trip a rule.
    """
    import urllib.request
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _state(ev: dict) -> str:
    return (((ev.get("status") or {}).get("type") or {}).get("state") or "")


def pick_event(league: str, prefer: str = "in",
               date: str = "") -> tuple[str, str]:
    """``(event_id, state)`` — a game in the preferred state, else the first.

    ``prefer="in"`` is the default and the right one for football:
    `drives.current` and a live `situation` only exist while the clock is
    running, so probing a final would answer a question nobody asked.

    ``prefer="post"`` EXISTS BECAUSE THE WNBA PROBE RAN PRE-GAME THREE
    TIMES IN A ROW (2026-09-04, 2026-09-05 twice) — every attempt landed
    between games, and the question it was asked ("under what key do
    basketball plays live") does not need a clock to be running. A final's
    summary keeps its play-by-play, so yesterday's finished game answers
    it just as well. ``date`` (YYYYMMDD) asks the scoreboard for that day
    rather than today, which is where yesterday's finals are.
    """
    from engine.sources.livescores import ESPN_SCOREBOARD
    url = ESPN_SCOREBOARD[league] + (f"?dates={date}" if date else "")
    data = _get(url)
    events = data.get("events") or []
    if not events:
        raise SystemExit(f"{league}: the scoreboard lists no events"
                         + (f" on {date}" if date else " today"))
    if prefer != "any":
        for ev in events:
            if _state(ev) == prefer:
                return str(ev.get("id")), prefer
    ev = events[0]
    return str(ev.get("id")), _state(ev)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default="nfl", choices=sorted(SUMMARY))
    ap.add_argument("--event", default="",
                    help="ESPN event id; omitted picks a live one")
    ap.add_argument("--dump", default="",
                    help="write the raw payload here (ESPN's content — "
                         "a working note, not something to publish)")
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--prefer", default="in", choices=("in", "post", "any"),
                    help="which game state to look for first; 'post' reads a "
                         "finished game's play-by-play, which basketball keeps")
    ap.add_argument("--date", default="",
                    help="YYYYMMDD — probe that day's scoreboard instead of "
                         "today's (yesterday's finals live there)")
    args = ap.parse_args()

    event, state = (args.event, "asked for") if args.event \
        else pick_event(args.league, args.prefer, args.date)
    print(f"league {args.league}  event {event}  state {state}")
    payload = _get(f"{SUMMARY[args.league]}?event={event}")

    print("\n=== is the play-by-play here at all ===")
    for key in WANTED:
        v = payload.get(key)
        if v is None:
            print(f"  {key:<16} ABSENT")
        elif isinstance(v, list):
            print(f"  {key:<16} list({len(v)})")
        elif isinstance(v, dict):
            print(f"  {key:<16} dict({len(v)}): "
                  f"{', '.join(sorted(v)[:10])}")
        else:
            print(f"  {key:<16} {_scalar(v)}")
    extra = sorted(set(payload) - set(WANTED))
    print(f"  other top-level keys: {', '.join(extra) or '(none)'}")

    for key in ("drives", "plays", "scoringPlays"):
        if key not in payload:
            continue
        print(f"\n=== {key} ===")
        for line in describe(payload[key], max_depth=args.depth,
                             list_sample=1):
            print("  " + line)

    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=1)
        print(f"\nraw payload → {args.dump}")


if __name__ == "__main__":
    sys.exit(main())
