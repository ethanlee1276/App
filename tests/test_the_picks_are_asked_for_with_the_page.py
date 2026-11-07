"""The picks are asked for with the page, and a page's own code is never a
blank wait.

2026-10-25, Lighthouse on its phone setting (Ethan: "continue on making the
app better"):

  - THE PICKS WAITED FOR THE APP. The board's light copy (engine/lightboard,
    the picks without the heavy half) was asked for only once app.js (284 KB
    compressed) had arrived and run, so on a slow network the picks landed a
    whole download after the page. boot.js, in the page's head, now asks for
    the light copy of the league this visit opens, by app.js startSport's own
    rules (?sport=, the kept league, the season), and app.js's paidFetch takes
    that answer instead of asking again. Only at the site's root: a clean
    path names its own league and page.
  - A PAGE'S OWN CODE ON ITS WAY. The first time the Record, a game, the
    account or a More page opens in a browser tab, its file is fetched; on a
    slow network that was a blank page. A shimmer holds the place once the
    wait is long enough to see (150 ms), and goes the moment the page draws
    or says it could not load.

What these hold: boot.js's league map and rules are app.js's (run side by
side in node across the cases); the early answer is taken once and only for
its own file; in Chromium the light copy leaves before app.js has finished
arriving and is fetched once, and a slow page file shows the shimmer while a
quick one never does.

Run directly: `python3 tests/test_the_picks_are_asked_for_with_the_page.py`
(the browser half with QB_BROWSER_TESTS=1 and Playwright)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
BOOT = open(os.path.join(ROOT, "web", "js", "boot.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _early():
    i = BOOT.index("var QB_EARLY_BOARD = null;")
    return BOOT[i:]


def test_boots_league_files_are_the_boards_light_copies():
    light = dict(re.findall(r'(\w+): "([a-z_]+\.json)"', _early().split("var sport")[0]))
    meta = dict(re.findall(r'\n  (\w+): \{ logo:.*?fallback: "data/([a-z_]+)\.json" \}', APP, re.S))
    assert set(light) == set(meta) == {"nfl", "mlb", "nba", "wnba", "cfb", "nhl"}, (light, meta)
    for sport, stem in meta.items():
        assert light[sport] == f"{stem}_picks.json", (sport, light[sport])
    assert 'return f.replace(/^data\\//, "").replace(/\\.json$/, "_picks.json");' in _fn("lightNameFor")


def test_boot_picks_the_league_app_js_opens():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    start = _fn("startSport")
    early = _early()
    prog = f"""
      const out = [];
      for (const [search, kept, iso] of {json.dumps([
          ["", None, "2026-10-25"], ["?sport=mlb", None, "2026-10-25"], ["?sport=nhl&x=1", "cfb", "2026-10-25"],
          ["", "cfb", "2026-10-25"], ["", "wnba", "2026-06-01"], ["", "nope", "2026-03-01"], ["", None, "2026-02-14"],
          ["", None, "2026-02-15"], ["", None, "2026-03-25"], ["", None, "2026-03-26"], ["", None, "2026-08-31"],
          ["", None, "2026-09-01"], ["?sport=ufc", None, "2026-07-04"]])}) {{
        const RealDate = Date;
        global.Date = class extends RealDate {{ constructor(...a) {{ super(...(a.length ? a : [iso + "T12:00:00"])); }} }};
        global.location = {{ search, pathname: "/" }};
        global.localStorage = {{ getItem: (k) => (k === "qb.sport" ? kept : null) }};
        global.URLSearchParams = URLSearchParams;
        const asked = [];
        global.window = {{ fetch: true }};
        global.fetch = (u) => {{ asked.push(u); const p = Promise.resolve({{}}); return p; }};
        {start}
        var QB_EARLY_BOARD;
        {early}
        out.push([startSport(), QB_EARLY_BOARD && QB_EARLY_BOARD.name, asked]);
        global.Date = RealDate;
      }}
      // A clean path or ?static asks for nothing.
      for (const [search, pathname] of [["", "/player/juan-soto"], ["?static=1", "/"], ["", "/mlb"]]) {{
        global.location = {{ search, pathname }};
        const asked = [];
        global.fetch = (u) => {{ asked.push(u); return Promise.resolve({{}}); }};
        var QB_EARLY_BOARD = null;
        {early}
        out.push(["skip", QB_EARLY_BOARD, asked]);
      }}
      console.log(JSON.stringify(out));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    files = {"nfl": "recommendations_picks.json", "mlb": "mlb_recommendations_picks.json", "nba": "nba_picks.json",
             "wnba": "wnba_picks.json", "cfb": "cfb_picks.json", "nhl": "nhl_picks.json"}
    for sport, name, asked in got[:-3]:
        assert name == files[sport] and asked == ["/api/board/" + name], (sport, name, asked)
    assert [g[0] for g in got[:-3]] == ["nfl", "mlb", "nhl", "cfb", "wnba", "nba", "nfl", "nba", "nba", "mlb", "mlb",
                                        "nfl", "mlb"], got
    for skip in got[-3:]:
        assert skip[1] is None and skip[2] == [], skip


def test_paid_fetch_takes_the_early_answer_once_and_only_for_its_file():
    body = _fn("paidFetch")
    assert "QB_EARLY_BOARD.name === name" in body and "if (early) QB_EARLY_BOARD = null;" in body
    assert 'await (early || boardFetch("/api/board/" + name))' in body
    assert body.index("if (early) QB_EARLY_BOARD = null;") < body.index("ask = (async () => {"), "taken before the ask"
    # The denied and fallback paths are unchanged: a 401/402 still falls to the static copy.
    assert "_paidDenied = boardMemWho();" in body and 'return boardFetch(`data/${name}`, { cache: "no-cache" });' in body


def test_a_cold_page_shows_a_shimmer_after_a_moment_and_loses_it_when_drawn():
    call = _fn("roomCall")
    assert "const ROOM_WAIT_MS = 150;" in APP
    assert "const cold = !(window._qbRooms && window._qbRooms.has(js));" in call
    assert "setTimeout(() => { wait = roomWait(); }, ROOM_WAIT_MS)" in call
    assert call.index("clearTimeout(timer);") < call.index("return window[name](...args);"), "gone before the page draws"
    assert call.index("if (wait) wait.remove();") < call.index("roomFailed();"), "gone before the failure note"
    wait = _fn("roomWait")
    assert 'document.querySelector(".view.active")' in wait and 'role="status"' in wait
    assert ".room-wait { height: min(60vh, 520px);" in CSS
    assert "@media (prefers-reduced-motion: reduce) { .room-wait { animation: none; } }" in CSS


def test_in_a_browser_the_picks_leave_with_the_page_and_a_slow_page_shimmers():
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
    from test_the_first_screen_holds_still import _board
    board = json.dumps(_board())
    srv, port = rendercheck._serve()
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                # 1. The light copy leaves before app.js has finished arriving, once.
                #    app.js is held 0.6 s (a slow network); only it and the boards are
                #    intercepted, so nothing else waits on the hold, and the page's own
                #    resource timings say when each request left and landed.
                import time
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                          service_workers="block")
                page = ctx.new_page()
                page.add_init_script("""try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); localStorage.setItem('qb.sport', 'nfl'); } catch (e) {}
                  window.__asks = []; const real = window.fetch;
                  window.fetch = function (u) { __asks.push([String(u).split('?')[0], performance.now()]); return real.apply(this, arguments); };""")
                page.route("https://**", lambda r: r.abort())
                for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=board))

                def slow_app(route):
                    time.sleep(0.6)
                    route.continue_()
                page.route("**/js/app.js*", slow_app)
                page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load")
                page.wait_for_timeout(1500)
                got["timing"] = page.evaluate("""() => {
                  const light = __asks.filter(([u]) => u === '/api/board/recommendations_picks.json');
                  const app = performance.getEntriesByType('resource').find((e) => /\\/js\\/app\\.js/.test(e.name));
                  return { asks: light.length, left: light.length ? light[0][1] : null, appLanded: app ? app.responseEnd : null };
                }""")
                ctx.close()
                # 2. A slow page file shimmers; a quick one never does. The file is
                #    held inside the page (its <script> joins the head 1.2 s late), and
                #    the page itself notes what it saw every 25 ms.
                watch = """(hold) => {
                  if (hold) {
                    const add = Node.prototype.appendChild;
                    Node.prototype.appendChild = function (n) {
                      if (n && n.tagName === 'SCRIPT' && /more\\.js/.test(n.src)) { setTimeout(() => add.call(this, n), hold); return n; }
                      return add.call(this, n);
                    };
                  }
                  window.__seen = { wait: [], drawn: null };
                  const t0 = performance.now();
                  const iv = setInterval(() => {
                    const t = Math.round(performance.now() - t0);
                    if (document.querySelector('.room-wait')) __seen.wait.push(t);
                    if (__seen.drawn === null && typeof window.FEATURES_DRAWN === 'undefined'
                        && document.getElementById('view-features').innerText.length > 2000) __seen.drawn = t;
                    if (t > 2600) clearInterval(iv);
                  }, 25);
                  switchView('features');
                }"""
                for name, hold in (("slow", 1200), ("quick", 0)):
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                              service_workers="block")
                    page = ctx.new_page()
                    page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=board))
                    page.goto(f"http://127.0.0.1:{port}/index.html#recommended", wait_until="load")
                    page.wait_for_timeout(1000)
                    page.evaluate(watch, hold)
                    page.wait_for_timeout(2900)
                    got[name] = dict(page.evaluate("window.__seen"),
                                     after=page.evaluate("() => !!document.querySelector('.room-wait')"))
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    timing = got["timing"]
    assert timing["asks"] == 1, ("the light copy is asked for once", timing)
    assert timing["left"] < timing["appLanded"], ("it leaves before app.js has landed", timing)
    slow, quick = got["slow"], got["quick"]
    assert slow["drawn"] and slow["wait"] and not slow["after"], slow
    assert min(slow["wait"]) >= 125 and 400 in range(min(slow["wait"]), max(slow["wait"]) + 1), ("shown from 150 ms", slow)
    assert max(slow["wait"]) <= slow["drawn"], ("gone once the page draws", slow)
    assert quick["drawn"] and not quick["after"], quick
    if quick["drawn"] < 120:                       # a quick load never flashes one
        assert not quick["wait"], quick


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
