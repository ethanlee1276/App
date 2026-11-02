"""A charge that does not go through tells the member, once; the trial's last-day notice says so first.

Ethan, 2026-11-02: "we set an alert or something to send them on their
third day to let them know that their trial will be canceled if they don't
pay". The trial takes a card up front and charges it when the three days
are up (Terms §5.3). What these hold:

  * the day-before notice (engine/trialnote's email and its phone twin in
    engine/lifecycle) lands on the trial's third day and says what happens:
    the charge, that a charge that does not go through pauses access, and
    that cancelling costs nothing and ends the trial's access;
  * a charge that fails — the trial's first, from Stripe's webhook or our
    own read of Stripe, or a renewal — is marked on the move into
    `past_due`/`unpaid` (engine/billing.apply_event), and the member hears
    once, by phone and by email, that access is paused and how to fix it;
  * the same failure is never told twice, however often Stripe repeats it;
    a renewal that fails after the card was fixed is a new failure, told;
  * a failure older than FAIL_FRESH_S, or one from before the mark existed,
    is left to the account page and the paywall;
  * an email that fails is tried again; no relay and no phone marks
    nothing; the address never goes in a log line;
  * the billing sweep runs it (one caller), and the Privacy Policy names
    what it keeps.

Run directly: `python3 tests/test_a_failed_charge_tells_the_member.py`
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import accounts as A                                  # noqa: E402
from engine import billing as BI                                  # noqa: E402
from engine import lifecycle as LC                                # noqa: E402
from engine import pushalerts as PA                               # noqa: E402
from engine import pushmine as PM                                 # noqa: E402
from engine import trialnote as TN                                # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
ET = ZoneInfo("America/New_York")
HOUR, DAY = 3600.0, 86400.0
NOW = dt.datetime(2026, 11, 2, 14, 0, tzinfo=ET).timestamp()      # Monday 2 p.m. Eastern
QUIET = lambda *_: None                                           # noqa: E731
SITE = "https://example.com"


def _db(d):
    conn = A.connect(Path(d) / "a.db")
    BI.init(conn)
    PA.ensure_tables(conn)
    PM.ensure_tables(conn)
    LC.ensure_tables(conn)
    return conn


def _trialist(conn, email, ends_in=-HOUR, plan="monthly"):
    """An account whose three-day monthly trial ends `ends_in` from NOW (the
    checkout and the subscription, as Stripe tells them)."""
    began = NOW + ends_in - BI.TRIAL_DAYS * DAY
    cur = conn.execute("INSERT INTO users (email, verifier, created_at, age_confirmed, terms_accepted_at) "
                       "VALUES (?, 'x', ?, 1, ?)", (email, began, began))
    uid = int(cur.lastrowid)
    conn.commit()
    _apply(conn, "checkout.session.completed", {
        "client_reference_id": str(uid), "customer": f"cus_{uid}", "subscription": f"sub_{uid}",
        "payment_status": "no_payment_required", "metadata": {"plan": plan}}, at=began)
    _apply(conn, "customer.subscription.updated", {
        "id": f"sub_{uid}", "customer": f"cus_{uid}", "status": "trialing", "metadata": {"plan": plan},
        "start_date": began, "trial_end": NOW + ends_in, "cancel_at_period_end": False,
        "items": {"data": [{"current_period_end": NOW + ends_in}]}}, at=began)
    return uid


def _apply(conn, kind, obj, at):
    return BI.apply_event(conn, BI.read_event({"type": kind, "created": at, "data": {"object": obj}}))


def _fail(conn, uid, at):
    """Stripe could not take the money: the invoice event, then the
    subscription's own (both say past_due; Stripe sends both)."""
    _apply(conn, "invoice.payment_failed", {"customer": f"cus_{uid}", "subscription": f"sub_{uid}"}, at=at)
    _apply(conn, "customer.subscription.updated", {
        "id": f"sub_{uid}", "customer": f"cus_{uid}", "status": "past_due",
        "items": {"data": [{"current_period_end": at + 30 * DAY}]}}, at=at + 1)


def _phone(conn, uid):
    code, out = PA.subscribe(conn, f"{uid:02d}" * 16, kind="apns", user_id=uid, topics=["posted"])
    assert code == 200, out


def _queued(conn, uid):
    return [tuple(r) for r in conn.execute(
        "SELECT id, title, body, url FROM push_mine WHERE user_id = ? AND kind = 'account' ORDER BY at", (uid,))]


def test_the_third_day_notice_says_what_a_failed_charge_does():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _trialist(conn, "trial@example.com", ends_in=20 * HOUR)
        _phone(conn, uid)
        # A day before a three-day trial ends is its third day.
        began = conn.execute("SELECT started_at FROM subscriptions WHERE user_id = ?", (uid,)).fetchone()[0]
        assert 2 * DAY <= NOW - began < 3 * DAY and TN.REMIND_WITHIN_S == DAY and BI.TRIAL_DAYS == 3
        box = []
        assert TN.run(conn, send=lambda *a: box.append(a), now=NOW, site=SITE, log=QUIET) == 1
        (to, subject, text, html), = box
        assert to == "trial@example.com" and subject == "Your free trial ends tomorrow"
        assert "charged $25.00 for the Monthly plan" in text
        assert "If that charge does not go through, the trial is over and your access pauses until you " \
               "update your card on your account page." in text
        assert "Cancel before the trial ends and you are charged nothing" in text and \
               "the account cannot start another trial" in text
        (_id, title, body, url), = _queued(conn, uid)
        assert title.startswith("Your free trial ends") and "$25 is charged to your card" in body
        assert "if it does not go through, access pauses until you update the card" in body
        assert "its access ends when you cancel" in body and len(body) <= 240 and url == "/#account"


def test_a_failed_first_charge_is_marked_and_told_once_by_phone_and_email():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _trialist(conn, "trial@example.com")
        _phone(conn, uid)
        _fail(conn, uid, at=NOW - 10 * 60)
        st, failed_at, was = conn.execute(
            "SELECT status, failed_at, failed_from FROM subscriptions WHERE user_id = ?", (uid,)).fetchone()
        assert st == "past_due" and was == "trialing", (st, was)
        assert abs(failed_at - (NOW - 10 * 60)) < 1, "when Stripe made the event, not the second one"
        assert BI.status_for(conn, uid)["entitled"] is False, "walled at once, as before"
        box = []
        assert LC.payment_failed(conn, now=NOW, send=lambda *a: box.append(a), site=SITE, log=QUIET) == 1
        (to, subject, text, html), = box
        assert to == "trial@example.com"
        assert subject == "Your trial ended, and the charge did not go through"
        assert "has ended, and the first charge for the Monthly plan did not go through, so your access is paused." in text
        assert "press Manage billing and update your card" in text and "opens again as soon as the payment clears" in text
        assert "If the card is not updated, the membership ends." in text and "cannot start another" in text
        assert "$" not in text, "no amount: a discount can make the charge differ from the price"
        assert f"{SITE}/#account" in text and f'href="{SITE}/#account"' in html
        (mid, title, body, url), = _queued(conn, uid)
        assert mid == f"account:payfail:{int(failed_at)}" and title == subject and url == "/#account"
        assert body.startswith("Your access is paused.") and "Manage billing" in body
        # Stripe repeats itself (a retry, the subscription event, our own read): never a second notice.
        _apply(conn, "invoice.payment_failed", {"customer": f"cus_{uid}", "subscription": f"sub_{uid}"}, at=NOW + HOUR)
        assert LC.payment_failed(conn, now=NOW + 2 * HOUR, send=lambda *a: box.append(a), site=SITE, log=QUIET) == 0
        assert len(box) == 1 and len(_queued(conn, uid)) == 1


def test_our_own_read_of_stripe_marks_it_the_same():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _trialist(conn, "trial@example.com")
        sub = {"id": f"sub_{uid}", "customer": f"cus_{uid}", "status": "past_due",
               "items": {"data": [{"current_period_end": NOW + 30 * DAY}]}}
        assert BI.refresh(conn, uid, now=NOW, fetch=lambda sid: sub, every=0) is True
        assert conn.execute("SELECT failed_from FROM subscriptions WHERE user_id = ?", (uid,)).fetchone()[0] == "trialing"
        box = []
        assert LC.payment_failed(conn, now=NOW + 60, send=lambda *a: box.append(a), site=SITE, log=QUIET) == 1


def test_a_renewal_that_fails_after_the_card_was_fixed_is_told_again():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _trialist(conn, "member@example.com", ends_in=-31 * DAY)
        _fail(conn, uid, at=NOW - 30 * DAY)
        box = []
        LC.payment_failed(conn, now=NOW - 30 * DAY + 60, send=lambda *a: box.append(a), site=SITE, log=QUIET)
        assert len(box) == 1
        # The card is updated and the invoice paid: active again.
        _apply(conn, "customer.subscription.updated", {
            "id": f"sub_{uid}", "customer": f"cus_{uid}", "status": "active",
            "items": {"data": [{"current_period_end": NOW + 60}]}}, at=NOW - 29 * DAY)
        assert BI.status_for(conn, uid)["entitled"] is True
        # A month later the renewal fails: a new failure, a renewal's words.
        _fail(conn, uid, at=NOW)
        assert conn.execute("SELECT failed_from FROM subscriptions WHERE user_id = ?", (uid,)).fetchone()[0] == "active"
        assert LC.payment_failed(conn, now=NOW + 60, send=lambda *a: box.append(a), site=SITE, log=QUIET) == 1
        assert box[-1][1] == "Your payment did not go through"
        assert "The charge for your Monthly plan of Qellys Book did not go through" in box[-1][2]
        assert "free trial" not in box[-1][2]


def test_an_old_failure_or_one_from_before_the_mark_is_left_to_the_page():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        old = _trialist(conn, "old@example.com", ends_in=-5 * DAY)
        _fail(conn, old, at=NOW - LC.FAIL_FRESH_S - HOUR)
        before = _trialist(conn, "before@example.com")
        conn.execute("UPDATE subscriptions SET status = 'past_due', failed_at = NULL WHERE user_id = ?", (before,))
        conn.commit()
        box = []
        assert LC.payment_failed(conn, now=NOW, send=lambda *a: box.append(a), site=SITE, log=QUIET) == 0
        assert box == []
        assert "Payment failed — your access is paused" in BI.describe("past_due"), "the page still says it"


def test_a_failed_email_is_tried_again_and_nothing_reached_marks_nothing():
    def boom(*_a):
        raise OSError("relay down")
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _trialist(conn, "trial@example.com")
        _phone(conn, uid)
        _fail(conn, uid, at=NOW)
        said = []
        assert LC.payment_failed(conn, now=NOW + 60, send=boom, site=SITE, log=said.append) == 0
        assert said and "trial@example.com" not in said[0], "the address never goes in a log line"
        assert len(_queued(conn, uid)) == 1, "the push went"
        box = []
        assert LC.payment_failed(conn, now=NOW + 120, send=lambda *a: box.append(a), site=SITE, log=QUIET) == 1
        assert [a[0] for a in box] == ["trial@example.com"] and len(_queued(conn, uid)) == 1, \
            "the email went on the retry, and the push did not go twice"
        # No phone and no relay: nothing reached them, so nothing is marked.
        alone = _trialist(conn, "alone@example.com")
        _fail(conn, alone, at=NOW)
        from engine import mailer
        was = mailer.configured
        mailer.configured = lambda: False
        try:
            assert LC.payment_failed(conn, now=NOW + 180, site=SITE, log=QUIET) == 0
        finally:
            mailer.configured = was
        assert conn.execute("SELECT fail_noted FROM subscriptions WHERE user_id = ?", (alone,)).fetchone()[0] is None
        assert LC.payment_failed(conn, now=NOW + 240, send=lambda *a: box.append(a), site=SITE, log=QUIET) == 1
        assert box[-1][0] == "alone@example.com", "the relay set later: the email goes then"


def test_the_billing_sweep_runs_it_and_the_policy_names_it():
    src = READ("launch.py")
    sweep = src[src.index("def _billing_sweeper("):src.index("SLIP_WATCH_S =")]
    assert "_lc.payment_failed(conn)" in sweep and sweep.index("_tn.run(conn)") < sweep.index("_lc.payment_failed(conn)"), \
        "every 30 minutes, beside the trial's reminder"
    lc = READ("engine", "lifecycle.py")
    assert "payment_failed(" not in lc[lc.index("def run("):], "one caller: never told twice by two loops at once"
    assert '"failed_at", "REAL"' in READ("engine", "billing.py") and '"fail_noted", "REAL"' in READ("engine", "billing.py")
    import re
    priv = re.sub(r"\s+", " ", READ("web", "privacy.html"))
    assert "if a charge does not go through, when it failed, whether it was the trial’s first charge, " \
           "and the failure we last told you about" in priv
    assert "that a charge did not go through" in priv and "a charge that did not go through" in priv


if __name__ == "__main__":
    os.environ.pop("QB_SMTP_HOST", None)
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
