"""Referral codes: a member's code, a friend's first payment, a credit each.

Ethan, 2026-10-25: *"users, when they have a paid account, they should be
given a referral code that they can use to give to other users for when
they sign up, and it'll give both users a discount per month. So let's say
a user that refers someone else, the new user would get 25% off 1 month,
and then the person that referred them would get 25% off their next
month."*

WHAT "25% OFF A MONTH" IS, IN MONEY. A month is the $25 plan, so a quarter
of it is $6.25 — and both halves are paid as that amount, never as a
percentage. The three plans share one Stripe Product (engine/billing's
PROMOS comment), so a 25%-off coupon on the yearly cart is 25% off $225:
$56.25 handed out for a referral meant to cost $6.25, and nothing would
fail. As an amount it is the same quarter-month on every plan.

  * THE NEW MEMBER: $6.25 off their first payment, a Stripe coupon on the
    Checkout their account opens (billing.checkout_request `coupon`). Only
    for an account that has never subscribed, and only once.
  * THE MEMBER WHO SHARED THE CODE: $6.25 on their Stripe balance once the
    friend's first payment clears, which Stripe takes off their next
    invoice by itself. Several friends stack; nothing is lost if a credit
    is bigger than one bill — it carries to the next.

WHO GETS A CODE. A member — Ethan's words, "when they have a paid
account". A free account can type somebody's code at sign-up; it has none
of its own to hand out.

WHAT IT REFUSES, and why each:
  * Its own code. The obvious one.
  * A second code on the same account, or a code after the account has
    ever subscribed. One referral per account, attached before the first
    purchase — otherwise a lapsed member re-buys with a friend's code.
  * A code it does not know, answered the same way as a malformed one.
What it cannot refuse is one person with two email addresses. Nothing can
without keeping something about a card, and the Privacy Policy says
nothing is kept. It does not pay: the second account has to pay $18.75 to
earn its owner $6.25.

THE CREDIT IS IDEMPOTENT TWICE. The row records it, and the Stripe call
carries an Idempotency-Key per referred account — so a retried webhook, or
a sweep racing a webhook, cannot pay the same friend twice.

    python3 tests/test_referrals.py
"""

from __future__ import annotations

import re
import secrets
import time

#: No 0/O, 1/I/L: a code is read off one phone and typed into another.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LEN = 7
#: What a typed code may look like at all (the client keeps the same rule).
CODE_RE = re.compile(r"^[A-Z0-9]{4,16}$")
#: A quarter of the $25 month, for each side.
NEW_MEMBER_OFF_CENTS = 625
REFERRER_CREDIT_CENTS = 625
#: The Stripe coupon the new member's Checkout carries. Fixed so that it
#: is made once and found again (billing.ensure_referral_coupon).
COUPON_ID = "qb-referral-first-payment"


def init(conn) -> None:
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS referral_codes (
        user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        code       TEXT NOT NULL UNIQUE,
        created_at REAL NOT NULL
      );
      -- One row per referred account: who sent them, and how far it got.
      CREATE TABLE IF NOT EXISTS referrals (
        referred_id  INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        referrer_id  INTEGER NOT NULL,
        code         TEXT NOT NULL,
        attached_at  REAL NOT NULL,
        discount_at  REAL,
        paid_at      REAL,
        credited_at  REAL,
        credit_ref   TEXT
      );
      CREATE INDEX IF NOT EXISTS referrals_by_referrer ON referrals(referrer_id);
    """)
    conn.commit()


def normalize(code) -> str:
    return re.sub(r"[\s-]+", "", str(code or "")).upper()


def _mint() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))


def code_for(conn, user_id: int, member: bool) -> str | None:
    """This account's code, minted on first ask — for a member only. A
    code once minted stays the account's after a lapse: it is printed on
    links already sent, and a friend arriving on one still gets their
    discount; the credit simply waits until its owner is paying again."""
    init(conn)
    row = conn.execute("SELECT code FROM referral_codes WHERE user_id=?", (int(user_id),)).fetchone()
    if row:
        return row[0]
    if not member:
        return None
    for _ in range(8):
        code = _mint()
        try:
            conn.execute("INSERT INTO referral_codes (user_id, code, created_at) VALUES (?,?,?)",
                         (int(user_id), code, time.time()))
            conn.commit()
            return code
        except Exception:                                    # noqa: BLE001  (a collision: draw again)
            conn.rollback()
    return None


def owner_of(conn, code) -> int | None:
    init(conn)
    c = normalize(code)
    if not CODE_RE.match(c):
        return None
    row = conn.execute("SELECT user_id FROM referral_codes WHERE code=?", (c,)).fetchone()
    return int(row[0]) if row else None


def attach(conn, user_id: int, code, subscribed_before: bool = False) -> tuple[bool, str]:
    """Tie a new account to the code it came in on. ``(ok, why)``.

    Never raises and never blocks a sign-up: a code that does not take is
    a sentence on the page, not a failed account."""
    init(conn)
    c = normalize(code)
    if not c:
        return False, "no code"
    owner = owner_of(conn, c)
    if owner is None:
        return False, "That referral code isn’t one we know."
    if owner == int(user_id):
        return False, "That’s your own code — it’s for your friends."
    if subscribed_before:
        return False, "Referral codes are for an account’s first membership."
    if conn.execute("SELECT 1 FROM referrals WHERE referred_id=?", (int(user_id),)).fetchone():
        return False, "This account already has a referral code."
    conn.execute("INSERT INTO referrals (referred_id, referrer_id, code, attached_at) VALUES (?,?,?,?)",
                 (int(user_id), owner, c, time.time()))
    conn.commit()
    return True, "Code added: $6.25 off your first payment."


def discount_for(conn, user_id: int, subscribed_before: bool) -> str:
    """The coupon id this account's Checkout carries, or "". Only before
    its first membership and only while unused."""
    init(conn)
    if subscribed_before:
        return ""
    row = conn.execute("SELECT discount_at FROM referrals WHERE referred_id=?", (int(user_id),)).fetchone()
    return COUPON_ID if row and row[0] is None else ""


def discount_taken(conn, user_id: int) -> None:
    """Called when the Checkout that carried the coupon completes."""
    init(conn)
    conn.execute("UPDATE referrals SET discount_at=COALESCE(discount_at, ?) WHERE referred_id=?",
                 (time.time(), int(user_id)))
    conn.commit()


def first_payment(conn, user_id: int) -> int | None:
    """A referred account's membership went active: its referrer is owed a
    credit. Returns the referrer's id when one became owed just now."""
    init(conn)
    cur = conn.execute("UPDATE referrals SET paid_at=? WHERE referred_id=? AND paid_at IS NULL",
                       (time.time(), int(user_id)))
    conn.commit()
    if not cur.rowcount:
        return None
    row = conn.execute("SELECT referrer_id FROM referrals WHERE referred_id=?", (int(user_id),)).fetchone()
    return int(row[0]) if row else None


def owed(conn, referrer_id: int | None = None) -> list[tuple[int, int]]:
    """``[(referred_id, referrer_id)]`` paid for and not yet credited."""
    init(conn)
    q = "SELECT referred_id, referrer_id FROM referrals WHERE paid_at IS NOT NULL AND credited_at IS NULL"
    args: tuple = ()
    if referrer_id is not None:
        q += " AND referrer_id=?"
        args = (int(referrer_id),)
    return [(int(a), int(b)) for a, b in conn.execute(q, args).fetchall()]


def settle(conn, customer_of, credit) -> int:
    """Pay every owed credit whose referrer has a Stripe customer. Returns
    how many were paid. `customer_of(user_id) -> customer id or None` and
    `credit(customer_id, cents, key, note) -> transaction id` are passed in,
    so this module moves no money itself and the test needs no Stripe.

    One failure stops nothing else: that row stays owed for the next pass."""
    paid = 0
    for referred, referrer in owed(conn):
        cus = customer_of(referrer)
        if not cus:
            continue                           # not paying right now: it waits
        try:
            ref = credit(cus, REFERRER_CREDIT_CENTS, f"qb-referral-credit-{referred}",
                         "Referral credit — a friend joined with your code")
        except Exception:                                    # noqa: BLE001
            continue
        conn.execute("UPDATE referrals SET credited_at=?, credit_ref=? WHERE referred_id=? AND credited_at IS NULL",
                     (time.time(), str(ref or ""), referred))
        conn.commit()
        paid += 1
    return paid


def summary(conn, user_id: int, member: bool) -> dict:
    """What the account page shows: the code, and how it has done."""
    init(conn)
    code = code_for(conn, user_id, member)
    rows = conn.execute("SELECT paid_at, credited_at FROM referrals WHERE referrer_id=?",
                        (int(user_id),)).fetchall()
    mine = conn.execute("SELECT code, discount_at FROM referrals WHERE referred_id=?",
                        (int(user_id),)).fetchone()
    return {
        "code": code,
        "joined": len(rows),
        "paid": sum(1 for p, _ in rows if p),
        "credited_cents": REFERRER_CREDIT_CENTS * sum(1 for _, c in rows if c),
        "waiting_cents": REFERRER_CREDIT_CENTS * sum(1 for p, c in rows if p and not c),
        "each_cents": REFERRER_CREDIT_CENTS,
        # The code THIS account came in on, while its discount is unused.
        "used_code": (mine[0] if mine and mine[1] is None else ""),
    }
