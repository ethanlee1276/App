"""Faces on the first-scorer boards — the Long Shots page, every sport.

Ethan, 2026-11-04, a screenshot of NBA Long Shots (Precious Achiuwa +1400,
Andrew Wiggins +1000, each card an initials chip): "Also the long shot page
is missing headshots for every sport."

WHY THEY WENT. Until 2026-10-31 the Long Shots board was the anytime-
touchdown and home-run menu, built from the prop rows, and a prop row
carries its player's photo (the NFL's from nflverse's roster file, college's
from its roster feeds, the hoops leagues' from ESPN's box scores). On that
day Long Shots became first-scorer picks only (engine/firsttd for the NFL
and college, engine/firstbasket for the NBA), and those boards are built
from the first-scorer price list and the play files — neither of which has
a photo — so every card, every "who scores first" row and every "our
numbers" row drew its initials. The page has always drawn the face it is
handed (`longShotCard`: `headshot: r.headshot`); it was handed none.

WHERE THE FACE COMES FROM, in trust order:

1. The board's own rows. The same build already priced most of these
   players' other props, and those rows carry the photo under the same
   name the first-scorer price list uses (both come off the odds feed),
   on the same team.
2. The sport's stored photos (`rosters.face_map`: `player_assets`, which
   the hoops ingest, the hockey ingest and the daily face pass for the NFL
   write, and MLB's own roster ids), joined on the normalised name — the
   one join key the site uses everywhere, which folds case, accents,
   punctuation and suffixes and nothing else, so two players cannot share
   a face.

A name two different photos claim on the board and no team settles is left
alone: initials beat somebody else's face. A row that already has a face
keeps it. Never raises — a board with no faces is a board, a build that
stops over a photo is not.

The Record's finished picks and tickets get their faces the same way, off
the game's own report first (`record_faces`, step AIT, at the end).
"""

from __future__ import annotations

#: The first-scorer boards a build may carry, and their row lists.
BOARDS = ("first_td", "first_basket")
LISTS = ("picks", "rows", "ours")


def _norm(name: str) -> str:
    try:
        from .sources.oddsapi import normalize_name
        return normalize_name(name or "")
    except Exception:                                        # noqa: BLE001
        return str(name or "").strip().lower()


def _rows_with_faces(result: dict):
    """Every row on the board that may carry a photo."""
    yield from result.get("recommendations") or []
    yield from result.get("most_likely") or []
    yield from ((result.get("likely_board") or {}).get("rows") or [])
    yield from result.get("longshot_watch") or []
    yield from result.get("td_scenarios") or []
    for g in result.get("matchup_picks") or []:
        if isinstance(g, dict):
            yield from (g.get("td") or []) + (g.get("props") or [])
    for key in BOARDS:
        b = result.get(key) or {}
        for lst in LISTS:
            yield from b.get(lst) or []


def board_faces(result: dict) -> tuple[dict, dict]:
    """({(name, team): photo}, {name: photo}) off the board's own rows; a
    name with two different photos is in the first map only."""
    by_team: dict = {}
    by_name: dict = {}
    clash: set = set()
    for r in _rows_with_faces(result or {}):
        if not isinstance(r, dict):
            continue
        url = str(r.get("headshot") or "")
        name = _norm(r.get("player") or "")
        if not url.startswith("http") or not name:
            continue
        by_team.setdefault((name, str(r.get("team") or "")), url)
        if by_name.get(name, url) != url:
            clash.add(name)
        by_name.setdefault(name, url)
    for name in clash:
        by_name.pop(name, None)
    return by_team, by_name


def stored_faces(sport: str, conn=None) -> dict:
    """{normalised name: photo} from the sport's stored photos, or {}. A
    connection it had to open itself it closes.

    Its {} on failure is also what a sport with no stored photos answers,
    so a failure prints "stored photos unreadable (<sport>, <error>)" and
    an empty store prints nothing (tests/test_silent_failures)."""
    own = None
    try:
        from . import rosters
        if conn is None:
            from . import db
            conn = own = db.connect()
        return rosters.face_map(conn, sport) or {}
    except Exception as exc:                                 # noqa: BLE001
        print(f"  ⚠️  Long Shots faces: stored photos unreadable ({sport}, "
              f"{type(exc).__name__}: {exc})")
        return {}
    finally:
        if own is not None:
            try:
                own.close()
            except Exception:                                # noqa: BLE001
                pass


def fill(result: dict, sport: str, conn=None, stored: dict | None = None) -> int:
    """Put a photo on every first-scorer row without one; how many got one.

    ``stored``: the sport's stored photos, when the caller has them (tests);
    read off `rosters.face_map` otherwise, and only if a row still needs one.

    Its 0 on failure is also what a board whose rows all have faces
    answers, so a failure prints "Long Shots faces skipped (<sport>,
    <error>)"; a quiet board prints nothing (tests/test_silent_failures).
    """
    try:
        by_team, by_name = board_faces(result)
        rows = []
        for key in BOARDS:
            b = (result or {}).get(key) or {}
            for lst in LISTS:
                rows += b.get(lst) or []
        rows += (result or {}).get("long_shots") or []
        # The picks are rows of the same list, so one row is met twice.
        need = list({id(r): r for r in rows if isinstance(r, dict) and not r.get("headshot")}.values())
        if not need:
            return 0
        n = 0
        for r in need:
            name = _norm(r.get("player") or "")
            url = by_team.get((name, str(r.get("team") or ""))) or by_name.get(name)
            if not url:
                if stored is None:
                    stored = stored_faces(sport, conn)
                url = stored.get(name) or stored.get(r.get("player") or "")
            if url:
                r["headshot"] = url
                n += 1
        return n
    except Exception as exc:                                 # noqa: BLE001
        print(f"  ⚠️  Long Shots faces skipped ({sport}, {type(exc).__name__}: {exc})")
        return 0


# ---------------------------------------------------------------------------
# FACES ON THE RECORD'S PICKS AND TICKETS (step AIT, 28 November 2026). Ethan,
# with a screenshot of a finished game on the Record (Cardinals at Chiefs, its
# three-leg tickets each wearing three drawn helmets with initials): "Also fix
# how there is no headshots on the game report record page here". The Record
# and Report Picks read a finished game's picks and tickets back off the journal
# (engine/reportoutcome.for_games, the Record's newest tickets through
# engine/ledger._game_parlay_record), and the journal keeps each leg's player,
# club, market and line, never its photo. The page draws the face it is handed
# (js/settled.js) and was handed none. So each pick and leg is given one here,
# in trust order: the game's own report (the archived report and the tickets it
# kept at the start, whose rows carry the board's photo from that day), its
# club's photo before its name's, then the sport's stored photos
# (`rosters.face_map`), joined on the normalised name as `fill` joins them. A
# club's bet (a moneyline, a spread, a total) wears its club's mark on the page,
# not a face, and is left alone; a row that already has a face keeps it.
# ---------------------------------------------------------------------------

#: The journal's club bets (engine/ledger.GAME_MARKETS): a club or the game in place of a player.
CLUB_MARKETS = frozenset(("moneyline", "spread", "total", "team_total"))


def doc_faces(*docs) -> tuple[dict, dict]:
    """({(name, team): photo}, {name: photo}) off every row these documents hold that names a player and a
    photo (an archived report, the tickets it kept at the start), walked to a fixed depth; a name two photos
    claim is in the first map only."""
    by_team: dict = {}
    by_name: dict = {}
    clash: set = set()

    def walk(x, depth=0):
        if depth > 12:
            return
        if isinstance(x, dict):
            url, who = str(x.get("headshot") or ""), x.get("player")
            if url.startswith("http") and isinstance(who, str) and _norm(who):
                name = _norm(who)
                by_team.setdefault((name, str(x.get("team") or "")), url)
                if by_name.get(name, url) != url:
                    clash.add(name)
                by_name.setdefault(name, url)
            for v in x.values():
                walk(v, depth + 1)
        elif isinstance(x, list):
            for v in x:
                walk(v, depth + 1)
    for d in docs:
        walk(d)
    for name in clash:
        by_name.pop(name, None)
    return by_team, by_name


def _stored_read_only(sport: str) -> dict:
    """The sport's stored photos off the history, read-only (a page's answer takes no writer's locks); {} on
    a box with no history, where opening one would leave an empty file behind."""
    from pathlib import Path
    from . import db, rosters
    path = Path(db.DEFAULT_DB)
    if not path.is_file():
        return {}
    conn = db.read_only(path)
    try:
        return rosters.face_map(conn, sport) or {}
    finally:
        conn.close()


def record_faces(groups, sport: str, stored: dict | None = None) -> int:
    """A photo on each of the record's rows without one, group by group: ``groups`` holds (rows, known), a
    game's picks and its tickets' legs with `doc_faces` of its own report (None where there is none). The
    report's own photo first, its club's before its name's, then the sport's stored photos (``stored`` when
    the caller has them, as the tests do; read once, off `rosters.face_map`, only if a row still needs one).
    How many got one.

    Its 0 on failure is also what a record whose rows all have faces answers, so a failure prints "record
    faces skipped (<sport>, <error>)"; a quiet record prints nothing. A photo must never cost a page its
    record."""
    try:
        n, later = 0, []
        for rows, known in groups or []:
            by_team, by_name = known or ({}, {})
            for r in rows or []:
                if not isinstance(r, dict) or r.get("headshot") or not isinstance(r.get("player"), str):
                    continue
                if r.get("game") or str(r.get("market") or "").lower() in CLUB_MARKETS:
                    continue
                name = _norm(r["player"])
                if not name:
                    continue
                url = by_team.get((name, str(r.get("team") or ""))) or by_name.get(name)
                if url:
                    r["headshot"] = url
                    n += 1
                else:
                    later.append((r, name))
        if later:
            if stored is None:
                stored = _stored_read_only(sport)
            for r, name in later:
                url = str((stored or {}).get(name) or "")
                if url.startswith("http"):
                    r["headshot"] = url
                    n += 1
        return n
    except Exception as exc:                                 # noqa: BLE001
        print(f"  ⚠️  record faces skipped ({sport}, {type(exc).__name__}: {exc})")
        return 0
