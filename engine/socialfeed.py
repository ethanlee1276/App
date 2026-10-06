"""The public feed: parlays people post, and the Tail button under them.

Ethan, 2026-10-06: *"adding a social page where users can make parlays and
share them on the site then we show a "tail" button that automatically
creates that parlay on any sportsbook so any user can tail the picks or
parlays … make it a whale's tail as the button … show a counter for how
many people click it and tail it … a like feature … comments … a bio …
write on the parlay post."*

WHAT CHANGED FROM AUGUST. engine/social.py refused a feed of strangers
("a moderation product") and kept every share between friends. Ethan has
now asked for the public version, so this module is that moderation
product, kept as small as it can be:

* **Slurs are refused, swearing is masked** (engine/profanity). The
  writer's words are stored as written; the reader decides whether to
  see the strong ones.
* **A post needs a handle**, chosen here, so nobody is named in public by
  their email's local part (social.display_name's fallback is fine for
  friends who came through your invite link; it is not fine for a feed).
* **Report and hide.** Three different accounts reporting a post or a
  comment hides it; the owner can hide or restore anything with the
  owner token.
* **Rate caps** on posts and comments, so one account cannot fill it.

THE PAYWALL STILL HOLDS. A leg is resolved by the SERVER against the
private board — the client sends which row, never a price, a link or a
URL — and a leg that is not on the public (redacted) copy of that board
is a PAID leg. Paid legs show only the pick's identity (player and
market: the pointer rule from engine/social) to a reader who is not
entitled, and that reader cannot tail the post. With the paywall off,
every reader is entitled and every leg shows. No model number — no
probability, edge, projection or tier — is ever stored on a post.

THE TAIL BUTTON opens the parlay at the books. What "automatically
creates the parlay" can honestly mean depends on the book's link format:
a book whose bet-slip links carry indexed selections (FanDuel's
``marketId[0]=…&selectionId[0]=…``) can take every leg in ONE link, and
:func:`combine_links` builds it. For every other book the box lists
one bet-slip link per leg — each tap adds that leg to the same slip.
Nothing here places a bet; the site still takes no wagers.
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import profanity

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"

MAX_CAPTION = 280
MAX_COMMENT = 280
MAX_BIO = 160
HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
RESERVED = {"qellys", "qellysbook", "admin", "owner", "zeno", "moderator", "mod",
            "support", "official", "staff", "system", "everyone", "here"}
MIN_LEGS = 1
MAX_LEGS = 3          # the slip's own cap (SLIP_MAX in app.js)
POSTS_PER_DAY = 10
COMMENTS_PER_HOUR = 30
REPORTS_TO_HIDE = 3
PAGE = 20
KEEP_DAYS = 30

#: The six sports boards a leg can come from — the same map Bet it uses.
SPORT_FILE = {"nfl": "recommendations.json", "cfb": "cfb.json",
              "mlb": "mlb_recommendations.json", "nba": "nba.json",
              "wnba": "wnba.json", "nhl": "nhl.json"}

GAME_WORDS = {"spread": "Spread", "total": "Game total", "team_total": "Team total",
              "moneyline": "Moneyline", "ml": "Moneyline", "h2h": "Moneyline",
              "run_line": "Run line", "puck_line": "Puck line"}


def ensure_tables(conn) -> None:
    """Additive, safe on every call — the posture every accounts.db module keeps."""
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
    """)
    conn.commit()


# ─── profiles ────────────────────────────────────────────────────────────────

def profile_of(conn, user_id: int) -> dict | None:
    ensure_tables(conn)
    r = conn.execute("SELECT handle, bio, created_at FROM feed_profiles WHERE user_id=?",
                     (int(user_id),)).fetchone()
    return {"handle": r["handle"], "bio": r["bio"], "since": r["created_at"]} if r else None


def profile_set(conn, user_id: int, handle, bio) -> tuple[int, dict]:
    """Choose (or change) the handle and write the bio."""
    ensure_tables(conn)
    handle = str(handle or "").strip().lstrip("@")
    bio = re.sub(r"\s+", " ", str(bio or "")).strip()[:MAX_BIO]
    if not HANDLE_RE.match(handle):
        return 400, {"error": "A handle is 3–20 letters, numbers or underscores."}
    if handle.lower() in RESERVED or not profanity.clean_name(handle):
        return 400, {"error": "That handle is not available."}
    why = profanity.check(bio, "Your bio")
    if why:
        return 400, {"error": why}
    taken = conn.execute("SELECT user_id FROM feed_profiles WHERE handle=? COLLATE NOCASE",
                         (handle,)).fetchone()
    if taken and int(taken["user_id"]) != int(user_id):
        return 409, {"error": "Somebody already has that handle."}
    now = time.time()
    conn.execute(
        "INSERT INTO feed_profiles (user_id, handle, bio, created_at, updated_at) "
        "VALUES (?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET handle=excluded.handle, "
        "bio=excluded.bio, updated_at=excluded.updated_at",
        (int(user_id), handle, bio, now, now))
    conn.commit()
    return 200, {"ok": True, "profile": profile_of(conn, user_id)}


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


def resolve_legs(sport: str, legs_in, data_dir: Path | None = None) -> tuple[list, str]:
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
        if key in seen:
            continue
        seen.add(key)
        out.append(_leg_from(row, paid=key not in public))
    if not (MIN_LEGS <= len(out) <= MAX_LEGS):
        return [], f"A post carries {MIN_LEGS}–{MAX_LEGS} legs."
    return out, ""


def combined_american(legs: list):
    dec = 1.0
    for l in legs:
        o = l.get("odds")
        if o is None:
            return None
        dec *= (1 + o / 100) if o > 0 else (1 + 100 / -o)
    if len(legs) < 2:
        return legs[0].get("odds") if legs else None
    return round((dec - 1) * 100) if dec >= 2 else -round(100 / (dec - 1))


# ─── posts ──────────────────────────────────────────────────────────────────

def create_post(conn, user_id: int, sport, date, legs_in, caption,
                data_dir: Path | None = None) -> tuple[int, dict]:
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
    now = time.time()
    n = conn.execute("SELECT COUNT(*) FROM feed_posts WHERE user_id=? AND created_at>?",
                     (int(user_id), now - 86400)).fetchone()[0]
    if n >= POSTS_PER_DAY:
        return 429, {"error": f"{POSTS_PER_DAY} posts a day is the limit."}
    legs, why = resolve_legs(sport, legs_in, data_dir)
    if why:
        return 400, {"error": why}
    blob = json.dumps(legs, sort_keys=True)
    same = conn.execute(
        "SELECT id FROM feed_posts WHERE user_id=? AND legs=? AND created_at>? AND hidden=0",
        (int(user_id), blob, now - 86400)).fetchone()
    if same:
        return 200, {"ok": True, "id": int(same["id"]), "already": True}
    cur = conn.execute(
        "INSERT INTO feed_posts (user_id, sport, date, legs, caption, combined, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (int(user_id), sport, str(date or "")[:10], blob, caption, combined_american(legs), now))
    # The prune rides the write, as every other accounts.db table does it.
    conn.execute("DELETE FROM feed_posts WHERE created_at<?", (now - KEEP_DAYS * 86400,))
    for t in ("feed_likes", "feed_tails", "feed_comments"):
        conn.execute(f"DELETE FROM {t} WHERE post_id NOT IN (SELECT id FROM feed_posts)")
    conn.commit()
    return 200, {"ok": True, "id": int(cur.lastrowid), "already": False}


def _counts(conn, table: str, ids: list) -> dict:
    if not ids:
        return {}
    q = ",".join("?" * len(ids))
    return {int(r[0]): int(r[1]) for r in conn.execute(
        f"SELECT post_id, COUNT(*) FROM {table} WHERE post_id IN ({q}) "
        + ("AND hidden=0 " if table == "feed_comments" else "") + "GROUP BY post_id", ids)}


def _mine(conn, table: str, ids: list, viewer) -> set:
    if not ids or not viewer:
        return set()
    q = ",".join("?" * len(ids))
    return {int(r[0]) for r in conn.execute(
        f"SELECT post_id FROM {table} WHERE user_id=? AND post_id IN ({q})", [int(viewer), *ids])}


def _text(s: str, strong: bool) -> str:
    return str(s or "") if strong else profanity.mask(s)


def public_leg(leg: dict, entitled: bool) -> dict:
    """What a reader sees of one leg. Never its links (Tail hands those out)."""
    if leg.get("paid") and not entitled:
        return {"locked": True, "kind": leg.get("kind"),
                "player": leg.get("player") or "",
                "matchup": leg.get("matchup") or "",
                "market_label": leg.get("market_label") or ""}
    keep = ("kind", "player", "market", "market_label", "side", "line", "team", "opponent",
            "home", "away", "matchup", "label", "odds", "book", "game_date", "gid")
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
        out.append({
            "id": pid, "sport": r["sport"], "date": r["date"], "at": r["created_at"],
            "handle": r["handle"] or "someone", "bio": _text(r["bio"] or "", strong),
            "caption": _text(r["caption"], strong),
            "strong": profanity.has_strong(r["caption"]) or profanity.has_strong(r["bio"] or ""),
            "legs": shown, "locked": locked,
            "combined": None if locked else r["combined"],
            "likes": likes.get(pid, 0), "liked": pid in liked,
            "tails": tails.get(pid, 0), "tailed": pid in tailed,
            "comments": comments.get(pid, 0),
            "mine": bool(viewer) and int(r["user_id"]) == int(viewer),
        })
    return out


_POST_SQL = ("SELECT p.*, f.handle, f.bio FROM feed_posts p "
             "LEFT JOIN feed_profiles f ON f.user_id=p.user_id ")


def feed(conn, viewer=None, entitled: bool = False, strong: bool = False,
         before: int = 0, sport: str = "", handle: str = "", order: str = "new") -> dict:
    ensure_tables(conn)
    where, args = ["p.hidden=0"], []
    if before:
        where.append("p.id<?")
        args.append(int(before))
    if sport in SPORT_FILE:
        where.append("p.sport=?")
        args.append(sport)
    if handle:
        where.append("f.handle=? COLLATE NOCASE")
        args.append(str(handle)[:20])
    sql = _POST_SQL + "WHERE " + " AND ".join(where)
    if order == "top":
        # Most tailed in the last three days — what the room is riding.
        sql += (" AND p.created_at>? ORDER BY (SELECT COUNT(*) FROM feed_tails t "
                "WHERE t.post_id=p.id) DESC, p.id DESC LIMIT ?")
        args += [time.time() - 3 * 86400, PAGE]
    else:
        sql += " ORDER BY p.id DESC LIMIT ?"
        args.append(PAGE)
    rows = conn.execute(sql, args).fetchall()
    posts = _views(conn, rows, viewer, entitled, strong)
    return {"posts": posts, "more": len(rows) == PAGE and order != "top",
            "next": posts[-1]["id"] if posts else 0}


def post_detail(conn, post_id: int, viewer=None, entitled: bool = False,
                strong: bool = False) -> tuple[int, dict]:
    ensure_tables(conn)
    r = conn.execute(_POST_SQL + "WHERE p.id=? AND p.hidden=0", (int(post_id),)).fetchone()
    if not r:
        return 404, {"error": "That post is gone."}
    post = _views(conn, [r], viewer, entitled, strong)[0]
    owner = int(r["user_id"])
    post["comment_list"] = [{
        "id": int(c["id"]), "handle": c["handle"] or "someone", "at": c["created_at"],
        "body": _text(c["body"], strong), "strong": profanity.has_strong(c["body"]),
        "mine": bool(viewer) and int(c["user_id"]) == int(viewer),
        "can_delete": bool(viewer) and int(viewer) in (int(c["user_id"]), owner),
    } for c in conn.execute(
        "SELECT c.*, f.handle FROM feed_comments c LEFT JOIN feed_profiles f "
        "ON f.user_id=c.user_id WHERE c.post_id=? AND c.hidden=0 ORDER BY c.id LIMIT 300",
        (int(post_id),))]
    return 200, {"post": post}


def profile_page(conn, handle: str, viewer=None, entitled: bool = False,
                 strong: bool = False) -> tuple[int, dict]:
    ensure_tables(conn)
    r = conn.execute("SELECT * FROM feed_profiles WHERE handle=? COLLATE NOCASE",
                     (str(handle or "")[:20],)).fetchone()
    if not r:
        return 404, {"error": "Nobody has that handle."}
    uid = int(r["user_id"])
    stats = conn.execute(
        "SELECT COUNT(*) AS posts, "
        "COALESCE(SUM((SELECT COUNT(*) FROM feed_tails t WHERE t.post_id=p.id)),0) AS tails, "
        "COALESCE(SUM((SELECT COUNT(*) FROM feed_likes l WHERE l.post_id=p.id)),0) AS likes "
        "FROM feed_posts p WHERE p.user_id=? AND p.hidden=0", (uid,)).fetchone()
    return 200, {"profile": {"handle": r["handle"], "bio": _text(r["bio"], strong),
                             "since": r["created_at"], "posts": int(stats["posts"]),
                             "tails": int(stats["tails"]), "likes": int(stats["likes"]),
                             "mine": bool(viewer) and uid == int(viewer)},
                 **feed(conn, viewer, entitled, strong, handle=r["handle"])}


def _live(conn, post_id: int):
    return conn.execute("SELECT * FROM feed_posts WHERE id=? AND hidden=0",
                        (int(post_id),)).fetchone()


def toggle_like(conn, user_id: int, post_id: int) -> tuple[int, dict]:
    ensure_tables(conn)
    if not _live(conn, post_id):
        return 404, {"error": "That post is gone."}
    had = conn.execute("SELECT 1 FROM feed_likes WHERE post_id=? AND user_id=?",
                       (int(post_id), int(user_id))).fetchone()
    if had:
        conn.execute("DELETE FROM feed_likes WHERE post_id=? AND user_id=?",
                     (int(post_id), int(user_id)))
    else:
        conn.execute("INSERT INTO feed_likes (post_id, user_id, created_at) VALUES (?,?,?)",
                     (int(post_id), int(user_id), time.time()))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM feed_likes WHERE post_id=?", (int(post_id),)).fetchone()[0]
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
    r = _live(conn, post_id)
    if not r:
        return 404, {"error": "That post is gone."}
    legs = json.loads(r["legs"] or "[]")
    if any(l.get("paid") for l in legs) and not entitled:
        return 402, {"error": "This parlay has subscriber picks in it — subscribe to tail it.",
                     "locked": True}
    conn.execute("INSERT OR IGNORE INTO feed_tails (post_id, user_id, created_at) VALUES (?,?,?)",
                 (int(post_id), int(user_id), time.time()))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM feed_tails WHERE post_id=?", (int(post_id),)).fetchone()[0]
    return 200, {"tails": int(n), "tailed": True, "n_legs": len(legs),
                 "legs": [public_leg(l, True) for l in legs],
                 "books": tail_box(legs, r["sport"], data_dir)}


# ─── comments, deletes, reports ────────────────────────────────────────────

def add_comment(conn, user_id: int, post_id: int, body) -> tuple[int, dict]:
    ensure_tables(conn)
    if not profile_of(conn, user_id):
        return 409, {"error": "Pick a handle first.", "need_handle": True}
    if not _live(conn, post_id):
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
    cur = conn.execute("INSERT INTO feed_comments (post_id, user_id, body, created_at) VALUES (?,?,?,?)",
                       (int(post_id), int(user_id), body, now))
    conn.commit()
    return 200, {"ok": True, "id": int(cur.lastrowid)}


def delete(conn, user_id: int, kind: str, item_id: int) -> tuple[int, dict]:
    """Your own post; your own comment, or any comment under your post."""
    ensure_tables(conn)
    if kind == "post":
        r = conn.execute("SELECT user_id FROM feed_posts WHERE id=?", (int(item_id),)).fetchone()
        if not r or int(r["user_id"]) != int(user_id):
            return 404, {"error": "Not yours to delete."}
        for t in ("feed_likes", "feed_tails", "feed_comments"):
            conn.execute(f"DELETE FROM {t} WHERE post_id=?", (int(item_id),))
        conn.execute("DELETE FROM feed_posts WHERE id=?", (int(item_id),))
    elif kind == "comment":
        r = conn.execute("SELECT c.user_id, p.user_id AS owner FROM feed_comments c "
                         "JOIN feed_posts p ON p.id=c.post_id WHERE c.id=?", (int(item_id),)).fetchone()
        if not r or int(user_id) not in (int(r["user_id"]), int(r["owner"])):
            return 404, {"error": "Not yours to delete."}
        conn.execute("DELETE FROM feed_comments WHERE id=?", (int(item_id),))
    else:
        return 400, {"error": "Unknown kind."}
    conn.execute("DELETE FROM feed_reports WHERE kind=? AND item_id=?", (kind, int(item_id)))
    conn.commit()
    return 200, {"ok": True}


def report(conn, user_id: int, kind: str, item_id: int) -> tuple[int, dict]:
    ensure_tables(conn)
    table = {"post": "feed_posts", "comment": "feed_comments"}.get(kind)
    if not table:
        return 400, {"error": "Unknown kind."}
    if not conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (int(item_id),)).fetchone():
        return 404, {"error": "That is gone already."}
    conn.execute("INSERT OR IGNORE INTO feed_reports (kind, item_id, user_id, created_at) VALUES (?,?,?,?)",
                 (kind, int(item_id), int(user_id), time.time()))
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
    """What readers flagged, for the owner: kind, id, reports, hidden, text."""
    ensure_tables(conn)
    out = []
    for r in conn.execute("SELECT kind, item_id, COUNT(*) AS n FROM feed_reports "
                          "GROUP BY kind, item_id ORDER BY n DESC LIMIT 100"):
        table, col = (("feed_posts", "caption") if r["kind"] == "post" else ("feed_comments", "body"))
        it = conn.execute(f"SELECT {col} AS text, hidden FROM {table} WHERE id=?", (r["item_id"],)).fetchone()
        if it:
            out.append({"kind": r["kind"], "id": int(r["item_id"]), "reports": int(r["n"]),
                        "hidden": bool(it["hidden"]), "text": it["text"]})
    return out


# ─── the account's own rows (accounts.delete_user / export_user) ────────────

FEED_TABLES = ("feed_profiles", "feed_posts", "feed_likes", "feed_tails",
               "feed_comments", "feed_reports")


def delete_user(conn, user_id: int) -> None:
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "feed_posts" not in have:
        return
    uid = int(user_id)
    mine = "SELECT id FROM feed_posts WHERE user_id=?"
    for t in ("feed_likes", "feed_tails", "feed_comments"):
        conn.execute(f"DELETE FROM {t} WHERE user_id=? OR post_id IN ({mine})", (uid, uid))
    conn.execute("DELETE FROM feed_reports WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM feed_posts WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM feed_profiles WHERE user_id=?", (uid,))


def export_user(conn, user_id: int) -> dict:
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "feed_posts" not in have:
        return {}
    uid = int(user_id)
    prof = profile_of(conn, uid)
    posts = [{"sport": r["sport"], "date": r["date"], "caption": r["caption"],
              "legs": [public_leg(l, True) for l in json.loads(r["legs"] or "[]")],
              "created_at": r["created_at"]}
             for r in conn.execute("SELECT * FROM feed_posts WHERE user_id=? ORDER BY id", (uid,))]
    comments = [{"post_id": int(r["post_id"]), "body": r["body"], "created_at": r["created_at"]}
                for r in conn.execute("SELECT * FROM feed_comments WHERE user_id=? ORDER BY id", (uid,))]
    return {"profile": prof, "posts": posts, "comments": comments,
            "likes": [int(r[0]) for r in conn.execute("SELECT post_id FROM feed_likes WHERE user_id=?", (uid,))],
            "tails": [int(r[0]) for r in conn.execute("SELECT post_id FROM feed_tails WHERE user_id=?", (uid,))]}
