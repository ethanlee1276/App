"""The game chat's doors open the whole sheet, every time, without an error.

2026-10-26, Ethan: "the buttons to get to the game chat page are buggy and
glitch out and throw errors sometimes". Two causes, both held here:

  - a second `mbLoad` (the Live strip's, now `lvmLoad`) replaced My Bets'
    loader once the chat room loaded, so opening the sheet threw
    "mbLoad(...).filter is not a function" and drew half of it;
  - the card under the scoreboard was rebuilt on every redraw and poll, so
    a tap that landed mid-rebuild hit a button that was gone. One button
    now lives for the visit.

And on a computer the bar no longer outstays the game: it was cleared by
state.view, which a view transition leaves on the game for a moment.

    python3 tests/test_the_chat_doors_open_without_errors.py
    (the browser half with QB_BROWSER_TESTS=1 and Playwright)
"""
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
CHAT = open(os.path.join(ROOT, "web", "js", "chat.js"), encoding="utf-8").read()


def test_the_bar_is_cleared_by_the_address_not_by_state_view():
    i = CHAT.index('window.addEventListener("hashchange", () => setTimeout(() => {')
    body = CHAT[i:CHAT.index("}, 0));", i)]
    assert 'const v = (location.hash || "").replace(/^#/, "").split("/")[0];' in body
    assert "chatGone()" not in body and "chatOnGame()" not in body


def _game(eid, n):
    iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    plays = [{"kind": "football", "id": f"p{i}", "period": 3, "clock": f"{9 - i % 9}:{10 + i % 40:02d}",
              "team": "CIN" if i % 2 else "PIT", "event": ["Rush", "Pass Reception", "Passing Touchdown"][i % 3],
              "yards": [4, 18, 31][i % 3], "scoring": i % 3 == 2, "away_score": 14, "home_score": 10,
              "players": ["Joe Burrow"], "rating": 7.8 if i % 3 == 2 else 2.1} for i in range(4 + n)]
    return {"league": "nfl", "event_id": eid, "generated_at": iso, "home": "CIN", "away": "PIT",
            "home_name": "Cincinnati Bengals", "away_name": "Pittsburgh Steelers",
            "live": {"state": "live", "home_score": 10, "away_score": 14, "period": 3, "clock": f"{9 - n % 9}:00",
                     "detail": f"3rd {9 - n % 9}:00"},
            "drives": [{"id": "d1", "team": "CIN", "result": "Touchdown", "plays": plays}], "plays": plays,
            "drive": {"team": "PIT", "plays": 1, "yards": 5}}


def test_in_a_browser_every_door_opens_the_whole_sheet_and_nothing_throws():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    pbp = os.path.join(ROOT, "web", "data", "pbp")
    made = not os.path.isdir(pbp)
    os.makedirs(pbp, exist_ok=True)
    path = os.path.join(pbp, "nfl_990077.json")
    with open(path, "w") as fh:
        fh.write(json.dumps(_game("990077", 0)))
    now = time.time()
    msgs = [{"id": 100 + i, "at": now - (6 - i) * 40, "body": f"message {i}", "by": {"handle": f"fan{i}", "color": i},
             "own": False, "reacts": {}, "mine": ""} for i in range(6)]
    n = {"room": 0, "pbp": 0}

    def room(route):
        n["room"] += 1
        route.fulfill(status=200, content_type="application/json", body=json.dumps({
            "room": "nfl_990077", "t": time.time(), "messages": msgs, "older": False, "reacts": {}, "plays": {},
            "threads": {}, "mine_plays": {}, "votes": {"home": 3 + n["room"], "away": 2, "mine": "", "open": True},
            "here": 20 + n["room"], "me": {"signed_in": True, "handle": "fan0"}}))

    def game(route):
        n["pbp"] += 1
        route.fulfill(status=200, content_type="application/json", body=json.dumps(_game("990077", n["pbp"])))

    me = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "fan0"}}
    bill = {"signed_in": True, "email": "you@example.com", "paywall": True, "entitled": True, "plans": []}
    slip = [{"id": "s1", "src": "slip", "result": "pending", "legs": [{"player": "Joe Burrow", "market": "pass yds",
             "side": "OVER", "line": 250.5, "odds": -110, "league": "nfl"}], "stake": 10, "odds": -110}]
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    errs, got = [], {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block",
                                          is_mobile=True, has_touch=True)
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/account/me*", ful(json.dumps(me)))
                page.route("**/api/billing/status*", ful(json.dumps(bill)))
                page.route("**/api/chat/room*", room)
                page.route("**/api/chat/counts*", ful(json.dumps({"rooms": {}})))
                page.route("**/api/chat/ticket*", ful(json.dumps({"legs": []})))
                page.route("**/api/callit/**", ful(json.dumps({"open": None, "kind": "football", "board": []})))
                page.route("**/data/pbp/nfl_990077*", game)
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb_chat_rules_v1','1');"
                                     f"localStorage.setItem('qb_mybets_v1', {json.dumps(json.dumps(slip))});}}catch(e){{}}")
                page.add_init_script("""window.__cards = new Set(); setInterval(() => { const c = document.querySelector('.gch-entry');
                  if (c) { c.__id = c.__id || Math.random(); window.__cards.add(c.__id); } }, 50);""")
                page.goto(f"http://127.0.0.1:{port}/index.html#pbp/nfl/990077", wait_until="load")
                page.wait_for_timeout(11500)       # two of the page's own redraws, and the room's polls
                got["buttons"] = page.evaluate("window.__cards.size")
                full = ("(() => { const s = document.getElementById('gch-sheet'); return !!(s && s.querySelector('.gch-body').children.length"
                        " && s.querySelector('.gch-foot').children.length); })()")
                page.evaluate("(() => { const c = document.querySelector('.gch-entry'); c.scrollIntoView({block: 'center'}); c.click(); })()")
                page.wait_for_timeout(700)
                got["card"] = page.evaluate(full)
                page.evaluate("document.querySelector('[data-gch=close]').click()")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(700)
                page.evaluate("document.getElementById('gch-fab').click()")
                page.wait_for_timeout(700)
                got["bar"] = page.evaluate(full)
                got["mybets"] = page.evaluate("Array.isArray(mbLoad())")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
        os.remove(path)
        if made:
            shutil.rmtree(pbp, ignore_errors=True)
    assert not errs, errs[:3]
    assert got["card"] and got["bar"], got
    assert got["buttons"] == 1, f"the card was rebuilt across redraws ({got['buttons']} buttons)"
    assert got["mybets"], "My Bets' loader was replaced once the chat room loaded"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
