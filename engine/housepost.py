"""The house posts the moment: a big play, dropped into its game's chat.

    python3 -m engine.housepost      # read-only: who would post, and what is on file

The ideas list (2026-10-25, "the live game as a place to be", item 2): a
play rated 8 or more drops into the game's chat as a message from the
site's own account, so the whole room reacts to the same thing at the
same time — Real's core loop, and the reason a quiet room still has
something to answer.

WHO POSTS: the site's own account — a verified profile holding a "qellys"
name (engine/socialfeed `_official`, handed out only by the owner's claim
command), never the founder's own account. No such account, no posts:
nothing is ever said in a made-up name, and the runbook's ES block names
the one command that sets it up.

WHAT IT SAYS: the moment's own line (engine/pushmine.clutch_line — the
score after it, who did it and when, the rating), posted on the play's own
thread. The chat shows it in the room with the play to tap (js/chat.js
"on <play>"), and the replies stay on that play. Every word is the game
file's: the score, the names, the feed's win chance. No pick, no price.

ONCE: a game's first look is its baseline — the plays already on it are
marked, not posted, so a restart late in a game does not replay the first
three quarters — and at most PER_GAME posts a game.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from . import gamechat as GC
from . import pushmine as PM

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

#: A play rated this high is posted (about a 30-point swing in the win
#: chance where the feed has one); a walk-off always is.
HOUSE_MIN = 8.0
#: The most one game's room hears from the house: a wild finish is a few
#: posts, not a stream.
PER_GAME = 6
#: A deep file not written for this long is not a game in progress.
FRESH_S = 15 * 60
KEEP_S = 2 * 86400

_mtimes: dict = {}


def ensure_tables(conn) -> None:
    GC.ensure_tables(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS chat_house_seen (game TEXT NOT NULL, play TEXT NOT NULL, "
                 "at REAL NOT NULL, posted INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (game, play))")


def house_id(conn) -> int | None:
    """The site's own account, or None. Verified, a "qellys" name, and not
    the founder's own profile."""
    from . import socialfeed as SF
    SF.ensure_tables(conn)
    r = conn.execute("SELECT user_id FROM feed_profiles WHERE verified = 1 AND COALESCE(founder, 0) = 0 "
                     "AND lower(handle) LIKE '%qellys%' ORDER BY user_id LIMIT 1").fetchone()
    return int(r[0]) if r else None


def big_plays(doc: dict) -> list:
    """``[(key, play)]``: each play on a deep file big enough to post, keyed
    the way the chat keys a play's thread (app.js chatPlayKey)."""
    if doc.get("league") == "mlb":
        rows = [e for e in doc.get("events") or [] if isinstance(e, dict) and e.get("kind") == "atbat"]
        key = (lambda r: f"ab{r['at_bat']}" if r.get("at_bat") is not None else "")
    else:
        rows = [p for p in doc.get("plays") or [] if isinstance(p, dict)]
        key = (lambda r: str(r.get("id") or ""))
    out = []
    for r in rows:
        k = key(r)
        if not k or not GC.PLAY_RE.match(k):
            continue
        try:
            big = float(r.get("rating") or 0) >= HOUSE_MIN
        except (TypeError, ValueError):
            big = False
        if big or r.get("swing") == "walkoff":
            out.append((k, r))
    return out


def line(doc: dict, play: dict) -> str:
    title, body = PM.clutch_line(doc, play)
    return f"{title}. {body}"[:GC.MAX_BODY]


def run(conn, pbp_dir: Path | None = None, now: float | None = None) -> int:
    """Post every new big moment on a game in progress; how many went."""
    ensure_tables(conn)
    t = time.time() if now is None else now
    conn.execute("DELETE FROM chat_house_seen WHERE at < ?", (t - KEEP_S,))
    hid = house_id(conn)
    base = Path(pbp_dir) if pbp_dir else WEB / "data" / "pbp"
    posted = 0
    for path in sorted(base.glob("*.json")) if base.is_dir() else []:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if t - mtime > FRESH_S or _mtimes.get(str(path)) == mtime:
            continue
        try:
            doc = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        _mtimes[str(path)] = mtime
        game = f"{doc.get('league')}_{doc.get('event_id')}"
        if not GC.room_ok(game):
            continue
        first = conn.execute("SELECT 1 FROM chat_house_seen WHERE game = ? LIMIT 1", (game,)).fetchone() is None
        seen = {r[0] for r in conn.execute("SELECT play FROM chat_house_seen WHERE game = ?", (game,))}
        told = conn.execute("SELECT COUNT(*) FROM chat_house_seen WHERE game = ? AND posted = 1",
                            (game,)).fetchone()[0]
        conn.execute("INSERT OR IGNORE INTO chat_house_seen (game, play, at) VALUES (?, '', ?)", (game, t))
        for key, play in big_plays(doc):
            if key in seen:
                continue
            say = not first and hid is not None and told < PER_GAME
            conn.execute("INSERT OR IGNORE INTO chat_house_seen (game, play, at, posted) VALUES (?, ?, ?, ?)",
                         (game, key, t, int(say)))
            if not say:
                continue
            conn.execute("INSERT INTO chat_msgs (room, user_id, body, play, created_at) VALUES (?,?,?,?,?)",
                         (game, hid, line(doc, play), key, t))
            told += 1
            posted += 1
        conn.commit()
    return posted


def run_once(connect=None, now: float | None = None, web: Path = WEB) -> int:
    """The minute's pass, from launch.py's slip-watch loop."""
    if connect is None:
        import os
        from . import accounts, modelstate
        if os.environ.get(modelstate.ENV_VAR):        # a replay never touches the live rooms
            return 0
        connect = accounts.connect
    conn = connect()
    try:
        return run(conn, Path(web) / "data" / "pbp", now=now)
    finally:
        conn.close()


def main() -> int:
    from . import accounts
    try:
        conn = sqlite3.connect(f"file:{accounts.DB_PATH}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        print(f"No accounts database to read ({exc}).")
        return 0
    try:
        try:
            hid = house_id(conn)
        except sqlite3.Error:
            hid = None
        print("The site's own account: " + (f"account {hid} — big plays post as it."
                                             if hid else "NONE — nothing posts (runbook ES says how to set it up)."))
        try:
            rows = conn.execute("SELECT game, COUNT(*), SUM(posted) FROM chat_house_seen WHERE play <> '' "
                                "GROUP BY game ORDER BY MAX(at) DESC LIMIT 10").fetchall()
        except sqlite3.Error:
            rows = []
        for game, n, p in rows:
            print(f"  {game}: {n} big play(s) seen, {int(p or 0)} posted")
        if not rows:
            print("  No game's big plays on file yet.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
