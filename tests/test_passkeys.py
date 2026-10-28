"""Passkeys: sign in with Face ID, Touch ID or a phone's own lock (WebAuthn)
(docs/IDEAS.md, the way in and the way up's eighth; built 2026-10-28,
runbook GA).

What these hold:

  * adding one takes a signed-in account and the browser's record of the
    ceremony: our challenge (once, unexpired, this account's), our origin,
    our site's id hashed, and the person present AND verified; the key is
    kept only when it is one we can check (ES256 on its curve, RS256 of
    2048 bits or more); one passkey is one account's, ten to an account;
  * signing in checks the signature over the authenticator's data and the
    record's hash with the kept key, the handle the passkey carries, and a
    count that moved on (a device that keeps none says 0, and may); a
    replayed answer, another site's, a tampered one, another key on the
    same id and a removed passkey sign nobody in;
  * the P-256 and RSA checks, plain Python because the box installs no
    crypto package, agree with a real crypto library both ways;
  * the server takes the site's id from its own name and the origin from
    the browser, refuses another site, a number address and plain http
    off localhost, signs the browser in by cookie as a password does, and
    counts the ceremonies in the sign-in allowance;
  * deleting an account takes its passkeys; the policy names the tables;
  * in Chromium with a virtual authenticator, Settings adds one and the
    sign-in card signs in with it (QB_BROWSER_TESTS=1).

Run directly: `python3 tests/test_passkeys.py`
"""
import hashlib
import json
import os
import random
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import accounts as A    # noqa: E402
from engine import passkeys as PK   # noqa: E402

RP = "qellysbook.example"
ORIGIN = "https://qellysbook.example"
NOW = 1_800_000_000.0
PASSWORD = "correct-horse-battery"


# --- a passkey authenticator, in plain Python ---------------------------------------------
def _cb(v) -> bytes:
    """The CBOR an authenticator writes (what engine.passkeys.cbor reads)."""
    def head(major, n):
        if n < 24:
            return bytes([major << 5 | n])
        for info, size in ((24, 1), (25, 2), (26, 4), (27, 8)):
            if n < 1 << (8 * size):
                return bytes([major << 5 | info]) + n.to_bytes(size, "big")
        raise ValueError(n)
    if isinstance(v, bool):
        return bytes([0xF5 if v else 0xF4])
    if isinstance(v, int):
        return head(0, v) if v >= 0 else head(1, -1 - v)
    if isinstance(v, bytes):
        return head(2, len(v)) + v
    if isinstance(v, str):
        return head(3, len(v.encode())) + v.encode()
    if isinstance(v, list):
        return head(4, len(v)) + b"".join(_cb(x) for x in v)
    if isinstance(v, dict):
        return head(5, len(v)) + b"".join(_cb(k) + _cb(x) for k, x in v.items())
    raise TypeError(v)


def _der(r: int, s: int) -> bytes:
    def i(x):
        b = x.to_bytes((x.bit_length() + 8) // 8, "big")
        return b"\x02" + bytes([len(b)]) + b
    body = i(r) + i(s)
    return b"\x30" + bytes([len(body)]) + body


_SMALL = [p for p in range(3, 2000, 2) if all(p % q for q in range(3, int(p ** 0.5) + 1, 2))]


def _prime(rng, bits):
    while True:
        c = rng.getrandbits(bits) | (3 << (bits - 2)) | 1
        if any(c % p == 0 for p in _SMALL):
            continue
        d, r = c - 1, 0
        while d % 2 == 0:
            d, r = d // 2, r + 1
        for _ in range(16):
            x = pow(rng.randrange(2, c - 1), d, c)
            if x in (1, c - 1):
                continue
            for _ in range(r - 1):
                x = pow(x, 2, c)
                if x == c - 1:
                    break
            else:
                break
        else:
            return c


def _rsa(rng, bits=2048):
    e = 65537
    while True:
        p, q = _prime(rng, bits // 2), _prime(rng, bits // 2)
        phi = (p - 1) * (q - 1)
        if p != q and phi % e:
            return p * q, e, pow(e, -1, phi)


class Device:
    """A passkey on a phone: a key (P-256, or RSA), the id it was given, the
    handle it carries for its account, and the count it keeps (or not)."""

    def __init__(self, alg="ES256", counts=True, seed=1):
        self.rng = random.Random(seed)
        self.cred = bytes(self.rng.getrandbits(8) for _ in range(32))
        self.alg, self.counts, self.count, self.handle = alg, counts, 0, ""
        if alg == "ES256":
            self.d = self.rng.randrange(1, PK.N)
            self.Q = PK.mul(self.d, PK.G)
        else:
            self.n, self.e, self.dd = _rsa(self.rng)

    def cose(self):
        if self.alg == "ES256":
            return {1: 2, 3: -7, -1: 1, -2: self.Q[0].to_bytes(32, "big"), -3: self.Q[1].to_bytes(32, "big")}
        return {1: 3, 3: -257, -1: self.n.to_bytes(256, "big"), -2: self.e.to_bytes(3, "big")}

    def auth(self, rp, flags, attested=False):
        if self.counts:
            self.count += 1
        ad = hashlib.sha256(rp.encode()).digest() + bytes([flags | (0x40 if attested else 0)]) \
            + self.count.to_bytes(4, "big")
        if attested:
            ad += bytes(16) + len(self.cred).to_bytes(2, "big") + self.cred + _cb(self.cose())
        return ad

    def sign(self, msg: bytes) -> bytes:
        if self.alg == "ES256":
            z = int.from_bytes(hashlib.sha256(msg).digest(), "big")
            while True:
                k = self.rng.randrange(1, PK.N)
                r = PK.mul(k, PK.G)[0] % PK.N
                s = pow(k, -1, PK.N) * (z + r * self.d) % PK.N
                if r and s:
                    return _der(r, s)
        em = (b"\x00\x01" + b"\xff" * (256 - 3 - 19 - 32) + b"\x00"
              + bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(msg).digest())
        return pow(int.from_bytes(em, "big"), self.dd, self.n).to_bytes(256, "big")

    def create(self, opts, origin=ORIGIN, rp=None, flags=0x05, kind="webauthn.create", challenge=None):
        """navigator.credentials.create's answer to the server's options."""
        self.handle = opts["user"]["id"]
        cd = json.dumps({"type": kind, "challenge": challenge or opts["challenge"], "origin": origin,
                         "crossOrigin": False}).encode()
        att = _cb({"fmt": "none", "attStmt": {}, "authData": self.auth(rp or opts["rp"]["id"], flags, True)})
        return {"clientDataJSON": PK.b64u(cd), "attestationObject": PK.b64u(att), "name": "Test phone"}

    def get(self, opts, origin=ORIGIN, rp=None, flags=0x05, kind="webauthn.get"):
        """navigator.credentials.get's answer: the signed assertion."""
        cd = json.dumps({"type": kind, "challenge": opts["challenge"], "origin": origin}).encode()
        ad = self.auth(rp or opts["rpId"], flags)
        sig = self.sign(ad + hashlib.sha256(cd).digest())
        return {"id": PK.b64u(self.cred), "rawId": PK.b64u(self.cred), "clientDataJSON": PK.b64u(cd),
                "authenticatorData": PK.b64u(ad), "signature": PK.b64u(sig), "userHandle": self.handle}


def _db():
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    ids = []
    for who in ("fan", "other"):
        _, out = A.create_user(conn, f"{who}@example.com", PASSWORD, confirmed=True)
        ids.append(out["id"])
    PK.ensure_tables(conn)
    return conn, ids


def _refused(fn, *a, said=""):
    try:
        fn(*a)
    except PK.PasskeyError as exc:
        assert said in str(exc), (said, str(exc))
        return str(exc)
    raise AssertionError(f"{fn.__name__} took what it should have refused ({said})")


def _add(conn, uid, dev, now=NOW):
    return PK.register(conn, uid, dev.create(PK.register_options(conn, uid, "x@example.com", RP, now=now)),
                       RP, ORIGIN, now=now)


# --- the engine ----------------------------------------------------------------------------
def test_a_passkey_is_added_and_signs_in():
    conn, (fan, other) = _db()
    dev = Device()
    opts = PK.register_options(conn, fan, "fan@example.com", RP, now=NOW)
    assert opts["rp"]["id"] == RP and opts["attestation"] == "none"
    assert opts["authenticatorSelection"] == {"residentKey": "required", "requireResidentKey": True,
                                              "userVerification": "required"}
    assert opts["user"]["id"] != str(fan) and len(PK.unb64u(opts["user"]["id"], 64)) == 16, "a random handle"
    got = PK.register(conn, fan, dev.create(opts), RP, ORIGIN, now=NOW + 5)
    assert got == {"id": PK.b64u(dev.cred), "name": "Test phone"}
    assert [(k["id"], k["made"], k["used"]) for k in PK.mine(conn, fan)] == [(got["id"], NOW + 5, None)]
    lo = PK.login_options(conn, RP, now=NOW + 10)
    assert lo["rpId"] == RP and lo["allowCredentials"] == [] and lo["userVerification"] == "required"
    assert PK.login(conn, dev.get(lo), RP, ORIGIN, now=NOW + 12) == fan
    assert PK.mine(conn, fan)[0]["used"] == NOW + 12
    again = PK.register_options(conn, fan, "fan@example.com", RP, now=NOW + 20)
    assert again["user"]["id"] == opts["user"]["id"], "the same handle every time"
    assert again["excludeCredentials"] == [{"type": "public-key", "id": got["id"]}], "a device asked twice says so"
    assert PK.mine(conn, other) == []


def test_each_answer_is_checked_before_a_key_is_kept():
    conn, (fan, other) = _db()
    dev = Device()
    o = lambda: PK.register_options(conn, fan, "fan@example.com", RP, now=NOW)  # noqa: E731
    _refused(PK.register, conn, fan, dev.create(o(), origin="https://evil.example"), RP, ORIGIN, NOW,
             said="made for another site")
    _refused(PK.register, conn, fan, dev.create(o(), kind="webauthn.get"), RP, ORIGIN, NOW, said="something else")
    framed = dev.create(o())
    cd = json.loads(PK.unb64u(framed["clientDataJSON"], 4096))
    framed["clientDataJSON"] = PK.b64u(json.dumps({**cd, "crossOrigin": True}).encode())
    _refused(PK.register, conn, fan, framed, RP, ORIGIN, NOW, said="inside another site")
    _refused(PK.register, conn, fan, dev.create(o(), rp="evil.example"), RP, ORIGIN, NOW, said="belongs to another site")
    _refused(PK.register, conn, fan, dev.create(o(), flags=0x01), RP, ORIGIN, NOW, said="check it was you")
    _refused(PK.register, conn, fan, dev.create(o(), challenge=PK.b64u(b"x" * 32)), RP, ORIGIN, NOW, said="ran out")
    stale = o()
    _refused(PK.register, conn, fan, dev.create(stale), RP, ORIGIN, NOW + PK.CHALLENGE_S + 1, said="ran out")
    theirs = PK.register_options(conn, other, "other@example.com", RP, now=NOW)
    _refused(PK.register, conn, fan, dev.create(theirs), RP, ORIGIN, NOW, said="ran out")
    ok = dev.create(o())
    PK.register(conn, fan, ok, RP, ORIGIN, now=NOW)
    _refused(PK.register, conn, fan, ok, RP, ORIGIN, NOW, said="ran out")
    twin = Device(seed=1)                       # the same credential id, offered to another account
    _refused(PK.register, conn, other, twin.create(PK.register_options(conn, other, "o", RP, now=NOW)),
             RP, ORIGIN, NOW, said="already on an account")
    assert len(PK.mine(conn, fan)) == 1 and PK.mine(conn, other) == []


def test_only_a_key_this_site_can_check_is_kept():
    _refused(PK.key_of, {1: 2, 3: -7, -1: 1, -2: (1).to_bytes(32, "big"), -3: (2).to_bytes(32, "big")},
             said="not on its curve")
    _refused(PK.key_of, {1: 3, 3: -257, -1: (2 ** 1023 + 1).to_bytes(128, "big"), -2: (65537).to_bytes(3, "big")},
             said="too weak")
    _refused(PK.key_of, {1: 1, 3: -8, -1: 6, -2: bytes(32)}, said="isn't one this site can check")
    for bad in (b"\xa1", b"\x81" * 10 + b"\x00", b"\x5a\xff\xff\xff\xff", b"\x1c", b"\x62\xff\xfe"):
        _refused(PK.cbor, bad, said="not readable")
    for bad in ("", "a" * 30_000, "has spaces", "plus+slash/"):
        _refused(PK.unb64u, bad or "!", 4096, said="not readable")


def test_signing_in_checks_the_signature_the_handle_and_the_count():
    conn, (fan, other) = _db()
    dev = Device()
    _add(conn, fan, dev)
    lo = lambda: PK.login_options(conn, RP, now=NOW)  # noqa: E731
    ans = dev.get(lo())
    assert PK.login(conn, ans, RP, ORIGIN, now=NOW) == fan
    _refused(PK.login, conn, ans, RP, ORIGIN, NOW, said="ran out")
    _refused(PK.login, conn, dev.get(lo()), RP, ORIGIN, NOW + PK.CHALLENGE_S + 1, said="ran out")
    _refused(PK.login, conn, dev.get(lo(), origin="https://evil.example"), RP, ORIGIN, NOW, said="another site")
    _refused(PK.login, conn, dev.get(lo(), rp="evil.example"), RP, ORIGIN, NOW, said="another site")
    _refused(PK.login, conn, dev.get(lo(), flags=0x01), RP, ORIGIN, NOW, said="check it was you")
    _refused(PK.login, conn, dev.get(lo(), kind="webauthn.create"), RP, ORIGIN, NOW, said="something else")
    bad = dev.get(lo())
    sig = bytearray(PK.unb64u(bad["signature"], 1024))
    sig[-1] ^= 1
    bad["signature"] = PK.b64u(bytes(sig))
    _refused(PK.login, conn, bad, RP, ORIGIN, NOW, said="signature")
    thief = Device(seed=99)                     # the passkey's id and handle, another key
    thief.cred, thief.handle = dev.cred, dev.handle
    _refused(PK.login, conn, thief.get(lo()), RP, ORIGIN, NOW, said="signature")
    wrong = dev.get(lo())
    wrong["userHandle"] = PK.b64u(b"someone else's")
    _refused(PK.login, conn, wrong, RP, ORIGIN, NOW, said="isn't one this site knows")
    dev.count = 0                               # a count gone back: a copied key
    _refused(PK.login, conn, dev.get(lo()), RP, ORIGIN, NOW, said="copied")
    synced = Device(seed=5, counts=False)       # Apple's and Google's synced passkeys say 0 every time
    _add(conn, other, synced)
    for _ in range(2):
        assert PK.login(conn, synced.get(lo()), RP, ORIGIN, now=NOW) == other
    assert PK.remove(conn, other, PK.b64u(dev.cred)) is False, "only the account's own"
    assert PK.remove(conn, fan, PK.b64u(dev.cred)) is True
    dev.count = 50
    _refused(PK.login, conn, dev.get(lo()), RP, ORIGIN, NOW, said="isn't one this site knows")


def test_an_rsa_passkey_and_ten_to_an_account():
    conn, (fan, other) = _db()
    rsa = Device(alg="RS256", seed=3)
    _add(conn, fan, rsa)
    assert PK.login(conn, rsa.get(PK.login_options(conn, RP, now=NOW)), RP, ORIGIN, now=NOW) == fan
    for i in range(PK.MAX_PER_ACCOUNT - 1):
        _add(conn, fan, Device(seed=100 + i))
    assert len(PK.mine(conn, fan)) == PK.MAX_PER_ACCOUNT
    _refused(PK.register_options, conn, fan, "f", RP, NOW, said="Remove one to add another")


def test_the_plain_python_checks_agree_with_a_crypto_library():
    msg = b"the authenticator's data and the hash of the browser's record"
    dev = Device(seed=7)
    sig = dev.sign(msg)
    assert PK.es256_ok(dev.Q, msg, sig) and not PK.es256_ok(dev.Q, msg + b"!", sig)
    assert not PK.es256_ok(dev.Q, msg, sig[:-1] + bytes([sig[-1] ^ 1]))
    rsa = Device(alg="RS256", seed=21)
    rs = rsa.sign(msg)
    assert PK.rs256_ok((rsa.n, rsa.e), msg, rs) and not PK.rs256_ok((rsa.n, rsa.e), msg + b"!", rs)
    plus_n = int.from_bytes(rs, "big") + rsa.n  # the same signature plus the modulus: not one (RFC 8017)
    assert plus_n < 1 << 2048 and pow(plus_n, rsa.e, rsa.n) == pow(int.from_bytes(rs, "big"), rsa.e, rsa.n)
    assert not PK.rs256_ok((rsa.n, rsa.e), msg, plus_n.to_bytes(256, "big"))
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, padding
        from cryptography.hazmat.primitives.asymmetric import rsa as rsa_lib
    except ImportError:
        print("      (cross-check skipped: no cryptography package)")
        return
    key = ec.generate_private_key(ec.SECP256R1())
    nums = key.public_key().public_numbers()
    lib_sig = key.sign(msg, ec.ECDSA(hashes.SHA256()))
    assert PK.es256_ok((nums.x, nums.y), msg, lib_sig), "the library's P-256 signature checks here"
    assert not PK.es256_ok((nums.x, nums.y), msg + b"!", lib_sig)
    pub = ec.EllipticCurvePublicNumbers(dev.Q[0], dev.Q[1], ec.SECP256R1()).public_key()
    pub.verify(sig, msg, ec.ECDSA(hashes.SHA256()))          # and ours checks there (raises if not)
    rk = rsa_lib.generate_private_key(public_exponent=65537, key_size=2048)
    rn = rk.public_key().public_numbers()
    lib_rs = rk.sign(msg, padding.PKCS1v15(), hashes.SHA256())
    assert PK.rs256_ok((rn.n, rn.e), msg, lib_rs) and not PK.rs256_ok((rn.n, rn.e), msg + b"!", lib_rs)


def test_deleting_an_account_takes_its_passkeys_and_the_policy_names_them():
    conn, (fan, other) = _db()
    dev = Device()
    _add(conn, fan, dev)
    _add(conn, other, Device(seed=2))
    assert A.export_user(conn, fan)["passkeys"][0]["name"] == "Test phone"
    assert "pubkey" not in json.dumps(A.export_user(conn, fan)), "the key is for checking, not data"
    A.delete_user(conn, fan)
    for table in ("passkeys", "passkey_users"):
        assert not conn.execute(f"SELECT 1 FROM {table} WHERE user_id=?", (fan,)).fetchone(), table
    assert len(PK.mine(conn, other)) == 1, "nobody else's"
    _refused(PK.login, conn, dev.get(PK.login_options(conn, RP, now=NOW)), RP, ORIGIN, NOW,
             said="isn't one this site knows")
    policy = (ROOT / "web" / "privacy.html").read_text(encoding="utf-8")
    for table in ("passkeys", "passkey_users", "passkey_challenges"):
        assert f"<code>{table}</code>" in policy, table


# --- the server ----------------------------------------------------------------------------
def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _req(base, path, body=None, headers=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}"), r.headers.get("Set-Cookie") or ""
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), ""


def _start(db, port):
    env = {k: v for k, v in os.environ.items() if k not in ("QB_PASSKEY_RP_ID", "QB_SITE_URL")}
    env.update(QB_ACCOUNTS_DB=db, QB_PAYWALL="")
    proc = subprocess.Popen([sys.executable, "server.py", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(160):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/account/me", timeout=2).read()
            return proc
        except Exception:                                       # noqa: BLE001
            time.sleep(0.25)
    proc.terminate()
    raise AssertionError("the server did not come up")


def test_the_server_runs_the_ceremonies_and_signs_the_browser_in():
    db = os.path.join(tempfile.mkdtemp(), "accounts.db")
    port = _free_port()
    proc = _start(db, port)
    base = f"http://127.0.0.1:{port}"
    site = {"Host": f"localhost:{port}", "Origin": f"http://localhost:{port}"}
    origin = site["Origin"]
    try:
        code, _b, cookie = _req(base, "/api/account/signup", {"email": "fan@example.com", "password": PASSWORD,
                                                              "confirmed": True})
        assert code == 200
        me = {**site, "Cookie": cookie.split(";")[0]}
        assert _req(base, "/api/passkey/register-options", {}, site)[0] == 401, "an account first"
        assert _req(base, "/api/passkey/list", None, site)[0] == 401
        for bad in ({"Host": f"localhost:{port}", "Origin": "https://evil.example"},
                    {"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}"},
                    {"Host": f"fan.example:{port}", "Origin": f"http://fan.example:{port}"},
                    {"Host": f"localhost:{port}"}):
            code, body, _c = _req(base, "/api/passkey/login-options", {}, bad)
            assert code == 400 and "over https" in body["error"], (bad, code, body)
        code, opts, _c = _req(base, "/api/passkey/register-options", {}, me)
        assert code == 200 and opts["rp"]["id"] == "localhost" and opts["user"]["name"] == "fan@example.com", opts
        dev = Device(seed=11)
        code, out, _c = _req(base, "/api/passkey/register", dev.create(opts, origin=origin), me)
        assert code == 200 and [k["name"] for k in out["passkeys"]] == ["Test phone"], out
        assert [k["name"] for k in _req(base, "/api/passkey/list", None, me)[1]["passkeys"]] == ["Test phone"]
        assert _req(base, "/api/account/logout", {}, me)[0] == 200
        code, lo, _c = _req(base, "/api/passkey/login-options", {}, site)
        assert code == 200 and lo["rpId"] == "localhost"
        code, body, cookie = _req(base, "/api/passkey/login", dev.get(lo, origin=origin), site)
        assert code == 200 and body == {"signed_in": True, "email": "fan@example.com"}, body
        assert "HttpOnly" in cookie and "qb_session=" in cookie, "signed in by cookie, as a password does"
        back = {**site, "Cookie": cookie.split(";")[0]}
        assert _req(base, "/api/account/me", None, back)[1]["signed_in"] is True
        code, body, _c = _req(base, "/api/passkey/login", dev.get(lo, origin=origin), site)
        assert code == 400 and "ran out" in body["error"], "an answer works once"
        gone = _req(base, "/api/passkey/remove", {"id": PK.b64u(dev.cred)}, back)
        assert gone[0] == 200 and gone[1]["passkeys"] == []
        lo = _req(base, "/api/passkey/login-options", {}, site)[1]
        code, body, _c = _req(base, "/api/passkey/login", dev.get(lo, origin=origin), site)
        assert code == 400 and "isn't one this site knows" in body["error"], body
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_the_ceremonies_count_against_the_sign_in_allowance():
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert 'auth = parsed.path.startswith(("/api/account/", "/api/passkey/"))' in src
    i = src.index("    def _passkey_site(self):")
    site = src[i:src.index("\n    def ", i + 10)]
    assert 'self.headers.get("Origin")' in site and "ipaddress.ip_address(" in site
    assert 'u.scheme == "http" and host == "localhost"' in site, "plain http only for localhost"


# --- the page --------------------------------------------------------------------------------
def test_the_page_offers_them_where_the_browser_can():
    acct = (ROOT / "web" / "js" / "account.js").read_text(encoding="utf-8")
    assert "${pkDoorHTML()}\n    ${phoneDoorHTML(\"login\")}" in acct, "the sign-in card"
    assert "...(pkOK() ? [setItem({ ico: \"shield\", tone: \"gold\", title: \"Passkeys\"" in acct, "Settings › Account"
    i = acct.index("const pkOK = () =>")
    ok = acct[i:acct.index(";\n", i)]
    assert "window.PublicKeyCredential" in ok and "isNativePlatform" in ok, "not in the iPhone app's web view yet"
    assert 'if (page === "passkeys") {' in acct
    # Safari opens the prompt only close behind the tap: the options are
    # fetched as the screen draws, and the tap goes straight to the device.
    assert 'setTimeout(() => pkPrefetch("login"), 0);' in acct and 'pkPrefetch("register");' in acct
    for fn in ("pkAdd", "pkSignIn"):
        i = acct.index(f"async function {fn}(")
        body = acct[i:acct.index("\n}\n", i)]
        assert "await pkOptions(" in body and "-options\")" not in body, fn


def test_in_a_browser_settings_adds_one_and_the_sign_in_card_uses_it():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    db = os.path.join(tempfile.mkdtemp(), "accounts.db")
    port = _free_port()
    proc = _start(db, port)
    base = f"http://localhost:{port}"          # a site's id cannot be a number address
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            b = pw.chromium.launch(**kw)
            try:
                ctx = b.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
                p = ctx.new_page()
                errs = []
                p.on("pageerror", lambda e: errs.append(str(e)))
                cdp = ctx.new_cdp_session(p)
                cdp.send("WebAuthn.enable")
                auth = cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {
                    "protocol": "ctap2", "transport": "internal", "hasResidentKey": True,
                    "hasUserVerification": True, "isUserVerified": True, "automaticPresenceSimulation": True}})
                p.add_init_script("try { localStorage.setItem('qb_intro_v1', '1'); localStorage.setItem('qb.tour', 'done');"
                                  " localStorage.setItem('qb-seen-intro', '1'); } catch (e) {}")
                p.route(lambda u: not u.startswith(base + "/"), lambda r: r.abort())
                r = ctx.request.post(base + "/api/account/signup", headers={"Content-Type": "application/json"},
                                     data=json.dumps({"email": "fan@example.com", "password": PASSWORD,
                                                      "confirmed": True}))
                assert r.ok, r.text()
                p.goto(base + "/index.html", wait_until="load")
                p.wait_for_function("() => typeof switchView === 'function'", timeout=20000)
                p.evaluate("() => { window._acctTab = 'settings'; window._setOpen = 'passkeys'; switchView('account', true); }")
                p.wait_for_selector('[data-pk="add"]', timeout=20000)
                p.click('[data-pk="add"]')
                p.wait_for_selector(".pk-rm", timeout=20000)
                note = p.locator(".pk-note").inner_text()
                assert "Added" in note, note
                creds = cdp.send("WebAuthn.getCredentials", {"authenticatorId": auth["authenticatorId"]})["credentials"]
                assert len(creds) == 1 and creds[0]["isResidentCredential"] and creds[0]["rpId"] == "localhost", creds
                ctx.request.post(base + "/api/account/logout", headers={"Content-Type": "application/json"}, data="{}")
                p.goto(base + "/index.html#account", wait_until="load")
                p.wait_for_function("() => typeof acctGoLogin === 'function'", timeout=20000)
                p.evaluate("() => acctGoLogin()")
                p.wait_for_selector('[data-pk="signin"]', timeout=20000)
                assert ctx.request.get(base + "/api/account/me").json()["signed_in"] is False, "signed out first"
                p.click('[data-pk="signin"]')
                p.wait_for_function("""async () => {
                  const r = await fetch('/api/account/me', { credentials: 'same-origin' });
                  return (await r.json()).signed_in === true; }""", timeout=20000, polling=500)
                assert not errs, errs
            finally:
                b.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)


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
