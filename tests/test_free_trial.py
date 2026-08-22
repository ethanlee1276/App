"""There is no free plan, and there is a 3-day trial on the $25 plan.

Ethan, 2026-08-22: *"what exactly is the free plan? i didnt see it on the
site or when i went to buy a plan on the site … we should completly get rid
of the free plan and only have the paid plans. if anything we can offer a
3 day free trial only for the $25 plan."*

WHAT THE FREE PLAN WAS. A card on the ACCOUNT page — which is why he never
saw it while buying — headed "Free / $0 always", listing the Record page,
scores, standings, rosters, injuries, the fantasy room and the bet log as
things you got for nothing. Every one of those is behind the wall:
WALL_OPEN lets an unpaid reader reach the Record page and the account page
and nothing else. It was describing a tier the site does not grant, on the
page a customer reads after paying.

THE TRIAL, AND WHY IT IS WRITTEN OUT EVERYWHERE. It takes a card and
converts to $25 automatically on day 4. A trial that collects a card and
starts charging quietly is the most complained-about pattern in
subscriptions and several states legislate against it by name. So the
conversion — card required, what it becomes, when, and how to stop it —
appears on the plan card, on the checkout page, in the FAQ and in Terms
§5.3. This file checks all four, because the one that gets forgotten is
the one a chargeback quotes.

WHO DECIDES. The server, from the database. `trial_days` is never read off
a request body: a trial length the browser can set is a free subscription
for anyone who opens the network tab. And one per account — otherwise
"cancel on day two, resubscribe on day four" is a permanently free site.

    python3 tests/test_free_trial.py
"""

import os
import re
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import billing as BI                            # noqa: E402

APP = os.path.join(ROOT, "web", "js", "app.js")
TERMS = os.path.join(ROOT, "web", "terms.html")
SERVER = os.path.join(ROOT, "server.py")


def _read(p):
    return open(p, encoding="utf-8").read()


def _code(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    BI.init(conn)
    return conn, path


# --- the free plan is gone --------------------------------------------------
def test_no_page_offers_a_free_plan():
    app = _code(_read(APP))
    for phrase in ('"Free"', ">Free<", "$0<span>always",
                   "Everything in Free", "free half is free forever"):
        assert phrase not in app, "a free plan survives: %r" % phrase


def test_nothing_advertises_the_walled_pages_as_free():
    """The specific lie: the card listed pages the wall refuses. Whatever
    a page says is included has to be something an unpaid reader can
    actually reach."""
    app = _code(_read(APP))
    m = re.search(r"const WALL_OPEN = \[([^\]]*)\]", app)
    openable = set(re.findall(r'"([a-z]+)"', m.group(1)))
    assert "record" in openable
    for shut in ("standings", "rosters", "injuries", "fantasy", "mybets",
                 "bankroll"):
        assert shut not in openable, (
            "%s is reachable unpaid; if that is deliberate this test needs "
            "updating, and so does whatever page says it is not" % shut)


def test_the_account_page_still_says_what_a_subscription_costs():
    """Removing the free card must not remove the price list with it."""
    app = _read(APP)
    body = app[app.index("function billPlansHTML("):]
    body = body[:body.index("\n}\n")]
    assert "$25" in body
    assert "billSeePlans()" in body, "no way through to the plans page"


# --- who gets a trial -------------------------------------------------------
def test_only_the_monthly_plan_has_one():
    assert BI.TRIAL_PLAN == "monthly"
    assert BI.trial_days_for("monthly", True) == BI.TRIAL_DAYS
    for other in ("sixmonth", "yearly", "", None, "nonsense"):
        assert BI.trial_days_for(other, True) == 0, other


def test_it_is_three_days():
    assert BI.TRIAL_DAYS == 3


def test_somebody_who_has_subscribed_before_does_not_get_another():
    """Otherwise cancel-and-resubscribe is a permanently free account."""
    conn, path = _db()
    try:
        assert BI.has_subscribed_before(conn, 1) is False
        BI.apply_event(conn, {"user_id": 1, "customer_id": "cus_A",
                              "subscription_id": "sub_A", "status": "canceled",
                              "period_end": None, "plan": "monthly"})
        assert BI.has_subscribed_before(conn, 1) is True, (
            "a cancelled subscriber is offered a fresh trial")
        assert BI.trial_days_for("monthly", False) == 0
        # …and a different account is unaffected.
        assert BI.has_subscribed_before(conn, 2) is False
    finally:
        os.unlink(path)


def test_a_broken_lookup_refuses_the_trial_rather_than_granting_it():
    """Refusing costs a conversion. Granting to everybody costs the first
    month of every subscription on the site."""
    class Broken:
        def execute(self, *a, **kw):
            raise sqlite3.OperationalError("no such table")
    assert BI.has_subscribed_before(Broken(), 1) is True


def test_the_length_is_never_taken_from_the_request():
    """THE WHOLE CHECKOUT BLOCK, not a fixed slice forward from the call.
    This read 260 characters after `trial_days_for(` and broke the moment
    the eligibility lookup moved onto its own line above it — a passing
    test turning red for a change that did not touch its subject. The
    claim is about the handler, so the handler is what it reads."""
    src = _read(SERVER)
    block = src[src.index('if path == "checkout":'):]
    block = block[:block.index("else:")]
    assert "BI.trial_days_for(" in block
    assert "body.get" not in block.split("BI.trial_days_for(")[1], (
        "the trial length comes from the request body — anybody can edit "
        "that and give themselves a year")
    assert "has_subscribed_before" in block, (
        "eligibility is no longer decided from the database")


def test_the_checkout_body_carries_the_trial_only_when_there_is_one():
    import urllib.parse as up

    def field(body, name):
        """Read it back the way Stripe will: form-decoded. The brackets
        are percent-encoded on the wire like every other nested field, so
        grepping the raw bytes for `trial_period_days=3` looks for a
        string that is correctly not there."""
        return dict(up.parse_qsl(body.decode())).get(name)

    _u, _h, with_trial = BI.checkout_request(
        "sk_test_x", "price_m", 7, "a@b.c", "https://s/", "https://c/",
        "monthly", trial_days=3)
    assert field(with_trial, "subscription_data[trial_period_days]") == "3"
    # And the rest of the body survived being appended to.
    assert field(with_trial, "mode") == "subscription"
    assert field(with_trial, "client_reference_id") == "7"
    assert field(with_trial, "metadata[plan]") == "monthly"

    _u, _h, without = BI.checkout_request(
        "sk_test_x", "price_y", 7, "a@b.c", "https://s/", "https://c/",
        "yearly", trial_days=0)
    assert field(without, "subscription_data[trial_period_days]") is None


def test_a_trial_still_entitles_and_still_has_a_sentence():
    assert "trialing" in BI.ENTITLED, (
        "a trialing subscriber cannot read the boards they are trialling")
    assert "trial" in BI.describe("trialing").lower()


# --- what the reader is told ------------------------------------------------
def _trial_copy():
    """Everything on the paywall and checkout that mentions the trial."""
    app = _read(APP)
    out = []
    for fn in ("paywallHTML", "checkoutHTML", "faqFor"):
        i = app.index("function " + fn + "(")
        out.append(app[i:app.index("\n}\n", i)])
    return "\n".join(out)


def test_the_card_says_a_card_is_required():
    copy = _trial_copy()
    assert re.search(r"[Cc]ard (is )?(required|taken)", copy), (
        "the trial does not say it takes a card, which is the part that "
        "surprises people")


def test_the_copy_says_what_it_becomes_and_when():
    copy = _trial_copy()
    assert "$${pl.price} a month" in copy or "a month" in copy
    assert re.search(r"day \$?\{?\s*(trialDays|tDays|days)\s*\+\s*1", copy), (
        "nothing states the day the charge lands")


def test_the_copy_says_how_to_stop_it():
    copy = _trial_copy()
    assert "cancel" in copy.lower()
    assert "account page" in copy.lower()


def test_the_offer_is_not_shown_to_somebody_who_cannot_have_it():
    """A card promising three days that checkout then refuses is worse
    than no offer."""
    for fn in ("paywallHTML", "checkoutHTML", "faqFor", "billPlansHTML"):
        app = _read(APP)
        i = app.index("function " + fn + "(")
        body = _code(app[i:app.index("\n}\n", i)])
        assert "trial_eligible" in body, (
            "%s advertises the trial without checking eligibility" % fn)


def test_the_client_never_invents_a_trial_the_server_did_not_offer():
    app = _code(_read(APP))
    assert "trial_days" in app
    # No hardcoded 3 driving the offer.
    assert not re.search(r"trialDays\s*=\s*3\b", app)
    assert not re.search(r"tDays\s*=\s*3\b", app)


# --- the binding version ----------------------------------------------------
def test_the_terms_describe_the_trial_in_full():
    # Whitespace-normalised and tag-stripped: this is prose in HTML, so
    # every phrase below is liable to wrap mid-sentence or carry a <b>
    # through the middle of it, and searching the raw source finds
    # nothing while the page says exactly the right thing.
    t = _read(TERMS)
    i = t.index("Free trial")
    section = re.sub(r"<[^>]+>", " ", t[i:i + 3200])
    section = re.sub(r"\s+", " ", section)
    for needed, why in (
            ("3-day", "the length"),
            ("monthly plan only", "which plan it applies to"),
            ("One trial per account", "that it is not repeatable"),
            ("payment method is required", "that a card is taken"),
            ("charged automatically", "that it converts on its own"),
            ("$25", "what it converts to"),
            ("day 4", "when"),
            ("charged nothing at all", "what happens if you cancel in time")):
        assert needed in section, "Terms §5.3 does not state %s" % why


def test_the_terms_section_numbers_do_not_collide():
    t = _read(TERMS)
    nums = re.findall(r"<h3>(\d+\.\d+)\s", t)
    assert len(nums) == len(set(nums)), (
        "duplicate section numbers: %s"
        % [n for n in nums if nums.count(n) > 1])


def test_the_site_and_the_terms_agree_the_trial_is_monthly_only():
    t = _read(TERMS)
    assert "6-month and yearly plans have no trial" in t
    assert BI.TRIAL_PLAN == "monthly"


def test_the_auto_renewal_answer_is_not_a_promise_we_do_not_keep():
    """It used to say "Nothing auto-renews without telling you first",
    which was never true of an ordinary subscription and is emphatically
    untrue of a trial that converts on day 4."""
    app = _read(APP)
    assert "auto-renews without telling you first" not in app


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
