"""The site's own account always finds its desk, and the desk is one page.

Ethan, 2026-11-02, signed in as @Qellys_Book, on its profile's Settings:
"it's not giving me access to the page. It should give this account access.
Also The Who's on and owners page should be one page".

The server let that account in (engine/whoson.is_site_account) and told the
page so (`whoson` on /api/account/me). The page lost the word: a sign-in on
the page — a password, a reset link, a passkey, a texted code — set the
account to the sign-in's own answer, {signed_in, email}, until the next
load, and Settings drew the desk's rows from `whoson` at the very bottom,
under Help. These hold:

  * every sign-in on the page asks the server who this is at once
    (app.js acctMeAgain); a failed ask, or one that has not seen the
    cookie yet, keeps what the sign-in said;
  * the site's own account's group heads Settings, one row: Owner desk;
  * its own profile carries a row to the desk, under the date it joined;
  * Who's on now is the desk's first card, on its own ten-second clock; an
    old #whoson link opens the desk;
  * in a browser: the old link lands on the desk, the account a sign-in
    left half-known finds its desk first in Settings, and the card's redraw
    leaves a notice being written alone.

Run directly: `python3 tests/test_the_site_account_finds_its_desk.py`
(the browser checks with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
APP = READ("web", "js", "app.js")
ACCT = READ("web", "js", "account.js")
SOCIAL = READ("web", "js", "social.js")
OWNER = READ("web", "js", "owner.js")


def _fn(src, name):
    i = src.index(f"function {name}(")
    if src[max(0, i - 6):i] == "async ":
        i -= 6
    return src[i:src.index("\n}\n", i) + 2]


def test_every_sign_in_on_the_page_asks_who_this_is():
    sets = [(name, m.start()) for name, src in (("app.js", APP), ("account.js", ACCT))
            for m in re.finditer(r"_acctUser = \{ signed_in: true", src)]
    assert len(sets) == 4, sets                     # a password, a reset link, a passkey, a texted code
    for name, at in sets:
        src = APP if name == "app.js" else ACCT
        assert "acctMeAgain()" in src[at:at + 260], (name, src[at:at + 260])    # after pushRelink, where there is one
    node = shutil.which("node")
    if not node:
        return
    prog = """
      let _acctUser = { signed_in: true, email: "site@example.com" };
      const state = { view: "account" };
      let repainted = 0;
      const setRepaint = () => { repainted++; };
      let answer;
      global.fetch = async () => answer();
    """ + _fn(APP, "acctMeAgain") + """
      (async () => {
        answer = async () => ({ ok: true, json: async () => ({ signed_in: true, email: "site@example.com", whoson: true,
                                                             profile: { handle: "Qellys_Book", verified: true } }) });
        await acctMeAgain();
        const full = JSON.parse(JSON.stringify(_acctUser));
        _acctUser = { signed_in: true, email: "fan@example.com" };
        answer = async () => { throw new Error("offline"); };
        await acctMeAgain();
        const kept = JSON.parse(JSON.stringify(_acctUser));
        answer = async () => ({ ok: true, json: async () => ({ signed_in: false }) });
        await acctMeAgain();
        const still = JSON.parse(JSON.stringify(_acctUser));
        const before = repainted;
        state.view = "live";
        await acctMeAgain();
        console.log(JSON.stringify({ full, kept, still, before, after: repainted }));
      })();
    """
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got["full"]["whoson"] is True and got["full"]["profile"]["handle"] == "Qellys_Book", got["full"]
    assert got["kept"] == {"signed_in": True, "email": "fan@example.com"}, "a failed ask keeps the sign-in's answer"
    assert got["still"] == got["kept"], "an answer that has not seen the cookie yet signs nobody out"
    assert got["before"] == 3 and got["after"] == 3, "Settings is drawn again only where it is open"


def test_the_desk_heads_settings_and_the_profile_for_the_site_account():
    body = _fn(ACCT, "setListHTML")
    assert body.index("if (inn && u.whoson) {") < body.index('out.push(setGroup("Account"'), "the desk heads the list"
    group = body[body.index("if (inn && u.whoson) {"):body.index('out.push(setGroup("Account"')]
    assert group.count("setItem(") == 1 and 'title: "Owner desk"' in group and 'href: "#owner"' in group
    assert "Who’s on now" in group, "the row names the card the old page became"
    assert 'href: "#whoson"' not in ACCT
    # Its own profile: a row to the desk, by the server's own rule or its word.
    assert 'p.verified && String(p.handle || "").toLowerCase() === "qellys_book"' in SOCIAL
    assert "_acctUser && _acctUser.whoson" in SOCIAL
    head = SOCIAL[SOCIAL.index("function profileHeaderHTML("):SOCIAL.index("function followsHTML(")]
    assert 'o.mine && siteDesk(p) ? `<a class="fd-prof-desk" href="#owner">' in head and "<b>Owner desk</b>" in head
    assert head.index("Joined ${") < head.index('class="fd-prof-desk"') < head.index('class="fd-pstats"')


def test_the_desk_is_one_page_with_its_own_clock_for_who_is_on():
    assert "const WO_EVERY_MS = 10000;" in OWNER and "const OD_EVERY_MS = 60000;" in OWNER
    render = _fn(OWNER, "renderOwner")
    assert "odFill();" in render and "woFill();" in render and "woTick();" in render
    fill = _fn(OWNER, "woFill")
    assert 'document.getElementById("od-who")' in fill and "card.innerHTML = odWhoInner(" in fill, \
        "only the card is redrawn on the fast clock"
    page = _fn(OWNER, "odHTML")
    assert page.index("odNeedsHTML(d.needs)") < page.index('id="od-who"') < page.index("odNoticeHTML(d.notice)")
    route = _fn(APP, "ownerRoute")
    assert 'if (h !== "whoson") return false;' in route and 'history.replaceState({ view: "owner" }, "", "#owner")' in route
    assert APP.count("if (feedRoute(h)) return;\n  if (ownerRoute(h)) return;") == 1, "the boot router"
    assert APP.count("if (feedRoute(h)) return;\n    if (ownerRoute(h)) return;") == 1, "the hash router"


SNAP = {"at": 1_793_600_000, "window_s": 150, "members_total": 1, "visitors": 1, "unnamed_members": 0,
        "members": [{"handle": "SharpSam", "name": "Sam", "color": 3, "view": "likely", "detail": "nfl",
                     "tabs": 1, "on_page_s": 60, "on_site_s": 300, "seen_s": 5}],
        "pages": [{"view": "likely", "detail": "nfl", "members": 1, "visitors": 1}]}
DESK = {"at": 1_793_600_000, "now": {"members": 1, "visitors": 1, "pages": 1}, "switches": [], "alerts": {"phones": 1},
        "notice": None, "needs": []}
ME = {"signed_in": True, "email": "site@example.com", "whoson": True,
      "profile": {"handle": "Qellys_Book", "name": "Qellys Book", "verified": True, "founder": False, "color": 0}}


def test_in_a_browser_the_old_link_the_settings_and_the_card():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    srv, port = rendercheck._serve()
    base = f"http://127.0.0.1:{port}"
    got, errors = {}, []
    js_json = lambda body: (lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body)))  # noqa: E731
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                def fresh():
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
                    page = ctx.new_page()
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.route(lambda u: not u.startswith(base + "/"), lambda r: r.abort())
                    page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}catch(e){}")
                    return ctx, page

                def wait(page, fn, arg=None, tries=60):
                    for _ in range(tries):
                        if page.evaluate(fn, arg):
                            return True
                        page.wait_for_timeout(250)
                    return False

                # 1. An old #whoson link, signed out: the desk, which says whose it is.
                ctx, page = fresh()
                page.goto(f"{base}/index.html#whoson", wait_until="load")
                wait(page, "() => /only for the site/.test((document.getElementById('owner-body') || {}).textContent || '')")
                got["old_link"] = page.evaluate("""() => ({ hash: location.hash,
                    on: !!document.querySelector('#view-owner.active'),
                    said: (document.getElementById('owner-body') || {}).textContent || '' })""")
                ctx.close()

                # 2. A sign-in on the page left the account half-known: the server is asked, and
                #    the desk heads Settings without a reload.
                ctx, page = fresh()
                me = {"now": {"signed_in": False}}
                page.route("**/api/account/me*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                     body=json.dumps(me["now"])))
                page.route("**/api/billing/status*", js_json({"paywall": False, "entitled": True}))
                page.goto(f"{base}/index.html#live", wait_until="load")
                page.wait_for_timeout(1500)
                me["now"] = ME
                page.evaluate("""async () => { _acctUser = { signed_in: true, email: "site@example.com" };
                                              await acctMeAgain(); location.hash = "#account"; }""")
                wait(page, "() => !!document.querySelector('.qb-settings .set-group-h')")
                got["settings"] = page.evaluate("""() => {
                    const heads = [...document.querySelectorAll('.qb-settings .set-group-h')].map((h) => h.textContent);
                    const first = document.querySelector('.qb-settings .set-group');
                    return { heads, first: first ? first.textContent.replace(/\\s+/g, ' ') : '',
                             link: !!document.querySelector('.qb-settings a[href="#owner"]'), whoson: !!_acctUser.whoson }; }""")
                ctx.close()

                # 3. The desk as the site account: the card names who is on, and its redraw
                #    leaves a notice being written alone.
                ctx, page = fresh()
                page.route("**/api/account/me*", js_json(ME))
                page.route("**/api/billing/status*", js_json({"paywall": False, "entitled": True}))
                page.route("**/api/owner/desk*", js_json(DESK))
                page.route("**/api/owner/whoson*", js_json(SNAP))
                page.goto(f"{base}/index.html#owner", wait_until="load")
                wait(page, "() => /@SharpSam/.test((document.getElementById('od-who') || {}).textContent || '')")
                page.fill("#od-text", "Tonight's picks are late")
                page.evaluate("async () => { _woBusy = false; await woFill(); }")
                got["desk"] = page.evaluate("""() => ({
                    card: (document.getElementById('od-who') || {}).textContent || '',
                    typed: (document.getElementById('od-text') || {}).value || '',
                    first: (document.querySelector('#owner-body > .od-card') || {}).id || '' })""")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errors, errors
    o = got["old_link"]
    assert o["hash"] == "#owner" and o["on"], o
    assert "only for the site’s own account" in o["said"], o["said"][:300]
    st = got["settings"]
    assert st["whoson"] and st["link"], st
    assert st["heads"][0] == "The site’s own account", st["heads"]
    assert "Owner desk" in st["first"] and "Who’s on now" in st["first"], st["first"][:300]
    d = got["desk"]
    assert "@SharpSam" in d["card"] and "Most Likely" in d["card"] and "Every page open" in d["card"], d["card"][:400]
    assert d["typed"] == "Tonight's picks are late", "the card's redraw never touches the notice being written"
    assert d["first"] == "od-who", "Who's on now is the desk's first card"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
