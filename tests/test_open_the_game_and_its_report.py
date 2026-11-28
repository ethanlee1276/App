"""The button that says it opens the game and its report opens them (25 November 2026).

Ethan, circling Best Parlays' "Open the game and its report": "Also this button isn't working". It never had: the
page drew it (js/bestparlays.js, step AAL, 21 November) with no listener, and Report Picks' "Open the report"
(js/reportpicks.js) the same. The one test of it read its markup and never pressed it. Now:

  * app.js `openGameReport` opens the game's page (`openGame`) and brings the report to the top once the page has
    drawn it; a page with no report to show stays at its top, opened;
  * one listener on the document answers both buttons, wherever and whenever their cards are drawn;
  * in a browser, a press on either button lands on the game's page with its report in view.

The browser half runs with QB_BROWSER_TESTS=1 and /usr/bin/python3.
"""
import copy
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
BP = (ROOT / "web" / "js" / "bestparlays.js").read_text(encoding="utf-8")
RP = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def test_the_buttons_are_answered_and_open_the_report():
    fn = _fn(APP, "openGameReport")
    assert fn.startswith("function openGameReport(gid) {\n  openGame(gid);")
    assert 'document.getElementById("gp-sec-report")' in fn and "scrollIntoView" in fn
    assert 'if (state.view !== "game") return;' in fn, "a reader who has moved on is not pulled back"
    assert ('const b = e.target.closest && e.target.closest(".bp-open[data-gid], .rpk-open[data-gid]");\n'
            "  if (b) openGameReport(b.dataset.gid);") in APP
    assert 'class="btn ghost bp-open" data-gid="${escapeAttr(gameId(g))}">Open the game and its report</button>' in BP
    assert 'class="btn ghost rpk-open" data-gid="${escapeAttr(gameId(g))}">Open the report</button>' in RP


def _board():
    from engine import gameparlays as GP
    EG = __import__("test_each_game_gets_its_parlays")
    board = EG.board()
    board["game_parlays"] = GP.build(board, "nfl")
    base = board["game_parlays"]["games"][0]
    x = copy.deepcopy(base)
    x["away"], x["home"] = "DAL", "PHI"
    board["game_parlays"]["games"].append(x)
    g = copy.deepcopy(board["games"][0])
    g["away"], g["home"] = "DAL", "PHI"
    board["games"].append(g)
    GP.attach_ranked(board, "nfl")
    board.pop("locked", None)
    board["game_reports"] = [{"away": gm["away"], "home": gm["home"], "sections": [
        {"key": "verdict", "title": "Who we think wins", "blocks": [{"type": "text", "text": "The report's first line."}]}]}
        for gm in board["games"]]
    return board


def test_in_a_browser_a_press_lands_on_the_game_with_its_report_in_view():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    board = _board()
    body = json.dumps(board)
    srv, port = rendercheck._serve()
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for view, button in (("bestparlays", ".bp-open"), ("reportpicks", ".rpk-open")):
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                              service_workers="block")
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)[:300]))
                    page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1');"
                                         " localStorage.setItem('qb_intro_v1', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                    for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#{view}", wait_until="load")
                    if view == "reportpicks":
                        # A game's fold holds its button: open the first.
                        page.wait_for_selector("#reportpicks-body details", timeout=20000)
                        page.evaluate("document.querySelector('#reportpicks-body details').open = true")
                    page.wait_for_selector(f"{button}[data-gid]", state="attached", timeout=20000)
                    gid = page.evaluate(f"document.querySelector('{button}[data-gid]').dataset.gid")
                    page.evaluate(f"document.querySelector('{button}[data-gid]').scrollIntoView({{block: 'center'}})")
                    page.locator(f"{button}[data-gid]").first.click()
                    page.wait_for_function("() => state.view === 'game' && document.getElementById('gp-sec-report')",
                                           timeout=20000)
                    page.wait_for_timeout(1200)
                    got[view] = page.evaluate("""(gid) => { const r = document.getElementById('gp-sec-report');
                        return { view: state.view, active: (document.querySelector('.view.active') || {}).id,
                          same: findGame(gid) === findGame(state.gameId), top: Math.round(r.getBoundingClientRect().top),
                          errors: [] }; }""", gid)
                    got[view]["errors"] = list(errors)
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    for view in ("bestparlays", "reportpicks"):
        g = got[view]
        assert g["view"] == "game" and g["active"] == "view-game" and g["same"], (view, g)
        assert 0 <= g["top"] < 300, ("the report at the top of the screen", view, g)
        assert not g["errors"], (view, g["errors"])


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
