"""A page that only some visits open loads when it opens, once, and never
mixes two versions of the site.

Ethan, 2026-10-24: "keep going and finish everything". The Record page,
the game, pick and play-by-play pages, the account pages and the rest of the
More menu moved out of app.js into rooms loaded on first use (app.js
loadRoom), as Fantasy and Rocket Radar had: app.js 450.5 -> 284.2 KB gz, a
first visit 570 -> 398.9. What these hold:

  - the first screen fetches none of the rooms;
  - opening a room's page fetches its script once (and its styles first,
    when it has any), and a second visit fetches nothing;
  - after a deploy the service worker takes over an open page still running
    the old app.js (register-sw.js marks it QB_STALE): a room asked for then
    reloads the page into the page that was asked for, rather than running
    the new version's room on the old app.js — and the first install is not
    an update;
  - a room that cannot arrive says so on the page that asked for it, and
    opening the page again tries again.

Run directly: `python3 tests/test_a_room_loads_when_its_page_opens.py` (the
browser half with QB_BROWSER_TESTS=1 and Playwright)
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
READ = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()  # noqa: E731
APP, REG = READ("web", "js", "app.js"), READ("web", "js", "register-sw.js")


def test_the_loader_reloads_a_stale_page_and_says_when_a_room_failed():
    at = APP.index("function loadRoom(js, css) {")
    fn = APP[at:APP.index("\n}\n", at)]
    assert "if (window.QB_STALE) {" in fn and "setTimeout(() => location.reload(), 0);" in fn
    assert "rooms.delete(js)" in fn, "a failed load can be tried again"
    assert fn.index("const style") < fn.index('s.src = js;'), "the styles are asked for first"
    call = APP[APP.index("function roomCall("):APP.index("function roomFailed(")]
    assert "window[name] !== stub" in call and "roomFailed()" in call
    assert 'class="room-failed empty"' in APP


def test_only_an_update_marks_the_page_stale():
    assert "var hadWorker = !!navigator.serviceWorker.controller;" in REG
    at = REG.index('addEventListener("controllerchange"')
    body = REG[at:REG.index("});", at)]
    assert body.index("if (!hadWorker) { hadWorker = true; return; }") < body.index("window.QB_STALE = true;")


def test_every_room_is_shipped_trimmed_and_kept_by_the_installed_app():
    from engine import shrink
    sw, caddy = READ("web", "sw.js"), READ("deploy", "Caddyfile")
    rooms = sorted(set(re.findall(r'roomCall\(\w+, "\w+", "(js/[a-z0-9_-]+\.js)"', APP)))
    assert {"js/record.js", "js/detail.js", "js/account.js", "js/more.js", "js/fantasy.js", "js/memes.js"} <= set(rooms)
    for js in rooms:
        assert js in shrink.FILES, f"{js} is served with its comments"
        assert f'"/{js}"' in sw, f"{js} is not in the installed app's copy"
        assert f"/{js}" in caddy[caddy.index("@trimmed {"):], f"Caddy does not serve {js} trimmed"


def test_in_a_browser_a_room_loads_once_when_its_page_opens():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import rendercheck
    srv, port = rendercheck._serve()
    origin = f"http://127.0.0.1:{port}"
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
                page = ctx.new_page()
                asked, errors = [], []
                page.on("request", lambda r: asked.append(r.url.split("?")[0].replace(origin, "")))
                page.on("pageerror", lambda e: errors.append(str(e)[:200]))
                page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                page.goto(origin + "/index.html#recommended", wait_until="load")
                page.wait_for_timeout(1500)
                rooms = ("/js/record.js", "/js/detail.js", "/js/account.js", "/js/more.js")
                got["first"] = [r for r in rooms if r in asked]
                page.evaluate("switchView('record')")
                page.wait_for_timeout(1500)
                page.evaluate("switchView('recommended')")
                page.wait_for_timeout(300)
                page.evaluate("switchView('record')")
                page.wait_for_timeout(800)
                got["record"] = asked.count("/js/record.js")
                got["record_drawn"] = page.evaluate("typeof renderRecord === 'function' && !String(renderRecord).includes('roomCall(')")
                page.evaluate("switchView('account')")
                page.wait_for_timeout(1200)
                got["account"] = asked.count("/js/account.js")
                got["errors"] = list(errors)
                # A deploy arrived while this page was open: the next room reloads.
                page.evaluate("window.QB_STALE = true")
                with page.expect_navigation(timeout=10000):
                    page.evaluate("switchView('about')")
                page.wait_for_timeout(1500)
                got["after_reload"] = page.evaluate("""() => ({ stale: !!window.QB_STALE, hash: location.hash,
                    real: typeof renderAbout === 'function' && !String(renderAbout).includes('roomCall('),
                    view: (document.querySelector('.view.active') || {}).id || '' })""")
                ctx.close()
                # A room that cannot arrive says so; the next try loads it.
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
                page = ctx.new_page()
                page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                block = {"on": True}
                page.route("**/js/more.js*", lambda r: r.abort() if block["on"] else r.continue_())
                page.goto(origin + "/index.html#recommended", wait_until="load")
                page.wait_for_timeout(1000)
                page.evaluate("switchView('features')")
                page.wait_for_timeout(1200)
                got["failed_note"] = page.evaluate("!!document.querySelector('.view.active .room-failed')")
                block["on"] = False
                page.evaluate("switchView('recommended')")
                page.wait_for_timeout(300)
                page.evaluate("switchView('features')")
                page.wait_for_timeout(1500)
                got["retry"] = page.evaluate("typeof renderFeatures === 'function' && !String(renderFeatures).includes('roomCall(')")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert got["first"] == [], ("the first screen fetched a room", got["first"])
    assert got["record"] == 1 and got["record_drawn"], got
    assert got["account"] == 1, got
    assert not got["errors"], got["errors"]
    after = got["after_reload"]
    assert not after["stale"] and after["real"] and after["hash"] == "#about" and after["view"] == "view-about", after
    assert got["failed_note"] and got["retry"], got


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
