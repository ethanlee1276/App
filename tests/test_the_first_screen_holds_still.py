"""The first screen holds still and answers quickly on a mid-range phone.

Ethan, 2026-10-24: "We need to make sure it's going to be sharp and running
quickly ... I want this app just to run better." Measured that day the way
Lighthouse measures a phone (Chromium, the CPU slowed 4x, a slow mobile
network, a cold load of a board with picks on it):

                      before        after
    layout shift      0.78          0.016      (Google: good under 0.1)
    blocked time      765 ms        ~370 ms    (Lighthouse: good under 200)
    longest freeze    635 ms        ~280 ms

What moved the page: the markup's placeholder board (another league's
wording, no crests, the footer showing under it) replaced by the real one;
the launcher row landing on top of the page with the board; the freshness
chip appearing and sliding the logo; the generic `.loading` style (60px of
padding, meant for loading TEXT) also matching the logo while a board
loaded — on every refresh, not only the first; and the Live page's
scoreboard filling in above bets already drawn. What froze it: the
Toolbox's 2,000-run bankroll simulation, drawn in the background on every
load for a page that redraws it on each visit anyway.

The fixes, pinned here: boot.js marks the page `booting` and app.js lifts it
the frame after its first draw (styles.css shows the page after 4s whatever
happens); the launcher row is drawn at boot; the chip holds its width from
the first frame; `#brand-home.loading` undoes the text style; the Live
scoreboard holds its place; the Toolbox draws on its visit and runs its
simulation after the page has painted.

The browser half is opt-in like the others (QB_BROWSER_TESTS=1) and runs in
the nightly code-health pass. Its bars are looser than the measurement, so a
slower night is not a red one; a regression to the old numbers is.

Run directly: `QB_BROWSER_TESTS=1 python3 tests/test_the_first_screen_holds_still.py`
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

READ = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()  # noqa: E731
APP, CSS, BOOT, EXTRAS, HTML = (READ("web", "js", "app.js"), READ("web", "css", "styles.css"), READ("web", "js", "boot.js"),
                                READ("web", "js", "extras.js"), READ("web", "index.html"))
#: Bars for the browser half, at 4x CPU on a slow mobile network.
#: The shift bar came down from 0.1 on 2026-10-25, when the launch shimmer's
#: margin stopped holding the page 14px low (0.016 -> 0.000 on all four):
#: a shift does not wander the way time does, so the bar can sit close.
MAX_SHIFT = 0.02
MAX_FREEZE_MS = 500
MAX_BLOCKED_MS = 900
VIEWS = ("recommended", "likely", "live", "record")


def test_the_page_is_hidden_until_drawn_and_never_left_blank():
    assert 'document.documentElement.classList.add("booting");' in BOOT
    at = APP.index("\nrenderQuickTools();\nload();\n")
    tail = APP[at:at + 300]
    assert 'requestAnimationFrame(() => document.documentElement.classList.remove("booting"));' in tail
    block = CSS[CSS.index("html.booting main > *"):]
    assert "animation: boot-reveal 0s linear 4s forwards" in block[:200], "a script that never lands cannot leave it blank"
    assert "@keyframes boot-reveal { to { visibility: visible; } }" in CSS
    assert "@media (max-width: 760px) { main { min-height: calc(100svh" in CSS


def test_nothing_lands_on_top_of_the_page():
    assert "#brand-home.loading { padding: 0; grid-column: auto;" in CSS, "the logo must not swell while a board loads"
    assert '<span id="live-refresh" class="live-refresh" style="visibility:hidden"><span class="lr-full">' in HTML
    at = APP.index("function updateAgo() {")
    assert "|| !state.lastLoad ? \"hidden\" : \"\"" in APP[at:at + 900]
    at = APP.index("async function renderLiveBoard() {")
    body = APP[at:at + 700]
    assert body.index("lv-hold") < body.index("await fetchAllLive()"), "the scoreboard holds its place while the feeds answer"


def test_the_toolbox_never_freezes_a_page_it_is_not_on():
    assert '["tools-body", () => renderTools(), true],' in APP
    at = EXTRAS.index("  function tools(host) {")
    body = EXTRAS[at:EXTRAS.index("\n  }\n", at)]
    assert 'box.dataset.calc !== "roll"' in body and "setTimeout(() => calc(box)" in body


def _board():
    from test_every_page_opens_clean import _board as base
    b = base()
    today = time.strftime("%Y-%m-%d")
    b.update(generated_from="live", date=today)
    for g in b["games"]:
        g["date"] = today
    return b


OBS = r"""
try { localStorage.setItem('qb-seen-intro', '1'); } catch (e) {}
window.__m = {cls: 0, long: [], shifts: []};
new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) {
  __m.cls += e.value; __m.shifts.push([Math.round(e.startTime), +e.value.toFixed(3),
  (e.sources || []).map((s) => s.node ? (s.node.id || s.node.nodeName) : '?')]); } }).observe({type: 'layout-shift', buffered: true});
new PerformanceObserver((l) => { for (const e of l.getEntries()) __m.long.push(Math.round(e.duration)); }).observe({type: 'longtask', buffered: true});
"""


def test_in_a_browser_the_first_screen_holds_still_on_a_mid_phone():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    body = json.dumps(_board())
    stamp = {"Last-Modified": time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())}
    srv, port = rendercheck._serve()
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-component-update",
                           "--disable-background-networking"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for view in VIEWS:
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                              device_scale_factor=3, service_workers="block")
                    page = ctx.new_page()
                    page.add_init_script(OBS)
                    cdp = ctx.new_cdp_session(page)
                    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
                    cdp.send("Network.enable")
                    cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 150,
                                                                  "downloadThroughput": 2e6, "uploadThroughput": 1e5})
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/data/**", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                 body="{}", headers=stamp))
                    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                    for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json",
                                                            body=body, headers=stamp))
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#{view}", wait_until="load")
                    page.wait_for_timeout(5000)
                    m = page.evaluate("window.__m")
                    got[view] = {"cls": round(m["cls"], 3), "freeze": max(m["long"] or [0]),
                                 "blocked": sum(max(0, d - 50) for d in m["long"]), "shifts": m["shifts"][:4]}
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    for view, g in got.items():
        print(f"      {view:12s} shift {g['cls']:.3f}  longest {g['freeze']} ms  blocked {g['blocked']} ms")
        assert g["cls"] <= MAX_SHIFT, (view, g)
        assert g["freeze"] <= MAX_FREEZE_MS, (view, g)
        assert g["blocked"] <= MAX_BLOCKED_MS, (view, g)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
