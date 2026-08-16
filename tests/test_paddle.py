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


def test_the_secrets_template_names_the_variables_the_code_reads():
    """A template that names the wrong variables is worse than none.

    It described Stripe for a day after the processor changed, so anyone
    following it on a fresh server would have filled in four keys the code
    never reads and then wondered why billing stayed switched off — with
    nothing failing, because unset billing is a supported state.

    Derived from the module's own ENV_ constants rather than typed twice.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "secrets.local.example"), encoding="utf-8") as fh:
        tmpl = fh.read()
    for var in (paddle.ENV_API_KEY, paddle.ENV_WEBHOOK_SECRET,
                paddle.ENV_PRICE_ID, paddle.ENV_SANDBOX):
        assert f"\n{var}=" in tmpl, f"{var} is not in secrets.local.example"
    assert "STRIPE_SECRET_KEY=" not in tmpl, \
        "the template still asks for Stripe keys nothing reads"
    # The VALUE must stay empty — the template is tracked in git, and
    # "every value here is blank" is the rule that stops a real key being
    # committed by someone who edited the template instead of their copy.
    # So the sandbox instruction lives in the prose above it instead.
    assert f"\n{paddle.ENV_SANDBOX}=\n" in tmpl, "the flag carries a value"
    i = tmpl.index(f"\n{paddle.ENV_SANDBOX}=")
    assert "SANDBOX=1" in tmpl[max(0, i - 700):i], \
        "nothing tells the reader to switch sandbox on first"



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


def test_the_webhook_reads_paddles_header_not_stripes():
    """A verifier pointed at a header that never arrives sees "" every
    time, fails every signature, and rejects every real event — which at
    least fails loudly. The same mistake in the other direction is what
    the tolerance checks above are for."""
    s = _server()
    assert 'self.headers.get("Paddle-Signature")' in s
    assert "Stripe-Signature" not in s, "still reading Stripe's header"


def test_the_replay_guard_reads_the_field_paddle_actually_sends():
    """Paddle names the event id `event_id`; Stripe names it `id`. Asking
    for the wrong one yields None, already_handled() treats a falsy id as
    "never seen", and the guard returns False for every event — switched
    off while still looking present. A retried subscription.created is
    then a second grant. Found by reading Paddle's payload shape against
    code that had been copied from the Stripe path."""
    s = _server()
    i = s.index("def _billing_webhook")
    body = s[i:i + 3000]
    assert 'payload.get("event_id")' in body, \
        "the replay guard reads Stripe's field name and never fires"
    assert "already_handled" in body


def test_the_server_calls_paddle_for_money_and_billing_only_for_storage():
    """The split the two modules were built around. Storage (init,
    apply_event, status_for, already_handled) is provider-neutral and
    stays in billing; anything that talks to a processor or verifies its
    signature must come from paddle, or the swap is cosmetic."""
    s = _server()
    for call in ("PAY.start_checkout(", "PAY.open_portal(",
                 "PAY.verify_signature(", "PAY.read_event(",
                 "PAY.configured()"):
        assert call in s, f"server.py never calls {call}"
    for dead in ("BI.start_checkout(", "BI.open_portal(",
                 "BI.verify_signature(", "BI.read_event(",
                 "BI.live_mode("):
        assert dead not in s, f"server.py still uses the Stripe path {dead}"
    # …and the storage half is still the shared one.
    for kept in ("BI.init(", "BI.apply_event(", "BI.status_for(",
                 "BI.already_handled("):
        assert kept in s, f"storage call {kept} disappeared in the swap"


def test_the_status_card_uses_paddles_wording_for_paddles_statuses():
    """`paused` is Paddle-only. billing.describe has never heard of it and
    falls through to "No subscription." — telling somebody who chose to
    pause that they have nothing. status_for takes the processor's
    describe for exactly this."""
    s = _server()
    assert "describe_with=PAY.describe" in s, \
        "the account card would call a paused subscription 'none'"
    assert "paused" in paddle.describe("paused").lower()
    assert "No subscription" not in paddle.describe("paused")


def test_no_stripe_environment_variable_is_still_being_read():
    """A leftover STRIPE_* lookup is a config the deploy notes no longer
    mention, so it reads as unset for ever and takes a code path nobody
    tests."""
    s = _server()
    assert "STRIPE_" not in s, "server.py still reads a Stripe env var"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmpl = open(os.path.join(root, "secrets.local.example"),
                encoding="utf-8").read()
    assert "STRIPE_" not in tmpl, "the secrets template still offers Stripe"



if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
