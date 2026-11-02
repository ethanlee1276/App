"""One free trial per person: an email address or a card that has had one cannot start another.

Ethan, 2026-11-02: "we do not want people making a new account and taking
advantage of the trials". engine/trialguard. What these hold:

  * one mailbox however it is written (case, +tags, Gmail's dots);
  * a mark is a keyed one-way hash with no account attached, so it outlives
    a deleted account and holds neither the address nor the card;
  * an address that has had a trial (from 2 November 2026) is offered none,
    on any account, a deleted one's address included;
  * a trial started with a card that has had one is cancelled at Stripe at
    once, nothing charged, and the account page says why; a first trial's
    card is remembered; a trial from before the rule is left alone;
  * a read of Stripe that fails is tried again by the sweep; the card is
    found on the subscription, else the customer, else the customer's cards;
  * the webhook, the return from Checkout and the billing sweep all check,
    the plans page and the checkout ask, and the Terms, the Privacy Policy,
    the plans card, the checkout note and the FAQ say so.

Run directly: `python3 tests/test_one_trial_per_person.py`
"""
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import accounts as A                                  # noqa: E402
from engine import billing as BI                                  # noqa: E402
from engine import trialguard as TG                               # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
DAY = 86400
NOW = max(time.time(), TG.RULE_FROM + DAY)


def _db():
    conn = A.connect(str(Path(tempfile.mkdtemp()) / "acc.db"))
    TG.init(conn)
    return conn


def _trial(conn, email, began=None):
    """An account with a monthly trial, as Stripe tells it."""
    uid = int(A.create_user(conn, email, "correct horse battery", confirmed=True)[1]["id"])
    began = NOW - 3600 if began is None else began
    for kind, obj in (("checkout.session.completed", {
            "client_reference_id": str(uid), "customer": f"cus_{uid}", "subscription": f"sub_{uid}",
            "payment_status": "no_payment_required", "metadata": {"plan": "monthly"}}),
            ("customer.subscription.updated", {
                "id": f"sub_{uid}", "customer": f"cus_{uid}", "status": "trialing", "metadata": {"plan": "monthly"},
                "start_date": began, "trial_end": began + 3 * DAY, "cancel_at_period_end": False,
                "items": {"data": [{"current_period_end": began + 3 * DAY}]}})):
        BI.apply_event(conn, BI.read_event({"type": kind, "created": began, "data": {"object": obj}}))
    return uid


class Stripe:
    """Stripe, as far as the guard reads it: each subscription's card."""
    def __init__(self):
        self.cards, self.cancelled, self.down = {}, [], False

    def fetch(self, path):
        if self.down:
            raise BI.BillingUnavailable("Could not reach Stripe")
        sid = path.split("/", 1)[1].split("?", 1)[0] if path.startswith("subscriptions/") else None
        if sid:
            fp = self.cards.get(sid)
            return {"id": sid, "default_payment_method": {"type": "card", "card": {"fingerprint": fp}} if fp else None}
        return {}

    def cancel(self, sid):
        self.cancelled.append(sid)
        return {"id": sid, "customer": "cus_" + sid[4:], "status": "canceled"}


def test_one_mailbox_however_it_is_written():
    same = TG.same_address
    assert same("John.Smith+promo@GoogleMail.com") == same("johnsmith@gmail.com") == "johnsmith@gmail.com"
    assert same(" Pat+trial2@Example.com ") == "pat@example.com"
    assert same("pat.lee@example.com") != same("patlee@example.com"), "dots are only Gmail's to ignore"
    assert same("15555550123@phone.invalid") == "15555550123@phone.invalid"


def test_a_mark_is_a_keyed_hash_tied_to_no_account():
    conn = _db()
    TG.remember(conn, "email", "Pat+x@Example.com")
    TG.remember(conn, "card", "fpCARD123")
    rows = conn.execute("SELECT kind, mark FROM trial_marks").fetchall()
    assert len(rows) == 2 and all(re.fullmatch(r"[0-9a-f]{64}", r[1]) for r in rows)
    assert all("pat" not in r[1] and "CARD" not in r[1] for r in rows)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(trial_marks)")]
    assert cols == ["kind", "mark", "at"], "no account is attached"
    assert TG.seen(conn, "email", "pat@example.com") and TG.seen(conn, "card", "fpCARD123")
    assert not TG.seen(conn, "card", "fpOTHER") and not TG.seen(conn, "email", "")
    # Kept three years, then dropped.
    TG.remember(conn, "email", "new@example.com", now=time.time() + TG.MARK_KEEP_S + DAY)
    assert not TG.seen(conn, "email", "pat@example.com")


def test_an_address_that_had_a_trial_is_offered_none_even_after_deleting_the_account():
    conn = _db()
    uid = _trial(conn, "Sam.Ortiz@gmail.com")
    assert TG.note(conn, uid) is True
    assert TG.had_trial(conn, "samortiz+again@gmail.com"), "an alias of the same mailbox"
    A.delete_user(conn, uid)
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    assert TG.had_trial(conn, "sam.ortiz@gmail.com"), "the mark outlives the account — that is its point"
    again = int(A.create_user(conn, "sam.ortiz@gmail.com", "correct horse battery", confirmed=True)[1]["id"])
    assert not BI.has_subscribed_before(conn, again), "the new account has no history of its own"
    fresh = not BI.has_subscribed_before(conn, again) and not TG.had_trial(conn, "sam.ortiz@gmail.com")
    assert BI.trial_days_for("monthly", fresh) == 0, "and still no second trial"
    # A trial from before the rule is not marked.
    old = _trial(conn, "early@example.com", began=TG.RULE_FROM - 2 * DAY)
    assert TG.note(conn, old) is False and not TG.had_trial(conn, "early@example.com")


def test_a_trial_with_a_card_that_had_one_is_cancelled_at_once_and_says_why():
    conn = _db()
    st = Stripe()
    first = _trial(conn, "first@example.com")
    st.cards[f"sub_{first}"] = "fpSAMECARD"
    assert TG.check(conn, first, fetch=st.fetch, cancel=st.cancel) == "ok"
    assert TG.check(conn, first, fetch=st.fetch, cancel=st.cancel) == "skip", "looked at once"
    assert BI.status_for(conn, first)["entitled"] is True and st.cancelled == []
    second = _trial(conn, "brand.new@example.com")
    st.cards[f"sub_{second}"] = "fpSAMECARD"
    assert BI.status_for(conn, second)["entitled"] is True, "until the card is looked at"
    assert TG.check(conn, second, fetch=st.fetch, cancel=st.cancel) == "refused"
    assert st.cancelled == [f"sub_{second}"], "cancelled at Stripe: nothing is charged"
    out = BI.status_for(conn, second)
    assert out["status"] == "canceled" and out["entitled"] is False
    assert out["note"] == BI.TRIAL_REFUSED and "already had a free trial" in out["note"]
    assert BI.has_subscribed_before(conn, second), "a plan from here is a paid one"
    assert TG.had_trial(conn, "brand.new@example.com"), "its address is marked too"
    # A different card is a first trial.
    third = _trial(conn, "third@example.com")
    st.cards[f"sub_{third}"] = "fpOTHERCARD"
    assert TG.check(conn, third, fetch=st.fetch, cancel=st.cancel) == "ok"


def test_a_trial_from_before_the_rule_and_a_stripe_that_does_not_answer():
    conn = _db()
    st = Stripe()
    early = _trial(conn, "early@example.com", began=TG.RULE_FROM - DAY)
    assert TG.check(conn, early, fetch=st.fetch, cancel=st.cancel) == "skip"
    uid = _trial(conn, "later@example.com")
    st.cards[f"sub_{uid}"] = "fpX"
    st.down = True
    assert TG.check(conn, uid, fetch=st.fetch, cancel=st.cancel) == "later"
    assert conn.execute("SELECT card_checked FROM subscriptions WHERE user_id = ?", (uid,)).fetchone()[0] is None
    st.down = False
    assert TG.sweep(conn, fetch=st.fetch, cancel=st.cancel) == 0
    assert conn.execute("SELECT card_checked FROM subscriptions WHERE user_id = ?", (uid,)).fetchone()[0]
    assert TG.seen(conn, "card", "fpX")
    # No card Stripe will show: the address alone is marked.
    bare = _trial(conn, "bare@example.com")
    assert TG.check(conn, bare, fetch=st.fetch, cancel=st.cancel) == "ok" and TG.had_trial(conn, "bare@example.com")
    # The sweep refuses a reused card it finds.
    again = _trial(conn, "again@example.com")
    st.cards[f"sub_{again}"] = "fpX"
    assert TG.sweep(conn, fetch=st.fetch, cancel=st.cancel) == 1 and BI.status_for(conn, again)["status"] == "canceled"


def test_the_card_is_found_on_the_subscription_the_customer_or_their_cards():
    calls = []

    def fetch(path):
        calls.append(path.split("?")[0])
        if path.startswith("subscriptions/"):
            return {"id": "sub_1", "default_payment_method": None}
        if path.startswith("customers/"):
            return {"invoice_settings": {"default_payment_method": None}}
        return {"data": [{"type": "card", "card": {"fingerprint": "fpLIST"}}]}
    assert TG.fingerprint("sub_1", "cus_1", fetch) == "fpLIST"
    assert calls == ["subscriptions/sub_1", "customers/cus_1", "payment_methods"]
    assert TG.fingerprint("sub_1", None, fetch) is None, "no customer: nothing more to read"


def test_the_webhook_the_return_trip_and_the_sweep_check_and_the_pages_ask():
    srv = READ("server.py")
    assert 'out["trial_eligible"] = not BI.has_subscribed_before(\n                    conn, who["id"]) and not TG.had_trial(conn, who["email"])' in srv
    assert 'fresh = not BI.has_subscribed_before(conn, who["id"]) and not TG.had_trial(conn, who["email"])' in srv
    hook = srv[srv.index("applied = BI.apply_event(conn, event) if event else False"):][:700]
    assert "TG.after_event(conn, event)" in hook and "except Exception" in hook, "never the reason Stripe is not answered"
    back = srv[srv.index("out = BI.reconcile_session("):][:700]
    assert 'TG.check(conn, who["id"]) == "refused"' in back
    launch = READ("launch.py")
    sweep = launch[launch.index("def _billing_sweeper("):launch.index("SLIP_WATCH_S =")]
    assert "_tg.sweep(conn)" in sweep
    conn = _db()
    uid = _trial(conn, "hooked@example.com")
    st = Stripe()
    st.cards[f"sub_{uid}"] = "fpH"
    ev = BI.read_event({"type": "customer.subscription.updated", "data": {"object": {
        "id": f"sub_{uid}", "customer": f"cus_{uid}", "status": "trialing"}}})
    assert TG.after_event(conn, ev, fetch=st.fetch, cancel=st.cancel) == "ok", "the account found by its customer"


def test_the_terms_the_policy_and_every_page_that_offers_a_trial_say_so():
    flat = lambda h: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))  # noqa: E731
    terms = flat(READ("web", "terms.html"))
    assert "One trial per person — if you have subscribed before, on this account or with the same email address or card on another" in terms
    assert "a trial started with a card that has already had one is cancelled at once, with nothing charged" in terms
    assert "The changes of 2 November 2026 are two parts of §5.3" in terms
    priv = READ("web", "privacy.html")
    assert 'id="one-trial"' in priv and "<code>trial_marks</code>" in priv
    p = flat(priv)
    for want in ("after your account is deleted too", "A free trial’s one-way fingerprints (§2.3) — three years",
                 "all but a one-way fingerprint of the email and card a free trial was started with",
                 "except a free trial’s one-way fingerprints (§2.3)"):
        assert want in p, want
    acct = READ("web", "js", "account.js")
    assert "One\n            free trial per person: a card or email that has had one can’t start another." in acct
    assert "only, one per person: an email address or a card that has had one, " in acct
    from _app import app_js
    assert "One free trial per person: a trial started with a card that has had one is cancelled at once" in flat(app_js())
    assert "one free trial per person, whatever the account" in READ("engine", "trialnote.py")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
