"""Gift a month: a member buys a month for a friend, delivered as a code.

From the ideas list (docs/IDEAS.md, the way in and the way up, ninth):
"Buy a month for a friend, delivered as a code (engine/redeem already
grants one)."

ONLY A PAYMENT MAKES A GIFT. engine/redeem's rule holds here: nothing a
request can reach may mint access. A gift code is made by exactly two
things, both of them Stripe's word that a gift was paid for:

  * the signed webhook, `checkout.session.completed` for a Checkout this
    module opened (`metadata[kind]=gift`, `mode=payment`, paid) — the same
    door that grants a subscription (`from_webhook`);
  * the buyer's own return trip from Checkout, which carries the session
    id and makes us ASK Stripe, as billing.reconcile_session does for a
    subscription: Stripe must say paid, and the session must be this
    buyer's (`confirm`).

Either way one session is one code (`mint` is keyed on the session), and
a gift never touches the buyer's own plan: the server answers the gift's
webhook before the subscription code ever reads it.

REDEEMED like any code, in the Redeem a code box: one month of full access
from that day, once, and the code is spent. It is written to
code_redemptions, so it entitles exactly as a redeemed code does
(redeem.active). Wrong guesses count against redeem's hourly allowance;
eight characters from a 32-letter alphabet are not guessable inside it.

KEPT (gift_codes): the code, who bought it and when, the Checkout session
it was paid in, and who redeemed it and when. Named in the Privacy
Policy; deleting an account takes the person off both sides (the gift
stays bought, and stays spent).

OFF until STRIPE_PRICE_GIFT names a one-time price in Stripe (runbook FZ).
Standard library only.
"""
from __future__ import annotations

import re
import secrets
import time

ENV_GIFT_PRICE = "STRIPE_PRICE_GIFT"
#: What a gift is: one month, at the monthly plan's price.
GIFT_MONTHS = 1
GIFT_CENTS = 2500
#: No I, O, 0 or 1: a code is read off a phone and typed into another.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_RE = re.compile(r"^GIFT-[A-Z2-9]{4}-[A-Z2-9]{4}$")


def ensure_tables(conn) -> None:
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS gift_codes (
        code        TEXT PRIMARY KEY,
        user_id     INTEGER NOT NULL,
        session_id  TEXT NOT NULL UNIQUE,
        created_at  REAL NOT NULL,
        redeemed_by INTEGER,
        redeemed_at REAL
      );
      CREATE INDEX IF NOT EXISTS gift_codes_buyer ON gift_codes (user_id);
    """)
    conn.commit()


def price() -> str:
    import os
    from . import secrets as _s
    _s.load_local_secrets()
    return os.environ.get(ENV_GIFT_PRICE, "").strip()


def enabled() -> bool:
    """A gift can be bought: Stripe is set up and a gift price is named."""
    from . import billing as BI
    return bool(price()) and BI.configured()


def looks_like(code) -> bool:
    return str(code or "").strip().upper().startswith("GIFT-")


def _new_code() -> str:
    pick = lambda: "".join(secrets.choice(ALPHABET) for _ in range(4))  # noqa: E731
    return f"GIFT-{pick()}-{pick()}"


def mint(conn, buyer_id: int, session_id: str, now: float | None = None) -> str:
    """The code for this paid session: made once, the same code ever after."""
    ensure_tables(conn)
    now = time.time() if now is None else now
    row = conn.execute("SELECT code FROM gift_codes WHERE session_id=?", (str(session_id),)).fetchone()
    if row:
        return str(row[0])
    for _ in range(8):
        code = _new_code()
        cur = conn.execute("INSERT OR IGNORE INTO gift_codes (code, user_id, session_id, created_at) "
                           "VALUES (?,?,?,?)", (code, int(buyer_id), str(session_id), now))
        if cur.rowcount:
            conn.commit()
            return code
        row = conn.execute("SELECT code FROM gift_codes WHERE session_id=?", (str(session_id),)).fetchone()
        if row:                       # a second writer minted it first
            return str(row[0])
    raise RuntimeError("no free gift code after eight draws")


def is_gift(payload: dict) -> bool:
    """A Checkout this module opened, finished: the webhook's gift."""
    obj = (((payload or {}).get("data") or {}).get("object") or {})
    return (str((payload or {}).get("type") or "") == "checkout.session.completed"
            and str((obj.get("metadata") or {}).get("kind") or "") == "gift")


def _paid_gift(sess: dict) -> int | None:
    """The buyer's account id when this session is a paid gift, else None."""
    if str((sess.get("metadata") or {}).get("kind") or "") != "gift" or str(sess.get("mode") or "") != "payment":
        return None
    if str(sess.get("payment_status") or "") != "paid":
        return None
    try:
        return int(sess.get("client_reference_id"))
    except (TypeError, ValueError):
        return None


def from_webhook(conn, payload: dict, now: float | None = None) -> str | None:
    """Mint the code a paid gift's (signed, already verified) webhook names."""
    sess = (((payload or {}).get("data") or {}).get("object") or {})
    buyer = _paid_gift(sess)
    if buyer is None or not sess.get("id"):
        return None
    return mint(conn, buyer, str(sess["id"]), now)


def confirm(conn, buyer_id: int, session_id: str, fetch=None, now: float | None = None) -> str | None:
    """The return trip: ask Stripe about this session and mint its code
    when it is a paid gift of THIS buyer's. ``fetch(session_id)`` stands in
    for Stripe in a test."""
    from . import billing as BI
    sid = str(session_id or "").strip()
    if not BI._SESSION_ID.fullmatch(sid):
        return None
    sess = (fetch or (lambda s: BI._get(f"{BI.API}/checkout/sessions/{s}", BI.keys()[0], timeout=10)))(sid) or {}
    if sess.get("id") != sid or _paid_gift(sess) != int(buyer_id):
        return None
    return mint(conn, int(buyer_id), sid, now)


def mine(conn, buyer_id: int) -> list:
    """The gifts this account bought, newest first: the code, and whether it is spent."""
    ensure_tables(conn)
    return [{"code": r[0], "made": r[1], "redeemed": r[2] is not None}
            for r in conn.execute("SELECT code, created_at, redeemed_by FROM gift_codes WHERE user_id=? "
                                  "ORDER BY created_at DESC", (int(buyer_id),))]


def redeem(conn, user_id: int, code: str, now: float | None = None) -> dict:
    """A month of full access from now, once; the code is spent. Raises
    redeem.RedeemError with the same sentences, and the same allowance for
    wrong guesses, as any other code."""
    from . import redeem as RD
    now = time.time() if now is None else now
    RD.init(conn)
    ensure_tables(conn)
    code = RD.normalize(code)
    if RD._recent_attempts(conn, user_id, now) >= RD.MAX_ATTEMPTS:
        raise RD.RedeemError("Too many attempts. Try again in an hour.")
    row = conn.execute("SELECT redeemed_by FROM gift_codes WHERE code=?", (code,)).fetchone() \
        if CODE_RE.match(code) else None
    if row is not None and row[0] == int(user_id):
        raise RD.RedeemError("You have already used this code.")
    if row is None or row[0] is not None:
        RD._note_attempt(conn, user_id, now)
        conn.commit()
        raise RD.RedeemError("That code is not valid.")
    cur = conn.execute("UPDATE gift_codes SET redeemed_by=?, redeemed_at=? WHERE code=? AND redeemed_by IS NULL",
                       (int(user_id), now, code))
    if cur.rowcount != 1:            # another account spent it a moment ago
        conn.commit()
        raise RD.RedeemError("That code is not valid.")
    until = now + GIFT_MONTHS * RD.MONTH_S
    conn.execute("INSERT OR REPLACE INTO code_redemptions(code, user_id, months, granted_to, created_at) "
                 "VALUES(?, ?, ?, ?, ?)", (code, int(user_id), GIFT_MONTHS, until, now))
    conn.commit()
    return {"code": code, "months": GIFT_MONTHS, "granted_to": until}


def checkout_request(secret_key: str, price_id: str, user_id: int, email: str, success_url: str,
                     cancel_url: str, now: float | None = None) -> tuple[str, dict, bytes]:
    """Stripe Checkout for one gift: a one-time payment, marked as a gift so
    its webhook mints a code and grants the buyer nothing."""
    from . import billing as BI
    body = BI._form({"mode": "payment", "line_items[0][price]": price_id, "line_items[0][quantity]": "1",
                     "client_reference_id": str(int(user_id)), "customer_email": email or None,
                     "metadata[kind]": "gift", "payment_intent_data[metadata][kind]": "gift",
                     "success_url": success_url, "cancel_url": cancel_url})
    return f"{BI.API}/checkout/sessions", {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Idempotency-Key": BI.idempotency_key(user_id, "gift", now),
    }, body


def start_checkout(user_id: int, email: str, success_url: str, cancel_url: str, post=None) -> str:
    """The address of Stripe's Checkout page for one gift."""
    from . import billing as BI
    if not price():
        raise BI.BillingUnavailable("Gifts aren't switched on yet.")
    url, headers, body = checkout_request(BI.keys()[0], price(), user_id, email, success_url, cancel_url)
    out = (post or BI._post)(url, headers, body)
    if not out.get("url"):
        raise BI.BillingUnavailable("Stripe did not return a checkout page.")
    return str(out["url"])
