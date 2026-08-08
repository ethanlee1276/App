#!/usr/bin/env python3
"""Which team-logo and player-headshot URLs actually resolve. Probe only.

    python3 assets.py --probe            # every sport
    python3 assets.py --probe --sport nfl

WHY THIS EXISTS BEFORE THE FEATURE. Every image host involved —
`a.espncdn.com`, `static.www.nfl.com`, `midfield.mlbstatic.com` — is
refused by the cloud container's network policy, so the URL patterns below
are recalled, not verified. This session has already paid three times for
writing code against an API shape nobody had called:

  * `limit=400` on ESPN's scoreboard, which EMPTIED every response
  * a custom User-Agent, which 403'd four feeds silently for weeks
  * `score: "0"`, read as a live 0-0 on 48 scheduled fixtures

A wrong logo URL fails softer than any of those — a broken image instead of
a wrong number — but it fails on every card at once, and a layout built
around an image that never arrives is worse than no image. So: run this on
a machine with a normal connection, send the output, and the feature gets
built against whatever answered.

NOTHING HERE IS WIRED INTO THE SITE. It writes nothing, caches nothing and
changes no board. It prints a table.

WHAT IT CANNOT TELL YOU. Only whether a URL returns an image. Whether the
site may USE these is a separate question with a real answer: team logos
are trademarks and headshots are licensed photographs. On a local board
served by `python3 launch.py` to one person that is a non-issue in
practice. It stops being one the day this gets a public address, and
hotlinking a league's own CDN is the version of it that gets noticed first.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
TIMEOUT = 15

#: Candidate logo patterns. `{k}` is the league key, `{a}` the abbreviation
#: (lower-cased for ESPN, which is what its paths use).
LOGO_PATTERNS = [
    ("espn-500", "https://a.espncdn.com/i/teamlogos/{k}/500/{a}.png"),
    ("espn-500-dark", "https://a.espncdn.com/i/teamlogos/{k}/500-dark/{a}.png"),
    ("espn-scoreboard", "https://a.espncdn.com/combiner/i?img=/i/teamlogos/{k}/500/{a}.png&w=200&h=200"),
]

#: Which ESPN league key each of our sports uses, and three real
#: abbreviations to try — including one where our spelling and ESPN's are
#: known to differ, because that is where a naive map breaks.
SPORTS = {
    "nfl":  ("nfl",  ["kc", "was", "la"]),
    "mlb":  ("mlb",  ["nyy", "bos", "laa"]),
    "nba":  ("nba",  ["bos", "lal", "gs"]),
    "wnba": ("wnba", ["min", "lv", "ny"]),
    "cfb":  ("ncaa", ["333", "130", "2"]),   # ESPN uses numeric team ids here
}


def _get(url: str) -> tuple[str, str]:
    """(verdict, detail) — never raises, so one dead host cannot end the run."""
    req = urllib.request.Request(url)          # no custom User-Agent; see fetch.py
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read(4096)
            ctype = r.headers.get("Content-Type", "?")
            total = r.headers.get("Content-Length") or f"{len(body)}+"
            ok = ctype.startswith("image/")
            return ("OK " if ok else "NOT-IMAGE",
                    f"{r.status} {ctype} {total}b")
    except Exception as exc:                                  # noqa: BLE001
        return "FAIL", f"{type(exc).__name__}: {str(exc)[:60]}"


def probe_logos(only: str | None) -> None:
    print("=" * 78)
    print("TEAM LOGOS")
    print("=" * 78)
    for sport, (key, abbrs) in SPORTS.items():
        if only and sport != only:
            continue
        print(f"\n  {sport.upper()}  (ESPN league key '{key}')")
        for label, pat in LOGO_PATTERNS:
            for a in abbrs:
                url = pat.format(k=key, a=a)
                verdict, detail = _get(url)
                print(f"    {verdict:<10} {label:<16} {a:<5} {detail}")
                if verdict == "OK ":
                    break        # one success per pattern is enough to judge it


def probe_nfl_headshots() -> None:
    """The one case that needs no guessing: nflverse ships the URL.

    Measured on the cached 2026 roster — 2,824 of 2,930 players carry a
    `headshot_url`, 96%. So for NFL the question is not "what is the
    pattern" but only "does the host serve it to us".
    """
    print("\n" + "=" * 78)
    print("PLAYER HEADSHOTS — NFL (URL comes from the roster, not a guess)")
    print("=" * 78)
    path = os.path.join(ROOT, "data", "cache", "roster_2026.csv")
    if not os.path.exists(path):
        print("  no cached 2026 roster; run `python3 ingest.py nfl` first")
        return
    with open(path, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh)
                if (r.get("headshot_url") or "").strip()]
    print(f"  {len(rows)} roster rows carry a headshot_url")
    for r in rows[:3]:
        verdict, detail = _get(r["headshot_url"])
        name = r.get("full_name") or r.get("player_name") or "?"
        print(f"    {verdict:<10} {name[:24]:<24} {detail}")
        print(f"    {'':<10} {r['headshot_url'][:70]}")


def probe_other_headshots(only: str | None) -> None:
    """The sports where we hold a NAME and the CDN wants an ID.

    This is the real cost of the feature and the reason it is not one
    change: NFL hands us the URL, and every other sport needs an id we do
    not currently store anywhere — `player_game_logs` has `player` and no
    identifier. Each of these would mean capturing the id during ingest.
    """
    print("\n" + "=" * 78)
    print("PLAYER HEADSHOTS — the sports that need an ID we do not store")
    print("=" * 78)
    cands = [
        ("mlb", "MLB Stats API, Aaron Judge (592450)",
         "https://midfield.mlbstatic.com/v1/people/592450/spots/120"),
        ("mlb", "ESPN, by ESPN athlete id",
         "https://a.espncdn.com/i/headshots/mlb/players/full/33192.png"),
        ("nba", "ESPN, by ESPN athlete id",
         "https://a.espncdn.com/i/headshots/nba/players/full/1966.png"),
        ("wnba", "ESPN, by ESPN athlete id",
         "https://a.espncdn.com/i/headshots/wnba/players/full/2529205.png"),
    ]
    for sport, label, url in cands:
        if only and sport != only:
            continue
        verdict, detail = _get(url)
        print(f"  {verdict:<10} {sport:<5} {label}")
        print(f"  {'':<10} {detail}")
        print(f"  {'':<10} {url}")


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--probe", action="store_true",
                   help="try every candidate URL and report what answered")
    p.add_argument("--sport", default="",
                   help="limit to one sport (nfl, mlb, nba, wnba, cfb)")
    a = p.parse_args(argv)
    if not a.probe:
        p.print_help()
        return 1
    only = a.sport.lower() or None
    probe_logos(only)
    if not only or only == "nfl":
        probe_nfl_headshots()
    probe_other_headshots(only)
    print("\n" + "=" * 78)
    print("READ IT LIKE THIS")
    print("=" * 78)
    print("  Every logo pattern FAILs   -> the host is blocked or the path")
    print("                                changed; send the output and I")
    print("                                will find the shape that works.")
    print("  One pattern is OK          -> that is the one to build on, and")
    print("                                the abbreviation map is the only")
    print("                                remaining work for logos.")
    print("  NFL headshots OK           -> faces ship for NFL immediately;")
    print("                                the URL is already in the roster.")
    print("  MLB/NBA/WNBA OK            -> faces need an id captured during")
    print("                                ingest first. That is per-sport")
    print("                                work, not one change.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
