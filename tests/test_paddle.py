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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
