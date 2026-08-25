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

* **Friends form through INVITE LINKS, never lookup.** Search-by-email
  is an oracle for which addresses hold accounts, and open friend
  requests are a spam channel to anyone whose address leaks. An invite
  is an unguessable token (the unsubscribe pattern) that its owner
  hands to a friend over a channel they already share; opening it
  signed-in forms the friendship instantly, both ways. No pending
  state, no inbound requests from strangers, no enumeration — by
  construction rather than by moderation.

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

#: Inbox rows kept per user. Shares are pointers at a board that rebuilds
#: nightly, so an old one is a dead link — pruning is honesty, not tidiness.
INBOX_KEEP = 200


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
             "name": display_name(conn, r["friend_id"])} for r in rows]


def friend_remove(conn, user_id: int, friend_id: int) -> None:
    """BOTH directions in one call. A one-sided friendship would let the
    removed side keep sending — removal has to mean the channel closed."""
    ensure_tables(conn)
    conn.execute("DELETE FROM friendships WHERE user_id=? AND friend_id=?",
                 (int(user_id), int(friend_id)))
    conn.execute("DELETE FROM friendships WHERE user_id=? AND friend_id=?",
                 (int(friend_id), int(user_id)))
    conn.commit()


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
            names[fid] = display_name(conn, fid)
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
        for t in ("pick_shares", "parlay_shares"))
    return {"shares": out, "unseen": int(unseen)}


def mark_seen(conn, user_id: int) -> None:
    ensure_tables(conn)
    conn.execute("UPDATE pick_shares SET seen=1 WHERE to_id=?",
                 (int(user_id),))
    conn.execute("UPDATE parlay_shares SET seen=1 WHERE to_id=?",
                 (int(user_id),))
    conn.commit()
