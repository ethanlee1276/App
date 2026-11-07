"""The owner's account tools: find any account, see where it stands, act on it, and keep a record of every action.

Ethan, 2026-11-02, after a trial that was cancelled on Stripe's page and never
charged: "I know you added features and data for me to see, but I also want
more access and stuff to be able to do to people's accounts". The desk
(engine/ownerdesk) counts and never names a member; this is the one card on it
that does, behind the same door (server `_site_door`: the site's own account
signed in, or the owner token), for support and for keeping the Terms (§7,
§14). The Privacy Policy says so (§2.14).

FIND (`find`): by email, username or account number.

SEE (`card`): the email or phone number, the username, when it joined and was
last seen, how it signs in, how many devices are signed in and how many phones
take its alerts; its membership as the account page shows it (status, plan,
dates, cancelled or not), whether it has had its free trial, its Stripe
customer (a link to it on Stripe's dashboard), codes redeemed, free access we
gave and until when, whether it is suspended, and the actions taken on it.

DO (`act`), each one a line in the record (`owner_actions`):

  * ``grant``    free access for 1 to MAX_GRANT_DAYS days from now — the
                 paywall lets it in until then, like a redeemed code;
  * ``ungrant``  end that free access now;
  * ``signout``  sign it out on every device;
  * ``suspend``  sign it out everywhere, take its phones' alerts, and refuse
                 every way back in (password, reset link, passkey, texted
                 code), saying why; ``unsuspend`` lifts it;
  * ``rename``   reset a username (an offensive one) to ``member<number>``,
                 clearing the display name and the bio;
  * ``delete``   delete the account and everything attached to it, as the
                 member's own Delete does; the account's email is typed to
                 confirm it.

REFUSED WHILE STRIPE CAN STILL CHARGE IT: suspend and delete. Stripe holds
the money; locking a member out (or forgetting them) while their card keeps
being billed is the one outcome these tools must never produce. The refusal
says to cancel the subscription on Stripe first and links the customer there.
A trial or plan already set to cancel is let through: Stripe will not charge
it again. The site's own account can be neither suspended nor deleted from
its own desk.

WHY A WEB ENDPOINT MAY GRANT ACCESS HERE when engine/redeem refuses to mint
codes from one: that rule keeps the PUBLIC from minting access. This door is
the owner's own account (or token); every grant is capped, dated and written
down where the desk shows it, so a grant nobody remembers making is seen.

Standard library only.
"""
from __future__ import annotations

import re
import sqlite3
import time

#: The longest free access one grant gives. A year and a day: a season comp,
#: never "forever" by a typo.
MAX_GRANT_DAYS = 366
#: The record of actions is kept this long, then dropped (Privacy Policy §7).
LOG_KEEP_S = 365 * 86400
#: How many accounts one search lists.
FIND_LIMIT = 20
ACTIONS = ("grant", "ungrant", "signout", "suspend", "unsuspend", "rename", "delete")
STRIPE_CUSTOMER = "https://dashboard.stripe.com/{test}customers/{cid}"
_CUS = re.compile(r"cus_[A-Za-z0-9]{1,190}")


def init(conn) -> None:
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS owner_grants (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        until   REAL NOT NULL,
        at      REAL NOT NULL
      );
      -- The record of what the owner did to which account. Not deleted with
      -- the account (a deletion is one of the things it records); it names
      -- the account by number only, and is dropped after LOG_KEEP_S.
      CREATE TABLE IF NOT EXISTS owner_actions (
        id      INTEGER PRIMARY KEY,
        at      REAL NOT NULL,
        user_id INTEGER NOT NULL,
        action  TEXT NOT NULL,
        detail  TEXT NOT NULL DEFAULT ''
      );
      CREATE INDEX IF NOT EXISTS owner_actions_user ON owner_actions(user_id, at);
    """)
    conn.commit()


def granted(conn, user_id, now: float | None = None) -> float | None:
    """The date the owner's free access runs to, while it runs; else None."""
    if not user_id:
        return None
    try:
        row = conn.execute("SELECT until FROM owner_grants WHERE user_id = ?", (int(user_id),)).fetchone()
    except sqlite3.OperationalError:          # never initialised: no grants
        return None
    t = time.time() if now is None else float(now)
    return float(row[0]) if row and float(row[0]) > t else None


def _day(ts) -> str:
    return time.strftime("%-d %b %Y", time.localtime(float(ts))) if ts else ""


def _note(conn, user_id, action: str, detail: str = "", now: float | None = None) -> None:
    t = time.time() if now is None else float(now)
    conn.execute("INSERT INTO owner_actions (at, user_id, action, detail) VALUES (?,?,?,?)",
                 (t, int(user_id), action, str(detail)[:120]))
    conn.execute("DELETE FROM owner_actions WHERE at < ?", (t - LOG_KEEP_S,))


def _like(q: str) -> str:
    return re.sub(r"([\\%_])", r"\\\1", q)


def find(conn, q, limit: int = FIND_LIMIT) -> list[dict]:
    """Accounts matching an email (any part), a username (its start) or an
    account number (exact), newest first."""
    from . import socialfeed as SF
    SF.ensure_tables(conn)
    q = str(q or "").strip().lstrip("@")[:80]
    if len(q) < 2 and not q.isdigit():
        return []
    sql = ("SELECT u.id, u.email, u.created_at, u.last_seen, u.suspended_at, p.handle FROM users u "
           "LEFT JOIN feed_profiles p ON p.user_id = u.id WHERE ")
    if q.isdigit():
        rows = conn.execute(sql + "u.id = ? OR u.phone LIKE ? ESCAPE '\\' ORDER BY u.id DESC LIMIT ?",
                            (int(q), f"%{_like(q)}%", int(limit))).fetchall()
    else:
        rows = conn.execute(sql + "u.email LIKE ? ESCAPE '\\' OR p.handle LIKE ? ESCAPE '\\' "
                            "ORDER BY u.id DESC LIMIT ?",
                            (f"%{_like(q.lower())}%", f"{_like(q)}%", int(limit))).fetchall()
    return [_row(conn, r) for r in rows]


#: The desk's list of every account (`listed`): newest first, this many at most.
LIST_LIMIT = 500


def listed(conn, limit: int = LIST_LIMIT) -> list[dict]:
    """Every account by its NUMBER alone, newest first: when it joined, when
    it was last here and where its membership stands. Never its email, phone
    number or username.

    Ethan, 2026-11-05, the desk's Accounts card circled: "I should have a list
    of all accounts on the website in this section". The Privacy Policy
    (§2.14) tells members the owner looks an account up one at a time, so
    who an account is shows only when the owner opens it (`card`), the
    look-up it describes; the list says how the accounts are doing."""
    from . import billing as BI
    rows = conn.execute("SELECT id, created_at, last_seen, suspended_at FROM users "
                        "ORDER BY created_at DESC, id DESC LIMIT ?", (int(limit),)).fetchall()
    out = []
    for r in rows:
        try:
            st = BI.status_for(conn, int(r["id"]))
        except Exception:                                    # noqa: BLE001 — a row still lists
            st = {}
        out.append({"id": int(r["id"]), "joined": r["created_at"], "seen": r["last_seen"],
                    "suspended": bool(r["suspended_at"]), "status": st.get("status") or "none",
                    "entitled": bool(st.get("entitled"))})
    return out


def _row(conn, r) -> dict:
    from . import billing as BI
    st = {}
    try:
        st = BI.status_for(conn, int(r["id"]))
    except Exception:                                        # noqa: BLE001 — a row still lists
        st = {}
    return {"id": int(r["id"]), "who": _who(r["email"]), "handle": r["handle"] or "",
            "joined": r["created_at"], "seen": r["last_seen"], "suspended": bool(r["suspended_at"]),
            "status": st.get("status") or "none", "entitled": bool(st.get("entitled"))}


def _who(email) -> str:
    """The account's address, or its phone number for a phone account."""
    from . import smsverify as SV
    e = str(email or "")
    if SV.is_placeholder(e):
        digits = e.split("@", 1)[0]
        return SV.say("+" + digits) if digits.isdigit() else "phone account"
    return e


def charges(st: dict) -> bool:
    """Can Stripe still charge this account? The server's own rule for a
    member's Delete (`_live_subscription`): open there and not set to cancel."""
    return bool((st.get("entitled") or st.get("open")) and not st.get("cancel_at_end"))


def _stripe_link(cid) -> str:
    from . import billing as BI
    if not cid or not _CUS.fullmatch(str(cid)):
        return ""
    test = ""
    try:
        test = "" if BI.live_mode(BI.keys()[0]) else "test/"
    except Exception:                                        # noqa: BLE001 — unconfigured: assume live
        test = ""
    return STRIPE_CUSTOMER.format(test=test, cid=cid)


def card(conn, user_id, now: float | None = None) -> dict | None:
    """Everything the desk shows about one account; None for no such account."""
    from . import billing as BI
    from . import socialfeed as SF
    init(conn)
    BI.init(conn)
    SF.ensure_tables(conn)
    t = time.time() if now is None else float(now)
    u = conn.execute("SELECT id, email, created_at, last_seen, phone, suspended_at FROM users WHERE id = ?",
                     (int(user_id),)).fetchone()
    if not u:
        return None
    uid = int(u["id"])
    prof = SF.profile_of(conn, uid) or {}
    one = lambda q, *a: (conn.execute(q, a).fetchone() or [0])[0] or 0   # noqa: E731
    keys = 0
    try:
        keys = one("SELECT COUNT(*) FROM passkeys WHERE user_id = ?", uid)
    except sqlite3.OperationalError:
        keys = 0
    phones = 0
    try:
        phones = one("SELECT COUNT(*) FROM push_subs WHERE user_id = ?", uid)
    except sqlite3.OperationalError:
        phones = 0
    ways = (["phone"] if u["phone"] else []) + (["password"] if not u["phone"] else []) + \
        ([f"{keys} passkey{'s' if keys != 1 else ''}"] if keys else [])
    st = BI.status_for(conn, uid)
    sub = conn.execute("SELECT customer_id, started_at FROM subscriptions WHERE user_id = ?", (uid,)).fetchone()
    from . import redeem as RD
    from . import gate
    from . import siteowners as SO
    from . import whoson as W
    try:
        RD.init(conn)
        codes = RD.describe(conn, uid, now=t)
    except Exception:                                        # noqa: BLE001
        codes = {"active": False, "granted_to": None, "codes": []}
    grant = granted(conn, uid, t)
    log = [{"at": r[0], "action": r[1], "detail": r[2]} for r in conn.execute(
        "SELECT at, action, detail FROM owner_actions WHERE user_id = ? ORDER BY at DESC, id DESC LIMIT 10", (uid,))]
    return {
        "id": uid, "who": _who(u["email"]), "phone_account": bool(u["phone"]),
        "handle": prof.get("handle") or "", "name": prof.get("name") or "", "verified": bool(prof.get("verified")),
        "joined": u["created_at"], "seen": u["last_seen"], "ways": ways,
        "sessions": one("SELECT COUNT(*) FROM sessions WHERE user_id = ? AND expires_at > ?", uid, t),
        "phones": phones,
        "membership": {"status": st.get("status") or "none", "note": st.get("note") or "",
                       "entitled": bool(st.get("entitled")), "plan": st.get("plan"),
                       "plan_name": st.get("plan_name"),
                       "period_end": st.get("period_end"), "cancel_at_end": bool(st.get("cancel_at_end")),
                       "started": sub["started_at"] if sub else None,
                       "trial_used": BI.has_subscribed_before(conn, uid),
                       "charges": charges(st)},
        "stripe": _stripe_link(sub["customer_id"] if sub else None),
        "codes": codes, "comped": gate.comped(u["email"]),
        "grant": grant, "suspended": u["suspended_at"],
        "site_account": W.is_site_account(conn, uid) or uid in SO.owner_ids(conn),
        "log": log,
    }


def act(conn, user_id, action: str, args: dict | None = None, now: float | None = None) -> tuple[int, dict]:
    """Do one thing to one account. ``(status, body)``; the body carries the
    account's card as it now stands (or ``deleted``), or the refusal."""
    from . import accounts as A
    from . import billing as BI
    init(conn)
    BI.init(conn)
    args = args if isinstance(args, dict) else {}
    t = time.time() if now is None else float(now)
    action = str(action or "")
    if action not in ACTIONS:
        return 400, {"error": "That is not something the desk can do."}
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return 400, {"error": "Which account?"}
    u = conn.execute("SELECT id, email, phone, suspended_at FROM users WHERE id = ?", (uid,)).fetchone()
    if not u:
        return 404, {"error": "No such account."}
    from . import whoson as W
    from . import siteowners as SO
    if action in ("suspend", "delete") and (W.is_site_account(conn, uid) or uid in SO.owner_ids(conn)):
        return 409, {"error": "That is one of the site’s own accounts — it cannot be suspended or deleted from the desk."}
    st = BI.status_for(conn, uid)
    if action in ("suspend", "delete") and charges(st):
        sub = conn.execute("SELECT customer_id FROM subscriptions WHERE user_id = ?", (uid,)).fetchone()
        return 409, {"error": "Stripe can still charge this account. Cancel its subscription on Stripe first "
                              "(the customer is linked here), then come back: otherwise the card keeps being "
                              "billed for an account that cannot get in.",
                     "stripe": _stripe_link(sub["customer_id"] if sub else None)}
    if action == "grant":
        try:
            days = int(args.get("days"))
        except (TypeError, ValueError):
            days = 0
        if not 1 <= days <= MAX_GRANT_DAYS:
            return 400, {"error": f"Free access is 1 to {MAX_GRANT_DAYS} days."}
        until = t + days * 86400
        conn.execute("INSERT INTO owner_grants (user_id, until, at) VALUES (?,?,?) "
                     "ON CONFLICT(user_id) DO UPDATE SET until = excluded.until, at = excluded.at", (uid, until, t))
        _note(conn, uid, "grant", f"{days} day{'s' if days != 1 else ''}, to {_day(until)}", t)
    elif action == "ungrant":
        if not granted(conn, uid, t):
            return 409, {"error": "This account has no free access from the desk to end."}
        conn.execute("DELETE FROM owner_grants WHERE user_id = ?", (uid,))
        _note(conn, uid, "ungrant", "", t)
    elif action == "signout":
        n = A.end_all_sessions(conn, uid)
        _note(conn, uid, "signout", f"{n} device{'s' if n != 1 else ''}", t)
    elif action == "suspend":
        if u["suspended_at"]:
            return 409, {"error": "This account is already suspended."}
        conn.execute("UPDATE users SET suspended_at = ? WHERE id = ?", (t, uid))
        n = A.end_all_sessions(conn, uid)
        try:                    # its phones keep the site's public alerts, as a signed-out phone does
            conn.execute("UPDATE push_subs SET user_id = NULL WHERE user_id = ?", (uid,))
        except sqlite3.OperationalError:
            pass
        _note(conn, uid, "suspend", f"signed out of {n} device{'s' if n != 1 else ''}", t)
    elif action == "unsuspend":
        if not u["suspended_at"]:
            return 409, {"error": "This account is not suspended."}
        conn.execute("UPDATE users SET suspended_at = NULL WHERE id = ?", (uid,))
        _note(conn, uid, "unsuspend", "", t)
    elif action == "rename":
        from . import socialfeed as SF
        prof = SF.profile_of(conn, uid)
        if not prof:
            return 409, {"error": "This account has no username to reset."}
        new = f"member{uid}"
        if prof["handle"].lower() == new.lower() and not prof.get("name"):
            return 409, {"error": "Its username is already the plain one."}
        code, out = SF.profile_set(conn, uid, new, "", name="", _owner=True)
        if code != 200:
            return code, out
        _note(conn, uid, "rename", f"@{prof['handle']} to @{new}", t)
    elif action == "delete":
        typed = str(args.get("confirm") or "").strip().lower()
        digits = re.sub(r"\D", "", typed)
        by_phone = bool(u["phone"]) and len(digits) >= 7 and digits == re.sub(r"\D", "", str(u["phone"]))
        if not typed or (typed != str(u["email"] or "").strip().lower() and not by_phone):
            return 400, {"error": "Type the account’s email (or, for a phone account, its number) exactly to delete it."}
        A.delete_user(conn, uid)
        _note(conn, uid, "delete", "", t)
        conn.commit()
        return 200, {"deleted": True, "id": uid}
    conn.commit()
    return 200, {"done": action, "card": card(conn, uid, t)}


def recent(conn, limit: int = 15) -> list[dict]:
    """The desk's record of actions, newest first, each with the account's
    username or address while it still exists."""
    from . import socialfeed as SF
    init(conn)
    SF.ensure_tables(conn)
    rows = conn.execute(
        "SELECT a.at, a.user_id, a.action, a.detail, u.email, p.handle FROM owner_actions a "
        "LEFT JOIN users u ON u.id = a.user_id LEFT JOIN feed_profiles p ON p.user_id = a.user_id "
        "ORDER BY a.at DESC, a.id DESC LIMIT ?", (int(limit),)).fetchall()
    return [{"at": r[0], "id": int(r[1]), "action": r[2], "detail": r[3],
             "who": ("@" + r[5]) if r[5] else (_who(r[4]) if r[4] else ""), "gone": r[4] is None}
            for r in rows]
