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
    print("\n  RAW, as nflverse ships it:")
    for r in rows[:2]:
        verdict, detail = _get(r["headshot_url"])
        name = r.get("full_name") or r.get("player_name") or "?"
        print(f"    {verdict:<10} {name[:24]:<24} {detail}")

    # THE SIZE IS THE PROBLEM, not the availability. Measured from Ethan's
    # machine 2026-08-08: 3,797,822 / 3,145,446 / 4,307,894 bytes. A board
    # showing twelve props would pull ~45MB of headshots to draw them at
    # 40px. That is not a face feature, it is a stall.
    #
    # These are Cloudinary URLs (`/image/upload/<transforms>/league/<id>`),
    # so transforms go in the path. Which ones this account allows is the
    # open question, and guessing it is how the last three feed bugs
    # happened — so it is asked here rather than written into the site.
    print("\n  RESIZED — which transform does this Cloudinary allow?")
    variants = [
        ("w_96,h_96,c_fill,g_face", "square crop centred on the face"),
        ("w_96,c_fill",             "width only, default gravity"),
        ("w_96",                    "width only, no crop"),
        ("t_headshot_desktop",      "a named preset, if one exists"),
    ]
    base = rows[0]["headshot_url"]
    name = rows[0].get("full_name") or "?"
    marker = "/image/upload/"
    if marker not in base:
        print(f"    the URL shape changed — no '{marker}' in {base[:70]}")
        return
    head, tail = base.split(marker, 1)
    # nflverse already ships `f_auto,q_auto` as the transform segment; the
    # new one replaces it rather than stacking a second copy.
    tail_id = tail.split("/", 1)[1] if "/" in tail else tail
    for tf, label in variants:
        url = f"{head}{marker}f_auto,q_auto,{tf}/{tail_id}"
        verdict, detail = _get(url)
        print(f"    {verdict:<10} {label:<34} {detail}")
        print(f"    {'':<10} {url[:96]}")
    print(f"\n    (all four are the same player: {name})")


def probe_other_headshots(only: str | None) -> None:
    """The sports where we hold a NAME and the CDN wants an ID.

    This is the real cost of the feature and the reason it is not one
    change: NFL hands us the URL, and every other sport needs an id we do
    not currently store anywhere — `player_game_logs` has `player` and no
    identifier. Each of these would mean capturing the id during ingest.

    NBA and WNBA are now DONE and are here only as a regression check: the
    box-score summary carries `athlete.headshot.href`, ingest writes it to
    `player_assets`, and the board reads it. MLB is still open, because we
    ingest statsapi — which gives MLB's ids, not ESPN's — so it needs a
    name→id join before an ESPN path means anything.
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

    # Is the raw ESPN headshot worth resizing? The board ships the href the
    # feed handed us, untouched, because that URL cannot be wrong about its
    # own shape. Whether to route it through the combiner — as the LOGOS
    # already do, where it measured 40,228 bytes against 11,537 — is a
    # question with a number behind it, and this is the number. Both sizes
    # print; nobody has to remember which is which.
    if not only or only in ("nba", "wnba"):
        print("\n  Raw vs combiner, same ESPN headshot (decides whether the")
        print("  board should resize faces the way it resizes logos):")
        raw = "https://a.espncdn.com/i/headshots/nba/players/full/1966.png"
        sized = ("https://a.espncdn.com/combiner/i?img=/i/headshots/nba/"
                 "players/full/1966.png&w=112&h=112")
        for label, url in (("raw full", raw), ("combiner 112", sized)):
            verdict, detail = _get(url)
            print(f"    {verdict:<10} {label:<14} {detail}")


def _teams_for(sport: str) -> list[str]:
    """Every abbreviation the site actually uses for a sport, from the same
    teams_*.js the page reads — so the audit covers what will be rendered,
    not a list kept in step by hand."""
    import re
    fname = {"nfl": "teams.js"}.get(sport, f"teams_{sport}.js")
    path = os.path.join(ROOT, "web", "js", fname)
    if not os.path.exists(path):
        return []
    src = open(path, encoding="utf-8").read()
    return sorted(set(re.findall(r'^\s{2}"([A-Za-z0-9]{2,5})":\s*\{', src, re.M)))


#: Mirrors ESPN_ABBR in web/js/visuals.js. Two copies is a real hazard, and
#: `--audit` is exactly what catches them drifting: it reads the map out of
#: the JS rather than trusting this comment.
def _js_abbr_map() -> dict:
    import json
    import re
    src = open(os.path.join(ROOT, "web", "js", "visuals.js"),
               encoding="utf-8").read()
    m = re.search(r"const ESPN_ABBR = (\{.*?\n\};)", src, re.S)
    if not m:
        return {}
    body = m.group(1).rstrip(";")
    body = re.sub(r"(\w+):", r'"\1":', body)          # bare keys -> quoted
    body = re.sub(r",(\s*[}\]])", r"\1", body)        # trailing commas
    try:
        return json.loads(body)
    except ValueError:
        return {}


def audit(only: str | None) -> int:
    """Fetch the logo for EVERY team the site can render, and name the misses.

    The map in visuals.js is recalled for everything the probe did not
    test, which is most of it. A miss is not a crash — the <img> removes
    itself and the monogram chip shows — but it is a team quietly wearing
    the old mark forever, which nobody would notice on a board they do not
    open. This is the measurement that replaces the memory.
    """
    amap = _js_abbr_map()
    if not amap:
        print("  could not read ESPN_ABBR out of visuals.js — audit aborted")
        return 2
    bad = 0
    for sport, (key, _) in SPORTS.items():
        if only and sport != only:
            continue
        teams = _teams_for(sport)
        if not teams:
            print(f"\n  {sport.upper()}: no teams file, skipped")
            continue
        misses = []
        for ab in teams:
            espn = amap.get(sport, {}).get(ab.upper(), ab.lower())
            url = (f"https://a.espncdn.com/combiner/i?img=/i/teamlogos/{key}"
                   f"/500/{espn}.png&w=96&h=96")
            verdict, detail = _get(url)
            if verdict != "OK ":
                misses.append((ab, espn, detail))
        print(f"\n  {sport.upper()}: {len(teams) - len(misses)}/{len(teams)} "
              f"logos resolve")
        for ab, espn, detail in misses:
            print(f"    MISS  {ab:<5} -> tried '{espn}'   {detail}")
        bad += len(misses)
    print(f"\n  {bad} miss(es) total.")
    if bad:
        print("  Send this and I will correct the map. Every miss renders the")
        print("  monogram chip in the meantime, which is the old behaviour.")
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--probe", action="store_true",
                   help="try every candidate URL and report what answered")
    p.add_argument("--audit", action="store_true",
                   help="fetch the logo for EVERY team the site renders and "
                        "name the abbreviations that miss")
    p.add_argument("--sport", default="",
                   help="limit to one sport (nfl, mlb, nba, wnba, cfb)")
    a = p.parse_args(argv)
    if not (a.probe or a.audit):
        p.print_help()
        return 1
    only = a.sport.lower() or None
    if a.audit:
        print("=" * 78)
        print("LOGO AUDIT — every abbreviation the site can render")
        print("=" * 78)
        return audit(only)
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
