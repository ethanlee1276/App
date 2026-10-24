"""Every open of the site asks Stripe whether they are still subscribed.

Ethan, 2026-10-13: "every time a user opens the site or launches the site
it should check too see if they are still subscribed".

What was true before this file: the page asked OUR server at boot, on
coming back to the tab (at most every five minutes) and on a five-minute
timer, and our server answered from the row Stripe's webhook keeps. It
read Stripe itself only when that row was due a read — hourly while
entitled (engine/billing.RECHECK_S) — so a lapse whose webhook was lost
could keep opening the site for up to an hour.

Now an open is a read of Stripe: the boot call, the call after a sign-in
and the call on coming back to the tab say `fresh=1`, and the server reads
the subscription then, at most once a minute per account
(billing.RECHECK_OPEN_S) so a reload loop cannot hammer Stripe. The
five-minute timer still answers from the row. A walled tab that comes back
entitled is let back in.

Every test here is offline: Stripe is a stub `fetch`, never the network.

    python3 tests/test_every_open_checks_the_subscription.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A      # noqa: E402
from engine import billing as B       # noqa: E402

DAY = 86400


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


SERVER = _read("server.py")
APP = _read("web", "js", "app.js")


def _db():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "acc.db")
    conn = A.connect(path)
    B.init(conn)
    _code, who = A.create_user(conn, "open@example.com",
                               "correct-horse-battery", confirmed=True)
    return conn, who["id"], path


def _subscribed(conn, uid, sub="sub_O1", cus="cus_O1"):
    for kind, obj in (
            ("checkout.session.completed", {
                "client_reference_id": str(uid), "customer": cus,
                "subscription": sub, "payment_status": "paid",
                "metadata": {"plan": "monthly"}}),
            ("customer.subscription.updated", {
                "id": sub, "customer": cus, "status": "active",
                "metadata": {"plan": "monthly"},
                "items": {"data": [{"current_period_end": time.time() + 30 * DAY}]}})):
        B.apply_event(conn, B.read_event({"type": kind, "data": {"object": obj}}))


def _stub(status):
    calls = []

    def fetch(sid):
        calls.append(sid)
        return {"id": sid, "customer": "cus_O1", "status": status}
    return fetch, calls


def _body(src, head):
    i = src.index(head)
    return src[i:src.index("\n}\n", i)]


# --- the rule: an open reads Stripe, a reload loop does not ---------------------
def test_an_open_reads_stripe_inside_the_hour_the_row_would_wait():
    conn, uid, _ = _db()
    _subscribed(conn, uid)
    now = time.time()
    fetch, calls = _stub("active")
    assert B.refresh(conn, uid, now=now, fetch=fetch)
    # Ten minutes on, Stripe has cancelled and the webhook never came.
    fetch, calls = _stub("canceled")
    assert B.refresh(conn, uid, now=now + 600, fetch=fetch) is False and calls == [], \
        "the plain status call should still wait out the hour"
    assert B.refresh(conn, uid, now=now + 600, fetch=fetch, every=B.RECHECK_OPEN_S) is True
    assert calls == ["sub_O1"]
    assert B.status_for(conn, uid)["entitled"] is False, "an open did not hear the lapse"


def test_a_reload_loop_asks_stripe_once_a_minute():
    conn, uid, _ = _db()
    _subscribed(conn, uid)
    now = time.time()
    fetch, calls = _stub("active")
    assert B.refresh(conn, uid, now=now, fetch=fetch, every=B.RECHECK_OPEN_S)
    for later in (1, 10, B.RECHECK_OPEN_S - 1):
        assert B.refresh(conn, uid, now=now + later, fetch=fetch, every=B.RECHECK_OPEN_S) is False
    assert len(calls) == 1, f"Stripe asked {len(calls)} times inside a minute"
    assert B.refresh(conn, uid, now=now + B.RECHECK_OPEN_S + 1, fetch=fetch, every=B.RECHECK_OPEN_S)
    assert len(calls) == 2
    assert 0 < B.RECHECK_OPEN_S <= B.RECHECK_S


# --- the server: `fresh=1` is what makes the status call an open ----------------
def test_the_status_call_reads_stripe_on_an_open_and_waits_otherwise():
    import server
    conn, uid, path = _db()
    _subscribed(conn, uid)
    conn.close()
    seen = []
    saved = (A.DB_PATH, B.refresh)
    A.DB_PATH = path
    B.refresh = lambda conn, user_id, **kw: seen.append((user_id, kw)) or False
    try:
        h = object.__new__(server.Handler)
        sent = []
        h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
        h._account = lambda conn: {"id": uid, "email": "open@example.com"}
        h._billing_get("status", {"fresh": ["1"]})
        assert sent[-1][0] == 200 and sent[-1][1]["entitled"] is True, sent[-1]
        assert seen[-1] == (uid, {"every": B.RECHECK_OPEN_S}), seen
        h._billing_get("status", {})
        assert seen[-1] == (uid, {}), "a plain status call is not an open"
        h._billing_get("status")
        assert seen[-1] == (uid, {}) and sent[-1][0] == 200
        h._billing_get("status", {"fresh": ["yes"]})
        assert seen[-1] == (uid, {}), "only fresh=1 is an open"
    finally:
        A.DB_PATH, B.refresh = saved
    i = SERVER.index('if parsed.path.startswith("/api/billing/"):')
    assert "parse_qs(parsed.query)" in SERVER[i:i + 240], "the query never reaches the status call"


# --- the page: boot, sign-in and the return are opens ---------------------------
def test_the_page_opens_with_fresh_on_boot_sign_in_and_return():
    check = _body(APP, "async function paywallCheck(fresh)")
    assert '"/api/billing/status" + (fresh ? "?fresh=1" : "")' in check
    assert "paidReturnWait().then((paid) => paywallCheck(1).then((walled) => {" in APP, \
        "opening the site does not ask Stripe"
    assert "const walled = await paywallCheck(1);" in _body(APP, "async function acctLandAfterAuth("), \
        "signing in does not ask Stripe"
    ret = _body(APP, "function refreshOnReturn(")
    assert "wallRecheck()" in ret, "coming back to the tab does not ask"
    assert "setInterval(wallRecheck, 3e5, 1);" in APP, "the five-minute timer should read the row"


def _node(script):
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return None
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    return out.stdout


def test_coming_back_asks_and_the_wall_goes_up_or_comes_down():
    i = APP.index("let _wallAsked = Date.now();")
    j = APP.index("setInterval(wallRecheck, 3e5, 1);", i) + len("setInterval(wallRecheck, 3e5, 1);")
    src = APP[i:j]
    cases = [
        # (walled before, server says walled, view, timer?, seconds since last ask, static)
        ("entitled, back after a minute", False, False, "recommended", False, 61, False),
        ("entitled, back inside a minute", False, False, "recommended", False, 30, False),
        ("timer inside five minutes", False, False, "recommended", True, 61, False),
        ("timer after five minutes", False, False, "recommended", True, 301, False),
        ("lapsed while away", False, True, "recommended", False, 61, False),
        ("lapsed on an open page", False, True, "record", False, 61, False),
        ("walled, paid elsewhere", True, False, "paywall", False, 61, False),
        ("walled, still walled", True, True, "paywall", False, 61, False),
        ("a static copy", False, True, "recommended", False, 61, True),
    ]
    script = (
        "const vm = require('vm');"
        f"const src = {json.dumps(src)};"
        f"const cases = {json.dumps(cases)};"
        "(async () => { const out = {};"
        "for (const [name, before, answer, view, timer, age, stat] of cases) {"
        "  const log = []; let now = 1e9;"
        "  const ctx = { state: { static: stat, view },"
        "    document: { body: { classList: { contains: (c) => c === 'walled' && before } } },"
        "    location: { hash: '#' + view, reload: () => log.push('reload') },"
        "    WALL_OPEN: ['paywall', 'checkout', 'record', 'account', 'discord'],"
        "    dcFirstStop: () => '#recommended',"
        "    paywallCheck: async (fresh) => { log.push(fresh ? 'ask stripe' : 'ask row'); return answer; },"
        "    setInterval: (fn, ms, arg) => log.push('timer ' + ms + ' ' + arg),"
        "    Date: { now: () => now } };"
        "  vm.createContext(ctx); vm.runInContext(src, ctx); now += age * 1000;"
        "  await vm.runInContext(timer ? 'wallRecheck(1)' : 'wallRecheck()', ctx);"
        "  out[name] = { log, hash: ctx.location.hash }; }"
        "process.stdout.write(JSON.stringify(out)); })();")
    raw = _node(script)
    if raw is None:
        return
    got = json.loads(raw)
    timer = "timer 300000 1"
    assert got["entitled, back after a minute"] == {"log": [timer, "ask stripe"], "hash": "#recommended"}
    assert got["entitled, back inside a minute"]["log"] == [timer], "a tab-switch storm asks once a minute"
    assert got["timer inside five minutes"]["log"] == [timer]
    assert got["timer after five minutes"]["log"] == [timer, "ask row"], "the timer reads the row, not Stripe"
    assert got["lapsed while away"] == {"log": [timer, "ask stripe", "reload"], "hash": "#paywall"}
    assert got["lapsed on an open page"] == {"log": [timer, "ask stripe", "reload"], "hash": "#record"}
    assert got["walled, paid elsewhere"] == {"log": [timer, "ask stripe", "reload"], "hash": "#recommended"}, \
        "a walled tab that comes back entitled stays on the plans"
    assert got["walled, still walled"]["log"] == [timer, "ask stripe"]
    assert got["a static copy"]["log"] == [timer], "a static copy has no server to ask"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
