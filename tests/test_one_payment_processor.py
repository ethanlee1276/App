"""One payment processor, and it is Stripe.

These six checks lived at the bottom of tests/test_paddle.py. When
engine/paddle.py was retired (audit D-8 / remove-merge #3, roadmap #53 —
Paddle's own acceptable-use rules exclude this business, so the module
was never a working fallback), the module's own unit tests went with it
and these moved here unchanged: they assert the swap to Stripe is
COMPLETE, which matters more with the module gone, not less. The module
is recoverable from git history (the commit retiring it says which).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import billing                                     # noqa: E402

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
    # The sentence lives in billing.describe now (paddle.py retired, #53);
    # it is the function the account page actually calls.
    assert "paused" in billing.describe("paused").lower()
    assert "No subscription" not in billing.describe("paused")


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
    for var in ("PADDLE_API_KEY", "PADDLE_PRICE_ID", "PADDLE_SANDBOX"):
        assert f"\n{var}=" not in tmpl, \
            f"the template still asks for {var}, which nothing reads"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
