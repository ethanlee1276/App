"""Answering "is the Stripe review over?" with a fact instead of a guess.

Ethan, 2026-08-25: "how do we know when the review of our site is over so
we can start displaying everything our site offers... Pretty sure my
stripe account is verified."

NOTHING ON THIS SITE COULD ANSWER THAT, which is the whole finding.
`preflight()` checked the CONFIGURATION — is a key set, does the product
exist, are the three prices wired — and every one of those can be perfect
while the account itself is still pending. So "pretty sure" was the best
answer available, and it is the wrong confidence to hold when the thing
you are deciding is whether to change what a reviewer sees. The comment
on EXTERNAL_MARKET_LINKS is blunt about the downside: a feature a
reviewer discovers that we did not mention "is how accounts get
terminated with a reserve held".

Stripe answers it directly, so now we ask.

WHY `reviewed` IS STRICT. It requires charges AND payouts AND an empty
requirements list AND no disabled_reason. charges_enabled goes true on
its own while payouts are still held — from outside that looks exactly
like approval, and it is the state where money arrives and cannot leave.
An "approved" that can be true during a payout hold is not a check, it
is a coin flip with extra steps.

Run directly: `python3 tests/test_review_status.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import billing as BI                             # noqa: E402
from engine import stripeset as SS                           # noqa: E402

KEY = "sk_live_THIS_MUST_NEVER_APPEAR_IN_OUTPUT"


class _Stub:
    """Stands in for Stripe, and records what it was handed."""

    def __init__(self, payload):
        self.payload = payload
        self.seen = []

    def __call__(self, url, secret_key, *a, **kw):
        self.seen.append((url, secret_key))
        return self.payload


def _with_account(payload, fn):
    real_get, real_live = BI._get, BI.live_mode
    stub = _Stub(payload)
    BI._get, BI.live_mode = stub, (lambda k: True)
    try:
        return fn(), stub
    finally:
        BI._get, BI.live_mode = real_get, real_live


def _preflight_body():
    """preflight() is the LAST function in the file, so slicing to the
    next `\ndef ` raised rather than failing an assertion — a test
    breaking on its own reader instead of on the code."""
    src = open(os.path.join(ROOT, "engine", "stripeset.py"),
               encoding="utf-8").read()
    i = src.index("def preflight(")
    j = src.find("\ndef ", i + 1)
    return src[i:] if j < 0 else src[i:j]


APPROVED = {
    "id": "acct_123", "charges_enabled": True, "payouts_enabled": True,
    "requirements": {"currently_due": [], "past_due": [],
                     "pending_verification": [], "disabled_reason": None},
}


def test_a_clean_account_reads_as_approved():
    st, _ = _with_account(APPROVED, lambda: SS.account_status(KEY))
    assert st["reviewed"] is True
    assert st["charges_enabled"] and st["payouts_enabled"]
    assert st["account"] == "acct_123"


def test_charges_without_payouts_is_not_approval():
    """The state that looks like approval from outside: money arrives and
    cannot leave."""
    payload = dict(APPROVED, payouts_enabled=False)
    st, _ = _with_account(payload, lambda: SS.account_status(KEY))
    assert st["reviewed"] is False, \
        "a payout hold is being reported as a finished review"
    ok, _head, detail = SS.review_verdict(st)
    assert ok is False and "payouts are not enabled" in detail


def test_an_outstanding_requirement_is_not_approval():
    payload = dict(APPROVED, requirements={
        "currently_due": ["business_profile.url", "company.tax_id"],
        "past_due": [], "pending_verification": [], "disabled_reason": None})
    st, _ = _with_account(payload, lambda: SS.account_status(KEY))
    assert st["reviewed"] is False
    _ok, _head, detail = SS.review_verdict(st)
    assert "business_profile.url" in detail, \
        "the verdict does not say WHAT Stripe is still waiting for"


def test_a_disabled_reason_is_not_approval():
    payload = dict(APPROVED, requirements={
        "currently_due": [], "past_due": [], "pending_verification": [],
        "disabled_reason": "requirements.pending_verification"})
    st, _ = _with_account(payload, lambda: SS.account_status(KEY))
    assert st["reviewed"] is False
    _ok, _head, detail = SS.review_verdict(st)
    assert "pending_verification" in detail


def test_a_long_requirement_list_is_summarised_not_dumped():
    payload = dict(APPROVED, requirements={
        "currently_due": [f"field_{i}" for i in range(20)],
        "past_due": [], "pending_verification": [], "disabled_reason": None})
    st, _ = _with_account(payload, lambda: SS.account_status(KEY))
    _ok, _head, detail = SS.review_verdict(st)
    assert "+14 more" in detail, "a twenty-item list is printed in full"


def test_the_approved_verdict_names_the_flag_and_what_it_changes():
    """A check that says "you're clear" and stops leaves you where you
    started. It has to name the next action."""
    st, _ = _with_account(APPROVED, lambda: SS.account_status(KEY))
    ok, head, detail = SS.review_verdict(st)
    assert ok is True and "review is over" in head
    assert "EXTERNAL_MARKET_LINKS" in detail, \
        "the verdict does not say what to turn on"
    for thing in ("polymarket", "chart"):
        assert thing in detail.lower(), \
            f"the verdict does not say the {thing} comes back"


def test_the_pending_verdict_says_to_leave_the_flag_alone():
    payload = dict(APPROVED, charges_enabled=False)
    st, _ = _with_account(payload, lambda: SS.account_status(KEY))
    _ok, _head, detail = SS.review_verdict(st)
    assert "Leave EXTERNAL_MARKET_LINKS false" in detail


# --- the rule this repo does not bend ------------------------------------

def test_the_key_never_appears_in_anything_this_returns():
    """A key in a traceback is a key in a log file, and this command is
    meant to be run over ssh and screenshotted."""
    st, stub = _with_account(APPROVED, lambda: SS.account_status(KEY))
    assert stub.seen and stub.seen[0][1] == KEY, "the stub was not called"
    blob = repr(st) + "".join(str(x) for x in SS.review_verdict(st))
    assert KEY not in blob, "the secret key is in the status output"
    assert "sk_live" not in blob and "sk_test" not in blob


def test_preflight_reports_the_account_before_the_configuration():
    """Order matters: every configuration check below it can be perfect
    while the account is still pending."""
    body = _preflight_body()
    assert "account_status(sk)" in body, \
        "preflight no longer checks whether the account is clear"
    assert body.index("account_status(sk)") < body.index("find_product(sk)"), \
        "the account check sank below the configuration checks"


def test_an_unreachable_stripe_is_not_reported_as_a_bad_account():
    """"We could not check" and "you are rejected" send you to different
    places for an hour."""
    body = _preflight_body()
    j = body.index("account_status(sk)")
    seg = body[j:j + 700]
    assert "except Exception" in seg, \
        "a failed read from Stripe now crashes the whole preflight"
    assert "Could not reach Stripe" in seg


def test_preflight_still_runs_with_no_key_at_all():
    """A developer with no key must still get the configuration report
    rather than a crash."""
    saved = {k: os.environ.pop(k, None)
             for k in (BI.ENV_SECRET, "QB_ENV_FILE")}
    os.environ["QB_ENV_FILE"] = os.path.join(ROOT, "no-such-env-file")
    try:
        checks = SS.preflight()
    finally:
        os.environ.pop("QB_ENV_FILE", None)
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    assert checks and any("is not set" in h for _ok, h, _d in checks)
    assert not any("review is over" in h for _ok, h, _d in checks), \
        "an account with no key was reported as approved"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
