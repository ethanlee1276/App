"""Stripe, end to end: the request, the return trip, and what grants access.

Ethan, 2026-08-21, with the dashboard open: *"everything is all set so
lets fully push this pay wall … figure out how to code stripe into the
website seemlessly and get it all set and square."*

WHAT CAN AND CANNOT BE PROVED FROM HERE, said first because the gap is
the risk. This container cannot reach api.stripe.com. Nothing below
proves Stripe agrees with any request we build. What it proves is that
the request is the RIGHT SHAPE, that the pieces which decide entitlement
are wired to the signed webhook and to nothing else, and that the paths
which could silently charge the wrong amount refuse instead.

The one live-fire check that has no substitute is a real test-mode
purchase with card 4242 4242 4242 4242, and docs/BILLING.md says so at
the point where it matters.

THE IDEA THE WHOLE FILE RESTS ON. A browser saying "I paid" is a claim
from an untrusted party — `?paid=1` is a string anyone can type. Only a
signature-verified webhook moves entitlement. Several tests below exist
purely to prove the return-trip code cannot grant anything.

    python3 tests/test_stripe_wiring.py
"""

import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import billing                                     # noqa: E402
from engine import stripeset                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _server():
    return _read("server.py")


def _app():
    return _read("web", "js", "app.js")


def _body(secret="sk_test_k", price="price_x", uid=7, plan="monthly"):
    _url, headers, body = billing.checkout_request(
        secret, price, uid, "a@b.c", "https://s/ok", "https://s/no", plan)
    return headers, body.decode()


# --- the checkout request ------------------------------------------------------
def test_the_session_carries_the_account_the_payment_belongs_to():
    """Without `client_reference_id` a completed payment arrives with a
    Stripe customer id and nothing to say whose it is."""
    _h, body = _body(uid=41)
    assert "client_reference_id=41" in body


def test_the_plan_is_stamped_on_the_subscription_and_not_only_the_session():
    """They are different objects. Later `customer.subscription.updated`
    events carry the subscription's metadata and never the session's, so
    a plan stamped one place is known at purchase and forgotten at the
    first renewal."""
    _h, body = _body(plan="yearly")
    assert "subscription_data%5Bmetadata%5D%5Bplan%5D=yearly" in body
    assert "metadata%5Bplan%5D=yearly" in body


def test_idempotency_is_a_header_because_that_is_where_stripe_reads_it():
    """It used to be a form field named `idempotency_key`, which is not a
    feature — so the double-tap protection the comment claimed was never
    switched on."""
    headers, body = _body()
    assert "Idempotency-Key" in headers
    assert "idempotency_key" not in body, \
        "still sending idempotency as a body parameter, where it does nothing"


def test_a_double_tap_dedupes_and_a_later_attempt_does_not():
    """A FIXED KEY PER ACCOUNT IS WORSE THAN NONE. Stripe replays the
    first session's response to a repeated key for 24 hours, so somebody
    who cancelled and came back — or bought monthly and wanted yearly —
    would be handed a stale or dead Checkout URL with no error saying
    why."""
    now = 1_700_000_000.0
    a = billing.idempotency_key(7, "monthly", now)
    b = billing.idempotency_key(7, "monthly", now + 2)
    assert a == b, "two taps two seconds apart would make two subscriptions"
    later = billing.idempotency_key(7, "monthly",
                                    now + billing.IDEMPOTENCY_WINDOW + 1)
    assert later != a, "the same account can never start a second checkout"
    other = billing.idempotency_key(7, "yearly", now)
    assert other != a, "switching plan would replay the old plan's session"
    assert billing.idempotency_key(8, "monthly", now) != a, \
        "two accounts share one key"


def test_no_card_field_is_ever_sent_to_stripe_by_us():
    """We hand off; we do not collect. A card parameter in this body
    would mean the number passed through this server."""
    _h, body = _body()
    low = body.lower()
    for bad in ("card", "cvc", "cvv", "number=", "exp_month"):
        assert bad not in low, f"the checkout body carries {bad!r}"


def test_stripes_own_promotion_codes_are_not_switched_on():
    """Discount codes here are ours (engine/redeem.py) and grant
    entitlement with no card and no subscription. A second coupon system
    that knows nothing about the first makes "why did my code work on the
    account page but not at checkout" a question with no good answer."""
    _h, body = _body()
    assert "allow_promotion_codes" not in body


def test_the_secret_key_travels_in_a_header_and_never_in_the_body():
    headers, body = _body(secret="sk_test_do_not_log_me")
    assert headers["Authorization"] == "Bearer sk_test_do_not_log_me"
    assert "sk_test_do_not_log_me" not in body


# --- what moves entitlement ----------------------------------------------------
def test_the_browser_reads_entitlement_and_never_writes_it():
    """`?paid=1` is a string anybody can type, and it must grant nothing.

    THIS USED TO SAY "only the webhook grants". That was the architecture
    until 2026-08-21, when it turned out to be a liability rather than a
    guarantee: a webhook is a request from Stripe's servers to ours, so
    every box in front of the site — a WAF, a proxy, a firewall rule —
    gets a vote on whether a paying customer receives what they paid for.
    Cloudflare's Bot Fight Mode went on over the live site that evening
    and on the free plan cannot be told to skip the webhook path.

    The return trip may now ASK. What it must never do is DECIDE. The
    browser sends a session id to our server; our server reads that
    session from Stripe and checks it was paid and whose it is. The claim
    still comes from Stripe, and the only thing that changed is the
    direction the answer travels — see engine/billing.reconcile_session
    and tests/test_paid_without_webhook.py, which is where the ownership
    and payment checks are tested.

    So: nothing in the browser writes entitlement, and the return trip
    must go through the server to get one."""
    app = _app()
    fn = app[app.index("async function paidReturnWait("):]
    fn = fn[:fn.index("\n}\n") + 2]
    # Comments here describe what the function refuses to do, and four
    # other tests in this repo have tripped on exactly that.
    fn = re.sub(r"/\*.*?\*/", " ", fn, flags=re.S)
    fn = re.sub(r"(?m)//.*$", "", fn).lower()
    for writer in ("redeem", "localstorage", "entitled =", "entitled=true",
                   "entitled = true", "classlist.remove"):
        assert writer not in fn, \
            f"the return-trip handler contains {writer!r}"
    assert "paywallcheck()" in fn, \
        "it does not re-ask the server, so it is asserting rather than checking"
    # And the asking goes to OUR server, which is what verifies with
    # Stripe. A fetch straight to Stripe from the page would need a key
    # in the page.
    assert "/api/billing/confirm" in fn
    assert "api.stripe.com" not in fn, \
        "the page talks to Stripe directly, which means a key in the page"


def test_the_return_trip_gives_up_rather_than_spinning_forever():
    """At the point it gives up, something is actually wrong — the
    webhook is unconfigured, or Stripe cannot reach us — and a spinner
    would hide it."""
    app = _app()
    assert re.search(r"PAID_WAIT_MS\s*=\s*\d+", app), "no bound on the wait"
    fn = app[app.index("async function paidReturnWait("):]
    fn = fn[:fn.index("\n}\n") + 2]
    assert "Date.now() <" in fn, "the loop has no deadline"


def test_the_paid_flag_is_stripped_so_a_refresh_is_an_ordinary_load():
    app = _app()
    fn = app[app.index("async function paidReturnWait("):]
    fn = fn[:fn.index("\n}\n") + 2]
    assert "searchParams.delete" in fn and "replaceState" in fn


def test_a_forged_event_body_cannot_move_a_subscription():
    """The signature is the whole defence on a public URL. This checks
    the verifier the endpoint calls, with the endpoint's own tolerance."""
    secret = "whsec_test"
    raw = b'{"id":"evt_1","type":"customer.subscription.deleted"}'
    ts = int(time.time())
    import hashlib
    import hmac
    good = hmac.new(secret.encode(), f"{ts}.".encode() + raw,
                    hashlib.sha256).hexdigest()
    assert billing.verify_signature(raw, f"t={ts},v1={good}", secret)
    assert not billing.verify_signature(raw + b" ", f"t={ts},v1={good}", secret)
    assert not billing.verify_signature(raw, f"t={ts},v1={'0' * 64}", secret)
    stale = ts - billing.SIGNATURE_TOLERANCE - 5
    old = hmac.new(secret.encode(), f"{stale}.".encode() + raw,
                   hashlib.sha256).hexdigest()
    assert not billing.verify_signature(raw, f"t={stale},v1={old}", secret), \
        "a captured webhook replayed later still verifies"


def test_the_whole_purchase_lands_in_the_database_with_its_plan():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT);")
    conn.execute("INSERT INTO users (id,email) VALUES (9,'a@b.c')")
    billing.init(conn)

    done = billing.read_event({
        "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": "9", "customer": "cus_9",
                            "subscription": "sub_9", "payment_status": "paid",
                            "metadata": {"plan": "sixmonth"}}}})
    assert billing.apply_event(conn, done)
    st = billing.status_for(conn, 9)
    assert st["entitled"] and st["plan"] == "sixmonth"
    assert st["plan_name"] == "6 months"

    # A renewal failure keeps them in until the paid period ends — a card
    # that failed to renew is usually an expiry date, not a decision.
    fail = billing.read_event({
        "type": "invoice.payment_failed",
        "data": {"object": {"customer": "cus_9", "subscription": "sub_9"}}})
    assert billing.apply_event(conn, fail)
    st = billing.status_for(conn, 9)
    assert st["status"] == "past_due"
    assert st["plan"] == "sixmonth", \
        "an event carrying no plan blanked the term off the account page"

    gone = billing.read_event({
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_9", "customer": "cus_9",
                            "status": "canceled"}}})
    assert billing.apply_event(conn, gone)
    assert not billing.status_for(conn, 9)["entitled"]
    conn.close()


def test_a_subscription_without_metadata_still_finds_its_plan():
    """Older subscriptions, and any made by hand in the dashboard, carry
    no metadata. The price id on the line item still identifies the plan
    when it is one of ours."""
    os.environ["STRIPE_PRICE_YEARLY"] = "price_yr"
    try:
        ev = billing.read_event({
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_1", "customer": "cus_1",
                                "status": "active",
                                "items": {"data": [{"price": {"id": "price_yr"}}]}}}})
        assert ev["plan"] == "yearly"
        blind = billing.read_event({
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_1", "customer": "cus_1",
                                "status": "active",
                                "items": {"data": [{"price": {"id": "price_?"}}]}}}})
        assert blind["plan"] is None, "an unknown price was guessed at"
    finally:
        os.environ.pop("STRIPE_PRICE_YEARLY", None)


def test_the_paid_through_date_is_read_from_where_stripe_now_puts_it():
    """STRIPE MOVED IT, and a new account gets the new API version.

    `current_period_start/end` used to sit on the Subscription; on recent
    versions they live on each subscription ITEM, because a subscription
    can hold items on different cycles. So a brand-new install reads None
    from the old location and nothing says why.

    Found on the first real purchase — the row came back `active` with
    the right plan and `period_end` NULL. That looks harmless and is not:
    see the next test.
    """
    now = time.time()
    ev = billing.read_event({
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_1", "customer": "cus_1",
                            "status": "active",
                            "items": {"data": [
                                {"current_period_end": now + 2592000}]}}}})
    assert ev["period_end"] and ev["period_end"] > now, \
        "the paid-through date on the item was not read"

    # …and the old location still works, for an account on an older
    # version and for every subscription created before the change.
    legacy = billing.read_event({
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_1", "customer": "cus_1",
                            "status": "active",
                            "current_period_end": now + 864000}}})
    assert legacy["period_end"] and legacy["period_end"] > now

    # Several items: access ends when the LAST thing they paid for ends.
    many = billing.read_event({
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "s", "customer": "c", "status": "active",
                            "items": {"data": [
                                {"current_period_end": now + 100},
                                {"current_period_end": now + 9999}]}}}})
    assert abs(many["period_end"] - (now + 9999)) < 1, \
        "the earliest item won, so access ends before it should"


def test_a_null_paid_through_date_silently_kills_the_grace_period():
    """WHY THE ONE ABOVE MATTERS, stated as the consequence rather than
    the mechanism.

    `entitled()` grants `past_due` only while the paid-through date is
    still in the future — a failed renewal is usually an expiry date
    rather than a decision, and locking somebody out on the first failed
    charge turns a payment blip into a refund request. With the date
    null, `bool(period_end)` is False and that whole grace period is off:
    the customer is cut the instant a renewal fails.

    Nothing errors. The subscription reads `active` and correct right up
    until the day it does not.
    """
    now = time.time()
    assert billing.entitled("past_due", now + 86400, now=now), \
        "a past-due subscription inside its paid period was refused"
    assert not billing.entitled("past_due", None, now=now), \
        "this test no longer describes the code it is protecting"
    assert not billing.entitled("past_due", now - 1, now=now)
    # active does not depend on the date, which is why the null was
    # invisible on the first purchase.
    assert billing.entitled("active", None, now=now)


def test_a_malformed_subscription_payload_does_not_throw():
    """Webhook handlers that raise get retried forever. Every shape below
    is one Stripe could send on an edge case."""
    for obj in ({"id": "s", "customer": "c", "status": "active", "items": {}},
                {"id": "s", "customer": "c", "status": "active",
                 "items": {"data": []}},
                {"id": "s", "customer": "c", "status": "active",
                 "items": {"data": [{}]}},
                {"id": "s", "customer": "c", "status": "active",
                 "items": {"data": [{"price": None}]}},
                {"id": "s", "customer": "c", "status": "active",
                 "metadata": "not-a-dict"}):
        got = billing.read_event({"type": "customer.subscription.updated",
                                  "data": {"object": obj}})
        assert got["plan"] is None


# --- the server's half ---------------------------------------------------------
def test_the_endpoint_reads_the_plan_the_browser_asked_for():
    s = _server()
    i = s.index("def _billing_post(")
    body = s[i:s.index("\n    def ", i + 1)]
    assert 'body.get("plan")' in body, \
        "the checkout endpoint ignores the plan and charges one price"
    assert "BI.start_checkout(" in body


def test_the_return_and_cancel_urls_both_land_somewhere_real():
    s = _server()
    i = s.index("def _billing_post(")
    body = s[i:s.index("\n    def ", i + 1)]
    assert "?paid=1" in body, "nothing marks the return trip"
    assert "#paywall" in body, \
        "cancelling at Stripe drops them somewhere with no plans on it"


def test_the_return_url_can_be_pinned_because_host_is_whatever_they_typed():
    """Somebody who reaches the site on a bare IP gets returned to a bare
    IP after paying — to a certificate warning, or to nothing."""
    s = _server()
    i = s.index("def _site_base(")
    body = s[i:s.index("\n    def ", i + 1)]
    assert "QB_SITE_URL" in body


def test_the_status_endpoint_says_which_plans_can_actually_be_sold():
    s = _server()
    i = s.index("def _billing_get(")
    body = s[i:s.index("\n    def ", i + 1)]
    assert "BI.plan_catalogue()" in body


# --- provisioning ---------------------------------------------------------------
def test_setup_is_safe_to_run_twice():
    """The natural way to use it is to run it, get interrupted, and run
    it again. The natural bug is duplicate prices with nothing to say
    which one the site charges."""
    src = _read("engine", "stripeset.py")
    assert "lookup_key" in src, "prices carry no unique key, so a rerun duplicates"
    for plan in billing.PLANS.values():
        assert plan["lookup_key"].startswith("qellys_")


def test_an_existing_price_that_disagrees_is_reported_and_not_edited():
    """Stripe prices are immutable on purpose: a price somebody is
    subscribed to must not change underneath them."""
    plan = billing.PLANS["monthly"]
    ok = {"unit_amount": plan["cents"], "currency": "usd",
          "recurring": {"interval": "month", "interval_count": 1}}
    assert stripeset._matches(ok, "monthly") == []
    wrong = dict(ok, unit_amount=3000)
    assert stripeset._matches(wrong, "monthly"), \
        "a price charging $30 for our $25 plan reported as fine"
    assert stripeset._matches(dict(ok, currency="eur"), "monthly")
    assert stripeset._matches(
        dict(ok, recurring={"interval": "year", "interval_count": 1}), "monthly")


def test_the_product_is_matched_on_metadata_and_never_on_its_name():
    """A name match would attach us to whatever somebody else called
    "Qellys Book", and renaming a product — allowed, harmless — would
    make setup create a second one."""
    src = _read("engine", "stripeset.py")
    fn = src[src.index("def find_product("):]
    fn = fn[:fn.index("\n\n\n")]
    assert "metadata" in fn
    assert "PRODUCT_NAME" not in fn, "the product is matched on its name"


def test_preflight_reports_every_missing_piece_rather_than_the_first():
    """Seeing all of them at once is the difference between one round of
    setup and five."""
    for name in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
                 "STRIPE_PRICE_MONTHLY", "STRIPE_PRICE_SIXMONTH",
                 "STRIPE_PRICE_YEARLY", "STRIPE_PRICE_ID"):
        os.environ.pop(name, None)
    checks = stripeset.preflight()
    missing = [h for ok, h, _ in checks if not ok]
    assert len(missing) >= 5, f"only reported {missing}"
    assert any("WEBHOOK" in h for h in missing)


def test_no_check_ever_prints_a_key():
    """A key in a terminal is a key in a scrollback buffer, a screenshot
    and a support thread."""
    os.environ["STRIPE_SECRET_KEY"] = "sk_test_SECRETVALUE"
    os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_SECRETVALUE"
    try:
        blob = " ".join(f"{h} {d}" for _ok, h, d in stripeset.preflight())
        assert "SECRETVALUE" not in blob
        assert "sk_test_SECRETVALUE" not in blob
    finally:
        os.environ.pop("STRIPE_SECRET_KEY", None)
        os.environ.pop("STRIPE_WEBHOOK_SECRET", None)


def test_test_and_live_are_distinguishable_before_anyone_is_charged():
    """`sk_test_` and `sk_live_` look nearly identical in a config file
    and behave completely differently. "Why did nobody get charged" is a
    bad thing to debug in production."""
    assert billing.live_mode("sk_live_abc")
    assert not billing.live_mode("sk_test_abc")
    assert not billing.live_mode("")
    assert not billing.live_mode(None)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
