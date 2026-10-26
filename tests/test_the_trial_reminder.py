"""The free trial reminds the member, once, about a day before it charges.

The trial takes a card and turns into $25 a month on day 4 (Terms §5.3).
What these hold (engine/trialnote, js/chat.js lvmTrialHTML):

  - a trialing member whose trial ends within a day gets ONE email, with
    when it ends, what is charged and how to cancel, and the next sweep
    sends nothing more;
  - nobody else does: not a trial a day and a half out, not a member who
    already cancelled, not an active subscription, not a phone account
    (no address — marked and skipped);
  - no relay, or a send that fails, marks nothing, so it still goes later;
  - the billing sweep runs it, and the Terms and Privacy pages say so;
  - the Live tab carries the same line while the trial runs, in the
    reader's own clock, and drops it once they cancel.

    python3 tests/test_the_trial_reminder.py
    (the browser half with QB_BROWSER_TESTS=1 and Playwright)
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A          # noqa: E402
from engine import billing as BI          # noqa: E402
from engine import trialnote as TN        # noqa: E402

CHAT = open(os.path.join(ROOT, "web", "js", "chat.js"), encoding="utf-8").read()
HOUR = 3600.0
# Mon 26 Oct 2026, 12:00 PM Eastern (16:00 UTC), so "tomorrow" is a fixed day.
NOW = 1793030400.0


def _db(d):
    conn = A.connect(Path(d) / "a.db")
    BI.init(conn)
    return conn


def _member(conn, email, status="trialing", ends_in=20 * HOUR, cancel=False, plan="monthly"):
    cur = conn.execute("INSERT INTO users (email, verifier, created_at, age_confirmed, terms_accepted_at) "
                       "VALUES (?, 'x', ?, 1, ?)", (email, NOW, NOW))
    uid = int(cur.lastrowid)
    conn.execute("INSERT INTO subscriptions (user_id, customer_id, subscription_id, status, period_end, plan, "
                 "cancel_at_end, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                 (uid, f"cus_{uid}", f"sub_{uid}", status, NOW + ends_in, plan, int(cancel), NOW))
    conn.commit()
    return uid


def _outbox():
    box = []
    return box, (lambda to, subject, text, html: box.append({"to": to, "subject": subject, "text": text, "html": html}))


def test_one_email_a_day_out_and_never_a_second():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        _member(conn, "you@example.com")
        box, send = _outbox()
        assert TN.run(conn, send=send, now=NOW, site="https://example.com", log=lambda *_: None) == 1
        assert [m["to"] for m in box] == ["you@example.com"]
        assert TN.run(conn, send=send, now=NOW + HOUR, site="https://example.com", log=lambda *_: None) == 0
        assert len(box) == 1, "the next sweep sent it again"
        conn.close()


def test_nobody_else_gets_one():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        _member(conn, "later@example.com", ends_in=36 * HOUR)
        _member(conn, "cancelled@example.com", cancel=True)
        _member(conn, "paying@example.com", status="active")
        _member(conn, "over@example.com", ends_in=-HOUR)
        phone = _member(conn, "15555550123@phone.invalid")
        box, send = _outbox()
        assert TN.run(conn, send=send, now=NOW, site="https://example.com", log=lambda *_: None) == 0
        assert not box, [m["to"] for m in box]
        noted = conn.execute("SELECT trial_noted FROM subscriptions WHERE user_id=?", (phone,)).fetchone()[0]
        assert noted is not None, "the phone account is marked, so it is not looked at every sweep"
        # A day and a half out is not yet; twelve hours later it is.
        assert TN.run(conn, send=send, now=NOW + 13 * HOUR, site="https://example.com", log=lambda *_: None) == 1
        assert [m["to"] for m in box] == ["later@example.com"]
        conn.close()


def test_no_relay_or_a_failed_send_marks_nothing():
    from engine import mailer
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _member(conn, "you@example.com")
        was = mailer.configured
        mailer.configured = lambda: False
        try:
            assert TN.run(conn, now=NOW, site="https://example.com") == 0
        finally:
            mailer.configured = was

        def broken(*_a):
            raise OSError("relay down")
        said = []
        assert TN.run(conn, send=broken, now=NOW, site="https://example.com", log=said.append) == 0
        assert said and "you@example.com" not in said[0], "the address never goes in a log line"
        assert conn.execute("SELECT trial_noted FROM subscriptions WHERE user_id=?", (uid,)).fetchone()[0] is None
        box, send = _outbox()
        assert TN.run(conn, send=send, now=NOW + HOUR, site="https://example.com", log=lambda *_: None) == 1
        conn.close()


def test_a_moved_trial_end_gets_its_own_reminder():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _member(conn, "you@example.com")
        box, send = _outbox()
        TN.run(conn, send=send, now=NOW, site="https://example.com", log=lambda *_: None)
        conn.execute("UPDATE subscriptions SET period_end=? WHERE user_id=?", (NOW + 22 * HOUR, uid))
        conn.commit()
        assert TN.run(conn, send=send, now=NOW + HOUR, site="https://example.com", log=lambda *_: None) == 1
        conn.close()


def test_the_email_says_when_what_and_how_to_cancel():
    subject, text, html = TN.message(NOW + 20 * HOUR, "monthly", "https://example.com/", now=NOW)
    assert subject == "Your free trial ends tomorrow"
    assert "ends tomorrow, Tue Oct 27, at 8:00 AM ET." in text
    assert "charged $25.00 for the Monthly plan, and every month after that until you cancel." in text
    assert "Manage billing" in text and "you are charged nothing" in text
    assert "https://example.com/#account" in text and 'href="https://example.com/#account"' in html
    assert "Stop these emails" not in text, "a notice about a charge is not a list to leave"
    assert "one reminder we send" in text and "one reminder we send" in html


def test_the_day_word_follows_eastern_time():
    assert TN.when(NOW + 3 * HOUR, NOW)[0] == "today"
    assert TN.when(NOW + 13 * HOUR, NOW)[0] == "tomorrow"        # 1 AM Tuesday
    day, full = TN.when(NOW + 60 * HOUR, NOW)
    assert day == "Thursday" and full == "Thu Oct 29 at 12:00 AM ET"


def test_the_billing_sweep_runs_it():
    launch = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    body = launch[launch.index("def _billing_sweeper()"):]
    body = body[:body.index("\n\n\n")]
    assert body.index("_bi.settle_referrals(conn)") < body.index("_tn.run(conn)")
    assert "trial_noted" in open(os.path.join(ROOT, "engine", "billing.py"), encoding="utf-8").read()


def test_the_terms_promise_it_and_privacy_names_it():
    terms = open(os.path.join(ROOT, "web", "terms.html"), encoding="utf-8").read()
    priv = open(os.path.join(ROOT, "web", "privacy.html"), encoding="utf-8").read()
    assert "About a day before it ends we <b>email you once</b>" in terms
    assert "trial end we last sent the one reminder email about" in priv


def _strip(status, sells=True):
    i = CHAT.index("function lvmTrialHTML(")
    fn = CHAT[i:CHAT.index("\n}\n", i) + 3]
    js = f"""
    const chEsc = (s) => String(s), icon = () => "", tzOpts = (o) => o;
    const tzTime = (d) => new Intl.DateTimeFormat(undefined, {{ hour: "numeric", minute: "2-digit" }}).format(new Date(d));
    const storeSells = () => {json.dumps(sells)};
    const PLANS = [{{ id: "monthly", price: 25, months: 1 }}, {{ id: "yearly", price: 225, months: 12 }}];
    {fn}
    console.log(JSON.stringify(lvmTrialHTML({json.dumps(status)})));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30,
                         env={**os.environ, "TZ": "America/New_York"})
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_live_tab_line_while_the_trial_runs():
    soon = time.time() + 26 * HOUR
    out = _strip({"status": "trialing", "period_end": soon, "plan": "monthly"})
    assert '<a class="lvm-strip lvm-trial" href="#account">' in out
    assert "Your free trial ends" in out and "Then $25 a month. Cancel before then and you pay nothing." in out
    assert _strip({"status": "trialing", "period_end": soon, "cancel_at_end": True}) == "", "gone once they cancel"
    assert _strip({"status": "active", "period_end": soon}) == ""
    assert _strip({"status": "trialing", "period_end": time.time() - 60}) == ""
    assert _strip({"status": "trialing", "period_end": soon}, sells=False) == "", "a store build that sells nothing"
    load = CHAT[CHAT.index("async function lvmLoad("):]
    assert load.index("lvmTrialHTML(") < load.index("isWalled()"), "the trial line comes before the members strip"


def test_in_a_browser_a_trialing_member_sees_it_on_live():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    end = time.time() + 20 * HOUR
    me = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "fan0"}}
    bill = {"configured": True, "signed_in": True, "email": "you@example.com", "paywall": True, "entitled": True,
            "status": "trialing", "period_end": end, "plan": "monthly", "cancel_at_end": False,
            "plans": [{"id": "monthly", "ready": True}]}
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    errs, got = [], None
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/account/me*", ful(json.dumps(me)))
                page.route("**/api/billing/status*", ful(json.dumps(bill)))
                page.route("**/api/alerts/live*", ful(json.dumps({"players": []})))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html#live", wait_until="load")
                for _ in range(30):                 # the page's CSP refuses wait_for_function's eval
                    if page.evaluate("!!document.querySelector('.lvm-trial')"):
                        break
                    page.wait_for_timeout(500)
                got = page.evaluate("""(() => { const a = document.querySelector('.lvm-trial'); const r = a.getBoundingClientRect();
                  return { text: a.textContent.replace(/\\s+/g, ' ').trim(), href: a.getAttribute('href'),
                           fits: r.right <= innerWidth && r.left >= 0 }; })()""")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs[:3]
    assert got["href"] == "#account" and got["fits"], got
    assert "Your free trial ends" in got["text"] and "Then $25 a month." in got["text"], got


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
