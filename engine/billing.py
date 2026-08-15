"""Subscriptions through Stripe: money we never touch.

Ethan, 2026-08-15: *"we will be accepting money for people to use the
website once it is complete."*

CARD NUMBERS NEVER REACH THIS SERVER, and that is the whole architecture
rather than a nicety. The customer is sent to a Checkout page hosted by
Stripe, types the card there, and comes back with nothing sensitive in
hand. We store a customer id and a subscription status. That is what keeps
this repo out of PCI scope entirely — the moment a card field is rendered
by us, the compliance surface stops being a paragraph and becomes a
project. Do not build a card form.

THE ONLY SOURCE OF TRUTH IS STRIPE, NEVER THE BROWSER. A page returning
from Checkout saying "I paid" is a claim from an untrusted party; anybody
can issue that request with curl. Entitlement moves only when a **signed
webhook** says it does, or when we ask Stripe directly. `success_url` is
for showing a thank-you, and this module deliberately gives it no power to
grant anything.

WHICH MAKES SIGNATURE VERIFICATION THE LOAD-BEARING FUNCTION HERE.
`/api/billing/webhook` is a public endpoint that grants paid access. Without
a verified signature it is a free-subscription button for anyone who finds
the URL. `verify_signature` is pure, and it is the most heavily tested
thing in this file:

  * HMAC-SHA256 over Stripe's exact `{timestamp}.{body}` construction;
  * compared with `hmac.compare_digest`, never `==`;
  * a timestamp older than the tolerance is REJECTED, because a captured
    valid webhook replayed a month later is otherwise still valid;
  * and it takes the RAW BODY. Parsing and re-serializing JSON changes
    bytes — key order, spacing, unicode escapes — and the signature is
    over bytes, so a re-serialized body fails to verify even when honest.

WRITTEN AGAINST AN API THIS CONTAINER CANNOT REACH, like the Yahoo
adapter, and with the same split: everything that can be decided without
the network is pure and unit-tested (signatures, state, request shapes),
and the two calls that must go out are thin. The parts that CANNOT be
verified from here are named in docs/BILLING.md rather than implied to
work.

Standard library only. No `stripe` package — it is a dependency this repo
does not otherwise need, and the two calls are a form POST each.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.stripe.com/v1"

#: Stripe signs `{timestamp}.{raw body}` and sends
#: `t=<unix>,v1=<hex>` in the `Stripe-Signature` header. Five minutes is
#: Stripe's own recommended tolerance.
SIGNATURE_TOLERANCE = 300

#: Statuses that mean "this account has paid and may use paid features".
#: `trialing` counts — a trial is a deliberate grant, not an accident.
#: `past_due` counts UNTIL the period ends: a card that failed to renew
#: is usually an expiry date, not a decision, and locking someone out on
#: the first failed charge is how you turn a payment blip into a refund
#: request.
ENTITLED = ("active", "trialing", "past_due")
#: …and the ones that end it. `incomplete` is a Checkout that was never
#: finished, which is not a subscription at all.
NOT_ENTITLED = ("canceled", "unpaid", "incomplete", "incomplete_expired",
                "paused", "none")

#: Events we act on. Anything else is acknowledged (200) and ignored —
#: Stripe retries anything it does not get a 2xx for, so a 500 on an event
#: we simply do not care about becomes a retry loop.
HANDLED = (
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_failed",
)


class BillingUnavailable(RuntimeError):
    """Stripe is not configured, or would not answer."""


# --- configuration -----------------------------------------------------------
def keys() -> tuple[str, str, str]:
    """``(secret_key, webhook_secret, price_id)`` from secrets.local.

    Raises with the setup steps rather than returning blanks: an empty
    key produces a Stripe error about authentication that says nothing
    about what to go and do.
    """
    from . import secrets as _s
    _s.load_local_secrets()
    sk = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    wh = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    price = os.environ.get("STRIPE_PRICE_ID", "").strip()
    if not sk or not price:
        raise BillingUnavailable(
            "Stripe is not set up yet. In the Stripe dashboard: create a "
            "Product with a recurring Price, then put STRIPE_SECRET_KEY "
            "and STRIPE_PRICE_ID in secrets.local. Add "
            "STRIPE_WEBHOOK_SECRET once the webhook endpoint exists. "
            "docs/BILLING.md has the order to do it in.")
    return sk, wh, price


def configured() -> bool:
    try:
        keys()
        return True
    except BillingUnavailable:
        return False


def live_mode(secret_key: str) -> bool:
    """Whether this key spends real money.

    Worth surfacing on the page. `sk_test_` and `sk_live_` look nearly
    identical in a config file and behave completely differently, and
    "why did nobody get charged" is a bad thing to debug in production.
    """
    return str(secret_key or "").startswith("sk_live_")


# --- the load-bearing function -----------------------------------------------
def parse_signature(header: str) -> tuple[int, list]:
    """``(timestamp, [v1 signatures])`` from a `Stripe-Signature` header.

    A list because Stripe sends more than one v1 during a secret roll,
    and rejecting the second one breaks exactly the operation that exists
    to avoid downtime.
    """
    ts, sigs = 0, []
    for part in str(header or "").split(","):
        k, _, v = part.strip().partition("=")
        if k == "t":
            try:
                ts = int(v)
            except ValueError:
                ts = 0
        elif k == "v1":
            sigs.append(v)
    return ts, sigs


def verify_signature(raw_body: bytes, header: str, secret: str,
                     tolerance: int = SIGNATURE_TOLERANCE,
                     now: float | None = None) -> bool:
    """Whether this webhook really came from Stripe.

    THE FUNCTION THAT STANDS BETWEEN A PUBLIC URL AND FREE SUBSCRIPTIONS.
    Takes the RAW BODY: the signature is over bytes, and JSON that has
    been parsed and re-serialized is different bytes even when it means
    the same thing.
    """
    if not secret or not isinstance(raw_body, (bytes, bytearray)):
        return False
    ts, sigs = parse_signature(header)
    if not ts or not sigs:
        return False
    now = time.time() if now is None else now
    # A REPLAY IS A REAL ATTACK, not a theoretical one: a webhook captured
    # once is otherwise valid forever, so a cancellation event could be
    # replayed to undo an upgrade, or a payment event replayed to extend
    # access. The timestamp is inside the signed payload, so it cannot be
    # edited without breaking the signature.
    if abs(now - ts) > tolerance:
        return False
    signed = f"{ts}.".encode() + bytes(raw_body)
    want = hmac.new(str(secret).encode(), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(want, s) for s in sigs)


# --- what a status means ------------------------------------------------------
def entitled(status: str, period_end: float | None = None,
             now: float | None = None) -> bool:
    """Whether this subscription state grants paid access right now."""
    st = str(status or "none").lower()
    if st in NOT_ENTITLED:
        return False
    if st not in ENTITLED:
        return False
    if st == "past_due":
        # Grace, but not forever: access holds until the period they last
        # paid for actually ends.
        now = time.time() if now is None else now
        return bool(period_end) and float(period_end) > now
    return True


def describe(status: str, period_end: float | None = None) -> str:
    """A sentence for the page. Says what is true, including the awkward
    cases — "past due" with a date is more useful than "inactive"."""
    st = str(status or "none").lower()
    when = ""
    if period_end:
        try:
            when = time.strftime("%-d %b %Y", time.localtime(float(period_end)))
        except (TypeError, ValueError):
            when = ""
    if st == "active":
        return f"Subscribed — renews {when}." if when else "Subscribed."
    if st == "trialing":
        return f"Free trial — ends {when}." if when else "Free trial."
    if st == "past_due":
        return (f"Payment failed. Access continues until {when}; update the "
                f"card to keep it." if when else
                "Payment failed — update the card.")
    if st == "canceled":
        return "Cancelled. Nothing further will be charged."
    if st == "unpaid":
        return "Unpaid — access has stopped."
    return "No subscription."


# --- request shapes (pure, so they can be tested without the network) --------
def _form(pairs: dict) -> bytes:
    return urllib.parse.urlencode(
        {k: v for k, v in pairs.items() if v not in (None, "")}).encode()


def checkout_request(secret_key: str, price_id: str, user_id: int,
                     email: str, success_url: str,
                     cancel_url: str) -> tuple[str, dict, bytes]:
    """``(url, headers, body)`` for a Checkout Session.

    `client_reference_id` is how the webhook finds its way back to a row
    in our own users table. Without it a completed payment arrives with a
    Stripe customer id and no way to say whose it is.
    """
    body = _form({
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(int(user_id)),
        "customer_email": email,
        # Stripe deduplicates on this, so a double-tap on a slow phone
        # does not create two subscriptions for one person.
        "idempotency_key": f"qb-checkout-{int(user_id)}",
    })
    return f"{API}/checkout/sessions", {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }, body


def portal_request(secret_key: str, customer_id: str,
                   return_url: str) -> tuple[str, dict, bytes]:
    """The Stripe-hosted page where someone changes a card or cancels.

    Cancelling is THEIRS to do, on Stripe's own page. Building our own
    cancel flow would mean a company deciding how hard it is to leave,
    and this one is not going to be that.
    """
    body = _form({"customer": customer_id, "return_url": return_url})
    return f"{API}/billing_portal/sessions", {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }, body


def _post(url: str, headers: dict, body: bytes, timeout: int = 20) -> dict:
    """NOTHING FROM `headers` EVER REACHES AN EXCEPTION. The secret key
    lives there, and a key in a traceback is a key in a log file."""
    req = urllib.request.Request(url, data=body, headers=dict(headers),
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            said = json.loads(exc.read().decode("utf-8", "replace"))
            detail = str((said.get("error") or {}).get("message") or "")
        except Exception:                                # noqa: BLE001
            detail = ""
        raise BillingUnavailable(
            f"Stripe refused the request (HTTP {exc.code})."
            f"{' ' + detail if detail else ''}") from exc
    except Exception as exc:                             # noqa: BLE001
        raise BillingUnavailable(f"Could not reach Stripe: {exc}") from exc


def start_checkout(user_id: int, email: str, success_url: str,
                   cancel_url: str) -> str:
    """The Stripe-hosted URL to send the customer to."""
    sk, _wh, price = keys()
    url, headers, body = checkout_request(sk, price, user_id, email,
                                          success_url, cancel_url)
    out = _post(url, headers, body)
    got = out.get("url")
    if not got:
        raise BillingUnavailable("Stripe did not return a Checkout URL.")
    return str(got)


def open_portal(customer_id: str, return_url: str) -> str:
    sk, _wh, _price = keys()
    url, headers, body = portal_request(sk, customer_id, return_url)
    out = _post(url, headers, body)
    got = out.get("url")
    if not got:
        raise BillingUnavailable("Stripe did not return a portal URL.")
    return str(got)


# --- reading an event ---------------------------------------------------------
def read_event(payload: dict) -> dict | None:
    """``{user_id, customer_id, subscription_id, status, period_end}``.

    Returns None for an event we do not act on — which is acknowledged
    with a 200 rather than an error, because Stripe retries anything that
    is not 2xx and a rejected irrelevant event becomes a retry loop.

    `user_id` is only present on the Checkout event; subscription updates
    carry the customer id instead, and the caller matches on that. That
    asymmetry is Stripe's, not ours, and pretending otherwise is how the
    link between a payment and an account gets quietly lost.
    """
    kind = str((payload or {}).get("type") or "")
    if kind not in HANDLED:
        return None
    obj = (((payload or {}).get("data") or {}).get("object") or {})
    out = {"event": kind, "customer_id": None, "subscription_id": None,
           "user_id": None, "status": None, "period_end": None}

    if kind == "checkout.session.completed":
        ref = obj.get("client_reference_id")
        try:
            out["user_id"] = int(ref) if ref is not None else None
        except (TypeError, ValueError):
            out["user_id"] = None
        out["customer_id"] = obj.get("customer")
        out["subscription_id"] = obj.get("subscription")
        # A completed Checkout with a paid invoice is active; Stripe sends
        # the subscription event too, and that one carries the real status.
        out["status"] = ("active" if obj.get("payment_status") == "paid"
                         else "incomplete")
        return out

    if kind == "invoice.payment_failed":
        out["customer_id"] = obj.get("customer")
        out["subscription_id"] = obj.get("subscription")
        out["status"] = "past_due"
        return out

    # customer.subscription.*
    out["customer_id"] = obj.get("customer")
    out["subscription_id"] = obj.get("id")
    out["status"] = ("canceled" if kind.endswith(".deleted")
                     else str(obj.get("status") or "none"))
    end = obj.get("current_period_end")
    try:
        out["period_end"] = float(end) if end is not None else None
    except (TypeError, ValueError):
        out["period_end"] = None
    return out


# --- storage ------------------------------------------------------------------
def init(conn) -> None:
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS subscriptions (
        user_id         INTEGER PRIMARY KEY
                        REFERENCES users(id) ON DELETE CASCADE,
        customer_id     TEXT,
        subscription_id TEXT,
        status          TEXT NOT NULL DEFAULT 'none',
        period_end      REAL,
        updated_at      REAL NOT NULL
      );
      CREATE INDEX IF NOT EXISTS subs_customer
        ON subscriptions(customer_id);
      -- Stripe retries, and a retry must not be a second grant. Seen ids
      -- are remembered so replaying an event is a no-op.
      CREATE TABLE IF NOT EXISTS billing_events (
        event_id TEXT PRIMARY KEY,
        seen_at  REAL NOT NULL
      );
    """)
    conn.commit()


def already_handled(conn, event_id: str) -> bool:
    """True if this exact event has been applied before.

    Stripe delivers at least once, not exactly once. Without this, a
    retried `checkout.session.completed` is a second subscription row and
    a retried cancellation can undo a fresh upgrade.
    """
    if not event_id:
        return False
    row = conn.execute("SELECT 1 FROM billing_events WHERE event_id=?",
                       (str(event_id),)).fetchone()
    if row:
        return True
    conn.execute("INSERT INTO billing_events (event_id, seen_at) VALUES (?,?)",
                 (str(event_id), time.time()))
    conn.execute("DELETE FROM billing_events WHERE seen_at < ?",
                 (time.time() - 60 * 86400,))
    conn.commit()
    return False


def user_for_customer(conn, customer_id: str) -> int | None:
    if not customer_id:
        return None
    row = conn.execute("SELECT user_id FROM subscriptions WHERE customer_id=?",
                       (str(customer_id),)).fetchone()
    return int(row["user_id"]) if row else None


def apply_event(conn, event: dict) -> bool:
    """Move a subscription to what Stripe says it is. True if applied.

    Refuses to guess: an event whose customer we have never seen and
    which carries no `client_reference_id` cannot be attributed to an
    account, and inventing one would attach somebody's payment to the
    wrong person.
    """
    if not event:
        return False
    uid = event.get("user_id")
    if uid is None:
        uid = user_for_customer(conn, event.get("customer_id"))
    if uid is None:
        return False
    conn.execute(
        "INSERT INTO subscriptions (user_id, customer_id, subscription_id, "
        "status, period_end, updated_at) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "  customer_id=COALESCE(excluded.customer_id, customer_id), "
        "  subscription_id=COALESCE(excluded.subscription_id, subscription_id), "
        "  status=excluded.status, "
        "  period_end=COALESCE(excluded.period_end, period_end), "
        "  updated_at=excluded.updated_at",
        (int(uid), event.get("customer_id"), event.get("subscription_id"),
         str(event.get("status") or "none"), event.get("period_end"),
         time.time()))
    conn.commit()
    return True


def status_for(conn, user_id: int) -> dict:
    """What the page shows. Never a promise the database cannot back."""
    row = conn.execute(
        "SELECT customer_id, subscription_id, status, period_end "
        "FROM subscriptions WHERE user_id=?", (int(user_id),)).fetchone()
    if row is None:
        return {"status": "none", "entitled": False,
                "note": describe("none"), "customer_id": None}
    st, end = row["status"], row["period_end"]
    return {"status": st, "period_end": end,
            "entitled": entitled(st, end), "note": describe(st, end),
            "customer_id": row["customer_id"]}
