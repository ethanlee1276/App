"""Friends, and picks sent between them.

Ethan, 2026-08-25: *"lets add a social network on the app where users can
send picks back and forth between there friends."*

WHAT THIS IS AND DELIBERATELY IS NOT. Friends — a mutual connection
between two accounts — and a private pick inbox. There is no public
feed, no follower graph, no discovery, and no page where a stranger's
words appear in front of you. A feed of strangers is a moderation
product; picks between people who already know each other is a feature.
The share cards and pick permalinks cover the OUTSIDE of the app; this
is the inside.

THE TWO RULES EVERYTHING BELOW IS BUILT AROUND
----------------------------------------------
* **A shared pick is a POINTER, never a copy.** A share row stores the
  pick's identity — sport, date, player, market — and none of its
  content: no side, no line, no odds, no projection, no edge, no stake.
  The recipient opens it through the same board fetch every page uses,
  where THEIR entitlement applies. Carried content would be the paywall's
  cleanest bypass: one subscriber feeding a paid board to any number of
  free friends, one share at a time. This is the pick-permalink rule
  (engine/routes.pick_slug), applied to messages.

* **Friends form through INVITE LINKS or NAMED REQUESTS — never email.**
  The first cut allowed links only; Ethan asked for lookup (2026-08-25:
  "add in where you can look up someone's user name on the site and add
  them as a friend, then the friend request will go through the message
  inbox"), and the way it is built keeps every protection the refusal
  existed for. Search matches the DISPLAY NAME only — the streak name,
  the one name this site has, chosen to appear in public — so an
  account is findable exactly when its owner named it, and an email
  address remains an oracle nobody can query. A hit does not open a
  channel: it creates a REQUEST the recipient answers from their inbox,
  capped per sender (:data:`MAX_PENDING_REQUESTS`), deduped per pair,
  and carrying nothing but the asker's name. Invite links keep working
  unchanged and stay the only path to someone who never named
  themselves.

Tables live in accounts.db beside the accounts they belong to, created
here (the streak/tailfade posture), deleted with the account, included
in the export.
"""

from __future__ import annotations

import json
import secrets
import time

#: An invite works for a week and for up to this many acceptances — one
#: link can be dropped in a group chat. Multi-use is why revoke exists.
INVITE_TTL_S = 7 * 86400
INVITE_MAX_USES = 25

#: The ceiling on one account's friendships. Not a social limit — a
#: blast-radius one: `share_pick` fans out to friends one row each, and
#: an unbounded graph makes every write unbounded with it.
MAX_FRIENDS = 100

#: A note rides along, capped where a text message is capped. It is the
#: only free text in the whole feature and it is only ever shown to a
#: friend the recipient chose to add.
MAX_NOTE = 280

#: Legs a shared parlay may carry. Two is the smallest parlay there is;
#: eight is where every book stops taking props seriously anyway.
MIN_PARLAY_LEGS = 2
MAX_PARLAY_LEGS = 8

#: Friend requests one account may have outstanding. The cap is what
#: keeps name-search from becoming the spam channel the module header
#: refuses: twenty unanswered askings is a person being ignored, not a
#: person still making friends.
MAX_PENDING_REQUESTS = 20

#: Search results returned per query — enough to find a name, few
#: enough that the endpoint is useless as an enumeration pump.
FIND_LIMIT = 8

#: Inbox rows kept per user. Shares are pointers at a board that rebuilds
#: nightly, so an old one is a dead link — pruning is honesty, not tidiness.
INBOX_KEEP = 200

#: A text message's ceiling, and how much of one conversation is kept.
#: Long enough to talk a pick over, short enough that this never
#: becomes a document store; the prune rides every send like the
#: share prunes do.
DM_MAX = 500
DM_KEEP_PER_PAIR = 500

#: A nickname is capped like the display name it stands in for.
NICK_MAX = 24


def ensure_tables(conn) -> None:
    """Additive, safe on every call — same posture as the streak game."""
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS friendships (
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        friend_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        PRIMARY KEY (user_id, friend_id)
      );
      CREATE TABLE IF NOT EXISTS friend_invites (
        token      TEXT PRIMARY KEY,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        uses       INTEGER NOT NULL DEFAULT 0,
        revoked    INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS pick_shares (
        id         INTEGER PRIMARY KEY,
        from_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        to_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        sport      TEXT NOT NULL,
        date       TEXT NOT NULL,
        player     TEXT NOT NULL,
        market     TEXT NOT NULL,
        note       TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        seen       INTEGER NOT NULL DEFAULT 0
      );
      CREATE INDEX IF NOT EXISTS pick_shares_inbox
        ON pick_shares(to_id, created_at);
      CREATE TABLE IF NOT EXISTS parlay_shares (
        id         INTEGER PRIMARY KEY,
        from_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        to_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        sport      TEXT NOT NULL,
        date       TEXT NOT NULL,
        legs       TEXT NOT NULL,
        note       TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        seen       INTEGER NOT NULL DEFAULT 0
      );
      CREATE INDEX IF NOT EXISTS parlay_shares_inbox
        ON parlay_shares(to_id, created_at);
      CREATE TABLE IF NOT EXISTS dm_messages (
        id         INTEGER PRIMARY KEY,
        from_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        to_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        body       TEXT NOT NULL,
        created_at REAL NOT NULL,
        seen       INTEGER NOT NULL DEFAULT 0
      );
      CREATE INDEX IF NOT EXISTS dm_pair
        ON dm_messages(from_id, to_id, created_at);
      CREATE TABLE IF NOT EXISTS friend_nicknames (
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        friend_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        nickname   TEXT NOT NULL,
        PRIMARY KEY (user_id, friend_id)
      );
      CREATE TABLE IF NOT EXISTS friend_requests (
        id         INTEGER PRIMARY KEY,
        from_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        to_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        UNIQUE (from_id, to_id)
      );
    """)
    conn.commit()


# --- identity, shown to friends only -----------------------------------------

def display_name(conn, user_id: int) -> str:
    """What a friend sees. The streak name when one was chosen (it is the
    one display name this site has), else the email's LOCAL PART — a
    friend got here through your invite link, but the full address is
    still not the app's to repeat."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='streak_state'"
    ).fetchone()
    if row is not None:
        st = conn.execute("SELECT name FROM streak_state WHERE user_id=?",
                          (int(user_id),)).fetchone()
        if st and (st["name"] or "").strip():
            return st["name"].strip()[:24]
    u = conn.execute("SELECT email FROM users WHERE id=?",
                     (int(user_id),)).fetchone()
    return (u["email"].split("@", 1)[0][:24] if u else "someone")


def name_for(conn, viewer: int, other: int) -> str:
    """What THIS viewer calls that person: their private nickname when
    they set one, the display name otherwise. Ethan, 2026-08-26: "add a
    nickname to your friends so you don't have to see there username in
    the chat if you don't want to." Private means private — the nickname
    lives only in the viewer's rows and is never shown to, or leaked at,
    the friend it names."""
    ensure_tables(conn)
    row = conn.execute(
        "SELECT nickname FROM friend_nicknames WHERE user_id=? AND friend_id=?",
        (int(viewer), int(other))).fetchone()
    if row and (row["nickname"] or "").strip():
        return row["nickname"].strip()[:NICK_MAX]
    return display_name(conn, other)


def nickname_set(conn, me: int, friend_id: int, nickname: str
                 ) -> tuple[int, dict]:
    """Set (or, with an empty string, clear) my nickname for one friend.
    Friends-only like every channel here — you cannot label a stranger."""
    ensure_tables(conn)
    ok = conn.execute("SELECT 1 FROM friendships WHERE user_id=? AND friend_id=?",
                      (int(me), int(friend_id))).fetchone()
    if not ok:
        return 403, {"error": "You can only nickname your friends."}
    nickname = str(nickname or "").strip()[:NICK_MAX]
    if nickname:
        conn.execute(
            "INSERT OR REPLACE INTO friend_nicknames (user_id, friend_id, "
            "nickname) VALUES (?,?,?)", (int(me), int(friend_id), nickname))
    else:
        conn.execute("DELETE FROM friend_nicknames WHERE user_id=? AND "
                     "friend_id=?", (int(me), int(friend_id)))
    conn.commit()
    return 200, {"name": name_for(conn, me, friend_id),
                 "username": display_name(conn, friend_id)}


# --- invites -----------------------------------------------------------------

def invite_get_or_create(conn, user_id: int) -> dict:
    """The account's live invite link, minting one if none stands.

    ONE live invite per account, reused until revoked or expired: a
    fresh token per view would orphan every link already sent, which is
    the unsubscribe lesson (mint once, keep it standing).
    """
    ensure_tables(conn)
    now = time.time()
    row = conn.execute(
        "SELECT token, created_at, uses FROM friend_invites "
        "WHERE user_id=? AND revoked=0 ORDER BY created_at DESC LIMIT 1",
        (int(user_id),)).fetchone()
    if row and now - row["created_at"] < INVITE_TTL_S and row["uses"] < INVITE_MAX_USES:
        return {"token": row["token"],
                "expires_in_s": int(INVITE_TTL_S - (now - row["created_at"]))}
    token = secrets.token_urlsafe(18)
    conn.execute("INSERT INTO friend_invites (token, user_id, created_at) "
                 "VALUES (?,?,?)", (token, int(user_id), now))
    conn.commit()
    return {"token": token, "expires_in_s": INVITE_TTL_S}


def invite_revoke(conn, user_id: int) -> None:
    ensure_tables(conn)
    conn.execute("UPDATE friend_invites SET revoked=1 WHERE user_id=?",
                 (int(user_id),))
    conn.commit()


def invite_accept(conn, user_id: int, token: str) -> tuple[int, dict]:
    """Open a friend's link, signed in → instant mutual friendship.

    THE ANSWER FOR A DEAD TOKEN IS THE SAME AS FOR A FAKE ONE. An error
    that distinguishes "expired" from "never existed" turns this
    endpoint into a token oracle; "that invite is not live" covers every
    failure a guesser could probe, and the real holder can just mint a
    new link.
    """
    ensure_tables(conn)
    tok = str(token or "").strip()
    if not tok or len(tok) < 16:
        return 400, {"error": "That invite is not live."}
    now = time.time()
    row = conn.execute(
        "SELECT user_id, created_at, uses, revoked FROM friend_invites "
        "WHERE token=?", (tok,)).fetchone()
    if (row is None or row["revoked"] or row["uses"] >= INVITE_MAX_USES
            or now - row["created_at"] >= INVITE_TTL_S):
        return 400, {"error": "That invite is not live."}
    owner = int(row["user_id"])
    me = int(user_id)
    if owner == me:
        return 400, {"error": "That is your own invite link."}
    if _n_friends(conn, me) >= MAX_FRIENDS or _n_friends(conn, owner) >= MAX_FRIENDS:
        return 400, {"error": "One of you has a full friends list."}
    already = conn.execute(
        "SELECT 1 FROM friendships WHERE user_id=? AND friend_id=?",
        (me, owner)).fetchone()
    if already:
        return 200, {"friend": display_name(conn, owner), "already": True}
    conn.execute("INSERT INTO friendships (user_id, friend_id, created_at) "
                 "VALUES (?,?,?)", (me, owner, now))
    conn.execute("INSERT INTO friendships (user_id, friend_id, created_at) "
                 "VALUES (?,?,?)", (owner, me, now))
    conn.execute("UPDATE friend_invites SET uses=uses+1 WHERE token=?", (tok,))
    conn.commit()
    return 200, {"friend": display_name(conn, owner), "already": False}


def _n_friends(conn, user_id: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM friendships WHERE user_id=?",
                        (int(user_id),)).fetchone()[0]


def friends_list(conn, user_id: int) -> list[dict]:
    ensure_tables(conn)
    rows = conn.execute(
        "SELECT friend_id, created_at FROM friendships WHERE user_id=? "
        "ORDER BY created_at", (int(user_id),)).fetchall()
    return [{"id": int(r["friend_id"]),
             "name": name_for(conn, user_id, r["friend_id"]),
             "username": display_name(conn, r["friend_id"])} for r in rows]


def friend_remove(conn, user_id: int, friend_id: int) -> None:
    """BOTH directions in one call. A one-sided friendship would let the
    removed side keep sending — removal has to mean the channel closed."""
    ensure_tables(conn)
    conn.execute("DELETE FROM friendships WHERE user_id=? AND friend_id=?",
                 (int(user_id), int(friend_id)))
    conn.execute("DELETE FROM friendships WHERE user_id=? AND friend_id=?",
                 (int(friend_id), int(user_id)))
    conn.execute("DELETE FROM friend_nicknames WHERE (user_id=? AND friend_id=?)"
                 " OR (user_id=? AND friend_id=?)",
                 (int(user_id), int(friend_id), int(friend_id), int(user_id)))
    conn.commit()


# --- name search and requests ------------------------------------------------

def find_users(conn, me: int, q: str) -> list[dict]:
    """Accounts whose DISPLAY NAME contains ``q`` — and nothing else.

    The display name is the streak name: chosen, public by intent, and
    absent by default — so an account is findable exactly when its
    owner named it. Emails never match here, which keeps the address
    oracle closed however this endpoint is hammered. Each hit says how
    it already stands with the asker (friend / asked / asked_me) so the
    page can draw the right button instead of a second guess."""
    ensure_tables(conn)
    q = " ".join(str(q or "").split()).lower()
    if len(q) < 2:
        return []
    has = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='streak_state'").fetchone()
    if has is None:
        return []
    me = int(me)
    friends = {int(r["friend_id"]) for r in conn.execute(
        "SELECT friend_id FROM friendships WHERE user_id=?", (me,))}
    asked = {int(r["to_id"]) for r in conn.execute(
        "SELECT to_id FROM friend_requests WHERE from_id=?", (me,))}
    asked_me = {int(r["from_id"]) for r in conn.execute(
        "SELECT from_id FROM friend_requests WHERE to_id=?", (me,))}
    out = []
    for r in conn.execute(
            "SELECT user_id, name FROM streak_state WHERE name != '' "
            "ORDER BY name"):
        uid = int(r["user_id"])
        if uid == me or q not in r["name"].lower():
            continue
        out.append({"id": uid, "name": r["name"],
                    "standing": ("friend" if uid in friends
                                 else "asked" if uid in asked
                                 else "asked_me" if uid in asked_me
                                 else "")})
        if len(out) >= FIND_LIMIT:
            break
    return out


def request_send(conn, from_id: int, to_id: int) -> tuple[int, dict]:
    """Ask to be friends. The answer happens in the recipient's inbox.

    Asking someone who already asked YOU is both of you saying yes, so
    it accepts their request instead of stacking a second one."""
    ensure_tables(conn)
    me, them = int(from_id), int(to_id)
    if me == them:
        return 400, {"error": "That would be you."}
    if not conn.execute("SELECT 1 FROM users WHERE id=?", (them,)).fetchone():
        return 400, {"error": "That account is not here."}
    if conn.execute("SELECT 1 FROM friendships WHERE user_id=? AND friend_id=?",
                    (me, them)).fetchone():
        return 200, {"already_friends": True}
    reverse = conn.execute(
        "SELECT id FROM friend_requests WHERE from_id=? AND to_id=?",
        (them, me)).fetchone()
    if reverse:
        return request_answer(conn, me, int(reverse["id"]), True)
    if conn.execute("SELECT 1 FROM friend_requests WHERE from_id=? AND to_id=?",
                    (me, them)).fetchone():
        return 200, {"requested": True, "already": True}
    pending = conn.execute(
        "SELECT COUNT(*) FROM friend_requests WHERE from_id=?",
        (me,)).fetchone()[0]
    if pending >= MAX_PENDING_REQUESTS:
        return 400, {"error": f"{MAX_PENDING_REQUESTS} unanswered requests "
                              "is the ceiling — wait for some answers."}
    if _n_friends(conn, me) >= MAX_FRIENDS:
        return 400, {"error": "Your friends list is full."}
    conn.execute("INSERT INTO friend_requests (from_id, to_id, created_at) "
                 "VALUES (?,?,?)", (me, them, time.time()))
    conn.commit()
    return 200, {"requested": True, "already": False}


def request_answer(conn, me: int, req_id: int,
                   accept: bool) -> tuple[int, dict]:
    """Answer one request FROM the recipient's side. Declining deletes
    it quietly — the asker is never told, because "declined" delivered
    as a notification is a small cruelty with no product in it."""
    ensure_tables(conn)
    row = conn.execute(
        "SELECT id, from_id FROM friend_requests WHERE id=? AND to_id=?",
        (int(req_id), int(me))).fetchone()
    if row is None:
        return 404, {"error": "That request is not here any more."}
    asker = int(row["from_id"])
    conn.execute("DELETE FROM friend_requests WHERE id=?", (int(row["id"]),))
    if not accept:
        conn.commit()
        return 200, {"declined": True}
    if _n_friends(conn, me) >= MAX_FRIENDS or _n_friends(conn, asker) >= MAX_FRIENDS:
        conn.commit()
        return 400, {"error": "One of you has a full friends list."}
    now = time.time()
    for a, b in ((int(me), asker), (asker, int(me))):
        conn.execute("INSERT OR IGNORE INTO friendships "
                     "(user_id, friend_id, created_at) VALUES (?,?,?)",
                     (a, b, now))
    # A stray mirror request between the same pair is settled too.
    conn.execute("DELETE FROM friend_requests WHERE from_id=? AND to_id=?",
                 (int(me), asker))
    conn.commit()
    return 200, {"friend": display_name(conn, asker), "accepted": True}


def requests_in(conn, me: int) -> list[dict]:
    ensure_tables(conn)
    return [{"id": int(r["id"]), "from": display_name(conn, r["from_id"]),
             "created_at": r["created_at"]}
            for r in conn.execute(
                "SELECT id, from_id, created_at FROM friend_requests "
                "WHERE to_id=? ORDER BY created_at DESC", (int(me),))]


# --- the shares --------------------------------------------------------------

def share_pick(conn, from_id: int, to_id: int, sport: str, date: str,
               player: str, market: str, note: str = "") -> tuple[int, dict]:
    """Send one pick to one friend — the POINTER, never the content.

    The identity fields are the ONLY pick fields accepted, by signature:
    there is no argument through which a side, a line or a price could
    even arrive here, which beats validating them away. See the module
    header for why.
    """
    ensure_tables(conn)
    ok = conn.execute("SELECT 1 FROM friendships WHERE user_id=? AND friend_id=?",
                      (int(from_id), int(to_id))).fetchone()
    if not ok:
        return 403, {"error": "You can only send picks to your friends."}
    sport = str(sport or "").strip().lower()[:8]
    date = str(date or "").strip()[:10]
    player = str(player or "").strip()[:60]
    market = str(market or "").strip()[:40]
    if not (sport and player and market):
        return 400, {"error": "That pick is missing its identity."}
    note = str(note or "").strip()[:MAX_NOTE]
    dup = conn.execute(
        "SELECT 1 FROM pick_shares WHERE from_id=? AND to_id=? AND sport=? "
        "AND date=? AND player=? AND market=?",
        (int(from_id), int(to_id), sport, date, player, market)).fetchone()
    if dup:
        return 200, {"sent": True, "already": True}
    conn.execute(
        "INSERT INTO pick_shares (from_id, to_id, sport, date, player, market,"
        " note, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (int(from_id), int(to_id), sport, date, player, market, note,
         time.time()))
    # The prune rides the write so no cron is owed — the lazy-fold rule
    # the streak and tail/fade already keep.
    conn.execute(
        "DELETE FROM pick_shares WHERE to_id=? AND id NOT IN "
        "(SELECT id FROM pick_shares WHERE to_id=? ORDER BY created_at DESC "
        "LIMIT ?)", (int(to_id), int(to_id), INBOX_KEEP))
    conn.commit()
    return 200, {"sent": True, "already": False}


def share_parlay(conn, from_id: int, to_id: int, sport: str, date: str,
                 legs: list, note: str = "") -> tuple[int, dict]:
    """Send a built parlay to one friend — the POINTER rule, leg by leg.

    A leg is a {player, market} identity and NOTHING else, enforced the
    same way share_pick enforces it: this function reads exactly those
    two keys out of each leg dict, so a side, a line or a price sent by
    a crafted client lands nowhere. The recipient's slip re-prices the
    legs off THEIR board, under THEIR entitlement — a parlay that
    carried its own numbers would be the paywall bypass with a bow on.
    """
    ensure_tables(conn)
    ok = conn.execute("SELECT 1 FROM friendships WHERE user_id=? AND friend_id=?",
                      (int(from_id), int(to_id))).fetchone()
    if not ok:
        return 403, {"error": "You can only send picks to your friends."}
    sport = str(sport or "").strip().lower()[:8]
    date = str(date or "").strip()[:10]
    clean = []
    for l in legs if isinstance(legs, list) else []:
        if not isinstance(l, dict):
            continue
        player = str(l.get("player") or "").strip()[:60]
        market = str(l.get("market") or "").strip()[:40]
        if player and market:
            clean.append({"player": player, "market": market})
    if not sport or not (MIN_PARLAY_LEGS <= len(clean) <= MAX_PARLAY_LEGS):
        return 400, {"error": f"A parlay is {MIN_PARLAY_LEGS}–"
                              f"{MAX_PARLAY_LEGS} named legs."}
    note = str(note or "").strip()[:MAX_NOTE]
    blob = json.dumps(clean, sort_keys=True)
    dup = conn.execute(
        "SELECT 1 FROM parlay_shares WHERE from_id=? AND to_id=? AND sport=? "
        "AND date=? AND legs=?",
        (int(from_id), int(to_id), sport, date, blob)).fetchone()
    if dup:
        return 200, {"sent": True, "already": True}
    conn.execute(
        "INSERT INTO parlay_shares (from_id, to_id, sport, date, legs, note,"
        " created_at) VALUES (?,?,?,?,?,?,?)",
        (int(from_id), int(to_id), sport, date, blob, note, time.time()))
    conn.execute(
        "DELETE FROM parlay_shares WHERE to_id=? AND id NOT IN "
        "(SELECT id FROM parlay_shares WHERE to_id=? ORDER BY created_at DESC "
        "LIMIT ?)", (int(to_id), int(to_id), INBOX_KEEP))
    conn.commit()
    return 200, {"sent": True, "already": False}


def inbox(conn, user_id: int, limit: int = 50) -> dict:
    """What friends sent, newest first, with the unseen count for the
    badge. Reading does NOT mark seen — the page says when it has
    actually shown them (`mark_seen`), so a background poll cannot eat
    the badge."""
    ensure_tables(conn)
    names = {}

    def _name(fid):
        fid = int(fid)
        if fid not in names:
            names[fid] = name_for(conn, user_id, fid)
        return names[fid]

    out = []
    for r in conn.execute(
            "SELECT id, from_id, sport, date, player, market, note, "
            "created_at, seen FROM pick_shares WHERE to_id=? "
            "ORDER BY created_at DESC LIMIT ?", (int(user_id), int(limit))):
        out.append({"kind": "pick", "id": int(r["id"]), "from": _name(r["from_id"]),
                    "sport": r["sport"], "date": r["date"],
                    "player": r["player"], "market": r["market"],
                    "note": r["note"], "created_at": r["created_at"],
                    "seen": bool(r["seen"])})
    for r in conn.execute(
            "SELECT id, from_id, sport, date, legs, note, created_at, seen "
            "FROM parlay_shares WHERE to_id=? "
            "ORDER BY created_at DESC LIMIT ?", (int(user_id), int(limit))):
        try:
            legs = json.loads(r["legs"])
        except ValueError:
            legs = []
        out.append({"kind": "parlay", "id": int(r["id"]),
                    "from": _name(r["from_id"]),
                    "sport": r["sport"], "date": r["date"], "legs": legs,
                    "note": r["note"], "created_at": r["created_at"],
                    "seen": bool(r["seen"])})
    out.sort(key=lambda s: s["created_at"], reverse=True)
    out = out[:int(limit)]
    unseen = sum(int(conn.execute(
        f"SELECT COUNT(*) FROM {t} WHERE to_id=? AND seen=0",
        (int(user_id),)).fetchone()[0])
        for t in ("pick_shares", "parlay_shares", "dm_messages"))
    return {"shares": out, "unseen": int(unseen)}


def sent(conn, user_id: int, limit: int = 30) -> list[dict]:
    """What YOU sent, newest first — the Messages page's Sent tab.
    Same pointer-shaped rows the inbox gets, with the recipient named."""
    ensure_tables(conn)
    names = {}

    def _name(uid):
        uid = int(uid)
        if uid not in names:
            names[uid] = name_for(conn, user_id, uid)
        return names[uid]

    out = []
    for r in conn.execute(
            "SELECT id, to_id, sport, date, player, market, note, created_at "
            "FROM pick_shares WHERE from_id=? "
            "ORDER BY created_at DESC LIMIT ?", (int(user_id), int(limit))):
        out.append({"kind": "pick", "id": int(r["id"]), "to": _name(r["to_id"]),
                    "sport": r["sport"], "date": r["date"],
                    "player": r["player"], "market": r["market"],
                    "note": r["note"], "created_at": r["created_at"]})
    for r in conn.execute(
            "SELECT id, to_id, sport, date, legs, note, created_at "
            "FROM parlay_shares WHERE from_id=? "
            "ORDER BY created_at DESC LIMIT ?", (int(user_id), int(limit))):
        try:
            legs = json.loads(r["legs"])
        except ValueError:
            legs = []
        out.append({"kind": "parlay", "id": int(r["id"]), "to": _name(r["to_id"]),
                    "sport": r["sport"], "date": r["date"], "legs": legs,
                    "note": r["note"], "created_at": r["created_at"]})
    out.sort(key=lambda s: s["created_at"], reverse=True)
    return out[:int(limit)]


def mark_seen(conn, user_id: int, friend_id=None) -> None:
    """Everything shown is read. With `friend_id`, only that
    conversation — the thread view calls it when it opens, so the other
    threads keep their unread dots."""
    ensure_tables(conn)
    for t in ("pick_shares", "parlay_shares", "dm_messages"):
        if friend_id is None:
            conn.execute(f"UPDATE {t} SET seen=1 WHERE to_id=?",
                         (int(user_id),))
        else:
            conn.execute(f"UPDATE {t} SET seen=1 WHERE to_id=? AND from_id=?",
                         (int(user_id), int(friend_id)))
    conn.commit()


# --- the conversations -------------------------------------------------------
#
# Ethan, 2026-08-26: "I want too be able too actually text people on
# here along with sending the picks … there is no actual like message
# area too text back and forth with someone."
#
# A text is just words between two friends. It carries no pick fields at
# all, so the pointer rule has nothing to police here — but the FRIENDS
# gate is the same one the shares keep: no friendship row, no message,
# so a stranger cannot cold-DM anybody through a crafted POST.

def dm_send(conn, from_id: int, to_id: int, body: str) -> tuple[int, dict]:
    """One text to one friend. Friends-only, bounded, pruned in place —
    the same lazy-fold shape as the share writes, so no cron is owed."""
    ensure_tables(conn)
    ok = conn.execute("SELECT 1 FROM friendships WHERE user_id=? AND friend_id=?",
                      (int(from_id), int(to_id))).fetchone()
    if not ok:
        return 403, {"error": "You can only message your friends."}
    body = str(body or "").strip()[:DM_MAX]
    if not body:
        return 400, {"error": "Say something first."}
    conn.execute(
        "INSERT INTO dm_messages (from_id, to_id, body, created_at, seen) "
        "VALUES (?,?,?,?,0)",
        (int(from_id), int(to_id), body, time.time()))
    # Prune the PAIR (both directions together) so an old conversation
    # stays a conversation, not one side's monologue.
    conn.execute(
        "DELETE FROM dm_messages WHERE "
        "((from_id=? AND to_id=?) OR (from_id=? AND to_id=?)) "
        "AND id NOT IN (SELECT id FROM dm_messages WHERE "
        "((from_id=? AND to_id=?) OR (from_id=? AND to_id=?)) "
        "ORDER BY created_at DESC, id DESC LIMIT ?)",
        (int(from_id), int(to_id), int(to_id), int(from_id),
         int(from_id), int(to_id), int(to_id), int(from_id),
         DM_KEEP_PER_PAIR))
    conn.commit()
    return 200, {"sent": True}


def thread(conn, me: int, friend_id: int, limit: int = 100) -> tuple[int, dict]:
    """One conversation, oldest first, texts and shares interleaved the
    way they actually happened. Only a friend's thread opens — asking
    for a stranger's id gets the same refusal a stranger's DM would."""
    ensure_tables(conn)
    me, friend_id = int(me), int(friend_id)
    ok = conn.execute("SELECT 1 FROM friendships WHERE user_id=? AND friend_id=?",
                      (me, friend_id)).fetchone()
    if not ok:
        return 403, {"error": "You can only message your friends."}
    items = []
    # `seen` rides every item: on YOUR bubbles it is the read receipt
    # (did the friend see it), on theirs it drives the unread state.
    for r in conn.execute(
            "SELECT id, from_id, body, created_at, seen FROM dm_messages "
            "WHERE (from_id=? AND to_id=?) OR (from_id=? AND to_id=?)",
            (me, friend_id, friend_id, me)):
        items.append({"kind": "text", "id": int(r["id"]),
                      "mine": int(r["from_id"]) == me,
                      "body": r["body"], "created_at": r["created_at"],
                      "seen": bool(r["seen"])})
    for r in conn.execute(
            "SELECT id, from_id, sport, date, player, market, note, "
            "created_at, seen FROM pick_shares WHERE "
            "(from_id=? AND to_id=?) OR (from_id=? AND to_id=?)",
            (me, friend_id, friend_id, me)):
        items.append({"kind": "pick", "id": int(r["id"]),
                      "mine": int(r["from_id"]) == me,
                      "sport": r["sport"], "date": r["date"],
                      "player": r["player"], "market": r["market"],
                      "note": r["note"], "created_at": r["created_at"],
                      "seen": bool(r["seen"])})
    for r in conn.execute(
            "SELECT id, from_id, sport, date, legs, note, created_at, seen "
            "FROM parlay_shares WHERE "
            "(from_id=? AND to_id=?) OR (from_id=? AND to_id=?)",
            (me, friend_id, friend_id, me)):
        try:
            legs = json.loads(r["legs"])
        except ValueError:
            legs = []
        items.append({"kind": "parlay", "id": int(r["id"]),
                      "mine": int(r["from_id"]) == me,
                      "sport": r["sport"], "date": r["date"], "legs": legs,
                      "note": r["note"], "created_at": r["created_at"],
                      "seen": bool(r["seen"])})
    items.sort(key=lambda s: s["created_at"])
    items = items[-int(limit):]
    return 200, {"friend": name_for(conn, me, friend_id),
                 "username": display_name(conn, friend_id),
                 "friend_id": friend_id, "items": items}


def _preview(row) -> str:
    """One line for the conversation list — an identity, never a line."""
    if row["kind"] == "text":
        body = row["body"]
        return body if len(body) <= 80 else body[:79] + "\u2026"
    if row["kind"] == "pick":
        return f'Pick: {row["player"]} \u00b7 {row["market"]}'
    n = len(row.get("legs") or [])
    return f"{n}-leg parlay"


def threads(conn, me: int) -> list[dict]:
    """The conversation list: every friend, the last thing said between
    you, and how much of it you have not read. Friends you have never
    talked to are still listed — a conversation has to start somewhere —
    sorted under the live ones."""
    ensure_tables(conn)
    me = int(me)
    out = []
    for f in friends_list(conn, me):
        fid = int(f["id"])
        last = None
        code, t = thread(conn, me, fid, limit=1)
        if code == 200 and t["items"]:
            row = t["items"][-1]
            last = {"kind": row["kind"], "mine": row["mine"],
                    "preview": _preview(row),
                    "created_at": row["created_at"]}
        unseen = sum(int(conn.execute(
            f"SELECT COUNT(*) FROM {tab} WHERE to_id=? AND from_id=? "
            "AND seen=0", (me, fid)).fetchone()[0])
            for tab in ("pick_shares", "parlay_shares", "dm_messages"))
        out.append({"friend_id": fid, "name": f["name"],
                    "username": f["username"], "last": last,
                    "unseen": int(unseen)})
    out.sort(key=lambda t: (t["last"] is None,
                            -(t["last"] or {}).get("created_at", 0),
                            t["name"].lower()))
    return out
