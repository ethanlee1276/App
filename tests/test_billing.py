"""Subscriptions: the signature is the whole security model.

Ethan, 2026-08-15: *"we will be accepting money for people to use the
website once it is complete."*

`/api/billing/webhook` is a PUBLIC URL THAT GRANTS PAID ACCESS. Every
other endpoint in this repo is either read-only or behind a session; this
one has to be reachable by a company we do not control, so it is
authenticated by a signature and nothing else. Get that wrong and it is a
free-subscription button for whoever finds the path.

So the tests here are weighted the way the risk is:

  * forged, wrong-secret, replayed and tampered payloads must all be
    refused — and the replay case is a real attack, not a theoretical one,
    because a captured valid webhook is otherwise valid forever;
  * a Stripe RETRY must not be a second grant. Stripe delivers at least
    once, not exactly once;
  * the browser must never be able to grant itself anything. `success_url`
    is a thank-you page, not an authorisation;
  * and no card number may pass through this server at all, which is what
    keeps the whole repo out of PCI scope.

The state machine gets tested too, including the awkward one: `past_due`
keeps access until the paid period ends, because a failed renewal is
usually an expiry date rather than a decision.
"""

import hashlib
import hmac
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import accounts as A                               # noqa: E402
from engine import billing as B                                # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


SERVER = _read("server.py")
APP = _read("web", "js", "app.js")
SECRET = "whsec_test_secret"


def _signed(payload, secret=SECRET, skew=0):
    body = json.dumps(payload).encode()
    ts = int(time.time()) + skew
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body,
                   hashlib.sha256).hexdigest()
    return body, f"t={ts},v1={sig}"


def _db():
    d = tempfile.mkdtemp()
    conn = A.connect(os.path.join(d, "acc.db"))
    B.init(conn)
    _code, who = A.create_user(conn, "ethan@example.com",
                               "correct-horse-battery")
    return conn, who["id"]


# --- the load-bearing function -----------------------------------------------
def test_a_genuine_webhook_verifies():
    body, hdr = _signed({"id": "evt_1", "type": "ping"})
    assert B.verify_signature(body, hdr, SECRET) is True


def test_an_unsigned_webhook_is_refused():
    """The forged case: somebody finds the URL and POSTs a payment event."""
    body = json.dumps({"id": "evt_1", "type": "ping"}).encode()
    assert B.verify_signature(body, "", SECRET) is False
    assert B.verify_signature(body, "t=1,v1=deadbeef", SECRET) is False


def test_the_wrong_secret_is_refused():
    body, hdr = _signed({"id": "evt_1", "type": "ping"})
    assert B.verify_signature(body, hdr, "whsec_other") is False
    assert B.verify_signature(body, hdr, "") is False


def test_a_tampered_body_is_refused():
    """The signature is over the bytes, so editing the amount or the
    status after signing has to break it."""
    body, hdr = _signed({"id": "evt_1", "status": "canceled"})
    assert B.verify_signature(body.replace(b"canceled", b"activeee"),
                              hdr, SECRET) is False
    assert B.verify_signature(body + b" ", hdr, SECRET) is False


def test_a_replayed_webhook_is_refused():
    """A REAL ATTACK, not a theoretical one. Without the timestamp check a
    captured valid webhook is valid forever — a cancellation could be
    replayed to undo an upgrade, or a payment replayed to extend access."""
    body, hdr = _signed({"id": "evt_1", "type": "ping"}, skew=-7200)
    assert B.verify_signature(body, hdr, SECRET) is False
    # …and a timestamp from the FUTURE is equally not a live delivery.
    body, hdr = _signed({"id": "evt_1", "type": "ping"}, skew=7200)
    assert B.verify_signature(body, hdr, SECRET) is False


def test_a_signature_at_the_edge_of_tolerance_still_works():
    """Clock skew between two machines is normal. Rejecting a webhook
    because the sender's clock is four seconds ahead would be an outage
    that looks like an attack."""
    body, hdr = _signed({"id": "evt_1"}, skew=-(B.SIGNATURE_TOLERANCE - 30))
    assert B.verify_signature(body, hdr, SECRET) is True


def test_more_than_one_signature_is_accepted_during_a_secret_roll():
    """Stripe sends several v1 values while a secret is being rotated.
    Taking only the first breaks precisely the operation that exists to
    avoid downtime."""
    body, hdr = _signed({"id": "evt_1"})
    ts, sigs = B.parse_signature(hdr)
    rolled = f"t={ts},v1=deadbeef,v1={sigs[0]}"
    assert B.verify_signature(body, rolled, SECRET) is True


def test_the_comparison_is_constant_time():
    src = _read("engine", "billing.py")
    body = src[src.index("def verify_signature("):]
    body = body[:body.index("\n\n\n")]
    assert "hmac.compare_digest" in body


def test_it_verifies_the_raw_body_not_a_reparse():
    """Parsing and re-serializing JSON changes bytes — key order, spacing,
    unicode escapes — and the signature is over bytes. A server that
    verified a re-serialized body would reject honest webhooks."""
    i = SERVER.index("def _billing_webhook(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert "verify_signature(raw" in body
    verify = body.index("verify_signature(raw")
    parse = body.index("json.loads(raw")
    assert verify < parse, "the body is parsed before the signature is checked"
    # And the POST router hands it bytes without touching them first.
    # Anchored inside do_POST on purpose: the same startswith line appears
    # in do_GET, and matching that one would test nothing at all.
    post = SERVER[SERVER.index("def do_POST("):]
    j = post.index('if parsed.path.startswith("/api/billing/")')
    route = post[j:j + 900]
    assert "self.rfile.read(length)" in route
    assert "json.loads" not in route


# --- retries and idempotency -------------------------------------------------
def test_a_retried_event_is_not_a_second_grant():
    """Stripe delivers AT LEAST once. Without this, a retried checkout is
    a second subscription and a retried cancellation can undo a fresh
    upgrade."""
    conn, _uid = _db()
    assert B.already_handled(conn, "evt_1") is False
    assert B.already_handled(conn, "evt_1") is True
    assert B.already_handled(conn, "evt_2") is False


def test_an_event_we_do_not_handle_is_ignored_rather_than_rejected():
    """Anything not 2xx gets retried, so refusing an irrelevant event
    creates a retry loop that never ends."""
    assert B.read_event({"type": "charge.refunded", "data": {"object": {}}}) is None
    i = SERVER.index("def _billing_webhook(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert '"received": True' in body


def test_an_event_for_a_customer_we_never_saw_is_not_guessed_at():
    """Inventing an owner would attach somebody's payment to the wrong
    account, which is worse than dropping it."""
    conn, _uid = _db()
    ev = B.read_event({"type": "customer.subscription.updated", "data": {
        "object": {"id": "sub_x", "customer": "cus_stranger",
                   "status": "active"}}})
    assert B.apply_event(conn, ev) is False


# --- the state machine --------------------------------------------------------
def test_who_is_entitled():
    now = time.time()
    assert B.entitled("active") is True
    assert B.entitled("trialing") is True
    assert B.entitled("canceled") is False
    assert B.entitled("canceled", now + 9999) is False
    assert B.entitled("unpaid") is False
    assert B.entitled("incomplete") is False
    assert B.entitled("none") is False
    assert B.entitled("") is False
    assert B.entitled("something_new_stripe_invented") is False


def test_a_failed_renewal_keeps_access_until_the_paid_period_ends():
    """A card that failed to renew is usually an expiry date, not a
    decision. Cutting access on the first failed charge turns a payment
    blip into a refund request."""
    now = time.time()
    assert B.entitled("past_due", now + 86400) is True
    assert B.entitled("past_due", now - 86400) is False
    assert B.entitled("past_due", None) is False


def test_the_checkout_event_carries_the_account_it_belongs_to():
    """`client_reference_id` is the only link between a Stripe payment and
    a row in our users table. Without it a completed payment arrives with
    no way to say whose it is."""
    ev = B.read_event({"type": "checkout.session.completed", "data": {
        "object": {"client_reference_id": "42", "customer": "cus_1",
                   "subscription": "sub_1", "payment_status": "paid"}}})
    assert ev["user_id"] == 42 and ev["status"] == "active"
    i = _read("engine", "billing.py").index("def checkout_request(")
    assert "client_reference_id" in _read("engine", "billing.py")[i:i + 1400]


def test_an_unpaid_checkout_does_not_grant_anything():
    ev = B.read_event({"type": "checkout.session.completed", "data": {
        "object": {"client_reference_id": "42", "payment_status": "unpaid"}}})
    assert B.entitled(ev["status"]) is False


def test_the_lifecycle_lands_where_it_should():
    conn, uid = _db()
    B.apply_event(conn, B.read_event({
        "type": "checkout.session.completed", "data": {"object": {
            "client_reference_id": str(uid), "customer": "cus_1",
            "subscription": "sub_1", "payment_status": "paid"}}}))
    assert B.status_for(conn, uid)["entitled"] is True
    # A renewal arrives by CUSTOMER id, with no client_reference_id.
    B.apply_event(conn, B.read_event({
        "type": "customer.subscription.updated", "data": {"object": {
            "id": "sub_1", "customer": "cus_1", "status": "active",
            "current_period_end": time.time() + 2592000}}}))
    assert B.status_for(conn, uid)["entitled"] is True
    B.apply_event(conn, B.read_event({
        "type": "customer.subscription.deleted", "data": {"object": {
            "id": "sub_1", "customer": "cus_1", "status": "canceled"}}}))
    got = B.status_for(conn, uid)
    assert got["entitled"] is False and got["status"] == "canceled"


def test_the_page_copy_says_what_is_true_including_the_awkward_states():
    assert "renews" in B.describe("active", time.time())
    assert "Payment failed" in B.describe("past_due", time.time() + 100)
    assert "Cancelled" in B.describe("canceled")
    assert "No subscription" in B.describe("none")


# --- the boundary that keeps this out of PCI scope ---------------------------
def test_no_card_number_ever_reaches_this_server():
    """The whole architecture in one assertion. The moment a card field is
    rendered here, the compliance surface stops being a paragraph and
    becomes a project."""
    src = _read("engine", "billing.py")
    for bad in ("card_number", "cvc", "exp_month", "exp_year", "card[number]"):
        assert bad not in src, f"billing.py handles {bad}"
    for bad in ('type="card"', 'name="cardnumber"', "cardNumber"):
        assert bad not in APP, f"the page renders {bad}"
    # Checkout is hosted BY STRIPE — we only ever send them somewhere.
    assert "checkout/sessions" in src


def test_the_browser_cannot_grant_itself_a_subscription():
    """`success_url` is a thank-you page. If returning from Checkout were
    enough to become entitled, so would be typing that URL."""
    src = _read("engine", "billing.py")
    i = src.index("def checkout_request(")
    assert "success_url" in src[i:i + 1400]
    # Nothing in the server grants entitlement outside the webhook path.
    for marker in ("apply_event(", "already_handled("):
        first = SERVER.index(marker)
        hook = SERVER.index("def _billing_webhook(")
        end = SERVER.index("\n    def ", hook + 1)
        assert hook < first < end, f"{marker} is used outside the webhook"


def test_an_unsigned_endpoint_refuses_rather_than_trusting():
    """"We will add the signing secret later" is exactly how a webhook
    ships accepting anything."""
    i = SERVER.index("def _billing_webhook(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert "if not whsec" in body
    assert "503" in body


def test_the_secret_key_never_reaches_an_exception():
    src = _read("engine", "billing.py")
    body = src[src.index("def _post("):]
    body = body[:body.index("\n\n\n")]
    assert "{headers" not in body and "headers!r" not in body
    assert "secret_key" not in body


def test_checkout_and_portal_need_a_signed_in_account():
    i = SERVER.index("def _billing_post(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert "sign in first" in body


# --- what is switched off, on purpose ----------------------------------------
def test_nothing_is_gated_yet_and_that_is_written_down():
    """The plumbing is complete and no feature asks "has this person
    paid?". Turning a paywall on before Ethan has said what is behind it
    would lock him out of his own board on an inference."""
    doc = _read("docs", "BILLING.md")
    assert "Nothing is charging anyone yet" in doc
    assert "No feature checks entitlement" in doc
    # Entitlement is computed and reported, and read by nothing else.
    hits = [f for f in os.listdir(os.path.join(ROOT, "engine"))
            if f.endswith(".py") and f not in ("billing.py",)
            and "entitled" in _read("engine", f)]
    assert not hits, f"something started gating on entitlement: {hits}"


def test_the_unverified_parts_are_named_rather_than_implied_to_work():
    """This container cannot reach Stripe. Saying which parts that leaves
    unproven is the difference between a limitation and a surprise."""
    doc = _read("docs", "BILLING.md")
    assert "What has NOT been verified" in doc
    assert "cannot be from here" in doc


def test_the_setup_order_is_written_down():
    """The webhook secret does not exist until the endpoint does, so the
    steps only work in one order."""
    doc = _read("docs", "BILLING.md")
    assert "in this order" in doc
    assert doc.index("A Product with a recurring Price") < doc.index("The webhook, last")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
