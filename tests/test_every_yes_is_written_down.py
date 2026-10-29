"""Consent first, and a record of it (engine/consent, engine/activity, the
"Make it yours" card in js/account.js, its trigger in js/app.js mineTick).

Ethan's second research paper (2026-10-29, "Data, Retention & the ESPN
Playbook"): "A consent log. Store what each user agreed to, which policy
version, and when", "nothing fires before consent", and onboarding that
asks "at most three questions ... the rest at the moment each one is
needed". What these hold:

  * a choice is written once with the Privacy Policy's own date, a change
    of mind is a new row, the same word again is not, and an unknown kind
    or a reader with no account writes nothing;
  * signing up writes the 21+ and Terms confirmation; turning alerts on (the
    kinds), off, or taking a break from them writes theirs;
  * the log is in the account's export, deleted with it, and named in the
    policy;
  * the card asks a signed-in reader on their second visit, never over
    another sheet, once; its activity box is drawn only while the site
    keeps activity, unticked, and only a tick sends a yes;
  * its answers are synced settings, and Settings shows and edits them;
    the books lead the Bet it sheet.

Run directly: `python3 tests/test_every_yes_is_written_down.py`
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
from engine import consent as CS                                  # noqa: E402

A.DB_PATH = _TMP / "accounts.db"
READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
NOW = 1_793_304_000.0                                             # 2026-10-29 16:00 Eastern


def test_a_choice_is_written_once_with_the_policy_s_date():
    c = sqlite3.connect(":memory:")
    assert CS.record(c, 1, "alerts", "on: posted", NOW)
    assert not CS.record(c, 1, "alerts", "on: posted", NOW + 60), "the same word again is not a new choice"
    assert CS.record(c, 1, "alerts", "off on a phone", NOW + 120)
    assert CS.record(c, 1, "alerts", "on: posted", NOW + 180), "a change of mind back is a new row"
    assert not CS.record(c, 1, "marketing", "yes", NOW), "an unknown kind"
    assert not CS.record(c, None, "alerts", "on", NOW) and not CS.record(c, 0, "terms", "x", NOW), "no account"
    log = CS.history(c, 1)
    assert [x["choice"] for x in log] == ["on: posted", "off on a phone", "on: posted"]
    assert all(x["policy"] == "2026-10-29" and x["kind"] == "alerts" for x in log), log
    assert [x["at"] for x in log] == [NOW, NOW + 120, NOW + 180]
    assert CS.latest(c, 1, "alerts") == "on: posted" and CS.latest(c, 1, "terms") is None
    assert CS.history(c, 2) == []
    cols = [r[1] for r in c.execute("PRAGMA table_info(consent_log)")]
    assert cols == ["user_id", "kind", "choice", "version", "at"]


def test_the_version_is_the_policy_s_own_last_updated():
    p = Path(tempfile.mkdtemp()) / "privacy.html"
    p.write_text('<p class="legal-date">Last updated 3 March 2027</p>')
    assert CS.policy_version(p) == "2027-03-03"
    p.write_text("<p>no date here</p>")
    os.utime(p, ns=(1, 1))
    assert CS.policy_version(p) == ""
    assert CS.policy_version(Path("/nonexistent/privacy.html")) == ""
    assert CS.policy_version() == "2026-10-29", "the live policy's date"


def test_signing_up_writes_the_terms_and_the_account_carries_the_log():
    conn = A.connect()
    try:
        code, out = A.create_user(conn, "terms@example.com", "correct horse battery", confirmed=True)
        assert code == 200
        uid = out["id"]
        log = CS.history(conn, uid)
        assert len(log) == 1 and log[0]["kind"] == "terms" and "21 or older" in log[0]["choice"], log
        assert A.export_user(conn, uid)["consent_log"] == log
        A.delete_user(conn, uid)
        assert conn.execute("SELECT COUNT(*) FROM consent_log WHERE user_id=?", (uid,)).fetchone()[0] == 0
    finally:
        conn.close()
    src = READ("engine", "accounts.py")
    assert src.count("_consented(conn, cur.lastrowid)") == 2, "email and phone sign-ups both"
    priv = READ("web", "privacy.html")
    assert "<code>consent_log</code>" in priv and "A record of each yes and no you give us" in priv


def _serve():
    import server
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _post(base, path, body, cookie=""):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, json.loads(r.read() or b"null")


def test_alerts_on_off_and_a_break_are_written():
    httpd, base = _serve()
    try:
        conn = A.connect()
        code, out = A.create_user(conn, "alerts@example.com", "correct horse battery", confirmed=True)
        uid, token = out["id"], A.start_session(conn, out["id"])
        conn.close()
        cookie, phone = f"qb_session={token}", "ab" * 32
        on = {"endpoint": phone, "kind": "apns", "topics": ["posted", "settled", "nonsense"]}
        assert _post(base, "/api/push/subscribe", on, cookie)[0] == 200
        assert _post(base, "/api/push/subscribe", on, cookie)[0] == 200, "a re-subscribe at sign-in"
        assert _post(base, "/api/push/pause", {"endpoint": phone, "hours": 24})[0] == 200
        assert _post(base, "/api/push/pause", {"endpoint": phone, "hours": 0})[0] == 200
        assert _post(base, "/api/push/unsubscribe", {"endpoint": phone})[0] == 200
        assert _post(base, "/api/push/subscribe", {"endpoint": "cd" * 32, "kind": "apns", "topics": ["posted"]})[0] == 200
        conn = A.connect()
        try:
            log = [(x["kind"], x["choice"]) for x in CS.history(conn, uid)]
        finally:
            conn.close()
        assert log[0][0] == "terms"
        assert log[1:] == [("alerts", "on: posted,settled"), ("limits", "alerts paused 24 hours"),
                           ("limits", "alerts resumed"), ("alerts", "off on a phone")], log
    finally:
        httpd.shutdown()


def test_the_card_asks_once_on_the_second_visit_and_never_presumes_a_yes():
    app = READ("web", "js", "app.js")
    tick = app[app.index("function mineTick()"):app.index("async function pushRelink()")]
    assert 'if (n < 2 || localStorage.getItem("qb.mine")) return;' in tick, "the second visit, once"
    assert 'sessionStorage.getItem("qb.v")' in tick, "a visit is counted once however many pages it opens"
    assert '_acctUser && _acctUser.signed_in' in tick and 'document.querySelector("#a2hs, #pushask, #mine")' in tick
    assert "if (!due || !pushAskDue()) { if (!ctx) mineTick(); return; }" in app, "the alerts sheet goes first"
    acct = READ("web", "js", "account.js")
    card = acct[acct.index("async function mineSheet()"):acct.index("/* A plan tapped before the account exists")]
    assert "const ask = !!(_pwStatus && _pwStatus.activity_switch && !_pwStatus.activity);" in card
    box = card[card.index("${ask ?"):card.index("</label>")]
    assert 'type="checkbox" data-mine-consent' in box and "checked" not in box, "unticked until they tick it"
    assert "if (ok && ok.checked) {" in card and "JSON.stringify({ off: false })" in card
    assert 'setSetting("goals", picked("goals"));' in card and 'setSetting("books", picked("books"));' in card
    assert 'track("onboarding", ' in card
    assert 'localStorage.setItem("qb.mine", go.dataset.mineGo === "yes" ? "done" : "no")' in card, \
        "Not now is an answer too: never asked again"
    from engine import analytics as AN
    assert "onboarding" in AN.CLIENT_EVENTS and "limit_set" in AN.CLIENT_EVENTS


def test_settings_keep_and_edit_the_answers():
    app = READ("web", "js", "app.js")
    assert "  books: []," in app and "  goals: []," in app
    assert app.count('["teams", "leagues", "books", "goals"].forEach((k) => { if (!Array.isArray(_settings[k])) _settings[k] = []; });') == 2
    acct = READ("web", "js", "account.js")
    assert 'data-set-open="books"' in acct and 'data-set-open="goals"' in acct
    assert 'if (page === "books" || page === "goals") {' in acct and 'hit("[data-set-multi]")' in acct, \
        "one screen for each list, and its handler"
    assert "Off: nothing is kept until you say yes" in acct
    # Their books lead the Bet it sheet: an answer that does something.
    sheet = app[app.index("function betSheetShow("):app.index("function betSheetShow(") + 1400]
    assert "const own = settings().books;" in sheet and "Your book" in sheet


def test_in_a_browser_the_card_saves_the_answers_and_only_a_tick_says_yes():
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
    seen = ("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); "
            "localStorage.setItem('qb.a2hs', 'off'); if (!localStorage.getItem('qb.visits')) "
            "localStorage.setItem('qb.visits', '1'); } catch (e) {}")
    got, posts, errors = {}, [], []

    def staged(ctx, signed_in=True):
        ctx.add_init_script(seen)
        ctx.route("**/api/account/me", lambda r: r.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"signed_in": signed_in, "email": "you@example.com"} if signed_in
                                  else {"signed_in": False})))
        ctx.route("**/api/billing/status*", lambda r: r.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"configured": False, "signed_in": signed_in, "activity_switch": True,
                                   "activity": False})))
        ctx.route("**/api/account/activity", lambda r: (posts.append(r.request.post_data or ""), r.fulfill(
            status=200, content_type="application/json", body=json.dumps({"switch": True, "off": False}))))
        ctx.route("**/api/activity", lambda r: r.fulfill(status=204))

    with sync_playwright() as pw:
        kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if os.path.exists("/opt/pw-browsers/chromium"):
            kw["executable_path"] = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**kw)
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            staged(ctx)
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)[:200]))
            page.goto(origin + "/index.html#recommended", wait_until="load")
            page.wait_for_selector("#mine .mine-card", timeout=8000)
            got["box"] = page.evaluate("(() => { const b = document.querySelector('[data-mine-consent]');"
                                       " return b ? b.checked : null; })()")
            page.click("#mine [data-mine='goals'][data-v='props']")
            page.click("#mine [data-mine='books'][data-v='fanduel']")
            page.click("#mine [data-mine-go='yes']")
            page.wait_for_timeout(500)
            got["first"] = page.evaluate("({ s: settings(), mine: localStorage.getItem('qb.mine'),"
                                         " gone: !document.getElementById('mine') })")
            got["posts_untucked"] = list(posts)
            page.reload(wait_until="load")
            page.wait_for_timeout(2500)
            got["again"] = page.evaluate("!!document.getElementById('mine')")
            ctx.close()
            # Ticked this time: the yes is sent.
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            staged(ctx)
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)[:200]))
            page.goto(origin + "/index.html#recommended", wait_until="load")
            page.wait_for_selector("#mine .mine-card", timeout=8000)
            page.check("#mine [data-mine-consent]")
            page.click("#mine [data-mine-go='yes']")
            page.wait_for_timeout(800)
            got["posts_ticked"] = list(posts)
            ctx.close()
            # Signed out: never asked.
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            staged(ctx, signed_in=False)
            page = ctx.new_page()
            page.goto(origin + "/index.html#recommended", wait_until="load")
            page.wait_for_timeout(3000)
            got["signed_out"] = page.evaluate("!!document.getElementById('mine')")
            ctx.close()
        finally:
            browser.close()
    assert got["box"] is False, got
    s = got["first"]["s"]
    assert s["goals"] == ["props"] and s["books"] == ["fanduel"], s
    assert got["first"]["mine"] == "done" and got["first"]["gone"], got["first"]
    assert got["posts_untucked"] == [], "no tick, no yes"
    assert got["again"] is False, "asked once"
    assert [json.loads(p) for p in got["posts_ticked"]] == [{"off": False}], got["posts_ticked"]
    assert got["signed_out"] is False
    assert not errors, errors


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
