"""A cancelled trial ends its access at once, and the account never gets a second trial.

Ethan, 2026-11-02, after a trial that was cancelled on Stripe's page and never
charged: "If someone cancels the trial, there account needs to be deleted or
we take access from that account and we DO NOT offer a second trial for that
account".

Access is taken, not the account: deleting it would delete the subscription
row the one-trial rule reads, and the same address could sign up again and
start a second trial (engine/billing TRIAL_CANCEL_ENDS_ACCESS_FROM). These
hold:

  * a trial started from 2 November 2026 that its member cancels is walled
    the moment we hear of it (Stripe's webhook, or our own read of Stripe,
    which builds the same event) and the account page says so; changing
    their mind in the portal gives the trial back;
  * a trial started before that keeps the rule it started under (access to
    the end of the trial), and a paid plan cancelled to its period end keeps
    the days paid for;
  * the account is never given or offered a second trial;
  * the owner's desk no longer counts it as a trial;
  * the plans card, the checkout, the FAQ, the reminder email and its phone
    version, the Live tab and the Terms all say what cancelling a trial does.

Run directly: `python3 tests/test_a_cancelled_trial_ends_at_once.py`
"""
import os
import re
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from engine import accounts as A      # noqa: E402
from engine import billing as B       # noqa: E402
from engine import ownerdesk as OD    # noqa: E402
from _app import app_js               # noqa: E402  (app.js and the rooms it loads on first use)

DAY = 86400
RULE = B.TRIAL_CANCEL_ENDS_ACCESS_FROM


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _db():
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    B.init(conn)
    _code, who = A.create_user(conn, "trial@example.com", "correct-horse-battery", confirmed=True)
    return conn, who["id"]


def _apply(conn, kind, obj):
    return B.apply_event(conn, B.read_event({"type": kind, "data": {"object": obj}}))


def _trial(conn, uid, started, ends, cancel=False):
    """A monthly trial as Stripe tells it: the checkout, then the subscription."""
    _apply(conn, "checkout.session.completed", {
        "client_reference_id": str(uid), "customer": "cus_T1", "subscription": "sub_T1",
        "payment_status": "no_payment_required", "metadata": {"plan": "monthly"}})
    _apply(conn, "customer.subscription.updated", {
        "id": "sub_T1", "customer": "cus_T1", "status": "trialing", "metadata": {"plan": "monthly"},
        "start_date": started, "trial_end": ends, "cancel_at_period_end": cancel,
        "items": {"data": [{"current_period_end": ends}]}})


def test_the_rule_in_five_cases():
    now = time.time()
    new, old = max(now, RULE) - 3600, RULE - DAY
    assert B.entitled("trialing", now + 2 * DAY, now=now, cancel_at_end=False, started_at=new), "a running trial"
    assert not B.entitled("trialing", now + 2 * DAY, now=now, cancel_at_end=True, started_at=new), "cancelled: walled"
    assert not B.entitled("trialing", now + 2 * DAY, now=now, cancel_at_end=True), "no start known: the new rule"
    assert B.entitled("trialing", now + DAY, now=now, cancel_at_end=True, started_at=old), \
        "a trial started before the rule keeps access to its end"
    assert not B.entitled("trialing", now - 1, now=now, cancel_at_end=True, started_at=old), "…and no further"
    assert B.entitled("active", now + 20 * DAY, now=now, cancel_at_end=True, started_at=new), \
        "a paid plan keeps the days paid for"
    assert B.trial_cancel_walls("trialing", True, new) and not B.trial_cancel_walls("active", True, new)
    assert not B.trial_cancel_walls("trialing", False, new) and not B.trial_cancel_walls("trialing", True, old)


def test_a_trial_cancelled_from_today_is_walled_at_once_and_says_so():
    conn, uid = _db()
    started = max(time.time(), RULE) - 3600
    _trial(conn, uid, started, time.time() + 2 * DAY)
    st = B.status_for(conn, uid)
    assert st["status"] == "trialing" and st["entitled"] is True, st
    # Cancelled on Stripe's page: Stripe keeps it `trialing`, set to cancel.
    _apply(conn, "customer.subscription.updated", {
        "id": "sub_T1", "customer": "cus_T1", "status": "trialing", "start_date": started,
        "cancel_at_period_end": True, "items": {"data": [{"current_period_end": time.time() + 2 * DAY}]}})
    st = B.status_for(conn, uid)
    assert st["cancel_at_end"] is True and st["entitled"] is False, st
    assert st["note"].startswith("Trial cancelled — nothing will be charged"), st["note"]
    assert "access ended when you cancelled" in st["note"] and "had its free trial" in st["note"]
    # Changed their mind in the portal before the trial ended: it is theirs again.
    _apply(conn, "customer.subscription.updated", {
        "id": "sub_T1", "customer": "cus_T1", "status": "trialing", "start_date": started,
        "cancel_at_period_end": False, "cancel_at": None,
        "items": {"data": [{"current_period_end": time.time() + 2 * DAY}]}})
    assert B.status_for(conn, uid)["entitled"] is True


def test_a_trial_started_before_the_rule_keeps_its_days():
    conn, uid = _db()
    _trial(conn, uid, RULE - DAY, time.time() + DAY, cancel=True)
    st = B.status_for(conn, uid)
    assert st["entitled"] is True and st["note"].startswith("Cancelled — access until"), st


def test_the_account_is_never_given_or_offered_a_second_trial():
    conn, uid = _db()
    assert B.trial_days_for("monthly", not B.has_subscribed_before(conn, uid)) == B.TRIAL_DAYS, "a first trial"
    _trial(conn, uid, max(time.time(), RULE), time.time() + 2 * DAY, cancel=True)
    _apply(conn, "customer.subscription.deleted", {"id": "sub_T1", "customer": "cus_T1", "status": "canceled"})
    assert B.status_for(conn, uid)["entitled"] is False
    assert B.has_subscribed_before(conn, uid) is True
    assert B.trial_days_for("monthly", not B.has_subscribed_before(conn, uid)) == 0, "no second trial"
    srv = _read("server.py")
    assert 'out["trial_eligible"] = not BI.has_subscribed_before(' in srv, "the plans page is told"
    assert "fresh = not BI.has_subscribed_before(conn, who[\"id\"])" in srv and \
        "trial = BI.trial_days_for(plan, fresh)" in srv, "and checkout decides from the database"


def test_the_desk_no_longer_counts_it_as_a_trial():
    conn, uid = _db()
    _trial(conn, uid, max(time.time(), RULE), time.time() + 2 * DAY)
    assert OD.money(conn)["trialing"] == 1
    conn.execute("UPDATE subscriptions SET cancel_at_end = 1 WHERE user_id = ?", (uid,))
    conn.commit()
    assert OD.money(conn)["trialing"] == 0


def _flat(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_everything_that_offers_or_reminds_says_what_cancelling_does():
    acct = _read("web", "js", "account.js")
    assert "which ends the trial’s access at once" in acct, "the plans card, before the click"
    assert "it ends the trial’s access at once" in acct and "the account cannot start another trial" in acct, "the FAQ"
    assert "trial’s access ends when you cancel" in _flat(app_js()), "the checkout's note"
    assert "its access ends when you cancel" in _read("web", "js", "chat.js"), "the Live tab's trial line"
    note = _read("engine", "trialnote.py")
    assert "access ends when you cancel" in note and "cannot start another trial" in note, "the reminder email"
    assert "its access ends when you cancel" in _read("engine", "lifecycle.py"), "its phone version"
    terms = _read("web", "terms.html")
    assert "Last updated 2 November 2026" in terms
    flat = _flat(terms)
    assert "If you cancel during the trial, its access ends when you cancel" in flat, "Terms §5.3"
    assert "The changes of 2 November 2026" in flat and "a trial started earlier keeps the rule it started under" in flat
    assert "One trial per person" in flat


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
