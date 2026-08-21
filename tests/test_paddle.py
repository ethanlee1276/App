"""Paddle: the processor half, after Stripe refused the category.

Ethan, 2026-08-15: *"no we cant use stripe so we gotta find a different
alternative … if u think Paddle then lets do paddel."*

WHAT THESE TESTS CAN AND CANNOT PROVE, stated plainly because the gap is
the whole risk. The dev container's egress blocks developer.paddle.com
and api.paddle.com, so the signature scheme in engine/paddle.py was
written from memory and could not be checked against their docs or a real
webhook.

What is proved here is that the construction is SELF-CONSISTENT and has
the properties a verifier must have: it accepts a payload signed the way
we sign it, rejects a changed body, rejects a changed timestamp, rejects a
stale one, and does not use `==` on the digest. What is NOT proved is that
this is the same construction Paddle uses. Only a real test webhook from
their dashboard proves that, and it is the first thing to do once the
account exists.

The distinction matters because a verifier that is wrong in the accepting
direction looks exactly like one that works.

THE SPLIT THAT MADE THIS CHEAP. Everything about what a payment MEANS —
which statuses grant access, the replay guard, the schema, the paid-through
date — stayed in engine/billing.py and is reused unchanged. `read_event`
here returns the identical dict, so the storage layer cannot tell which
processor produced it. Changing processor is one file.

2026-08-21: AND IT WAS CHANGED BACK. Paddle does not serve this business
model — Ethan checked their own site — and the Stripe account was
approved on appeal, so server.py is wired to Stripe again. That did not
make this file dead: engine/paddle.py stays correct and tested, the
adapter contract it proves (an identical event dict, so the storage layer
cannot tell the difference) is what makes the swap one file in either
direction, and it is the fallback if the Stripe account is ever closed.

What changed is the wiring tests at the bottom. They used to assert that
server.py calls PAY; they now assert the opposite — that nothing does —
because an adapter that is half-wired is worse than one that is not
wired, and "which of these two modules grants entitlement" must have
exactly one answer. tests/test_stripe_wiring.py holds the other half.
"""

import hashlib
import hmac
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import billing                                     # noqa: E402
from engine import paddle                                      # noqa: E402

SECRET = "pdl_ntfset_test_secret_value"


def _signed(body: bytes, secret=SECRET, ts=None):
    """Build a header the way engine/paddle.py says Paddle builds one."""
    ts = int(time.time()) if ts is None else int(ts)
    mac = hmac.new(secret.encode(), str(ts).encode() + b":" + body,
                   hashlib.sha256).hexdigest()
    return f"ts={ts};h1={mac}"


# --- the signature ------------------------------------------------------------
def test_a_correctly_signed_body_is_accepted():
    body = b'{"event_type":"subscription.created","data":{"id":"sub_1"}}'
    assert paddle.verify_signature(body, _signed(body), SECRET) is True


def test_one_changed_byte_is_refused():
    """The property the whole endpoint rests on. A webhook that grants
    paid access is a public URL, so anyone can POST to it — the signature
    is the only thing between that and a free subscription."""
    body = b'{"event_type":"subscription.created","data":{"id":"sub_1"}}'
    header = _signed(body)
    assert paddle.verify_signature(body + b" ", header, SECRET) is False
    assert paddle.verify_signature(body.replace(b"sub_1", b"sub_2"),
                                   header, SECRET) is False


def test_the_wrong_secret_is_refused():
    body = b'{"event_type":"subscription.created"}'
    assert paddle.verify_signature(body, _signed(body), "pdl_ntfset_other") is False


def test_a_replayed_timestamp_goes_stale():
    """Bounds how long a captured webhook stays useful. It is NOT what
    stops a replay being applied twice — billing.already_handled() is —
    and the two guard different attacks."""
    body = b'{"event_type":"subscription.created"}'
    old = time.time() - 3600
    assert paddle.verify_signature(body, _signed(body, ts=old), SECRET) is False
    # Inside the window it is fine.
    recent = time.time() - 60
    assert paddle.verify_signature(body, _signed(body, ts=recent), SECRET) is True


def test_a_timestamp_that_is_not_the_signed_one_is_refused():
    """The timestamp is part of the signed payload, so editing it to look
    fresh invalidates the hash. Without that, the freshness window is
    decoration — an attacker replays the body with a new `ts`."""
    body = b'{"event_type":"subscription.created"}'
    # Signed 200s ago — still inside the window, so the ORIGINAL verifies
    # and the only thing the forgery changes is the timestamp. (Signing
    # at "now" made the forged header byte-identical to the real one and
    # the test passed for the wrong reason.)
    signed_at = int(time.time()) - 200
    header = _signed(body, ts=signed_at)
    assert paddle.verify_signature(body, header, SECRET) is True
    _ts, hashes = paddle.parse_signature(header)
    forged = f"ts={int(time.time())};h1={hashes[0]}"
    assert forged != header
    assert paddle.verify_signature(body, forged, SECRET) is False


def test_a_malformed_header_is_a_refusal_not_a_crash():
    body = b"{}"
    for header in ("", "garbage", "ts=;h1=", "h1=abc", "ts=notanumber;h1=abc",
                   None):
        assert paddle.verify_signature(body, header, SECRET) is False


def test_an_empty_body_or_secret_is_refused():
    assert paddle.verify_signature(b"", _signed(b""), SECRET) is False
    assert paddle.verify_signature(b"{}", _signed(b"{}"), "") is False


def test_the_digest_is_not_compared_with_equals():
    """`==` on a hex digest returns early on the first wrong character,
    which leaks the prefix to anyone willing to measure the difference."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "engine",
                            "paddle.py"), encoding="utf-8").read()
    body = src[src.index("def verify_signature("):]
    body = body[:body.index("\n\n\n")]
    assert "compare_digest" in body
    assert "== h" not in body and "want ==" not in body


def test_the_raw_body_requirement_is_written_down():
    """A re-serialised body is different bytes and fails every genuine
    webhook. The reason has to survive in the file, or the next person
    'tidies' the endpoint into parsing first."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "engine",
                            "paddle.py"), encoding="utf-8").read()
    assert "RAW BODY" in src.upper()


def test_the_unverified_scheme_is_flagged_loudly():
    """The one thing that must not be quiet. This was written without
    access to Paddle's documentation, and a signature verifier that is
    wrong in the accepting direction is indistinguishable from a correct
    one until somebody forges a subscription."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "engine",
                            "paddle.py"), encoding="utf-8").read()
    assert "UNVERIFIED" in src.upper()
    assert "test webhook" in src.lower()


# --- events, normalised to the shape billing.py already understands -----------
def _sub_payload(kind, status="active", **kw):
    data = {"id": "sub_abc", "customer_id": "ctm_abc", "status": status,
            "custom_data": {"user_id": 7},
            "current_billing_period": {"ends_at": "2026-09-15T00:00:00Z"}}
    data.update(kw)
    return {"event_type": kind, "data": data}


def test_a_created_subscription_carries_the_account_it_belongs_to():
    ev = paddle.read_event(_sub_payload("subscription.created"))
    assert ev["user_id"] == 7
    assert ev["customer_id"] == "ctm_abc"
    assert ev["subscription_id"] == "sub_abc"
    assert ev["status"] == "active"
    assert ev["period_end"] and ev["period_end"] > time.time()


def test_the_normalised_event_has_exactly_the_stripe_shape():
    """The storage layer must not be able to tell which processor sent
    this. If these drift apart, apply_event() starts silently dropping a
    field and the drift is invisible until a subscription goes missing."""
    ours = set(paddle.read_event(_sub_payload("subscription.created")))
    theirs = set(billing.read_event({
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_1", "customer": "cus_1",
                            "status": "active", "current_period_end": 4e9}}}))
    assert ours == theirs, f"shapes diverged: {ours ^ theirs}"


def test_an_event_we_do_not_act_on_is_ignored_not_rejected():
    """Paddle retries anything that is not 2xx, so rejecting an
    irrelevant event builds a retry loop out of nothing."""
    assert paddle.read_event({"event_type": "report.created"}) is None
    assert paddle.read_event({}) is None
    assert paddle.read_event(None) is None


def test_cancelled_and_paused_are_different_things():
    """Paused has no Stripe equivalent. It means the customer suspended
    billing deliberately and intends to come back; treating it as
    cancelled would tear down a subscription they still want."""
    assert paddle.read_event(_sub_payload("subscription.canceled"))["status"] == "canceled"
    assert paddle.read_event(_sub_payload("subscription.paused"))["status"] == "paused"
    # And paused does NOT grant access.
    assert billing.entitled("paused", time.time() + 9e5) is False
    assert billing.entitled("active", time.time() + 9e5) is True


def test_an_unknown_status_is_passed_through_not_downgraded():
    """If Paddle adds a status word, mapping it to "none" would revoke a
    paying customer's access on our side for a vocabulary change.
    Unknown passes through, and entitled() — which grants only from a
    known-good list — refuses it without destroying the row."""
    ev = paddle.read_event(_sub_payload("subscription.updated", status="quiescent"))
    assert ev["status"] == "quiescent"
    assert billing.entitled(ev["status"], time.time() + 9e5) is False


def test_a_missing_paid_through_date_is_none_not_a_guess():
    ev = paddle.read_event(_sub_payload("subscription.updated",
                                        current_billing_period={}))
    assert ev["period_end"] is None
    ev = paddle.read_event(_sub_payload("subscription.updated",
                                        current_billing_period={"ends_at": "not a date"}))
    assert ev["period_end"] is None


def test_a_missing_user_id_falls_back_to_the_customer():
    """The link between a payment and an account is the one thing that
    cannot be repaired from our side, so the fallback has to exist."""
    ev = paddle.read_event(_sub_payload("subscription.updated", custom_data={}))
    assert ev["user_id"] is None
    assert ev["customer_id"] == "ctm_abc"


# --- it plugs into the existing storage unchanged -----------------------------
def test_a_paddle_event_writes_through_the_existing_billing_layer():
    """The point of the split: no Paddle-specific storage code exists."""
    from engine import accounts as A
    import tempfile
    from pathlib import Path
    conn = A.connect(Path(tempfile.mkdtemp()) / "acc.db")
    billing.init(conn)
    _, who = A.create_user(conn, "e@example.com", "correct-horse-battery",
                           confirmed=True)
    ev = paddle.read_event(_sub_payload("subscription.created"))
    ev["user_id"] = who["id"]
    assert billing.apply_event(conn, ev) is True
    st = billing.status_for(conn, who["id"])
    assert st["status"] == "active" and st["entitled"] is True
    assert st["customer_id"] == "ctm_abc"


def test_the_replay_guard_is_the_shared_one():
    from engine import accounts as A
    import tempfile
    from pathlib import Path
    conn = A.connect(Path(tempfile.mkdtemp()) / "acc.db")
    billing.init(conn)
    assert billing.already_handled(conn, "evt_paddle_1") is False
    assert billing.already_handled(conn, "evt_paddle_1") is True


def test_sandbox_is_a_separate_base_url():
    """A mistake in sandbox costs nothing, which is only true if the two
    cannot be confused."""
    assert paddle.SANDBOX_API != paddle.API
    os.environ["PADDLE_SANDBOX"] = "1"
    try:
        assert paddle.api_base() == paddle.SANDBOX_API
    finally:
        os.environ.pop("PADDLE_SANDBOX", None)
    assert paddle.api_base() == paddle.API


def test_the_notification_secret_is_not_the_api_key():
    """Different strings, different lifetimes, and only one belongs in a
    signature check. Reading the wrong one fails every webhook in a way
    that looks like Paddle's fault."""
    assert paddle.ENV_WEBHOOK_SECRET != paddle.ENV_API_KEY
    src = open(os.path.join(os.path.dirname(__file__), "..", "engine",
                            "paddle.py"), encoding="utf-8").read()
    vs = src[src.index("def verify_signature("):]
    vs = vs[:vs.index("\n\n\n")]
    assert "API_KEY" not in vs


# --- checkout and portal: the two calls that must go out ---------------------
#
# Same rule as the signature above: what is proved here is the SHAPE of
# the request and the parsing of the reply, not that Paddle agrees with
# either. A wrong shape at least fails loudly the first time somebody
# presses Subscribe; the tests that matter most are the ones about
# failing loudly rather than quietly.

def test_the_checkout_body_carries_the_account_id_paddle_will_hand_back():
    """custom_data.user_id is the whole link between a payment and an
    account. Lose it and a completed payment arrives with a customer id
    we have never seen and no way to attribute it — the one failure that
    cannot be repaired from our side."""
    url, headers, body = paddle.checkout_request(
        "sk_test", "pri_abc", 4242, "https://qellysbook.com/#mybets")
    sent = json.loads(body.decode())
    assert sent["custom_data"]["user_id"] == "4242"
    assert sent["items"] == [{"price_id": "pri_abc", "quantity": 1}]
    assert sent["checkout"]["url"] == "https://qellysbook.com/#mybets"
    assert url.endswith("/transactions")
    assert headers["Authorization"] == "Bearer sk_test"
    # _user_id() is the other half of the link; the two must agree on the
    # field name, and a test that only checked one would not notice.
    assert paddle._user_id({"custom_data": sent["custom_data"]}) == 4242


def test_the_checkout_body_contains_no_card_field_and_no_email():
    """Card numbers never reach this server — that is the architecture,
    not a nicety, and it is what keeps this repo out of PCI scope. The
    email is Paddle's to collect too: one less piece of somebody's data
    passing through here for no reason."""
    _u, _h, body = paddle.checkout_request("k", "pri_1", 1, "https://x/")
    sent = json.loads(body.decode())
    flat = json.dumps(sent).lower()
    for word in ("card", "number", "cvc", "cvv", "expiry", "email"):
        assert word not in flat, f"the checkout request mentions {word}"


def test_sandbox_sends_the_requests_somewhere_that_cannot_charge_anyone():
    """A sandbox flag that changes the status text but not the URL is
    worse than none: it reads as safe while moving real money."""
    was = os.environ.get(paddle.ENV_SANDBOX)
    try:
        os.environ[paddle.ENV_SANDBOX] = "1"
        assert paddle.sandbox() and paddle.api_base() == paddle.SANDBOX_API
        assert paddle.checkout_request("k", "p", 1, "u")[0].startswith(
            paddle.SANDBOX_API)
        assert paddle.portal_request("k", "ctm_1")[0].startswith(
            paddle.SANDBOX_API)
        os.environ[paddle.ENV_SANDBOX] = ""
        assert not paddle.sandbox()
        assert paddle.checkout_request("k", "p", 1, "u")[0].startswith(
            paddle.API + "/")
    finally:
        if was is None:
            os.environ.pop(paddle.ENV_SANDBOX, None)
        else:
            os.environ[paddle.ENV_SANDBOX] = was


def test_an_unreadable_reply_raises_instead_of_returning_an_empty_url():
    """The silent version of this bug sends a paying customer to a blank
    page believing they have subscribed."""
    for bad in ({}, {"data": {}}, {"data": {"checkout": {}}},
                {"data": {"checkout": {"url": ""}}}):
        try:
            paddle.checkout_url(bad)
            raise AssertionError(f"returned a URL for {bad!r}")
        except billing.BillingUnavailable:
            pass
    assert paddle.checkout_url(
        {"data": {"checkout": {"url": "https://pay.paddle.io/x"}}}) \
        == "https://pay.paddle.io/x"
    for bad in ({}, {"data": {"urls": {}}},
                {"data": {"urls": {"general": {}}}}):
        try:
            paddle.portal_url(bad)
            raise AssertionError(f"returned a URL for {bad!r}")
        except billing.BillingUnavailable:
            pass


def test_every_failure_path_raises_the_one_class_the_server_catches():
    """server.py catches BillingUnavailable and answers 502. Any OTHER
    exception is an unhandled 500 at the exact moment somebody is trying
    to pay. Found by running it: the first draft of these functions
    referenced the name without importing it, so every one of these paths
    raised NameError instead."""
    assert paddle.BillingUnavailable is billing.BillingUnavailable
    was = {k: os.environ.get(k) for k in
           (paddle.ENV_API_KEY, paddle.ENV_PRICE_ID)}
    try:
        os.environ[paddle.ENV_API_KEY] = ""
        os.environ[paddle.ENV_PRICE_ID] = ""
        for call in (lambda: paddle.start_checkout(1, "a@b", "https://x/"),
                     lambda: paddle.open_portal("ctm_1", "https://x/")):
            try:
                call()
                raise AssertionError("unconfigured call did not raise")
            except billing.BillingUnavailable:
                pass
    finally:
        for k, v in was.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_the_portal_is_paddles_page_and_we_do_not_build_a_cancel_flow():
    """A company that builds its own cancel flow is deciding how hard it
    is to leave. Cancelling happens on Paddle's page."""
    url, _h, body = paddle.portal_request("k", "ctm_77")
    assert "ctm_77" in url and url.endswith("/portal-sessions")
    assert body == b"{}", "the portal request sends account data it need not"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "engine", "paddle.py"), encoding="utf-8").read()
    assert "def cancel" not in src, "a homegrown cancel flow appeared"



# --- the server is actually wired to Paddle ---------------------------------
#
# The module can be perfect and unreachable. These read server.py, because
# the failure mode of a half-finished processor swap is a site that looks
# subscribed-capable and silently uses the dead one.

def _server() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return open(os.path.join(root, "server.py"), encoding="utf-8").read()


# --- and the wiring, which now points the other way --------------------------
#
# These five used to say "server.py must call PAY". Reversed on
# 2026-08-21, when Paddle turned out not to serve this business model and
# the Stripe account came back approved. They still exist, and still
# assert something worth asserting: that the swap is COMPLETE. A codebase
# with two live processors has two answers to "what grants access", and
# the second one is the one nobody is watching.


def _server():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "server.py"), encoding="utf-8") as fh:
        return fh.read()


def test_paddle_is_not_wired_to_anything():
    """No call path from the server reaches this module.

    Named per-call rather than checking for the string "paddle", because
    the honest mentions — a comment explaining why the module is still
    here — must not fail. This is the same trap that has bitten this repo
    repeatedly: a test that fires on the comment warning about the thing
    it checks for.
    """
    s = _server()
    for call in ("PAY.start_checkout(", "PAY.open_portal(",
                 "PAY.verify_signature(", "PAY.read_event(",
                 "PAY.configured()", "PAY.describe", "PAY.keys("):
        assert call not in s, (
            f"server.py still calls {call} — the processor swap is half "
            "done, and two things can grant entitlement")
    assert "from engine import paddle" not in s, \
        "server.py still imports paddle"


def test_the_webhook_reads_stripes_header_not_paddles():
    """One header, and it is the one the live processor sends.

    Reading the wrong one is not a loud failure. `headers.get` returns "",
    verification fails, and every real event is refused with a 400 —
    which looks from here like nobody is paying, and looks from Stripe's
    dashboard like our endpoint is broken.
    """
    s = _server()
    assert 'self.headers.get("Stripe-Signature")' in s
    assert 'self.headers.get("Paddle-Signature")' not in s, \
        "still reading Paddle's header"


def test_the_replay_guard_reads_the_field_stripe_actually_sends():
    """Stripe names the event `id`; Paddle named it `event_id`. Asking for
    the wrong one yields None, already_handled() treats a falsy id as
    "never seen", and the guard returns False for every event — switched
    off while still looking present. A retried checkout.session.completed
    is then a second grant.

    Both names are read, `id` first. That is not indecision: it costs
    nothing, and it means a replayed event is still caught if this ever
    swaps back.
    """
    s = _server()
    i = s.index("def _billing_webhook")
    body = s[i:i + 3000]
    assert 'payload.get("id")' in body, \
        "the replay guard does not read Stripe's field name"
    assert "already_handled" in body


def test_the_server_calls_stripe_for_money_and_billing_for_storage():
    """The split both modules were built around, pointing at Stripe.

    Stripe is unusual here in being BOTH halves — engine/billing.py holds
    the storage layer and the Stripe adapter — so this reads as one
    module where the Paddle version read as two. The split still exists,
    it is just internal, and tests/test_stripe_wiring.py checks the parts
    that must not blur.
    """
    s = _server()
    for call in ("BI.start_checkout(", "BI.open_portal(",
                 "BI.verify_signature(", "BI.read_event(",
                 "BI.live_mode("):
        assert call in s, f"server.py never calls {call}"
    for kept in ("BI.init(", "BI.apply_event(", "BI.status_for(",
                 "BI.already_handled("):
        assert kept in s, f"storage call {kept} disappeared in the swap"


def test_paused_is_still_handled_even_though_stripe_does_not_send_it():
    """`paused` is Paddle-only wording, and the row can still hold it.

    A subscription paused under Paddle and stored before the swap keeps
    that status in the database for ever. `entitled()` refuses it, which
    is right. What must not happen is the account page calling it "No
    subscription." — that tells somebody who deliberately paused that
    they have nothing.
    """
    assert not billing.entitled("paused"), \
        "a paused subscription would be treated as paying"
    assert "paused" in paddle.describe("paused").lower()
    assert "No subscription" not in paddle.describe("paused")


def test_the_secrets_template_has_swapped_back_too():
    """A template naming variables nothing reads is worse than none.

    Whoever sets up a fresh server follows this file. Left on Paddle it
    would have them fill in four keys the code never looks at, and then
    wonder why billing stayed off — with nothing failing, because unset
    billing is a supported state.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "secrets.local.example"),
              encoding="utf-8") as fh:
        tmpl = fh.read()
    for var in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
                "STRIPE_PRICE_MONTHLY", "STRIPE_PRICE_SIXMONTH",
                "STRIPE_PRICE_YEARLY"):
        assert f"\n{var}=" in tmpl, f"{var} is not in secrets.local.example"
    for var in (paddle.ENV_API_KEY, paddle.ENV_PRICE_ID,
                paddle.ENV_SANDBOX):
        assert f"\n{var}=" not in tmpl, \
            f"the template still asks for {var}, which nothing reads"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
