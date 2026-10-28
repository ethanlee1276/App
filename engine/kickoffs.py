"""Kickoff by push: a game of a team you follow is about to start.

Ethan, 2026-10-28: "keep building and adding more features ... we want to
keep user retainment". The pair to engine/finals ("Final scores of games I
follow") and the automatic cousin of the game chat's Remind me bell
(engine/gamechat): the push every sports app sends first, "CHI @ GB starts
in 10 minutes", a tap into the game, its chat and Call it, where the rest
of the night happens.

Topic "kickoff", its own switch on the Alerts page. Public facts (the two
teams and the start), so anyone who follows gets it, member or not, and it
carries no pick.

IN ITS OWN LEAGUE. A followed team is the page's "nfl:MIA" from the
account's synced settings (engine/alerts.team_leagues), or a team watch
whose abbreviation only one league uses (engine/divisions). A watch on
"MIA" that never said which league is the Dolphins, the Heat and the
Marlins at once, and a push before every one of their games is noise, so
it gets none.

ONCE A GAME, about LEAD_S before the fast scoreboard's start time
(live_{lg}.json, the one the game chat's bell reads), never for a game
already under way. A reader who rang the game's own bell hears that one
instead. Quiet hours do not hold it, like the bell (it was asked for).

Run from engine/pushmine.run_once's minute. Standard library only.
"""
from __future__ import annotations

import time
from pathlib import Path

from engine import alerts as AL
from engine import divisions as DV
from engine import pushmine as PM

TOPIC = "kickoff"
#: Told the first minute a game is this close to its start.
LEAD_S = 10 * 60
#: The scoreboards read, in the game chat's own league codes.
LEAGUES = ("nfl", "cfb", "nba", "wnba", "nhl", "mlb")
#: A scoreboard's word for a game that has begun or ended.
UNDER_WAY = ("live", "in", "final", "post")


def _one_league(abbr: str) -> str | None:
    """The league a bare abbreviation names, when only one of ours uses it."""
    hits = [lg for lg, teams in DV.MAPS.items()
            if abbr in teams or abbr in (DV.ALIASES.get(lg) or {})]
    return hits[0] if len(hits) == 1 else None


def follows(conn, user_id) -> set:
    """{("nfl", "GB")}: the teams an account follows, each in its league,
    spelled the way that league's map is keyed (ESPN's hockey "LA" is the
    Kings' "LAK")."""
    named = AL.team_leagues(conn, user_id)
    out = {(lg, DV.canonical(lg, abbr)) for abbr, lgs in named.items() for lg in lgs}
    for w in AL.list_watches(conn, user_id):
        abbr = str(w.get("value") or "").strip().upper()
        if w.get("kind") != "team" or not abbr or abbr in named:
            continue
        lg = _one_league(abbr)
        if lg:
            out.add((lg, DV.canonical(lg, abbr)))
    return out


def _games(data_dir: Path, t: float) -> list:
    """(league, event id, away, home, start) for every game starting within
    LEAD_S that has not begun."""
    from engine.gamechat import _when
    from engine.socialfeed import _read
    out = []
    for lg in LEAGUES:
        for g in (_read(data_dir / f"live_{lg}.json") or {}).get("games") or []:
            live = g.get("live") or {}
            start = _when(live.get("start_time"))
            event = str(g.get("event_id") or g.get("game_pk") or "")
            if (start is None or not event or str(live.get("state") or "").lower() in UNDER_WAY
                    or not 0 < start - t <= LEAD_S):
                continue
            out.append((lg, event, str(g.get("away") or "").upper(), str(g.get("home") or "").upper(), start))
    return out


def kickoff_pass(conn, data_dir: Path | None = None, now: float | None = None) -> int:
    """Tell each account whose phone carries the topic about a followed
    team's game starting in the next LEAD_S. Returns how many were told."""
    PM.ensure_tables(conn)
    t = time.time() if now is None else float(now)
    games = _games(Path(data_dir) if data_dir else PM.WEB / "data", t)
    if not games:
        return 0
    users = conn.execute("SELECT DISTINCT user_id FROM push_subs WHERE user_id IS NOT NULL "
                         "AND (',' || topics || ',') LIKE ?", (f"%,{TOPIC},%",)).fetchall()
    told = 0
    for (uid,) in users:
        mine = follows(conn, uid)
        for lg, event, away, home, start in games:
            if (lg, DV.canonical(lg, away)) not in mine and (lg, DV.canonical(lg, home)) not in mine:
                continue
            room = f"{lg}_{event}"
            if conn.execute("SELECT 1 FROM push_mine WHERE user_id=? AND id=?", (uid, f"remind:{room}")).fetchone():
                continue
            try:
                if conn.execute("SELECT 1 FROM chat_reminders WHERE user_id=? AND room=?", (uid, room)).fetchone():
                    continue                                  # the bell they rang tells them
            except Exception:                                 # noqa: BLE001 — no bells yet on this database
                pass
            mins = max(1, round((start - t) / 60))
            told += PM.tell(conn, uid, f"kickoff:{room}", TOPIC,
                            f"{away} @ {home} starts in {mins} minute{'' if mins == 1 else 's'}",
                            "Tap for the game, its chat and Call it.", f"/#pbp/{lg}/{event}", now=t)
    return told
