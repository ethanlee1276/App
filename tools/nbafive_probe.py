"""Can the box read tonight's CONFIRMED starting five? A read-only probe.

Knowing tonight's five outright is the largest gain the NBA lab has left:
5.5-6.0% off the board's minutes error and 0.9-1.2% off points (docs/NBA_LAB.md,
"Who starts tonight"), and another 0.012-0.013 off first basket's Brier
("First basket, tonight's five"). The five is confirmed about half an hour
before the tip. Neither source below answers from the lab, so this asks
them from the box, where the board runs:

  * ESPN's game summary — the feed the box already reads for every final.
    Before the tip, does its box score list the players with ESPN's
    ``starter`` flag set?
  * The league's daily lineups file (stats.nba.com, the JSON behind
    nba.com's "Today's lineups" page) — each player's ``lineupStatus``
    ("Expected", then "Confirmed").

It prints what each one says for today's games and how long before each tip
it asked. Nothing is stored: no cache file, no database, no board. The
clients name themselves as Python's urllib does, as the box's other ESPN
reads do (engine/sources/fetch.py); nothing else is sent.

    python3 tools/nbafive_probe.py            # today, Eastern
    python3 tools/nbafive_probe.py 2026-11-05

Standard library only.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
LINEUPS = "https://stats.nba.com/js/data/leaders/00_daily_lineups_{day}.json"
TIMEOUT = 20


def _get(url: str, headers: dict | None = None) -> tuple:
    """``(status, payload or None, note)`` — never raises, never caches."""
    req = urllib.request.Request(url, headers=dict(headers or {}))
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read()
            try:
                return r.status, json.loads(body.decode("utf-8")), ""
            except ValueError:
                return r.status, None, f"not JSON ({len(body)} bytes)"
    except urllib.error.HTTPError as e:
        return e.code, None, str(e.reason or "")
    except Exception as e:                                    # noqa: BLE001
        return None, None, f"{type(e).__name__}: {e}"


def espn_games(scoreboard: dict) -> list:
    """``[{"id", "away", "home", "tip" (UTC ISO), "state"}]`` from ESPN's
    scoreboard."""
    out = []
    for ev in (scoreboard or {}).get("events") or []:
        comp = (ev.get("competitions") or [{}])[0]
        side = {}
        for c in comp.get("competitors") or []:
            side[c.get("homeAway")] = str(((c.get("team") or {}).get("abbreviation")) or "")
        out.append({"id": str(ev.get("id") or ""), "away": side.get("away", ""), "home": side.get("home", ""),
                    "tip": str(ev.get("date") or comp.get("date") or ""),
                    "state": str(((ev.get("status") or {}).get("type") or {}).get("state") or "")})
    return out


def espn_starters(summary: dict) -> dict:
    """``{club: [names]}`` for the athletes ESPN's summary flags ``starter``,
    every club its box score lists (an empty list where none is flagged)."""
    out = {}
    for block in ((summary or {}).get("boxscore") or {}).get("players") or []:
        club = str(((block.get("team") or {}).get("abbreviation")) or "?")
        names = out.setdefault(club, [])
        for group in block.get("statistics") or []:
            for ath in group.get("athletes") or []:
                if ath.get("starter"):
                    a = ath.get("athlete") or {}
                    names.append(str(a.get("displayName") or a.get("shortName") or a.get("id") or "?"))
    return out


def daily_lineups(payload: dict) -> list:
    """``[{"club", "players", "status": {lineupStatus: n}, "roster": {rosterStatus: n},
    "latest"}]`` per club in the league's daily lineups file, read without
    assuming more than a games list with home and away teams."""
    out = []
    for g in (payload or {}).get("games") or []:
        for key in ("awayTeam", "homeTeam"):
            t = g.get(key) or {}
            players = t.get("players") or []
            status: dict = {}
            roster: dict = {}
            stamps = []
            for p in players:
                s = str(p.get("lineupStatus") or "-")
                status[s] = status.get(s, 0) + 1
                r = str(p.get("rosterStatus") or "-")
                roster[r] = roster.get(r, 0) + 1
                if p.get("timestamp"):
                    stamps.append(str(p["timestamp"]))
            out.append({"club": str(t.get("teamAbbreviation") or t.get("teamTricode") or "?"),
                        "players": len(players), "status": status, "roster": roster,
                        "latest": max(stamps) if stamps else ""})
    return out


def _minutes_to(tip: str, now: dt.datetime) -> str:
    try:
        t = dt.datetime.fromisoformat(tip.replace("Z", "+00:00"))
    except ValueError:
        return "?"
    m = int((t - now).total_seconds() // 60)
    return f"in {m} min" if m >= 0 else f"{-m} min ago"


def main(argv) -> int:
    now = dt.datetime.now(dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        et = now.astimezone(ZoneInfo("America/New_York"))
    except Exception:                                         # noqa: BLE001
        et = now - dt.timedelta(hours=5)
    day = argv[1] if len(argv) > 1 else et.date().isoformat()
    compact = day.replace("-", "")
    print(f"NBA confirmed-five probe for {day}, asked {now.strftime('%Y-%m-%d %H:%M')} UTC")
    st, board, note = _get(f"{ESPN}/scoreboard?dates={compact}&limit=60")
    games = espn_games(board) if board else []
    print(f"\nESPN scoreboard: HTTP {st} {note}".rstrip() + f" — {len(games)} game(s)")
    for g in games:
        st2, summ, note2 = _get(f"{ESPN}/summary?event={g['id']}")
        five = espn_starters(summ) if summ else {}
        flagged = ", ".join(f"{c} {len(n)}" for c, n in five.items()) or "no box score yet"
        print(f"  {g['away']} @ {g['home']}  tips {_minutes_to(g['tip'], now)} ({g['state'] or '?'})  "
              f"summary HTTP {st2}{(' ' + note2) if note2 else ''}  starters flagged: {flagged}")
        for c, n in five.items():
            if n:
                print(f"      {c}: {', '.join(n)}")
    st3, lu, note3 = _get(LINEUPS.format(day=compact),
                          {"Referer": "https://www.nba.com/", "Accept": "application/json"})
    rows = daily_lineups(lu) if lu else []
    print(f"\nLeague daily lineups ({LINEUPS.format(day=compact).rsplit('/', 1)[-1]}): HTTP {st3} {note3}".rstrip()
          + (f" — {len(rows)} club(s)" if lu else ""))
    for r in rows:
        print(f"  {r['club']}: {r['players']} listed, lineup {r['status']}, roster {r['roster']}"
              + (f", newest {r['latest']}" if r["latest"] else ""))
    print("\nWhat it means: a source that flags five starters per club a half hour before the tip "
          "(ESPN `starter`, or the league's `Confirmed`) is one the board can rebuild on.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
