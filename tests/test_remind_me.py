"""Remind me (engine/gamechat remind; Ethan, 2026-10-28: "keep building …
keep inventing … keep user retainment").

theScore's "notify me": a bell on a game that has not started, and the
phone hears ten minutes before it does. What this file pins:

  * the bell shows only on a game the scoreboard says has not started and
    gives a start for; once it is live or final, or the start has passed,
    it is gone;
  * setting it is the account's, so every phone signed in to it carries the
    "reminders" topic while one is set (and drops it when none is), and a
    phone signed out never does;
  * the push goes once, about ten minutes before the start ("CHI @ GB
    starts in 10 minutes"), to the game; a game well under way is let go
    untold; either way the reminder is spent; quiet hours do not hold it
    (the account asked for that game);
  * the server's route, the chat's bell, account deletion and the policy.

Run directly: `python3 tests/test_remind_me.py`
"""
import datetime as _dt
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
from engine import pushalerts as PA                          # noqa: E402
from engine import pushmine as PM                            # noqa: E402
from engine import socialfeed as SF                          # noqa: E402

ROOM = "nfl_401873017"
FCM = "https://fcm.googleapis.com/fcm/send/"


def _iso(t):
    return _dt.datetime.fromtimestamp(t, tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _data(start, state="scheduled"):
    d = Path(tempfile.mkdtemp())
    (d / "live_nfl.json").write_text(json.dumps({"games": [
        {"event_id": "401873017", "home": "GB", "away": "CHI", "live": {"state": state, "start_time": _iso(start)}}]}))
    return d


def _data2(start):
    """Another game, for a reminder the pass first sees well after its start."""
    d = Path(tempfile.mkdtemp())
    (d / "live_nfl.json").write_text(json.dumps({"games": [
        {"event_id": "401873018", "home": "DET", "away": "MIN", "live": {"state": "scheduled", "start_time": _iso(start)}}]}))
    return d


def _db(n=2):
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    SF.ensure_tables(conn)
    GC.ensure_tables(conn)
    PM.ensure_tables(conn)
    ids = []
    for who in ("ethan", "sam")[:n]:
        _, out = A.create_user(conn, f"{who}@example.com", "correct-horse-battery", confirmed=True)
        ids.append(out["id"])
        SF.profile_set(conn, out["id"], who, "")
    return conn, ids


def _phone(conn, uid, topics=("bets",)):
    code, out = PA.subscribe(conn, FCM + str(uid), kind="web", user_id=uid, topics=list(topics))
    assert code == 200, out
    return out["topics"]


def _topics(conn, uid):
    return conn.execute("SELECT topics FROM push_subs WHERE user_id=?", (uid,)).fetchone()[0].split(",")


def test_the_bell_is_only_on_a_game_that_has_not_started():
    conn, (me, _sam) = _db()
    t = time.time()
    assert GC.remind_view(conn, ROOM, me, _data(t + 3600), t) == {"on": False, "start": float(int(t + 3600))}
    assert GC.remind_view(conn, ROOM, me, _data(t + 3600, "live"), t) is None
    assert GC.remind_view(conn, ROOM, me, _data(t - 60), t) is None, "the start has passed"
    assert GC.remind_view(conn, "nfl_1", me, _data(t + 3600), t) is None, "not on the scoreboard"
    assert GC.remind(conn, me, ROOM, True, _data(t + 3600, "final"), t)[0] == 409
    assert GC._when("not a time") is None and GC._when("") is None


def test_setting_it_puts_the_topic_on_the_accounts_phones():
    conn, (me, _sam) = _db()
    t = time.time()
    d = _data(t + 3600)
    assert "reminders" not in _phone(conn, me)
    code, out = GC.remind(conn, me, ROOM, True, d, t)
    assert code == 200 and out == {"ok": True, "on": True, "phones": 1}, out
    # (with the mentions every account carries unless it said no, engine/socialfeed)
    assert _topics(conn, me) == ["bets", "mentions", "reminders"]
    assert GC.remind_view(conn, ROOM, me, d, t)["on"] is True
    # The Alerts page re-subscribes knowing nothing of it: it stays.
    assert _phone(conn, me, ("bets", "clutch")) == ["bets", "clutch", "mentions", "reminders"]
    # Signed out, never.
    code, out = PA.subscribe(conn, FCM + "x", kind="web", user_id=None, topics=["posted", "reminders"])
    assert "reminders" not in out["topics"], out
    GC.remind(conn, me, ROOM, False, d, t)
    assert _topics(conn, me) == ["bets", "clutch", "mentions"], "no reminder left, no topic"
    assert "reminders" in PA.PERSONAL and PM.TOPICS == PA.PERSONAL


def test_the_push_goes_once_ten_minutes_before_and_the_reminder_is_spent():
    conn, (me, sam) = _db()
    t = time.time()
    _phone(conn, me)
    _phone(conn, sam)
    d = _data(t + 3600)
    GC.remind(conn, me, ROOM, True, d, t)
    GC.remind(conn, sam, ROOM, True, d, t)
    assert GC.reminders_pass(conn, now=t + 60) == 0, "too early"
    told = GC.reminders_pass(conn, now=t + 3600 - 600)
    assert told == 2, told
    row = conn.execute("SELECT id, kind, title, url FROM push_mine WHERE user_id=?", (me,)).fetchone()
    assert tuple(row) == (f"remind:{ROOM}", "reminders", "CHI @ GB starts in 10 minutes", "/#pbp/nfl/401873017"), row
    assert conn.execute("SELECT COUNT(*) FROM chat_reminders").fetchone()[0] == 0, "spent"
    assert GC.reminders_pass(conn, now=t + 3600 - 540) == 0, "once"
    # A game well under way when the pass first sees it: let go untold.
    GC.remind(conn, me, "nfl_401873018", True, _data2(t + 7200), t)
    assert GC.reminders_pass(conn, now=t + 7200 + GC.REMIND_LATE_S + 60) == 0
    assert conn.execute("SELECT COUNT(*) FROM chat_reminders").fetchone()[0] == 0


def test_quiet_hours_do_not_hold_a_reminder():
    conn, (me, _sam) = _db()
    t = time.time()
    _phone(conn, me)
    GC.remind(conn, me, ROOM, True, _data(t + 600), t)
    GC.reminders_pass(conn, now=t + 30)
    sent = []
    stats = PM.flush(conn, knock=lambda *a, **k: sent.append(a) or 201, vapid={"x": 1}, now=t + 40, quiet=True)
    assert stats["messages"] == 1 and sent, stats
    src = Path(ROOT, "engine", "pushmine.py").read_text(encoding="utf-8")
    run = src[src.index("def run_once("):src.index("def main(")]
    assert "told += _gc.reminders_pass(conn, now=t)" in run
    assert "'reminders'" not in src[src.index("held = "):src.index("held = ") + 120]


def test_the_route_the_bell_deletion_and_the_policy():
    srv = Path(ROOT, "server.py").read_text(encoding="utf-8")
    assert '"vote", "potg", "remind", "report",' in srv
    assert 'GC.remind(conn, uid, room, body.get("on") is True)' in srv
    js = Path(ROOT, "web", "js", "chat.js").read_text(encoding="utf-8")
    for want in ("function chatBellPaint(slot)", "async function chatBellToggle()", "CH.remind = v.remind || null;",
                 'chatPost("remind", { on: !r.on })', "chatBellPaint(slot);"):
        assert want in js, want
    acc = Path(ROOT, "engine", "accounts.py").read_text(encoding="utf-8")
    assert '"chat_reminders",' in acc
    policy = " ".join(Path(ROOT, "web", "privacy.html").read_text(encoding="utf-8").split())
    assert 'for a game you set "Remind me" on, that it starts in ten minutes' in policy
    assert "<code>chat_reminders</code>" in policy


def test_in_a_browser_the_bell_sits_under_the_chat_card_and_sets():
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
    start = time.time() + 3 * 3600
    room = {"room": "nfl_990399", "t": time.time(), "messages": [], "older": False, "reacts": {}, "plays": {},
            "threads": {}, "mine_plays": {}, "votes": {"home": 0, "away": 0, "mine": "", "open": True},
            "vote_path": [], "here": 3, "me": {"signed_in": True, "handle": "ethan"},
            "remind": {"on": False, "start": start}}
    who = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "ethan", "color": 1}}
    game = _game("990399", 0)
    game["live"] = {"state": "scheduled", "start_time": _iso(start)}
    pbp = os.path.join(ROOT, "web", "data", "pbp")
    made = not os.path.isdir(pbp)
    os.makedirs(pbp, exist_ok=True)
    path = os.path.join(pbp, "nfl_990399.json")
    with open(path, "w") as fh:
        fh.write(json.dumps(game))
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    posted = []

    def remind(route):
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
                page.route("**/api/chat/room*", ful(json.dumps(room)))
                page.route("**/api/chat/counts*", ful(json.dumps({"rooms": {}})))
                page.route("**/api/chat/remind*", remind)
                page.route("**/api/alerts/**", ful(json.dumps({"players": []})))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html#pbp/nfl/990399", wait_until="load")
                page.wait_for_timeout(6000)
                got["bell"] = page.evaluate("(document.querySelector('.gch-entry-slot .gch-bell') || {}).textContent || ''")
                page.click(".gch-entry-slot .gch-bell")
                page.wait_for_timeout(700)
                got["after"] = page.evaluate("(document.querySelector('.gch-entry-slot .gch-bell') || {}).textContent || ''")
                got["pressed"] = page.evaluate("document.querySelector('.gch-entry-slot .gch-bell').getAttribute('aria-pressed')")
                got["sheet"] = page.evaluate("!!document.getElementById('gch-sheet')")
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
    assert "Remind me 10 minutes before it starts" in got["bell"], got
    assert posted and posted[0] == {"room": "nfl_990399", "on": True}, posted
    assert "Reminder set" in got["after"] and got["pressed"] == "true", got
    assert not got["sheet"], "the bell sets the reminder; it does not open the chat"


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
