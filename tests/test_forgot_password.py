"""Sign-up asks for the password twice, and a forgotten one can be replaced.

Ethan, 2026-10-11: "in the create account area, you should have to be able
to put in your password twice, so you confirm that you're putting in the
right password ... And then also add an option for forget a password. Like,
after you create your account, or you're trying to log in, there's no
option for if you forget your password, you can't get it back."

These check, one rule each: a reset link is stored only as a hash and works
once, for an hour; a weak new password does not spend it; using it ends
every session and every other link, and forgives the lockout; an address
gets at most three links an hour; an unknown address gets nothing and the
browser is told the same thing either way; changing the password or
deleting the account kills outstanding links; the link points at the
site's own address in the fragment, never at a request's Host header; the
email carries the link in both parts; the server answers known and unknown
addresses identically, signs the reset browser in, refuses a reused link,
and says when mail is off; the page asks for the password twice, offers
"Forgot password?" on sign-in, sign-up and the account settings, and takes
the token out of the address bar.

Tests never touch the network: the one server here is on loopback with its
own throwaway accounts file, and the mail relay is a stand-in.

Run directly: `python3 tests/test_forgot_password.py`
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_DIR = tempfile.mkdtemp()
os.environ["QB_ACCOUNTS_DB"] = os.path.join(_DIR, "accounts.db")
os.environ["QB_SITE_URL"] = "https://qellysbook.example"
for _k in ("QB_SMTP_HOST", "QB_SMTP_USER", "QB_SMTP_PASS", "QB_MAIL_FROM"):
    os.environ.pop(_k, None)

from engine import accounts as A                                    # noqa: E402

GOOD = "correct horse battery"
NEW = "a brand new passphrase"
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
SERVER = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()


def _db():
    c = A.connect(os.path.join(tempfile.mkdtemp(), "a.db"))
    _, who = A.create_user(c, "fan@example.com", GOOD, confirmed=True)
    return c, who["id"]


def test_the_link_is_stored_only_as_a_hash_and_works_once():
    c, uid = _db()
    token = A.start_reset(c, "  FAN@example.com ")
    assert token and len(token) >= 40
    rows = [tuple(r) for r in c.execute("SELECT * FROM password_resets")]
    assert len(rows) == 1 and token not in repr(rows), "the raw token is never on disk"
    assert A.finish_reset(c, token, NEW) == (200, {"id": uid, "email": "fan@example.com"})
    code, out = A.finish_reset(c, token, "another new passphrase")
    assert code == 400 and out["error"] == A.RESET_EXPIRED, "a second use is refused"
    assert A.authenticate(c, "fan@example.com", NEW)[0] == 200
    assert A.authenticate(c, "fan@example.com", GOOD)[0] == 403


def test_an_hour_old_link_is_dead():
    c, _ = _db()
    token = A.start_reset(c, "fan@example.com")
    c.execute("UPDATE password_resets SET expires_at = ?", (time.time() - 1,))
    c.commit()
    assert A.finish_reset(c, token, NEW)[0] == 400
    assert A.RESET_TTL == 3600
    assert A.finish_reset(c, "made-up", NEW)[0] == 400 and A.finish_reset(c, "", NEW)[0] == 400


def test_a_weak_new_password_does_not_spend_the_link():
    c, _ = _db()
    token = A.start_reset(c, "fan@example.com")
    code, out = A.finish_reset(c, token, "short")
    assert code == 400 and "10 characters" in out["error"]
    assert A.finish_reset(c, token, NEW)[0] == 200, "they can try a better password on the same link"


def test_using_it_ends_every_session_and_every_other_link_and_the_lockout():
    c, uid = _db()
    session = A.start_session(c, uid)
    first, second = A.start_reset(c, "fan@example.com"), A.start_reset(c, "fan@example.com")
    for _ in range(A.MAX_FAILS):
        A.authenticate(c, "fan@example.com", "wrong guess here", where="10.0.0")
    assert A.authenticate(c, "fan@example.com", GOOD, where="10.0.0")[0] == 429
    assert A.finish_reset(c, second, NEW)[0] == 200
    assert A.session_user(c, session) is None, "the old password may be why they are here"
    assert A.finish_reset(c, first, "yet another passphrase")[0] == 400, "the other link died too"
    assert A.authenticate(c, "fan@example.com", NEW, where="10.0.0")[0] == 200, \
        "the owner just proved the address; the lockout is forgiven"


def test_three_links_an_hour_and_nothing_for_a_stranger():
    c, _ = _db()
    got = [A.start_reset(c, "fan@example.com") for _ in range(A.RESET_PER_HOUR + 1)]
    assert all(got[:A.RESET_PER_HOUR]) and got[-1] is None
    assert A.start_reset(c, "nobody@example.com") is None
    assert A.start_reset(c, "not an address") is None


def test_changing_the_password_or_deleting_the_account_kills_the_links():
    c, uid = _db()
    token = A.start_reset(c, "fan@example.com")
    assert A.change_password(c, uid, GOOD, NEW)[0] == 200
    assert A.finish_reset(c, token, "yet another passphrase")[0] == 400
    A.start_reset(c, "fan@example.com")
    A.delete_user(c, uid)
    assert c.execute("SELECT COUNT(*) FROM password_resets").fetchone()[0] == 0


def test_the_link_is_the_sites_own_address_in_the_fragment():
    assert A.reset_link("TOK") == "https://qellysbook.example/#reset/TOK"
    saved = os.environ.pop("QB_SITE_URL")
    os.environ["QB_SITE_URL"] = ""
    try:
        assert A.reset_link("TOK") == "https://qellysbook.com/#reset/TOK"
    finally:
        os.environ["QB_SITE_URL"] = saved
    i = SERVER.index("def _send_reset(")
    body = SERVER[i:SERVER.index("\ndef ", i + 1)]
    assert "A.reset_link(token)" in body and "Host" not in body, \
        "never built from the request: a forged Host header would mail the token to the attacker"


def test_the_email_carries_the_link_in_both_parts():
    subject, text, html = A.reset_message('https://x.example/#reset/a"b<')
    assert "password" in subject.lower()
    assert 'https://x.example/#reset/a"b<' in text and "within the hour" in text
    assert "https://x.example/#reset/a&quot;b&lt;" in html and '"b<' not in html
    assert "ignore this email" in text


def test_the_background_sender_mails_a_real_address_and_nobody_else():
    import server
    from engine import mailer
    assert str(A.DB_PATH) == os.environ["QB_ACCOUNTS_DB"], "this file's own throwaway accounts"
    sent = []
    real_send = mailer.send
    mailer.send = lambda to, subject, text, html="": sent.append((to, text))
    try:
        A.create_user(A.connect(), "member@example.com", GOOD, confirmed=True)
        server._send_reset("member@example.com")
        server._send_reset("stranger@example.com")
    finally:
        mailer.send = real_send
    assert [to for to, _ in sent] == ["member@example.com"]
    assert "https://qellysbook.example/#reset/" in sent[0][1]


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}"), r.headers.get("Set-Cookie") or ""
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), ""


def test_the_server_answers_every_address_alike_and_signs_the_reset_browser_in():
    db = os.path.join(tempfile.mkdtemp(), "accounts.db")
    port = _free_port()
    env = dict(os.environ, QB_ACCOUNTS_DB=db, QB_PAYWALL="")
    proc = subprocess.Popen([sys.executable, "server.py", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                me = json.loads(urllib.request.urlopen(base + "/api/account/me", timeout=2).read())
                break
            except Exception:                                   # noqa: BLE001
                time.sleep(0.25)
        assert me["reset_by_email"] is False, "no relay configured: the page is told before anyone types"
        assert _post(base, "/api/account/signup", {"email": "fan@example.com", "password": GOOD,
                                                   "confirmed": True})[0] == 200
        known = _post(base, "/api/account/forgot", {"email": "fan@example.com"})
        unknown = _post(base, "/api/account/forgot", {"email": "nobody@example.com"})
        assert known[:2] == unknown[:2] == (200, {"sent": False, "by_email": False,
                                                  "contact": "qellysbook@gmail.com"})
        assert _post(base, "/api/account/forgot", {"email": "nope"})[0] == 400
        c = A.connect(db)
        token = A.start_reset(c, "fan@example.com")
        c.close()
        code, body, cookie = _post(base, "/api/account/reset", {"token": token, "password": NEW})
        assert code == 200 and body == {"signed_in": True, "email": "fan@example.com"}
        assert "HttpOnly" in cookie and token not in json.dumps(body), "signed in by cookie, as on sign-in"
        code, body, _ = _post(base, "/api/account/reset", {"token": token, "password": NEW})
        assert code == 400 and "expired" in body["error"]
        assert _post(base, "/api/account/login", {"email": "fan@example.com", "password": NEW})[0] == 200
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_a_reset_carries_a_password_so_it_is_refused_over_cleartext():
    j = SERVER.index("PASSWORD_PATHS = ")
    assert '"reset"' in SERVER[j:j + 120]
    i = SERVER.index("def _forgot_password(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert "threading.Thread(target=_send_reset" in body, \
        "the lookup and the send happen after the reply, so the clock tells a prober nothing"


def test_sign_up_asks_for_the_password_twice():
    i = APP.index("function acctFieldsHTML(mode)")
    fields = APP[i:APP.index("\n}\n", i)]
    assert 'acctPwHTML("acct-pw2"' in fields and fields.count('"new-password"') == 2
    j = APP.index("window.acctAuth = async function")
    auth = APP[j:j + 1800]
    assert "acctPwMismatch(card)" in auth and auth.index("acctPwMismatch(card)") < auth.index("fetch(")
    assert "acctPwMatch:" in APP, "leaving a box says at once if the two differ"


def test_forgot_password_is_offered_wherever_someone_gets_stuck():
    i = APP.index("function acctFieldsHTML(mode)")
    assert 'data-act="acctGoForgot"' in APP[i:APP.index("\n}\n", i)], "the sign-in form"
    k = APP.index("function signupHTML()")
    assert 'data-act="acctGoForgot"' in APP[k:APP.index("\n}\n", k)], "the sign-up page"
    assert "Email me a reset link</button>" in APP, "the signed-in account settings"
    for name in ("acctGoForgot:", "acctForgotSend:", "acctResetSave:"):
        assert name in APP


def test_the_token_leaves_the_address_bar_and_the_page_is_open_behind_the_wall():
    assert APP.count('if (h.startsWith("reset/")) { openReset(') == 2, "cold load and hash change"
    i = APP.index("function openReset(token)")
    assert 'switchView("reset")' in APP[i:i + 300]
    assert '"reset"' in APP[APP.index("const WALL_OPEN = ["):APP.index("];", APP.index("const WALL_OPEN = ["))]
    assert '"reset"' in APP[APP.index("const VIEW_ORDER = ["):APP.index("];", APP.index("const VIEW_ORDER = ["))]
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    assert 'id="view-reset"' in html


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
