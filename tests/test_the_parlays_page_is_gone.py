"""The Parlays page is gone from every league; the game report picks and parlays replace it.

Ethan, 2026-11-16, circling Parlays in the menu: "Also get rid of these
parlays and the parlay page for all sports since we have replaced it with the
game report picks and parlays".

What the page showed lives on, or goes, like this:

* each game's three-leg parlays and scorer pairs (engine/gameparlays) stay:
  on each game's report and on the Report Picks page, graded on the Record
  page under "The Game Report Picks and Parlays";
* the Edge and Most Likely two-leg tickets (engine/twoleg) are no longer
  built: no board carries `two_leg`, nothing new is journaled, and their
  record stays on the Record page, marked retired;
* an old #parlays link opens Report Picks, and Ask answers "parlays" from
  each game's report parlays.

Run directly: `python3 tests/test_the_parlays_page_is_gone.py`
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())


def _read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


HTML = _read("web", "index.html")
APP = _read("web", "js", "app.js")


def _block(start, end="];"):
    i = APP.index(start)
    return APP[i:APP.index(end, i)]


def test_no_menu_has_a_door_to_it():
    assert 'data-view="parlays"' not in HTML and 'id="parlays-tab"' not in HTML, "the sidebar button"
    assert 'id="view-parlays"' not in HTML and 'id="parlays-body"' not in HTML, "the page itself"
    assert '"view:parlays"' not in _block("const MORE_GROUPS = ["), "the phone's More sheet"
    more = _read("web", "js", "more.js")
    assert '"parlays"],' not in more, "the Features page's entry"


def test_every_list_of_pages_forgot_it():
    for start in ("const VIEW_ORDER = [", "const BOARD_VIEWS = [", "const SWIPE_VIEWS = [",
                  "const OFFSCREEN_PAGES = ["):
        assert "parlays" not in _block(start), start
    assert '"parlays"' not in _block("const EMPTY_DOOR_VIEWS = new Set([", "]);")
    assert '"parlays"' not in _block("const HIDDEN_VIEWS = {", "};")
    assert "parlays:" not in _block("const HIDDEN_WHY = {", "};")
    for gone in ("function renderParlayPage(", "function fillGameParlays(", "const TL_POOLS", "function tlTicketHTML(",
                 'if (name === "parlays")'):
        assert gone not in APP, gone
    report = _read("web", "js", "report.js")
    assert "function gameParlays(" not in report and "function gameParlaysRecord(" not in report
    # The report's own tickets and, since 20 November, the same tickets followed live (liveTickets, liveGame).
    assert ("window.QBReport = { html, block, toText, teaser, gameTickets, slipCombine, liveTickets, liveGame };"
            in report)
    assert ".tl-card" not in _read("web", "css", "styles.css")


def test_an_old_link_opens_report_picks():
    """A bookmark or a shared #parlays opens the page that carries each game's
    parlays, and the address says so, on a cold load and on a click alike."""
    assert 'const MOVED_VIEWS = { parlays: "reportpicks" };' in APP
    assert APP.count('const h = movedView((location.hash || "").replace("#", ""));') == 2, "both routers ask"
    fn = APP[APP.index("function movedView(h) {"):APP.index("function initialView() {")]
    assert 'history.replaceState(history.state, "", `#${to}`)' in fn


def test_no_board_builds_two_leg_tickets_but_each_game_keeps_its_parlays():
    from engine import parlays as P
    import inspect
    for sport in ("nfl", "cfb", "nba", "cbb", "mlb", "nhl", "wnba"):
        board = {"recommendations": [], "most_likely": [], "date": "2026-11-16"}
        P.attach(board, sport, state="normal")
        assert "two_leg" not in board, sport
    src = inspect.getsource(P.attach)
    assert "gameparlays.attach(slate, sport)" in src, "each game's parlays still hang on every board"


def test_the_journal_and_the_record_keep_what_they_made():
    """No board carries `two_leg`, so nothing new is journaled; the journal
    still reads one if an old board on disk carries it; the Record page let
    their history go on 2026-11-16."""
    from engine import parlayledger
    src = _read("engine", "parlayledger.py")
    assert 'tl = board.get("two_leg")' in src and "log_twoleg(conn, tl, sport" in src
    assert callable(parlayledger.log_twoleg)
    # The Record page's retired heading went too (2026-11-16; Ethan: "retire the 2 leg parlays record and
    # shit"): the journal keeps every ticket, the page draws each game report's parlays.
    rec = _read("web", "js", "record.js")
    assert "Two-leg parlays — retired" not in rec and "recTwoLegSection" not in rec


def test_ask_answers_parlays_from_each_games_report():
    from engine import askbot
    boards = {"nba": {"game_parlays": {"games": [{"game": "IND @ PHI", "home": "PHI", "away": "IND",
        "threes": [{"joint": 0.33, "legs": [{"player": "Tyrese Maxey", "side": "Over", "line": 24.5,
                                             "market": "points", "odds": -110}]}], "scorers": []}]},
                      "two_leg": {"edge": {"tickets": [{"joint": 0.9, "legs": [{"player": "Old Ticket"}]}]}}}}
    got = askbot.our_picks(boards, kind="parlays", sport="nba")
    assert got["count"] == 1 and got["rows"][0]["game"] == "IND @ PHI", got
    assert got["rows"][0]["legs"] == ["Tyrese Maxey Over 24.5 points (-110)"], got


def _browser(run):
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return None
    import rendercheck
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                return run(browser, port)
            finally:
                browser.close()
    finally:
        srv.shutdown()


def test_in_a_browser_the_menu_has_no_parlays_and_an_old_link_lands_on_report_picks():
    board = {"sport": "nfl", "date": "2026-11-16", "recommendations": [], "most_likely": [],
             "games": [{"home": "BUF", "away": "LAC", "date": "2026-11-16", "kickoff": "13:00"}],
             "game_parlays": {"games": [{"game": "LAC @ BUF", "home": "BUF", "away": "LAC", "threes": [
                 {"joint": 0.3, "independent": 0.25, "fair_words": "+233", "take_words": "+270", "legs": [
                     {"player": "Josh Allen", "team": "BUF", "market": "pass_yds", "side": "Over", "line": 249.5,
                      "odds": -115, "p": 0.6}]}], "scorers": []}]}}

    def run(browser, port):
        ctx = browser.new_context(viewport={"width": 412, "height": 823}, is_mobile=True, has_touch=True,
                                  device_scale_factor=1, service_workers="block")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        local = f"http://127.0.0.1:{port}/"
        page.route(lambda u: not u.startswith(local), lambda r: r.abort())
        for pat in ("**/api/recommendations*", "**/data/recommendations*"):
            page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(board)))
        page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}"
                             "catch(e){}")
        page.goto(f"{local}index.html?sport=nfl#parlays", wait_until="load")
        page.wait_for_function("() => typeof state !== 'undefined' && state.view === 'reportpicks'", timeout=30000)
        page.wait_for_selector("#view-reportpicks .rpk-game", timeout=30000)
        out = {"hash": page.evaluate("location.hash"),
               "menu": page.evaluate("[...document.querySelectorAll('.nav-btn')].map((b) => b.textContent.trim())"),
               "game": page.inner_text("#view-reportpicks .rpk-game summary")}
        # And a click on an old link inside the app, not only a cold load.
        page.evaluate("location.hash = '#recommended'")
        page.wait_for_function("() => state.view === 'recommended'", timeout=10000)
        page.evaluate("location.hash = '#parlays'")
        page.wait_for_function("() => state.view === 'reportpicks'", timeout=10000)
        out["hash2"] = page.evaluate("location.hash")
        out["errors"] = errors
        ctx.close()
        return out
    got = _browser(run)
    if got is None:
        return
    assert got["hash"] == "#reportpicks" and got["hash2"] == "#reportpicks", got
    assert "Parlays" not in got["menu"] and "Report Picks" in got["menu"], got["menu"]
    assert "BUF" in got["game"] or "Bills" in got["game"], got["game"]
    assert not got["errors"], got["errors"]


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except Exception as exc:                                  # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    if fails:
        print(f"\n{fails} failed")
        sys.exit(1)
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
