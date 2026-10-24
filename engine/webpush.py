"""Push to a phone without a crypto library: a signed, empty knock.

Ethan, 2026-10-24: "do both from my call" — the second call being the native
feature the iOS review asks for (guideline 4.2): an alert when a pick posts
or settles. engine/alerts.py wrote this off in 2026-08 because Web Push
"needs P-256 ECDH and AES-GCM, which the standard library does not have".
That is true of a push that CARRIES its words, which must be encrypted to
the browser. It is not true of a push that carries nothing:

    the server signs a request (VAPID: one ES256 signature, P-256 ECDSA),
    the push service wakes the phone's service worker with an empty push,
    the worker asks OUR server what to say (/api/push/latest) and shows it.

ECDSA signing is a page of integer arithmetic, written out below and checked
against RFC 6979's own test vectors (tests/test_push_alerts.py); where the
box has the `cryptography` package, that signs instead (`sign`). Nothing is
encrypted because nothing secret travels: the words come over the site's own
HTTPS, from the same server that would have encrypted them.

The same signature serves Apple's native push for the iOS shell (APNs token
auth is an ES256 JWT too). APNs speaks only HTTP/2, which the standard
library does not, so that one request goes through the box's `curl
--http2`; without curl, or without the Apple key (docs/APP_STORES.md), it
says so and sends nothing.

WHERE A PUSH MAY GO. A subscription is a URL the browser hands us, so a
stranger could hand us any URL and have the box POST to it. Only the real
push services are accepted (PUSH_HOSTS), over https, on port 443.

Standard library only. Keys live in data/push/ (gitignored), mode 0600.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
KEY_PATH = ROOT / "data" / "push" / "vapid.json"
#: Who the push services may contact about our pushes (VAPID `sub`): the
#: site, never a person's address.
SUBJECT = os.environ.get("QB_PUSH_SUBJECT", "").strip() or "https://qellysbook.com"
#: The push services a subscription may point at — Chrome, Android and
#: Samsung (FCM), Firefox, Safari, Edge. Anything else is refused.
PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com")
PUSH_SUFFIXES = (".notify.windows.com", ".push.apple.com")
AGENT = "qellys-book/0.1 (+push)"

# --- P-256 -------------------------------------------------------------------
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
A = P - 3
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
     0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)


def _jac_double(p):
    x, y, z = p
    if not y:
        return (0, 1, 0)
    yy = y * y % P
    s = 4 * x * yy % P
    zz = z * z % P
    m = 3 * (x - zz) * (x + zz) % P            # a = -3
    x3 = (m * m - 2 * s) % P
    return (x3, (m * (s - x3) - 8 * yy * yy) % P, 2 * y * z % P)


def _jac_add(p, q):
    if not p[2]:
        return q
    if not q[2]:
        return p
    z1z1, z2z2 = p[2] * p[2] % P, q[2] * q[2] % P
    u1, u2 = p[0] * z2z2 % P, q[0] * z1z1 % P
    s1, s2 = p[1] * q[2] * z2z2 % P, q[1] * p[2] * z1z1 % P
    if u1 == u2:
        return _jac_double(p) if s1 == s2 else (0, 1, 0)
    h, r = (u2 - u1) % P, (s2 - s1) % P
    hh = h * h % P
    hhh, v = h * hh % P, u1 * hh % P
    x3 = (r * r - hhh - 2 * v) % P
    return (x3, (r * (v - x3) - s1 * hhh) % P, h * p[2] * q[2] % P)


def _affine(p):
    if not p[2]:
        return None
    zi = pow(p[2], -1, P)
    zi2 = zi * zi % P
    return (p[0] * zi2 % P, p[1] * zi2 * zi % P)


def mul(k: int, point=G):
    """k·point on P-256, affine; None at infinity."""
    acc, add = (0, 1, 0), (point[0], point[1], 1)
    while k:
        if k & 1:
            acc = _jac_add(acc, add)
        add = _jac_double(add)
        k >>= 1
    return _affine(acc)


def on_curve(pt) -> bool:
    return bool(pt) and (pt[1] * pt[1] - (pt[0] ** 3 + A * pt[0] + B)) % P == 0


def _rfc6979_k(d: int, digest: bytes) -> int:
    """The deterministic nonce of RFC 6979 §3.2 (HMAC-SHA256): no random
    number is ever needed to sign, so a weak one can never leak the key."""
    x = d.to_bytes(32, "big")
    h = (int.from_bytes(digest, "big") % N).to_bytes(32, "big")
    v, k = b"\x01" * 32, b"\x00" * 32
    k = hmac.new(k, v + b"\x00" + x + h, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    k = hmac.new(k, v + b"\x01" + x + h, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    while True:
        v = hmac.new(k, v, hashlib.sha256).digest()
        cand = int.from_bytes(v, "big")
        if 1 <= cand < N:
            return cand
        k = hmac.new(k, v + b"\x00", hashlib.sha256).digest()
        v = hmac.new(k, v, hashlib.sha256).digest()


def _library_signer():
    """The `cryptography` package's ECDSA where the box has a working one —
    a vetted implementation is preferred to this page whenever it exists.
    None otherwise (a broken install panics rather than failing to import,
    hence the broad catch)."""
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    except BaseException as exc:                              # noqa: BLE001
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return None

    def lib_sign(d: int, message: bytes) -> bytes:
        r, s = decode_dss_signature(ec.derive_private_key(d, ec.SECP256R1()).sign(message, ec.ECDSA(hashes.SHA256())))
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return lib_sign


_LIB = None


def sign(d: int, message: bytes) -> bytes:
    """ECDSA P-256 / SHA-256: r‖s, 64 bytes (the JWS ES256 form) — by the
    `cryptography` package when the box has it, else by `sign_plain`."""
    global _LIB
    if _LIB is None:
        _LIB = _library_signer() or False
    if _LIB:
        try:
            return _LIB(d, message)
        except Exception:                                     # noqa: BLE001
            pass
    return sign_plain(d, message)


def sign_plain(d: int, message: bytes) -> bytes:
    """The same signature in plain Python, with RFC 6979's deterministic
    nonce (no random number to get wrong). Checked digit for digit against
    the RFC's own vector in tests/test_push_alerts.py. It signs only on the
    box's background cycle, never on a request, so its timing is never
    something a stranger can measure; and the key it guards can send our
    subscribers an empty knock and nothing more."""
    digest = hashlib.sha256(message).digest()
    z = int.from_bytes(digest, "big")
    while True:
        k = _rfc6979_k(d, digest)
        r = mul(k)[0] % N
        s = pow(k, -1, N) * (z + r * d) % N
        if r and s:
            return r.to_bytes(32, "big") + s.to_bytes(32, "big")
        digest = hashlib.sha256(digest).digest()     # unreachable in practice


def verify(pub, message: bytes, sig: bytes) -> bool:
    if len(sig) != 64 or not on_curve(pub):
        return False
    r, s = int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")
    if not (1 <= r < N and 1 <= s < N):
        return False
    z = int.from_bytes(hashlib.sha256(message).digest(), "big")
    w = pow(s, -1, N)
    a, b = mul(z * w % N), mul(r * w % N, pub)
    if a is None or b is None:
        return False
    pt = _affine(_jac_add((a[0], a[1], 1), (b[0], b[1], 1)))
    return bool(pt) and pt[0] % N == r


# --- keys --------------------------------------------------------------------
def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def unb64u(text: str) -> bytes:
    text = str(text or "")
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def public_bytes(pub) -> bytes:
    return b"\x04" + pub[0].to_bytes(32, "big") + pub[1].to_bytes(32, "big")


def new_key() -> dict:
    d = secrets.randbelow(N - 1) + 1
    pub = mul(d)
    return {"d": b64u(d.to_bytes(32, "big")), "pub": b64u(public_bytes(pub)), "made": int(time.time())}


def keys(path: Path | None = None) -> dict:
    """The server's VAPID pair, made once on first use and kept. Losing it
    only means every phone must subscribe again."""
    path = Path(path or KEY_PATH)
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
        if got.get("d") and got.get("pub"):
            return got
    except (OSError, ValueError):
        pass
    got = new_key()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(got, fh)
    os.replace(tmp, path)
    return got


def _d(k: dict) -> int:
    return int.from_bytes(unb64u(k["d"]), "big")


def jwt(claims: dict, d: int, header: dict | None = None) -> str:
    head = b64u(json.dumps(header or {"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64u(json.dumps(claims, separators=(",", ":")).encode())
    return f"{head}.{body}." + b64u(sign(d, f"{head}.{body}".encode()))


# --- web push ------------------------------------------------------------------
def endpoint_ok(url: str) -> bool:
    """Only a real push service, https, the default port, no credentials."""
    try:
        u = urlsplit(str(url or ""))
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    if u.scheme != "https" or u.username or u.password or u.port not in (None, 443) or len(url) > 1024:
        return False
    return host in PUSH_HOSTS or any(host.endswith(s) and len(host) > len(s) for s in PUSH_SUFFIXES)


def vapid_header(endpoint: str, k: dict, now: float | None = None) -> str:
    u = urlsplit(endpoint)
    claims = {"aud": f"{u.scheme}://{u.netloc}", "exp": int((now or time.time()) + 12 * 3600), "sub": SUBJECT}
    return f"vapid t={jwt(claims, _d(k))}, k={k['pub']}"


def knock(endpoint: str, k: dict, topic: str = "", ttl: int = 6 * 3600, urgency: str = "normal",
          opener=None) -> int:
    """POST the empty push; the HTTP status (201 delivered, 404/410 gone,
    0 not reached). Never raises."""
    if not endpoint_ok(endpoint):
        return 0
    headers = {"Authorization": vapid_header(endpoint, k), "TTL": str(int(ttl)), "Urgency": urgency,
               "Content-Length": "0", "User-Agent": AGENT}
    topic = "".join(c for c in topic if c.isalnum() or c in "-_")[:32]
    if topic:
        headers["Topic"] = topic            # a newer knock replaces an undelivered one
    req = urllib.request.Request(endpoint, data=b"", headers=headers, method="POST")
    try:
        with (opener or urllib.request.urlopen)(req, timeout=15) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except (OSError, ValueError):
        return 0


# --- Apple's native push (the iOS shell) -------------------------------------
APNS_HOSTS = {"production": "api.push.apple.com", "development": "api.sandbox.push.apple.com"}


def p8_private(pem: str) -> int:
    """The private scalar out of Apple's .p8 key (PKCS#8, P-256): the
    ECPrivateKey inside always opens 02 01 01 04 20 <32 bytes>."""
    body = "".join(ln for ln in str(pem).splitlines() if ln and not ln.startswith("-----"))
    der = base64.b64decode(body)
    at = der.find(b"\x02\x01\x01\x04\x20")
    if at < 0 or len(der) < at + 37:
        raise ValueError("not a P-256 private key")
    d = int.from_bytes(der[at + 5:at + 37], "big")
    if not 1 <= d < N:
        raise ValueError("not a P-256 private key")
    return d


def apns_config(env=None) -> dict | None:
    """The Apple key, set with deploy/setenv.sh; None until it is."""
    env = os.environ if env is None else env
    need = {k: (env.get(k) or "").strip() for k in ("QB_APNS_KEY_FILE", "QB_APNS_KEY_ID", "QB_APNS_TEAM_ID", "QB_APNS_TOPIC")}
    if not all(need.values()):
        return None
    need["env"] = "development" if (env.get("QB_APNS_ENV") or "").strip() == "development" else "production"
    return need


def apns_send(token: str, alert: dict, cfg: dict, run=subprocess.run, now: float | None = None) -> int:
    """One alert to one iPhone through `curl --http2`; the status, 0 when it
    could not be tried. Never raises."""
    token = str(token or "")
    if not cfg or not token or not all(c in "0123456789abcdefABCDEF" for c in token) or len(token) > 200:
        return 0
    if run is subprocess.run and not shutil.which("curl"):
        return 0
    try:
        d = p8_private(Path(cfg["QB_APNS_KEY_FILE"]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    bearer = jwt({"iss": cfg["QB_APNS_TEAM_ID"], "iat": int(now or time.time())}, d,
                 {"alg": "ES256", "kid": cfg["QB_APNS_KEY_ID"]})
    payload = json.dumps({"aps": {"alert": {"title": alert.get("title", ""), "body": alert.get("body", "")},
                                  "sound": "default", "thread-id": alert.get("kind", "")},
                          "url": alert.get("url", "/")})
    url = f"https://{APNS_HOSTS[cfg['env']]}/3/device/{token}"
    cmd = ["curl", "--http2", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "15",
           "-H", f"authorization: bearer {bearer}", "-H", f"apns-topic: {cfg['QB_APNS_TOPIC']}",
           "-H", "apns-push-type: alert", "-H", "apns-priority: 5", "--data-binary", "@-", url]
    try:
        out = run(cmd, input=payload, capture_output=True, text=True, timeout=30)
        return int((out.stdout or "0").strip() or 0)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0
