"""Yearly at month two: a monthly member on their third bill sees "switch to
yearly, save $75" once, in Settings (docs/IDEAS.md, the way in and the way
up's sixth; built 2026-10-28, off until runbook FY).

What these hold:

  * the offer is for an active monthly member whose subscription began
    eight weeks ago or more, not cancelling, while QB_YEARLY_OFFER=1 and the
    yearly price is set; never a trial, a lapse, another plan or a member
    who is leaving; it says $75 off a year of monthly bills;
  * when a subscription began is Stripe's own start date, read off the
    subscription events the webhook and the hourly read already handle,
    and kept on the account's row;
  * the switch is Stripe's page confirming it (the portal's
    subscription_update_confirm flow, this subscription's one item to the
    yearly price), opened only for a member the offer is for and only for
    a subscription that is the monthly plan alone;
  * the server says the offer on the billing status and opens the switch
    on POST /api/billing/yearly; the plan screen shows it with a way to put
    it away for good on the device.

Run directly: `python3 tests/test_yearly_at_month_two.py`
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import billing as BI  # noqa: E402

DAY = 86400.0
NOW = 1_800_000_000.0
ENV = {"QB_YEARLY_OFFER": "1", "STRIPE_PRICE_MONTHLY": "price_month_fake", "STRIPE_PRICE_YEARLY": "price_year_fake",
       "STRIPE_SECRET_KEY": "sk_test_yearly_fake", "STRIPE_WEBHOOK_SECRET": "whsec_yearly_fake"}


class _Env:
    def __init__(self, **over):
        self.want = {**ENV, **over}

    def __enter__(self):
        self.was = {k: os.environ.get(k) for k in self.want}
        for k, v in self.want.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def __exit__(self, *a):
        for k, v in self.was.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")
    BI.init.__wrapped__(c)
    return c


def _row(c, uid=1, status="active", plan="monthly", cancel=0, started=NOW - 60 * DAY):
    c.execute("INSERT OR REPLACE INTO subscriptions (user_id, customer_id, subscription_id, status, period_end, "
              "updated_at, plan, cancel_at_end, started_at) VALUES (?,?,?,?,?,?,?,?,?)",
              (uid, "cus_fake", "sub_fake", status, NOW + 9 * DAY, NOW, plan, cancel, started))


def test_the_offer_is_for_a_monthly_member_on_the_third_bill():
    c = _db()
    _row(c)
    with _Env():
        assert BI.yearly_offer(c, 1, now=NOW) == {"save_cents": 7500, "yearly_cents": 22500}
        assert BI.yearly_saving_cents() == 7500, "$300 of monthly bills less $225"
        for kw in ({"status": "trialing"}, {"status": "past_due"}, {"plan": "yearly"}, {"plan": "sixmonth"},
                   {"cancel": 1}, {"started": NOW - 20 * DAY}, {"started": None}):
            _row(c, **kw)
            assert BI.yearly_offer(c, 1, now=NOW) is None, kw
        _row(c, started=NOW - 56 * DAY)
        assert BI.yearly_offer(c, 1, now=NOW), "the eighth week is the third bill"
        assert BI.yearly_offer(c, 2, now=NOW) is None, "no row, no offer"
    with _Env(QB_YEARLY_OFFER=None):
        assert BI.yearly_offer(c, 1, now=NOW) is None, "off until switched on"
    with _Env(STRIPE_PRICE_YEARLY=None):
        assert BI.yearly_offer(c, 1, now=NOW) is None, "no yearly price, nothing to switch to"


def test_the_start_is_stripe_s_own_kept_from_its_events():
    c = _db()
    ev = BI.read_event({"type": "customer.subscription.updated", "created": NOW, "data": {"object": {
        "id": "sub_fake", "customer": "cus_fake", "status": "active", "start_date": NOW - 70 * DAY,
        "metadata": {"plan": "monthly"}, "items": {"data": [{"current_period_end": NOW + 20 * DAY}]}}}})
    assert ev["started_at"] == NOW - 70 * DAY
    ev["user_id"] = 1
    assert BI.apply_event(c, ev)
    assert c.execute("SELECT started_at FROM subscriptions WHERE user_id=1").fetchone()[0] == NOW - 70 * DAY
    fail = BI.read_event({"type": "invoice.payment_failed", "created": NOW + 1,
                          "data": {"object": {"customer": "cus_fake", "subscription": "sub_fake"}}})
    assert "started_at" not in fail or fail["started_at"] is None
    BI.apply_event(c, fail)
    assert c.execute("SELECT started_at FROM subscriptions WHERE user_id=1").fetchone()[0] == NOW - 70 * DAY, \
        "an event without one leaves it"
    src = Path(BI.__file__).read_text(encoding="utf-8")
    refresh = src[src.index("def refresh("):src.index("def recheck_soon(")]
    assert 'ev = read_event({"type": "customer.subscription.updated",' in refresh, "the hourly read carries it too"


def test_the_switch_is_stripe_s_page_and_only_for_the_offer():
    url, headers, body = BI.yearly_switch_request("sk_test_yearly_fake", "cus_fake", "https://site/#account",
                                                   "sub_fake", "si_fake", "price_year_fake")
    assert url.endswith("/billing_portal/sessions") and headers["Authorization"].startswith("Bearer ")
    form = dict(x.split("=", 1) for x in body.decode().split("&"))
    from urllib.parse import unquote_plus
    form = {unquote_plus(k): unquote_plus(v) for k, v in form.items()}
    assert form["flow_data[type]"] == "subscription_update_confirm"
    assert form["flow_data[subscription_update_confirm][subscription]"] == "sub_fake"
    assert form["flow_data[subscription_update_confirm][items][0][id]"] == "si_fake"
    assert form["flow_data[subscription_update_confirm][items][0][price]"] == "price_year_fake"
    assert form["flow_data[after_completion][redirect][return_url]"] == "https://site/#account"
    c = _db()
    _row(c)
    posted = []
    one = lambda sid: {"id": sid, "items": {"data": [{"id": "si_fake", "price": {"id": "price_month_fake"}}]}}  # noqa: E731
    with _Env():
        got = BI.open_yearly_switch(c, 1, "https://site/#account", fetch=one, now=NOW,
                                    post=lambda u, h, b: posted.append(b) or {"url": "https://billing.stripe.example/s"})
        assert got == "https://billing.stripe.example/s" and len(posted) == 1
        two = lambda sid: {"id": sid, "items": {"data": [{"id": "a", "price": {"id": "price_month_fake"}},  # noqa: E731
                                                        {"id": "b", "price": {"id": "x"}}]}}
        for fetch in (two, lambda sid: {"id": sid, "items": {"data": [{"id": "a", "price": {"id": "price_other"}}]}}):
            try:
                BI.open_yearly_switch(c, 1, "u", fetch=fetch, post=lambda *a: {"url": "x"}, now=NOW)
                raise AssertionError("switched a subscription that is not the monthly plan alone")
            except BI.BillingUnavailable:
                pass
        _row(c, plan="yearly")
        try:
            BI.open_yearly_switch(c, 1, "u", fetch=one, post=lambda *a: {"url": "x"}, now=NOW)
            raise AssertionError("opened the switch for a member the offer is not for")
        except BI.BillingUnavailable:
            pass


def test_the_server_says_it_and_opens_it():
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert "offer = BI.yearly_offer(conn, who[\"id\"])\n                if offer:\n                    out[\"yearly_offer\"] = offer" in src
    assert 'if path not in ("checkout", "portal", "yearly"' in src
    assert 'url = BI.open_yearly_switch(conn, who["id"], f"{base}/#account")' in src


def _fn(src, name):
    i = src.index(f"function {name}(")
    ends = [src.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\nif (")]
    ends = [e for e in ends if e != -1] or [len(src)]
    return src[i:min(ends)]


def test_the_plan_screen_shows_it_once():
    acct = (ROOT / "web" / "js" / "account.js").read_text(encoding="utf-8")
    assert "${s.entitled ? planPanelHTML(s) + yearlyOfferHTML(s) : none}" in acct
    assert 'if (b.dataset.yearly === "go") { _billGo(b, "yearly"); return; }' in acct
    assert "localStorage.setItem(YEARLY_SEEN_KEY, \"1\")" in acct
    node = shutil.which("node")
    if not node:
        return
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    prog = f"""
      let store = {{}};
      const localStorage = {{ getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => {{ store[k] = String(v); }} }};
      const escapeHtml = (s) => String(s); const icon = () => "";
      const setIco = () => "";
      {_fn(app, "setHref")}
      {_fn(app, "setItem")}
      {_fn(app, "setGroup")}
      const YEARLY_SEEN_KEY = "qb_yearly_seen";
      {_fn(acct, "yearlyOfferHTML")}
      const offer = {{ yearly_offer: {{ save_cents: 7500, yearly_cents: 22500 }} }};
      const out = [yearlyOfferHTML(offer), yearlyOfferHTML({{}})];
      store.qb_yearly_seen = "1";
      out.push(yearlyOfferHTML(offer));
      console.log(JSON.stringify(out));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    shown, none, dismissed = json.loads(out.stdout)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", shown)).strip()
    assert "Switch to yearly" in text and "Save $75 a year" in text and "$225 once a year instead of $25 a month" in text
    assert "Not now" in text and 'data-yearly="go"' in shown and 'data-yearly="no"' in shown
    assert none == "" and dismissed == "", "no offer, or put away: nothing"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
