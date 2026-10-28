"""The game chat talks back (engine/gamechat, engine/socialfeed,
engine/pushalerts, engine/pushmine; Ethan, 2026-10-28: "keep building …
keep inventing … we want to keep user retainment").

  * A REPLY lands in Activity like an @mention does (Discord's, Slack's,
    every messaging app's): "replied to you in a game chat", the words and a
    tap into the game. Never for your own message, once when a reply also
    names you, never past a block; a hidden or deleted reply takes it back.
  * A PUSH for a mention or a reply, unless the account turned off "Push me
    mentions and replies" on Activity (Ethan, 2026-10-28: "@ any profile in
    a chat should notify them they were mentioned" — on until said no): the
    account's choice, so every phone signed in to it carries the topic
    whatever the Alerts page sends, a phone that subscribed before learns it
    at the first mention, and a phone signed out never does. One a game
    every five minutes; none while the page is on that game; quiet hours
    hold them.
  * @ SUGGESTIONS in the composer: an @ and the start of a name offers the
    room's names and friends; a tap puts the name in.

Run directly: `python3 tests/test_the_chat_talks_back.py`
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
from engine import pushalerts as PA                          # noqa: E402
from engine import pushmine as PM                            # noqa: E402
from engine import social as SOC                             # noqa: E402
from engine import socialfeed as SF                          # noqa: E402

GOOD = "correct-horse-battery"
ROOM = "nfl_401873017"
FCM = "https://fcm.googleapis.com/fcm/send/"
#: The start of a five-minute stretch, ten seconds in: two messages a minute
#: apart fall in the same stretch.
T0 = (int(time.time()) // GC.PING_EVERY_S) * GC.PING_EVERY_S + 10


def _db(n=4):
    K._cache.clear()
    K._graded.clear()
    K._ready.clear()
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    SF.ensure_tables(conn)
    GC.ensure_tables(conn)
    SOC.ensure_tables(conn)
    K.ensure_tables(conn)
    PM.ensure_tables(conn)
    ids = []
    for who in ("ethan", "sam", "casey", "drew")[:n]:
        _, out = A.create_user(conn, f"{who}@example.com", GOOD, confirmed=True)
        ids.append(out["id"])
        SF.profile_set(conn, out["id"], who, "")
    return conn, ids


def _notes(conn, uid):
    return [n for n in SF.notifications(conn, uid)["items"] if n["kind"] in ("chat_mention", "chat_reply")]


def _phone(conn, uid, topics=("bets",)):
    code, out = PA.subscribe(conn, FCM + str(uid), kind="web", user_id=uid, topics=list(topics))
    assert code == 200, out
    return out["topics"]


def _pushes(conn, uid):
    return [dict(zip(("id", "kind", "title", "body", "url"), r)) for r in conn.execute(
        "SELECT id, kind, title, body, url FROM push_mine WHERE user_id=? ORDER BY at", (uid,))]


def _live():
    d = Path(tempfile.mkdtemp())
    (d / "live_nfl.json").write_text(json.dumps({"games": [
        {"event_id": "401873017", "home": "GB", "away": "CAR", "live": {"state": "live"}}]}))
    return d


def test_a_reply_lands_in_activity_once_and_never_for_your_own():
    conn, ids = _db()
    me, sam, casey = ids[:3]
    _, first = GC.send(conn, sam, ROOM, "that was holding", now=T0)
    code, out = GC.send(conn, me, ROOM, "no way, clean hands", reply_to=first["id"], now=T0 + 5)
    assert code == 200, out
    got = _notes(conn, sam)
    assert [(n["kind"], n["handle"], n["link"]) for n in got] == [("chat_reply", "ethan", "#pbp/nfl/401873017")], got
    assert got[0]["snippet"] == "no way, clean hands"
    # Answering yourself tells nobody; a reply that also names you is one notice.
    GC.send(conn, sam, ROOM, "and another thing", reply_to=first["id"], now=T0 + 65)
    assert len(_notes(conn, sam)) == 1
    _, mine = GC.send(conn, casey, ROOM, "who called it", now=T0 + 70)
    GC.send(conn, me, ROOM, "@casey I did", reply_to=mine["id"], now=T0 + 130)
    assert [n["kind"] for n in _notes(conn, casey)] == ["chat_reply"]
    # A block either way stops it.
    SF.toggle_block(conn, casey, "ethan")
    GC.send(conn, me, ROOM, "still me", reply_to=mine["id"], now=T0 + 190)
    assert len(_notes(conn, casey)) == 1
    # Hidden for everyone: the reply's notice goes with it.
    rid = conn.execute("SELECT id FROM chat_msgs WHERE body='no way, clean hands'").fetchone()[0]
    GC.set_hidden(conn, rid, True)
    assert _notes(conn, sam) == []


def test_the_switch_is_the_accounts_and_its_phones_carry_it():
    conn, ids = _db()
    sam = ids[1]
    # On until said no: a phone signed in to the account carries the topic.
    assert SF.mention_alerts(conn, sam) and _phone(conn, sam) == ["bets", "mentions"]
    assert SF.notifications(conn, sam)["alerts"] == {"on": True, "phones": 1}
    code, out = SF.set_mention_alerts(conn, sam, False)
    assert code == 200 and out == {"ok": True, "on": False, "phones": 1}, out
    assert conn.execute("SELECT topics FROM push_subs WHERE user_id=?", (sam,)).fetchone()[0] == "bets"
    # The Alerts page re-subscribes knowing nothing of it: the no stays.
    assert _phone(conn, sam, ("bets", "clutch")) == ["bets", "clutch"]
    assert SF.export_user(conn, sam)["mention_alerts"] is False
    code, out = SF.set_mention_alerts(conn, sam, True)
    assert code == 200 and out == {"ok": True, "on": True, "phones": 1}, out
    assert _phone(conn, sam, ("bets", "clutch")) == ["bets", "clutch", "mentions"]
    # Signed out, a phone never carries an account's alerts.
    code, out = PA.subscribe(conn, FCM + "x", kind="web", user_id=None, topics=["posted", "mentions"])
    assert code == 200 and "mentions" not in out["topics"], out
    _, nobody = A.create_user(conn, "nohandle@example.com", GOOD, confirmed=True)
    assert not SF.mention_alerts(conn, nobody["id"]), "no username, nothing to be named by"
    assert SF.set_mention_alerts(conn, nobody["id"], True)[0] == 409, "a mention names a username"
    assert "mentions" in PA.PERSONAL and PM.TOPICS == PA.PERSONAL


def test_a_phone_that_subscribed_before_learns_the_topic_at_the_first_mention():
    """Phones that took alerts while mentions were off by default carry no
    "mentions": the first mention puts it on every phone of the account
    that has not said no, and the push goes."""
    conn, ids = _db(3)
    me, sam, casey = ids
    for uid in (sam, casey):
        _phone(conn, uid)
        conn.execute("UPDATE push_subs SET topics='bets' WHERE user_id=?", (uid,))   # the old row
    conn.execute("UPDATE feed_profiles SET push_mentions=? WHERE user_id=?", (SF.MENTION_OFF, casey))
    conn.commit()
    GC.send(conn, me, ROOM, "@sam @casey look", now=T0)
    assert [p["kind"] for p in _pushes(conn, sam)] == ["mentions"]
    assert conn.execute("SELECT topics FROM push_subs WHERE user_id=?", (sam,)).fetchone()[0] == "bets,mentions"
    assert _pushes(conn, casey) == [] and len(_notes(conn, casey)) == 1, "said no: Activity only"
    assert conn.execute("SELECT topics FROM push_subs WHERE user_id=?", (casey,)).fetchone()[0] == "bets"


def test_a_mention_or_a_reply_buzzes_once_a_game_every_five_minutes():
    conn, ids = _db()
    me, sam, casey, drew = ids
    for uid in (sam, casey):
        _phone(conn, uid)
    keep = K.DATA
    try:
        K.DATA = _live()
        GC.send(conn, me, ROOM, "@sam did you see that", now=T0)
        got = _pushes(conn, sam)
        assert got == [{"id": f"chat:{ROOM}:{T0 // GC.PING_EVERY_S}", "kind": "mentions",
                        "title": "@ethan mentioned you in CAR @ GB", "body": "@sam did you see that",
                        "url": "/#pbp/nfl/401873017"}], got
        GC.send(conn, me, ROOM, "@sam hello??", now=T0 + 60)
        assert len(_pushes(conn, sam)) == 1, "the rest of the five minutes wait in Activity"
        assert len(_notes(conn, sam)) == 2
        # Their page on the game: they see it land, no push.
        conn.execute("INSERT INTO karma_watch (user_id, room, league, first_at, last_at) VALUES (?,?,?,?,?)",
                     (casey, ROOM, "nfl", T0, T0 + 100))
        conn.commit()
        GC.send(conn, me, ROOM, "@casey you here", now=T0 + 120)
        assert _pushes(conn, casey) == [] and len(_notes(conn, casey)) == 1
        # No phone takes alerts: Activity only.
        GC.send(conn, me, ROOM, "@drew hi", now=T0 + 180)
        assert _pushes(conn, drew) == [] and len(_notes(conn, drew)) == 1
        # A reply, a later stretch.
        _, theirs = GC.send(conn, sam, ROOM, "what a game", now=T0 + 400)
        GC.send(conn, me, ROOM, "best of the year", reply_to=theirs["id"], now=T0 + 460)
        assert _pushes(conn, sam)[-1]["title"] == "@ethan replied to you in CAR @ GB"
    finally:
        K.DATA = keep
    # A watch party's: its own words, to the party — and to anyone named,
    # member or not, the party's link asking them in.
    code, party = GC.party_create(conn, me, ROOM, "Sunday crew")
    assert code == 200 and GC.party_join(conn, sam, party["token"])[0] == 200
    GC.send(conn, me, ROOM, "@sam @casey party's on", now=T0 + 900, party=party["id"])
    last = _pushes(conn, sam)[-1]
    assert last["title"] == "@ethan mentioned you in your watch party", last
    assert last["url"] == f"/#pbp/nfl/401873017/party/{party['token']}", last
    asked = _pushes(conn, casey)[-1]
    assert asked["title"] == "@ethan mentioned you in a watch party", asked
    assert asked["url"] == f"/#pbp/nfl/401873017/party/{party['token']}", asked


def test_quiet_hours_hold_them():
    conn, ids = _db(2)
    sam = ids[1]
    _phone(conn, sam)
    GC.send(conn, ids[0], ROOM, "@sam late one", now=T0)
    sent = []
    stats = PM.flush(conn, knock=lambda *a, **k: sent.append(a) or 201, vapid={"x": 1}, now=T0 + 60, quiet=True)
    assert stats["messages"] == 0 and not sent, stats
    stats = PM.flush(conn, knock=lambda *a, **k: sent.append(a) or 201, vapid={"x": 1}, now=T0 + 120, quiet=False)
    assert stats["messages"] == 1 and sent, stats
    assert PM.TTL_S["mentions"] == 2 * 3600


def test_the_pages_carry_the_switch_the_words_and_the_suggestions():
    js = Path(ROOT, "web", "js", "social.js").read_text(encoding="utf-8")
    for want in ('chat_reply: "replied to you in a game chat"', "function mentionAlertsHTML(a)",
                 'data-fd="mention-alerts"', 'api("mention-alerts", { on })', "${mentionAlertsHTML(alerts)}"):
        assert want in js, want
    chat = Path(ROOT, "web", "js", "chat.js").read_text(encoding="utf-8")
    for want in ("function chatAtWord(box)", "function chatAtNames(q)", 'data-gch="at"',
                 'if (act === "at") return chatAtPut(t.dataset.handle);'):
        assert want in chat, want
    srv = Path(ROOT, "server.py").read_text(encoding="utf-8")
    assert '"friend", "mention-alerts",' in srv and "SF.set_mention_alerts(conn, uid, body.get(\"on\") is True)" in srv
    policy = " ".join(Path(ROOT, "web", "privacy.html").read_text(encoding="utf-8").split())
    for want in ('unless you turned off "Push me mentions, replies and friend requests" on Activity',
                 "with an @ or answers yours",
                 "in a game chat, a watch party, a post or a comment"):
        assert want in policy, want


def test_in_a_browser_an_at_offers_names_and_activity_has_the_switch():
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
    msgs = [{"id": 100 + i, "at": time.time() - 60 * (5 - i), "body": f"message {i}", "own": False, "reacts": {},
             "mine": "", "by": {"handle": h, "color": i}} for i, h in enumerate(("sam", "casey", "samantha_k", "ethan"))]
    room = {"room": "nfl_990188", "t": time.time(), "messages": msgs, "older": False, "reacts": {}, "plays": {},
            "threads": {}, "mine_plays": {}, "votes": {"home": 3, "away": 2, "mine": "", "open": True},
            "vote_path": [], "here": 9, "me": {"signed_in": True, "handle": "ethan"}}
    who = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "ethan", "color": 1}}
    notes = {"unseen": 0, "items": [{"id": 1, "kind": "chat_reply", "at": time.time() - 60, "seen": True,
                                     "handle": "sam", "name": "", "color": 2, "post_id": None, "comment_id": -5,
                                     "result": "", "snippet": "no way", "link": "#pbp/nfl/990188"}],
             "alerts": {"on": False, "phones": 1}}
    pbp = os.path.join(ROOT, "web", "data", "pbp")
    made = not os.path.isdir(pbp)
    os.makedirs(pbp, exist_ok=True)
    path = os.path.join(pbp, "nfl_990188.json")
    with open(path, "w") as fh:
        fh.write(json.dumps(_game("990188", 1)))
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    posted = []

    def alerts(route):
        posted.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "on": True, "phones": 1}))

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
                page.route("**/api/feed/me*", ful(json.dumps({"me": who["profile"], "signed_in": True})))
                page.route("**/api/feed/notifications*", ful(json.dumps(notes)))
                page.route("**/api/feed/mention-alerts*", alerts)
                page.route("**/api/chat/room*", ful(json.dumps(room)))
                page.route("**/api/chat/counts*", ful(json.dumps({"rooms": {}})))
                page.route("**/api/alerts/**", ful(json.dumps({"players": []})))
                page.route("**/api/callit/**", ful(json.dumps({"open": None, "kind": "football", "board": []})))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');"
                                     "localStorage.setItem('qb_chat_rules_v1','1');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html#pbp/nfl/990188", wait_until="load")
                page.wait_for_timeout(6000)
                page.evaluate("(() => { const c = document.querySelector('.gch-entry'); c.scrollIntoView({block: 'center'}); c.click(); })()")
                page.wait_for_timeout(900)
                page.fill("#gch-sheet .gch-input", "nice @sa")
                page.wait_for_timeout(200)
                got["offered"] = page.evaluate("[...document.querySelectorAll('#gch-sheet .gch-atrow button')].map((b) => b.textContent)")
                page.click('#gch-sheet .gch-atrow button[data-handle="sam"]')
                got["typed"] = page.evaluate("document.querySelector('#gch-sheet .gch-input').value")
                got["gone"] = page.evaluate("!document.querySelector('#gch-sheet .gch-atrow')")
                page.fill("#gch-sheet .gch-input", "an email@sam is not one")
                got["mid"] = page.evaluate("!document.querySelector('#gch-sheet .gch-atrow')")
                page.goto(f"http://127.0.0.1:{port}/index.html#feed/activity", wait_until="load")
                page.wait_for_timeout(3500)
                got["note"] = page.evaluate("(document.querySelector('.fd-note') || {}).textContent || ''")
                got["href"] = page.evaluate("(document.querySelector('.fd-note') || {}).getAttribute && document.querySelector('.fd-note').getAttribute('href')")
                page.click('[data-fd="mention-alerts"]')
                page.wait_for_timeout(600)
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
        if os.path.exists(path):
            os.remove(path)
        if made:
            shutil.rmtree(pbp, ignore_errors=True)
    assert not errs, errs
    assert got["offered"] == ["@samantha_k", "@sam"], "the room's latest writer first, never your own name"
    assert got["typed"] == "nice @sam " and got["gone"], got
    assert got["mid"], "an @ inside a word is not a mention"
    assert "replied to you in a game chat" in got["note"] and got["href"] == "#pbp/nfl/990188", got
    assert posted == [{"on": True}], posted


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
