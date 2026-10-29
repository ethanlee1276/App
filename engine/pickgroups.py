"""Private pick'em groups: your own table with the people you pick against.

Ethan, 2026-10-29: "keep building ... we want to keep user retainment",
and a lot of the members are 21 to 35. The pick'em (engine/pickem) already
ranks everyone and your friends; a group is the office pool, the group
chat's league: a name, an invite link, and the same standings counted over
its members only, by wins or by beating the close. The link is how a group
brings people in: opened by somebody without an account, it waits for
their sign-up and joins them after.

WHAT A GROUP HOLDS. A name (screened like a display name), an invite code,
an owner and its members. Nothing else: the picks are the pick'em's, and a
group's tables are the public tables cut to its members (pickem.standings
and clv_table with ``only``), so a group can never show anything the
public table does not. A block still hides both ways inside a group.

WHO MAY DO WHAT. Anybody with a Social handle (the pick'em's own rule) may
start one or join one with its code, up to MAX_GROUPS. The owner may rename
it, remove a member, or make a new link (the old code stops working); a
removed member can come back only with the new link. Leaving is one tap;
an owner who leaves hands the group to the member who joined first, and
the last member out deletes it. Deleting an account takes its memberships
with it the same way (engine/accounts).

The code is eight characters from an alphabet with no look-alikes, so it
reads aloud and types on a phone; it is the only key, so it is random
(secrets) and never derived from the name or the owner.

Standard library only.
"""
from __future__ import annotations

import re
import secrets
import time

#: The most groups one account belongs to, and the most members one group has.
MAX_GROUPS = 10
MAX_MEMBERS = 200
NAME_MAX = 40
CODE_LEN = 8
#: No 0/O, 1/I/L: a code is read aloud and typed on a phone.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def ensure_tables(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS pickem_groups (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT NOT NULL,
        code       TEXT NOT NULL UNIQUE,
        owner      INTEGER NOT NULL,
        created_at REAL NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS pickem_group_members (
        group_id  INTEGER NOT NULL,
        user_id   INTEGER NOT NULL,
        joined_at REAL NOT NULL,
        PRIMARY KEY (group_id, user_id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS pickem_group_user ON pickem_group_members (user_id)")


def _code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))


def norm_code(code) -> str:
    """A typed or pasted code as stored (upper case, spaces and dashes
    dropped), or "" when it cannot be one."""
    c = re.sub(r"[^A-Za-z0-9]", "", str(code or "")).upper()
    return c if len(c) == CODE_LEN and all(ch in ALPHABET for ch in c) else ""


def _name(name) -> tuple[str, str]:
    """(the name to keep, or "", and why not)."""
    from . import profanity
    from . import socialfeed as SF
    n = re.sub(r"\s+", " ", str(name or "")).strip()[:NAME_MAX]
    if len(n) < 2:
        return "", "Give the group a name of two characters or more."
    if re.search(r"https?:|www\.|\.(com|net|org|io)\b", n, re.I):
        return "", "A group's name can't be a link."
    if not profanity.clean_name(n) or SF._reserved(n):
        return "", "That name is not available."
    return n, ""


def _handle(conn, user_id) -> bool:
    from . import socialfeed as SF
    prof = SF.profile_of(conn, user_id)
    return bool(prof and prof.get("handle"))


def _count(conn, user_id) -> int:
    return conn.execute("SELECT COUNT(*) FROM pickem_group_members WHERE user_id = ?", (int(user_id),)).fetchone()[0]


def members(conn, group_id) -> set:
    ensure_tables(conn)
    return {int(u) for (u,) in conn.execute("SELECT user_id FROM pickem_group_members WHERE group_id = ?",
                                            (int(group_id),))}


def _group(conn, group_id):
    return conn.execute("SELECT id, name, code, owner, created_at FROM pickem_groups WHERE id = ?",
                        (int(group_id),)).fetchone()


def _out(conn, row, viewer) -> dict:
    n = conn.execute("SELECT COUNT(*) FROM pickem_group_members WHERE group_id = ?", (row[0],)).fetchone()[0]
    return {"id": int(row[0]), "name": row[1], "code": row[2], "owner": int(row[3]) == int(viewer), "members": int(n)}


def mine(conn, user_id) -> list:
    """The groups this account is in, oldest joined first, each with its code."""
    ensure_tables(conn)
    rows = conn.execute("SELECT g.id, g.name, g.code, g.owner, g.created_at FROM pickem_groups g "
                        "JOIN pickem_group_members m ON m.group_id = g.id WHERE m.user_id = ? "
                        "ORDER BY m.joined_at, g.id", (int(user_id),)).fetchall()
    return [_out(conn, r, user_id) for r in rows]


def is_member(conn, group_id, user_id) -> bool:
    ensure_tables(conn)
    return bool(conn.execute("SELECT 1 FROM pickem_group_members WHERE group_id = ? AND user_id = ?",
                             (int(group_id), int(user_id))).fetchone())


def create(conn, user_id, name, now: float | None = None) -> tuple[int, dict]:
    ensure_tables(conn)
    if not _handle(conn, user_id):
        return 403, {"error": "Make your Social profile first: the table shows your handle."}
    n, why = _name(name)
    if not n:
        return 400, {"error": why}
    if _count(conn, user_id) >= MAX_GROUPS:
        return 400, {"error": f"You are in {MAX_GROUPS} groups, the most there can be. Leave one to start another."}
    t = time.time() if now is None else float(now)
    for _ in range(5):
        try:
            cur = conn.execute("INSERT INTO pickem_groups (name, code, owner, created_at) VALUES (?, ?, ?, ?)",
                               (n, _code(), int(user_id), t))
            break
        except Exception as exc:                              # noqa: BLE001 — a code taken already: draw again
            if "UNIQUE" not in str(exc):
                raise
    else:
        return 503, {"error": "Could not make a link just now. Try again."}
    gid = int(cur.lastrowid)
    conn.execute("INSERT INTO pickem_group_members (group_id, user_id, joined_at) VALUES (?, ?, ?)",
                 (gid, int(user_id), t))
    conn.commit()
    return 200, {"group": _out(conn, _group(conn, gid), user_id)}


def peek(conn, code) -> dict | None:
    """What an invite link shows before anybody joins: the name, how many
    are in it and who started it. None for a code that is not a group's."""
    from . import socialfeed as SF
    ensure_tables(conn)
    c = norm_code(code)
    row = conn.execute("SELECT id, name, owner FROM pickem_groups WHERE code = ?", (c,)).fetchone() if c else None
    if not row:
        return None
    n = conn.execute("SELECT COUNT(*) FROM pickem_group_members WHERE group_id = ?", (row[0],)).fetchone()[0]
    prof = SF.profile_of(conn, row[2]) or {}
    return {"name": row[1], "members": int(n), "by": prof.get("handle") or ""}


def join(conn, user_id, code, now: float | None = None) -> tuple[int, dict]:
    ensure_tables(conn)
    c = norm_code(code)
    row = conn.execute("SELECT id, name, code, owner, created_at FROM pickem_groups WHERE code = ?",
                       (c,)).fetchone() if c else None
    if not row:
        return 404, {"error": "That invite link has expired or is not right. Ask for a new one."}
    if not _handle(conn, user_id):
        return 403, {"error": "Make your Social profile first: the table shows your handle."}
    if is_member(conn, row[0], user_id):
        return 200, {"group": _out(conn, row, user_id), "already": True}
    if _count(conn, user_id) >= MAX_GROUPS:
        return 400, {"error": f"You are in {MAX_GROUPS} groups, the most there can be. Leave one to join this."}
    if len(members(conn, row[0])) >= MAX_MEMBERS:
        return 400, {"error": f"{row[1]} is full ({MAX_MEMBERS} players)."}
    conn.execute("INSERT INTO pickem_group_members (group_id, user_id, joined_at) VALUES (?, ?, ?)",
                 (int(row[0]), int(user_id), time.time() if now is None else float(now)))
    conn.commit()
    return 200, {"group": _out(conn, row, user_id)}


def leave(conn, user_id, group_id, commit: bool = True) -> tuple[int, dict]:
    """Out of a group; an owner hands it to the earliest member left, and
    the last one out deletes it. ``commit=False`` leaves the transaction to
    the caller (an account's deletion is one transaction: engine/accounts)."""
    ensure_tables(conn)
    row = _group(conn, group_id)
    if not row or not is_member(conn, group_id, user_id):
        return 404, {"error": "You are not in that group."}
    conn.execute("DELETE FROM pickem_group_members WHERE group_id = ? AND user_id = ?", (int(group_id), int(user_id)))
    nxt = conn.execute("SELECT user_id FROM pickem_group_members WHERE group_id = ? ORDER BY joined_at, user_id "
                       "LIMIT 1", (int(group_id),)).fetchone()
    if not nxt:
        conn.execute("DELETE FROM pickem_groups WHERE id = ?", (int(group_id),))
    elif int(row[3]) == int(user_id):
        conn.execute("UPDATE pickem_groups SET owner = ? WHERE id = ?", (int(nxt[0]), int(group_id)))
    if commit:
        conn.commit()
    return 200, {"ok": True}


def _owned(conn, user_id, group_id):
    row = _group(conn, group_id)
    return row if row and int(row[3]) == int(user_id) else None


def rename(conn, user_id, group_id, name) -> tuple[int, dict]:
    ensure_tables(conn)
    if not _owned(conn, user_id, group_id):
        return 403, {"error": "Only the group's owner can rename it."}
    n, why = _name(name)
    if not n:
        return 400, {"error": why}
    conn.execute("UPDATE pickem_groups SET name = ? WHERE id = ?", (n, int(group_id)))
    conn.commit()
    return 200, {"group": _out(conn, _group(conn, group_id), user_id)}


def new_code(conn, user_id, group_id) -> tuple[int, dict]:
    """A new invite link; the old one stops working."""
    ensure_tables(conn)
    if not _owned(conn, user_id, group_id):
        return 403, {"error": "Only the group's owner can make a new link."}
    for _ in range(5):
        try:
            conn.execute("UPDATE pickem_groups SET code = ? WHERE id = ?", (_code(), int(group_id)))
            break
        except Exception as exc:                              # noqa: BLE001
            if "UNIQUE" not in str(exc):
                raise
    else:
        # Never "a new link" while the old one still works.
        return 503, {"error": "Could not make a new link just now. Try again."}
    conn.commit()
    return 200, {"group": _out(conn, _group(conn, group_id), user_id)}


def remove(conn, user_id, group_id, handle) -> tuple[int, dict]:
    """The owner takes a member out by their handle."""
    from . import socialfeed as SF
    ensure_tables(conn)
    if not _owned(conn, user_id, group_id):
        return 403, {"error": "Only the group's owner can remove someone."}
    SF.ensure_tables(conn)
    r = conn.execute("SELECT user_id FROM feed_profiles WHERE LOWER(handle) = LOWER(?)",
                     (str(handle or "").lstrip("@")[:20],)).fetchone()
    if not r or int(r[0]) == int(user_id) or not is_member(conn, group_id, r[0]):
        return 404, {"error": "Nobody by that name is in the group."}
    conn.execute("DELETE FROM pickem_group_members WHERE group_id = ? AND user_id = ?", (int(group_id), int(r[0])))
    conn.commit()
    return 200, {"group": _out(conn, _group(conn, group_id), user_id)}


def forget(conn, user_id) -> None:
    """An account going: out of every group, the way leaving does, inside the
    deletion's own transaction (nothing committed here)."""
    ensure_tables(conn)
    for (gid,) in conn.execute("SELECT group_id FROM pickem_group_members WHERE user_id = ?",
                               (int(user_id),)).fetchall():
        leave(conn, user_id, gid, commit=False)


def act(conn, user_id, body: dict, now: float | None = None) -> tuple[int, dict]:
    """The page's one POST: {"do": create|join|leave|rename|code|remove, ...}."""
    do = str((body or {}).get("do") or "")
    gid = (body or {}).get("group")
    try:
        gid = int(gid) if gid is not None else None
    except (TypeError, ValueError):
        gid = None
    if do == "create":
        return create(conn, user_id, body.get("name"), now)
    if do == "join":
        return join(conn, user_id, body.get("code"), now)
    if gid is None:
        return 400, {"error": "Which group?"}
    if do == "leave":
        return leave(conn, user_id, gid)
    if do == "rename":
        return rename(conn, user_id, gid, body.get("name"))
    if do == "code":
        return new_code(conn, user_id, gid)
    if do == "remove":
        return remove(conn, user_id, gid, body.get("handle"))
    return 400, {"error": "Unknown group action."}
