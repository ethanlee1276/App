"""A player's own numbers are asked before its market cards' charts (step AFN, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load". A player page drawn cold asked for its own answer
and, beside it, every market card's charts (routes, carries, role and tonight's matchup for a running back): five
answers at once from a server with one core, the top of the page's among them. The market cards' charts now wait
until the page's own numbers have landed (app.js mountCharts and chartsAfterPage; js/playerpage.js marks the address
filled), and never past four seconds, so a page whose answer never comes still draws them. Every other chart slot
(a pick page's) draws at once, as before. And two draws of the page at once share one ask for the player's logs.

The browser half runs with QB_BROWSER_TESTS=1 and /usr/bin/python3.
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
PAGE = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")

CHARTS = ("/api/players/routes", "/api/players/carries", "/api/players/chart")
ANSWER = {"sport": "nfl", "player": "Chuba Hubbard", "team": "CAR", "position": "RB", "bio": {},
          "notes": {"injury": None, "moves": []}, "seasons": [2026], "season": 2026, "role": "rushing",
          "headline": [], "splits": {"season": 2026, "groups": [], "rows": []},
          "career": {"groups": [], "per_game": False, "rows": [], "total": {"gp": 0, "values": {}}}}


def _fn(src, head):
    i = src.index(head)
    return src[i:src.index("\n}\n", i) + 2]


def test_the_page_holds_its_cards_charts_until_its_numbers_land():
    mount = _fn(APP, "function mountCharts(root, all) {")
    assert ('.filter((el) => all || !(state.playerSlug\n'
            '    && window._plrFilledRoute !== state.playerSlug && el.closest("#players-board") && _ccHeld.push(el)));'
            ) in mount, "on a player's address, in the players view, until its page is filled"
    assert "if (_ccHeld.length) setTimeout(chartsAfterPage, 4000);" in mount
    assert "el.isConnected && !el.dataset.on && m.mount(el)" in mount
    after = _fn(APP, "function chartsAfterPage() {")
    assert "mountCharts({ querySelectorAll: () => _ccHeld.splice(0) }, true);" in after, \
        "every held slot, released past the hold, so the four seconds' fallback draws them too"
    fill = PAGE[PAGE.index("  const fill = (d) => {"):]
    fill = fill[:fill.index("  };\n") + 5]
    assert fill.index("window._plrFilledRoute = state.playerSlug;") < fill.index("plrFill(page, d);") < fill.index(
        "chartsAfterPage();"), "filled first, so the page's own chart draws in plrFill; then the cards'"


def test_two_draws_share_one_ask_for_the_players_logs():
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("node"):
        print("      (skipped: no node)")
        return
    fn = _fn(APP, "function oneAsk(key, make) {") + _fn(APP, "async function leagueLogs(player, sport) {")
    prog = ("let calls = 0; const state = { sport: 'nfl' };\n"
            "const fetch = async (u) => { calls++; await new Promise((r) => setTimeout(r, 20));"
            " return { ok: true, json: async () => ({ stats: { Receptions: [{ week: 12, value: 7 }] } }) }; };\n"
            + fn +
            "(async () => { const [a, b] = await Promise.all([leagueLogs('Amon-Ra St. Brown', 'nfl'),"
            " leagueLogs('Amon-Ra St. Brown', 'nfl')]); const c = await leagueLogs('Amon-Ra St. Brown', 'nfl');"
            " console.log(JSON.stringify({ calls, same: a === b, again: c.Receptions[0].value })); })();\n")
    path = os.path.join(tempfile.mkdtemp(), "t.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    assert json.loads(out.stdout) == {"calls": 2, "same": True, "again": 7}, \
        "one ask for two draws at once; a later draw asks afresh"


def test_three_draws_share_one_ask_for_the_players_search():
    """STEP AFS: Jahmyr Gibbs's address drew the players view three times as it came up, and each draw asked the
    server for the same search (three answers at once, landing 1.4, 2.1 and 2.2 s in); the page's own request
    waited for the last. A search asked while the same one is out shares it."""
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("node"):
        print("      (skipped: no node)")
        return
    prog = ("let calls = 0; const LEAGUE_RETRY_MS = 30000; const _leagueCache = new Map();"
            " const searchLeague = () => 'nfl';\n"
            "const fetch = async (u) => { calls++; await new Promise((r) => setTimeout(r, 20));"
            " return { ok: true, json: async () => ({ players: [{ player: 'Jahmyr Gibbs', team: 'DET' }] }) }; };\n"
            + _fn(APP, "function oneAsk(key, make) {") + _fn(APP, "async function leagueSearch(q) {") +
            "(async () => { const got = await Promise.all([leagueSearch('jahmyr gibbs'), leagueSearch('jahmyr gibbs'),"
            " leagueSearch('jahmyr gibbs')]); const again = await leagueSearch('jahmyr gibbs');"
            " console.log(JSON.stringify({ calls, n: got.map((g) => g.length), again: again[0].player })); })();\n")
    path = os.path.join(tempfile.mkdtemp(), "t.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    assert json.loads(out.stdout) == {"calls": 1, "n": [1, 1, 1], "again": "Jahmyr Gibbs"}, \
        "one ask for three draws, and the answer kept for the next"


def _run(answer_after):
    from playwright.sync_api import sync_playwright
    import rendercheck
    ML = __import__("test_a_market_line_can_be_moved")
    board = json.dumps(ML._board())
    srv, port = rendercheck._serve()
    held, seen = [], []
    got = {}
    t0 = [0.0]
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
                page = ctx.new_page()
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.on("request", lambda r: seen.append((time.time() - t0[0], r.url)) if any(
                    c in r.url for c in CHARTS) else None)
                page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); "
                                     "localStorage.setItem('qb_intro_v1', '1'); localStorage.setItem('qb.tour', 'done');"
                                     " } catch (e) {}")
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=board))
                page.route("**/api/players/page*", lambda r: held.append(r))
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl", wait_until="load")
                page.wait_for_function("() => typeof openPlayerRoute === 'function' && state.data", timeout=20000)
                page.wait_for_timeout(1500)
                seen.clear()
                t0[0] = time.time()
                page.evaluate("openPlayerRoute('chuba-hubbard', 'Chuba Hubbard')")
                page.wait_for_selector(".plr .plr-tonight .cc-slot", state="attached", timeout=15000)
                page.wait_for_timeout(1500)
                got["asked"] = bool(held)
                got["charts_while_held"] = len(seen)
                if answer_after:
                    released = time.time() - t0[0]
                    for r in held:
                        r.fulfill(status=200, content_type="application/json", body=json.dumps(ANSWER))
                    for _ in range(60):
                        if seen:
                            break
                        page.wait_for_timeout(100)
                    got["first_chart_after_release"] = (seen[0][0] - released) if seen else None
                else:
                    for _ in range(60):
                        if seen:
                            break
                        page.wait_for_timeout(100)
                    got["first_chart_at"] = seen[0][0] if seen else None
                    for r in held:              # answered at last, so nothing is left hanging at close
                        r.fulfill(status=200, content_type="application/json", body=json.dumps(ANSWER))
                    page.wait_for_timeout(300)
                got["errs"] = list(errs)
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return got


def test_in_a_browser_the_charts_wait_for_the_pages_numbers():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    got = _run(answer_after=True)
    assert got["asked"], "the page asked for its numbers"
    assert got["charts_while_held"] == 0, got
    assert got["first_chart_after_release"] is not None and got["first_chart_after_release"] >= 0, got
    assert not got["errs"], got["errs"]
    late = _run(answer_after=False)
    assert late["asked"] and late["charts_while_held"] == 0, late
    assert late["first_chart_at"] is not None and 3.5 <= late["first_chart_at"] <= 6.5, \
        f"an answer that never comes holds them four seconds: {late}"
    assert not late["errs"], late["errs"]


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
