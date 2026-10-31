"""A member's own weekly limit (engine/limits, Settings → Limits, My Bets,
engine/pushalerts and engine/pushmine).

Ethan's second research paper (2026-10-29): "Self-set limits (alert pause,
weekly bet cap) — Settings, always visible — Responsible-play tools, and
your best legal defense", "limit_set: User sets a pause or cap", and its
checklist: "Users who set a pause or limit get zero promotional alerts
until it ends." What these hold:

  * the limit is the member's own dollars a week, Monday to Sunday,
    Eastern; nonsense is no limit; a week's stakes are the bets dated in it,
    whatever became of them;
  * once reached, no promotional alert reaches that member's phones until
    Monday — not the shared ones, not their own queue's, not what a knocked
    phone is shown — while their own tickets' alerts still come;
  * setting, changing or clearing it is written in the consent log;
  * Settings shows it always, My Bets says where the week stands and says
    so once when a bet crosses it, and setting it or a break is counted.

Run directly: `python3 tests/test_your_own_limit_quiets_the_invitations.py`
"""
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp())

from engine import accounts as A                                  # noqa: E402
from engine import limits as LM                                   # noqa: E402
from engine import pushalerts as PA                               # noqa: E402
from engine import pushmine as PM                                 # noqa: E402

A.DB_PATH = _TMP / "accounts.db"
READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
ET = ZoneInfo("America/New_York")
NOW = 1_793_304_000.0                                             # Thursday 2026-10-29 16:00 Eastern


def _et(y, mo, d, h, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=ET).timestamp()


def test_the_limit_and_the_week():
    assert LM.limit_of({"limit_week": 200}) == 200 and LM.limit_of({"limit_week": "150"}) == 150
    for bad in ({}, None, {"limit_week": 0}, {"limit_week": -5}, {"limit_week": "lots"}, {"limit_week": 2e6}, "x"):
        assert LM.limit_of(bad) == 0, bad
    assert LM.week_of(NOW) == ("2026-10-26", "2026-11-01")
    assert LM.week_of(_et(2026, 11, 1, 23, 30)) == ("2026-10-26", "2026-11-01"), "Sunday night is still the week"
    assert LM.week_of(_et(2026, 11, 2, 0, 30)) == ("2026-11-02", "2026-11-08"), "Monday starts the next"
    bets = [{"date": "2026-10-26", "stake": 50, "result": "loss"}, {"date": "2026-10-29", "stake": "25.5"},
            {"date": "2026-11-01", "stake": 10, "result": "win"}, {"date": "2026-10-25", "stake": 999},
            {"date": "2026-11-02", "stake": 999}, {"date": "2026-10-28", "stake": -40}, {"date": "2026-10-28"},
            {"date": "2026-10-28", "stake": "x"}, "junk", None]
    assert LM.staked(bets, LM.week_of(NOW)) == 85.5
    assert LM.changed({}, {"limit_week": 200}) == "weekly limit $200"
    assert LM.changed({"limit_week": 200}, {"limit_week": 1500}) == "weekly limit $1,500"
    assert LM.changed({"limit_week": 200}, {"limit_week": 0}) == "weekly limit off"
    assert LM.changed({"limit_week": 200}, {"limit_week": 200, "odds": "decimal"}) is None
    assert LM.changed(None, None) is None


def _db():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE user_data (user_id INTEGER, section TEXT, ts INTEGER, payload TEXT, "
              "PRIMARY KEY (user_id, section))")
    PA.ensure_tables(c)
    PM.ensure_tables(c)
    return c


def _member(c, uid, limit, stakes, day="2026-10-28"):
    c.execute("INSERT INTO user_data VALUES (?, 'settings', 1, ?)", (uid, json.dumps({"limit_week": limit})))
    c.execute("INSERT INTO user_data VALUES (?, 'mybets', 1, ?)", (uid, json.dumps(
        {"rows": [{"id": f"b{i}", "date": day, "stake": s, "result": "pending"} for i, s in enumerate(stakes)],
         "deleted": []})))


def test_who_has_reached_their_limit():
    c = _db()
    _member(c, 1, 200, [150, 60])                    # $210 of $200: reached
    _member(c, 2, 200, [150])                        # under
    _member(c, 3, 0, [5000])                         # no limit at all
    _member(c, 4, 100, [500], day="2026-10-20")      # last week's stakes do not count
    assert LM.reached(c, NOW) == {1}
    assert LM.standing(c, 2, NOW) == {"limit": 200, "staked": 150, "week": ("2026-10-26", "2026-11-01")}
    assert LM.standing(c, 3, NOW) is None
    assert LM.reached(sqlite3.connect(":memory:"), NOW) == set(), "no accounts table: nobody"


def _sub(c, endpoint, uid, topics):
    assert PA.subscribe(c, endpoint, kind="apns", user_id=uid, topics=topics)[0] == 200


def test_a_reached_limit_stops_the_shared_alerts_and_their_own_promotions():
    c = _db()
    _member(c, 1, 200, [250])
    _member(c, 2, 200, [20])
    _sub(c, "a1" * 16, 1, ["posted", "settled", "bets", "away"])
    _sub(c, "b2" * 16, 2, ["posted", "settled", "bets", "away"])
    _sub(c, "c3" * 16, None, ["posted", "settled"])
    sent = []
    apns = lambda e, m, cfg: sent.append((e[:2], m["kind"])) or 200          # noqa: E731
    kw = dict(apns=apns, apns_cfg={"x": 1}, vapid={"x": 1})
    msg = {"id": "posted:nfl", "kind": "posted", "league": "nfl", "title": "t", "body": "b", "url": "/"}
    st = PA.send(c, [msg], now_s=NOW, **kw)
    assert ("a1", "posted") not in sent and ("b2", "posted") in sent and ("c3", "posted") in sent, sent
    assert st["limited"] == 1 and st["sent"] == 2, st
    # Their own queue: the away line is dropped for the member at their
    # limit, never held for Monday; their ticket's alert still goes.
    sent.clear()
    for uid in (1, 2):
        assert PM.tell(c, uid, f"away:{uid}", "away", "New since you were here", "b", "/", now=NOW)
        assert PM.tell(c, uid, f"bet:{uid}", "bets", "Your parlay starts in 10", "b", "/", now=NOW)
    st = PM.flush(c, now=NOW, quiet=False, **kw)
    assert ("a1", "bets") in sent and ("a1", "away") not in sent, sent
    assert ("b2", "bets") in sent and ("b2", "away") in sent, sent
    assert st["limited"] == 1, st
    assert c.execute("SELECT COUNT(*) FROM push_mine WHERE sent = 0").fetchone()[0] == 0, "dropped, not held"


def test_a_knocked_phone_is_never_shown_a_promotion_past_the_limit():
    path = Path(tempfile.mkdtemp()) / "latest.json"
    t = NOW
    path.write_text(json.dumps({"messages": [
        {"id": "posted:nba", "kind": "posted", "league": "nba", "title": "NBA picks are up", "body": "b", "url": "/",
         "at": t - 60}]}))
    mine = [{"id": "bet:1", "kind": "bets", "title": "Your parlay starts in 10", "body": "b", "url": "/", "at": t - 600}]
    sub = {"topics": ["posted", "bets"], "leagues": []}
    assert PA.latest_for(sub, path, now=t, mine=mine)["title"] == "NBA picks are up"
    assert PA.latest_for(sub, path, now=t, mine=mine, skip=LM.PROMO)["title"] == "Your parlay starts in 10"
    srv = READ("server.py")
    at = srv.index('if path == "latest":')
    assert "skip=LM.PROMO if st and st[\"staked\"] >= st[\"limit\"] else ()" in srv[at:at + 700]


def _serve():
    import server
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _post(base, path, body, cookie):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Cookie": cookie})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, json.loads(r.read() or b"null")


def test_setting_changing_and_clearing_it_is_written_down():
    from engine import consent as CS
    httpd, base = _serve()
    try:
        conn = A.connect()
        code, out = A.create_user(conn, "limit@example.com", "correct horse battery", confirmed=True)
        uid, token = out["id"], A.start_session(conn, out["id"])
        conn.close()
        cookie = f"qb_session={token}"
        for ts, settings in ((10, {"odds": "american"}), (20, {"odds": "american", "limit_week": 200}),
                             (30, {"odds": "decimal", "limit_week": 200}), (40, {"limit_week": 300}),
                             (50, {"limit_week": 0})):
            assert _post(base, "/api/account/data", {"sections": {"settings": {"ts": ts, "data": settings}}},
                         cookie)[0] == 200
        conn = A.connect()
        try:
            log = [x["choice"] for x in CS.history(conn, uid) if x["kind"] == "limits"]
        finally:
            conn.close()
        assert log == ["weekly limit $200", "weekly limit $300", "weekly limit off"], log
    finally:
        httpd.shutdown()


def test_settings_my_bets_and_the_counts():
    app = READ("web", "js", "app.js")
    assert "  limit_week: 0," in app
    save = app[app.index("function mbSave(bets) {"):app.index("function mbSave(bets) {") + 900]
    assert "if (lim && was < lim && now >= lim) tfToast(" in save, "said once, as a bet crosses it"
    acct = READ("web", "js", "account.js")
    lst = acct[acct.index('out.push(setGroup("Limits", ['):acct.index('out.push(setGroup("Limits", [') + 900]
    assert 'data-set-open="limit"' in lst and 'href: "#alerts"' in lst and "1-800-GAMBLER" in lst
    assert "const inn" not in lst, "always visible, signed in or not"
    assert 'if (page === "limit") {' in acct and 'track("limit_set", off ? "off" : "week");' in acct
    assert "${mbLimitHTML(bets)}" in acct and 'data-act="toAccount" data-arg="limit"' in acct
    more = READ("web", "js", "more.js")
    assert 'track("limit_set", `pause${el.dataset.pushPause}`);' in more
    from engine import analytics as AN
    assert "limit_set" in AN.CLIENT_EVENTS
    priv = READ("web", "privacy.html")
    assert "once the bets you log that week reach it we send none of" in priv


def test_the_page_counts_the_eastern_week_the_way_the_box_does():
    import shutil
    node = shutil.which("node")
    if not node:
        print("      (skipped: no node)")
        return
    app = READ("web", "js", "app.js")
    fns = app[app.index("function limitWeek() {"):app.index("function mbSave(bets) {")]
    js = fns + """
const [lo, hi] = limitWeek();
const iso = (d) => d.toISOString().slice(0, 10);
const day = (n) => { const d = new Date(lo + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return iso(d); };
console.log(JSON.stringify({ lo, hi, sum: limitStaked([{ date: lo, stake: 50 }, { date: hi, stake: "25" },
  { date: day(-1), stake: 999 }, { date: day(7), stake: 999 }, { date: lo, stake: -5 }, null, { date: lo }]) }));
"""
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    got = json.loads(out.stdout)
    lo, hi = LM.week_of()
    assert (got["lo"], got["hi"]) == (lo, hi), (got, lo, hi)
    assert got["sum"] == 75, got


def test_in_a_browser_set_it_log_past_it_and_hear_it_once():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    srv, port = rendercheck._serve()
    origin = f"http://127.0.0.1:{port}"
    got, errors = {}, []
    with sync_playwright() as pw:
        kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if os.path.exists("/opt/pw-browsers/chromium"):
            kw["executable_path"] = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**kw)
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            ctx.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done');"
                                " localStorage.setItem('qb.a2hs', 'off'); localStorage.setItem('qb.mine', 'no'); } catch (e) {}")
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)[:200]))
            page.goto(origin + "/index.html#recommended", wait_until="load")
            page.wait_for_timeout(1500)
            page.evaluate("window._acctTab = 'settings'; window._setOpen = 'limit'; switchView('account', true);")
            page.wait_for_selector(".set-limit", timeout=8000)
            page.fill(".set-limit", "100")
            page.click("[data-set-limit='save']")
            page.wait_for_timeout(300)
            got["limit"] = page.evaluate("settings().limit_week")
            got["row"] = page.evaluate("(document.querySelector('[data-set-open=\"limit\"]') || {}).textContent || ''")
            page.evaluate("switchView('mybets', true)")
            page.wait_for_selector("#mb-stake", timeout=8000)
            for stake, desc in (("60", "Lakers ML"), ("50", "Celtics -3.5")):
                page.fill("#mb-desc", desc)
                page.fill("#mb-stake", stake)
                page.fill("#mb-odds", "-110")
                page.click("[data-act='mbAdd']")
                page.wait_for_timeout(400)
                got.setdefault("toasts", []).append(page.evaluate(
                    "[...document.querySelectorAll('.tf-toast, .toast')].map((t) => t.textContent).join(' | ')"))
            got["strip"] = page.evaluate("(document.querySelector('.wk-limit') || {}).className || ''")
            got["strip_text"] = page.evaluate("(document.querySelector('.wk-limit') || {}).textContent || ''")
            ctx.close()
        finally:
            browser.close()
    assert got["limit"] == 100 and "$100" in got["row"], got
    assert "past the $100.00 you set" in got["toasts"][1] or "past the $100 you set" in got["toasts"][1], got
    assert "past the" not in got["toasts"][0], "under the limit: nothing said"
    assert "over" in got["strip"] and "$110" in got["strip_text"], got
    assert not errors, errors


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
