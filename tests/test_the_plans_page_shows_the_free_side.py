"""The plans page leads with the free side, and every button goes somewhere.

Ethan, 2026-10-26: "the paywall page also makes it seem like everything is
still locked on a paid service. It doesn't give u an option to create an
account or anything ... People need to know that there is free features
available." What these hold:

  - the page opens on two doors, the free account and the membership, each
    with its own button, ahead of the pitch;
  - signed out, the top bar and the free door both say "sign up free", and a
    plan's button goes to the sign-up with the plan kept (checkout straight
    after), not to a log-in page;
  - signed in without a plan, the free door says so and leads back to the
    live games;
  - the store build, which names no price, says what is free too.

    python3 tests/test_the_plans_page_shows_the_free_side.py
    (the browser half with QB_BROWSER_TESTS=1 and Playwright)
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
ACCOUNT = open(os.path.join(ROOT, "web", "js", "account.js"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def _doors(status, trial):
    rows = ACCOUNT[ACCOUNT.index("const FL_ROWS = ["):ACCOUNT.index("];", ACCOUNT.index("const FL_ROWS = [")) + 2]
    js = f"""
    const escapeHtml = (s) => String(s), iconMark = () => "", pwLaterHTML = () => "<later>";
    const PLANS = [{{ id: "monthly", name: "Monthly", price: 25, months: 1 }}, {{ id: "yearly", name: "Yearly", price: 225, months: 12 }}];
    const planPerMonth = (p) => p.price / p.months;
    const bestValuePlanId = () => "yearly";
    {rows}
    {_fn(ACCOUNT, "pwDoorsHTML")}
    console.log(JSON.stringify(pwDoorsHTML({json.dumps(status)}, {trial})));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_page_opens_on_two_doors_ahead_of_the_pitch():
    body = _fn(ACCOUNT, "paywallHTML")
    assert body.index("${pwDoorsHTML(status, trialOK && sellable(trialPlan) ? trialDays : 0)}") \
        < body.index('<section class="pw-hero">')
    out = _doors({"signed_in": False}, 3)
    assert out.index('<article class="pw-door free">') < out.index('<article class="pw-door mem">'), "the free side first"
    assert 'data-act="acctGoSignup">Create a free account</button>' in out
    assert "Every game live" in out and "The Pick of the Day, every league" in out
    assert "Every other pick tonight" in out, "the members' side names the rest of the board"
    assert 'data-act="pwToPlans">Start 3 days free</button>' in out, "to the plan card's fine print, not checkout"
    assert "$25 a month · 3 days free · or $18.75 a month yearly" in out


def test_signed_in_without_a_plan_the_free_door_says_so():
    out = _doors({"signed_in": True}, 0)
    assert "You have this" in out and 'href="#live">Go to the live games</a>' in out
    assert "Create a free account" not in out and "See the plans</button>" in out, "no trial on offer, none promised"
    assert "<later>" in out and "<later>" not in _doors({"signed_in": False}, 3), "not today, for a signed-in reader"


def test_signed_out_every_buy_button_goes_through_the_free_sign_up():
    body = _fn(ACCOUNT, "paywallHTML")
    assert "const join = (id) => (status && status.signed_in ? 'data-act=\"coStart\"' : `data-pwjoin=\"${escapeAttr(id)}\"`);" in body
    assert body.count("${join(") == 3, "the plan card, the longer plans and the FAQ's button"
    assert 'data-act="coStart"' not in body.replace("'data-act=\"coStart\"'", ""), "no buy button skips the check"
    assert '<button class="btn primary pw-join" data-act="acctGoSignup">Sign up free</button>' in body
    join = _fn(ACCOUNT, "pwJoin")
    assert "rememberPendingPlan(pl.id);" in join and 'switchView("signup", true);' in join
    render = _fn(ACCOUNT, "renderSignup")
    assert "if (!introSeen() && !_pendingPlanPeek()) {" in render, "a buyer skips the tour"
    assert '<p class="fsu-plan-note" role="status">${escapeHtml(_suNote)}</p>' in _fn(ACCOUNT, "signupHTML")


def test_checkouts_own_signed_out_answer_opens_the_sign_up():
    pay = APP[APP.index("window.coPay = async function"):]
    pay = pay[:pay.index("\n};\n")]
    assert 'setTimeout(() => { _switchViewNow("signup", false, 0); }, 1200);' in pay
    assert '_switchViewNow("account", false, 0)' not in pay


def test_the_store_page_says_what_is_free_too():
    store = _fn(ACCOUNT, "storePaywallHTML")
    assert "Every game live, the game chat and Call it are free with an account." in store
    assert 'data-act="acctGoSignup">Create a free account</button>' in store


def test_in_a_browser_a_stranger_finds_the_free_door_and_a_plan_carries_through():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    plans = [{"id": "monthly", "ready": True}, {"id": "sixmonth", "ready": True}, {"id": "yearly", "ready": True}]
    bill = {"configured": True, "signed_in": False, "plans": plans, "trial_days": 3, "trial_plan": "monthly",
            "paywall": True, "account_wall": True}
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
                page.route("**/api/billing/status*", ful(json.dumps(bill)))
                page.route("**/api/account/me*", ful(json.dumps({"signed_in": False, "account_wall": True})))
                page.route("**/api/firstlook*", ful(json.dumps({"tonight": []})))
                page.goto(f"http://127.0.0.1:{port}/#paywall", wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                got["door"] = page.evaluate("""(() => { const b = document.querySelector('.pw-door.free .pw-door-go');
                  const r = b && b.getBoundingClientRect(); return b ? [b.textContent.trim(), r.top < innerHeight] : null; })()""")
                page.evaluate("document.querySelector('[data-pwjoin=\"yearly\"]').click()")
                page.wait_for_timeout(1500)
                got["after"] = page.evaluate("""({ view: state.view, plan: localStorage.getItem('qb_pending_plan'),
                  note: (document.querySelector('.fsu-plan-note') || {}).textContent || '', tour: !!document.querySelector('.wiz') })""")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs[:3]
    assert got["door"] == ["Create a free account", True], f"the free door is not on the first screen: {got['door']}"
    a = got["after"]
    assert a["view"] == "signup" and a["plan"] == "yearly" and "yearly plan" in a["note"] and not a["tour"], a


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
