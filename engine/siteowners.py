"""The site's owners: the accounts the Owner desk opens for, and no others.

Ethan, 2026-11-02: "my other accounts have access too the owners page too.
Only the account with [his two addresses] should have access to that page".
The desk (engine/ownerdesk, engine/owneraccounts, engine/whoson) used to open
for the verified Qellys_Book account; now it opens for the accounts named
here, by account, and for nobody else.

BY ACCOUNT, NOT BY ADDRESS. A list of addresses would let in whoever signs up
with one of them first — signing up does not prove an address (engine/
accounts.create_user) — so an address is turned into its account once, on the
box, by the owner, with the account's username and the day it was made
printed to check:

    python3 -m engine.siteowners add you@example.com other@example.com
    python3 -m engine.siteowners list
    python3 -m engine.siteowners remove other@example.com

An address with no account is refused (make the account, then add it). The
addresses are typed on the box and never kept in this repository, which is
public. Deleting an account takes it off the list (ON DELETE CASCADE, and
accounts.delete_user names the table).

UNTIL THE LIST HAS ANYBODY ON IT, the verified Qellys_Book account opens the
desk, as it did, so the owner is never locked out by an upgrade; from the
first add, the list alone. The owner token (QB_OWNER_TOKEN) stays the door for
the box's own scripts. The site's problems (engine/owneralerts) go to every
listed account's phones.

Standard library only. The addresses are never logged.
"""
from __future__ import annotations

import sqlite3
import sys
import time


def init(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS site_owners (
        user_id  INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        added_at REAL NOT NULL)""")
    conn.commit()


def owner_ids(conn) -> set:
    """The listed accounts that still exist."""
    try:
        return {int(r[0]) for r in conn.execute(
            "SELECT o.user_id FROM site_owners o JOIN users u ON u.id = o.user_id")}
    except sqlite3.OperationalError:          # never initialised: nobody listed
        return set()


def is_owner(conn, user_id) -> bool:
    """May this account open the Owner desk? The listed accounts; until there
    are any, the verified Qellys_Book account."""
    if not user_id:
        return False
    listed = owner_ids(conn)
    if listed:
        return int(user_id) in listed
    from . import whoson as W
    return W.is_site_account(conn, user_id)


def desk_accounts(conn) -> list:
    """Every account the desk opens for: whose phones hear the site's problems."""
    listed = owner_ids(conn)
    if listed:
        return sorted(listed)
    from . import owneralerts as OA
    uid = OA.site_account(conn)
    return [uid] if uid else []


def add(conn, email, now: float | None = None) -> tuple[bool, str]:
    """List the account with exactly this address (as the site stores
    addresses: trimmed, lower case). ``(ok, a line to print)``."""
    from . import accounts as A
    init(conn)
    e = A.normalize_email(email)
    row = conn.execute("SELECT id, created_at FROM users WHERE email = ?", (e,)).fetchone()
    if not row:
        return False, "No account has that address. Make the account first, then add it."
    conn.execute("INSERT OR IGNORE INTO site_owners (user_id, added_at) VALUES (?, ?)",
                 (int(row[0]), time.time() if now is None else float(now)))
    conn.commit()
    return True, _line(conn, int(row[0]), row[1])


def remove(conn, email) -> tuple[bool, str]:
    from . import accounts as A
    init(conn)
    row = conn.execute("SELECT id FROM users WHERE email = ?", (A.normalize_email(email),)).fetchone()
    if not row:
        return False, "No account has that address."
    gone = conn.execute("DELETE FROM site_owners WHERE user_id = ?", (int(row[0]),)).rowcount
    conn.commit()
    return bool(gone), ("Taken off the list." if gone else "That account was not on the list.")


def _line(conn, uid: int, created) -> str:
    from . import socialfeed as SF
    prof = SF.profile_of(conn, uid) or {}
    made = time.strftime("%-d %b %Y", time.localtime(float(created))) if created else "?"
    return f"account #{uid}{(' @' + prof['handle']) if prof.get('handle') else ''}, made {made}"


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    from . import accounts as A
    conn = A.connect()
    try:
        init(conn)
        if args[:1] == ["add"] and len(args) > 1:
            bad = 0
            for email in args[1:]:
                ok, said = add(conn, email)
                print(("Owner: " if ok else "Not added: ") + said)
                bad += not ok
            print(f"{len(owner_ids(conn))} account(s) can open the Owner desk now; nobody else can.")
            return 1 if bad else 0
        if args[:1] == ["remove"] and len(args) > 1:
            for email in args[1:]:
                print(remove(conn, email)[1])
            left = owner_ids(conn)
            print(f"{len(left)} account(s) on the list."
                  + ("" if left else " With nobody on it, the verified Qellys_Book account opens the desk again."))
            return 0
        if args[:1] in (["list"], []):
            rows = conn.execute("SELECT u.id, u.email, u.created_at FROM site_owners o JOIN users u "
                                "ON u.id = o.user_id ORDER BY u.id").fetchall()
            if not rows:
                print("Nobody is listed, so the verified Qellys_Book account opens the Owner desk.")
            for uid, email, created in rows:
                print(f"  {email} — {_line(conn, int(uid), created)}")
            return 0
        print("usage: python3 -m engine.siteowners add EMAIL [EMAIL ...] | remove EMAIL | list")
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
