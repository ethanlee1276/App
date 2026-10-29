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


# ─── the research's two follow alerts (2026-10-29) ──────────────────────────
#: A followed team's game in its last LATE_SHARE of regulation (the 9th
#: inning on, in baseball) within one score is a close game (topic
#: "closegame", the same message id as a ticket's, so a member with both
#: hears it once). Apple's TV app had editors flag exactly these.
CLOSE_TOPIC = "closegame"
TODAY_TOPIC = "today"
#: The morning slate goes from this hour where the member is (their
#: Settings' zone, Eastern when they named none), once a day.
TODAY_HOUR = 10


def late_and_close(league: str, live: dict) -> bool:
    """In its last minutes (or the 9th inning on) and within one score."""
    from engine import slipwatch as SW
    from engine.proplive import share_left
    lg = str(league or "").lower()
    if lg not in SW.ONE_SCORE or str((live or {}).get("state") or "").lower() != "live":
        return False
    try:
        margin = abs(float(live.get("home_score")) - float(live.get("away_score")))
    except (TypeError, ValueError):
        return False
    if margin > SW.ONE_SCORE[lg]:
        return False
    if lg == "mlb":
        try:
            return int(live.get("period") or 0) >= 9
        except (TypeError, ValueError):
            return False
    f = share_left(lg, live)
    return f is not None and 0 < f <= SW.LATE_SHARE


def closegame_pass(conn, data_dir: Path | None = None, now: float | None = None) -> int:
    """Tell each account whose phone carries "closegame" about a followed
    team's game that is late and close. Returns how many were told."""
    from engine.socialfeed import _read
    PM.ensure_tables(conn)
    t = time.time() if now is None else float(now)
    users = conn.execute("SELECT DISTINCT user_id FROM push_subs WHERE user_id IS NOT NULL "
                         "AND (',' || topics || ',') LIKE ?", (f"%,{CLOSE_TOPIC},%",)).fetchall()
    if not users:
        return 0
    base = Path(data_dir) if data_dir else PM.WEB / "data"
    close = []
    for lg in LEAGUES:
        for g in (_read(base / f"live_{lg}.json") or {}).get("games") or []:
            live = g.get("live") or {}
            if late_and_close(lg, live):
                away, home = str(g.get("away") or "").upper(), str(g.get("home") or "").upper()
                event = str(g.get("event_id") or g.get("game_pk") or "")
                close.append((lg, event, away, home, live))
    told = 0
    for (uid,) in users:
        mine = follows(conn, uid)
        for lg, event, away, home, live in close:
            if (lg, DV.canonical(lg, away)) not in mine and (lg, DV.canonical(lg, home)) not in mine:
                continue
            score = f"{away} {live.get('away_score')} – {live.get('home_score')} {home}"
            clock = live.get("clock") or ""
            told += PM.tell(conn, uid, f"closegame:{lg}:{away}@{home}", CLOSE_TOPIC,
                            f"Close game: {score}" + (f", {clock}" if clock else ""),
                            "Final minutes, within one score.", f"/#pbp/{lg}/{event}" if event else "/#live",
                            now=t)
    return told


def today_pass(conn, data_dir: Path | None = None, now: float | None = None) -> int:
    """The morning slate (topic "today"): once a day, from TODAY_HOUR where
    the member is, the games their teams play today, with the times. A day
    with none of their teams playing says nothing."""
    from engine import engagement as EN
    from engine import pushalerts as PA
    PM.ensure_tables(conn)
    t = time.time() if now is None else float(now)
    users = conn.execute("SELECT DISTINCT user_id FROM push_subs WHERE user_id IS NOT NULL "
                         "AND (',' || topics || ',') LIKE ?", (f"%,{TODAY_TOPIC},%",)).fetchall()
    if not users:
        return 0
    games = None
    told = 0
    for (uid,) in users:
        try:
            from zoneinfo import ZoneInfo
            local = __import__("datetime").datetime.fromtimestamp(t, ZoneInfo(PA.member_tz(conn, uid) or "America/New_York"))
        except Exception:                                     # noqa: BLE001 — an unknown zone: Eastern
            local = EN.ACT.eastern(t)
        if local.hour < TODAY_HOUR:
            continue
        if games is None:
            games = EN._today_games(Path(data_dir) if data_dir else PM.WEB / "data", t)
        mine = follows(conn, uid)
        theirs = sorted((g for g in games if (g[0], DV.canonical(g[0], g[2])) in mine
                         or (g[0], DV.canonical(g[0], g[3])) in mine), key=lambda g: g[4])
        if not theirs:
            continue
        line = ", ".join(f"{a} @ {h} {EN._clock(st).replace(' ET', '')}" for _lg, _ev, a, h, st in theirs[:3])
        body = ""
        for x in brief_extras(theirs, mine, Path(data_dir) if data_dir else PM.WEB / "data"):
            if len(body) + 1 + len(x) <= BRIEF_CHARS:               # whole sentences only, on a lock screen
                body = f"{body} {x}".strip()
        told += PM.tell(conn, uid, f"today:{local.date().isoformat()}", TODAY_TOPIC,
                        f"Today: {line}"[:120] + (" ET" if len(theirs) <= 3 else " ET and more"),
                        body or "Your teams’ games — the slate, the chats and Call it.", "/#live", now=t)
    return told


#: The statuses the morning brief names, most serious first.
BRIEF_STATUSES = ("OUT", "DOUBTFUL", "QUESTIONABLE")
#: What a push body holds (pushmine.tell keeps 240), and the line moves named.
BRIEF_CHARS = 240
BRIEF_MOVES = 2


def brief_extras(games: list, mine: set, data_dir: Path) -> list:
    """The morning brief's own lines past the slate (the second paper: "each
    user's games, model edges, injuries and line moves, every morning"):
    who on their teams is out, doubtful or questionable; a spread that has
    moved a point or more since it opened; and how many picks the board has
    on those games — a count, the pick itself a member's."""
    from engine import gate
    from engine import newsalerts as NA
    from engine import socialfeed as SF
    out = []
    hurt: dict = {}
    for _k, (lg, name, team, status, _inj) in NA.board(data_dir).items():
        if status in BRIEF_STATUSES and (lg, DV.canonical(lg, team.upper())) in mine:
            hurt.setdefault(status, []).append(f"{name} ({team.upper()})")
    said = [f"{st.title()}: {', '.join(sorted(hurt[st])[:2])}." for st in BRIEF_STATUSES if hurt.get(st)]
    if said:
        out.append(" ".join(said[:2]))
    picks = moves = 0
    for lg, _ev, away, home, _st in games:
        name = SF.SPORT_FILE.get(lg)
        if not name:
            continue
        public = SF._read(Path(data_dir) / name) or {}
        for g in public.get("games") or []:
            if str(g.get("home") or "").upper() != home or str(g.get("away") or "").upper() != away:
                continue
            lo = g.get("line_open") or {}
            try:
                was, move = float(lo["spread_home"]), float(lo["spread_move"])
            except (KeyError, TypeError, ValueError):
                continue
            if abs(move) >= 1 and moves < BRIEF_MOVES:
                fmt = lambda x: "PK" if abs(x) < 0.25 else f"{'+' if x > 0 else '−'}{abs(x):g}"   # noqa: E731
                out.append(f"{home} opened {fmt(was)}, now {fmt(was + move)}.")
                moves += 1
        private = SF._read(gate.board_source(Path(data_dir) / name)) or {}
        picks += sum(1 for r in private.get("recommendations") or []
                     if isinstance(r, dict) and str(r.get("team") or "").upper() in (away, home)
                     and str(r.get("opponent") or "").upper() in (away, home, ""))
    if picks:
        out.append(f"{picks} pick{'s' if picks != 1 else ''} on {'this game' if len(games) == 1 else 'these games'} — members see them.")
    return out
