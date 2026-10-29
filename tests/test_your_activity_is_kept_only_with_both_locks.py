"""Each member's own time here, a row a day (engine/activity, web/js/activity.js,
Settings → Your activity; docs/RETENTION.md §6).

Ethan, 2026-10-29: "we can be recording what users do on the app, how long
they spend on it, and we can base notifications off that." What these hold:

  * nothing is kept until BOTH locks open: QB_ACTIVITY=1 and the Privacy
    Policy's own section on it (id="your-activity"); the draft wording is
    in docs/RETENTION.md for Ethan, and the live policy has no such section
    until he approves it;
  * a beat is checked word by word: seconds capped a beat and a day, pages
    and leagues by name only, the hour the box's own, a visit and an
    alert's tap counted once; an alert opened resets the phone's count of
    unopened ones;
  * a member's own switch: off deletes every row and keeps nothing more; the
    rows go after KEEP_DAYS, with the account, and are in its export;
  * the server answers 204 whatever happens and keeps nothing signed out;
    the page fetches the script only when told, and the script sends
    seconds, pages, leagues and two marks — never an address or a word typed;
  * Settings and the Alerts page offer it only while the site keeps it.

Run directly: `python3 tests/test_your_activity_is_kept_only_with_both_locks.py`
"""
import json
import os
import sqlite3
import sys
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp())
os.environ.pop("QB_ACTIVITY", None)

from engine import accounts as A                                  # noqa: E402
from engine import activity as ACT                                # noqa: E402

A.DB_PATH = _TMP / "accounts.db"
READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
NOW = 1_793_304_000.0                                             # 2026-10-29 16:00 Eastern


def _policy(with_section: bool) -> Path:
    p = Path(tempfile.mkdtemp()) / "privacy.html"
    p.write_text("<h3 id=\"your-activity\">Your activity</h3>" if with_section else "<h3>Nothing</h3>")
    return p


class _Locks:
    """Both locks open (or as asked) for the length of a with-block."""
    def __init__(self, switch=True, section=True):
        self.switch, self.section = switch, section

    def __enter__(self):
        self.old = (os.environ.get(ACT.ENV), ACT.POLICY)
        if self.switch:
            os.environ[ACT.ENV] = "1"
        else:
            os.environ.pop(ACT.ENV, None)
        ACT.POLICY = _policy(self.section)
        return self

    def __exit__(self, *exc):
        env, ACT.POLICY = self.old
        if env is None:
            os.environ.pop(ACT.ENV, None)
        else:
            os.environ[ACT.ENV] = env


def _conn():
    c = sqlite3.connect(":memory:")
    ACT.ensure_tables(c)
    return c


def test_nothing_until_both_locks_open():
    c = _conn()
    assert not ACT.enabled() and "QB_ACTIVITY" in ACT.why_off()
    assert ACT.beat(c, 1, {"s": 60, "n": 1}, NOW) is False
    with _Locks(switch=True, section=False):
        assert not ACT.enabled() and "Privacy Policy" in ACT.why_off(), "the switch alone does nothing"
        assert ACT.beat(c, 1, {"s": 60, "n": 1}, NOW) is False
    with _Locks(switch=False, section=True):
        assert not ACT.enabled()
    with _Locks():
        assert ACT.enabled() and ACT.why_off() == ""
    assert c.execute("SELECT COUNT(*) FROM activity_days").fetchone()[0] == 0
    # The live policy has no section yet: the wording waits for Ethan.
    assert 'id="your-activity"' not in READ("web", "privacy.html")
    assert 'id="your-activity"' in READ("docs", "RETENTION.md"), "the draft for him to approve"


def test_a_beat_is_checked_and_kept_as_a_day():
    c = _conn()
    with _Locks():
        assert ACT.beat(c, 7, {"s": 300, "v": {"live": 200, "pbp": 100}, "sp": {"nba": 300}, "n": 1, "a": 1}, NOW)
        assert ACT.beat(c, 7, {"s": 120, "v": {"live": 120}, "sp": {"nba": 120}}, NOW + 300)
        # Nonsense is dropped word by word; nothing at all is no row.
        assert ACT.beat(c, 7, {"s": "lots", "v": {"<b>": 9, "x" * 40: 9, "ok": -3}, "n": 0}, NOW) is False
        assert ACT.beat(c, 7, {"s": 99999, "v": {"record": 99999}}, NOW + 600)
        rows = ACT.rows(c, 7, now=NOW)
    assert len(rows) == 1, rows
    r = rows[0]
    assert r["day"] == "2026-10-29" and r["visits"] == 1 and r["taps"] == 1
    assert r["seconds"] == 300 + 120 + ACT.BEAT_MAX_S, "a beat carries fifteen minutes at most"
    assert r["views"] == {"live": 320, "pbp": 100, "record": ACT.BEAT_MAX_S} and r["sports"] == {"nba": 420}
    assert r["hours"][16] == r["seconds"] and sum(r["hours"]) == r["seconds"], "the box's own Eastern hour"
    cols = [x[1] for x in c.execute("PRAGMA table_info(activity_days)")]
    assert cols == ["user_id", "day", "seconds", "visits", "taps", "views", "sports", "hours"], \
        "no column for an address, a device, a location or anything typed"


def test_a_day_has_a_ceiling_and_the_pages_share_only_what_was_kept():
    c = _conn()
    with _Locks():
        c.execute("INSERT INTO activity_days (user_id, day, seconds) VALUES (3, '2026-10-29', ?)",
                  (ACT.DAY_MAX_S - 100,))
        assert ACT.beat(c, 3, {"s": 400, "v": {"live": 400}}, NOW)
        r = ACT.rows(c, 3, now=NOW)[0]
    assert r["seconds"] == ACT.DAY_MAX_S and r["views"] == {"live": 100}


def test_an_alert_opened_resets_the_phone_s_unopened_count():
    from engine import pushalerts as PA
    c = _conn()
    PA.ensure_tables(c)
    PA.subscribe(c, "ab" * 32, kind="apns", user_id=5)
    c.execute("UPDATE push_subs SET unopened = 20")
    with _Locks():
        ACT.beat(c, 5, {"s": 10, "n": 1}, NOW)
        assert c.execute("SELECT unopened FROM push_subs").fetchone()[0] == 20, "a visit of their own is not a tap"
        ACT.beat(c, 5, {"s": 10, "n": 1, "a": 1}, NOW)
    assert c.execute("SELECT unopened FROM push_subs").fetchone()[0] == 0


def test_the_member_s_own_switch_deletes_and_stops():
    c = _conn()
    with _Locks():
        ACT.beat(c, 9, {"s": 60, "n": 1}, NOW)
        assert ACT.on_for(c, 9)
        ACT.set_off(c, 9, True, NOW)
        assert not ACT.on_for(c, 9) and ACT.opted_out(c, 9)
        assert ACT.rows(c, 9, now=NOW) == [], "off deletes what was kept"
        assert ACT.beat(c, 9, {"s": 60, "n": 1}, NOW) is False, "and keeps nothing more"
        ACT.set_off(c, 9, False, NOW)
        assert ACT.beat(c, 9, {"s": 60, "n": 1}, NOW)


def test_summary_kept_days_and_the_account():
    c = _conn()
    with _Locks():
        for d in range(5):
            ACT.beat(c, 4, {"s": 600, "v": {"pbp": 600}, "sp": {"nfl": 500, "nba": 100}, "n": 1,
                            "a": int(d == 0)}, NOW - d * 86400)
        s = ACT.summary(c, 4, NOW)
        assert s["days_active"] == 5 and s["minutes_a_day"] == 10 and s["visits"] == 5 and s["from_alerts"] == 1
        assert s["sports"] == ["nfl", "nba"] and s["pages"] == ["pbp"] and s["hour_et"] == 16
        c.execute("INSERT INTO activity_days (user_id, day, seconds) VALUES (4, '2026-01-01', 60)")
        assert ACT.prune(c, NOW) == 1, f"kept {ACT.KEEP_DAYS} days, then deleted"
    # The account: in its export, gone with it.
    conn = A.connect()
    try:
        code, out = A.create_user(conn, "act@example.com", "correct horse battery", confirmed=True)
        uid = out["id"]
        with _Locks():
            ACT.beat(conn, uid, {"s": 60, "n": 1}, NOW)
        assert A.export_user(conn, uid)["activity_by_day"][0]["seconds"] == 60
        ACT.set_off(conn, uid, True)
        assert A.export_user(conn, uid)["activity"] == "turned off in Settings"
        A.delete_user(conn, uid)
        for table in ("activity_days", "activity_prefs"):
            assert not conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=?", (uid,)).fetchone()[0], table
    finally:
        conn.close()
    src = READ("engine", "accounts.py")
    assert '"activity_days", "activity_prefs", "engagement_away"' in src


def _serve():
    import server
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _req(base, path, body=None, cookie=""):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})})
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read()
        return r.status, (json.loads(raw) if raw else None)


def test_the_server_keeps_only_a_signed_in_member_s_beats():
    httpd, base = _serve()
    try:
        conn = A.connect()
        code, out = A.create_user(conn, "beats@example.com", "correct horse battery", confirmed=True)
        uid, token = out["id"], A.start_session(conn, out["id"])
        conn.close()
        cookie = f"qb_session={token}"
        st = _req(base, "/api/billing/status", cookie=cookie)[1]
        assert st["activity_switch"] is False and st["activity"] is False, "off: the page is told so"
        assert _req(base, "/api/activity", {"s": 60, "n": 1}, cookie)[0] == 204
        with _Locks():
            st = _req(base, "/api/billing/status", cookie=cookie)[1]
            assert st["activity_switch"] is True and st["activity"] is True
            assert _req(base, "/api/billing/status")[1]["activity"] is False, "signed out"
            assert _req(base, "/api/activity", {"s": 60, "n": 1})[0] == 204
            assert _req(base, "/api/activity", {"s": 60, "v": {"live": 60}, "n": 1}, cookie)[0] == 204
            got = _req(base, "/api/account/activity", cookie=cookie)[1]
            assert got["switch"] and not got["off"] and got["summary"]["days_active"] == 1
            off = _req(base, "/api/account/activity", {"off": True}, cookie)[1]
            assert off["off"] is True and "summary" not in off
            assert _req(base, "/api/billing/status", cookie=cookie)[1]["activity"] is False
        conn = A.connect()
        try:
            n = conn.execute("SELECT COUNT(*) FROM activity_days").fetchone()[0]
        finally:
            conn.close()
        assert n == 0, "one signed-out beat, one before the locks opened, one deleted by the switch"
    finally:
        httpd.shutdown()


def test_the_page_fetches_it_only_when_told_and_sends_only_this():
    app = READ("web", "js", "app.js")
    at = app.index("_pwStatus = await r.json();")
    assert 'if (_pwStatus.activity) loadRoom("js/activity.js");' in app[at:at + 300]
    js = READ("web", "js", "activity.js")
    assert 'JSON.stringify({ s: secs, v: views, sp: sports, n: fresh ? 1 : 0, a: fresh && tapped ? 1 : 0 })' in js
    for never in ("location", "referrer", "innerText", "textContent", "value", "cookie", "navigator.userAgent"):
        assert never not in js, f"the beat must not read {never}"
    assert 'document.visibilityState !== "visible"' in js and "IDLE_S" in js, "only time somebody is there"
    assert '"/api/activity"' in js and "sendBeacon" in js
    assert '"/js/activity.js"' in READ("web", "sw.js"), "the installed app keeps it with its pages"


def test_settings_and_alerts_offer_it_only_while_kept():
    acct = READ("web", "js", "account.js")
    at = acct.index('out.push(setGroup("Your data", [')
    assert "_pwStatus && _pwStatus.activity_switch" in acct[at:at + 400] and 'data-set-open="activity"' in acct[at:at + 600]
    page = acct[acct.index("function actHTML()"):acct.index("async function actFill(")]
    assert "Never sold, never shared, never an ad. Off deletes all of it." in page
    assert '"/api/account/activity"' in acct
    app = READ("web", "js", "app.js")
    at = app.index('box("lineup", "My fantasy lineup')
    assert '_pwStatus && _pwStatus.activity_switch' in app[at:at + 400] and 'box("away"' in app[at:at + 400]


def test_in_a_browser_the_beat_goes_and_says_only_this():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    sys.path.insert(0, str(ROOT))                         # rendercheck.py is the repository's own
    import rendercheck
    srv, port = rendercheck._serve()
    origin = f"http://127.0.0.1:{port}"
    beats, errors = [], []
    with sync_playwright() as pw:
        kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if os.path.exists("/opt/pw-browsers/chromium"):
            kw["executable_path"] = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**kw)
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)[:200]))
            page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); "
                                 "localStorage.setItem('qb.a2hs', 'off'); } catch (e) {}")
            page.route("**/api/billing/status*", lambda r: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"configured": False, "signed_in": True, "activity": True, "activity_switch": True})))
            page.route("**/api/activity", lambda r: (beats.append(r.request.post_data or ""), r.fulfill(status=204)))
            page.goto(origin + "/index.html?from=alert#recommended", wait_until="load")
            page.wait_for_timeout(3000)
            page.mouse.wheel(0, 200)
            page.wait_for_timeout(6000)
            page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
            page.evaluate("Object.defineProperty(document, 'visibilityState', {value: 'hidden', configurable: true});"
                          "document.dispatchEvent(new Event('visibilitychange'))")
            page.wait_for_timeout(500)
            ctx.close()
        finally:
            browser.close()
    got = [json.loads(b) for b in beats if b]
    assert got, "no beat was sent"
    assert got[0]["n"] == 1 and got[0]["a"] == 1, got[0]
    assert all(set(b) == {"s", "v", "sp", "n", "a"} for b in got), got
    assert sum(b["s"] for b in got) >= 5 and not any(b["n"] for b in got[1:]), got
    assert not errors, errors


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
