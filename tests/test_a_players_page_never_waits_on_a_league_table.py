"""A player's page never waits for a league table to be built (step AFU, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load". The season card's league places come from one
table per league, season and kind of player (engine/playerpage.rank_table). `warm` builds each league's newest
season at start and the tables are kept on disk (step AFO), but a page for an older season built its table while
the reader waited: Cameron Boozer's college page (his newest season is 2025-26) took 29.3 s on the live site,
28.7 s of it the college table (7.1 s of the server's own time). The site's pages now never wait: a table neither
kept nor on disk is built behind the page, the answer comes without its places and says "ranks_pending", the server
keeps no copy of it, and the page asks again at 3, 6, 12 and 24 s and redraws its season card once they are in.
`warm` leaves a table a page started to that build, and marks its own, so one table is never built twice at once.
Called directly (tools, tests), `page` still builds the table first, as before.

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
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import playerpage as PP                                         # noqa: E402

EV = __import__("test_every_player_has_a_page_of_their_own")
PAGE = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")
KEY = ("nfl", 2026, "passing")


def _built(key, timeout=20.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if key in PP._RANKS and key not in PP._REFRESHING:
            return True
        time.sleep(0.05)
    return False


def test_a_page_whose_table_is_not_built_answers_at_once_and_builds_it_behind():
    path, rosters = EV._fresh()
    d = PP.page("nfl", "Josh Allen", db_path=path, data_dir=rosters, wait_ranks=False)
    h = {x["key"]: x for x in d["headline"]}
    assert d.get("ranks_pending") is True, "said so"
    assert (h["yds"]["value"], h["yds"]["rank"], h["td"]["rank"]) == (803, None, None), \
        "the numbers, without places this once"
    assert d["last"]["score"] == "31-12" and d["splits"]["rows"], "and the rest of the page as ever"
    assert _built(KEY), "the table was built behind the answer"
    again = PP.page("nfl", "Josh Allen", db_path=path, data_dir=rosters, wait_ranks=False)
    h = {x["key"]: x for x in again["headline"]}
    assert "ranks_pending" not in again and (h["yds"]["rank"], h["td"]["rank"]) == (2, 2)


def test_called_directly_the_page_still_builds_its_table_first():
    path, rosters = EV._fresh()
    d = PP.page("nfl", "Josh Allen", db_path=path, data_dir=rosters)
    h = {x["key"]: x for x in d["headline"]}
    assert "ranks_pending" not in d and (h["yds"]["rank"], h["int"]["rank"]) == (2, 1)


def test_a_kept_table_answers_without_a_build():
    path, rosters = EV._fresh()
    PP._RANKS[KEY] = (time.time(), {"yds": {"Josh Allen": 9}})
    d = PP.page("nfl", "Josh Allen", db_path=path, data_dir=rosters, wait_ranks=False)
    assert "ranks_pending" not in d and {x["key"]: x for x in d["headline"]}["yds"]["rank"] == 9
    assert KEY not in PP._REFRESHING


def test_warm_leaves_a_table_being_built_to_that_build_and_marks_its_own():
    path, _ = EV._fresh()
    seen = []
    real = PP._build_table

    def build(conn, sport, season, kind):
        seen.append(((sport, season, kind), (sport, season, kind) in PP._REFRESHING))
        return real(conn, sport, season, kind)
    PP._build_table = build
    PP._REFRESHING.add(KEY)
    try:
        PP.warm(db_path=path, delay=0).join(timeout=60)
    finally:
        PP._REFRESHING.discard(KEY)
        PP._build_table = real
    built = {k for k, _ in seen}
    assert KEY not in built and KEY not in PP._RANKS, "the page's own build of it is left to finish"
    assert ("nfl", 2026, "rushing") in built and all(marked for _, marked in seen), seen
    assert not any(k[0] == "nfl" for k in PP._REFRESHING), "and none is left marked"


def _handler(path):
    import server
    h = object.__new__(server.Handler)
    sent = []
    h.send_response = lambda code, *a: sent.append(("status", code))
    h.send_header = lambda k, v: sent.append((k, v))
    h.end_headers = lambda: None

    class _Out:
        def write(self, b):
            sent.append(("body", b))
    h.wfile = _Out()
    h._is_https = lambda: False
    h.path = path
    h._clock = (time.perf_counter(), time.thread_time())
    return h, sent


def test_the_server_sends_an_answer_without_places_but_never_keeps_it():
    import server
    pending = json.dumps({"player": "Sam Hands", "sport": "nfl", "headline": [], "ranks_pending": True}).encode()
    whole = json.dumps({"player": "Sam Hands", "sport": "nfl", "headline": []}).encode()
    made, real_made, real_stamp = [pending], server._player_page_made, server._player_games_stamp
    server._player_page_made = lambda *a, **k: made[0]
    server._player_games_stamp = lambda *a, **k: None
    key = ("nfl", "sam hands", "", "")
    try:
        server._PLAYER_PAGES.pop(key, None)
        h, sent = _handler("/api/players/page?sport=nfl&player=Sam+Hands")
        h._players_page({"sport": ["nfl"], "player": ["Sam Hands"]})
        assert ("body", pending) in sent and ("status", 200) in sent
        assert key not in server._PLAYER_PAGES, "sent, never kept: the next ask finds the table"
        server._player_page_fresh("nfl", "Sam Hands", "", "", key)
        assert key not in server._PLAYER_PAGES, "nor kept by a rebuild behind a kept one"
        made[0] = whole
        h, sent = _handler("/api/players/page?sport=nfl&player=Sam+Hands")
        h._players_page({"sport": ["nfl"], "player": ["Sam Hands"]})
        assert server._PLAYER_PAGES[key][1] == whole, "a whole answer is kept as before"
    finally:
        server._player_page_made, server._player_games_stamp = real_made, real_stamp
        server._PLAYER_PAGES.pop(key, None)
    assert "took=took, wait_ranks=False)" in SERVER, "the site's pages never wait on a table"


def _node(answers, tries_body):
    if not shutil.which("node"):
        return None

    def fn(head):
        i = PAGE.index(head)
        return PAGE[i:PAGE.index("\n}\n", i) + 2]

    def const(head):
        i = PAGE.index(head)
        return PAGE[i:PAGE.index("\n", i) + 1]
    prog = ("const delays = []; const asked = [];\n"
            "const setTimeout = (f, ms) => { delays.push(ms); Promise.resolve().then(f); };\n"
            "const loadRoom = async () => false;\n"
            f"const ANSWERS = {json.dumps(answers)};\n"
            "const fetch = async (u) => { asked.push(u); const a = ANSWERS[Math.min(asked.length - 1, ANSWERS.length - 1)];"
            " return { ok: true, json: async () => JSON.parse(JSON.stringify(a)) }; };\n"
            "const plrSeasonHTML = (d) => `rank ${(d.headline[0] || {}).rank}`;\n"
            + const("const PLR_CACHE = new Map();") + const("const PLR_ASK = new Map();") + const("const PLR_LOG = new Map();")
            + fn("function plrLogSoon(sport, player, team) {") + fn("function plrRanksLater(page, was, tries = 0) {")
            + fn("function plrFetch(sport, player, team, season) {")
            + fn("async function plrAsk(key, sport, player, team, season) {")
            + "const season = { innerHTML: 'rank null' };\n"
              "const page = { isConnected: true, _plr: { sport: 'nfl' }, _ask: { player: 'Sam Hands', team: 'BUF' },"
              " querySelector: (s) => (s === '.plr-season' ? season : null) };\n"
              "(async () => {\n" + tries_body + "\n})().catch((e) => { console.error(e); process.exit(1); });\n")
    path = os.path.join(tempfile.mkdtemp(), "t.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


PENDING = {"player": "Sam Hands", "sport": "nfl", "season": 2026, "ranks_pending": True,
           "headline": [{"key": "yds", "label": "YDS", "value": 803, "rank": None}]}
WHOLE = {"player": "Sam Hands", "sport": "nfl", "season": 2026,
         "headline": [{"key": "yds", "label": "YDS", "value": 803, "rank": 2}]}
SETTLE = "for (let i = 0; i < 50; i++) await new Promise((r) => global.setTimeout(r, 1));\n"


def test_the_page_asks_again_and_redraws_its_season_card():
    got = _node([PENDING, PENDING, WHOLE],
                "const first = await plrFetch('nfl', 'Sam Hands', 'BUF');\n"
                "plrRanksLater(page, first);\n" + SETTLE +
                "console.log(JSON.stringify({ delays, asks: asked.length, card: season.innerHTML,"
                " kept: (PLR_CACHE.get('nfl|Sam Hands|BUF|') || {}).headline[0].rank }));")
    if got is None:
        print("      (skipped: no node)")
        return
    assert got == {"delays": [3000, 6000], "asks": 3, "card": "rank 2", "kept": 2}, got


def test_the_page_stops_asking_after_four_tries():
    got = _node([PENDING],
                "const first = await plrFetch('nfl', 'Sam Hands', 'BUF');\n"
                "plrRanksLater(page, first);\n" + SETTLE +
                "console.log(JSON.stringify({ delays, asks: asked.length, card: season.innerHTML }));")
    if got is None:
        print("      (skipped: no node)")
        return
    assert got == {"delays": [3000, 6000, 12000, 24000], "asks": 5, "card": "rank null"}, got


def test_the_page_starts_asking_when_its_answer_says_so():
    fill = PAGE[PAGE.index("  const fill = (d) => {"):]
    fill = fill[:fill.index("  };\n") + 5]
    assert "if (d && d.ranks_pending && page.isConnected) plrRanksLater(page, d);" in fill


ANSWER = {"sport": "nfl", "player": "Chuba Hubbard", "team": "CAR", "position": "RB", "bio": {},
          "notes": {"injury": None, "moves": []}, "seasons": [2026], "season": 2026, "role": "rushing",
          "headline": [{"key": "yds", "label": "YDS", "title": "Rushing yards", "value": 812, "rank": None,
                        "per_game": False, "low": False}],
          "splits": {"season": 2026, "groups": [], "rows": []},
          "career": {"groups": [], "per_game": False, "rows": [], "total": {"gp": 0, "values": {}}}}


def test_in_a_browser_the_places_come_in_a_few_seconds_on():
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
    board = json.dumps(ML._board())
    srv, port = rendercheck._serve()
    asks = []
    got = {}

    def on_page(r):
        asks.append(time.time())
        body = dict(ANSWER, ranks_pending=True) if len(asks) == 1 else dict(
            ANSWER, headline=[dict(ANSWER["headline"][0], rank=7)])
        r.fulfill(status=200, content_type="application/json", body=json.dumps(body))
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
                page.route("**/api/players/page*", on_page)
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl", wait_until="load")
                page.wait_for_function("() => typeof openPlayerRoute === 'function' && state.data", timeout=20000)
                page.wait_for_timeout(1500)
                page.evaluate("openPlayerRoute('chuba-hubbard', 'Chuba Hubbard')")
                page.wait_for_selector(".plr .plr-season .plr-num", state="attached", timeout=15000)
                got["first"] = page.inner_text(".plr .plr-season")
                page.wait_for_selector(".plr .plr-season .plr-rank", state="attached", timeout=15000)
                got["then"] = page.inner_text(".plr .plr-season")
                got["asks"] = len(asks)
                got["gap"] = asks[1] - asks[0] if len(asks) > 1 else None
                got["errs"] = list(errs)
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert "812" in got["first"] and "7th" not in got["first"], got
    assert "812" in got["then"] and "7th" in got["then"], got
    assert got["asks"] == 2 and 2.5 <= got["gap"] <= 6, got
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
