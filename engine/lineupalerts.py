"""Lineup alerts: a starter in your lineup who will not play, by push.

Ethan, 2026-10-27: "make sure … the fantasy room is actually a useful tool
and doing what it's supposed to be". Every fantasy app guards against one
mistake above all: a starter who is out, or on a bye, left in the lineup
(docs/FANTASY.md, item 7). The to-do list on the league desk says it, but
only to someone who opens the desk; this knocks the phone.

WHAT IT CHECKS, every pushmine.LINEUP_EVERY_S, for each account that turned "My
fantasy lineup" on: the Sleeper league its league desk last opened (kept
in `push_lineup_leagues` only while the switch is on), the lineup actually
set there (the roster's `starters`, Sleeper's own), and each starter
against this week's file (fantasyweek: its byes and its injury
designations) and Sleeper's own injury status. A starter whose team is on
a bye, or who is Out, on IR or suspended, or Doubtful (usually sits), is
told once a week per reason.

WHAT IT SAYS: the player's name and his designation, both on the public
injury report, and that he is in your lineup, which is yours. Never a
projection or who should replace him: that is the desk's, a tap away.

Sleeper only: its rosters are public. Standard library only.
"""
from __future__ import annotations

import json
import re
import time

SLEEPER_BASE = "https://api.sleeper.app/v1/"
#: Designations that mean he will not play, and what each reads as.
OUT = {"OUT": "out", "IR": "on IR", "INJURED RESERVE": "on IR", "SUSPENDED": "suspended", "SUS": "suspended",
       "PUP": "on the PUP list", "NFI": "on the NFI list", "INACTIVE": "inactive", "NA": "not with the team"}
#: Usually sits: told, and said as "doubtful".
DOUBTFUL = {"DOUBTFUL": "doubtful", "D": "doubtful"}


def _grab(path: str, ttl: int):
    """One Sleeper read through the server's own cache files (the same
    names server.sleeper_cache_name gives them)."""
    from engine.sources.fetch import fetch_text
    name = "sleeper_" + re.sub(r"[^A-Za-z0-9]+", "_", path) + ".json"
    return json.loads(fetch_text(SLEEPER_BASE + path, name, ttl=ttl))


def why_not(name: str, team: str | None, *, byes=(), listed: dict | None = None,
            sleeper_status: str | None = None) -> str | None:
    """Why this starter will not play, in words ("on a bye", "out",
    "doubtful"), or None. The week file's designation first, Sleeper's
    status when the week file has none."""
    if team and team in set(byes or ()):
        return "on a bye"
    status = str(((listed or {}).get(name) or {}).get("status") or sleeper_status or "").strip().upper()
    return OUT.get(status) or DOUBTFUL.get(status)


def starters_out(starters: list, *, byes=(), listed: dict | None = None) -> list:
    """[(name, why)] for the starters who will not play. ``starters`` is
    [{player, team, status}] (status: Sleeper's injury_status)."""
    from engine.backtest import _norm
    norm = {_norm(k): v for k, v in (listed or {}).items()}
    out = []
    for s in starters or []:
        name = s.get("player")
        if not name:
            continue
        why = why_not(_norm(name), s.get("team"), byes=byes, listed=norm, sleeper_status=s.get("status"))
        if why:
            out.append((name, why))
    return out


def message(league: str, outs: list) -> tuple[str, str]:
    """(title, body): the names and the designations, never a number."""
    where = f"your {league} lineup" if league else "your lineup"
    if len(outs) == 1:
        name, why = outs[0]
        # "Still in", not "He is in": a team defense gets this too.
        return f"{name} is {why}", f"Still in {where}. Tap to see who to start instead."[:240]
    listed = ", ".join(f"{n} ({w})" for n, w in outs[:-1]) + f" and {outs[-1][0]} ({outs[-1][1]})"
    return (f"{len(outs)} of your starters won’t play",
            f"{listed} are in {where}. Tap to see who to start instead."[:240])


def _roster_starters(league_id: str, sleeper_user: str, grab) -> tuple[dict, list, int]:
    league = grab(f"league/{league_id}", 600) or {}
    rosters = grab(f"league/{league_id}/rosters", 300) or []
    players = grab("players/nfl", 86400) or {}
    mine = next((r for r in rosters if str(r.get("owner_id") or "") == str(sleeper_user)
                 or str(sleeper_user) in [str(x) for x in r.get("co_owners") or []]), None)
    starters = []
    for pid in (mine or {}).get("starters") or []:
        p = players.get(str(pid)) or {}
        name = " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
        if name:
            starters.append({"player": name, "team": str(p.get("team") or "").upper() or None,
                             "status": p.get("injury_status")})
    week = int((league.get("settings") or {}).get("leg") or 0)
    return league, starters, week


def lineup_pass(conn, now: float | None = None, grab=None, week_doc: dict | None = None) -> int:
    """Queue a lineup alert for each opted-in account whose lineup holds a
    starter who will not play. Returns how many were told. An account
    whose switch is off has its league forgotten here."""
    from engine import pushmine as PM
    from engine.divisions import canonical
    PM.ensure_tables(conn)
    t = time.time() if now is None else now
    PM.lineup_forget(conn)
    rows = conn.execute("SELECT user_id, league_id, sleeper_user FROM push_lineup_leagues").fetchall()
    if not rows:
        return 0
    # One read of each path a pass: the players file is five megabytes, and
    # every account in the pass shares it.
    read, memo = grab or _grab, {}

    def grab(path, ttl):
        if path not in memo:
            memo[path] = read(path, ttl)
        return memo[path]
    if week_doc is None:
        from engine import fantasyweek
        week_doc = fantasyweek.load()
        week_doc = week_doc if fantasyweek.current(week_doc) else {}
    told = 0
    for uid, league_id, sleeper_user in rows:
        try:
            league, starters, week = _roster_starters(league_id, sleeper_user, grab)
        except Exception:                                     # noqa: BLE001 — Sleeper down: next pass
            continue
        same = bool(week_doc) and week_doc.get("week") == week
        byes = {canonical("nfl", b) for b in (week_doc or {}).get("byes") or []} if same else set()
        for s in starters:
            s["team"] = canonical("nfl", s["team"]) if s.get("team") else None
        outs = starters_out(starters, byes=byes, listed=(week_doc or {}).get("listed") if same else None)
        if not outs or not week:
            continue
        title, body = message(str(league.get("name") or ""), outs)
        # Once a week per starter and reason: the same news is not told twice,
        # a new name or a worse designation is.
        import hashlib
        key = hashlib.sha1(";".join(sorted(f"{n}:{w}" for n, w in outs)).encode()).hexdigest()[:16]
        told += PM.tell(conn, uid, f"lineup:{league_id}:{week}:{key}", "lineup", title, body,
                        "/#fantasy", now=t)
    return told
