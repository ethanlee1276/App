"""The game chat on every game page, a thread on every play, and the
Live tab's feed of every game's big plays (2026-10-25).

Ethan: "look into Reel [Real] and basically copy them ... it has like a
live chat ... they have a live game feed ... a live chat for each game,
where you're able to comment on each big play". What this file pins:

* the chat is a room of its own (js/chat.js, css/chat.css) that loads the
  first time a game page mounts it, ships trimmed and is kept by the
  installed app like every other room;
* every game page mounts it — the play-by-play page on every draw, and a
  game's own page before kickoff;
* every play row in all four sports carries its thread's bubble, keyed the
  same way the chat files the thread (app.js chatPlayKey);
* the box writes each game's recent big plays onto its card, and the rule
  that picks them (espnplays.big_play) is the page's own (js/chat.js
  playIsBig), checked on the same rows in both languages;
* the Live tab has Games and a Play feed, remembered per reader.

Run directly: `python3 tests/test_the_game_chat_on_every_page.py`
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
sys.path.insert(0, str(ROOT / "tests"))

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CHAT = (ROOT / "web" / "js" / "chat.js").read_text(encoding="utf-8")
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
HOOPS = (ROOT / "web" / "js" / "hoopscast.js").read_text(encoding="utf-8")
RINK = (ROOT / "web" / "js" / "rinkcast.js").read_text(encoding="utf-8")
GC = (ROOT / "web" / "js" / "gamecast.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "chat.css").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def test_the_chat_is_a_room_of_its_own():
    assert 'function chatMount(...a) { return roomCall(chatMount, "chatMount", "js/chat.js", "css/chat.css", a); }' in APP
    assert 'function chatOpen(...a) { return roomCall(chatOpen, "chatOpen", "js/chat.js", "css/chat.css", a); }' in APP
    assert "\nfunction chatMount(league, event, d) {" in CHAT and "\nfunction chatOpen(opts) {" in CHAT
    from engine import shrink
    assert "js/chat.js" in shrink.FILES and "css/chat.css" in shrink.FILES
    assert '"/js/chat.js", "/css/chat.css"' in (ROOT / "web" / "sw.js").read_text()
    assert "@keyframes" not in CSS, "a room sheet defines no keyframes (it may use the shell's)"


def test_every_game_page_mounts_it():
    body = DETAIL[DETAIL.index("async function renderPbpPage("):]
    body = body[:body.index("\n}\n")]
    i = body.index("chatMount(league, event, d);")
    assert i < body.index("const again = () => {"), "mounted before the page chooses its layout, so all four get it"
    game = DETAIL[DETAIL.index("function renderGamePage("):]
    assert "chatMount(state.sport, row.event_id || row.game_pk, row)" in game[:game.index("\nfunction ")], \
        "a game's own page opens the same room before kickoff"


def test_the_button_stays_on_game_pages_and_the_sheet_may_open_from_live():
    assert 'const chatOnGame = () => state.view === "pbp" || state.view === "game";' in CHAT
    assert 'return !(chatOnGame() || state.view === "live");' in CHAT
    fab = _fn(CHAT, "chatFab")
    assert "if (!chatOnGame() || !CH.room) { if (f) f.remove(); return; }" in fab


def test_every_play_row_carries_its_thread():
    rows = APP[APP.index("function playsHTML(g) {"):]
    rows = rows[:rows.index("\n}\n")]
    assert 'const bubble = (p) => (g.room ? chatPlayBadge(g.room, p) : "");' in rows
    assert rows.count("${at}${bubble(p)}</div>`") == 3, "football, basketball/hockey and baseball rows"
    assert "playsHTML({ ...g, room: (g.event_id || g.game_pk) ? `${sport}_${g.event_id || g.game_pk}` : \"\" })" in APP
    assert "room: pbpRoom(d, league)" in DETAIL and "chatPlayBadge(room, r)" in DETAIL
    assert "chatPlayBadge(`${league}_${d.event_id}`, p)" in HOOPS
    assert "chatPlayBadge(`nhl_${d.event_id}`, e)" in RINK
    assert GC.count("room: d.event_id ? `${league}_${d.event_id}` : \"\"") == 2
    # One key everywhere: the chat files threads under it, the rows read it.
    assert 'const chatPlayKey = (p) => String((p && (p.kind === "atbat" ? (p.at_bat != null ? `ab${p.at_bat}` : "") : p.id)) || "");' in APP
    assert "chatPlayKey(p) === key" in CHAT


def test_the_bubble_opens_the_thread_not_the_card_under_it():
    i = APP.index('const b = e.target.closest && e.target.closest(".pr-chat");')
    seg = APP[i:i + 400]
    assert "e.stopPropagation();" in seg and "chatOpen({ room: b.dataset.chatRoom, play: b.dataset.chatPlay" in seg
    assert "chatMount(m[1], m[2], o.d || chatRowFor(o.room));" in CHAT, "a thread from the Live tab knows its game"
    assert "}, true);" in seg, "captured, ahead of the card's own click"


ROWS = [
    {"kind": "football", "event": "Pass Reception", "yards": 38, "scoring": False},
    {"kind": "football", "event": "Rush", "yards": 4, "scoring": True},
    {"kind": "football", "event": "Rush", "yards": 7},
    {"kind": "football", "event": "Penalty", "yards": 33, "penalty": True},
    {"kind": "football", "event": "Field Goal Good", "yards": 33, "scoring": True},
    {"kind": "football", "event": "Punt", "yards": 12},
    {"kind": "football", "event": "Kickoff Return (Offense)", "yards": 45},
    {"kind": "football", "event": "Sack", "yards": -8},
    {"kind": "football", "event": "Pass Interception Return", "yards": 0, "turnover": True},
    {"kind": "hoops", "event": "Jump Shot", "scoring": True, "points": 2},
    {"kind": "hoops", "event": "Three Point Jumper", "scoring": True, "points": 3},
    {"kind": "hoops", "event": "Driving Dunk Shot", "scoring": True, "points": 2},
    {"kind": "hoops", "event": "Defensive Rebound"},
    {"kind": "hockey", "event": "Goal", "scoring": True},
    {"kind": "hockey", "event": "Shot"},
]


def test_the_box_and_the_page_agree_on_a_big_play():
    from engine.sources import espnplays
    py = [espnplays.big_play(r) for r in ROWS]
    assert py == [True, True, False, False, True, False, True, True, True,
                  False, True, True, False, True, False], py
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    rink = CHAT[CHAT.index("const PLAY_RINK_WORD = {"):CHAT.index("};", CHAT.index("const PLAY_RINK_WORD = {")) + 2]
    js = rink + "\n" + _fn(CHAT, "playIsBig") + f"""
      console.log(JSON.stringify({json.dumps(ROWS)}.map(playIsBig)));"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == py, (json.loads(out.stdout), py)


def test_the_box_writes_each_games_big_plays_onto_its_card():
    import livescore_build as LB
    from engine.sources import espnplays
    src = (ROOT / "livescore_build.py").read_text()
    assert "big = [r for r in every if espnplays.big_play(r)][-BIG_PER_GAME:]" in src
    assert src.count('g["big"] = big') == 2, "football and basketball/hockey"
    assert 'if old.get("big"):\n            g["big"] = old["big"]' in src, "a capped game keeps its big plays"
    assert LB.BIG_PER_GAME >= 6
    live = (ROOT / "live_build.py").read_text()
    assert 'g["big"] = big' in live, "baseball's big at-bats too"
    # Each play keeps ESPN's own stamp, so plays from two games can be ordered.
    assert espnplays._wallclock({"wallclock": "2026-10-25T17:25:31Z"}) == "2026-10-25T17:25:31Z"
    assert espnplays._wallclock({"wallclock": "yesterday"}) == ""


def test_the_live_tab_has_games_and_a_play_feed():
    assert 'const LIVE_VIEW_KEY = "qb_live_view";' in APP
    items = _fn(CHAT, "playFeedItems")
    assert "[...(g.big || []), ...(g.plays || [])]" in items and "playIsBig(p)" in items
    assert 'Date.parse(p.at || "") || _pfSeen.get(id)' in items, "ESPN's stamp first, first seen otherwise"
    board = APP[APP.index("async function renderLiveBoard("):]
    board = board[:board.index("\n}\n")]
    # The Games / Play feed switch is drawn by the shared league chips (one
    # pill look, and the bytes the app's budget needed).
    assert '{ group: "pf-view", attr: "data-live-view", active: _liveView' in board
    assert "playFeedMount(pfHost, shown)" in board
    assert '<div class="pf-host"></div>' in board, "the feed's slot is the games' slot"
    assert "liveChatCounts(games);" in board and "async function liveChatCounts(" in CHAT
    assert "g.big," in APP[APP.index("const liveSig = "):APP.index("const liveSig = ") + 300], \
        "a new big play redraws the tab"


def test_in_a_browser_the_chat_opens_reacts_and_sends():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import time
    import rendercheck
    pbp = {"league": "nfl", "event_id": "401", "home": "ATL", "away": "SF", "generated_at": "2026-10-25T17:00:00Z",
           "live": {"state": "live", "period": "Q2", "clock": "4:12", "away_score": 7, "home_score": 3},
           "plays": [{"kind": "football", "id": "p1", "period": 2, "clock": "4:12", "team": "SF", "event": "Pass Reception",
                      "yards": 38, "scoring": True, "away_score": 7, "home_score": 3, "players": ["Brock Purdy", "George Kittle"]}],
           "drives": [{"team": "SF", "plays": [], "yards": 75}]}
    pbp["drives"][0]["plays"] = pbp["plays"]
    room = {"room": "nfl_401", "t": time.time(), "older": False, "reacts": {}, "plays": {"p1": {"fire": 3}}, "threads": {},
            "mine_plays": {}, "votes": {"home": 1, "away": 2, "mine": "", "open": True}, "here": 9,
            "me": {"signed_in": True, "handle": "kai", "founder": False},
            "messages": [{"id": 1, "at": time.time() - 30, "body": "what a throw", "own": False, "reacts": {}, "mine": "",
                          "by": {"handle": "sam", "name": "", "color": 1, "team": "", "verified": False, "official": False,
                                 "founder": False, "following": False}}]}
    posted = []
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(args=["--no-sandbox"], executable_path="/opt/pw-browsers/chromium")
            p = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                              service_workers="block").new_page()
            errs = []
            p.on("pageerror", lambda e: errs.append(str(e)))
            p.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
            p.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())

            def mk(body):
                return lambda r: r.fulfill(status=200, content_type="application/json", body=body)

            def post(r):
                posted.append(r.request.url.rsplit("/", 1)[-1])
                r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "mine": "fire", "id": 2}))
            p.route("**/data/pbp/nfl_401.json*", mk(json.dumps(pbp)))
            p.route("**/api/chat/room*", mk(json.dumps(room)))
            for k in ("send", "play", "vote", "react"):
                p.route(f"**/api/chat/{k}", post)
            p.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#pbp/nfl/401", wait_until="load")
            # The card under the scoreboard is the door in (EJ, step 193); the
            # bar at the bottom says the same thing, so it waits until the
            # card has scrolled away (chat.js: body.gch-card-in).
            p.wait_for_selector(".gch-entry", timeout=20000)
            p.click(".gch-entry")
            p.wait_for_selector("#gch-sheet .gch-msg", timeout=10000)
            assert "what a throw" in p.inner_text("#gch-sheet .gch-body")
            assert "9 watching" in p.inner_text("#gch-sheet .gch-head")   # the rebuilt sheet's word (EJ)
            p.click("#gch-sheet [data-gch=tab][data-tab=plays]")
            p.wait_for_selector("#gch-sheet .gch-playcard", timeout=5000)
            p.click("#gch-sheet .gch-playcard [data-gch=playface][data-kind=fire]")
            p.click("#gch-sheet [data-gch=vote][data-side=away]")
            p.click("#gch-sheet [data-gch=tab][data-tab=all]")
            p.fill("#gch-sheet .gch-input", "Kittle is a cheat code")
            p.click("#gch-sheet .gch-send")
            p.wait_for_timeout(600)
            assert {"play", "vote", "send"} <= set(posted), posted
            p.click("#gch-sheet [data-gch=close]")
            assert p.is_visible(".gch-entry"), "the card is the way back in"
            # Scrolled past the card, the bar at the bottom takes its place.
            p.evaluate("window.scrollTo(0, document.scrollingElement.scrollHeight)")
            p.wait_for_timeout(400)
            assert p.evaluate("(() => { const r = document.querySelector('.gch-entry').getBoundingClientRect();"
                              " return r.bottom < 0 || r.top > innerHeight; })()"), "the card scrolled away"
            p.wait_for_selector("#gch-fab", timeout=5000)
            assert not errs, errs
            b.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
