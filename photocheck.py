#!/usr/bin/env python3
"""Does every league's player card get its photo? Read-only, on the box.

    cd /srv/qellys && sudo -u qellys python3 photocheck.py
    cd /srv/qellys && sudo -u qellys python3 photocheck.py --sport nhl

Ethan, 2026-10-14: "why do baseball players have cool ass photos of
themselves but no one else does, fix that". Every chart now opens on his
card (js/carrychart.js `playerHero`), and its photo is the first of these
that answers: his league's action shot where it files one under his id
(MLB's and the NHL's, engine/photos), his cut-out headshot asked for at the
card's size, then the whole headshot. The NHL's address is the league's
documented `actionShot` field, and the card-size requests reuse shapes the
headshot probe (assets.py) verified at other sizes; none was seen answering
at these addresses, because the cloud container reaches none of these
hosts. This asks from the box.

For three regulars of each league with a face on file — the most games
this season, his face found the way his chart finds it (`statlogs.face`; a
fighter's off his ESPN id) — every address on his card in the order the
page asks, and what the server said: status, type and size. Each league
ends on the photo its cards draw. One GET per address, nothing kept,
nothing written. A 403 is not a verdict on the page: this asks as a Python
script, and a browser asks as itself.
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

LEAGUES = ("nfl", "cfb", "mlb", "nba", "wnba", "nhl", "ufc")
#: The card draws his photo 160px wide (carrychart.js `heroShots`: facePreview(full, 160)).
CARD_PX = 160
#: visuals.js's resizes, as `facePreview` splices them into a Cloudinary path.
FACE_TRANSFORM = "w_{W},h_{W},c_fill,g_face"
FACE_TRANSFORM_NFL = "w_{W}"
TIMEOUT = 15
#: Read at most this much of one photo (a whole NFL headshot runs 3 to 4 MB).
CAP = 8 * 1024 * 1024


def face_preview(url: str, px: int) -> str:
    """visuals.js `facePreview`: the address the page asks for at ``px``."""
    if not url:
        return url
    w = max(48, math.floor(px * 2 + 0.5))
    host = "a.espncdn.com"
    if host in url:
        if "/combiner/" in url:
            return url
        path = url[url.index(host) + len(host):].split("?")[0]
        return f"https://{host}/combiner/i?img={path}&w={w}&h={w}" if path else url
    marker = "/image/upload/"
    if marker not in url:
        return url
    head, tail = url.split(marker)[:2]
    pid = tail[tail.index("/") + 1:] if "/" in tail else tail
    tf = (FACE_TRANSFORM_NFL if "static.www.nfl.com" in url else FACE_TRANSFORM).format(W=w)
    return f"{head}{marker}f_auto,q_auto,{tf}/{pid}"


def card_shots(sport: str, face: str, action: str = "") -> list[tuple[str, str]]:
    """carrychart.js `heroShots`: ``[(which, address)]`` in the order his card asks."""
    from engine import photos
    action = action or photos.action_url(sport, face)
    out = [("action", action)] if action else []
    small = face_preview(face, CARD_PX)
    if small and small != face:
        out.append(("card size", small))
    if face:
        out.append(("whole", face))
    return out


def players(conn, sport: str, n: int = 3) -> list[tuple[str, str]]:
    """``[(name, face)]``: the league's regulars this season with a face on file."""
    if sport == "ufc":
        from engine.ufc import history
        rows = conn.execute(
            "SELECT fighter, MAX(fighter_id), MAX(date) AS d FROM ufc_fights WHERE COALESCE(fighter_id, '') != '' "
            "GROUP BY fighter ORDER BY d DESC LIMIT ?", (n * 5,)).fetchall()
        return [(f, history.FACE.format(aid=aid)) for f, aid, _d in rows if str(aid).isdigit()][:n]
    from engine import statlogs
    rows = conn.execute(
        "SELECT player FROM player_game_logs WHERE sport=? AND season=(SELECT MAX(season) FROM player_game_logs "
        "WHERE sport=?) GROUP BY player ORDER BY COUNT(DISTINCT game_id) DESC, player LIMIT 60",
        (sport, sport)).fetchall()
    out = []
    for (name,) in rows:
        face = statlogs.face(conn, sport, name)
        if face:
            out.append((name, face))
            if len(out) == n:
                break
    return out


def fetch(url: str) -> tuple[bool, str]:
    """(an image came back, what the server said). Never raises."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=TIMEOUT) as r:
            body = r.read(CAP)
            ctype = r.headers.get("Content-Type", "?")
            size = f"{len(body):,} b" + ("+" if len(body) >= CAP else "")
            return ctype.startswith("image/"), f"{r.status} {ctype} {size}"
    except urllib.error.HTTPError as exc:
        return False, f"{exc.code} {exc.reason}"
    except Exception as exc:                                       # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:60]}"


def report(conn, sports=LEAGUES, get=fetch, n: int = 3) -> list[str]:
    """The check's lines; ``get(url) -> (ok, said)`` asks for one photo."""
    out = ["player card photos — each card asks for these in turn and draws the first that answers"]
    for sport in sports:
        try:
            who = players(conn, sport, n)
        except sqlite3.Error as exc:
            out.append(f"\n{sport.upper()}: no players to read ({exc})")
            continue
        out.append(f"\n{sport.upper()}")
        if not who:
            out.append("   no regular with a face on file: every card draws his initials")
            continue
        drawn: dict = {}
        for name, face in who:
            out.append(f"   {name}")
            first = None
            for which, url in card_shots(sport, face):
                ok, said = get(url)
                out.append(f"      {which:<9} {'OK' if ok else 'no':<3}{said}   {url}")
                if ok and first is None:
                    first = which
            drawn[first or "initials"] = drawn.get(first or "initials", 0) + 1
        out.append("   → the cards draw: " + ", ".join(f"{k} for {v} of {len(who)}" for k, v in drawn.items()))
    return out


def main(argv=None) -> int:
    from engine import db
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    ap.add_argument("--sport", choices=LEAGUES)
    a = ap.parse_args(argv)
    conn = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    try:
        for line in report(conn, (a.sport,) if a.sport else LEAGUES):
            print(line)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
