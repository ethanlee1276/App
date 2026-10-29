"""The fans' player of the game (engine/gamechat potg; Ethan, 2026-10-28:
"keep building … keep inventing … keep user retainment").

theScore and ESPN close a game with a fan vote; ours opens in the game's
chat the moment the game is final, where the who-wins bar was. What this
file pins:

  * the four names are the game's best lines off its box, scored per sport
    as the final-score alert does, each with its line ("312 pass yds, 2
    TD"); a file with no box falls back to the plays' own 0-10 ratings (the
    first named carries a play, the rest half of it), either team;
  * the vote opens only once the scoreboard calls the game final, keeps
    the names it opened with whatever the file says after, takes one vote
    an account, shows how the room voted only to those who have, and
    closes after a day;
  * a vote pays +5 karma once a game; the votes go with the account and
    the old ones are pruned with the room;
  * the chat draws it, and in a browser a tap votes and shows the room.

Run directly: `python3 tests/test_the_fans_player_of_the_game.py`
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A                             # noqa: E402
from engine import gamechat as GC                            # noqa: E402
from engine import karma as K                                # noqa: E402
from engine import socialfeed as SF                          # noqa: E402

ROOM = "nfl_401873017"
PLAYS = [{"players": ["Jordan Love", "Christian Watson"], "rating": 8.0, "team": "GB"},
         {"players": ["Montez Sweat"], "rating": 9.5, "team": "CHI"},
         {"players": ["Jordan Love"], "rating": 3.0, "team": "GB"},
         {"players": ["DJ Moore", "Caleb Williams"], "rating": 2.0, "team": "CHI"},
         {"players": ["Nobody"], "rating": 0}, "not a play"]


def _data(state="final", plays=PLAYS):
    d = Path(tempfile.mkdtemp())
    (d / "pbp").mkdir()
    (d / "pbp" / f"{ROOM}.json").write_text(json.dumps({"league": "nfl", "event_id": "401873017", "plays": plays}))
    (d / "live_nfl.json").write_text(json.dumps({"games": [
        {"event_id": "401873017", "home": "GB", "away": "CHI", "live": {"state": state}}]}))
    return d


def _db(n=3):
    K._cache.clear()
    K._graded.clear()
    K._ready.clear()
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    SF.ensure_tables(conn)
    GC.ensure_tables(conn)
    K.ensure_tables(conn)
    ids = []
    for who in ("ethan", "sam", "casey")[:n]:
        _, out = A.create_user(conn, f"{who}@example.com", "correct-horse-battery", confirmed=True)
        ids.append(out["id"])
        SF.profile_set(conn, out["id"], who, "")
    return conn, ids


def test_the_four_names_come_from_the_games_biggest_plays():
    got = GC.potg_options(ROOM, _data())
    assert got == [{"name": "Jordan Love", "team": "GB"}, {"name": "Montez Sweat", "team": "CHI"},
                   {"name": "Christian Watson", "team": ""}, {"name": "DJ Moore", "team": "CHI"}], got
    assert GC.potg_options(ROOM, _data(plays=[{"players": ["One Man"], "rating": 9}])) == [], "a vote needs two"
    assert GC.potg_options("nfl_1", _data()) == [], "no file, no vote"
    assert GC.potg_options("../etc", _data()) == []


def test_with_a_box_the_names_are_its_best_lines_each_with_its_line():
    d = _data()
    doc = json.loads((d / "pbp" / f"{ROOM}.json").read_text())
    doc["players"] = [
        {"player": "Jordan Love", "team": "GB", "stats": {"pass_yds": 312, "pass_td": 2}},
        {"player": "Josh Jacobs", "team": "GB", "stats": {"rush_yds": 96, "rush_td": 1}},
        {"player": "DJ Moore", "team": "CHI", "stats": {"rec_yds": 121}},
        {"player": "Caleb Williams", "team": "CHI", "stats": {"pass_yds": 240, "pass_td": 1}},
        {"player": "Backup Guy", "team": "CHI", "stats": {}}, "not a row"]
    (d / "pbp" / f"{ROOM}.json").write_text(json.dumps(doc))
    got = GC.potg_options(ROOM, d)
    assert got == [{"name": "Jordan Love", "team": "GB", "line": "312 pass yds, 2 TD"},
                   {"name": "DJ Moore", "team": "CHI", "line": "121 rec yds"},
                   {"name": "Josh Jacobs", "team": "GB", "line": "96 rush yds, 1 TD"},
                   {"name": "Caleb Williams", "team": "CHI", "line": "240 pass yds, 1 TD"}], got
    # Baseball keeps its plays elsewhere; the box is the same box.
    m = Path(tempfile.mkdtemp()) / "pbp"
    m.mkdir()
    (m / "mlb_7.json").write_text(json.dumps({"league": "mlb", "events": [], "players": [
        {"player": "Aaron Judge", "team": "NYY", "line": {"batting": {"h": 3, "ab": 4, "hr": 2, "rbi": 4}}},
        {"player": "Gerrit Cole", "team": "NYY", "line": {"pitching": {"ip": "7.0", "k": 9}}}]}))
    got = GC.potg_options("mlb_7", m.parent)
    # Scored as the final-score alert does: nine strikeouts (13.5) over two homers (13).
    assert [(o["name"], o["line"]) for o in got] == [("Gerrit Cole", "7.0 IP, 9 K"),
                                                     ("Aaron Judge", "3-for-4, 2 HR, 4 RBI")], got


def test_the_vote_opens_at_the_final_and_keeps_its_names():
    conn, (me, sam, casey) = _db()
    t = time.time()
    live = _data("live")
    assert GC.potg_view(conn, ROOM, me, live, t) is None
    assert GC.potg_vote(conn, me, ROOM, 0, live, t)[0] == 409, "not before the final"
    d = _data("final")
    v = GC.potg_view(conn, ROOM, me, d, t)
    assert v["open"] and v["mine"] is None and "counts" not in v and len(v["options"]) == 4, v
    code, out = GC.potg_vote(conn, me, ROOM, 1, d, t + 5)
    assert code == 200 and out["mine"] == 1 and out["counts"] == [0, 1, 0, 0] and out["n"] == 1, out
    assert GC.potg_vote(conn, me, ROOM, 0, d, t + 6)[0] == 409, "one vote"
    assert GC.potg_vote(conn, sam, ROOM, 9, d, t + 7)[0] == 400
    assert GC.potg_vote(conn, sam, ROOM, "x", d, t + 7)[0] == 400
    # The file is rewritten after: the names stay the ones it opened with.
    later = _data("final", plays=[{"players": ["Somebody Else", "Another"], "rating": 9}])
    assert [o["name"] for o in GC.potg_view(conn, ROOM, sam, later, t + 8)["options"]][0] == "Jordan Love"
    code, v = GC.room_view(conn, ROOM, sam, data_dir=d, now=t + 9)
    assert code == 200 and v["potg"]["options"][0]["name"] == "Jordan Love" and "counts" not in v["potg"], v["potg"]
    # A day on, it closes: everybody sees the room's pick, nobody votes.
    closed = GC.potg_view(conn, ROOM, casey, d, t + GC.POTG_OPEN_S + 60)
    assert closed["open"] is False and closed["counts"] == [0, 1, 0, 0], closed
    assert GC.potg_vote(conn, casey, ROOM, 0, d, t + GC.POTG_OPEN_S + 60)[0] == 409


def test_a_vote_pays_once_and_goes_with_the_account():
    conn, (me, _sam, _casey) = _db()
    d = _data("final")
    GC.potg_vote(conn, me, ROOM, 0, d)
    got = K.on_potg(conn, me, ROOM)
    assert got and got["got"] == 5 and got["why"] == "Voted the player of the game", got
    assert K.on_potg(conn, me, ROOM) is None, "once a game"
    assert K.RULES["potg"][0] == 5
    acc = Path(ROOT, "engine", "accounts.py").read_text(encoding="utf-8")
    assert '"chat_potg",' in acc
    GC._prune(conn, time.time() + GC.KEEP_DAYS * 86400 + 60)
    assert conn.execute("SELECT COUNT(*) FROM chat_potg").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM chat_potg_opts").fetchone()[0] == 0


def test_the_chat_the_server_and_the_policy():
    js = Path(ROOT, "web", "js", "chat.js").read_text(encoding="utf-8")
    for want in ("function chatPotgHTML(p)", 'data-gch="potg"', "CH.potg = v.potg || CH.potg || null;",
                 "if (!v.open && CH.potg && (CH.potg.options || []).length) { box.innerHTML = chatPotgHTML(CH.potg); return; }",
                 'chatPost("potg", { pick: Number(t.dataset.i) })'):
        assert want in js, want
    srv = Path(ROOT, "server.py").read_text(encoding="utf-8")
    assert '"vote", "potg", "remind", "report",' in srv and "GC.potg_vote(conn, uid, room, body.get(\"pick\"))" in srv
    assert '"potg": lambda K: K.on_potg(conn, uid, room),' in srv
    kjs = Path(ROOT, "web", "js", "karma.js").read_text(encoding="utf-8")
    assert '"vote_won", "potg", "call_won"' in kjs
    policy = " ".join(Path(ROOT, "web", "privacy.html").read_text(encoding="utf-8").split())
    assert "your vote for the player of the game once it is final" in policy
    assert "<code>chat_potg</code>" in policy and "<code>chat_potg_opts</code>" in policy


def test_in_a_browser_a_final_games_chat_asks_and_shows_the_room():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import shutil
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import rendercheck
    from test_the_chat_doors_open_without_errors import _game
    names = [{"name": "Jordan Love", "team": "GB"}, {"name": "Montez Sweat", "team": "CHI"},
             {"name": "Christian Watson", "team": ""}, {"name": "DJ Moore", "team": "CHI"}]
    potg = {"options": names, "mine": None, "open": True}
    voted = dict(potg, mine=1, counts=[12, 30, 4, 2], n=48,
                 karma={"got": 5, "why": "Voted the player of the game", "total": 105, "level": 2, "up": False})
    msgs = [{"id": 100, "at": time.time() - 60, "body": "what a finish", "own": False, "reacts": {}, "mine": "",
             "by": {"handle": "sam", "color": 1}}]
    room = {"room": "nfl_990299", "t": time.time(), "messages": msgs, "older": False, "reacts": {}, "plays": {},
            "threads": {}, "mine_plays": {}, "votes": {"home": 3, "away": 2, "mine": "", "open": False},
            "vote_path": [], "here": 9, "me": {"signed_in": True, "handle": "ethan"}, "potg": potg}
    who = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "ethan", "color": 1}}
    pbp = os.path.join(ROOT, "web", "data", "pbp")
    made = not os.path.isdir(pbp)
    os.makedirs(pbp, exist_ok=True)
    path = os.path.join(pbp, "nfl_990299.json")
    with open(path, "w") as fh:
        fh.write(json.dumps(_game("990299", 1)))
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    posted = []

    def vote(route):
        posted.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(voted))

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
                page.route("**/api/**", ful("{}"))
                page.route("**/api/account/**", ful(json.dumps({"sections": {}})))
                page.route("**/api/account/me*", ful(json.dumps(who)))
                page.route("**/api/feed/**", ful(json.dumps({"posts": []})))
                page.route("**/api/chat/room*", ful(json.dumps(room)))
                page.route("**/api/chat/counts*", ful(json.dumps({"rooms": {}})))
                page.route("**/api/chat/potg*", vote)
                page.route("**/api/alerts/**", ful(json.dumps({"players": []})))
                page.route("**/api/callit/**", ful(json.dumps({"open": None, "kind": "football", "board": []})))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');"
                                     "localStorage.setItem('qb_chat_rules_v1','1');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html#pbp/nfl/990299", wait_until="load")
                page.wait_for_timeout(6000)
                page.evaluate("(() => { const c = document.querySelector('.gch-entry'); c.scrollIntoView({block: 'center'}); c.click(); })()")
                page.wait_for_timeout(900)
                got["ask"] = page.evaluate("(document.querySelector('#gch-sheet .gch-poll') || {}).textContent || ''")
                got["names"] = page.evaluate("[...document.querySelectorAll('#gch-sheet [data-gch=potg] b')].map((b) => b.textContent)")
                page.click('#gch-sheet [data-gch="potg"][data-i="1"]')
                page.wait_for_timeout(700)
                got["after"] = page.evaluate("(document.querySelector('#gch-sheet .gch-poll') || {}).textContent || ''")
                got["mine"] = page.evaluate("(document.querySelector('#gch-sheet .gch-vote.mine b') || {}).textContent || ''")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
        if os.path.exists(path):
            os.remove(path)
        if made:
            # Only if empty (2026-10-29): the browser gate runs three at a time and
            # five tests share this folder, so the one that made it could delete it
            # under another's file (a clean checkout has no web/data at all).
            try:
                os.rmdir(pbp)
            except OSError:
                pass
    assert not errs, errs
    assert "Player of the game?" in got["ask"] and "+5 karma" in got["ask"], got
    assert got["names"] == [n["name"] for n in names], got
    assert posted and posted[0]["pick"] == 1 and posted[0]["room"] == "nfl_990299", posted
    assert "Fans' player of the game" in got["after"] and "63%" in got["after"] and "48 votes" in got["after"], got
    assert got["mine"] == "Montez Sweat", got


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
