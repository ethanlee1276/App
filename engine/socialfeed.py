"""The public feed: posts, profiles, follows, threads, and the Tail button.

Ethan, 2026-10-06: *"adding a social page where users can make parlays and
share them on the site then we show a "tail" button …"* and 2026-10-07:
*"go deeper … a full social feature … take reference from something like
facebook or reddit … there needs to be profiles for users."* The audit
behind this build is docs/SOCIAL_AUDIT.md.

WHAT CHANGED FROM AUGUST. engine/social.py refused a feed of strangers
("a moderation product") and kept every share between friends. Ethan has
asked for the public version, so this module is that moderation product:

* **Slurs are refused, swearing is masked** (engine/profanity). The
  writer's words are stored as written; the reader decides whether to
  see the strong ones.
* **Public posts need a handle**, so nobody is named in public by their
  email's local part.
* **Report, block and hide.** Three different accounts reporting a post
  or comment hides it; a block hides two people from each other both
  ways; the owner can hide or restore anything.
* **Rate caps** on posts, comments and follows, tighter for accounts
  under a day old.

THE RECORD CANNOT BE FAKED (the Action Network / Pikkit rule). A leg is
resolved by the SERVER against the private board — the client sends
which row, never a price, a link or a URL — and only before its game
starts. Legs are never editable afterwards (a caption can be fixed for
15 minutes, marked "edited"). Every parlay is then GRADED from the
journal's own recorded stat (ledger.db `bets.actual`, the source the
Record page reads), at the line the poster took.

THE PAYWALL STILL HOLDS. A leg that is not on the public (redacted) copy
of its board is a PAID leg: a reader who has not paid sees only the
player and market (the pointer rule from engine/social) and cannot tail
the post. No model number — probability, edge, projection, tier — is
ever stored on a post.

THE TAIL BUTTON opens the parlay at the books. A book whose bet-slip
links carry indexed selections (FanDuel's ``marketId[0]=…``) can take
every leg in ONE link (:func:`combine_links`); every other book gets one
link per leg. Nothing here places a bet; the site takes no wagers.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import re
import threading
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import profanity

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"

MAX_CAPTION = 280
MAX_COMMENT = 500
MAX_BIO = 200
MAX_NAME = 30
MAX_TITLE = 120
MAX_BODY = 2000
HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
MENTION_RE = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_]{3,20})")
RESERVED = {"qellys", "qellysbook", "admin", "owner", "zeno", "moderator", "mod",
            "support", "official", "staff", "system", "everyone", "here"}
MIN_LEGS = 1
MAX_LEGS = 3          # the slip's own cap (SLIP_MAX in app.js)
POSTS_PER_DAY = 10
NEW_ACCOUNT_POSTS = 3          # accounts under a day old
NEW_ACCOUNT_S = 86400
COMMENTS_PER_HOUR = 30
FOLLOWS_PER_DAY = 100
REPORTS_TO_HIDE = 3
EDIT_WINDOW_S = 15 * 60
MAX_MENTIONS = 5
PAGE = 20
KEEP_DAYS = 120                # a profile's record needs a season's history
HOT_WINDOW_S = 7 * 86400
GRADE_AFTER_S = 2 * 3600       # nothing to grade before kickoff + a game
GRADE_RETRY_S = 15 * 60
GRADE_GIVE_UP_S = 10 * 86400
NOTIF_KEEP = 200
COLORS = 8                     # avatar colours, drawn from the theme by index
REPORT_REASONS = ("spam", "abuse", "hate", "scam", "other")
TOP_WINDOWS = {"day": 86400, "week": 7 * 86400, "month": 30 * 86400, "all": None}
LEADER_MIN = 5

#: The six sports boards a leg can come from — the same map Bet it uses.
SPORT_FILE = {"nfl": "recommendations.json", "cfb": "cfb.json",
              "mlb": "mlb_recommendations.json", "nba": "nba.json",
              "wnba": "wnba.json", "nhl": "nhl.json"}

GAME_WORDS = {"spread": "Spread", "total": "Game total", "team_total": "Team total",
              "moneyline": "Moneyline", "ml": "Moneyline", "h2h": "Moneyline",
              "run_line": "Run line", "puck_line": "Puck line"}


def _cols(conn, table: str) -> set:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _add(conn, table: str, col: str, decl: str) -> None:
    if col not in _cols(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def ensure_tables(conn) -> None:
    """Additive, safe on every call — the posture every accounts.db module
    keeps. The columns added after the first cut (2026-10-06) arrive by
    ALTER, so a box that already holds posts keeps them."""
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS feed_profiles (
        user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        handle     TEXT NOT NULL UNIQUE COLLATE NOCASE,
        bio        TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
      );
      CREATE TABLE IF NOT EXISTS feed_posts (
        id         INTEGER PRIMARY KEY,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        sport      TEXT NOT NULL,
        date       TEXT NOT NULL DEFAULT '',
        legs       TEXT NOT NULL,
        caption    TEXT NOT NULL DEFAULT '',
        combined   INTEGER,
        created_at REAL NOT NULL,
        hidden     INTEGER NOT NULL DEFAULT 0
      );
      CREATE INDEX IF NOT EXISTS feed_posts_new ON feed_posts(created_at);
      CREATE INDEX IF NOT EXISTS feed_posts_by ON feed_posts(user_id, created_at);
      CREATE TABLE IF NOT EXISTS feed_likes (
        post_id    INTEGER NOT NULL REFERENCES feed_posts(id) ON DELETE CASCADE,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        PRIMARY KEY (post_id, user_id)
      );
      CREATE TABLE IF NOT EXISTS feed_tails (
        post_id    INTEGER NOT NULL REFERENCES feed_posts(id) ON DELETE CASCADE,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        PRIMARY KEY (post_id, user_id)
      );
      CREATE TABLE IF NOT EXISTS feed_comments (
        id         INTEGER PRIMARY KEY,
        post_id    INTEGER NOT NULL REFERENCES feed_posts(id) ON DELETE CASCADE,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        body       TEXT NOT NULL,
        created_at REAL NOT NULL,
        hidden     INTEGER NOT NULL DEFAULT 0
      );
      CREATE INDEX IF NOT EXISTS feed_comments_post ON feed_comments(post_id, created_at);
      CREATE TABLE IF NOT EXISTS feed_reports (
        kind       TEXT NOT NULL,
        item_id    INTEGER NOT NULL,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        PRIMARY KEY (kind, item_id, user_id)
      );
      CREATE TABLE IF NOT EXISTS feed_follows (
        follower_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        followee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at  REAL NOT NULL,
        PRIMARY KEY (follower_id, followee_id)
      );
      CREATE INDEX IF NOT EXISTS feed_follows_in ON feed_follows(followee_id);
      CREATE TABLE IF NOT EXISTS feed_blocks (
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        blocked_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        PRIMARY KEY (user_id, blocked_id)
      );
      CREATE TABLE IF NOT EXISTS feed_comment_likes (
        comment_id INTEGER NOT NULL REFERENCES feed_comments(id) ON DELETE CASCADE,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        PRIMARY KEY (comment_id, user_id)
      );
      CREATE TABLE IF NOT EXISTS feed_notifs (
        id         INTEGER PRIMARY KEY,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        actor_id   INTEGER,
        kind       TEXT NOT NULL,
        post_id    INTEGER,
        comment_id INTEGER,
        created_at REAL NOT NULL,
        seen       INTEGER NOT NULL DEFAULT 0
      );
      CREATE UNIQUE INDEX IF NOT EXISTS feed_notifs_once
        ON feed_notifs(user_id, COALESCE(actor_id, 0), kind, COALESCE(post_id, 0), COALESCE(comment_id, 0));
      CREATE INDEX IF NOT EXISTS feed_notifs_inbox ON feed_notifs(user_id, created_at);
    """)
    for col, decl in (("display_name", "TEXT NOT NULL DEFAULT ''"),
                      ("color", "INTEGER NOT NULL DEFAULT 0"),
                      ("fav_team", "TEXT NOT NULL DEFAULT ''")):
        _add(conn, "feed_profiles", col, decl)
    for col, decl in (("kind", "TEXT NOT NULL DEFAULT 'parlay'"),
                      ("title", "TEXT NOT NULL DEFAULT ''"),
                      ("body", "TEXT NOT NULL DEFAULT ''"),
                      ("result", "TEXT NOT NULL DEFAULT 'pending'"),
                      ("units", "REAL"),
                      ("graded_at", "REAL"),
                      ("last_try", "REAL NOT NULL DEFAULT 0"),
                      ("edited_at", "REAL")):
        _add(conn, "feed_posts", col, decl)
    _add(conn, "feed_comments", "parent_id", "INTEGER")
    conn.commit()


# ─── profiles ────────────────────────────────────────────────────────────────

def _uid_of(conn, handle: str):
    r = conn.execute("SELECT user_id FROM feed_profiles WHERE handle=? COLLATE NOCASE",
                     (str(handle or "").lstrip("@")[:20],)).fetchone()
    return int(r["user_id"]) if r else None


def profile_of(conn, user_id: int) -> dict | None:
    ensure_tables(conn)
    r = conn.execute("SELECT * FROM feed_profiles WHERE user_id=?", (int(user_id),)).fetchone()
    if not r:
        return None
    return {"handle": r["handle"], "bio": r["bio"], "since": r["created_at"],
            "name": r["display_name"], "color": int(r["color"] or 0), "team": r["fav_team"]}


def profile_set(conn, user_id: int, handle, bio, name=None, color=None,
                team=None) -> tuple[int, dict]:
    """Choose (or change) the handle; write the name, bio, colour and team.
    Fields passed as None keep what is stored."""
    ensure_tables(conn)
    old = profile_of(conn, user_id) or {}
    handle = str(handle if handle is not None else old.get("handle", "")).strip().lstrip("@")
    bio = re.sub(r"\s+", " ", str(bio if bio is not None else old.get("bio", ""))).strip()[:MAX_BIO]
    name = re.sub(r"\s+", " ", str(name if name is not None else old.get("name", ""))).strip()[:MAX_NAME]
    try:
        color = int(color if color is not None else old.get("color", 0)) % COLORS
    except (TypeError, ValueError):
        color = 0
    team = str(team if team is not None else old.get("team", "")).strip()[:16]
    if team and not re.fullmatch(r"(nfl|cfb|mlb|nba|wnba|nhl):[A-Za-z0-9&.\- ]{2,12}", team):
        return 400, {"error": "That favourite team is not one this site knows."}
    if not HANDLE_RE.match(handle):
        return 400, {"error": "A handle is 3–20 letters, numbers or underscores."}
    if handle.lower() in RESERVED or not profanity.clean_name(handle):
        return 400, {"error": "That handle is not available."}
    if name and (name.lower().replace(" ", "") in RESERVED or not profanity.clean_name(name)):
        return 400, {"error": "That display name is not available."}
    why = profanity.check(bio, "Your bio")
    if why:
        return 400, {"error": why}
    taken = _uid_of(conn, handle)
    if taken is not None and taken != int(user_id):
        return 409, {"error": "Somebody already has that handle."}
    now = time.time()
    conn.execute(
        "INSERT INTO feed_profiles (user_id, handle, bio, created_at, updated_at, display_name, color, fav_team) "
        "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET handle=excluded.handle, "
        "bio=excluded.bio, updated_at=excluded.updated_at, display_name=excluded.display_name, "
        "color=excluded.color, fav_team=excluded.fav_team",
        (int(user_id), handle, bio, now, now, name, color, team))
    conn.commit()
    return 200, {"ok": True, "profile": profile_of(conn, user_id)}


# ─── blocks and follows ─────────────────────────────────────────────────────

def blocked_ids(conn, viewer) -> set:
    """Everyone this viewer must not see, or be seen by: both directions."""
    if not viewer:
        return set()
    out = set()
    for r in conn.execute("SELECT blocked_id AS o FROM feed_blocks WHERE user_id=? "
                          "UNION SELECT user_id AS o FROM feed_blocks WHERE blocked_id=?",
                          (int(viewer), int(viewer))):
        out.add(int(r["o"]))
    return out


def toggle_block(conn, user_id: int, handle: str) -> tuple[int, dict]:
    ensure_tables(conn)
    other = _uid_of(conn, handle)
    if other is None:
        return 404, {"error": "Nobody has that handle."}
    if other == int(user_id):
        return 400, {"error": "You cannot block yourself."}
    had = conn.execute("SELECT 1 FROM feed_blocks WHERE user_id=? AND blocked_id=?",
                       (int(user_id), other)).fetchone()
    if had:
        conn.execute("DELETE FROM feed_blocks WHERE user_id=? AND blocked_id=?", (int(user_id), other))
    else:
        conn.execute("INSERT INTO feed_blocks (user_id, blocked_id, created_at) VALUES (?,?,?)",
                     (int(user_id), other, time.time()))
        # A block ends the follow both ways, as on every platform.
        conn.execute("DELETE FROM feed_follows WHERE (follower_id=? AND followee_id=?) "
                     "OR (follower_id=? AND followee_id=?)", (int(user_id), other, other, int(user_id)))
    conn.commit()
    return 200, {"blocked": not had}


def toggle_follow(conn, user_id: int, handle: str) -> tuple[int, dict]:
    ensure_tables(conn)
    other = _uid_of(conn, handle)
    if other is None:
        return 404, {"error": "Nobody has that handle."}
    if other == int(user_id):
        return 400, {"error": "You cannot follow yourself."}
    if other in blocked_ids(conn, user_id):
        return 403, {"error": "You cannot follow this account."}
    had = conn.execute("SELECT 1 FROM feed_follows WHERE follower_id=? AND followee_id=?",
                       (int(user_id), other)).fetchone()
    if had:
        conn.execute("DELETE FROM feed_follows WHERE follower_id=? AND followee_id=?", (int(user_id), other))
    else:
        n = conn.execute("SELECT COUNT(*) FROM feed_follows WHERE follower_id=? AND created_at>?",
                         (int(user_id), time.time() - 86400)).fetchone()[0]
        if n >= FOLLOWS_PER_DAY:
            return 429, {"error": f"{FOLLOWS_PER_DAY} follows a day is the limit."}
        conn.execute("INSERT INTO feed_follows (follower_id, followee_id, created_at) VALUES (?,?,?)",
                     (int(user_id), other, time.time()))
        _notify(conn, other, user_id, "follow")
    conn.commit()
    return 200, {"following": not had, "followers": _n_followers(conn, other)}


def _n_followers(conn, uid: int) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM feed_follows WHERE followee_id=?", (int(uid),)).fetchone()[0])


def follow_list(conn, handle: str, which: str, viewer=None) -> tuple[int, dict]:
    ensure_tables(conn)
    uid = _uid_of(conn, handle)
    if uid is None:
        return 404, {"error": "Nobody has that handle."}
    if which == "followers":
        sql = ("SELECT f.* FROM feed_follows x JOIN feed_profiles f ON f.user_id=x.follower_id "
               "WHERE x.followee_id=? ORDER BY x.created_at DESC LIMIT 200")
    else:
        sql = ("SELECT f.* FROM feed_follows x JOIN feed_profiles f ON f.user_id=x.followee_id "
               "WHERE x.follower_id=? ORDER BY x.created_at DESC LIMIT 200")
    hide = blocked_ids(conn, viewer)
    mine = _following_set(conn, viewer)
    return 200, {"people": [_person(r, mine) for r in conn.execute(sql, (uid,)) if int(r["user_id"]) not in hide]}


def _following_set(conn, viewer) -> set:
    if not viewer:
        return set()
    return {int(r[0]) for r in conn.execute("SELECT followee_id FROM feed_follows WHERE follower_id=?",
                                            (int(viewer),))}


def _person(r, following: set | None = None) -> dict:
    return {"handle": r["handle"], "name": r["display_name"], "color": int(r["color"] or 0),
            "team": r["fav_team"], "following": int(r["user_id"]) in (following or set())}


# ─── notifications ──────────────────────────────────────────────────────────

def _notify(conn, user_id, actor_id, kind: str, post_id=None, comment_id=None) -> None:
    """One row per (who, what, where): a like toggled ten times notifies once."""
    if user_id is None or (actor_id is not None and int(user_id) == int(actor_id)):
        return
    if actor_id is not None and int(actor_id) in blocked_ids(conn, user_id):
        return
    conn.execute("INSERT OR IGNORE INTO feed_notifs (user_id, actor_id, kind, post_id, comment_id, created_at) "
                 "VALUES (?,?,?,?,?,?)", (int(user_id), None if actor_id is None else int(actor_id), kind,
                                          post_id, comment_id, time.time()))
    conn.execute("DELETE FROM feed_notifs WHERE user_id=? AND id NOT IN (SELECT id FROM feed_notifs "
                 "WHERE user_id=? ORDER BY created_at DESC LIMIT ?)", (int(user_id), int(user_id), NOTIF_KEEP))


def _mentions(conn, text: str, actor: int, post_id: int, comment_id=None) -> None:
    seen = set()
    for h in MENTION_RE.findall(str(text or ""))[:MAX_MENTIONS]:
        uid = _uid_of(conn, h)
        if uid is not None and uid not in seen:
            seen.add(uid)
            _notify(conn, uid, actor, "mention", post_id, comment_id)


def unseen(conn, user_id) -> int:
    if not user_id:
        return 0
    ensure_tables(conn)
    return int(conn.execute("SELECT COUNT(*) FROM feed_notifs WHERE user_id=? AND seen=0",
                            (int(user_id),)).fetchone()[0])


def notifications(conn, user_id: int, strong: bool = False) -> dict:
    ensure_tables(conn)
    out = []
    for r in conn.execute(
            "SELECT n.*, f.handle, f.display_name, f.color, p.title, p.caption, p.kind AS pkind, "
            "p.result, c.body AS cbody FROM feed_notifs n "
            "LEFT JOIN feed_profiles f ON f.user_id=n.actor_id "
            "LEFT JOIN feed_posts p ON p.id=n.post_id "
            "LEFT JOIN feed_comments c ON c.id=n.comment_id "
            "WHERE n.user_id=? ORDER BY n.created_at DESC LIMIT 60", (int(user_id),)):
        what = r["cbody"] or r["title"] or r["caption"] or ""
        out.append({"id": int(r["id"]), "kind": r["kind"], "at": r["created_at"], "seen": bool(r["seen"]),
                    "handle": r["handle"] or "", "name": r["display_name"] or "",
                    "color": int(r["color"] or 0), "post_id": r["post_id"], "comment_id": r["comment_id"],
                    "result": r["result"] or "", "snippet": _text(what, strong)[:90]})
    return {"items": out, "unseen": unseen(conn, user_id)}


def mark_seen(conn, user_id: int) -> None:
    ensure_tables(conn)
    conn.execute("UPDATE feed_notifs SET seen=1 WHERE user_id=? AND seen=0", (int(user_id),))
    conn.commit()


# ─── the boards a leg is read from ──────────────────────────────────────────

_MEMO: dict = {}
_LOCK = threading.Lock()


def _read(path: Path):
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_mtime_ns, st.st_size)
    with _LOCK:
        hit = _MEMO.get(str(path))
        if hit and hit[0] == key:
            return hit[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    with _LOCK:
        _MEMO[str(path)] = (key, data)
    return data


def _jsnum(v) -> str:
    """A line as JavaScript prints it — gameBetId's own spelling, so a
    game leg's id from the page matches the one built here."""
    if v is None or v == "":
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f.is_integer() else repr(f)


def is_game(row: dict) -> bool:
    return str(row.get("kind") or "") == "game" or not row.get("player")


def game_id(row: dict) -> str:
    """engine twin of app.js gameBetId."""
    return "|".join(("game", f"{row.get('away') or ''}@{row.get('home') or ''}",
                     str(row.get("market") or row.get("bet_type") or ""),
                     str(row.get("side") or row.get("team") or ""), _jsnum(row.get("line"))))


def prop_key(player, market, side, line) -> str:
    from .betlinks import point
    return "|".join((str(player or "").strip().lower(), str(market or "").strip().lower(),
                     str(side or "").strip().upper(), point(line)))


def _rows(payload) -> dict:
    """{identity: row} for every priced pick row on a board."""
    from .betlinks import _walk
    found: list = []
    _walk(payload or {}, found)
    out: dict = {}
    for r in found:
        k = game_id(r) if is_game(r) else prop_key(r.get("player"), r.get("market"),
                                                  r.get("side"), r.get("line"))
        # A row that carries bet-slip links beats a copy of it that does not.
        if k not in out or (r.get("bet_links") and not out[k].get("bet_links")):
            out[k] = r
    return out


def boards(sport: str, data_dir: Path | None = None) -> tuple[dict, dict]:
    """(full rows, public rows) for one sport's board."""
    from . import gate
    name = SPORT_FILE.get(str(sport or "").lower())
    if not name:
        return {}, {}
    if data_dir is None:
        public = DATA / name
        full = gate.board_source(public)
    else:
        public = data_dir / name
        full = data_dir / "built" / name if (data_dir / "built" / name).exists() else public
    return _rows(_read(full)), _rows(_read(public))


def started(row: dict, now: float | None = None) -> bool:
    """Has this row's game begun? The board's own live flags, then its kickoff."""
    if row.get("live") or row.get("started") or any(
            "already started" in str(w) for w in (row.get("warnings") or [])):
        return True
    k = row.get("kickoff") or row.get("commence_time")
    if not k:
        return False
    try:
        t = _dt.datetime.fromisoformat(str(k).strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return t.timestamp() <= (now if now is not None else time.time())


def _label(row: dict) -> str:
    if not is_game(row):
        line = "" if row.get("line") in (None, "") or row.get("market") == "anytime_td" else f" {_jsnum(row.get('line'))}"
        side = str(row.get("side") or "").upper()
        mk = row.get("market_label") or str(row.get("market") or "").replace("_", " ")
        return f"{side}{line} {mk}".strip()
    if row.get("pick_label") or row.get("headline"):
        return str(row.get("pick_label") or row.get("headline"))
    kind = str(row.get("bet_type") or row.get("market") or "").lower()
    team, line = str(row.get("team") or ""), row.get("line")
    if kind == "spread" and line not in (None, ""):
        return f"{team} {'+' if float(line) > 0 else ''}{_jsnum(line)}"
    if kind == "total":
        return f"{row.get('side') or ''} {_jsnum(line)}".strip()
    if kind == "team_total":
        return f"{team} {row.get('side') or ''} {_jsnum(line)}".strip()
    return f"{team} ML"


def _leg_from(row: dict, paid: bool) -> dict:
    links = [[str(t), str(u), px] for t, u, px in (row.get("bet_links") or [])
             if str(u).lower().startswith("https://")][:12]
    try:
        odds = int(row.get("odds"))
    except (TypeError, ValueError):
        odds = None
    base = {"odds": odds, "book": str(row.get("book") or ""), "paid": bool(paid),
            "kickoff": str(row.get("kickoff") or "")[:25],
            "links": links, "label": _label(row),
            "team": str(row.get("team") or ""),
            "game_date": str(row.get("game_date") or row.get("date") or "")[:10]}
    if is_game(row):
        kind = str(row.get("bet_type") or row.get("market") or "").lower()
        base.update(kind="game", gid=game_id(row), market=kind,
                    market_label=GAME_WORDS.get(kind, kind.replace("_", " ").title()),
                    side=str(row.get("side") or ""), line=row.get("line"),
                    home=str(row.get("home") or ""), away=str(row.get("away") or ""),
                    matchup=str(row.get("matchup") or f"{row.get('away') or ''} @ {row.get('home') or ''}"))
    else:
        base.update(kind="prop", player=str(row.get("player") or ""),
                    market=str(row.get("market") or ""),
                    market_label=str(row.get("market_label") or str(row.get("market") or "").replace("_", " ")),
                    side=str(row.get("side") or ""), line=row.get("line"),
                    opponent=str(row.get("opponent") or ""))
    return base


def resolve_legs(sport: str, legs_in, data_dir: Path | None = None, now: float | None = None) -> tuple[list, str]:
    """([leg, ...], '') or ([], why). Every leg is a row on today's board."""
    full, public = boards(sport, data_dir)
    if not full:
        return [], "That board has nothing on it right now."
    out, seen = [], set()
    for l in legs_in if isinstance(legs_in, list) else []:
        if not isinstance(l, dict):
            continue
        gid = str(l.get("gid") or "")[:160]
        key = gid if gid else prop_key(str(l.get("player") or "")[:60], str(l.get("market") or "")[:40],
                                       str(l.get("side") or "")[:12], l.get("line"))
        row = full.get(key)
        if row is None:
            who = l.get("player") or l.get("label") or "One leg"
            return [], f"{str(who)[:60]} is not on today’s board at that line any more."
        if str(row.get("book") or "").lower() == "proxy":
            return [], "A leg without a real book price cannot be posted."
        if started(row, now):
            # The record rule: a pick posted after kickoff is a pick made
            # knowing part of the answer, and the profile would carry it.
            return [], f"{str(row.get('player') or row.get('matchup') or 'That game')[:60]} has already started — picks lock at kickoff."
        if key in seen:
            continue
        seen.add(key)
        out.append(_leg_from(row, paid=key not in public))
    if not (MIN_LEGS <= len(out) <= MAX_LEGS):
        return [], f"A post carries {MIN_LEGS}–{MAX_LEGS} legs."
    return out, ""


# ─── posts ──────────────────────────────────────────────────────────────────

def _post_cap(conn, user_id: int, now: float) -> str:
    """'' when this account may post now, else why not."""
    u = conn.execute("SELECT created_at FROM users WHERE id=?", (int(user_id),)).fetchone()
    young = bool(u) and (now - float(u["created_at"] or now)) < NEW_ACCOUNT_S
    cap = NEW_ACCOUNT_POSTS if young else POSTS_PER_DAY
    n = conn.execute("SELECT COUNT(*) FROM feed_posts WHERE user_id=? AND created_at>?",
                     (int(user_id), now - 86400)).fetchone()[0]
    if n >= cap:
        return (f"New accounts can post {cap} times in their first day." if young
                else f"{cap} posts a day is the limit.")
    return ""


def _prune(conn, now: float) -> None:
    # The prune rides the write, as every other accounts.db table does it.
    conn.execute("DELETE FROM feed_posts WHERE created_at<?", (now - KEEP_DAYS * 86400,))
    for t in ("feed_likes", "feed_tails", "feed_comments"):
        conn.execute(f"DELETE FROM {t} WHERE post_id NOT IN (SELECT id FROM feed_posts)")
    conn.execute("DELETE FROM feed_comment_likes WHERE comment_id NOT IN (SELECT id FROM feed_comments)")


def create_post(conn, user_id: int, sport, date, legs_in, caption,
                data_dir: Path | None = None, now: float | None = None) -> tuple[int, dict]:
    """A parlay (or single) of board legs, with an optional caption."""
    ensure_tables(conn)
    if not profile_of(conn, user_id):
        return 409, {"error": "Pick a handle first — it is the name your posts go out under.",
                     "need_handle": True}
    sport = str(sport or "").strip().lower()[:8]
    if sport not in SPORT_FILE:
        return 400, {"error": "Posts come from the NFL, college, MLB, NBA, WNBA or NHL boards."}
    caption = str(caption or "").strip()[:MAX_CAPTION]
    why = profanity.check(caption, "Your caption")
    if why:
        return 400, {"error": why}
    now = now if now is not None else time.time()
    why = _post_cap(conn, user_id, now)
    if why:
        return 429, {"error": why}
    legs, why = resolve_legs(sport, legs_in, data_dir, now=now)
    if why:
        return 400, {"error": why}
    blob = json.dumps(legs, sort_keys=True)
    same = conn.execute(
        "SELECT id FROM feed_posts WHERE user_id=? AND legs=? AND created_at>? AND hidden=0",
        (int(user_id), blob, now - 86400)).fetchone()
    if same:
        return 200, {"ok": True, "id": int(same["id"]), "already": True}
    cur = conn.execute(
        "INSERT INTO feed_posts (user_id, sport, date, legs, caption, combined, created_at, kind) "
        "VALUES (?,?,?,?,?,?,?,'parlay')",
        (int(user_id), sport, str(date or "")[:10], blob, caption, combined_american(legs), now))
    pid = int(cur.lastrowid)
    _mentions(conn, caption, user_id, pid)
    _prune(conn, now)
    conn.commit()
    return 200, {"ok": True, "id": pid, "already": False}


def create_talk(conn, user_id: int, sport, title, body, now: float | None = None) -> tuple[int, dict]:
    """A discussion post — Reddit's text post: a title, a body, a sport tag."""
    ensure_tables(conn)
    if not profile_of(conn, user_id):
        return 409, {"error": "Pick a handle first — it is the name your posts go out under.",
                     "need_handle": True}
    sport = str(sport or "").strip().lower()[:8]
    if sport and sport not in SPORT_FILE:
        sport = ""
    title = re.sub(r"\s+", " ", str(title or "")).strip()[:MAX_TITLE]
    body = str(body or "").strip()[:MAX_BODY]
    if len(title) < 3:
        return 400, {"error": "Give it a title."}
    why = profanity.check(f"{title}\n{body}", "Your post")
    if why:
        return 400, {"error": why}
    now = now if now is not None else time.time()
    why = _post_cap(conn, user_id, now)
    if why:
        return 429, {"error": why}
    cur = conn.execute(
        "INSERT INTO feed_posts (user_id, sport, date, legs, caption, combined, created_at, kind, "
        "title, body, result) VALUES (?,?,?,?,?,?,?,'text',?,?,'none')",
        (int(user_id), sport or "all", "", "[]", "", None, now, title, body))
    pid = int(cur.lastrowid)
    _mentions(conn, f"{title} {body}", user_id, pid)
    _prune(conn, now)
    conn.commit()
    return 200, {"ok": True, "id": pid}


def edit_post(conn, user_id: int, post_id: int, caption=None, title=None, body=None,
              now: float | None = None) -> tuple[int, dict]:
    """Words only, and only for 15 minutes. Legs never change: a parlay's
    legs ARE the record, and an editable record is no record."""
    ensure_tables(conn)
    r = conn.execute("SELECT * FROM feed_posts WHERE id=?", (int(post_id),)).fetchone()
    if not r or int(r["user_id"]) != int(user_id):
        return 404, {"error": "Not yours to edit."}
    now = now if now is not None else time.time()
    if now - float(r["created_at"]) > EDIT_WINDOW_S:
        return 403, {"error": "Posts can be edited for 15 minutes after posting."}
    if r["kind"] == "text":
        title = re.sub(r"\s+", " ", str(title if title is not None else r["title"])).strip()[:MAX_TITLE]
        body = str(body if body is not None else r["body"]).strip()[:MAX_BODY]
        if len(title) < 3:
            return 400, {"error": "Give it a title."}
        why = profanity.check(f"{title}\n{body}", "Your post")
        if why:
            return 400, {"error": why}
        conn.execute("UPDATE feed_posts SET title=?, body=?, edited_at=? WHERE id=?",
                     (title, body, now, int(post_id)))
    else:
        caption = str(caption if caption is not None else r["caption"]).strip()[:MAX_CAPTION]
        why = profanity.check(caption, "Your caption")
        if why:
            return 400, {"error": why}
        conn.execute("UPDATE feed_posts SET caption=?, edited_at=? WHERE id=?", (caption, now, int(post_id)))
    conn.commit()
    return 200, {"ok": True}


# ─── grading: the record nobody can type in ─────────────────────────────────

UP_SIDES = ("OVER", "YES")


def _leg_key(leg: dict):
    """(player, market, side, line) as the journal writes the same bet."""
    if leg.get("kind") == "game":
        from .ledger import game_row_keys
        bt = str(leg.get("market") or "").lower()
        bt = {"ml": "moneyline", "h2h": "moneyline"}.get(bt, bt)
        row = {"bet_type": bt, "team": leg.get("team") or "", "matchup": leg.get("matchup") or "",
               "side": leg.get("side") or "", "line": leg.get("line")}
        if bt == "moneyline":
            row["line"] = 0.5
        try:
            return game_row_keys(row, bt)
        except (TypeError, ValueError):
            return None
    line = leg.get("line")
    try:
        line = 0.5 if line in (None, "") else float(line)
    except (TypeError, ValueError):
        return None
    side = str(leg.get("side") or "").upper()
    if not leg.get("player") or side not in UP_SIDES + ("UNDER", "NO"):
        return None
    return str(leg["player"]), str(leg.get("market") or ""), side, line


def _et_date(iso: str) -> str:
    try:
        t = _dt.datetime.fromisoformat(str(iso).strip().replace("Z", "+00:00"))
    except ValueError:
        return ""
    if t.tzinfo is None:
        return t.date().isoformat()
    try:
        from zoneinfo import ZoneInfo
        return t.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except Exception:                                    # noqa: BLE001
        return t.date().isoformat()


def grade_leg(lconn, sport: str, leg: dict, post_date: str = ""):
    """'won' | 'lost' | 'push' | 'void' | None (not graded yet).

    Graded against the journal's recorded STAT at the poster's own line,
    so a leg taken at a different book's number than the journal's row
    is still graded at the number its poster saw."""
    key = _leg_key(leg)
    if key is None:
        return None
    player, market, side, line = key
    days = [d for d in {str(leg.get("game_date") or "")[:10], str(post_date or "")[:10],
                        _et_date(leg.get("kickoff") or "")} if d]
    if not days:
        return None
    q = ",".join("?" * len(days))
    rows = lconn.execute(
        f"SELECT status, actual FROM bets WHERE sport=? AND player=? AND market=? "
        f"AND status IN ('won','lost','push','void') AND (game_day IN ({q}) OR date IN ({q})) LIMIT 20",
        (sport, player, market, *days, *days)).fetchall()
    for r in rows:
        if r["status"] != "void" and r["actual"] is not None:
            a = float(r["actual"])
            if a == line:
                return "push"
            return "won" if (a > line) == (side in UP_SIDES) else "lost"
    if any(r["status"] == "void" for r in rows):
        return "void"
    return None


def _decimal(o) -> float:
    o = float(o)
    return 1 + (o / 100 if o > 0 else 100 / -o)


def post_result(legs: list) -> tuple[str, float | None]:
    """(result, units) for a parlay, one unit staked at the posted prices.
    A lost leg loses the ticket at once, as at a book; void and push legs
    drop out of the price; a leg that could never be graded keeps the
    whole post out of the record ('nograde') rather than flattering it."""
    res = [l.get("result") for l in legs]
    if "lost" in res:
        return "lost", -1.0
    if any(r is None for r in res):
        return "pending", None
    if "nograde" in res:
        return "nograde", None
    won = [l for l in legs if l.get("result") == "won"]
    if not won:
        return "push", 0.0
    dec = 1.0
    for l in won:
        if l.get("odds") is None:
            return "nograde", None
        dec *= _decimal(l["odds"])
    return "won", round(dec - 1, 3)


def _due(row, legs: list, now: float) -> bool:
    kicks = []
    for l in legs:
        k = l.get("kickoff")
        try:
            t = _dt.datetime.fromisoformat(str(k).replace("Z", "+00:00")) if k else None
        except ValueError:
            t = None
        if t is not None:
            if t.tzinfo is None:
                t = t.replace(tzinfo=_dt.timezone.utc)
            kicks.append(t.timestamp())
    first = min(kicks) if kicks else float(row["created_at"])
    return now >= first + GRADE_AFTER_S


def settle_pending(conn, opener, now: float | None = None, limit: int = 40) -> int:
    """Grade what can be graded — lazily, when the feed is read (the
    tail/fade fold), so no scheduled job is owed. `opener` opens the
    journal only when there is a post due, so a quiet read costs nothing."""
    ensure_tables(conn)
    now = now if now is not None else time.time()
    due = []
    for r in conn.execute("SELECT * FROM feed_posts WHERE kind='parlay' AND result='pending' "
                          "AND last_try<? ORDER BY last_try LIMIT 300", (now - GRADE_RETRY_S,)):
        legs = json.loads(r["legs"] or "[]")
        if _due(r, legs, now):
            due.append((r, legs))
        if len(due) >= limit:
            break
    if not due:
        return 0
    try:
        lconn = opener()
    except Exception:                                    # noqa: BLE001
        return 0
    n = 0
    try:
        for r, legs in due:
            for l in legs:
                if l.get("result") is None:
                    l["result"] = grade_leg(lconn, r["sport"], l, r["date"])
            if now - float(r["created_at"]) > GRADE_GIVE_UP_S:
                for l in legs:
                    if l.get("result") is None:
                        l["result"] = "nograde"
            result, units = post_result(legs)
            conn.execute("UPDATE feed_posts SET legs=?, result=?, units=?, graded_at=?, last_try=? WHERE id=?",
                         (json.dumps(legs, sort_keys=True), result, units,
                          now if result != "pending" else None, now, int(r["id"])))
            if result in ("won", "lost"):
                _notify(conn, int(r["user_id"]), None, result, int(r["id"]))
            n += result != "pending"
        conn.commit()
    finally:
        try:
            lconn.close()
        except Exception:                                # noqa: BLE001
            pass
    return n


def combined_american(legs: list):
    dec = 1.0
    for l in legs:
        o = l.get("odds")
        if o is None:
            return None
        dec *= _decimal(o)
    if len(legs) < 2:
        return legs[0].get("odds") if legs else None
    return round((dec - 1) * 100) if dec >= 2 else -round(100 / (dec - 1))


# ─── reading: views of posts ────────────────────────────────────────────────

def _counts(conn, table: str, ids: list, col: str = "post_id") -> dict:
    if not ids:
        return {}
    q = ",".join("?" * len(ids))
    extra = "AND hidden=0 " if table == "feed_comments" else ""
    return {int(r[0]): int(r[1]) for r in conn.execute(
        f"SELECT {col}, COUNT(*) FROM {table} WHERE {col} IN ({q}) {extra}GROUP BY {col}", ids)}


def _mine(conn, table: str, ids: list, viewer, col: str = "post_id") -> set:
    if not ids or not viewer:
        return set()
    q = ",".join("?" * len(ids))
    return {int(r[0]) for r in conn.execute(
        f"SELECT {col} FROM {table} WHERE user_id=? AND {col} IN ({q})", [int(viewer), *ids])}


def _text(s: str, strong: bool) -> str:
    return str(s or "") if strong else profanity.mask(s)


def public_leg(leg: dict, entitled: bool) -> dict:
    """What a reader sees of one leg. Never its links (Tail hands those out).
    A GRADED leg is shown to everybody: once its game is over the pick is
    in the public record anyway, exactly as the Record page shows it."""
    graded = leg.get("result") not in (None, "")
    if leg.get("paid") and not entitled and not graded:
        return {"locked": True, "kind": leg.get("kind"),
                "player": leg.get("player") or "",
                "matchup": leg.get("matchup") or "",
                "market_label": leg.get("market_label") or ""}
    keep = ("kind", "player", "market", "market_label", "side", "line", "team", "opponent",
            "home", "away", "matchup", "label", "odds", "book", "game_date", "gid", "result")
    return {k: leg.get(k) for k in keep if leg.get(k) not in (None, "")}


def _views(conn, rows, viewer, entitled: bool, strong: bool) -> list:
    ids = [int(r["id"]) for r in rows]
    likes, tails = _counts(conn, "feed_likes", ids), _counts(conn, "feed_tails", ids)
    comments = _counts(conn, "feed_comments", ids)
    liked, tailed = _mine(conn, "feed_likes", ids, viewer), _mine(conn, "feed_tails", ids, viewer)
    out = []
    for r in rows:
        legs = json.loads(r["legs"] or "[]")
        shown = [public_leg(l, entitled) for l in legs]
        locked = any(l.get("locked") for l in shown)
        pid = int(r["id"])
        words = f"{r['caption']} {r['title']} {r['body']}"
        out.append({
            "id": pid, "kind": r["kind"] or "parlay", "sport": r["sport"], "date": r["date"],
            "at": r["created_at"], "edited": bool(r["edited_at"]),
            "handle": r["handle"] or "someone", "name": r["display_name"] or "",
            "color": int(r["color"] or 0), "team": r["fav_team"] or "",
            "caption": _text(r["caption"], strong), "title": _text(r["title"], strong),
            "body": _text(r["body"], strong), "strong": profanity.has_strong(words),
            "legs": shown, "locked": locked,
            "combined": None if locked else r["combined"],
            "result": r["result"] or "pending", "units": r["units"],
            # Tail closes when its games begin: the lines are gone, and a
            # finished parlay has nothing left to copy.
            "closed": (r["kind"] or "parlay") == "parlay" and (
                (r["result"] or "pending") != "pending" or _kicked(legs)),
            "likes": likes.get(pid, 0), "liked": pid in liked,
            "tails": tails.get(pid, 0), "tailed": pid in tailed,
            "comments": comments.get(pid, 0),
            "mine": bool(viewer) and int(r["user_id"]) == int(viewer),
            "editable": bool(viewer) and int(r["user_id"]) == int(viewer)
                        and time.time() - float(r["created_at"]) <= EDIT_WINDOW_S,
        })
    return out


def _kicked(legs: list, now: float | None = None) -> bool:
    """Has any leg's game begun? Read off the kickoff each leg carries."""
    now = now if now is not None else time.time()
    for l in legs:
        k = l.get("kickoff")
        if not k:
            continue
        try:
            t = _dt.datetime.fromisoformat(str(k).replace("Z", "+00:00"))
        except ValueError:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=_dt.timezone.utc)
        if t.timestamp() <= now:
            return True
    return False


_POST_SQL = ("SELECT p.*, f.handle, f.bio, f.display_name, f.color, f.fav_team FROM feed_posts p "
             "LEFT JOIN feed_profiles f ON f.user_id=p.user_id ")


def _hot(score: int, created: float) -> float:
    """Reddit's Hot: log10 of the score plus the age term, so a post's
    rank decays by a factor of ten every 12.5 hours of age."""
    return math.log10(max(score, 1)) + (created - 1.7e9) / 45000


def feed(conn, viewer=None, entitled: bool = False, strong: bool = False,
         before: int = 0, sport: str = "", handle: str = "", order: str = "new",
         window: str = "week", kind: str = "", offset: int = 0) -> dict:
    """One page of posts. order: hot | new | top | following."""
    ensure_tables(conn)
    where, args = ["p.hidden=0"], []
    hide = blocked_ids(conn, viewer)
    if hide:
        where.append(f"p.user_id NOT IN ({','.join('?' * len(hide))})")
        args += sorted(hide)
    if sport in SPORT_FILE:
        where.append("p.sport=?")
        args.append(sport)
    if kind in ("parlay", "text"):
        where.append("p.kind=?")
        args.append(kind)
    if handle:
        where.append("f.handle=? COLLATE NOCASE")
        args.append(str(handle)[:20])
    if order == "following":
        if not viewer:
            return {"posts": [], "more": False, "next": 0, "need_signin": True}
        where.append("(p.user_id IN (SELECT followee_id FROM feed_follows WHERE follower_id=?) OR p.user_id=?)")
        args += [int(viewer), int(viewer)]
    now = time.time()
    if order in ("hot", "top"):
        span = HOT_WINDOW_S if order == "hot" else TOP_WINDOWS.get(window, TOP_WINDOWS["week"])
        if span:
            where.append("p.created_at>?")
            args.append(now - span)
        rows = conn.execute(_POST_SQL + "WHERE " + " AND ".join(where)
                            + " ORDER BY p.id DESC LIMIT 1000", args).fetchall()
        ids = [int(r["id"]) for r in rows]
        lk, tl, cm = (_counts(conn, "feed_likes", ids), _counts(conn, "feed_tails", ids),
                      _counts(conn, "feed_comments", ids))
        score = {i: lk.get(i, 0) + 2 * tl.get(i, 0) + cm.get(i, 0) for i in ids}
        if order == "hot":
            rows.sort(key=lambda r: -_hot(score[int(r["id"])], float(r["created_at"])))
        else:
            rows.sort(key=lambda r: (-score[int(r["id"])], -int(r["id"])))
        offset = max(0, int(offset or 0))
        page = rows[offset:offset + PAGE]
        return {"posts": _views(conn, page, viewer, entitled, strong),
                "more": len(rows) > offset + PAGE, "next": offset + len(page), "paged": "offset"}
    if before:
        where.append("p.id<?")
        args.append(int(before))
    rows = conn.execute(_POST_SQL + "WHERE " + " AND ".join(where) + " ORDER BY p.id DESC LIMIT ?",
                        [*args, PAGE]).fetchall()
    posts = _views(conn, rows, viewer, entitled, strong)
    return {"posts": posts, "more": len(rows) == PAGE, "next": posts[-1]["id"] if posts else 0,
            "paged": "before"}


def _comment_views(conn, post_id: int, owner: int, viewer, strong: bool) -> list:
    hide = blocked_ids(conn, viewer)
    rows = [c for c in conn.execute(
        "SELECT c.*, f.handle, f.display_name, f.color FROM feed_comments c LEFT JOIN feed_profiles f "
        "ON f.user_id=c.user_id WHERE c.post_id=? AND c.hidden=0 ORDER BY c.id LIMIT 500",
        (int(post_id),)) if int(c["user_id"]) not in hide]
    ids = [int(c["id"]) for c in rows]
    likes = _counts(conn, "feed_comment_likes", ids, "comment_id")
    liked = _mine(conn, "feed_comment_likes", ids, viewer, "comment_id")
    by_id, top = {}, []
    for c in rows:
        cid = int(c["id"])
        v = {"id": cid, "handle": c["handle"] or "someone", "name": c["display_name"] or "",
             "color": int(c["color"] or 0), "at": c["created_at"],
             "body": _text(c["body"], strong), "strong": profanity.has_strong(c["body"]),
             "likes": likes.get(cid, 0), "liked": cid in liked,
             "mine": bool(viewer) and int(c["user_id"]) == int(viewer),
             "can_delete": bool(viewer) and int(viewer) in (int(c["user_id"]), owner),
             "parent_id": c["parent_id"], "replies": []}
        by_id[cid] = v
        if c["parent_id"] and int(c["parent_id"]) in by_id:
            by_id[int(c["parent_id"])]["replies"].append(v)
        else:
            top.append(v)
    return top


def post_detail(conn, post_id: int, viewer=None, entitled: bool = False,
                strong: bool = False) -> tuple[int, dict]:
    ensure_tables(conn)
    r = conn.execute(_POST_SQL + "WHERE p.id=? AND p.hidden=0", (int(post_id),)).fetchone()
    if not r or int(r["user_id"]) in blocked_ids(conn, viewer):
        return 404, {"error": "That post is gone."}
    post = _views(conn, [r], viewer, entitled, strong)[0]
    post["comment_list"] = _comment_views(conn, post_id, int(r["user_id"]), viewer, strong)
    return 200, {"post": post}


def record_of(conn, uid: int, since: float | None = None) -> dict:
    """W-L-P, units and ROI over graded parlays — one unit a post."""
    args = [int(uid)] + ([since] if since else [])
    rows = conn.execute("SELECT result, units FROM feed_posts WHERE user_id=? AND kind='parlay' "
                        "AND hidden=0 AND result IN ('won','lost','push')"
                        + (" AND created_at>?" if since else ""), args).fetchall()
    w = sum(r["result"] == "won" for r in rows)
    lo = sum(r["result"] == "lost" for r in rows)
    p = sum(r["result"] == "push" for r in rows)
    units = round(sum(float(r["units"] or 0) for r in rows), 2)
    n = w + lo + p
    return {"w": w, "l": lo, "p": p, "units": units, "roi": round(units / n * 100, 1) if n else None,
            "n": n}


def _streak(conn, uid: int) -> str:
    out, last = 0, ""
    for r in conn.execute("SELECT result FROM feed_posts WHERE user_id=? AND kind='parlay' AND hidden=0 "
                          "AND result IN ('won','lost') ORDER BY created_at DESC LIMIT 50", (int(uid),)):
        if last and r["result"] != last:
            break
        last, out = r["result"], out + 1
    return f"{'W' if last == 'won' else 'L'}{out}" if out else ""


def profile_page(conn, handle: str, viewer=None, entitled: bool = False,
                 strong: bool = False, tab: str = "posts", before: int = 0) -> tuple[int, dict]:
    ensure_tables(conn)
    r = conn.execute("SELECT * FROM feed_profiles WHERE handle=? COLLATE NOCASE",
                     (str(handle or "").lstrip("@")[:20],)).fetchone()
    if not r or int(r["user_id"]) in blocked_ids(conn, viewer):
        return 404, {"error": "Nobody has that handle."}
    uid = int(r["user_id"])
    agg = conn.execute(
        "SELECT COUNT(*) AS posts, "
        "COALESCE(SUM((SELECT COUNT(*) FROM feed_tails t WHERE t.post_id=p.id)),0) AS tails, "
        "COALESCE(SUM((SELECT COUNT(*) FROM feed_likes l WHERE l.post_id=p.id)),0) AS likes "
        "FROM feed_posts p WHERE p.user_id=? AND p.hidden=0", (uid,)).fetchone()
    following = int(conn.execute("SELECT COUNT(*) FROM feed_follows WHERE follower_id=?", (uid,)).fetchone()[0])
    me = int(viewer) if viewer else None
    rel = {"mine": me == uid, "following": False, "follows_you": False, "blocked": False, "friend": False}
    if me and me != uid:
        rel["following"] = bool(conn.execute("SELECT 1 FROM feed_follows WHERE follower_id=? AND followee_id=?",
                                             (me, uid)).fetchone())
        rel["follows_you"] = bool(conn.execute("SELECT 1 FROM feed_follows WHERE follower_id=? AND followee_id=?",
                                               (uid, me)).fetchone())
        rel["blocked"] = bool(conn.execute("SELECT 1 FROM feed_blocks WHERE user_id=? AND blocked_id=?",
                                           (me, uid)).fetchone())
        have = {t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "friendships" in have:
            rel["friend"] = bool(conn.execute("SELECT 1 FROM friendships WHERE user_id=? AND friend_id=?",
                                              (me, uid)).fetchone())
    prof = {"handle": r["handle"], "name": r["display_name"], "bio": _text(r["bio"], strong),
            "color": int(r["color"] or 0), "team": r["fav_team"], "since": r["created_at"],
            "posts": int(agg["posts"]), "tails": int(agg["tails"]), "likes": int(agg["likes"]),
            "followers": _n_followers(conn, uid), "following_count": following,
            "record": record_of(conn, uid), "record30": record_of(conn, uid, time.time() - 30 * 86400),
            "streak": _streak(conn, uid), **rel}
    if tab == "record":
        rows = conn.execute(_POST_SQL + "WHERE p.user_id=? AND p.hidden=0 AND p.kind='parlay' "
                            "AND p.result IN ('won','lost','push') ORDER BY p.created_at DESC LIMIT 100",
                            (uid,)).fetchall()
        page = {"posts": _views(conn, rows, viewer, entitled, strong), "more": False, "next": 0}
    else:
        page = feed(conn, viewer, entitled, strong, handle=r["handle"], before=before)
    return 200, {"profile": prof, **page}


def _live(conn, post_id: int):
    return conn.execute("SELECT * FROM feed_posts WHERE id=? AND hidden=0", (int(post_id),)).fetchone()


def _reachable(conn, user_id: int, post_id: int):
    """The post, when it exists and no block stands between the two."""
    r = _live(conn, post_id)
    if r is None or int(r["user_id"]) in blocked_ids(conn, user_id):
        return None
    return r


def toggle_like(conn, user_id: int, post_id: int) -> tuple[int, dict]:
    ensure_tables(conn)
    r = _reachable(conn, user_id, post_id)
    if not r:
        return 404, {"error": "That post is gone."}
    had = conn.execute("SELECT 1 FROM feed_likes WHERE post_id=? AND user_id=?",
                       (int(post_id), int(user_id))).fetchone()
    if had:
        conn.execute("DELETE FROM feed_likes WHERE post_id=? AND user_id=?",
                     (int(post_id), int(user_id)))
    else:
        conn.execute("INSERT INTO feed_likes (post_id, user_id, created_at) VALUES (?,?,?)",
                     (int(post_id), int(user_id), time.time()))
        _notify(conn, int(r["user_id"]), user_id, "like", int(post_id))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM feed_likes WHERE post_id=?", (int(post_id),)).fetchone()[0]
    return 200, {"likes": int(n), "liked": not had}


def toggle_comment_like(conn, user_id: int, comment_id: int) -> tuple[int, dict]:
    ensure_tables(conn)
    c = conn.execute("SELECT * FROM feed_comments WHERE id=? AND hidden=0", (int(comment_id),)).fetchone()
    if not c or not _reachable(conn, user_id, c["post_id"]) or int(c["user_id"]) in blocked_ids(conn, user_id):
        return 404, {"error": "That comment is gone."}
    had = conn.execute("SELECT 1 FROM feed_comment_likes WHERE comment_id=? AND user_id=?",
                       (int(comment_id), int(user_id))).fetchone()
    if had:
        conn.execute("DELETE FROM feed_comment_likes WHERE comment_id=? AND user_id=?",
                     (int(comment_id), int(user_id)))
    else:
        conn.execute("INSERT INTO feed_comment_likes (comment_id, user_id, created_at) VALUES (?,?,?)",
                     (int(comment_id), int(user_id), time.time()))
        _notify(conn, int(c["user_id"]), user_id, "comment_like", int(c["post_id"]), int(comment_id))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM feed_comment_likes WHERE comment_id=?",
                     (int(comment_id),)).fetchone()[0]
    return 200, {"likes": int(n), "liked": not had}


# ─── the tail ───────────────────────────────────────────────────────────────

def combine_links(urls: list) -> str:
    """One bet-slip link carrying every leg, or '' when the book's format
    cannot be shown to take them.

    Only the indexed-selection format is combined: every leg's link at the
    same address, each carrying its selection as ``name[0]=value`` keys
    (FanDuel's ``marketId[0]`` / ``selectionId[0]``). The keys are
    renumbered ``[1]``, ``[2]`` … and joined. Any other shape — a path
    that differs, an unindexed selection, keys that disagree — returns ''
    and the box lists the legs one by one instead of guessing."""
    if not urls or any(not u for u in urls):
        return ""
    if len(urls) == 1:
        return urls[0]
    parts = [urlsplit(u) for u in urls]
    base = (parts[0].scheme, parts[0].netloc, parts[0].path)
    if any((p.scheme, p.netloc, p.path) != base for p in parts) or base[0] != "https":
        return ""
    plain: list | None = None
    indexed: list = []
    for i, p in enumerate(parts):
        q = parse_qsl(p.query, keep_blank_values=True)
        idx = [(k, v) for k, v in q if re.fullmatch(r"\w+\[0\]", k)]
        rest = sorted((k, v) for k, v in q if not re.fullmatch(r"\w+\[\d+\]", k))
        if not idx or len(idx) + len(rest) != len(q):
            return ""
        if plain is None:
            plain = rest
        elif rest != plain:
            return ""
        indexed += [(k[:-3] + f"[{i}]", v) for k, v in idx]
    query = urlencode((plain or []) + indexed, safe="[]")
    return urlunsplit((base[0], base[1], base[2], query, ""))


def tail_box(legs: list, sport: str, data_dir: Path | None = None) -> list:
    """[{book, combined, legs: [{label, url, price}|None per leg], have}] —
    every book holding at least one leg, the complete ones first."""
    full, _ = boards(sport, data_dir)
    per_leg = []
    for l in legs:
        key = l.get("gid") if l.get("kind") == "game" else prop_key(
            l.get("player"), l.get("market"), l.get("side"), l.get("line"))
        row = full.get(key) or {}
        # Today's links when the row is still on the board, else the ones
        # it carried when it was posted (links are banked for three days).
        fresh = [[t, u, px] for t, u, px in (row.get("bet_links") or [])
                 if str(u).lower().startswith("https://")]
        per_leg.append({str(t): (u, px) for t, u, px in (fresh or l.get("links") or [])})
    books: dict = {}
    for d in per_leg:
        for t in d:
            books.setdefault(t, None)
    out = []
    for t in books:
        cells = []
        for l, d in zip(legs, per_leg):
            u, px = d.get(t, (None, None))
            cells.append({"label": l.get("label") or "", "who": l.get("player") or l.get("matchup") or "",
                          "url": u, "price": px} if u else None)
        have = sum(1 for c in cells if c)
        combined = combine_links([c["url"] for c in cells]) if have == len(legs) else ""
        out.append({"book": t, "combined": combined, "legs": cells, "have": have})
    out.sort(key=lambda b: (-b["have"], not b["combined"], b["book"]))
    return out


def tail(conn, user_id: int, post_id: int, entitled: bool,
         data_dir: Path | None = None) -> tuple[int, dict]:
    ensure_tables(conn)
    r = _reachable(conn, user_id, post_id)
    if not r or r["kind"] == "text":
        return 404, {"error": "That post is gone."}
    legs = json.loads(r["legs"] or "[]")
    if (r["result"] or "pending") != "pending" or _kicked(legs):
        return 409, {"error": "Those games have started — this one can’t be tailed any more."}
    if any(l.get("paid") and l.get("result") in (None, "") for l in legs) and not entitled:
        return 402, {"error": "This parlay has subscriber picks in it — subscribe to tail it.",
                     "locked": True}
    had = conn.execute("SELECT 1 FROM feed_tails WHERE post_id=? AND user_id=?",
                       (int(post_id), int(user_id))).fetchone()
    if not had:
        conn.execute("INSERT INTO feed_tails (post_id, user_id, created_at) VALUES (?,?,?)",
                     (int(post_id), int(user_id), time.time()))
        _notify(conn, int(r["user_id"]), user_id, "tail", int(post_id))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM feed_tails WHERE post_id=?", (int(post_id),)).fetchone()[0]
    return 200, {"tails": int(n), "tailed": True, "n_legs": len(legs),
                 "legs": [public_leg(l, True) for l in legs],
                 "books": tail_box(legs, r["sport"], data_dir)}


# ─── comments, deletes, reports ────────────────────────────────────────────

def add_comment(conn, user_id: int, post_id: int, body, parent_id=None) -> tuple[int, dict]:
    ensure_tables(conn)
    if not profile_of(conn, user_id):
        return 409, {"error": "Pick a handle first.", "need_handle": True}
    r = _reachable(conn, user_id, post_id)
    if not r:
        return 404, {"error": "That post is gone."}
    body = str(body or "").strip()[:MAX_COMMENT]
    if not body:
        return 400, {"error": "Write something first."}
    why = profanity.check(body, "Your comment")
    if why:
        return 400, {"error": why}
    now = time.time()
    n = conn.execute("SELECT COUNT(*) FROM feed_comments WHERE user_id=? AND created_at>?",
                     (int(user_id), now - 3600)).fetchone()[0]
    if n >= COMMENTS_PER_HOUR:
        return 429, {"error": "Slow down — that is a lot of comments for one hour."}
    parent = None
    if parent_id:
        p = conn.execute("SELECT * FROM feed_comments WHERE id=? AND post_id=? AND hidden=0",
                         (int(parent_id), int(post_id))).fetchone()
        if not p:
            return 404, {"error": "That comment is gone."}
        # One level of replies, as Facebook and Instagram thread them: a
        # reply to a reply joins the same thread.
        parent = int(p["parent_id"] or p["id"])
        reply_to = int(p["user_id"])
    cur = conn.execute("INSERT INTO feed_comments (post_id, user_id, body, created_at, parent_id) "
                       "VALUES (?,?,?,?,?)", (int(post_id), int(user_id), body, now, parent))
    cid = int(cur.lastrowid)
    if parent is not None:
        _notify(conn, reply_to, user_id, "reply", int(post_id), cid)
        if int(r["user_id"]) != reply_to:
            _notify(conn, int(r["user_id"]), user_id, "comment", int(post_id), cid)
    else:
        _notify(conn, int(r["user_id"]), user_id, "comment", int(post_id), cid)
    _mentions(conn, body, user_id, int(post_id), cid)
    conn.commit()
    return 200, {"ok": True, "id": cid}


def delete(conn, user_id: int, kind: str, item_id: int) -> tuple[int, dict]:
    """Your own post; your own comment, or any comment under your post."""
    ensure_tables(conn)
    if kind == "post":
        r = conn.execute("SELECT user_id FROM feed_posts WHERE id=?", (int(item_id),)).fetchone()
        if not r or int(r["user_id"]) != int(user_id):
            return 404, {"error": "Not yours to delete."}
        conn.execute("DELETE FROM feed_comment_likes WHERE comment_id IN "
                     "(SELECT id FROM feed_comments WHERE post_id=?)", (int(item_id),))
        for t in ("feed_likes", "feed_tails", "feed_comments"):
            conn.execute(f"DELETE FROM {t} WHERE post_id=?", (int(item_id),))
        conn.execute("DELETE FROM feed_notifs WHERE post_id=?", (int(item_id),))
        conn.execute("DELETE FROM feed_posts WHERE id=?", (int(item_id),))
    elif kind == "comment":
        r = conn.execute("SELECT c.user_id, p.user_id AS owner FROM feed_comments c "
                         "JOIN feed_posts p ON p.id=c.post_id WHERE c.id=?", (int(item_id),)).fetchone()
        if not r or int(user_id) not in (int(r["user_id"]), int(r["owner"])):
            return 404, {"error": "Not yours to delete."}
        kids = [int(x[0]) for x in conn.execute("SELECT id FROM feed_comments WHERE parent_id=?", (int(item_id),))]
        for cid in [int(item_id), *kids]:
            conn.execute("DELETE FROM feed_comment_likes WHERE comment_id=?", (cid,))
            conn.execute("DELETE FROM feed_notifs WHERE comment_id=?", (cid,))
            conn.execute("DELETE FROM feed_comments WHERE id=?", (cid,))
    else:
        return 400, {"error": "Unknown kind."}
    conn.execute("DELETE FROM feed_reports WHERE kind=? AND item_id=?", (kind, int(item_id)))
    conn.commit()
    return 200, {"ok": True}


def report(conn, user_id: int, kind: str, item_id: int, reason: str = "other") -> tuple[int, dict]:
    ensure_tables(conn)
    _add(conn, "feed_reports", "reason", "TEXT NOT NULL DEFAULT ''")
    table = {"post": "feed_posts", "comment": "feed_comments"}.get(kind)
    if not table:
        return 400, {"error": "Unknown kind."}
    if not conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (int(item_id),)).fetchone():
        return 404, {"error": "That is gone already."}
    reason = reason if reason in REPORT_REASONS else "other"
    conn.execute("INSERT OR IGNORE INTO feed_reports (kind, item_id, user_id, created_at, reason) "
                 "VALUES (?,?,?,?,?)", (kind, int(item_id), int(user_id), time.time(), reason))
    n = conn.execute("SELECT COUNT(*) FROM feed_reports WHERE kind=? AND item_id=?",
                     (kind, int(item_id))).fetchone()[0]
    if n >= REPORTS_TO_HIDE:
        conn.execute(f"UPDATE {table} SET hidden=1 WHERE id=?", (int(item_id),))
    conn.commit()
    return 200, {"ok": True}


def set_hidden(conn, kind: str, item_id: int, hidden: bool) -> tuple[int, dict]:
    """The owner's switch (server checks the owner token)."""
    ensure_tables(conn)
    table = {"post": "feed_posts", "comment": "feed_comments"}.get(kind)
    if not table:
        return 400, {"error": "Unknown kind."}
    cur = conn.execute(f"UPDATE {table} SET hidden=? WHERE id=?", (1 if hidden else 0, int(item_id)))
    if not hidden:
        conn.execute("DELETE FROM feed_reports WHERE kind=? AND item_id=?", (kind, int(item_id)))
    conn.commit()
    return (200, {"ok": True}) if cur.rowcount else (404, {"error": "No such item."})


def reported(conn) -> list:
    """What readers flagged, for the owner: kind, id, reports, reasons, hidden, text."""
    ensure_tables(conn)
    _add(conn, "feed_reports", "reason", "TEXT NOT NULL DEFAULT ''")
    out = []
    for r in conn.execute("SELECT kind, item_id, COUNT(*) AS n, GROUP_CONCAT(reason) AS why "
                          "FROM feed_reports GROUP BY kind, item_id ORDER BY n DESC LIMIT 100"):
        table, col = (("feed_posts", "caption || ' ' || title || ' ' || body") if r["kind"] == "post"
                      else ("feed_comments", "body"))
        it = conn.execute(f"SELECT {col} AS text, hidden FROM {table} WHERE id=?", (r["item_id"],)).fetchone()
        if it:
            out.append({"kind": r["kind"], "id": int(r["item_id"]), "reports": int(r["n"]),
                        "reasons": sorted(set(filter(None, (r["why"] or "").split(",")))),
                        "hidden": bool(it["hidden"]), "text": str(it["text"]).strip()})
    return out


# ─── leaderboard, who to follow, search ─────────────────────────────────────

def leaders(conn, viewer=None, days: int = 30) -> dict:
    """Top bettors by units over the window (5+ graded posts to qualify),
    and the most-tailed accounts this week."""
    ensure_tables(conn)
    since = time.time() - days * 86400
    hide = blocked_ids(conn, viewer)
    mine = _following_set(conn, viewer)
    rows = conn.execute(
        "SELECT p.user_id, f.handle, f.display_name, f.color, f.fav_team, "
        "SUM(p.result='won') AS w, SUM(p.result='lost') AS l, SUM(p.result='push') AS pu, "
        "SUM(COALESCE(p.units,0)) AS u FROM feed_posts p JOIN feed_profiles f ON f.user_id=p.user_id "
        "WHERE p.kind='parlay' AND p.hidden=0 AND p.result IN ('won','lost','push') AND p.created_at>? "
        "GROUP BY p.user_id HAVING COUNT(*)>=? ORDER BY u DESC LIMIT 25", (since, LEADER_MIN)).fetchall()
    top = []
    for r in rows:
        if int(r["user_id"]) in hide:
            continue
        n = int(r["w"]) + int(r["l"]) + int(r["pu"])
        top.append({**_person(r, mine), "w": int(r["w"]), "l": int(r["l"]), "p": int(r["pu"]),
                    "units": round(float(r["u"] or 0), 2), "roi": round(float(r["u"] or 0) / n * 100, 1)})
    tailed = []
    for r in conn.execute(
            "SELECT p.user_id, f.handle, f.display_name, f.color, f.fav_team, COUNT(t.user_id) AS n "
            "FROM feed_tails t JOIN feed_posts p ON p.id=t.post_id JOIN feed_profiles f ON f.user_id=p.user_id "
            "WHERE t.created_at>? AND p.hidden=0 GROUP BY p.user_id ORDER BY n DESC LIMIT 10",
            (time.time() - 7 * 86400,)):
        if int(r["user_id"]) not in hide:
            tailed.append({**_person(r, mine), "tails": int(r["n"])})
    return {"top": top, "tailed": tailed, "days": days, "min": LEADER_MIN}


def suggestions(conn, viewer=None, n: int = 5) -> list:
    """Who to follow: the leaderboard first, then the most followed —
    never yourself, nobody you follow, nobody a block stands between."""
    ensure_tables(conn)
    skip = blocked_ids(conn, viewer) | _following_set(conn, viewer) | ({int(viewer)} if viewer else set())
    out, seen = [], set()
    for p in leaders(conn, viewer)["top"]:
        uid = _uid_of(conn, p["handle"])
        if uid not in skip and uid not in seen:
            out.append(p)
            seen.add(uid)
    for r in conn.execute("SELECT f.*, (SELECT COUNT(*) FROM feed_follows x WHERE x.followee_id=f.user_id) AS n "
                          "FROM feed_profiles f ORDER BY n DESC, f.created_at DESC LIMIT 50"):
        uid = int(r["user_id"])
        if uid not in skip and uid not in seen:
            out.append(_person(r))
            seen.add(uid)
        if len(out) >= n:
            break
    return out[:n]


def search(conn, q: str, viewer=None, entitled: bool = False, strong: bool = False) -> dict:
    ensure_tables(conn)
    q = re.sub(r"[%_]", "", str(q or "")).strip()[:40]
    if len(q) < 2:
        return {"people": [], "posts": []}
    hide = blocked_ids(conn, viewer)
    mine = _following_set(conn, viewer)
    people = [_person(r, mine) for r in conn.execute(
        "SELECT * FROM feed_profiles WHERE handle LIKE ? OR display_name LIKE ? "
        "ORDER BY (handle LIKE ?) DESC, handle LIMIT 8", (f"%{q}%", f"%{q}%", f"{q}%"))
        if int(r["user_id"]) not in hide]
    like = f"%{q}%"
    rows = [r for r in conn.execute(
        _POST_SQL + "WHERE p.hidden=0 AND (p.caption LIKE ? OR p.title LIKE ? OR p.body LIKE ? "
        "OR p.legs LIKE ?) ORDER BY p.id DESC LIMIT 20", (like, like, like, like))
        if int(r["user_id"]) not in hide]
    return {"people": people, "posts": _views(conn, rows, viewer, entitled, strong)}


def add_friend(conn, user_id: int, handle: str) -> tuple[int, dict]:
    """The profile's Add friend: the private friends layer's own request
    flow (engine/social.request_send), so the public feed and the private
    inbox join up without a second way to become friends."""
    other = _uid_of(conn, handle)
    if other is None:
        return 404, {"error": "Nobody has that handle."}
    if other in blocked_ids(conn, user_id):
        return 403, {"error": "You cannot add this account."}
    from . import social
    return social.request_send(conn, int(user_id), other)


# ─── the account's own rows (accounts.delete_user / export_user) ────────────

FEED_TABLES = ("feed_profiles", "feed_posts", "feed_likes", "feed_tails", "feed_comments",
               "feed_reports", "feed_follows", "feed_blocks", "feed_comment_likes", "feed_notifs")


def delete_user(conn, user_id: int) -> None:
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "feed_posts" not in have:
        return
    ensure_tables(conn)
    uid = int(user_id)
    mine = "SELECT id FROM feed_posts WHERE user_id=?"
    conn.execute("DELETE FROM feed_comment_likes WHERE user_id=? OR comment_id IN "
                 f"(SELECT id FROM feed_comments WHERE user_id=? OR post_id IN ({mine}))", (uid, uid, uid))
    for t in ("feed_likes", "feed_tails", "feed_comments"):
        conn.execute(f"DELETE FROM {t} WHERE user_id=? OR post_id IN ({mine})", (uid, uid))
    conn.execute("DELETE FROM feed_comments WHERE parent_id IS NOT NULL AND parent_id NOT IN "
                 "(SELECT id FROM feed_comments)")
    conn.execute(f"DELETE FROM feed_notifs WHERE user_id=? OR actor_id=? OR post_id IN ({mine})", (uid, uid, uid))
    conn.execute("DELETE FROM feed_reports WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM feed_follows WHERE follower_id=? OR followee_id=?", (uid, uid))
    conn.execute("DELETE FROM feed_blocks WHERE user_id=? OR blocked_id=?", (uid, uid))
    conn.execute("DELETE FROM feed_posts WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM feed_profiles WHERE user_id=?", (uid,))


def export_user(conn, user_id: int) -> dict:
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "feed_posts" not in have:
        return {}
    ensure_tables(conn)
    uid = int(user_id)
    prof = profile_of(conn, uid)
    posts = [{"kind": r["kind"], "sport": r["sport"], "date": r["date"], "caption": r["caption"],
              "title": r["title"], "body": r["body"], "result": r["result"],
              "legs": [public_leg(l, True) for l in json.loads(r["legs"] or "[]")],
              "created_at": r["created_at"]}
             for r in conn.execute("SELECT * FROM feed_posts WHERE user_id=? ORDER BY id", (uid,))]
    comments = [{"post_id": int(r["post_id"]), "body": r["body"], "created_at": r["created_at"]}
                for r in conn.execute("SELECT * FROM feed_comments WHERE user_id=? ORDER BY id", (uid,))]
    handles = lambda sql: [r[0] for r in conn.execute(sql, (uid,))]   # noqa: E731
    return {"profile": prof, "posts": posts, "comments": comments,
            "likes": [int(r[0]) for r in conn.execute("SELECT post_id FROM feed_likes WHERE user_id=?", (uid,))],
            "tails": [int(r[0]) for r in conn.execute("SELECT post_id FROM feed_tails WHERE user_id=?", (uid,))],
            "following": handles("SELECT f.handle FROM feed_follows x JOIN feed_profiles f "
                                 "ON f.user_id=x.followee_id WHERE x.follower_id=?"),
            "blocked": handles("SELECT f.handle FROM feed_blocks b JOIN feed_profiles f "
                               "ON f.user_id=b.blocked_id WHERE b.user_id=?")}
