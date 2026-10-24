"""Alerts on the phone: tonight's picks are up, last night is graded.

Ethan, 2026-10-24: "do both from my call" — the native feature the iOS
review asks for (4.2), push alerts when a pick posts or settles, built
without a crypto library: the push is an empty knock signed with VAPID
(P-256 ECDSA, engine/webpush), and the phone's service worker asks the site
what to say (POST /api/push/latest). The iOS shell's phones go through
Apple's push (APNs) with the same signature, by `curl --http2`.

What these hold:
  - the signature is right: RFC 6979's own P-256/SHA-256 vector, key, nonce
    and signature to the digit, and (where the `cryptography` package is
    installed) each side verifies the other's;
  - a push goes only to a real push service, https, port 443 — a look-alike
    host, a port, a password in the URL or plain http is refused, so a
    stranger cannot make the box POST anywhere;
  - the knock carries VAPID, TTL, Urgency and a clean Topic, and no body;
  - the key is made once, kept, readable only by the box's user;
  - Apple's .p8 key is read, and the APNs request is shaped as Apple asks;
  - what is owed: a league's picks once per board date, last night once,
    counts and the public record only — never a pick's name; nothing in
    quiet hours; a refused address is dropped, a flaky one after five tries;
  - the server, the worker, the page, the policy and the Play build carry it.

Run directly: `python3 tests/test_push_alerts.py`
"""
import datetime as dt
import json
import os
import sqlite3
import stat
import sys
import tempfile
import time
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gate, pushalerts as PA, webpush as W  # noqa: E402

READ = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()  # noqa: E731
FCM = "https://fcm.googleapis.com/fcm/send/abc123:APA91bHxyz"


def test_the_signature_is_rfc_6979s_own():
    d = 0xC9AFA9D845BA75166B5C215767B1D6934E50C3DB36E89B127B8A622B120F6721
    pub = W.mul(d)
    assert pub == (0x60FED4BA255A9D31C961EB74C6356D68C049B8923B61FA6CE669622E60F29FB6,
                   0x7903FE1008B8BC99A41AE9E95628BC64F2F1B20C2D7E9F5177A3C294D4462299)
    import hashlib
    assert W._rfc6979_k(d, hashlib.sha256(b"sample").digest()) == \
        0xA6E3C57DD01ABE90086538398355DD4C3B17AA873382B0F24D6129493D8AAD60
    sig = W.sign_plain(d, b"sample")
    assert sig.hex().upper() == ("EFD48B2AACB6A8FD1140DD9CD45E81D69D2C877B56AAF991C34D0EA84EAF3716"
                                 "F7CB1C942D657C41D436C7A1B6E29F65F3E900DBB9AFF4064DC4AB2F843ACDA8")
    assert W.verify(pub, b"sample", sig) and not W.verify(pub, b"samplf", sig)
    assert not W.verify(pub, b"sample", sig[:32] + bytes(32)) and W.on_curve(pub) and not W.on_curve((1, 2))


def test_another_library_agrees_where_one_is_installed():
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature
    except BaseException as exc:                    # noqa: BLE001 — a broken install panics (pyo3), not ImportError
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        print("      (skipped: no working cryptography package — the RFC vector above stands alone)")
        return
    k = W.new_key()
    d = int.from_bytes(W.unb64u(k["d"]), "big")
    theirs = ec.derive_private_key(d, ec.SECP256R1())
    raw = W.unb64u(k["pub"])
    nums = theirs.public_key().public_numbers()
    assert raw == b"\x04" + nums.x.to_bytes(32, "big") + nums.y.to_bytes(32, "big")
    msg = b"header.claims"
    ours = W.sign_plain(d, msg)
    assert W.verify((nums.x, nums.y), msg, W.sign(d, msg)), "the library path signs the same key"
    theirs.public_key().verify(encode_dss_signature(int.from_bytes(ours[:32], "big"), int.from_bytes(ours[32:], "big")),
                               msg, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(theirs.sign(msg, ec.ECDSA(hashes.SHA256())))
    assert W.verify((nums.x, nums.y), msg, r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def test_a_push_goes_only_to_a_real_push_service():
    for ok in (FCM, "https://updates.push.services.mozilla.com/wpush/v2/gAAAA",
               "https://web.push.apple.com/QGuQyavXutnMH", "https://wns2-par02p.notify.windows.com/w/?token=x",
               "https://fcm.googleapis.com:443/fcm/send/x"):
        assert W.endpoint_ok(ok), ok
    for bad in ("http://fcm.googleapis.com/fcm/send/x", "https://fcm.googleapis.com.evil.example/x",
                "https://evil.example/fcm.googleapis.com", "https://notify.windows.com/x",
                "https://fcm.googleapis.com:8443/x", "https://user:pw@fcm.googleapis.com/x",
                "https://127.0.0.1/x", "https://localhost/x", "file:///etc/passwd", "", None,
                "https://fcm.googleapis.com/" + "x" * 1100):
        assert not W.endpoint_ok(bad), bad


def test_the_knock_is_signed_empty_and_tagged():
    k = W.new_key()
    seen = {}

    class Resp:
        status = 201
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def opener(req, timeout):
        seen.update(url=req.full_url, data=req.data, method=req.get_method(), headers=dict(req.header_items()))
        return Resp()
    assert W.knock(FCM, k, topic="posted:nfl:2026-10-24!!", opener=opener) == 201
    h = {key.lower(): v for key, v in seen["headers"].items()}
    assert seen["method"] == "POST" and seen["data"] == b"" and h["content-length"] == "0"
    assert h["ttl"] == str(6 * 3600) and h["urgency"] == "normal" and h["topic"] == "postednfl2026-10-24"
    t, kk = h["authorization"][len("vapid t="):].split(", k=")
    assert kk == k["pub"]
    head, claims, sig = t.split(".")
    c = json.loads(W.unb64u(claims))
    assert json.loads(W.unb64u(head)) == {"typ": "JWT", "alg": "ES256"}
    assert c["aud"] == "https://fcm.googleapis.com" and c["sub"] == "https://qellysbook.com"
    assert 11 * 3600 < c["exp"] - time.time() <= 12 * 3600
    pub = W.unb64u(k["pub"])
    assert W.verify((int.from_bytes(pub[1:33], "big"), int.from_bytes(pub[33:], "big")),
                    f"{head}.{claims}".encode(), W.unb64u(sig))

    def gone(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 410, "Gone", {}, None)
    assert W.knock(FCM, k, opener=gone) == 410
    assert W.knock("https://evil.example/x", k, opener=lambda *a, **kw: 1 / 0) == 0, "never even tried"


def test_the_key_is_made_once_and_kept_private():
    path = os.path.join(tempfile.mkdtemp(), "push", "vapid.json")
    a = W.keys(path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert W.keys(path) == a and len(W.unb64u(a["pub"])) == 65 and W.unb64u(a["pub"])[0] == 4
    import subprocess
    got = subprocess.run(["git", "check-ignore", "-q", "data/push/vapid.json"], cwd=ROOT)
    assert got.returncode == 0, "the private key is one `git add -A` from the repo"


def _p8(d: int) -> str:
    x, y = W.mul(d)
    inner = b"\x02\x01\x01\x04\x20" + d.to_bytes(32, "big") + b"\xa1\x44\x03\x42\x00\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big")
    ecpk = b"\x30" + bytes([len(inner)]) + inner
    algo = bytes.fromhex("301306072a8648ce3d020106082a8648ce3d030107")
    body = b"\x02\x01\x00" + algo + b"\x04" + bytes([len(ecpk)]) + ecpk
    der = b"\x30\x81" + bytes([len(body)]) + body
    import base64
    return "-----BEGIN PRIVATE KEY-----\n" + base64.b64encode(der).decode() + "\n-----END PRIVATE KEY-----\n"


def test_apples_key_is_read_and_the_request_is_shaped_as_apple_asks():
    d = 0x1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCD
    assert W.p8_private(_p8(d)) == d
    try:
        W.p8_private("-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----")
        raise AssertionError("read a key out of nothing")
    except ValueError:
        pass
    path = os.path.join(tempfile.mkdtemp(), "AuthKey.p8")
    open(path, "w").write(_p8(d))
    env = {"QB_APNS_KEY_FILE": path, "QB_APNS_KEY_ID": "ABC123DEFG", "QB_APNS_TEAM_ID": "TEAM123456",
           "QB_APNS_TOPIC": "com.qellysbook.app"}
    cfg = W.apns_config(env)
    assert cfg and cfg["env"] == "production" and W.apns_config({}) is None
    got = {}

    class Out:
        stdout = "200"

    def run(cmd, input, **kw):
        got.update(cmd=cmd, input=input)
        return Out()
    token = "a" * 64
    assert W.apns_send(token, {"title": "Tonight’s NFL picks are up", "body": "6 picks", "url": "/?sport=nfl"}, cfg, run=run) == 200
    cmd = got["cmd"]
    assert cmd[:2] == ["curl", "--http2"] and cmd[-1] == f"https://api.push.apple.com/3/device/{token}"
    heads = [cmd[i + 1] for i, c in enumerate(cmd) if c == "-H"]
    assert "apns-topic: com.qellysbook.app" in heads and "apns-push-type: alert" in heads
    bearer = next(h for h in heads if h.startswith("authorization: bearer "))[len("authorization: bearer "):]
    head, claims, _ = bearer.split(".")
    assert json.loads(W.unb64u(head)) == {"alg": "ES256", "kid": "ABC123DEFG"}
    assert json.loads(W.unb64u(claims))["iss"] == "TEAM123456"
    body = json.loads(got["input"])
    assert body["aps"]["alert"]["title"].startswith("Tonight") and body["url"] == "/?sport=nfl"
    assert W.apns_send("not-hex!", {}, cfg, run=run) == 0 and W.apns_send(token, {}, None, run=run) == 0


def _conn():
    c = sqlite3.connect(":memory:")
    PA.ensure_tables(c)
    return c


def test_a_subscription_is_checked_before_it_is_kept():
    c = _conn()
    assert PA.subscribe(c, "https://evil.example/x")[0] == 400
    assert PA.subscribe(c, FCM, topics=["nonsense"])[0] == 400
    assert PA.subscribe(c, "zz", kind="apns")[0] == 400
    code, out = PA.subscribe(c, FCM, topics=["settled", "posted", "bogus"], leagues=["nfl", "xfl"], user_id=7)
    assert code == 200 and out["topics"] == ["posted", "settled"] and out["leagues"] == ["nfl"]
    assert PA.subscription(c, FCM) == {"topics": ["posted", "settled"], "leagues": ["nfl"]}
    assert PA.subscribe(c, "ab" * 32, kind="apns")[0] == 200
    PA.unsubscribe(c, FCM)
    assert PA.subscription(c, FCM) is None
    assert PA.wants("posted,settled", "nfl", {"kind": "posted", "league": "nfl"})
    assert not PA.wants("posted", "nfl", {"kind": "posted", "league": "nba"})
    assert PA.wants("settled", "nfl", {"kind": "settled", "league": ""}), "last night is every league's"


def _web(today: str, picks: int, recap_date: str | None):
    web = tempfile.mkdtemp()
    os.makedirs(os.path.join(web, "data"))
    rows = [{"player": f"Secret Player {i}", "recommended": True} for i in range(picks)] + [{"player": "Not a pick"}]
    json.dump({"date": today, "recommendations": rows}, open(os.path.join(web, "data", "recommendations.json"), "w"))
    json.dump({"date": "2020-01-01", "recommendations": rows}, open(os.path.join(web, "data", "nba.json"), "w"))
    ev = [{"kind": "settle_recap", "date": recap_date, "w": 7, "l": 3, "p": 1, "net_u": 3.14},
          {"kind": "settle_recap", "date": recap_date, "w": 1, "l": 0, "net_u": 0.5}] if recap_date else []
    json.dump({"events": ev}, open(os.path.join(web, "data", "feed.json"), "w"))
    return web


def test_what_is_owed_is_counts_and_the_record_once_and_never_a_pick():
    real = gate.board_source
    gate.board_source = lambda p: p
    try:
        today = dt.date(2026, 10, 24)
        web = _web(today.isoformat(), 6, "2026-10-23")
        got = PA.due({}, web=web, today=today)
        assert [m["id"] for m in got] == ["posted:nfl:2026-10-24", "settled:2026-10-23"], got
        posted, settled = got
        assert posted["title"] == "This week’s NFL picks are up" and posted["body"].startswith("6 picks")
        assert posted["url"] == "/?sport=nfl#recommended"
        assert settled["title"] == "Last night: 8–3–1, +3.6u" and settled["url"] == "/#record"
        assert "Secret Player" not in json.dumps(got), "a pick's name never reaches a lock screen"
        assert PA.due({"sent": [m["id"] for m in got]}, web=web, today=today) == [], "each once"
        assert [m["id"] for m in PA.due({}, web=_web(today.isoformat(), 0, None), today=today)] == []
    finally:
        gate.board_source = real


def test_quiet_hours_hold_the_night():
    at = lambda h: dt.datetime(2026, 10, 24, h, 30)              # noqa: E731
    assert PA.quiet_now(at(23)) and PA.quiet_now(at(3)) and PA.quiet_now(at(8))
    assert not PA.quiet_now(at(9)) and not PA.quiet_now(at(22))


def test_a_knocked_phone_is_told_its_newest_wanted_line():
    path = os.path.join(tempfile.mkdtemp(), "latest.json")
    now = time.time()
    json.dump({"messages": [
        {"id": "settled:x", "kind": "settled", "league": "", "title": "Last night: 5–2", "body": "b", "url": "/#record", "at": now - 60},
        {"id": "posted:nba:x", "kind": "posted", "league": "nba", "title": "NBA up", "body": "b", "url": "/?sport=nba", "at": now - 30},
        {"id": "posted:nfl:old", "kind": "posted", "league": "nfl", "title": "Old", "body": "b", "url": "/", "at": now - 2 * 86400}]},
        open(path, "w"))
    assert PA.latest_for(None, path, now)["title"] == "NBA up"
    assert PA.latest_for({"topics": ["settled"], "leagues": []}, path, now)["title"] == "Last night: 5–2"
    nfl_only = PA.latest_for({"topics": ["posted"], "leagues": ["nfl"]}, path, now)
    assert nfl_only["title"] == "Qellys Book" and nfl_only["url"] == "/", "a stale line is not today's"


def test_sending_drops_a_refused_address_and_a_flaky_one_after_five():
    c = _conn()
    a, b, z = FCM + "a", FCM + "b", FCM + "z"
    for e in (a, b, z):
        PA.subscribe(c, e)
    PA.subscribe(c, "cd" * 32, kind="apns")
    PA.subscribe(c, FCM + "nba", topics=["posted"], leagues=["nba"])
    codes = {a: 201, b: 410, z: 500}
    knocked = []

    def knock(endpoint, k, topic=""):
        knocked.append((endpoint, topic))
        return codes.get(endpoint, 201)
    msgs = [{"id": "posted:nfl:d", "kind": "posted", "league": "nfl"}, {"id": "settled:d", "kind": "settled", "league": ""}]
    st = PA.send(c, msgs, knock=knock, vapid=W.new_key(), apns_cfg=False)
    assert st == {"sent": 1, "gone": 1, "failed": 1, "skipped_apns": 1}, st
    assert sorted(e for e, _ in knocked) == [a, b, z], "one knock a phone; the NBA-only phone wants neither"
    assert all(t == "settled-d" for _, t in knocked), "the topic is the newest wanted message"
    left = {r[0]: r[1] for r in c.execute("SELECT endpoint, fails FROM push_subs")}
    assert b not in left and left[z] == 1
    for _ in range(PA.MAX_FAILS - 1):
        PA.send(c, msgs, knock=knock, vapid=W.new_key(), apns_cfg=False)
    assert z not in {r[0] for r in c.execute("SELECT endpoint FROM push_subs")}


def test_the_cycle_looks_every_five_minutes_and_records_what_it_said():
    real = gate.board_source
    gate.board_source = lambda p: p
    try:
        d = tempfile.mkdtemp()
        state = os.path.join(d, "state.json")
        web = _web(dt.date.today().isoformat(), 2, None)
        conns = []

        def connect():
            c = _conn()
            PA.subscribe(c, FCM)
            conns.append(c)
            return c
        st = PA.scan_and_send(log=lambda *a: None, connect=connect, state_path=state, web=web, force=True,
                              knock=lambda e, k, topic="": 201, vapid=W.new_key(), apns_cfg=False)
        assert st["messages"] == 1 and st["sent"] == 1
        said = json.load(open(os.path.join(d, "latest.json")))["messages"]
        assert said[0]["id"].startswith("posted:nfl:") and said[0]["at"] > 0
        assert PA.scan_and_send(log=lambda *a: None, connect=connect, state_path=state, web=web) is None, "throttled"
        again = PA.scan_and_send(log=lambda *a: None, connect=connect, state_path=state, web=web, force=True,
                                 knock=lambda *a, **kw: 201, vapid=W.new_key(), apns_cfg=False)
        assert again == {"messages": 0}, "said once"
    finally:
        gate.board_source = real


def test_the_server_the_worker_the_page_the_policy_and_the_play_build_carry_it():
    srv = READ("server.py")
    assert 'if parsed.path.startswith("/api/push/"):' in srv and 'parsed.path in ("/api/push/key", "/api/push/key/")' in srv
    at = srv.index("def _push_post(self, path: str):")
    body = srv[at:srv.index("def _event(self):")]
    assert "RATE_PUSH_PER_MIN" in body and "0 < length <= 4000" in body and "_client_ip" not in body
    maint = READ("engine", "maintenance.py")
    at = maint.index("def run_if_due(")
    assert "_run_push(log)" in maint[at:at + 2500]
    assert "if os.environ.get(modelstate.ENV_VAR):" in maint[maint.index("def _run_push("):][:600]
    sw = READ("web", "sw.js")
    assert 'self.addEventListener("push"' in sw and 'fetch("/api/push/latest"' in sw and 'credentials: "omit"' in sw
    click = sw[sw.index('self.addEventListener("notificationclick"'):]
    assert "u.origin === self.location.origin" in click, "a tap opens this site and nowhere else"
    app = READ("web", "js", "app.js")
    at = app.index("function renderPushZone(note) {")
    page = app[at:app.index("\nfunction renderAlerts() {", at)]
    assert "Add to Home Screen" in page and "never a pick on a lock screen" in page
    assert 'kind: "apns"' in app and "userVisibleOnly: true" in app and "renderPushZone();" in app
    assert "<h3>2.7 Alerts on your phone</h3>" in READ("web", "privacy.html")
    assert json.loads(READ("deploy", "twa", "twa-manifest.json"))["enableNotifications"] is True
    assert '"ab"' not in json.dumps(PA.KINDS) and set(PA.KINDS) == {"posted", "settled"}



def test_in_a_browser_the_worker_shows_an_alert_for_an_empty_knock():
    """The real sw.js, in Chromium, handed an empty push by DevTools (the
    knock a push service delivers). The test server has no /api/push/latest,
    so this is the worst case: the site cannot be asked, and the worker
    must still show something — a push with no notification is one the
    browser punishes."""
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import rendercheck
    srv, port = rendercheck._serve()
    origin = f"http://127.0.0.1:{port}"
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(permissions=["notifications"])
                page = ctx.new_page()
                page.goto(origin + "/index.html", wait_until="load")
                page.evaluate("navigator.serviceWorker.ready.then(() => true)")
                cdp = ctx.new_cdp_session(page)
                regs = []
                cdp.on("ServiceWorker.workerRegistrationUpdated", lambda e: regs.extend(e["registrations"]))
                cdp.send("ServiceWorker.enable")
                page.wait_for_timeout(1500)
                reg = next(r for r in regs if r["scopeURL"].startswith(origin))
                cdp.send("ServiceWorker.deliverPushMessage", {"origin": origin, "registrationId": reg["registrationId"], "data": ""})
                page.wait_for_timeout(2000)
                got = page.evaluate("navigator.serviceWorker.ready.then((r) => r.getNotifications())"
                                    ".then((ns) => ns.map((n) => [n.title, n.body, n.data && n.data.url]))")
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert got == [["Qellys Book", "The board has moved — open it for the latest.", "/"]], got

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
