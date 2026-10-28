"""Live game chat: a room for every game, a thread on every play.

Ethan, 2026-10-25: "my buddy was telling me about an app that is better
than ESPN ... it has like live chats on each game for the play-by-plays
... make it where we have like a live chat for each game so users can
talk about their props". The app is Real (Real Vault, Inc.), and the
pattern is theirs: the play-by-play is the spine of the conversation,
every play carries its own reaction counter and comment thread, and the
game has a room of its own around it. theScore pins the live scoreboard
over its game chat and lets a fan react to a play from inside it; Yahoo's
Game Discussions need an account to post, ask for the rules once, and
put Report on every comment; Sofascore and Real ask the room who wins.

WHAT A ROOM IS. ``{league}_{event}`` — the same key the deep play-by-play
file is named for (livescore_build.write_pbp, live_build.write_pbp), so
the page that draws a game's plays already holds its room's name. A
message is text (MAX_BODY), optionally ANCHORED to one play (``play``: the
play's own id off the deep file — that is the play's thread), optionally
CARRYING A BET the writer says they are on (``bet``: player, market,
side, line, price, book — their own words, never a row of ours, never a
link), optionally a reply to another message in the room.

THE FEED'S RULES, NOT NEW ONES (engine/socialfeed): a handle before the
first word, slurs refused and swearing masked for readers who did not ask
for it (engine/profanity), three reports hide a message, a block hides
two people from each other both ways, the founder hides or restores
anything, and anyone deletes their own. Reading needs nothing; writing,
reacting and voting need a free account.

NOTHING PAID PASSES THROUGH HERE. A message is what a reader typed; the
bet chip is what they say they bet. No board row is read, so no model
number — probability, edge, projection, tier — can ride along.

THE POLL IS CHEAP. A page asks every few seconds for messages after the
last id it holds and for counts that CHANGED since its last ask
(``since``): a reaction taken back is a row whose kind is emptied, not
deleted, so the change still carries a stamp. A quiet room answers with
two empty lists.
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from . import profanity

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"

ROOM_RE = re.compile(r"^(nfl|cfb|nba|wnba|nhl|mlb)_([0-9]{1,14})$")
#: A play's id as the deep files write it (ESPN's numeric ids, MLB's
#: at-bat index, the NHL feed's event id), with room for a ``:`` suffix.
PLAY_RE = re.compile(r"^[A-Za-z0-9:._-]{1,40}$")
MAX_BODY = 280
#: One message every few seconds, and a ceiling a minute — tighter for an
#: account under a day old, as the feed treats a new account's posts.
MSG_GAP_S = 3
MSGS_PER_MIN = 12
NEW_MSGS_PER_MIN = 5
NEW_ACCOUNT_S = 86400
REPORTS_TO_HIDE = 3
REPORT_REASONS = ("spam", "abuse", "hate", "scam", "other")
#: The four faces a message or a play can wear (Real's reaction counter,
#: theScore's cheer and boo). Codes on the wire, emoji on the page.
REACTIONS = ("fire", "wow", "lol", "ugh")
PAGE = 60
KEEP_DAYS = 14
#: The room against the math (2026-10-28): the who-wins vote's split is
#: marked at most once a minute, and a room hands back its last
#: VOTE_PATH_MAX marks — a game's worth at a busy minute.
VOTE_MARK_EVERY_S = 60
VOTE_PATH_MAX = 240
#: WATCH PARTIES (2026-10-28, docs/IDEAS.md): a private thread inside a
#: game's room for a group of friends, by invite link. An invite is a random
#: token; a party holds PARTY_MAX members, an account starts PARTY_PER_ROOM
#: in one game at most, and a party goes with the game's messages after
#: KEEP_DAYS. The room's rules are the party's: the same caps, the same
#: three reports, the same founder's switch.
PARTY_RE = re.compile(r"^[A-Za-z0-9_-]{8,40}$")
PARTY_MAX = 50
PARTY_PER_ROOM = 3
PARTY_NAME_MAX = 40
#: How long a page counts as "here" after its last ask.
HERE_S = 45
#: The most rooms one counts call may ask about (the Live tab's games).
MAX_ROOMS = 40

_HERE: dict = {}
_HERE_LOCK = threading.Lock()


def ensure_tables(conn) -> None:
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS chat_msgs (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        room       TEXT NOT NULL,
        user_id    INTEGER NOT NULL,
        body       TEXT NOT NULL DEFAULT '',
        play       TEXT NOT NULL DEFAULT '',
        bet        TEXT NOT NULL DEFAULT '',
        reply_to   INTEGER,
        created_at REAL NOT NULL,
        hidden     INTEGER NOT NULL DEFAULT 0
      );
      CREATE INDEX IF NOT EXISTS chat_msgs_room ON chat_msgs (room, id);
      CREATE INDEX IF NOT EXISTS chat_msgs_user ON chat_msgs (user_id, created_at);
      CREATE TABLE IF NOT EXISTS chat_reacts (
        msg_id     INTEGER NOT NULL,
        user_id    INTEGER NOT NULL,
        room       TEXT NOT NULL,
        kind       TEXT NOT NULL DEFAULT '',
        changed_at REAL NOT NULL,
        PRIMARY KEY (msg_id, user_id)
      );
      CREATE INDEX IF NOT EXISTS chat_reacts_room ON chat_reacts (room, changed_at);
      CREATE TABLE IF NOT EXISTS chat_play_reacts (
        room       TEXT NOT NULL,
        play       TEXT NOT NULL,
        user_id    INTEGER NOT NULL,
        kind       TEXT NOT NULL DEFAULT '',
        changed_at REAL NOT NULL,
        PRIMARY KEY (room, play, user_id)
      );
      CREATE INDEX IF NOT EXISTS chat_play_reacts_room ON chat_play_reacts (room, changed_at);
      CREATE TABLE IF NOT EXISTS chat_votes (
        room       TEXT NOT NULL,
        user_id    INTEGER NOT NULL,
        side       TEXT NOT NULL,
        changed_at REAL NOT NULL,
        PRIMARY KEY (room, user_id)
      );
      -- THE ROOM'S LINE THROUGH THE GAME (the room against the math): the
      -- vote's split as it stood, a mark a minute at most. Aggregates only,
      -- as the vote bar is: no user ids.
      CREATE TABLE IF NOT EXISTS chat_vote_marks (
        room TEXT NOT NULL,
        at   REAL NOT NULL,
        home INTEGER NOT NULL,
        away INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS chat_vote_marks_room ON chat_vote_marks (room, at);
      CREATE TABLE IF NOT EXISTS chat_reports (
        msg_id     INTEGER NOT NULL,
        user_id    INTEGER NOT NULL,
        reason     TEXT NOT NULL DEFAULT 'other',
        created_at REAL NOT NULL,
        PRIMARY KEY (msg_id, user_id)
      );
      -- WATCH PARTIES: who started one (user_id, cleared when they delete
      -- their account: the party stays for its friends), its name and its
      -- invite; and who is in it.
      CREATE TABLE IF NOT EXISTS chat_parties (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        room       TEXT NOT NULL,
        token      TEXT NOT NULL UNIQUE,
        name       TEXT NOT NULL,
        user_id    INTEGER NOT NULL,
        created_at REAL NOT NULL
      );
      CREATE INDEX IF NOT EXISTS chat_parties_room ON chat_parties (room, user_id);
      CREATE TABLE IF NOT EXISTS chat_party_members (
        party_id  INTEGER NOT NULL,
        user_id   INTEGER NOT NULL,
        joined_at REAL NOT NULL,
        PRIMARY KEY (party_id, user_id)
      );
      CREATE INDEX IF NOT EXISTS chat_party_members_user ON chat_party_members (user_id);
    """)
    # A party's messages are the room's rows with its id; the room's own are
    # 0. Added rather than declared (the table shipped first), and raced:
    # two first requests after a deploy both find the column missing.
    if "party" not in {r[1] for r in conn.execute("PRAGMA table_info(chat_msgs)")}:
        from .db import column_exists_or_raise
        try:
            conn.execute("ALTER TABLE chat_msgs ADD COLUMN party INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError as exc:
            column_exists_or_raise(exc)
    conn.execute("CREATE INDEX IF NOT EXISTS chat_msgs_party ON chat_msgs (party, id)")


def room_ok(room) -> bool:
    return bool(ROOM_RE.match(str(room or "")))


def _profile(conn, user_id):
    from . import socialfeed as SF
    return SF.profile_of(conn, user_id)


# ─── the game, read off its own fast file ───────────────────────────────────

def game_of(room: str, data_dir: Path | None = None) -> dict:
    """The room's game off the league's fast scoreboard (``live_{lg}.json``):
    its sides and state, or {} when the file does not carry it."""
    m = ROOM_RE.match(str(room or ""))
    if not m:
        return {}
    from .socialfeed import _read
    blob = _read((data_dir or DATA) / f"live_{m.group(1)}.json") or {}
    for g in blob.get("games") or []:
        if str(g.get("event_id") or g.get("game_pk") or "") == m.group(2):
            return {"home": g.get("home") or "", "away": g.get("away") or "",
                    "state": ((g.get("live") or {}).get("state") or "")}
    return {}


# ─── what a bet chip may say ────────────────────────────────────────────────

_SIDE_RE = re.compile(r"^[A-Za-z0-9 .'+-]{1,16}$")


def clean_bet(b) -> dict | None:
    """The writer's own bet, kept to the fields a chip shows. Strings are
    cut, numbers bounded, and nothing that could be a link survives —
    the chip is a claim in a chat, not a door to a book."""
    if not isinstance(b, dict):
        return None

    def s(k, n):
        v = re.sub(r"\s+", " ", str(b.get(k) or "")).strip()[:n]
        return "" if re.search(r"(https?:|www\.|\.com\b|[<>])", v, re.I) else v

    out = {"player": s("player", 60), "market": s("market", 40), "side": s("side", 16),
           "book": s("book", 24)}
    if out["side"] and not _SIDE_RE.match(out["side"]):
        out["side"] = ""
    try:
        line = float(b.get("line"))
        out["line"] = line if -1000 <= line <= 1000 else None
    except (TypeError, ValueError):
        out["line"] = None
    try:
        odds = int(float(b.get("odds")))
        out["odds"] = odds if (odds <= -100 or odds >= 100) and abs(odds) <= 100000 else None
    except (TypeError, ValueError):
        out["odds"] = None
    if not (out["player"] or out["market"]):
        return None
    if any(profanity.has_slur(out[k]) for k in ("player", "market", "book")):
        return None
    return {k: v for k, v in out.items() if v not in (None, "")}


# ─── writing ────────────────────────────────────────────────────────────────

def _cap(conn, user_id: int, now: float) -> str:
    last = conn.execute("SELECT MAX(created_at) FROM chat_msgs WHERE user_id=?",
                        (int(user_id),)).fetchone()[0]
    if last and now - float(last) < MSG_GAP_S:
        return "One message every few seconds."
    u = conn.execute("SELECT created_at FROM users WHERE id=?", (int(user_id),)).fetchone()
    young = bool(u) and (now - float(u["created_at"] or now)) < NEW_ACCOUNT_S
    cap = NEW_MSGS_PER_MIN if young else MSGS_PER_MIN
    n = conn.execute("SELECT COUNT(*) FROM chat_msgs WHERE user_id=? AND created_at>?",
                     (int(user_id), now - 60)).fetchone()[0]
    if n >= cap:
        return "Slow down — that is a lot of messages for one minute."
    return ""


def _prune(conn, now: float) -> None:
    old = now - KEEP_DAYS * 86400
    conn.execute("DELETE FROM chat_reacts WHERE msg_id IN (SELECT id FROM chat_msgs WHERE created_at<?)", (old,))
    conn.execute("DELETE FROM chat_reports WHERE msg_id IN (SELECT id FROM chat_msgs WHERE created_at<?)", (old,))
    conn.execute("DELETE FROM chat_msgs WHERE created_at<?", (old,))
    conn.execute("DELETE FROM chat_play_reacts WHERE changed_at<?", (old,))
    conn.execute("DELETE FROM chat_votes WHERE changed_at<?", (old,))
    conn.execute("DELETE FROM chat_vote_marks WHERE at<?", (old,))
    conn.execute("DELETE FROM chat_party_members WHERE party_id IN (SELECT id FROM chat_parties WHERE created_at<?)",
                 (old,))
    conn.execute("DELETE FROM chat_parties WHERE created_at<?", (old,))


def send(conn, user_id: int, room, body, play="", bet=None, reply_to=None,
         now: float | None = None, party: int = 0) -> tuple[int, dict]:
    ensure_tables(conn)
    now = time.time() if now is None else now
    room = str(room or "")
    if not room_ok(room):
        return 400, {"error": "That game has no room."}
    party = int(party or 0)
    if party and not _in_party(conn, user_id, party, room):
        return 403, {"error": "You are not in that watch party."}
    if not _profile(conn, user_id):
        return 409, {"error": "Pick a username first.", "need_handle": True}
    body = re.sub(r"[ \t]+", " ", str(body or "")).strip()[:MAX_BODY]
    chip = clean_bet(bet) if bet else None
    if not body and not chip:
        return 400, {"error": "Write something first."}
    why = profanity.check(body, "Your message")
    if why:
        return 400, {"error": why}
    play = str(play or "")
    if play and not PLAY_RE.match(play):
        play = ""
    why = _cap(conn, user_id, now)
    if why:
        return 429, {"error": why}
    parent = None
    if reply_to:
        p = conn.execute("SELECT id, play FROM chat_msgs WHERE id=? AND room=? AND party=? AND hidden=0",
                         (int(reply_to), room, party)).fetchone()
        if not p:
            return 404, {"error": "That message is gone."}
        parent = int(p["id"])
        # A reply stays in the thread it answers.
        play = play or str(p["play"] or "")
    cur = conn.execute("INSERT INTO chat_msgs (room, user_id, body, play, bet, reply_to, created_at, party) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       (room, int(user_id), body, play, json.dumps(chip) if chip else "", parent, now, party))
    mid = int(cur.lastrowid)
    if mid % 200 == 0:
        _prune(conn, now)
    _mention(conn, user_id, room, mid, body, party)
    conn.commit()
    return 200, {"ok": True, "id": mid}


MENTIONS_PER_MSG = 3


def _mention(conn, user_id, room: str, mid: int, body: str, party: int = 0) -> None:
    """@handle in a message (Social's own rule, socialfeed.MENTION_RE): each
    reader named hears it in their Activity, with the game to open — in a
    watch party, only its members; never the writer; a block stops it."""
    from . import socialfeed as SF
    if "@" not in (body or ""):
        return
    m = ROOM_RE.match(room)
    link = f"#pbp/{m.group(1)}/{m.group(2)}" if m else ""
    if party and link:
        # A party's words open the party (its invite link: a member
        # joining again is joining once).
        row = conn.execute("SELECT token FROM chat_parties WHERE id=?", (int(party),)).fetchone()
        link = f"{link}/party/{row['token']}" if row else link
    seen: set = set()
    try:
        for h in SF.MENTION_RE.findall(body)[:MENTIONS_PER_MSG]:
            uid = SF._uid_of(conn, h)
            if not uid or uid == int(user_id) or uid in seen:
                continue
            if party and not _in_party(conn, uid, party):
                continue
            seen.add(uid)
            # The message's id, negative, keeps each message's notice its
            # own without pointing at a feed comment.
            SF._notify(conn, uid, user_id, "chat_mention", comment_id=-int(mid), link=link, note=body)
    except sqlite3.OperationalError:
        return                                   # no Social tables here: nobody to name


def _unmention(conn, msg_id) -> None:
    """A message hidden or deleted takes its @mentions out of Activity."""
    try:
        conn.execute("DELETE FROM feed_notifs WHERE kind='chat_mention' AND comment_id=?", (-int(msg_id or 0),))
        conn.commit()
    except sqlite3.OperationalError:
        pass


def react(conn, user_id: int, msg_id, kind, now: float | None = None) -> tuple[int, dict]:
    """One face per reader per message; the same face again takes it back."""
    ensure_tables(conn)
    now = time.time() if now is None else now
    if kind not in REACTIONS:
        return 400, {"error": "Unknown reaction."}
    m = conn.execute("SELECT room, party FROM chat_msgs WHERE id=? AND hidden=0", (int(msg_id or 0),)).fetchone()
    if not m or (m["party"] and not _in_party(conn, user_id, m["party"])):
        return 404, {"error": "That message is gone."}
    was = conn.execute("SELECT kind FROM chat_reacts WHERE msg_id=? AND user_id=?",
                       (int(msg_id), int(user_id))).fetchone()
    new = "" if was and was["kind"] == kind else kind
    conn.execute("INSERT INTO chat_reacts (msg_id, user_id, room, kind, changed_at) VALUES (?,?,?,?,?) "
                 "ON CONFLICT(msg_id, user_id) DO UPDATE SET kind=excluded.kind, changed_at=excluded.changed_at",
                 (int(msg_id), int(user_id), m["room"], new, now))
    conn.commit()
    return 200, {"ok": True, "mine": new}


def react_play(conn, user_id: int, room, play, kind, now: float | None = None) -> tuple[int, dict]:
    """A face on a play (Real's counter): one per reader per play."""
    ensure_tables(conn)
    now = time.time() if now is None else now
    room, play = str(room or ""), str(play or "")
    if not room_ok(room) or not PLAY_RE.match(play):
        return 400, {"error": "That play has no thread."}
    if kind not in REACTIONS:
        return 400, {"error": "Unknown reaction."}
    was = conn.execute("SELECT kind FROM chat_play_reacts WHERE room=? AND play=? AND user_id=?",
                       (room, play, int(user_id))).fetchone()
    new = "" if was and was["kind"] == kind else kind
    conn.execute("INSERT INTO chat_play_reacts (room, play, user_id, kind, changed_at) VALUES (?,?,?,?,?) "
                 "ON CONFLICT(room, play, user_id) DO UPDATE SET kind=excluded.kind, changed_at=excluded.changed_at",
                 (room, play, int(user_id), new, now))
    conn.commit()
    return 200, {"ok": True, "mine": new}


def vote(conn, user_id: int, room, side, now: float | None = None,
         data_dir: Path | None = None) -> tuple[int, dict]:
    """Who wins? Open until the game is final; a reader may change their
    mind while it is open, as Sofascore's community vote allows."""
    ensure_tables(conn)
    now = time.time() if now is None else now
    room = str(room or "")
    if not room_ok(room):
        return 400, {"error": "That game has no room."}
    if side not in ("home", "away"):
        return 400, {"error": "Pick a side."}
    if game_of(room, data_dir).get("state") == "final":
        return 409, {"error": "The game is over — the vote is closed."}
    conn.execute("INSERT INTO chat_votes (room, user_id, side, changed_at) VALUES (?,?,?,?) "
                 "ON CONFLICT(room, user_id) DO UPDATE SET side=excluded.side, changed_at=excluded.changed_at",
                 (room, int(user_id), side, now))
    _mark_votes(conn, room, now)
    conn.commit()
    return 200, {"ok": True, "mine": side}


def _mark_votes(conn, room: str, now: float) -> None:
    """The split as it stands, on the room's line: a new mark once a
    minute has passed since the last, otherwise the last mark takes the
    new split — so a busy room is a line through the game, not a row for
    every tap."""
    n = {r[0]: int(r[1]) for r in conn.execute(
        "SELECT side, COUNT(*) FROM chat_votes WHERE room=? GROUP BY side", (room,))}
    home, away = n.get("home", 0), n.get("away", 0)
    last = conn.execute("SELECT rowid, at FROM chat_vote_marks WHERE room=? ORDER BY at DESC LIMIT 1",
                        (room,)).fetchone()
    if last and now - float(last[1]) < VOTE_MARK_EVERY_S:
        conn.execute("UPDATE chat_vote_marks SET home=?, away=? WHERE rowid=?", (home, away, last[0]))
    else:
        conn.execute("INSERT INTO chat_vote_marks (room, at, home, away) VALUES (?,?,?,?)",
                     (room, now, home, away))


def vote_path(conn, room: str) -> list:
    """[[at, home, away], ...] oldest first, the last VOTE_PATH_MAX marks."""
    rows = conn.execute("SELECT at, home, away FROM chat_vote_marks WHERE room=? ORDER BY at DESC LIMIT ?",
                        (room, VOTE_PATH_MAX)).fetchall()
    return [[round(float(r[0]), 1), int(r[1]), int(r[2])] for r in reversed(rows)]


def report(conn, user_id: int, msg_id, reason="other", now: float | None = None) -> tuple[int, dict]:
    ensure_tables(conn)
    now = time.time() if now is None else now
    m = conn.execute("SELECT id, user_id, party FROM chat_msgs WHERE id=?", (int(msg_id or 0),)).fetchone()
    if not m or (m["party"] and not _in_party(conn, user_id, m["party"])):
        return 404, {"error": "That is gone already."}
    if int(m["user_id"]) == int(user_id):
        return 400, {"error": "That one is yours — delete it instead."}
    reason = reason if reason in REPORT_REASONS else "other"
    conn.execute("INSERT OR IGNORE INTO chat_reports (msg_id, user_id, reason, created_at) VALUES (?,?,?,?)",
                 (int(msg_id), int(user_id), reason, now))
    n = conn.execute("SELECT COUNT(*) FROM chat_reports WHERE msg_id=?", (int(msg_id),)).fetchone()[0]
    if n >= REPORTS_TO_HIDE:
        conn.execute("UPDATE chat_msgs SET hidden=1 WHERE id=?", (int(msg_id),))
    conn.commit()
    if n >= REPORTS_TO_HIDE:
        _unpay(conn, msg_id)
    return 200, {"ok": True}


def delete(conn, user_id: int, msg_id) -> tuple[int, dict]:
    ensure_tables(conn)
    m = conn.execute("SELECT user_id FROM chat_msgs WHERE id=?", (int(msg_id or 0),)).fetchone()
    if not m or int(m["user_id"]) != int(user_id):
        return 404, {"error": "Not yours to delete."}
    conn.execute("DELETE FROM chat_reacts WHERE msg_id=?", (int(msg_id),))
    conn.execute("DELETE FROM chat_reports WHERE msg_id=?", (int(msg_id),))
    conn.execute("DELETE FROM chat_msgs WHERE id=?", (int(msg_id),))
    conn.commit()
    _unmention(conn, msg_id)
    return 200, {"ok": True}


def set_hidden(conn, msg_id, hidden: bool) -> tuple[int, dict]:
    """The founder's switch (the server checks who is asking)."""
    ensure_tables(conn)
    cur = conn.execute("UPDATE chat_msgs SET hidden=? WHERE id=?", (1 if hidden else 0, int(msg_id or 0)))
    if not hidden:
        conn.execute("DELETE FROM chat_reports WHERE msg_id=?", (int(msg_id or 0),))
    conn.commit()
    if hidden and cur.rowcount:
        _unpay(conn, msg_id)
    return (200, {"ok": True}) if cur.rowcount else (404, {"error": "No such message."})


def _unpay(conn, msg_id) -> None:
    """A hidden message keeps none of the karma it earned (engine/karma),
    and its @mentions leave Activity."""
    from . import karma as K
    K.revoke_message(conn, int(msg_id or 0))
    _unmention(conn, msg_id)


def reported(conn) -> list:
    """What readers flagged, for the founder: id, room, reports, reasons, text."""
    ensure_tables(conn)
    out = []
    for r in conn.execute("SELECT msg_id, COUNT(*) AS n, GROUP_CONCAT(reason) AS why FROM chat_reports "
                          "GROUP BY msg_id ORDER BY n DESC LIMIT 100"):
        m = conn.execute("SELECT room, body, hidden FROM chat_msgs WHERE id=?", (r["msg_id"],)).fetchone()
        if m:
            out.append({"id": int(r["msg_id"]), "room": m["room"], "reports": int(r["n"]),
                        "reasons": sorted(set(filter(None, (r["why"] or "").split(",")))),
                        "hidden": bool(m["hidden"]), "text": m["body"][:300]})
    return out


# ─── reading ────────────────────────────────────────────────────────────────

def touch(room: str, key: str, now: float | None = None) -> int:
    """Mark this page as in the room; returns how many pages are."""
    now = time.time() if now is None else now
    with _HERE_LOCK:
        seen = _HERE.setdefault(room, {})
        if key:
            seen[key] = now
        for k in [k for k, t in seen.items() if now - t > HERE_S]:
            seen.pop(k, None)
        if not seen:
            _HERE.pop(room, None)
        if len(_HERE) > 2000:                    # a scraper's rooms, not a slate's
            for r in sorted(_HERE, key=lambda r: max(_HERE[r].values() or [0]))[:1000]:
                _HERE.pop(r, None)
        return len(seen)


def here(room: str, now: float | None = None) -> int:
    now = time.time() if now is None else now
    with _HERE_LOCK:
        return sum(1 for t in (_HERE.get(room) or {}).values() if now - t <= HERE_S)


def here_total(now: float | None = None) -> int:
    """Pages in any game's room right now, each counted once however many
    rooms it has open (the first screen's "in game rooms right now")."""
    now = time.time() if now is None else now
    with _HERE_LOCK:
        return len({k for seen in _HERE.values() for k, t in seen.items() if now - t <= HERE_S})


def _counts(conn, sql: str, args) -> dict:
    out: dict = {}
    for r in conn.execute(sql, args):
        out.setdefault(str(r[0]), {})[r[1]] = int(r[2])
    return out


def _msg_view(r, strong: bool, viewer, reacts: dict, mine: dict) -> dict:
    from . import socialfeed as SF
    body = r["body"] if strong else profanity.mask(r["body"])
    out = {"id": int(r["id"]), "at": float(r["created_at"]), "body": body,
           "by": SF._person(r), "own": bool(viewer) and int(r["user_id"]) == int(viewer),
           "reacts": reacts.get(str(r["id"]), {}), "mine": mine.get(int(r["id"]), "")}
    if r["play"]:
        out["play"] = r["play"]
    if r["bet"]:
        try:
            out["bet"] = json.loads(r["bet"])
        except ValueError:
            pass
    if r["reply_to"]:
        out["reply_to"] = int(r["reply_to"])
    return out


_MSG_SQL = ("SELECT m.id, m.user_id, m.body, m.play, m.bet, m.reply_to, m.created_at, "
            "p.handle, p.display_name, p.color, p.fav_team, p.verified, p.founder "
            "FROM chat_msgs m JOIN feed_profiles p ON p.user_id=m.user_id ")


def room_view(conn, room: str, viewer=None, after: int = 0, before: int = 0,
              since: float = 0.0, strong: bool = False, here_key: str = "",
              now: float | None = None, data_dir: Path | None = None,
              party: int = 0, pafter: int = 0) -> tuple[int, dict]:
    """One poll's answer: messages after ``after`` (or the newest page, or
    the page before ``before``), and every count that moved since
    ``since``. ``t`` is the stamp to send back as ``since`` next time."""
    from . import socialfeed as SF
    ensure_tables(conn)
    SF.ensure_tables(conn)
    now = time.time() if now is None else now
    room = str(room or "")
    if not room_ok(room):
        return 400, {"error": "That game has no room."}
    hide = SF.blocked_ids(conn, viewer)
    if after:
        rows = conn.execute(_MSG_SQL + "WHERE m.room=? AND m.party=0 AND m.id>? AND m.hidden=0 ORDER BY m.id LIMIT ?",
                            (room, int(after), PAGE * 2)).fetchall()
    elif before:
        rows = conn.execute(_MSG_SQL + "WHERE m.room=? AND m.party=0 AND m.id<? AND m.hidden=0 "
                            "ORDER BY m.id DESC LIMIT ?", (room, int(before), PAGE)).fetchall()[::-1]
    else:
        rows = conn.execute(_MSG_SQL + "WHERE m.room=? AND m.party=0 AND m.hidden=0 ORDER BY m.id DESC LIMIT ?",
                            (room, PAGE)).fetchall()[::-1]
    rows = [r for r in rows if int(r["user_id"]) not in hide]
    ids = [int(r["id"]) for r in rows]
    # Counts for the messages in hand, and for any older message whose
    # faces moved since the last ask.
    moved = [int(x[0]) for x in conn.execute(
        "SELECT DISTINCT msg_id FROM chat_reacts WHERE room=? AND changed_at>=?", (room, since - 1))] if since else []
    want = sorted(set(ids) | set(moved))
    reacts, mine = {}, {}
    if want:
        q = ",".join("?" * len(want))
        reacts = _counts(conn, f"SELECT msg_id, kind, COUNT(*) FROM chat_reacts WHERE msg_id IN ({q}) "
                               "AND kind<>'' GROUP BY msg_id, kind", want)
        if viewer:
            mine = {int(x[0]): x[1] for x in conn.execute(
                f"SELECT msg_id, kind FROM chat_reacts WHERE user_id=? AND msg_id IN ({q})", [int(viewer), *want])}
    msgs = [_msg_view(r, strong, viewer, reacts, mine) for r in rows]
    # The Call it flame beside a handle: its author's calls right in a row now.
    from . import callit as CI
    flames = CI.current_streaks(conn, {int(r["user_id"]) for r in rows}, now)
    # And the author's karma level, with the flair it opened (engine/karma).
    from . import karma as K
    levels = K.cards(conn, {int(r["user_id"]) for r in rows}, now)
    for m, r in zip(msgs, rows):
        if int(r["user_id"]) in flames:
            m["by"]["streak"] = flames[int(r["user_id"])]
        if int(r["user_id"]) in levels:
            m["by"].update(levels[int(r["user_id"])])
    # Plays: the faces and the thread sizes, for every play that moved.
    cut = since - 1 if since else 0
    plays = _counts(conn, "SELECT play, kind, COUNT(*) FROM chat_play_reacts WHERE room=? AND kind<>'' "
                          "AND play IN (SELECT play FROM chat_play_reacts WHERE room=? AND changed_at>=?) "
                          "GROUP BY play, kind", (room, room, cut))
    # A play every face was taken back from still has to say so.
    for x in conn.execute("SELECT DISTINCT play FROM chat_play_reacts WHERE room=? AND changed_at>=?", (room, cut)):
        plays.setdefault(str(x[0]), {})
    threads = {str(x[0]): int(x[1]) for x in conn.execute(
        "SELECT play, COUNT(*) FROM chat_msgs WHERE room=? AND party=0 AND play<>'' AND hidden=0 "
        "AND play IN (SELECT play FROM chat_msgs WHERE room=? AND party=0 AND play<>'' AND created_at>=?) "
        "GROUP BY play", (room, room, cut))}
    mine_plays = {}
    if viewer:
        mine_plays = {str(x[0]): x[1] for x in conn.execute(
            "SELECT play, kind FROM chat_play_reacts WHERE room=? AND user_id=? AND changed_at>=?",
            (room, int(viewer), cut))}
    votes = {r["side"]: int(r["n"]) for r in conn.execute(
        "SELECT side, COUNT(*) AS n FROM chat_votes WHERE room=? GROUP BY side", (room,))}
    my_vote = ""
    if viewer:
        v = conn.execute("SELECT side FROM chat_votes WHERE room=? AND user_id=?", (room, int(viewer))).fetchone()
        my_vote = v["side"] if v else ""
    game = game_of(room, data_dir)
    out = {"room": room, "t": now, "messages": msgs,
           "older": bool(rows) and not after and conn.execute(
               "SELECT 1 FROM chat_msgs WHERE room=? AND party=0 AND id<? AND hidden=0 LIMIT 1",
               (room, ids[0] if ids else 0)).fetchone() is not None,
           # An older message whose faces moved — to zero, too.
           "reacts": {str(m): reacts.get(str(m), {}) for m in moved if m not in ids},
           "plays": plays, "threads": threads, "mine_plays": mine_plays,
           "votes": {"home": votes.get("home", 0), "away": votes.get("away", 0), "mine": my_vote,
                     "open": game.get("state") != "final"},
           # The room against the math: the vote through the game, drawn on
           # the game page's win-chance chart (detail.js pbpRoomLine).
           "vote_path": vote_path(conn, room),
           "here": touch(room, here_key, now) if here_key else here(room, now),
           # The room's heat (Twitch's Hype Train): the last five minutes as
           # a meter, paying a viewer who is part of it (engine/karma).
           "hype": K.hype(conn, room, viewer, now)}
    if viewer:
        # Friends in this game now (engine/karma), unless they hid it.
        out["friends"] = [f["handle"] for f in K.friends_watching(conn, viewer, now, room=room)]
        out["parties"] = my_parties(conn, viewer, room)
        if party and any(p["id"] == int(party) for p in out["parties"]):
            out["party"] = party_view(conn, viewer, int(party), pafter, strong, hide)
    return 200, out


# ─── watch parties ──────────────────────────────────────────────────────────

def _in_party(conn, user_id, party_id, room: str = "") -> bool:
    if not user_id or not party_id:
        return False
    row = conn.execute("SELECT p.room FROM chat_party_members m JOIN chat_parties p ON p.id=m.party_id "
                       "WHERE m.party_id=? AND m.user_id=?", (int(party_id), int(user_id))).fetchone()
    return bool(row) and (not room or row[0] == room)


def _party_out(conn, row) -> dict:
    n = conn.execute("SELECT COUNT(*) FROM chat_party_members WHERE party_id=?", (int(row["id"]),)).fetchone()[0]
    return {"id": int(row["id"]), "room": row["room"], "name": row["name"], "token": row["token"], "members": int(n)}


def party_create(conn, user_id: int, room, name="", now: float | None = None) -> tuple[int, dict]:
    """A watch party in this game's room, its starter its first member."""
    ensure_tables(conn)
    now = time.time() if now is None else now
    room = str(room or "")
    if not room_ok(room):
        return 400, {"error": "That game has no room."}
    me = _profile(conn, user_id)
    if not me:
        return 409, {"error": "Pick a username first.", "need_handle": True}
    n = conn.execute("SELECT COUNT(*) FROM chat_parties WHERE room=? AND user_id=?", (room, int(user_id))).fetchone()[0]
    if n >= PARTY_PER_ROOM:
        return 429, {"error": f"You have {PARTY_PER_ROOM} watch parties in this game already."}
    name = re.sub(r"\s+", " ", str(name or "")).strip()[:PARTY_NAME_MAX] or f"{me.get('handle') or 'Your'}’s party"
    why = profanity.check(name, "The party's name")
    if why:
        return 400, {"error": why}
    # A name is a label every member sees, whatever they chose for swearing.
    name = profanity.mask(name)
    token = secrets.token_urlsafe(9)
    cur = conn.execute("INSERT INTO chat_parties (room, token, name, user_id, created_at) VALUES (?,?,?,?,?)",
                       (room, token, name, int(user_id), now))
    pid = int(cur.lastrowid)
    conn.execute("INSERT OR IGNORE INTO chat_party_members (party_id, user_id, joined_at) VALUES (?,?,?)",
                 (pid, int(user_id), now))
    conn.commit()
    return 200, _party_out(conn, conn.execute("SELECT * FROM chat_parties WHERE id=?", (pid,)).fetchone())


def party_join(conn, user_id: int, token, now: float | None = None) -> tuple[int, dict]:
    """In by the invite's token; joining twice is joining once."""
    ensure_tables(conn)
    now = time.time() if now is None else now
    token = str(token or "")
    row = conn.execute("SELECT * FROM chat_parties WHERE token=?", (token,)).fetchone() \
        if PARTY_RE.match(token) else None
    if not row:
        return 404, {"error": "That invite has run out."}
    if not _in_party(conn, user_id, row["id"]):
        n = conn.execute("SELECT COUNT(*) FROM chat_party_members WHERE party_id=?", (int(row["id"]),)).fetchone()[0]
        if n >= PARTY_MAX:
            return 409, {"error": "That watch party is full."}
        conn.execute("INSERT OR IGNORE INTO chat_party_members (party_id, user_id, joined_at) VALUES (?,?,?)",
                     (int(row["id"]), int(user_id), now))
        conn.commit()
    return 200, _party_out(conn, row)


def party_leave(conn, user_id: int, party_id) -> tuple[int, dict]:
    ensure_tables(conn)
    conn.execute("DELETE FROM chat_party_members WHERE party_id=? AND user_id=?", (int(party_id or 0), int(user_id)))
    conn.commit()
    return 200, {"ok": True}


def my_parties(conn, user_id, room: str) -> list:
    """The reader's parties in this game, the newest joined first."""
    rows = conn.execute("SELECT p.* FROM chat_parties p JOIN chat_party_members m ON m.party_id=p.id "
                        "WHERE p.room=? AND m.user_id=? ORDER BY m.joined_at DESC", (room, int(user_id))).fetchall()
    return [_party_out(conn, r) for r in rows]


def party_view(conn, viewer, party_id: int, after: int = 0, strong: bool = False, hide=()) -> dict:
    """A party's messages after ``after`` (or its newest page), with their faces."""
    if after:
        rows = conn.execute(_MSG_SQL + "WHERE m.party=? AND m.id>? AND m.hidden=0 ORDER BY m.id LIMIT ?",
                            (party_id, int(after), PAGE * 2)).fetchall()
    else:
        rows = conn.execute(_MSG_SQL + "WHERE m.party=? AND m.hidden=0 ORDER BY m.id DESC LIMIT ?",
                            (party_id, PAGE)).fetchall()[::-1]
    rows = [r for r in rows if int(r["user_id"]) not in set(hide or ())]
    ids = [int(r["id"]) for r in rows]
    reacts, mine = {}, {}
    if ids:
        q = ",".join("?" * len(ids))
        reacts = _counts(conn, f"SELECT msg_id, kind, COUNT(*) FROM chat_reacts WHERE msg_id IN ({q}) "
                               "AND kind<>'' GROUP BY msg_id, kind", ids)
        mine = {int(x[0]): x[1] for x in conn.execute(
            f"SELECT msg_id, kind FROM chat_reacts WHERE user_id=? AND msg_id IN ({q})", [int(viewer), *ids])}
    msgs = [_msg_view(r, strong, viewer, reacts, mine) for r in rows]
    from . import karma as K
    levels = K.cards(conn, {int(r["user_id"]) for r in rows})
    for m, r in zip(msgs, rows):
        m["by"].update(levels.get(int(r["user_id"]), {}))
    return {"id": int(party_id), "messages": msgs}


def counts(conn, rooms, now: float | None = None) -> dict:
    """For the Live tab's cards and its play feed: per room, how many pages
    are in it, messages in the last ten minutes, and each play's total
    faces and replies."""
    ensure_tables(conn)
    now = time.time() if now is None else now
    rooms = [r for r in dict.fromkeys(str(x) for x in (rooms or [])) if room_ok(r)][:MAX_ROOMS]
    out = {}
    for room in rooms:
        recent = conn.execute("SELECT COUNT(*) FROM chat_msgs WHERE room=? AND party=0 AND hidden=0 "
                              "AND created_at>?", (room, now - 600)).fetchone()[0]
        plays: dict = {}
        for x in conn.execute("SELECT play, COUNT(*) FROM chat_play_reacts WHERE room=? AND kind<>'' "
                              "GROUP BY play", (room,)):
            plays[str(x[0])] = int(x[1])
        for x in conn.execute("SELECT play, COUNT(*) FROM chat_msgs WHERE room=? AND party=0 AND play<>'' "
                              "AND hidden=0 GROUP BY play", (room,)):
            plays[str(x[0])] = plays.get(str(x[0]), 0) + int(x[1])
        out[room] = {"here": here(room, now), "recent": int(recent), "plays": plays}
    return out
