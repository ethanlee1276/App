"""Paddle as the payment processor, after Stripe refused the category.

Ethan, 2026-08-15: *"no we cant use stripe so we gotta find a different
alternative … if u think Paddle then lets do paddel."*

WHY PADDLE AND NOT A HIGH-RISK MERCHANT ACCOUNT. Paddle is a merchant of
record: they are the legal seller, they take the payment, they handle
sales tax and VAT, and they pay us out. Two consequences that matter more
than the rate card:

  * the risk assessment is theirs, not ours. Stripe declined on the
    CATEGORY — a paid sports-betting tool — rather than on anything we
    do, and a broker like PaymentCloud or PayKings would price us as a
    gambling merchant at 4-6% with a rolling reserve for selling what is
    factually a software subscription;
  * digital-goods sales tax across fifty states stops being our problem
    at exactly the revenue level where it would otherwise become one.

The cost is roughly 5% + 50c against Stripe's 2.9% + 30c. That is about
two points for someone else to own risk and tax compliance, which at zero
subscribers is a good trade.

WHAT THIS MODULE IS, AND IS NOT
-------------------------------
It is the PROVIDER half only. Everything that decides what a payment
MEANS lives in `engine/billing.py` and is reused unchanged:

    entitled()       which statuses grant access, and the paid-through date
    apply_event()    writing a normalised event to `subscriptions`
    already_handled() the replay guard, because retries are not grants
    status_for()     what the account card reads
    init()           the schema

`read_event` below returns the SAME dict shape billing.read_event does —
``{event, user_id, customer_id, subscription_id, status, period_end}`` —
so the storage layer cannot tell which processor it came from. That was
the point of keeping the two halves apart: switching processors is this
file, not the billing logic and not the database.

⚠️  THE SIGNATURE SCHEME BELOW IS WRITTEN FROM MEMORY AND IS NOT VERIFIED.
The dev container's egress policy blocks developer.paddle.com and
api.paddle.com, so it could not be checked against their documentation or
against a real webhook. `verify_signature` is the single place where
being wrong is silent AND dangerous — a verifier that accepts everything
looks identical to one that works, right up until somebody forges a
subscription. **Before this goes live**: send a real test webhook from
the Paddle dashboard and confirm this function accepts it and rejects the
same body with one byte changed. `tests/test_paddle.py` proves the HMAC
construction is self-consistent; only a real payload proves it is Paddle's.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Live and sandbox. Sandbox is a separate account with separate keys, and
#: the whole point of it is that a mistake there costs nothing.
API = "https://api.paddle.com"
SANDBOX_API = "https://sandbox-api.paddle.com"

#: Paddle's subscription statuses. The mapping is deliberately conservative
#: and mirrors the argument already made in billing.ENTITLED: `past_due`
#: keeps access until the paid period ends, because a failed renewal is
#: usually an expiry date rather than a decision, and cutting someone off
#: on the first failed charge turns a payment blip into a refund request.
#:
#: `paused` is Paddle-specific and has no Stripe equivalent. It means the
#: customer deliberately suspended billing, so access stops — but it is
#: NOT `canceled`, and treating it as such would delete a subscription
#: they intend to resume.
STATUS_MAP = {
    "active": "active",
    "trialing": "trialing",
    "past_due": "past_due",
    "paused": "paused",
    "canceled": "canceled",
}

#: Events we act on. Anything else is acknowledged with a 200 and ignored:
#: Paddle retries any non-2xx, so rejecting an irrelevant event turns it
#: into a retry loop that we then have to explain to ourselves at 3am.
HANDLED = (
    "subscription.created",
    "subscription.updated",
    "subscription.activated",
    "subscription.canceled",
    "subscription.paused",
    "subscription.resumed",
    "transaction.completed",
)

#: Paddle signs with a notification secret, NOT the API key. They are
#: different strings with different lifetimes and only one of them belongs
#: in a signature check.
ENV_API_KEY = "PADDLE_API_KEY"
ENV_WEBHOOK_SECRET = "PADDLE_NOTIFICATION_SECRET"
ENV_PRICE_ID = "PADDLE_PRICE_ID"
ENV_SANDBOX = "PADDLE_SANDBOX"


def keys() -> tuple[str, str, str]:
    """(api_key, notification_secret, price_id) from the environment.

    Same contract as billing.keys(): read at call time, never cached, and
    never logged. A key that is printed once is a key that is in a
    terminal scrollback forever.
    """
    return (os.environ.get(ENV_API_KEY, "").strip(),
            os.environ.get(ENV_WEBHOOK_SECRET, "").strip(),
            os.environ.get(ENV_PRICE_ID, "").strip())


def configured() -> bool:
    api_key, secret, price = keys()
    return bool(api_key and secret and price)


def sandbox() -> bool:
    return os.environ.get(ENV_SANDBOX, "").strip().lower() in ("1", "true", "yes")


def api_base() -> str:
    return SANDBOX_API if sandbox() else API


def parse_signature(header: str) -> tuple[int, list[str]]:
    """``ts=1710000000;h1=abc…`` → ``(1710000000, ["abc…"])``.

    Tolerant of ordering and of extra fields, because a parser that
    depends on field order breaks the first time the sender adds one.
    Returns ``(0, [])`` for anything it cannot read, and the caller
    treats that as a failed verification rather than as an exception —
    a malformed header is a rejected webhook, not a 500.
    """
    ts = 0
    hashes: list[str] = []
    for part in str(header or "").split(";"):
        key, _, value = part.partition("=")
        key, value = key.strip(), value.strip()
        if key == "ts":
            try:
                ts = int(value)
            except (TypeError, ValueError):
                return 0, []
        elif key == "h1" and value:
            hashes.append(value)
    return ts, hashes


def verify_signature(raw_body: bytes, header: str, secret: str,
                     tolerance: int = 300, now: float | None = None) -> bool:
    """Is this webhook really from Paddle, and recent?

    THE RAW BODY, NEVER A RE-SERIALISED ONE. `json.dumps(json.loads(x))`
    is different bytes from `x` — key order, spacing, unicode escaping —
    so it produces a different HMAC and every genuine webhook fails. This
    is why the server hands the untouched request body straight here and
    only parses it after the check returns True.

    The signed payload is `{ts}:{raw_body}`, keyed with the notification
    secret. Compared with `compare_digest`, because `==` on a hex digest
    returns early on the first wrong character and leaks the prefix to
    anyone willing to measure.

    The timestamp window makes a captured-and-replayed webhook stale. It
    does NOT make a replay harmless on its own — `already_handled()` in
    billing.py is what stops the same event being applied twice — the two
    guard different attacks and both are needed.

    ⚠️  UNVERIFIED against a real Paddle payload; see the module docstring.
    """
    if not raw_body or not secret:
        return False
    ts, hashes = parse_signature(header)
    if not ts or not hashes:
        return False
    now = time.time() if now is None else now
    if abs(now - ts) > tolerance:
        return False
    signed = str(ts).encode() + b":" + raw_body
    want = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(want, h) for h in hashes)


def _period_end(sub: dict) -> float | None:
    """Paid-through, as a unix timestamp.

    Paddle dates are RFC3339 strings rather than Stripe's integers, and
    `current_billing_period.ends_at` is the field that answers "until
    when is this person entitled". Anything unparseable becomes None,
    which `entitled()` reads as "no known paid-through date" — the safe
    direction, because the alternative is granting access on a date we
    invented.
    """
    period = (sub or {}).get("current_billing_period") or {}
    raw = period.get("ends_at") or sub.get("next_billed_at")
    if not raw:
        return None
    text = str(raw).replace("Z", "+00:00")
    try:
        import datetime as _dt
        return _dt.datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError):
        return None


def _user_id(sub: dict) -> int | None:
    """Which account this subscription belongs to.

    We put it in `custom_data.user_id` when the checkout is created,
    which is Paddle's equivalent of Stripe's `client_reference_id`. If it
    is missing the caller falls back to matching on customer_id — the
    same asymmetry billing.read_event documents, for the same reason:
    losing the link between a payment and an account is the one failure
    that cannot be repaired from our side.
    """
    custom = (sub or {}).get("custom_data") or {}
    raw = custom.get("user_id")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def read_event(payload: dict) -> dict | None:
    """Normalise to the shape billing.apply_event already understands.

    Returns None for events we do not act on, which the endpoint answers
    with a 200 — see HANDLED above for why a rejection would be worse.
    """
    kind = str((payload or {}).get("event_type") or "")
    if kind not in HANDLED:
        return None
    data = (payload or {}).get("data") or {}
    out = {"event": kind, "customer_id": None, "subscription_id": None,
           "user_id": None, "status": None, "period_end": None}

    if kind == "transaction.completed":
        # A completed transaction proves money moved, and carries the
        # subscription it belongs to. The subscription.* event carries the
        # authoritative status, so this one deliberately does not guess at
        # one beyond "something was paid".
        out["customer_id"] = data.get("customer_id")
        out["subscription_id"] = data.get("subscription_id")
        out["user_id"] = _user_id(data)
        out["status"] = "active"
        return out

    out["customer_id"] = data.get("customer_id")
    out["subscription_id"] = data.get("id")
    out["user_id"] = _user_id(data)
    raw_status = str(data.get("status") or "").lower()
    if kind == "subscription.canceled":
        out["status"] = "canceled"
    elif kind == "subscription.paused":
        out["status"] = "paused"
    else:
        # An unknown status is NOT silently downgraded to "none": that
        # would revoke a paying customer's access because Paddle added a
        # word. Unknown is passed through, and entitled() — which grants
        # only on a known-good list — refuses it without destroying the row.
        out["status"] = STATUS_MAP.get(raw_status, raw_status or "none")
    out["period_end"] = _period_end(data)
    return out


def describe(status: str, period_end: float | None = None) -> str:
    """One line for the account card. Never a promise the row cannot back."""
    from engine.billing import describe as _describe
    if status == "paused":
        return ("Paused — billing is suspended and access is off until you "
                "resume it. Nothing has been cancelled.")
    return _describe(status, period_end)
