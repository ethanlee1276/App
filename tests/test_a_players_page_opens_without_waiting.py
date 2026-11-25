"""A player's page opens without waiting on what it does not show (step AFK, 25 November 2026).

Ethan, with Amon-Ra St. Brown's page open on a phone: "Also data on the player page takes a long time to load".
Timed on the live site at a phone's speed (Chromium's processor slowed four times), the season's numbers drew 2.3 s
after the address opened when the server had the page kept, and 8.3 s when it built it, 4.4 s of that the server's.
The page also waited on things it does not show:

  * the players view waited for the injury file before asking anything. A player's own page hides its cards' name
    rows, where the tag sits, and fills in the header's tag when the file lands (js/playerpage.js plrFill);
  * the league search waited out the typing pause (280 ms) for an address, where nobody is typing;
  * the page's own answer was asked only after the player's market logs answered, and js/playerpage.js was fetched
    only when the page was drawn. The page is asked beside the logs now, and the script as the address opens;
  * Home kept drawing its queued blocks, the idle pages and the other leagues' copies meanwhile. They wait for the
    page now, never past nine seconds in (app.js boardHeld);
  * three Home blocks asking for the record at once downloaded it twice. It is asked once (loadRecordOnce).

Two draws asked before js/playerpage.js lands both run when it does, and the second found the first's page in the
host and threw; the page is never its own new content now. And the server's answer says where its time went
(a Server-Timing header: each part's milliseconds, or "kept"), so the next slow one can be read off the site.

The browser half runs with QB_BROWSER_TESTS=1 and /usr/bin/python3.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import db  # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
PAGE = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")
SRV = (ROOT / "server.py").read_text(encoding="utf-8")


def _fn(src, head):
    i = src.index(head)
    return src[i:src.index("\n}\n", i) + 2]


def test_the_server_says_where_a_pages_time_went():
    from engine import playerpage as PP
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    rows = [{"sport": "nfl", "season": 2026, "period": f"{w:03d}", "game_id": f"DET-{w:03d}", "player": "Sam Hands",
             "team": "DET", "opponent": "GB", "position": "WR", "home": w % 2, "market": m, "value": v}
            for w in range(1, 6) for m, v in (("receptions", 5.0 + w), ("rec_yds", 60.0 + w))]
    conn = db.connect(path)
    db.upsert_player_logs(conn, rows)
    conn.commit()
    conn.close()
    took = []
    got = PP.page("nfl", "Sam Hands", db_path=path, data_dir=tempfile.mkdtemp(), took=took)
    assert [p for p, _ in took] == ["open", "name", "rows", "merge", "roster", "notes", "results", "games", "ranks",
                                    "splits", "career"], took
    assert all(isinstance(ms, float) and ms >= 0 for _, ms in took)
    assert got == PP.page("nfl", "Sam Hands", db_path=path, data_dir=tempfile.mkdtemp()), "timed or not, one page"
    body = SRV[SRV.index("def _players_page(self, q):"):]
    body = body[:body.index("\n    def ", 10)]
    assert 'return self._send(200, hit[1], ".json", headers=[("Server-Timing", "kept;dur=0")])' in body
    assert "took=took)" in body and 'took.append(("build", (time.perf_counter() - t0) * 1000.0))' in body
    assert 'timing = ", ".join(f"{part};dur={ms:.0f}" for part, ms in took)' in body, "names and numbers only"


def test_home_waits_while_a_cold_player_page_draws():
    assert ('const boardHeld = () => state.view === "players" && !!state.playerSlug && !window._plrDrawn '
            "&& performance.now() < 9e3;") in APP
    nxt = _fn(APP, "function boardNext() {")
    assert "if (boardHeld()) return boardNext();" in nxt and "}, boardHeld() ? 300 : 0);" in nxt
    assert "if (boardHeld()) return setTimeout(idleStale, 300);" in _fn(APP, "function idleStale() {")
    assert "while (boardHeld()) await new Promise((r) => setTimeout(r, 300));" in _fn(APP, "function prefetchLeaguesSoon() {")
    assert "const fill = (d) => { window._plrDrawn = true; if (page.isConnected) plrFill(page, d); };" in PAGE


def test_the_page_does_not_wait_on_what_it_does_not_show():
    players = APP[APP.index("async function renderPlayers() {"):]
    players = players[:players.index("\n}\n")]
    assert "const inj = loadInjuryBoard();\n  await (routed ? 0 : inj);" in players
    assert ('loadRoom("js/playerpage.js", "css/playerpage.css").then((ok) => ok && plrFetch(m.sport, m.player, '
            'm.team || ""));') in players
    assert players.index("plrFetch(m.sport, m.player") < players.index("const st = await leagueLogs(m.player, m.sport);")
    assert "if (!state.playerSlug) await new Promise((r) => setTimeout(r, LEAGUE_PAUSE_MS));" in APP
    route = APP[APP.index("function openPlayerRoute(slug, shown, pick) {"):]
    route = route[:route.index("\n}\n")]
    assert route.index('loadRoom("js/playerpage.js", "css/playerpage.css");') < route.index('switchView("players");')
    mount = _fn(PAGE, "function renderPlayerPage(host, player, sport) {")
    assert "for (const c of [...host.childNodes]) if (c !== same) kept.appendChild(c);" in mount
    assert "if (kept.childNodes.length) plrMarkets(same, kept);" in mount


def test_the_record_is_asked_once():
    if not shutil.which("node"):
        print("      (skipped: no node)")
        return
    decl = "let _recordCache = null, _recordAsk = null;\n"
    assert decl in APP
    prog = ("let calls = 0;\n"
            "const boardFetch = (u) => { calls++; return new Promise((r) => setTimeout(() => r({ ok: true, "
            "json: async () => ({ n: 1 }) }), 20)); };\n"
            "const adoptPooledRecord = (d) => d;\n" + decl + _fn(APP, "async function loadRecordOnce() {")
            + "\n(async () => { const got = await Promise.all([loadRecordOnce(), loadRecordOnce(), loadRecordOnce()]);"
              " const again = await loadRecordOnce();"
              " console.log(JSON.stringify({ calls, same: got.every((g) => g === got[0]) && again === got[0],"
              " n: got[0].n })); })();\n")
    path = os.path.join(tempfile.mkdtemp(), "t.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    assert json.loads(out.stdout) == {"calls": 1, "same": True, "n": 1}, out.stdout


HIT = {"player": "Amon-Ra St. Brown", "team": "DET", "position": "WR", "sport": "nfl", "rank": 0}
ANSWER = {"sport": "nfl", "player": "Amon-Ra St. Brown", "team": "DET", "position": "WR", "bio": {},
          "notes": {"injury": None, "moves": []}, "seasons": [2026], "season": 2026, "role": "receiving",
          "headline": [], "splits": {"season": 2026, "groups": [], "rows": []},
          "career": {"groups": [], "per_game": False, "rows": [], "total": {"gp": 0, "values": {}}}}
HURT = {"sports": {"nfl": [{"player": "Amon-Ra St. Brown", "team": "DET", "status": "Questionable",
                            "injury": "Ankle"}]}}


def _browser():
    from playwright.sync_api import sync_playwright
    kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
    if os.path.exists("/opt/pw-browsers/chromium"):
        kw["executable_path"] = "/opt/pw-browsers/chromium"
    return sync_playwright, kw


def _wait(page, check, tries=100):
    for _ in range(tries):
        if check():
            return True
        page.wait_for_timeout(100)
    return check()


def _ready(page, port, board):
    page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                         " localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=board))


def test_in_a_browser_the_page_is_asked_at_once_and_draws_before_the_injury_file():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        sync_playwright, kw = _browser()
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    ML = __import__("test_a_market_line_can_be_moved")
    board = json.dumps(ML._board())
    srv, port = rendercheck._serve()
    held = {"logs": [], "inj": []}
    asked = []
    got = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                          service_workers="block")
                page = ctx.new_page()
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)))
                _ready(page, port, board)
                page.route("**/api/players/search*", lambda r: r.fulfill(
                    status=200, content_type="application/json", body=json.dumps({"players": [HIT]})))
                page.route("**/api/players/logs*", lambda r: held["logs"].append(r))
                page.route("**/api/players/page*", lambda r: (asked.append(len(held["logs"])), r.fulfill(
                    status=200, content_type="application/json", body=json.dumps(ANSWER))))
                page.route("**/data/injuries.json*", lambda r: held["inj"].append(r))
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl", wait_until="load")
                page.wait_for_function("() => typeof openPlayerRoute === 'function' && state.data", timeout=20000)
                page.evaluate("openPlayerRoute('amon-ra-st-brown', 'Amon-Ra St. Brown')")
                got["asked_with_logs_held"] = _wait(page, lambda: bool(asked) and bool(held["logs"]))
                got["drawn_before_logs"] = page.evaluate("() => !!window._plrDrawn")
                for r in held["logs"]:
                    r.fulfill(status=200, content_type="application/json", body=json.dumps({"stats": {}}))
                held["logs"] = []
                page.wait_for_function("() => window._plrDrawn === true", timeout=15000)
                got["injury_file_asked_and_held"] = bool(held["inj"])
                got["page"] = page.evaluate("""() => ({ hero: !!document.querySelector('.plr .plr-hero'),
                    flag: (document.querySelector('.plr .plr-flag') || {}).textContent || '' })""")
                for r in held["inj"]:
                    r.fulfill(status=200, content_type="application/json", body=json.dumps(HURT))
                got["tagged"] = _wait(page, lambda: "Q" in page.evaluate(
                    "() => (document.querySelector('.plr .plr-flag') || {}).textContent || ''"))
                got["asks"] = len(asked)
                got["errs"] = list(errs)
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert got["asked_with_logs_held"], "the page's answer is asked while the market logs are still out"
    assert not got["drawn_before_logs"], "the page draws with its markets, once the logs land"
    assert got["injury_file_asked_and_held"] and got["page"]["hero"], "drawn while the injury file was still out"
    assert not got["page"]["flag"].strip(), got["page"]
    assert got["tagged"], "the header's tag fills in when the injury file lands"
    assert got["asks"] == 1, "one ask for the page: the draw found the early one"
    assert not got["errs"], got["errs"]


def test_in_a_browser_two_draws_before_the_page_script_lands_draw_one_page():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        sync_playwright, kw = _browser()
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    ML = __import__("test_a_market_line_can_be_moved")
    board = json.dumps(ML._board())
    srv, port = rendercheck._serve()
    room = []
    got = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
                page = ctx.new_page()
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)))
                _ready(page, port, board)
                page.route("**/js/playerpage.js*", lambda r: room.append(r))
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl", wait_until="load")
                page.wait_for_function("() => typeof openPlayerRoute === 'function' && state.data", timeout=20000)
                page.evaluate("openPlayerRoute('chuba-hubbard', 'Chuba Hubbard'); setTimeout(() => renderPlayers(), 50);")
                _wait(page, lambda: bool(room))
                page.wait_for_timeout(600)
                got["held"] = len(room)
                for r in room:
                    r.continue_()
                page.wait_for_selector(".plr .plr-tonight .profile", state="attached", timeout=15000)
                page.wait_for_timeout(300)
                got.update(page.evaluate("""() => ({ pages: document.querySelectorAll('.plr').length,
                    cards: document.querySelectorAll('.plr .plr-tonight .profile').length })"""))
                got["errs"] = list(errs)
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert got["held"] >= 1, got
    assert got["pages"] == 1 and got["cards"] >= 1, got
    assert not got["errs"], got["errs"]


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
