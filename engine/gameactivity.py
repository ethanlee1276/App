"""A live game on the iPhone's lock screen and in its Dynamic Island.

Ethan, 2026-10-29: "keep users and having users come back to the app and
feel like they need to use our app when there's live games going on.
Because I know a lot of people will flock to Real or ESPN." The apps that
own a live game on a phone own it on the lock screen: ESPN, theScore, the
NBA's and Yahoo's all put the score there as a Live Activity, and the one
published measure of it (OneSignal's, a vendor's: 23.7% higher 30-day
retention for apps that use them) points the same way. docs/RETENTION.md.

The iOS app already puts a saved parlay there (engine/pushmine, the
ParlayActivity plugin). This is the same thing for a game: "On my lock
screen" on a game's page starts a Live Activity in the app (deploy/ios/
native, GameActivity), which hands the box the activity's own push token
(POST /api/push/game-activity). Every GAME_EVERY_S the box reads the
league's fast scoreboard (`live_{league}.json`, rewritten every twelve
seconds by livescore_build.py) and sends the activity its new score and
clock when they changed, and its end when the game is final. It shows the
public score, the clock and the feed's own line on the situation — never a
pick, which is the paid half.

What is kept, per member and game, until the game ends or twelve hours
pass (Apple ends an activity after eight): the activity's push token and
the last state sent. Account deletion takes it (engine/accounts).

Standard library only.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
#: The leagues with a fast scoreboard of their own.
LEAGUES = ("nfl", "cfb", "nba", "wnba", "nhl", "mlb")
#: Games a member can have on the lock screen at once (Apple allows a few;
#: the parlays' own cap is the same, engine/pushmine.MAX_ACTIVITIES).
MAX_GAMES = 5
#: The box forgets an activity this long after it started.
GAME_S = 12 * 3600
#: How often the pass looks (launch.py's game-activity thread).
GAME_EVERY_S = 20
EVENT_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def ensure_tables(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS push_game_activities (
        user_id INTEGER NOT NULL, game TEXT NOT NULL, token TEXT NOT NULL,
        last TEXT NOT NULL DEFAULT '', started REAL NOT NULL,
        PRIMARY KEY (user_id, game))""")
    conn.commit()


def _game(league: str, event: str) -> str | None:
    lg, ev = str(league or "").lower(), str(event or "").strip()
    return f"{lg}:{ev}" if lg in LEAGUES and EVENT_RE.match(ev) else None


def add(conn, user_id, league: str, event: str, token: str, now: float | None = None) -> tuple[int, dict]:
    """Keep a game's lock-screen token for this member."""
    ensure_tables(conn)
    game, token = _game(league, event), str(token or "").strip()
    if not game:
        return 400, {"error": "that is not a game"}
    if not (8 <= len(token) <= 200 and all(c in "0123456789abcdefABCDEF" for c in token)):
        return 400, {"error": "that is not a lock-screen token"}
    t = time.time() if now is None else float(now)
    conn.execute("DELETE FROM push_game_activities WHERE started < ?", (t - GAME_S,))
    n = conn.execute("SELECT COUNT(*) FROM push_game_activities WHERE user_id = ? AND game != ?",
                     (int(user_id), game)).fetchone()[0]
    if n >= MAX_GAMES:
        return 400, {"error": f"{MAX_GAMES} games on the lock screen is the most"}
    conn.execute("INSERT INTO push_game_activities (user_id, game, token, last, started) VALUES (?,?,?,'',?) "
                 "ON CONFLICT(user_id, game) DO UPDATE SET token = excluded.token, started = excluded.started",
                 (int(user_id), game, token, t))
    conn.commit()
    return 200, {"ok": True}


def remove(conn, user_id, league: str, event: str) -> tuple[int, dict]:
    ensure_tables(conn)
    conn.execute("DELETE FROM push_game_activities WHERE user_id = ? AND game = ?",
                 (int(user_id), _game(league, event) or ""))
    conn.commit()
    return 200, {"ok": True}


def _read(path: Path) -> dict:
    try:
        got = json.loads(Path(path).read_text(encoding="utf-8"))
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def find(blob: dict, event: str) -> dict | None:
    """The game on a fast scoreboard by the feed's own id."""
    for g in (blob or {}).get("games") or []:
        if str(g.get("event_id") or g.get("game_pk") or "") == str(event):
            return g
    return None


def _score(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def state(g: dict) -> dict:
    """The lock screen's numbers (the iOS app's GameAttributes.ContentState,
    field for field): both scores, where the game is, the clock as the
    scoreboard says it, and the feed's own line on the situation."""
    live = (g or {}).get("live") or {}
    st = str(live.get("state") or "pre").lower()
    status = "final" if st in ("final", "post") else "live" if st in ("live", "in") else "pre"
    clock = "Final" if status == "final" else " ".join(
        x for x in (str(live.get("period") or "").strip(), str(live.get("clock") or "").strip()) if x)
    if status == "pre":
        clock = str(live.get("detail") or "").strip()[:40] or "Not started"
    return {"away": _score(live.get("away_score")), "home": _score(live.get("home_score")),
            "status": status, "clock": clock[:40],
            "last": ("" if status == "pre" else str(live.get("detail") or "").strip())[:90],
            "poss": str(live.get("possession") or "").upper()[:6] if status == "live" else ""}


def update_pass(conn, data_dir: Path | None = None, cfg=None, live=None, now: float | None = None,
                log=print) -> dict:
    """Send each kept game its new score where it changed, and its end once
    final. Costs one query when nobody has a game on the lock screen."""
    out = {"games": 0, "sent": 0, "ended": 0, "gone": 0}
    t = time.time() if now is None else float(now)
    try:
        if conn.execute("SELECT 1 FROM push_game_activities LIMIT 1").fetchone() is None:
            return out
    except sqlite3.Error:
        return out                                   # no table: nobody ever kept a game
    conn.execute("DELETE FROM push_game_activities WHERE started < ?", (t - GAME_S,))
    conn.commit()
    from engine import webpush as W
    cfg = W.apns_config() if cfg is None else cfg
    if not cfg:
        return out
    rows = conn.execute("SELECT user_id, game, token, last FROM push_game_activities").fetchall()
    send = live or W.apns_live
    boards: dict = {}
    for user_id, game, token, last in rows:
        league, _, event = str(game).partition(":")
        if league not in boards:
            boards[league] = _read(Path(data_dir or DATA) / f"live_{league}.json")
        g = find(boards[league], event)
        if g is None:
            continue
        out["games"] += 1
        s = state(g)
        blob = json.dumps(s, sort_keys=True)
        if blob == last:
            continue
        final = s["status"] == "final"
        code = send(token, s, cfg, event="end" if final else "update", now=t)
        if code in (200, 201):
            if final:
                out["ended"] += 1
                conn.execute("DELETE FROM push_game_activities WHERE user_id = ? AND game = ?", (user_id, game))
            else:
                out["sent"] += 1
                conn.execute("UPDATE push_game_activities SET last = ? WHERE user_id = ? AND game = ?",
                             (blob, user_id, game))
        elif code in (400, 404, 410):
            out["gone"] += 1
            conn.execute("DELETE FROM push_game_activities WHERE user_id = ? AND game = ?", (user_id, game))
    conn.commit()
    if out["sent"] or out["ended"] or out["gone"]:
        log(f"  lock screens: {out['sent']} game update(s), {out['ended']} ended, {out['gone']} gone")
    return out


def run_once(connect=None, **kw) -> dict:
    """One pass over the accounts database (launch.py's thread)."""
    if connect is None:
        from engine import accounts
        connect = accounts.connect
    conn = connect()
    try:
        return update_pass(conn, **kw)
    finally:
        conn.close()
