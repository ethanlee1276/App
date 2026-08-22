"""A customer who pays gets in even when the webhook never arrives.

WHY THIS IS NOT HYPOTHETICAL. Entitlement moved only when Stripe's signed
webhook reached us. A webhook is a request from Stripe's servers to ours,
so everything in front of the site gets a vote on whether a paying
customer receives what they paid for. On 2026-08-21 — the evening the site
went live and was posted to Instagram — Cloudflare's Bot Fight Mode was
switched on over it. On the free plan that feature cannot be scoped to
skip a path, and a webhook POST from a datacentre is exactly the shape of
traffic it exists to challenge.

That is one cause. A restart at the wrong second, a webhook secret rotated
and not updated, Stripe having a bad ten minutes: all of them end the same
way. Money taken, site still locked, and an email that begins "I paid".

THE FIX IS TO ASK RATHER THAN WAIT. The browser comes back from Checkout
carrying the session id; the server fetches that session FROM STRIPE and
writes the entitlement if Stripe says it was paid. Nothing has to be
delivered to us for that to work.

AND THE SESSION ID GRANTS NOTHING. It is a handle, not a credential:

  * the session is read from Stripe, never from the request body;
  * Stripe's own `payment_status` has to say `paid`;
  * `client_reference_id` has to be the account doing the asking.

A session id belonging to somebody else — pasted, guessed, or lifted from
a shared URL — entitles nobody. That is what most of this file tests.

    python3 tests/test_paid_without_webhook.py
"""

import json
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import billing as BI                            # noqa: E402

PAYER = 41
STRANGER = 77
SESSION = "cs_test_a1b2c3"


class FakeStripe:
    """Stands in for the network. Records what was asked for, so the
    ownership check can be shown to happen BEFORE anything is written."""

    def __init__(self, session, subscription=None):
        self.session = session
        self.subscription = subscription or {}
        self.asked = []

    def __call__(self, url, secret_key, timeout=20):
        self.asked.append(url)
        if "/checkout/sessions/" in url:
            return self.session
        if "/subscriptions/" in url:
            return self.subscription
        raise AssertionError("unexpected call: %s" % url)


def _db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    BI.init(conn)
    return conn, path


def _session(**over):
    out = {
        "id": SESSION,
        "payment_status": "paid",
        "client_reference_id": str(PAYER),
        "customer": "cus_ABC",
        "metadata": {"plan": "yearly", "user_id": str(PAYER)},
        "subscription": "sub_XYZ",
    }
    out.update(over)
    return out


def _sub(**over):
    out = {"id": "sub_XYZ", "status": "active",
           "metadata": {"plan": "yearly"},
           "items": {"data": [{"current_period_end": 4102444800}]}}
    out.update(over)
    return out


def _run(session, subscription=None, user=PAYER, sid=SESSION):
    conn, path = _db()
    fake = FakeStripe(session, subscription)
    real_get, real_keys = BI._get, BI.keys
    BI._get = fake
    BI.keys = lambda: ("sk_test_x", "whsec_x", "price_m")
    try:
        return BI.reconcile_session(conn, user, sid), conn, fake
    finally:
        BI._get, BI.keys = real_get, real_keys
        os.unlink(path)


# --- the point of the whole thing -------------------------------------------
def test_a_paid_session_entitles_the_person_who_paid():
    out, conn, _ = _run(_session(), _sub())
    assert out["entitled"] is True, out
    row = conn.execute("SELECT * FROM subscriptions").fetchone()
    assert row["user_id"] == PAYER
    assert row["customer_id"] == "cus_ABC"
    assert row["subscription_id"] == "sub_XYZ"
    assert row["plan"] == "yearly", (
        "the term was lost, so the account page cannot say what they bought")


def test_the_period_end_survives_being_on_the_subscription_item():
    """Stripe moved this field onto the items. Read from the top level
    only, it comes back NULL — and a NULL period_end silently disables the
    past_due grace period, locking out somebody whose card blipped."""
    out, conn, _ = _run(_session(), _sub())
    assert conn.execute(
        "SELECT period_end FROM subscriptions").fetchone()[0] == 4102444800


def test_a_session_whose_subscription_has_not_settled_still_lets_them_in():
    """A paid session with no subscription object yet is still a paid
    session. Telling a customer who just paid that they have nothing is
    the worse of the two mistakes by a distance."""
    out, _, _ = _run(_session(subscription=None), None)
    assert out["entitled"] is True, out


# --- the ownership check ----------------------------------------------------
def test_somebody_elses_session_id_entitles_nobody():
    """The whole security of the endpoint. Session ids travel: they are in
    a URL, in a browser history, in a screenshot."""
    out, conn, _ = _run(_session(), _sub(), user=STRANGER)
    assert out["entitled"] is False, (
        "a stranger presented a real paid session id and was let in")
    assert conn.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0] == 0


def test_a_session_with_no_owner_on_it_entitles_nobody():
    out, conn, _ = _run(_session(client_reference_id=None, metadata={}),
                        _sub())
    assert out["entitled"] is False
    assert conn.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0] == 0


def test_an_unpaid_session_changes_nothing():
    for status in ("unpaid", "no_payment_required", "", None):
        out, conn, _ = _run(_session(payment_status=status), _sub())
        assert out["entitled"] is False, status
        assert conn.execute(
            "SELECT COUNT(*) FROM subscriptions").fetchone()[0] == 0


def test_the_metadata_user_id_is_accepted_as_well_as_the_reference():
    """Both are stamped at checkout. Either identifies the payer; needing
    both would fail a session created before one of them existed."""
    out, _, _ = _run(_session(client_reference_id=None), _sub())
    assert out["entitled"] is True


# --- what it refuses to even ask about --------------------------------------
def test_a_session_id_that_is_not_one_is_not_sent_to_stripe():
    """Rate limiting is not the only reason. An arbitrary string in a URL
    path is a request we should not be making on a stranger's say-so."""
    for junk in ("", "   ", "sub_XYZ", "../../admin", "cs" + "x" * 400,
                 "'; DROP TABLE subscriptions;--"):
        out, _, fake = _run(_session(), _sub(), sid=junk)
        assert fake.asked == [], "sent %r to Stripe" % junk
        assert out["entitled"] is False


def test_somebody_already_entitled_is_not_re_read_from_stripe():
    """An idle browser refreshing a `?paid=1` URL should not turn into a
    Stripe call per reload."""
    conn, path = _db()
    try:
        BI.apply_event(conn, {"user_id": PAYER, "customer_id": "cus_ABC",
                              "subscription_id": "sub_XYZ",
                              "status": "active", "period_end": 4102444800,
                              "plan": "yearly"})
        fake = FakeStripe(_session(), _sub())
        real_get, real_keys = BI._get, BI.keys
        BI._get, BI.keys = fake, lambda: ("sk_test_x", "whsec_x", "price_m")
        try:
            out = BI.reconcile_session(conn, PAYER, SESSION)
        finally:
            BI._get, BI.keys = real_get, real_keys
        assert out["entitled"] is True
        assert fake.asked == [], "asked Stripe about a settled account"
    finally:
        os.unlink(path)


# --- the wiring -------------------------------------------------------------
def test_the_session_id_comes_back_from_checkout():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    assert "{CHECKOUT_SESSION_ID}" in src, (
        "Stripe is not asked to send the session id back, so there is "
        "nothing to reconcile with")
    assert "paid=1&s=" in src


def test_the_browser_asks_before_it_waits():
    """The wait is the fallback now, not the mechanism. Asking after a
    twelve-second spinner would be twelve seconds of a paying customer
    looking at a wall."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("async function paidReturnWait()")
    body = app[i:app.index("\n}", i)]
    assert "/api/billing/confirm" in body, "nothing asks Stripe on return"
    assert body.index("/api/billing/confirm") < body.index("PAID_WAIT_MS"), (
        "it waits for the webhook first and only then asks")


def test_the_endpoint_needs_an_account():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    i = src.index("def _billing_confirm(")
    body = src[i:src.index("\n    def ", i + 10)]
    assert "sign in first" in body, (
        "an anonymous caller can hand this endpoint session ids")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
