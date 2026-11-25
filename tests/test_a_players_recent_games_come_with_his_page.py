"""A player's recent games are asked beside his page's own numbers (step AFT, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load". The Overview's Recent games card read the game log
(/api/players/gamelog, 12 to 18 ms of the server's time), but asked for it only once the page's own answer had
landed, a round trip after it: timed live on Amon-Ra St. Brown's page, the page answered at 2.0 s, the log was asked
at 2.19 s and the card drew at 2.7 s. The page's first ask (js/playerpage.js plrFetch, season unset) now asks for
the log too (plrLogSoon), and the card uses that answer when it is the one the page names: the same stored player,
the same season, and the club the page was asked with being the club it answered (a name two players share keeps
his club's games, step AFF). Otherwise it asks as before. A season picked in Splits asks no log; a fighter has none.

The browser half runs with QB_BROWSER_TESTS=1 and /usr/bin/python3.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

PAGE = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")


def _fn(src, head):
    i = src.index(head)
    return src[i:src.index("\n}\n", i) + 2]


def _const(src, head):
    i = src.index(head)
    return src[i:src.index("\n", i) + 1]


def _node(body):
    if not shutil.which("node"):
        return None
    prog = ("const calls = []; let pageAsks = 0, logsAtAnswer = null;\n"
            "const escapeHtml = (s) => String(s);\n"
            "const glTableHTML = (d) => `T${d.games.length}`;\n"
            "const loadRoom = async () => true;\n"
            "async function glFetch(sport, player, season, team) { calls.push([sport, player, season, team]);"
            " await new Promise((r) => setTimeout(r, 5));"
            " return { sport, player: 'Amon-Ra St. Brown', season: 2026, team: 'DET', games: [{ week: 12 }] }; }\n"
            "const fetch = async (u) => { pageAsks++; await new Promise((r) => setTimeout(r, 30));"
            " if (logsAtAnswer === null) logsAtAnswer = calls.length;"
            " return { ok: true, json: async () => ({ player: 'Amon-Ra St. Brown', season: 2026, team: 'DET' }) }; };\n"
            + _const(PAGE, "const PLR_CACHE = new Map();") + _const(PAGE, "const PLR_ASK = new Map();")
            + _const(PAGE, "const PLR_LOG = new Map();")
            + _fn(PAGE, "function plrLogSoon(sport, player, team) {") + _fn(PAGE, "function plrFetch(sport, player, team, season) {")
            + _fn(PAGE, "async function plrAsk(key, sport, player, team, season) {")
            + _fn(PAGE, "async function plrRecentInto(slot, d, asked) {")
            + "(async () => {\n" + body + "\n})().catch((e) => { console.error(e); process.exit(1); });\n")
    path = os.path.join(tempfile.mkdtemp(), "t.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def test_the_log_is_asked_with_the_page_and_used_once_it_lands():
    got = _node(
        "const d = await plrFetch('nfl', 'Amon-Ra St. Brown', 'DET');\n"
        "const asked = logsAtAnswer;\n"
        "const slot = { isConnected: true, innerHTML: '' };\n"
        "await plrRecentInto(slot, { ...d, sport: 'nfl' }, { player: 'Amon-Ra St. Brown', team: 'DET' });\n"
        "console.log(JSON.stringify({ asked, calls, pageAsks, drawn: slot.innerHTML.includes('Recent games') }));")
    if got is None:
        print("      (skipped: no node)")
        return
    assert got["asked"] == 1, "the log was asked before the page's own answer landed"
    assert got["calls"] == [["nfl", "Amon-Ra St. Brown", "", "DET"]], "and only once: the card uses that answer"
    assert got["pageAsks"] == 1 and got["drawn"], got


def test_an_answer_naming_another_season_or_club_asks_afresh():
    got = _node(
        "await plrFetch('nfl', 'Amon-Ra St. Brown', '');\n"
        "const slot = { isConnected: true, innerHTML: '' };\n"
        "await plrRecentInto(slot, { sport: 'nfl', player: 'Amon-Ra St. Brown', season: 2026, team: 'DET' },"
        " { player: 'Amon-Ra St. Brown', team: '' });\n"
        "await plrRecentInto(slot, { sport: 'nfl', player: 'Amon-Ra St. Brown', season: 2025, team: '' },"
        " { player: 'Amon-Ra St. Brown', team: '' });\n"
        "await plrRecentInto(slot, { sport: 'nfl', player: 'Amon-Ra St. Brown', season: 2026, team: 'DET' });\n"
        "console.log(JSON.stringify({ calls }));")
    if got is None:
        print("      (skipped: no node)")
        return
    assert got["calls"] == [["nfl", "Amon-Ra St. Brown", "", ""],
                            ["nfl", "Amon-Ra St. Brown", 2026, "DET"],
                            ["nfl", "Amon-Ra St. Brown", 2025, ""],
                            ["nfl", "Amon-Ra St. Brown", 2026, "DET"]], \
        "asked without a club but answered with one; another season; no ask on record: each asks as before"


def test_a_season_picked_and_a_fighter_ask_no_log():
    got = _node(
        "await plrFetch('nfl', 'Amon-Ra St. Brown', 'DET', 2025);\n"
        "await plrFetch('ufc', 'Alex Pereira', '');\n"
        "console.log(JSON.stringify({ calls, pageAsks }));")
    if got is None:
        print("      (skipped: no node)")
        return
    assert got == {"calls": [], "pageAsks": 2}, got


def test_the_page_keeps_what_it_was_asked_with():
    assert "page._ask = { player, team };" in PAGE
    assert "plrRecentInto(at(\".plr-recent\"), d, page._ask);" in PAGE
    assert "if (!season && sport !== \"ufc\") plrLogSoon(sport, player, team);" in PAGE


LOG = {"sport": "nfl", "player": "Chuba Hubbard", "season": 2026, "seasons": [2026], "team": "CAR", "position": "RB",
       "groups": [{"key": "rushing", "title": "Rushing", "cols": [{"key": "yds", "label": "YDS", "title": "Rushing yards"}]}],
       "games": [{"date": "2026-11-23", "week": 12, "opponent": "SF", "home": True, "result": "W", "score": "20-17",
                  "values": {"rushing.yds": 88}}], "totals": {}, "per_game": {}, "played": 1}


def test_in_a_browser_the_log_is_asked_while_the_page_waits():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    ML = __import__("test_a_market_line_can_be_moved")
    CH = __import__("test_a_players_numbers_come_before_its_charts")
    board = json.dumps(ML._board())
    srv, port = rendercheck._serve()
    held, logs = [], []
    got = {}
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
                page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); "
                                     "localStorage.setItem('qb_intro_v1', '1'); localStorage.setItem('qb.tour', 'done');"
                                     " } catch (e) {}")
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=board))
                page.route("**/api/players/page*", lambda r: held.append(r))

                def on_log(r):
                    logs.append(r.request.url)
                    r.fulfill(status=200, content_type="application/json", body=json.dumps(LOG))
                page.route("**/api/players/gamelog*", on_log)
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl", wait_until="load")
                page.wait_for_function("() => typeof openPlayerRoute === 'function' && state.data", timeout=20000)
                page.wait_for_timeout(1500)
                logs.clear()
                page.evaluate("openPlayerRoute('chuba-hubbard', 'Chuba Hubbard')")
                page.wait_for_selector(".plr .plr-recent", state="attached", timeout=15000)
                t0 = time.time()
                while not logs and time.time() - t0 < 6:
                    page.wait_for_timeout(100)
                got["held"] = len(held)
                got["logs_while_held"] = len(logs)
                for r in held:
                    r.fulfill(status=200, content_type="application/json", body=json.dumps(CH.ANSWER))
                page.wait_for_selector(".plr .plr-recent .plr-card", state="attached", timeout=15000)
                page.wait_for_timeout(500)
                got["logs"] = list(logs)
                got["card"] = page.inner_text(".plr .plr-recent .plr-card")
                got["errs"] = list(errs)
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert got["held"], "the page asked for its numbers"
    assert got["logs_while_held"] >= 1, f"the log was asked while the page's own answer was still out: {got}"
    assert len(got["logs"]) == 1, f"one ask: the card used it ({got['logs']})"
    assert "Recent games" in got["card"] and "88" in got["card"], got["card"]
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
