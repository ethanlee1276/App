"""A failed payment or a cancellation locks the account to the paywall.

Ethan, 2026-10-12: "we need to figure out if a failed payment on stripe
and a cancellation on stripe will make the user not have access too the
website anymore. It should lock them too the paywall screen".

What was true before this file, and why each part had to change:

  * A CANCELLATION walled the account — when Stripe's webhook arrived. It
    is a request from Stripe's servers to ours, and Bot Fight Mode can eat
    it (engine/billing.reconcile_session). A lapse that never arrived was
    never heard about: the row stayed `active`.
  * A FAILED PAYMENT did not wall at all. `past_due` kept access "until
    the paid period ends", and the date it read was the end of the NEW
    period — Stripe moves it forward when it opens the renewal invoice,
    paid or not — so the whole unpaid month stayed open.
  * The PAGE put the wall up at boot only. A tab left open across a lapse
    kept the site's chrome over redacted boards.

Every test here is offline: Stripe is a stub `fetch`, never the network.

    python3 tests/test_a_lapse_locks_the_paywall.py
"""

import os
import re
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A      # noqa: E402
from engine import billing as B       # noqa: E402
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

DAY = 86400


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


SERVER = _read("server.py")
APP = app_js()
LAUNCH = _read("launch.py")


def _db():
    d = tempfile.mkdtemp()
    conn = A.connect(os.path.join(d, "acc.db"))
    B.init(conn)
    _code, who = A.create_user(conn, "lapse@example.com",
                               "correct-horse-battery", confirmed=True)
    return conn, who["id"]


def _apply(conn, kind, obj, created=None):
    payload = {"type": kind, "data": {"object": obj}}
    if created is not None:
        payload["created"] = created
    return B.apply_event(conn, B.read_event(payload))


def _subscribed(conn, uid, sub="sub_L1", cus="cus_L1", end=None):
    """Checkout, then the subscription event that carries the real status
    and the paid-through date — the order Stripe sends them in."""
    _apply(conn, "checkout.session.completed", {
        "client_reference_id": str(uid), "customer": cus,
        "subscription": sub, "payment_status": "paid",
        "metadata": {"plan": "monthly"}})
    _apply(conn, "customer.subscription.updated", {
        "id": sub, "customer": cus, "status": "active",
        "metadata": {"plan": "monthly"},
        "items": {"data": [{"current_period_end": end or time.time() + 30 * DAY}]}})


def _function(src, name):
    i = src.index(f"def {name}(")
    j = src.find("\n    def ", i + 1)
    k = src.find("\ndef ", i + 1)
    ends = [x for x in (j, k) if x != -1]
    return src[i:min(ends)] if ends else src[i:]


# --- the rule -------------------------------------------------------------------
def test_who_is_walled():
    now = time.time()
    for st in ("past_due", "unpaid", "canceled", "incomplete",
               "incomplete_expired", "paused", "none"):
        assert B.entitled(st, now + 30 * DAY, now=now) is False, st
    assert B.entitled("active", now + 30 * DAY, now=now) is True
    assert B.entitled("trialing", now + 3 * DAY, now=now) is True


def test_a_plan_cancelled_to_its_period_end_keeps_the_days_paid_for_then_walls():
    """Stripe's portal cancels at the period's end by default. The days
    already paid for are theirs; the second they are used, the wall goes
    up — without waiting for Stripe's closing webhook."""
    now = time.time()
    assert B.entitled("active", now + DAY, now=now, cancel_at_end=True)
    assert not B.entitled("active", now - 1, now=now, cancel_at_end=True)
    assert not B.entitled("trialing", now - 1, now=now, cancel_at_end=True)
    # Not cancelled: a date in the past alone does not wall (the renewal's
    # webhook may simply be late; `refresh` settles it).
    assert B.entitled("active", now - DAY, now=now)


def test_the_page_copy_says_what_to_do():
    """The paywall shows these sentences beside its Update card button, and
    the account page beside Manage billing, so each names the fix."""
    assert "Update your card" in B.describe("past_due")
    assert "Update your card" in B.describe("unpaid")
    assert "pick a plan" in B.describe("canceled")
    said = B.describe("active", time.time() + 5 * DAY, True)
    assert said.startswith("Cancelled — access until"), said
    assert "renews" not in said, "a cancelled plan still said it renews"
    gone = B.describe("active", time.time() - 5 * DAY, True)
    assert gone.startswith("Cancelled — access ended"), gone


# --- the webhook lifecycle --------------------------------------------------------
def test_a_failed_payment_walls_and_the_payment_that_clears_lets_them_back():
    conn, uid = _db()
    _subscribed(conn, uid)
    assert B.status_for(conn, uid)["entitled"] is True
    now = int(time.time())
    assert _apply(conn, "invoice.payment_failed",
                  {"customer": "cus_L1", "subscription": "sub_L1"}, now)
    st = B.status_for(conn, uid)
    assert st["status"] == "past_due" and st["entitled"] is False, st
    assert st["open"] is True, "a card Stripe is still retrying read as closed"
    assert st["plan"] == "monthly", "the failure blanked the plan"
    assert _apply(conn, "customer.subscription.updated", {
        "id": "sub_L1", "customer": "cus_L1", "status": "active"}, now + 60)
    assert B.status_for(conn, uid)["entitled"] is True


def test_a_payment_failure_delivered_late_cannot_wall_a_customer_who_paid():
    """Stripe does not deliver in order and retries a refused delivery for
    days. A failure first refused at the door can land after the payment
    that fixed it; while `past_due` walled nobody that cost nothing."""
    conn, uid = _db()
    _subscribed(conn, uid)
    now = int(time.time())
    _apply(conn, "customer.subscription.updated", {
        "id": "sub_L1", "customer": "cus_L1", "status": "active"}, now)
    assert _apply(conn, "invoice.payment_failed",
                  {"customer": "cus_L1", "subscription": "sub_L1"},
                  now - 3600) is False
    assert B.status_for(conn, uid)["entitled"] is True
    # The same second is not "older", and an event with no time at all is
    # applied as before.
    assert _apply(conn, "invoice.payment_failed",
                  {"customer": "cus_L1", "subscription": "sub_L1"}, now)
    assert B.status_for(conn, uid)["status"] == "past_due"


def test_a_cancellation_walls_on_the_webhook():
    conn, uid = _db()
    _subscribed(conn, uid)
    _apply(conn, "customer.subscription.deleted", {
        "id": "sub_L1", "customer": "cus_L1", "status": "canceled"})
    st = B.status_for(conn, uid)
    assert st["entitled"] is False and st["open"] is False


def test_cancel_at_period_end_is_read_and_undone():
    conn, uid = _db()
    end = time.time() + 9 * DAY
    _subscribed(conn, uid, end=end)
    _apply(conn, "customer.subscription.updated", {
        "id": "sub_L1", "customer": "cus_L1", "status": "active",
        "cancel_at_period_end": True,
        "items": {"data": [{"current_period_end": end}]}})
    st = B.status_for(conn, uid)
    assert st["cancel_at_end"] is True and st["entitled"] is True
    assert st["note"].startswith("Cancelled — access until"), st["note"]
    # Newer API versions say it with `cancel_at` instead.
    ev = B.read_event({"type": "customer.subscription.updated", "data": {
        "object": {"id": "sub_L1", "status": "active", "cancel_at": end}}})
    assert ev["cancel_at_end"] is True
    # Changed their mind in the portal: the flag clears, it is not kept.
    _apply(conn, "customer.subscription.updated", {
        "id": "sub_L1", "customer": "cus_L1", "status": "active",
        "cancel_at_period_end": False, "cancel_at": None})
    assert B.status_for(conn, uid)["cancel_at_end"] is False
    # An event with no opinion (an invoice) leaves the flag as it was.
    assert B.read_event({"type": "invoice.payment_failed", "data": {
        "object": {"customer": "cus_L1"}}})["cancel_at_end"] is None


def test_the_cancelled_plan_walls_when_its_date_passes_with_no_webhook():
    conn, uid = _db()
    end = time.time() + 2
    _subscribed(conn, uid, end=end)
    _apply(conn, "customer.subscription.updated", {
        "id": "sub_L1", "customer": "cus_L1", "status": "active",
        "cancel_at_period_end": True,
        "items": {"data": [{"current_period_end": end}]}})
    row = conn.execute("SELECT status, period_end, cancel_at_end FROM "
                       "subscriptions WHERE user_id=?", (uid,)).fetchone()
    assert B.entitled(row[0], row[1], now=end + 1, cancel_at_end=bool(row[2])) \
        is False, "the period ended and the cancelled plan stayed open"


def test_buying_again_after_a_cancelled_plan_starts_clean():
    """One row per account. The Checkout event carries no date and no
    cancel flag, so a COALESCE would hand the new plan the old one's
    "cancelled, paid through last month" and wall somebody who paid a
    minute ago."""
    conn, uid = _db()
    _subscribed(conn, uid, end=time.time() - 40 * DAY)
    _apply(conn, "customer.subscription.updated", {
        "id": "sub_L1", "customer": "cus_L1", "status": "active",
        "cancel_at_period_end": True,
        "items": {"data": [{"current_period_end": time.time() - 40 * DAY}]}})
    _apply(conn, "customer.subscription.deleted", {
        "id": "sub_L1", "customer": "cus_L1", "status": "canceled"})
    assert B.status_for(conn, uid)["entitled"] is False
    _apply(conn, "checkout.session.completed", {
        "client_reference_id": str(uid), "customer": "cus_L2",
        "subscription": "sub_L2", "payment_status": "paid"})
    st = B.status_for(conn, uid)
    assert st["entitled"] is True, f"a fresh purchase came back walled: {st}"
    assert st["cancel_at_end"] is False and st["period_end"] is None


# --- hearing about it when the webhook does not say -----------------------------
def _stub(reply):
    calls = []

    def fetch(sid):
        calls.append(sid)
        if isinstance(reply, Exception):
            raise reply
        return dict(reply, id=sid) if isinstance(reply, dict) else reply
    return fetch, calls


def test_refresh_hears_a_cancellation_the_webhook_never_delivered():
    conn, uid = _db()
    _subscribed(conn, uid)
    fetch, calls = _stub({"customer": "cus_L1", "status": "canceled"})
    assert B.refresh(conn, uid, fetch=fetch) is True
    assert calls == ["sub_L1"]
    assert B.status_for(conn, uid)["entitled"] is False


def test_refresh_hears_a_failed_card_and_then_the_fix():
    conn, uid = _db()
    _subscribed(conn, uid)
    now = time.time()
    fetch, _ = _stub({"customer": "cus_L1", "status": "past_due"})
    assert B.refresh(conn, uid, now=now, fetch=fetch)
    assert B.status_for(conn, uid)["entitled"] is False
    # Walled: asked again after a minute, not an hour.
    fetch, calls = _stub({"customer": "cus_L1", "status": "active"})
    assert B.refresh(conn, uid, now=now + 30, fetch=fetch) is False
    assert calls == []
    assert B.refresh(conn, uid, now=now + B.RECHECK_LOCKED_S + 1, fetch=fetch)
    assert B.status_for(conn, uid)["entitled"] is True


def test_refresh_is_paced_and_stamped_before_it_asks():
    conn, uid = _db()
    _subscribed(conn, uid)
    now = time.time()
    fetch, calls = _stub({"customer": "cus_L1", "status": "active"})
    assert B.refresh(conn, uid, now=now, fetch=fetch)
    assert B.refresh(conn, uid, now=now + 600, fetch=fetch) is False
    assert len(calls) == 1, "an entitled row was re-read inside the hour"
    # A Stripe that does not answer is asked once per interval, not once
    # per request that arrives while it hangs.
    boom, tried = _stub(TimeoutError("Stripe is slow"))
    later = now + B.RECHECK_S + 1
    assert B.refresh(conn, uid, now=later, fetch=boom) is False
    assert B.refresh(conn, uid, now=later + 5, fetch=boom) is False
    assert len(tried) == 1
    assert B.status_for(conn, uid)["entitled"] is True, \
        "a failed read changed the row"


def test_opening_the_billing_page_makes_the_next_status_read_stripe():
    conn, uid = _db()
    _subscribed(conn, uid)
    now = time.time()
    fetch, calls = _stub({"customer": "cus_L1", "status": "past_due"})
    B.refresh(conn, uid, now=now, fetch=fetch)
    B.recheck_soon(conn, uid)
    fetch, calls = _stub({"customer": "cus_L1", "status": "active"})
    assert B.refresh(conn, uid, now=now + 5, fetch=fetch), \
        "back from Stripe's page and still waiting out the interval"
    assert B.status_for(conn, uid)["entitled"] is True


def test_refresh_never_asks_about_what_cannot_change_or_cannot_be_asked():
    conn, uid = _db()
    fetch, calls = _stub({"status": "active"})
    assert B.refresh(conn, uid, fetch=fetch) is False          # no row at all
    _subscribed(conn, uid)
    _apply(conn, "customer.subscription.deleted", {
        "id": "sub_L1", "customer": "cus_L1", "status": "canceled"})
    assert B.refresh(conn, uid, fetch=fetch) is False          # final
    conn.execute("UPDATE subscriptions SET status='active', "
                 "subscription_id='sub_x/../../v1/customers' WHERE user_id=?",
                 (uid,))
    conn.commit()
    assert B.refresh(conn, uid, fetch=fetch) is False          # not an id
    assert calls == []


def test_a_reply_about_another_subscription_is_ignored():
    conn, uid = _db()
    _subscribed(conn, uid)
    assert B.refresh(conn, uid, fetch=lambda sid: {
        "id": "sub_SOMEONE_ELSE", "status": "canceled"}) is False
    assert B.status_for(conn, uid)["entitled"] is True


def test_a_webhook_older_than_a_read_of_stripe_is_dropped():
    conn, uid = _db()
    _subscribed(conn, uid)
    now = time.time()
    B.refresh(conn, uid, now=now,
              fetch=lambda sid: {"id": sid, "customer": "cus_L1",
                                 "status": "active"})
    assert _apply(conn, "invoice.payment_failed",
                  {"customer": "cus_L1", "subscription": "sub_L1"},
                  int(now) - 120) is False
    assert B.status_for(conn, uid)["entitled"] is True


def test_the_sweep_reads_the_rows_nobody_is_loading_pages_for():
    conn, uid = _db()
    _subscribed(conn, uid)
    _code, other = A.create_user(conn, "gone@example.com",
                                 "correct-horse-battery", confirmed=True)
    _subscribed(conn, other["id"], sub="sub_L2", cus="cus_L2")
    _apply(conn, "customer.subscription.deleted", {
        "id": "sub_L2", "customer": "cus_L2", "status": "canceled"})
    now = time.time()
    fetch, calls = _stub({"status": "past_due"})
    assert B.sweep(conn, now=now, fetch=fetch) == 1
    assert calls == ["sub_L1"], "the sweep asked about a cancelled plan"
    assert B.status_for(conn, uid)["entitled"] is False
    assert B.sweep(conn, now=now + 600, fetch=fetch) == 0, \
        "the sweep re-read a row it had just read"
    assert B.sweep(conn, now=now + B.SWEEP_EVERY_S + 1, fetch=fetch) == 1


# --- the server ---------------------------------------------------------------------
def test_the_status_call_reads_stripe_before_it_answers():
    body = _function(SERVER, "_billing_get")
    assert "BI.refresh(conn, who[\"id\"])" in body
    assert body.index("BI.refresh(") < body.index("BI.status_for("), \
        "the page is told the old status, then the row changes"
    seg = body[body.index("BI.refresh(") - 200:body.index("BI.refresh(") + 200]
    assert "try:" in seg and "except Exception" in seg, \
        "a Stripe that will not answer would break the status page"


def test_a_past_due_account_is_sent_to_fix_its_card_not_sold_a_second_plan():
    body = _function(SERVER, "_billing_post")
    guard = body.index('("past_due", "unpaid")')
    assert guard < body.index("BI.start_checkout("), \
        "the second-plan guard runs after Checkout has started"
    seg = body[guard:guard + 700]
    assert "409" in seg and '"portal": True' in seg
    assert "BI.recheck_soon(conn, who[\"id\"])" in body


def test_deleting_the_account_is_refused_while_stripe_can_still_charge():
    """`past_due` is walled, and Stripe is still retrying its card. The
    deletion refusal asked `entitled` only; it now asks `open` too."""
    import server
    conn, uid = _db()
    _subscribed(conn, uid)
    _apply(conn, "invoice.payment_failed",
           {"customer": "cus_L1", "subscription": "sub_L1"})
    said = server.Handler._live_subscription(None, conn, uid)
    assert "Cancel it first" in said, said
    # Cancelled to run out at the period's end: Stripe will not charge it
    # again, so delete works — the message promised exactly that.
    _apply(conn, "customer.subscription.updated", {
        "id": "sub_L1", "customer": "cus_L1", "status": "active",
        "cancel_at_period_end": True})
    assert server.Handler._live_subscription(None, conn, uid) == ""
    _apply(conn, "customer.subscription.deleted", {
        "id": "sub_L1", "customer": "cus_L1", "status": "canceled"})
    assert server.Handler._live_subscription(None, conn, uid) == ""


def test_an_old_database_still_refuses_the_delete():
    """A file from before this change has no cancel_at_end column, so
    status_for throws on it — and a throw in this check lets the delete
    through. The check migrates the table first."""
    import server
    d = tempfile.mkdtemp()
    conn = A.connect(os.path.join(d, "old.db"))
    _code, who = A.create_user(conn, "old@example.com",
                               "correct-horse-battery", confirmed=True)
    conn.executescript(
        "CREATE TABLE subscriptions (user_id INTEGER PRIMARY KEY, "
        "customer_id TEXT, subscription_id TEXT, status TEXT NOT NULL "
        "DEFAULT 'none', period_end REAL, updated_at REAL NOT NULL, "
        "plan TEXT);")
    conn.execute("INSERT INTO subscriptions VALUES (?,?,?,?,?,?,?)",
                 (who["id"], "cus_old", "sub_old", "active",
                  time.time() + 9 * DAY, time.time(), "monthly"))
    conn.commit()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(subscriptions)")}
    assert "cancel_at_end" not in cols, "the fixture is not an old file"
    said = server.Handler._live_subscription(None, conn, who["id"])
    assert "Cancel it first" in said, \
        "an old database let a subscribed account delete itself"


def test_the_launcher_sweeps():
    assert "def _billing_sweeper(" in LAUNCH
    body = _function(LAUNCH, "_billing_sweeper")
    assert "_bi.configured()" in body and "_bi.sweep(conn)" in body
    assert "except Exception" in body, "a billing failure could stop the site"
    assert re.search(r"threading\.Thread\(target=_billing_sweeper", LAUNCH)


# --- the page -----------------------------------------------------------------------
def test_an_open_tab_rechecks_the_wall_and_reloads_onto_it():
    i = APP.index("async function wallRecheck(")
    body = APP[i:APP.index("\n}\n", i)]
    assert "paywallCheck()" in body and "location.reload()" in body
    assert '"#paywall"' in body and "WALL_OPEN.includes(state.view)" in body
    assert "setInterval(wallRecheck," in APP
    ret = APP[APP.index("function refreshOnReturn("):]
    ret = ret[:ret.index("\n}\n")]
    assert "wallRecheck()" in ret, "coming back to the tab does not ask"


def test_the_paywall_says_why_and_offers_the_fix():
    i = APP.index("function pwLapseHTML(")
    body = APP[i:APP.index("\n}\n", i)]
    assert '"past_due"' in body and '"unpaid"' in body
    # The server's sentence, escaped — one wording for both pages.
    assert "escapeHtml(s.note)" in body
    assert 'data-act="billPortal"' in body and "Update card" in body
    # Its own line: every .acct-note carries the account's sync status.
    assert "pw-lapse-note" in body and "acct-note" not in body
    go = APP[APP.index("async function _billGo("):]
    go = go[:go.index("\n}\n")]
    assert ".pw-lapse-note" in go, "a portal error would have nowhere to show"
    assert '"canceled"' in body and "cancel_at_end" in body
    pw = APP[APP.index("function paywallHTML("):]
    # With the record since: what the picks did after the plan ended (pwSinceHTML).
    assert "${pwLapseHTML(status, rec)}" in pw[:pw.index("pw-hero")]
    assert "billPortal: (el) => billPortal(el)" in APP


def test_the_account_page_names_a_plan_that_is_running_out():
    panel = APP[APP.index("function planPanelHTML("):]
    panel = panel[:panel.index("\n}\n")]
    assert "s.cancel_at_end" in panel


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
