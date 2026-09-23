"""Analytics: counts, never people, and nothing at all until Ethan says yes.

Ethan's product audit, 2026-09-23, item 14 (where do subscribers come
from, which page converts them, how many open the Record), and "Ok keep
going" when it was named as the next build. The Privacy Policy promises
in bold that the site runs no analytics, so engine/analytics.py ships
switched off (QB_ANALYTICS=1 turns it on) with the policy wording drafted
for his sign-off. What this file holds it to:

  * off by default: the page is told so and sends nothing, the endpoint
    stores nothing, a subscription change counts nothing, and the policy's
    promise is still on the page;
  * on: one row per (day, event, page, source, who) and a count — no
    column that could hold an id, an address or a URL, every part checked
    against a list, and a page cannot claim a subscription;
  * a Stripe status change is counted as the business event it is;
  * a signed-in visit refreshes last_seen at most once a day, so "came
    back after day 1 / day 7" can be read from the accounts table;
  * the report says what it counts and where it came from.

Every fixture is built in a temp directory; nothing here reads the box.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp())
os.environ.pop("QB_ANALYTICS", None)
os.environ["QB_ANALYTICS_DB"] = str(_TMP / "analytics.db")

from engine import accounts as A                               # noqa: E402
from engine import analytics as AN                             # noqa: E402
from engine import billing as BI                               # noqa: E402

A.DB_PATH = _TMP / "accounts.db"
AN.DB_PATH = _TMP / "analytics.db"
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _on(flag: bool) -> None:
    if flag:
        os.environ["QB_ANALYTICS"] = "1"
    else:
        os.environ.pop("QB_ANALYTICS", None)


def _counts() -> list[tuple]:
    if not AN.DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(AN.DB_PATH))
    try:
        return conn.execute("SELECT event, page, source, who, n FROM counts ORDER BY event, page").fetchall()
    finally:
        conn.close()


def _wipe() -> None:
    AN.DB_PATH.unlink(missing_ok=True)


def test_off_by_default_and_the_policy_still_says_so():
    _on(False)
    _wipe()
    assert AN.enabled() is False
    assert AN.record("view", "record", "search", "visitor") is False
    assert not AN.DB_PATH.exists(), "switched off, not even a file"
    privacy = (ROOT / "web" / "privacy.html").read_text()
    assert "We run no analytics, no advertising, no tracking pixels" in privacy, \
        "the promise stays on the page until the switch and the new wording go live together"
    audit = (ROOT / "docs" / "AUDIT_2026-09-23.md").read_text()
    assert "Draft policy wording" in audit and "QB_ANALYTICS=1" in audit


def test_on_it_counts_one_row_per_key_and_nothing_about_anyone():
    _on(True)
    _wipe()
    try:
        for _ in range(3):
            assert AN.record("view", "record", "search", "visitor")
        assert AN.record("view", "Record", "search", "visitor"), "page names are lower-cased"
        assert AN.record("checkout_click", "prop", "social", "member")
        assert AN.record("view", "https://evil.example/x?email=a@b.c", "nosuch", "admin")
        assert AN.record("launch_missiles") is False, "only listed events"
        assert _counts() == [("checkout_click", "prop", "social", "member", 1),
                             ("view", "", "", "", 1),
                             ("view", "record", "search", "visitor", 4)], \
            "a URL, an unknown source or an unknown kind of reader is dropped to blank, not stored"
        conn = sqlite3.connect(str(AN.DB_PATH))
        cols = [r[1] for r in conn.execute("PRAGMA table_info(counts)")]
        conn.close()
        assert cols == ["day", "event", "page", "source", "who", "n"], "no column that could hold a person"
    finally:
        _on(False)
        _wipe()


def test_a_subscription_change_is_the_business_event_it_is():
    t = AN.transition
    assert t(None, None, "trialing", 1) == "trial_started"
    assert t("trialing", 1, "active", 2) == "trial_converted"
    assert t(None, None, "active", 2) == "subscribed" and t("canceled", 1, "active", 2) == "subscribed"
    assert t("past_due", 1, "active", 2) is None, "a card that went through again is not a new subscriber"
    assert t("active", 1, "canceled", 1) == "canceled" and t("trialing", 1, "canceled", 1) == "canceled"
    assert t("active", 1000.0, "active", 1000.0 + 30 * AN.DAY_S) == "renewed"
    assert t("active", 1000.0, "active", 1000.0 + 60) is None, "the same period again is not a renewal"
    assert t("trialing", 1, "trialing", 1) is None and t("active", None, "past_due", 1) is None


def test_stripe_s_word_is_counted_where_it_arrives_and_only_when_on():
    _wipe()
    conn = A.connect()
    try:
        BI.init(conn)
        code, out = A.create_user(conn, "fan@example.com", "correct horse battery", confirmed=True)
        assert code == 200, out
        uid = out["id"]
        _on(False)
        assert BI.apply_event(conn, {"user_id": uid, "status": "trialing", "period_end": 1.0})
        assert not AN.DB_PATH.exists(), "off: a trial is applied and nothing is counted"
        _on(True)
        assert BI.apply_event(conn, {"user_id": uid, "status": "active", "period_end": 2.0})
        assert BI.apply_event(conn, {"user_id": uid, "status": "active", "period_end": 2.0 + 31 * AN.DAY_S})
        assert BI.apply_event(conn, {"user_id": uid, "status": "canceled", "period_end": 2.0 + 31 * AN.DAY_S})
        assert [(e, n) for e, _p, _s, _w, n in _counts()] == [("canceled", 1), ("renewed", 1),
                                                             ("trial_converted", 1)]
        assert all(p == s == w == "" for _e, p, s, w, _n in _counts()), "no account attached"
    finally:
        conn.close()
        _on(False)
        _wipe()


def test_a_signed_in_visit_refreshes_last_seen_once_a_day():
    conn = A.connect()
    try:
        code, out = A.create_user(conn, "seen@example.com", "correct horse battery", confirmed=True)
        uid = out["id"]
        conn.execute("UPDATE users SET last_seen=NULL WHERE id=?", (uid,))
        _on(False)
        assert AN.seen(conn, uid) is False
        _on(True)
        now = time.time()
        assert AN.seen(conn, uid, now) is True
        assert AN.seen(conn, uid, now + 3600) is False, "at most once a day"
        assert AN.seen(conn, uid, now + AN.SEEN_EVERY_S + 1) is True
    finally:
        conn.close()
        _on(False)


def _serve():
    import server
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _post(base, body, cookie=""):
    req = urllib.request.Request(base + "/api/event", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status


def test_the_endpoint_counts_only_the_page_s_events_and_reads_who_off_the_request():
    _wipe()
    httpd, base = _serve()
    try:
        _on(False)
        status = json.loads(urllib.request.urlopen(base + "/api/billing/status", timeout=10).read())
        assert status["analytics"] is False, "the page is told it is off"
        assert _post(base, {"e": "view", "page": "record", "src": "search"}) == 204
        assert not AN.DB_PATH.exists(), "off: the endpoint stores nothing"
        _on(True)
        assert json.loads(urllib.request.urlopen(base + "/api/billing/status", timeout=10).read())["analytics"]
        assert _post(base, {"e": "view", "page": "record", "src": "search"}) == 204
        assert _post(base, {"e": "subscribed"}) == 204 and _post(base, {"e": "renewed"}) == 204
        conn = A.connect()
        code, out = A.create_user(conn, "member@example.com", "correct horse battery", confirmed=True)
        token = A.start_session(conn, out["id"])
        conn.close()
        assert _post(base, {"e": "visit", "page": "home", "src": "direct"}, f"qb_session={token}") == 204
        assert _counts() == [("view", "record", "search", "visitor", 1), ("visit", "home", "direct", "member", 1)], \
            "a page cannot claim a subscription; a signed-in reader is a member, and that word is all that is kept"
    finally:
        httpd.shutdown()
        _on(False)
        _wipe()


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    start = APP.index("const AN_QUEUE_MAX")
    flush = APP.index("function anFlush()", start)
    sect = APP[start:APP.index("\n}\n", flush) + 3]
    prelude = """
      const sent = [];
      globalThis.fetch = (url, opt) => { sent.push([url, JSON.parse(opt.body)]); return Promise.resolve({}); };
      const store = {};
      globalThis.sessionStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); } };
      globalThis.location = { search: "", hostname: "qellysbook.com" };
      globalThis.document = { referrer: "" };
      let _pwStatus = null;
      const state = { view: "home" };
    """
    prog = prelude + sect + f"\nconsole.log(JSON.stringify((() => {{ {js} }})()));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_page_sends_nothing_until_the_server_says_on():
    got = _node("""
      track("view", "record"); track("ask", "nfl");
      const before = sent.length;
      _pwStatus = { analytics: false }; anFlush(); track("view", "props");
      const off = sent.length;
      _pwStatus = null; track("view", "record");
      _pwStatus = { analytics: true }; anFlush(); track("checkout_click", "prop");
      return { before, off, sent: sent.map(([u, b]) => [u, b]) };""")
    if got is None:
        print("  SKIP node not installed")
        return
    assert got["before"] == 0 and got["off"] == 0, "queued, then thrown away when the answer is no"
    assert got["sent"] == [["/api/event", {"e": "visit", "page": "home", "src": "direct"}],
                           ["/api/event", {"e": "view", "page": "home", "src": "direct"}],
                           ["/api/event", {"e": "view", "page": "record", "src": "direct"}],
                           ["/api/event", {"e": "checkout_click", "page": "prop", "src": "direct"}]], \
        "one visit a tab, the page it landed on (a bare address never switches to it), then what waited, " \
        "then the rest — an event, a page name and a bucket, nothing else"


def test_where_a_visit_came_from_is_a_bucket_never_the_address():
    got = _node("""
      const at = (ref, search = "") => { document.referrer = ref; location.search = search; return anSource(); };
      return [at(""), at("https://qellysbook.com/#record"), at("https://www.google.com/search?q=x"),
              at("https://l.instagram.com/?u=x"), at("https://t.co/abc"), at("https://someblog.net/post"),
              at("https://www.google.com/", "?utm_source=ig&utm_campaign=launch"), at("not a url")];""")
    if got is None:
        return
    assert got == ["direct", "direct", "search", "social", "social", "referral", "campaign", ""]


def test_the_views_the_ask_and_the_plan_button_are_counted_where_they_happen():
    switch = APP[APP.index("function _switchViewNow("):]
    switch = switch[:switch.index("\n}\n")]
    assert 'track("view", name);' in switch and "if (name !== leaving || !_anLanded) {" in switch, \
        "the page a visit lands on is a view too, though state.view already names it"
    assert "if (!AN_NOT_FROM.includes(name)) _anFrom = name;" in switch
    send = APP[APP.index("async function askSend("):]
    assert 'track("ask", state.sport);' in send[:send.index("\n}\n")]
    pay = APP[APP.index("window.coPay = async function (btn) {"):]
    assert 'track("checkout_click", _anFrom);' in pay[:pay.index("\n};\n")]
    assert APP.index("COUNTS, NEVER PEOPLE") < APP.index("ACCOUNTS — one name, every device"), \
        "outside the block that holds personal data, which talks only to our account endpoints"
    assert "discord.gg" not in APP
    check = APP[APP.index("async function paywallCheck()"):]
    assert "_pwStatus = await r.json();\n    anFlush();" in check[:check.index("\n}\n")]


def test_the_report_says_what_it_counts():
    _on(True)
    _wipe()
    try:
        AN.record("visit", "home", "search", "visitor")
        AN.record("view", "paywall", "search", "visitor")
        AN.record("checkout_click", "record", "search", "visitor")
        AN.record("trial_started")
        text = AN.report(7, accounts_path=A.DB_PATH)
    finally:
        _on(False)
        _wipe()
    assert "Switched ON" in text and "most viewed pages:" in text and "paywall" in text
    assert "where visits came from" in text and "search" in text
    assert "the page a checkout click came from:" in text and "record" in text
    assert "came back after day 1" in text and "came back after day 7" in text
    assert "Switched OFF: nothing is being counted" in AN.report(7, accounts_path=A.DB_PATH)


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
            traceback.print_exc(limit=3)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
