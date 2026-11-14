"""The installed app opens from its own copy; prices never come from one.

Ethan, 2026-10-24: "build everything" — docs/IDEAS.md's first item. The
service worker had been network-first for everything, so an installed app on
a weak signal waited for the network before it could show itself. Now:

  - a page running as the installed app (a Home Screen app, the Play build,
    the iOS shell) tells the worker so (register-sw.js "app-mode"), and the
    worker keeps every file of the app — shell and pages — under this
    version's name and opens from it, even with no signal at all;
  - a browser tab never asks, so a one-time visitor downloads only what they
    open (the pages' files are not fetched for them);
  - a version is cached whole and replaced whole: the pages' files are in the
    version's hash (server.py), so a change to any one renames the version;
  - /data/ and /api/ are still never served from the app's copy — the one
    exception is the record, the free history, kept for reading offline and
    marked with the moment it was kept, which the Record page says.

Run directly: `python3 tests/test_the_app_opens_offline.py` (the browser
half with QB_BROWSER_TESTS=1 and Playwright)
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
READ = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()  # noqa: E731
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)
SW, REG, APP = READ("web", "sw.js"), READ("web", "js", "register-sw.js"), app_js()


def _list(name):
    return re.findall(r'"(/[^"]*)"', re.search(rf"const {name} = \[(.*?)\];", SW, re.S).group(1))


def test_every_file_the_app_loads_is_in_the_version():
    lazy = set(_list("LAZY")) | set(_list("SHELL"))
    for src in (APP, READ("web", "js", "visuals.js"), READ("web", "js", "extras.js"), READ("web", "js", "gamecast.js")):
        for f in re.findall(r'(?:s|el)\.src = "(js/[a-z0-9_-]+\.js)"', src) + re.findall(r'css\.href = "(css/[a-z0-9_-]+\.css)"', src):
            assert "/" + f in lazy, f"{f} loads on first use but is not in the version"
    # The rooms (app.js loadRoom): each stub names its script and its styles.
    rooms = re.findall(r'roomCall\((\w+), "(\w+)", "(js/[a-z0-9_-]+\.js)", (?:"(css/[a-z0-9_-]+\.css)"|null), a\)', APP)
    assert len(rooms) >= 24, len(rooms)
    for stub, name, js, css in rooms:
        assert stub == name, (stub, name)
        assert "/" + js in lazy, f"{js} loads on first use but is not in the version"
        assert not css or "/" + css in lazy, f"{css} loads on first use but is not in the version"
        assert f"function {name}(" in READ("web", *js.split("/")), f"{js} does not replace the stub {name}"
    for f in re.findall(r"js/chart-\$\{f\}\.js", READ("web", "js", "carrychart.js")):
        pass
    charts = {f"/js/{n}" for n in os.listdir(os.path.join(ROOT, "web", "js")) if n.startswith("chart-")}
    assert charts <= lazy, charts - lazy
    for u in lazy:
        assert os.path.exists(os.path.join(ROOT, "web", "index.html" if u == "/" else u.lstrip("/"))), u


def test_the_version_name_covers_the_pages_too():
    import server
    from pathlib import Path
    files = {p.name for p in server._sw_shell(SW, Path(ROOT) / "web")}
    assert {"memes.js", "gamecast.js", "chart-mlb.js", "app.js", "boot.js"} <= files, files


def test_only_the_installed_app_asks_and_the_worker_keeps_the_mark():
    at = REG.index("THE INSTALLED APP KEEPS ITS OWN COPY")
    block = REG[at:at + 900]
    assert "QB_STORE_APP" in block and "navigator.standalone === true" in block and "display-mode: standalone" in block
    assert 'postMessage({ type: "app-mode" })' in block
    assert 'e.data.type !== "app-mode"' in SW and '.put("/app", new Response("1"))' in SW
    at = SW.index('self.addEventListener("install"')
    assert "(await appMode()) ? [...SHELL, ...LAZY] : SHELL" in SW[at:SW.index("\n});", at)]
    assert 'new Request(u, { cache: "reload" })' in SW, "a new version is fetched past the browser's cache"


def test_the_record_is_the_one_data_file_kept_and_it_says_from_when():
    at = SW.index("const OFFLINE_COPIES")
    assert 'new Set(["/data/record.json", "/data/record_head.json"])' in SW[at:at + 120]
    assert "res.status >= 500 ? kept()" in SW, "the box down reads like no signal"
    assert '"X-QB-Offline-Copy": new Date().toISOString()' in SW
    at = APP.index("async function renderRecord() {")
    body = APP[at:at + 9000]
    assert 'res.headers.get("X-QB-Offline-Copy")' in body and "rec-offline" in body


def test_in_a_browser_the_app_opens_with_no_signal_and_a_tab_downloads_only_what_it_opens():
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
    down = [False]
    origin = f"http://127.0.0.1:{port}"
    got = {}
    keys_js = """async () => { const out = {}; for (const k of await caches.keys()) {
        out[k] = (await (await caches.open(k)).keys()).map((r) => new URL(r.url).pathname); } return out; }"""
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                # A browser tab: the shell only.
                ctx = browser.new_context()
                page = ctx.new_page()
                page.goto(origin + "/index.html", wait_until="load")
                page.evaluate("navigator.serviceWorker.ready.then(() => true)")
                page.wait_for_timeout(1500)
                got["tab"] = page.evaluate(keys_js)
                ctx.close()
                # The Play app: everything, then no signal.
                ctx = browser.new_context()
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)[:160]))
                page.goto(origin + "/index.html?app=play", wait_until="load")
                page.evaluate("navigator.serviceWorker.ready.then(() => true)")
                page.wait_for_timeout(2500)
                got["app"] = page.evaluate(keys_js)
                # The record's kept copy answers when the network cannot.
                page.evaluate("""async () => { const c = await caches.open("qb-offline");
                    await c.put("/data/record.json", new Response('{"overall": {"settled": 3}}',
                      { headers: { "Content-Type": "application/json", "X-QB-Offline-Copy": "2026-10-24T12:00:00Z" } })); }""")
                ctx.set_offline(True)
                page.reload(wait_until="load")
                page.wait_for_timeout(1500)
                got["offline"] = page.evaluate("""async () => {
                    const m = await fetch("/js/memes.js");
                    return { title: document.title, view: !!document.getElementById("view-recommended"),
                             app: typeof renderAll === "function", memes: m.ok,
                             board: await fetch("/data/recommendations.json").then((x) => x.ok, () => false) }; }""")
                # Chromium's offline switch covers the page, not the worker's
                # own requests; the server stopping is what no signal is to it.
                srv.shutdown()
                srv.server_close()        # refused, not queued: a stopped loop still listens
                down[0] = True
                got["offline"]["record"] = page.evaluate("""async () => { const r = await Promise.race([fetch("/data/record.json"),
                    new Promise((_, no) => setTimeout(() => no(new Error("hung")), 8000))]);
                    return r.ok && r.headers.get("X-QB-Offline-Copy"); }""")
                got["errors"] = errors
                ctx.close()
            finally:
                browser.close()
    finally:
        if not down[0]:
            srv.shutdown()
    # The version's box is named by server.py's hash, "qb-<12 hex>".
    version = lambda keys: next((v for k, v in keys.items() if re.fullmatch(r"qb-[0-9a-f]{12}", k)), [])  # noqa: E731
    tab, app = version(got["tab"]), version(got["app"])
    assert "/js/app.js" in tab and "/js/memes.js" not in tab, ("a tab keeps the shell, not every page", tab)
    assert {"/js/app.js", "/js/memes.js", "/js/gamecast.js", "/css/social.css"} <= set(app), app
    assert "/app" in got["app"].get("qb-mode", []), got["app"]
    assert not any(p.startswith(("/data/", "/api/")) for p in app), "a board or a session in the app's copy"
    off = got["offline"]
    assert off["view"] and off["app"] and off["memes"], off
    assert off["record"] == "2026-10-24T12:00:00Z", off
    assert off["board"] is False, "a board is never served from a copy"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
