"""The account and utility screens read like a phone's own settings.

2026-10-25, Ethan: "we need to fix the visuals of the app. I need u to audit
the whole thing. The settings and account area and shit like that is ugly
and doesn't look like real settings and more shit like that is the same.
Check all of it." The audit is docs/VISUAL_AUDIT.md (G1-G9 across the app,
S1-S15 on the account and utility screens). What it changed, and what holds
it here:

  - THE BROWSER WAS NEVER TOLD THE PAGE IS DARK, so it drew its own light
    controls: a white checkbox on sign-up, a white bankroll box, blue
    checkboxes on Alerts. `color-scheme` is set on both themes, and every
    field shares one style.
  - EVERY BUTTON SHOUTED, uppercase and spaced. Sentence case now.
  - SETTINGS WAS A STACK OF CARDS: the whole plans advert, two fantasy cards
    of paragraphs, a card of pill rows with a paragraph under each, Sign out
    and Delete hidden in a disclosure. It is groups of rows now, the way a
    phone draws its own: an icon tile, the name, the value, then a chevron
    (a screen of its own, with a way back), a switch, or a segmented control
    for two or three choices. Destructive rows last, in red.
  - THE ROWS ARE SHARED (app.js setItem/setGroup/setSwitch): the Alerts
    page's checkboxes are switches in the same rows, the Friends tab and the
    Membership screen are rows. A row that acts (Manage billing, Copy my
    invite link) keeps its tile and chevron while it works; the old buttons
    replaced their own text, which on a row would have flattened it.
  - SIGN-IN had placeholder-only fields and a grey Log in. The fields are
    labelled and Log in is gold; sign-up asks its question before its button.
  - THERE IS NO FREE PLAN (tests/test_free_trial.py), so a reader without a
    subscription reads "No membership", never "Free".

Run directly: `python3 tests/test_settings_read_like_a_phones_own.py`
(the browser half with QB_BROWSER_TESTS=1 and Playwright)
"""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
from _app import styles_css  # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
ACCT = open(os.path.join(ROOT, "web", "js", "account.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
ALL_CSS = styles_css()
HTML = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def _block(sel):
    i = CSS.index(sel)
    return CSS[i:CSS.index("}", i)]


# --- the whole app --------------------------------------------------------------
def test_the_browser_is_told_which_theme_is_showing():
    assert CSS.count("\n:root {") == 1 and CSS.count(':root[data-theme="light"] {') == 1
    assert "color-scheme: dark;" in _block("\n:root {"), "the browser draws light checkboxes on the dark page"
    assert "color-scheme: light;" in _block(':root[data-theme="light"] {')


def test_buttons_speak_in_sentence_case():
    i = CSS.index("APP CONTROLS (2026-10-25")
    tail = CSS[i:]
    btn = tail[tail.index("\n.btn {"):]
    btn = btn[:btn.index("}")]
    assert "text-transform: none;" in btn and "letter-spacing: 0;" in btn and "border-radius: 999px;" in btn
    assert ".tb-ask { text-transform: none; letter-spacing: 0; }" in tail, "the Ask pill is a button too"


def test_one_field_style_and_gold_checkboxes():
    i = CSS.index(":where(input:not([type])")
    field = CSS[i:CSS.index("}", i)]
    # A filled well, no outline, since 2026-10-27 (tests/test_no_hard_lines).
    for want in ("background-color: var(--fill-tone)", "solid transparent", "border-radius: var(--radius-sm)", "min-height: 44px"):
        assert want in field, want
    assert re.search(r':where\(input\[type="checkbox"\], input\[type="radio"\]\) \{[^}]*accent-color: var\(--brand-solid\)', CSS)
    # The pages that drew their own boxes defer to it.
    assert ".mb-form input, .mb-form select { font-weight: 400; }" in CSS
    assert ".acct-row input { flex: 1 1 200px; min-width: 0; }" in CSS
    assert 'class="bk-field"' in HTML and "bankroll-inputs" not in HTML and "bankroll-inputs" not in CSS


# --- the settings rows ------------------------------------------------------------
def test_the_rows_live_where_both_pages_reach_them():
    for name in ("setIco", "setItem", "setGroup", "setSwitch"):
        assert APP.count(f"function {name}(") == 1, f"{name} belongs to app.js (the Alerts page draws rows too)"
        assert f"function {name}(" not in ACCT, f"a second {name} in account.js would replace app.js's"
    sw = _fn(APP, "setSwitch")
    assert 'role="switch" aria-checked="${on ? "true" : "false"}"' in sw
    assert 'aria-pressed="${v === value ? "true" : "false"}"' in _fn(ACCT, "setSeg")
    item = _fn(APP, "setItem")
    assert 'set-item${ico || lead ? "" : " bare"}' in item, "a row without a tile starts its hairline at the text"


def test_settings_is_groups_of_rows_with_the_destructive_ones_last():
    rows = _fn(ACCT, "setListHTML")
    assert rows.count("setGroup(") >= 5, "the settings are a handful of groups"
    for gone in ("set-row", "set-opt", "acct-more"):
        assert gone not in ACCT, f"{gone}: the pill rows and the hidden disclosure are back"
    i = rows.index('title: "Sign out"')
    assert "danger: true" in rows[i:i + 200] and "danger: true" in rows[rows.index('title: "Delete account"'):][:200]
    assert rows.rindex("setGroup(") < i, "Sign out and Delete are the last group"
    for seg in ('setSeg("odds"', 'setSeg("stake"'):
        assert seg in rows, f"two or three choices are a segmented control: {seg}"
    assert 'data-set-switch="teamColors"' in rows


def test_every_row_that_opens_a_screen_has_that_screen_and_a_way_back():
    pages = _fn(ACCT, "setPageHTML")
    opened = set(re.findall(r'data-set-open="([a-z]+)"', _fn(ACCT, "setListHTML") + _fn(ACCT, "planRowsHTML")))
    assert {"password", "plan", "code", "tz", "leagues", "teams", "fantasy", "calendar"} <= opened, opened
    for p in opened:
        assert f'page === "{p}"' in pages, f"the {p} row opens nothing"
    assert '<button type="button" class="set-back" data-set-open="">' in pages
    assert 'class="qb-settings set-screen${_setPage ? " set-page" : ""}"' in _fn(ACCT, "settingsHTML")


def test_a_row_that_acts_keeps_its_shape_while_it_works():
    for name in ("_billGo", "copyRawURL"):
        body = _fn(APP, name)
        assert 'btn.classList.contains("set-item") && btn.querySelector(".set-title")' in body, name
    go = _fn(APP, "_billGo")
    assert 'box.querySelector(".bill-note, .pw-lapse-note")' in go, "a billing error has its own line"
    assert "billSubscribe" not in APP and "billSubscribe" not in ACCT, "nothing draws it any more"


# --- membership, sign-in, alerts, friends -----------------------------------------
def test_the_membership_screen_is_rows_and_never_a_free_plan():
    panel = _fn(ACCT, "planPanelHTML")
    assert 'return setGroup("Your plan", [' in panel and "setItem({ title: k, val: v })" in panel
    bill = ACCT[ACCT.index("async function renderBilling("):]
    bill = bill[:bill.index("\n}\n")]
    assert 'title: "No membership"' in bill and '"Free"' not in ACCT
    assert 'title: "Manage billing"' in bill and 'data-act="billPortal"' in bill
    code = _fn(ACCT, "codeBoxHTML")
    assert '<section class="set-group code-box">' in code and 'class="set-foot code-note"' in code \
        and 'class="acct-note' not in code, \
        "the code's note is not an .acct-note (those all carry the sync line)"
    assert 'if (own && s) own.innerHTML = codeBoxHTML(s.codes || {});' in _fn(ACCT, "codeScreenRedraw")


def test_sign_in_fields_are_labelled_and_the_action_is_gold():
    assert '<span class="acct-field-k">Email</span>' in _fn(APP, "acctEmailHTML")
    assert '<span class="acct-field-k">${label}</span>' in _fn(APP, "acctPwHTML")
    fields = _fn(APP, "acctFieldsHTML")
    assert '<button class="btn primary"\n        data-act="acctAuth"' in fields, "Log in is the gold button too"
    assert fields.index("${beforeButton}") < fields.index('data-act="acctAuth"')
    # The sign-up screen is the account room's since 2026-10-25 (js/account.js).
    assert '${acctFieldsHTML("signup", `' in _fn(ACCT, "signupHTML"), "the age box comes before Create account"
    card = _fn(ACCT, "acctSignInHTML")
    assert "acct-brand" not in card and "<svg" not in card, "the decorative eye is gone"
    assert ".acct-field { display: grid; gap: 6px; min-width: 0; }" in CSS, \
        "no flex basis: in the stacked form it became each field's height"


def test_alerts_are_switches_in_rows():
    # The Alerts page's renderer lives in js/more.js since 2026-10-29 (loaded on first use).
    more = open(os.path.join(ROOT, "web", "js", "more.js"), encoding="utf-8").read()
    zone = more[more.index("function renderPushZone(note) {"):more.index("\nfunction renderAlerts() {")]
    assert 'type="checkbox"' not in zone and "setSwitch(" in zone and "setGroup(" in zone
    assert '[data-push-topic][aria-checked="true"]' in zone, "the choice is read off the switches"
    assert 'host.classList.toggle("push-off", !on);' in zone
    assert ".push-off .switch[data-push-topic] { opacity: .55; }" in CSS


def test_friends_are_rows():
    fr = _fn(ACCT, "friendsCardHTML")
    assert "setGroup(\"Friends\"" in fr and "lead: msgAvatar(f.name)" in fr
    assert 'attrs: `data-copy-invite="${escapeAttr(inv.token)}"`' in fr and 'attrs: "data-revoke-invite"' in fr
    assert "fr-chip" not in ACCT and ".fr-chip" not in ALL_CSS


# --- in a browser -------------------------------------------------------------------
NOW = int(time.time())
ME = {"signed_in": True, "email": "you@example.com", "insecure": False, "allowed": True, "reset_by_email": True,
      "profile": {"handle": "tester", "name": "Tester", "bio": "", "color": "gold"}}
FEED_ME = {"me": {"handle": "tester", "name": "Tester", "bio": "", "followers": 0, "following": 0, "posts": 0,
                  "verified": False}, "signed_in": True, "unseen": 0}
BILL = {"configured": True, "signed_in": True, "entitled": True, "status": "active", "plan": "monthly",
        "period_end": NOW + 30 * 86400, "customer_id": "cus_test", "note": "Subscribed.", "live": True, "codes": {}}


def _browser():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return None
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        print("      (skipped: no Playwright)")
        return None
    return True


def _page(browser, port, body, signed_in, w=390, h=844, tab=""):
    ctx = browser.new_context(viewport={"width": w, "height": h}, is_mobile=True, has_touch=True,
                              service_workers="block", reduced_motion="reduce")
    page = ctx.new_page()
    page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done');"
                         + (f" sessionStorage.setItem('qb_acct_tab', '{tab}');" if tab else "") + " } catch (e) {}")
    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
    j = lambda obj: (lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(obj)))
    for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
    if signed_in:
        page.route("**/api/account/me*", j(ME))
        page.route("**/api/feed/me*", j(FEED_ME))
        page.route("**/api/feed/profile*", j({"profile": FEED_ME["me"], "posts": [], "more": False}))
        page.route("**/api/billing/status*", j(BILL))
        page.route("**/api/account/digest*", j({"available": True, "morning": True, "nightly": False}))
        page.route("**/api/account/data*", j({"sections": {}}))
        page.route("**/api/social/me*", j({"friends": [{"id": 7, "name": "Maya Ortiz"}], "inbox": [], "requests": [],
                                           "invite": {"token": "tok", "expires_in_s": 604800}}))
    return ctx, page


def test_in_a_browser_settings_behave_like_a_phones_own():
    if not _browser():
        return
    from playwright.sync_api import sync_playwright
    import rendercheck
    from test_every_page_opens_clean import _board
    body = json.dumps(_board())
    srv, port = rendercheck._serve()
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                # Signed in, the Settings tab.
                ctx, page = _page(browser, port, body, True, tab="settings")
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#account", wait_until="load")
                page.wait_for_function("() => document.querySelectorAll('.qb-settings .set-group').length >= 5"
                                       " && document.querySelector('.qb-settings').offsetParent", timeout=15000)
                page.wait_for_timeout(600)
                got["list"] = page.evaluate("""() => ({
                  groups: document.querySelectorAll('.qb-settings .set-group').length,
                  short: [...document.querySelectorAll('.qb-settings .set-item')].filter((r) => r.offsetParent && r.getBoundingClientRect().height < 44).length,
                  plan: (document.querySelector('[data-set-open="plan"] .set-val') || {}).textContent || '',
                  danger: [...document.querySelectorAll('.qb-settings .set-item.danger .set-title')].map((e) => e.textContent.trim()),
                  wide: document.documentElement.scrollWidth - innerWidth })""")
                page.click('.set-seg button[data-set-val="decimal"]')
                page.wait_for_timeout(300)
                got["decimal"] = page.evaluate("() => document.querySelector('.set-seg button[data-set-val=\"decimal\"]').getAttribute('aria-pressed')")
                page.click('[data-set-open="tz"]')
                page.wait_for_timeout(300)
                got["tz"] = page.evaluate("() => ({ page: !!document.querySelector('.qb-settings.set-page'), h: (document.querySelector('.set-page-h') || {}).textContent })")
                page.click('[data-set-key="tz"][data-set-val="America/Chicago"]')
                page.wait_for_timeout(300)
                got["tz_pick"] = page.evaluate("() => !!document.querySelector('[data-set-val=\"America/Chicago\"] .set-check')")
                page.click(".set-back")
                page.wait_for_timeout(300)
                got["back"] = page.evaluate("() => !document.querySelector('.qb-settings.set-page') && !!document.querySelector('[data-set-open=\"tz\"]')")
                page.click('[data-set-open="plan"]')
                page.wait_for_function("() => document.querySelector('[id=\"billing-slot\"] .set-group')", timeout=8000)
                got["plan_page"] = page.evaluate("""() => ({
                  rows: [...document.querySelectorAll('[id="billing-slot"] .set-title')].map((e) => e.textContent.trim()),
                  code: !!document.querySelector('[id="billing-slot"] .code-row input'),
                  flat: getComputedStyle(document.querySelector('.qb-settings'), null).getPropertyValue('max-width') })""")
                page.set_viewport_size({"width": 320, "height": 700})
                page.click(".set-back")
                page.wait_for_timeout(400)
                got["narrow"] = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
                ctx.close()

                # Signed out: the sign-in screen, and one fantasy host.
                ctx, page = _page(browser, port, body, False)
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#account", wait_until="load")
                page.wait_for_selector(".acct-signin", timeout=15000)
                got["signin"] = page.evaluate("""() => ({
                  labels: [...document.querySelectorAll('.acct-signin .acct-field-k')].map((e) => e.textContent.trim()),
                  bg: getComputedStyle(document.querySelector('.acct-signin [data-act="acctAuth"]')).backgroundColor,
                  hosts: document.querySelectorAll('[id="ffl-sleeper"]').length })""")
                page.click('[data-set-open="fantasy"]')
                page.wait_for_timeout(500)
                got["fantasy"] = page.evaluate("() => ({ hosts: document.querySelectorAll('[id=\"ffl-sleeper\"]').length, filled: !!(document.querySelector('[id=\"ffl-sleeper\"]') || {}).innerHTML })")
                ctx.close()

                # Alerts: a kind's switch is a choice while alerts are off.
                ctx, page = _page(browser, port, body, True)
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#alerts", wait_until="load")
                page.wait_for_timeout(2500)
                zone = page.evaluate("() => !!document.querySelector('[data-push-topic=\"posted\"]')")
                if zone:
                    before = page.evaluate("() => document.querySelector('[data-push-topic=\"posted\"]').getAttribute('aria-checked')")
                    page.click('[data-push-topic="posted"]')
                    page.wait_for_timeout(200)
                    after = page.evaluate("() => document.querySelector('[data-push-topic=\"posted\"]').getAttribute('aria-checked')")
                    got["alerts"] = (before, after, page.evaluate("() => document.getElementById('push-zone').classList.contains('push-off')"))
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    lst = got["list"]
    assert lst["groups"] >= 6 and lst["short"] == 0 and lst["wide"] <= 0, lst
    assert lst["plan"].startswith("Monthly"), lst
    assert lst["danger"] == ["Sign out", "Delete account"], lst
    assert got["decimal"] == "true", got
    assert got["tz"] == {"page": True, "h": "Time zone"} and got["tz_pick"] and got["back"], got
    rows = got["plan_page"]["rows"]
    assert "Monthly plan" in rows and "Price" in rows and "Renews" in rows and "Manage billing" in rows, got["plan_page"]
    assert got["plan_page"]["code"], got["plan_page"]
    assert got["narrow"] <= 0, ("the settings list scrolls sideways at 320px", got["narrow"])
    si = got["signin"]
    assert si["labels"] == ["Email", "Password"], si
    assert si["bg"] not in ("rgba(0, 0, 0, 0)", "transparent"), si
    assert si["hosts"] == 0 and got["fantasy"] == {"hosts": 1, "filled": True}, got
    if "alerts" in got:
        before, after, off = got["alerts"]
        assert before != after and off, got["alerts"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
