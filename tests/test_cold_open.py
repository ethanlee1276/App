"""Every view, tapped before the board has answered.

THE CASE THIS IS ABOUT is the one a phone actually does: the app opens,
the board fetch is in flight, and somebody taps a tab. `renderAll()`
guards that — `if (!state.data) return` — but the tab bar does not go
through renderAll. `switchView` calls a view's own render directly, so
every one of those renders has to survive being asked to draw with
nothing.

TWO DID NOT, both found here, both silent:

  * `renderTonight` reaches `noMarketHeading()` on its empty branch, and
    both that and `noMarketExplainer()` read `state.data.generated_from`.
    Tonight is the SECOND BUTTON on the mobile tab bar. Measured with the
    board unloaded: "Cannot read properties of null", tonight-body 0
    characters.
  * `renderPropPage` read `state.data.game_bets` on its first line, which
    is how a shared game-bet link opened cold rendered a blank page (see
    tests/test_prop_page.py).

WHY NEITHER SHOWED UP AS AN ERROR, and why this file drives a browser
rather than reading source: a view render runs inside
`document.startViewTransition`, where a throw becomes a rejected promise
the browser swallows. No page error, no console line, a blank screen. The
first version of the probe below reported every view "ok" for exactly
that reason — the throw never reached its try/catch — and it only became
a real check once it turned transitions off (`state.quiet`) AND measured
whether anything was actually drawn.

Opt in with QB_BROWSER_TESTS=1; the source checks always run.

Run directly: `python3 tests/test_cold_open.py`
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()

VIEWS = ["recommended", "scanner", "longshots", "futures", "edge", "injuries",
         "weather", "players", "live", "trending", "rosters", "standings",
         "bankroll", "alerts", "tonight", "record", "intel", "fantasy",
         "memes", "mybets", "lab", "about", "why", "account", "paywall",
         "game", "prop", "checkout"]


# --- the source, always ------------------------------------------------------
def test_the_two_that_were_caught_stay_guarded():
    # `renderPropPage`'s game-bet lookup moved into `findGameRow` on
    # 2026-09-02 — the likelihood board's own game rows had to be
    # searched too, and a second copy of a lookup is how two callers
    # drift apart. The guard travelled with it and is asserted where it
    # now lives; the caller is checked below.
    for name, needle in (
            ("noMarketHeading", "(state.data || {}).generated_from"),
            ("noMarketExplainer", "const d = state.data || {};"),
            ("findGameRow", "const d = state.data || {};"),
            ("renderScanner", "(state.data || {}).market_scan")):
        i = APP.index(f"function {name}(")
        body = APP[i:APP.index("\n}", i)]
        assert needle in body, (
            f"{name} dereferences state.data unguarded again — it is "
            "reachable before the board answers")


def test_the_prop_page_reaches_a_game_row_only_through_the_guarded_lookup():
    """The guard is only worth anything if the cold path actually uses
    it. renderPropPage must not grow its own `state.data.game_bets`
    back."""
    import re
    i = APP.index("function renderPropPage(")
    body = APP[i:APP.index("\n}", i)]
    assert "findGameRow(state.propId)" in body
    # CODE ONLY. The function's own comment tells the story of the 2026-08
    # blank-page bug and quotes the unguarded expression that caused it;
    # a check that reads comments would forbid the codebase from
    # remembering its own defects.
    code = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
    for bad in ("state.data.game_bets", "state.data.most_likely"):
        assert bad not in code, bad


def test_render_all_still_carries_the_guard_the_tab_bar_lacks():
    """The reason the tab bar is the dangerous path: renderAll checks and
    switchView does not. If renderAll ever stopped checking, every render
    in its cascade would join the reachable set."""
    i = APP.index("function renderAll(")
    body = APP[i:i + 300]
    assert "const d = state.data;" in body and "if (!d) return;" in body


# --- the browser, opt-in -----------------------------------------------------
def test_no_view_throws_or_draws_nothing_when_tapped_before_the_board():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck

    chromium = os.environ.get(
        "CHROMIUM_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    srv, port = rendercheck._serve()
    res, errs = {}, []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage",
                           "--disable-gpu"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            ctx = browser.new_context(viewport={"width": 390, "height": 844},
                                      is_mobile=True, has_touch=True,
                                      service_workers="block")
            page = ctx.new_page()
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load")
            page.wait_for_timeout(2500)
            # `state.quiet` turns OFF the view transition. Without it a
            # throw inside a render is swallowed and every view reports
            # clean — which is what the first version of this did.
            for v in VIEWS:
                # NULLED AND SWITCHED IN ONE CALL. Doing it in two let the
                # board fetch resolve in the gap and refill state.data, so
                # a view was sometimes rendered WITH data and reported
                # clean — which is how the first version of this passed
                # against code that throws on `tonight`.
                #
                # `state.quiet` turns off the view transition; without it
                # a throw inside a render becomes a rejected promise the
                # browser swallows and never reaches this try/catch.
                thrown = page.evaluate(
                    """(v) => { state.quiet = true; state.data = null;
                                try { switchView(v, false); return null; }
                                catch (e) { return String((e && e.message) || e); } }""", v)
                page.wait_for_timeout(1300)
                # An async render may have refilled it; keep it empty.
                page.evaluate("() => { state.data = null; }")
                info = page.evaluate("""() => {
                  const a = document.querySelector('.view.active');
                  const t = a ? a.innerText.trim() : '';
                  return { len: t.length,
                           head: t.replace(/\\s+/g, ' ').slice(0, 60) }; }""")
                res[v] = {"threw": thrown, **info}
            browser.close()
    finally:
        srv.shutdown()

    threw = {k: v["threw"] for k, v in res.items() if v["threw"]}
    assert not threw, f"renders that throw on a cold open: {threw}"
    # `game` legitimately says "Loading the slate…" here and nothing else,
    # because this probe holds state.data at null forever so its wait can
    # never end. That is an honest loading state, not a blank screen.
    blank = {k: v for k, v in res.items()
             if v["len"] < 20 and not v["head"].startswith("Loading")}
    assert not blank, f"views that draw nothing on a cold open: {blank}"
    assert not errs, f"page errors on a cold open: {errs[:3]}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
