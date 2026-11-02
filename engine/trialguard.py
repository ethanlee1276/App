"""One free trial per person: an email address or a card that has had one does not get another.

Ethan, 2026-11-02: "we do not want people making a new account and taking
advantage of the trials". The rule was one trial per ACCOUNT
(billing.has_subscribed_before), so a new account — or the same address
after deleting the old one — started the trial again.

TWO MARKS, made when a trial starts (`note`, `check`):

  * the account's email address (a phone account's number, which its
    placeholder address carries), the same mailbox however it is written:
    case, and the +tag of any address, and for Gmail the dots too
    (`same_address`);
  * the card the trial was started with, by Stripe's own card fingerprint —
    the same card number gives the same fingerprint on our Stripe account,
    and it is not the number.

Each is kept only as a keyed one-way hash (HMAC-SHA256 with the site's own
key, engine/digest._unsub_key, under its own prefix, as engine/calfeed does),
in `trial_marks`, with no account attached. So it outlives a deleted account,
which is the point, and cannot be read back into an address or a card. Kept
MARK_KEEP_S (three years), then dropped. The Privacy Policy says all of this.

WHAT THEY DO:

  * an address that has had a trial is offered none (`had_trial`: the plans
    page's `trial_eligible`, and the checkout, which decides);
  * a trial started with a card that has had one — a new address, the same
    card — is cancelled at Stripe the moment we see it (`check`): nothing is
    charged, the account page says why (billing TRIAL_REFUSED), and a plan
    from there is a paid one, since the account now has a subscription row.

FOR TRIALS STARTED FROM RULE_FROM (2 November 2026), the date the plans page,
the Terms and the Privacy Policy say so; an earlier one is neither marked nor
checked. Checked on the return from Checkout and on Stripe's webhook, and by
the billing sweep for anything those missed (`sweep`). A read of Stripe that
fails leaves the row for the next pass; a card Stripe does not show (none on
the subscription or the customer) marks the address alone.

Standard library only. No address, card fingerprint or mark is ever logged.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import billing as BI

#: The day the rule began: the same day as a cancelled trial's walled access.
RULE_FROM = BI.TRIAL_CANCEL_ENDS_ACCESS_FROM
#: How long a mark is kept, then dropped (Privacy Policy §7).
MARK_KEEP_S = 3 * 365 * 86400
#: The most one sweep checks: far above a real day; a bound on a loop that talks to Stripe.
MAX_PER_SWEEP = 50
_SUB = re.compile(r"sub_[A-Za-z0-9]{1,190}")
_CUS = re.compile(r"cus_[A-Za-z0-9]{1,190}")
_GMAIL = ("gmail.com", "googlemail.com")


def init(conn) -> None:
    BI.init(conn)
    conn.execute("""CREATE TABLE IF NOT EXISTS trial_marks (
        kind TEXT NOT NULL,          -- 'email' or 'card'
        mark TEXT NOT NULL,          -- HMAC-SHA256 hex; never the address or the card
        at   REAL NOT NULL,
        PRIMARY KEY (kind, mark))""")
    conn.commit()


def same_address(email) -> str:
    """One mailbox, however it is written: lower case, no +tag, and for
    Gmail no dots and one domain."""
    e = str(email or "").strip().lower()
    if "@" not in e:
        return e
    local, _, domain = e.rpartition("@")
    local = local.split("+", 1)[0]
    if domain in _GMAIL:
        local, domain = local.replace(".", ""), "gmail.com"
    return f"{local}@{domain}"


def _mark(kind: str, value: str) -> str:
    from . import digest as DG
    return hmac.new(DG._unsub_key(), f"trial:{kind}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def seen(conn, kind: str, value) -> bool:
    if not value:
        return False
    init(conn)
    v = same_address(value) if kind == "email" else str(value)
    return bool(conn.execute("SELECT 1 FROM trial_marks WHERE kind = ? AND mark = ?",
                             (kind, _mark(kind, v))).fetchone())


def remember(conn, kind: str, value, now: float | None = None) -> None:
    if not value:
        return
    init(conn)
    t = time.time() if now is None else float(now)
    v = same_address(value) if kind == "email" else str(value)
    conn.execute("INSERT OR IGNORE INTO trial_marks (kind, mark, at) VALUES (?,?,?)", (kind, _mark(kind, v), t))
    conn.execute("DELETE FROM trial_marks WHERE at < ?", (t - MARK_KEEP_S,))


def had_trial(conn, email) -> bool:
    """Has this address (any way it is written) had a free trial, on any
    account, deleted ones too? The plans page and the checkout ask."""
    try:
        return seen(conn, "email", email)
    except Exception:                                        # noqa: BLE001 — a broken lookup offers the trial; Stripe's card check still runs
        return False


def _row(conn, user_id):
    return conn.execute(
        "SELECT s.status, s.subscription_id, s.customer_id, s.started_at, s.card_checked, s.event_at, u.email "
        "FROM subscriptions s JOIN users u ON u.id = s.user_id WHERE s.user_id = ?", (int(user_id),)).fetchone()


def note(conn, user_id, now: float | None = None) -> bool:
    """Mark the address of a trial that started under the rule. True when
    the account holds such a trial."""
    init(conn)
    r = _row(conn, user_id)
    if not r or str(r["status"] or "") != "trialing" or float(r["started_at"] or 0) < RULE_FROM:
        return False
    remember(conn, "email", r["email"], now)
    conn.commit()
    return True


def _stripe_get(path: str) -> dict:
    return BI._get(f"{BI.API}/{path}", BI.keys()[0], timeout=8)


def _stripe_cancel(sub_id: str) -> dict:
    """Cancel a subscription now (DELETE). The key never reaches an
    exception, as in billing._post."""
    req = urllib.request.Request(f"{BI.API}/subscriptions/{sub_id}", method="DELETE",
                                 headers={"Authorization": f"Bearer {BI.keys()[0]}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        raise BI.BillingUnavailable(f"Stripe refused the cancel (HTTP {exc.code}).") from exc
    except Exception as exc:                                 # noqa: BLE001
        raise BI.BillingUnavailable(f"Could not reach Stripe: {type(exc).__name__}") from exc


def _fp(pm) -> str | None:
    if isinstance(pm, dict) and pm.get("type", "card") == "card":
        got = (pm.get("card") or {}).get("fingerprint")
        return str(got) if got else None
    return None


def fingerprint(sub_id: str, customer_id: str | None, fetch=None) -> str | None:
    """The card a subscription's trial was started with, by Stripe's
    fingerprint: the subscription's default, else the customer's, else the
    customer's first card. None when Stripe shows none. Raises
    BillingUnavailable when Stripe cannot be read."""
    get = fetch or _stripe_get
    sub = get(f"subscriptions/{sub_id}?expand%5B%5D=default_payment_method")
    fp = _fp((sub or {}).get("default_payment_method"))
    if fp or not (customer_id and _CUS.fullmatch(str(customer_id))):
        return fp
    cus = get(f"customers/{customer_id}?expand%5B%5D=invoice_settings.default_payment_method")
    fp = _fp(((cus or {}).get("invoice_settings") or {}).get("default_payment_method"))
    if fp:
        return fp
    cards = get(f"payment_methods?customer={urllib.parse.quote(str(customer_id))}&type=card&limit=1")
    data = (cards or {}).get("data") or []
    return _fp(data[0]) if data else None


def check(conn, user_id, now: float | None = None, fetch=None, cancel=None) -> str:
    """Look at the card a new trial was started with. ``"ok"`` (marked),
    ``"refused"`` (the card had a trial: cancelled at Stripe, nothing
    charged), ``"skip"`` (nothing to check) or ``"later"`` (Stripe could
    not be read; the next pass tries again)."""
    init(conn)
    t = time.time() if now is None else float(now)
    r = _row(conn, user_id)
    if (not r or str(r["status"] or "") != "trialing" or r["card_checked"]
            or float(r["started_at"] or 0) < RULE_FROM or not _SUB.fullmatch(str(r["subscription_id"] or ""))):
        return "skip"
    if fetch is None and not BI.configured():
        return "later"
    remember(conn, "email", r["email"], t)
    conn.commit()
    try:
        fp = fingerprint(r["subscription_id"], r["customer_id"], fetch)
    except BI.BillingUnavailable:
        return "later"
    if fp and seen(conn, "card", fp):
        try:
            sub = (cancel or _stripe_cancel)(r["subscription_id"])
        except BI.BillingUnavailable:
            return "later"
        ev = BI.read_event({"type": "customer.subscription.deleted",
                            "data": {"object": sub if isinstance(sub, dict) and sub.get("id")
                                     else {"id": r["subscription_id"], "customer": r["customer_id"]}}})
        ev["user_id"] = int(user_id)
        # Never older than what the row already reflects: apply_event drops
        # an older event, and Stripe's clock and ours need not agree.
        ev["at"] = max(t, float(r["event_at"] or 0) + 0.001)
        if not BI.apply_event(conn, ev):
            return "later"
        conn.execute("UPDATE subscriptions SET trial_refused = ?, card_checked = ? WHERE user_id = ?",
                     (t, t, int(user_id)))
        conn.commit()
        return "refused"
    if fp:
        remember(conn, "card", fp, t)
    conn.execute("UPDATE subscriptions SET card_checked = ? WHERE user_id = ?", (t, int(user_id)))
    conn.commit()
    return "ok"


def after_event(conn, event: dict, fetch=None, cancel=None) -> str:
    """The webhook's half: a trial an event has just started is checked."""
    if not event or str(event.get("status") or "") not in ("trialing", "incomplete", "active"):
        return "skip"
    uid = event.get("user_id")
    if uid is None:
        uid = BI.user_for_customer(conn, event.get("customer_id"))
    if uid is None:
        return "skip"
    return check(conn, uid, fetch=fetch, cancel=cancel)


def sweep(conn, now: float | None = None, fetch=None, cancel=None) -> int:
    """Check every trial under the rule that has not been; how many were refused."""
    init(conn)
    rows = conn.execute("SELECT user_id FROM subscriptions WHERE status = 'trialing' AND card_checked IS NULL "
                        "AND started_at >= ? LIMIT ?", (RULE_FROM, MAX_PER_SWEEP)).fetchall()
    return sum(1 for (uid,) in rows if check(conn, uid, now=now, fetch=fetch, cancel=cancel) == "refused")
