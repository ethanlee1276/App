"""Not today? The plans page keeps the door open with the free picks-are-up alert.

The ideas list (2026-10-26): a signed-in reader not ready to pay gets one
button under the two doors that turns on the free "tonight's picks are
up" alert — how many, never which (engine/pushalerts) — and its own off
switch there, since the Alerts page's switches are a members' page. What
these hold (account.js pwLaterHTML / pwLater):

  - shown only signed in, and only where alerts can work (app.js pushKind);
  - once on, it says so instead of asking again, with a Turn off;
  - on keeps whatever else the phone was told and adds "posted"; off takes
    only "posted" away, and drops the phone only when nothing is left.

    python3 tests/test_not_today_keeps_the_door_open.py
    (the browser half with QB_BROWSER_TESTS=1 and Playwright)
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
ACCOUNT = open(os.path.join(ROOT, "web", "js", "account.js"), encoding="utf-8").read()


def _fn(name):
    i = ACCOUNT.index(f"function {name}(")
    return ACCOUNT[i:ACCOUNT.index("\n}\n", i) + 3]


def _later(kind, saved):
    js = f"""
    const icon = () => "", iconMark = () => "";
    const pushKind = () => {json.dumps(kind)}, pushSaved = () => ({json.dumps(saved)});
    {_fn("pwLaterHTML")}
    {_fn("pwLaterOnHTML")}
    console.log(JSON.stringify(pwLaterHTML()));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_only_where_alerts_can_work():
    assert _later("", None) == "" and _later("home-screen", None) == ""
    ask = _later("web", None)
    assert 'data-pwlater="1"' in ask and "Not today — tell me when picks are up" in ask
    assert "how many, never which" in ask
    assert 'data-pwlater="1"' in _later("native", {"endpoint": "x", "topics": ["settled"]}), "settled alone is not this"


def test_once_on_it_says_so_with_its_own_off():
    on = _later("web", {"endpoint": "x", "topics": ["posted", "settled"]})
    assert "You’ll hear when tonight’s picks are up." in on and 'data-pwlater="off">Turn off</button>' in on
    assert 'data-pwlater="1"' not in on


def test_on_adds_to_the_phones_alerts_and_off_takes_only_its_own():
    fn = _fn("pwLater")
    assert 'const topics = [...new Set((saved.topics || []).concat("posted"))];' in fn
    assert "await pushOn(topics.concat(saved.mine || []));" in fn
    assert 'const rest = (saved.topics || []).filter((t) => t !== "posted");' in fn
    assert "if (rest.length || (saved.mine || []).length) {" in fn and "await pushOff(saved);" in fn
    listen = ACCOUNT[ACCOUNT.index('const t = e.target.closest && e.target.closest("[data-flplan]'):]
    assert "[data-pwlater]" in listen[:200] and "if (t.dataset.pwlater) return pwLater(t);" in listen[:600]
    doors = _fn("pwDoorsHTML")
    assert '${signed ? pwLaterHTML() : ""}' in doors


def test_in_a_browser_on_and_off_from_the_plans_page():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    me = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "fan0"}}
    bill = {"configured": True, "signed_in": True, "email": "you@example.com", "paywall": True, "entitled": False,
            "status": "none", "trial_days": 3, "trial_plan": "monthly", "trial_eligible": True,
            "plans": [{"id": "monthly", "ready": True}, {"id": "sixmonth", "ready": True}, {"id": "yearly", "ready": True}]}
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    errs, got = [], {}
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
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html#paywall", wait_until="load")
                for _ in range(30):                 # the page's CSP refuses wait_for_function's eval
                    if page.evaluate("!!document.querySelector('.pw-doors')"):
                        break
                    page.wait_for_timeout(500)
                # A browser whose alerts work, with the push service stood in for.
                page.evaluate("""(async () => { window.__offs = 0;
                  window.pushKind = () => "web";
                  window.pushOn = async (t) => ({ endpoint: "https://push.example/1", topics: t });
                  window.pushOff = async () => { window.__offs++; };
                  await renderPaywall(); })()""")
                page.wait_for_timeout(500)
                got["ask"] = page.evaluate("!!document.querySelector('[data-pwlater=\"1\"]')")
                page.evaluate("document.querySelector('[data-pwlater=\"1\"]').click()")
                page.wait_for_timeout(500)
                got["on"] = page.evaluate("""({ shown: !!document.querySelector('.pw-later.on'),
                  saved: JSON.parse(localStorage.getItem('qb_push') || 'null') })""")
                page.evaluate("document.querySelector('[data-pwlater=\"off\"]').click()")
                page.wait_for_timeout(500)
                got["off"] = page.evaluate("""({ ask: !!document.querySelector('[data-pwlater=\"1\"]'), offs: window.__offs,
                  saved: localStorage.getItem('qb_push') })""")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs[:3]
    assert got["ask"], got
    assert got["on"]["shown"] and got["on"]["saved"]["topics"] == ["posted"], got
    assert got["off"] == {"ask": True, "offs": 1, "saved": None}, got


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
