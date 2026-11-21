"""Passkeys: sign in with Face ID, Touch ID or a phone's own lock (WebAuthn).

From the ideas list (docs/IDEAS.md, the way in and the way up, eighth):
"Face ID / Touch ID sign-in (WebAuthn): no password to forget and no
text-message cost per sign-in."

WHAT IS KEPT (``passkeys``): for each passkey an account adds, the id its
device gave it, its public key, the count the device keeps of its uses, a
name for it and when it was made and last used. Never a private key, a
fingerprint or a face: those never leave the device, which is the point.
And ``passkey_challenges``: the random challenge each ceremony answers,
for CHALLENGE_S at most and once.

WHAT IS CHECKED, every time, in the order the WebAuthn spec gives it
(Level 2, §7.1 registering and §7.2 signing in):

  * the browser's own record of the ceremony (clientDataJSON): its type,
    our challenge (issued here, unexpired, used once) and our origin;
  * the authenticator's data: our site's id, hashed; the person present AND
    verified (the face or the finger, not a tap); and a signature count
    that moved on, unless the device keeps none (Apple's and Google's synced
    passkeys say 0 every time, and that is allowed);
  * on signing in, the signature over the authenticator's data and the hash
    of the browser's record, with the key kept when the passkey was added:
    ES256 (ECDSA on P-256) or RS256 (RSA PKCS#1 v1.5), both checked here in
    plain Python, because the box installs no crypto package.

ADDING ONE needs the account signed in already; the device's word is taken
for its key (attestation "none", as consumer sites do): what makes the key
an account's is that only that account, signed in, could add it.

Standard library only.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time

#: How long a challenge stands: the time to look at a phone and touch it.
CHALLENGE_S = 180
#: The most passkeys one account keeps (a phone, a laptop, a spare).
MAX_PER_ACCOUNT = 10
#: Bounds on what a browser may send, checked before anything is parsed.
MAX_CLIENT_DATA = 4096
MAX_ATTESTATION = 16384
MAX_AUTH_DATA = 4096
MAX_SIGNATURE = 1024
MAX_CRED_ID = 1023
NAME_MAX = 40
#: COSE algorithm numbers: what a new passkey may use.
ES256, RS256 = -7, -257
_B64U = re.compile(r"^[A-Za-z0-9_-]*$")


class PasskeyError(ValueError):
    """Refusal, with a sentence the person can read."""


# --- encodings ----------------------------------------------------------------
def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(bytes(b)).rstrip(b"=").decode()


def unb64u(s, limit: int) -> bytes:
    s = str(s or "")
    if not _B64U.match(s) or len(s) > limit * 4 // 3 + 4:
        raise PasskeyError("That passkey answer was not readable.")
    try:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except (ValueError, TypeError) as exc:
        raise PasskeyError("That passkey answer was not readable.") from exc


def cbor(data: bytes, i: int = 0, depth: int = 0):
    """``(value, next index)``: the CBOR WebAuthn writes (definite lengths;
    integers, byte and text strings, arrays, maps, true/false/null)."""
    if depth > 6:
        raise PasskeyError("That passkey answer was not readable.")
    if i >= len(data):
        raise PasskeyError("That passkey answer was not readable.")
    ib = data[i]
    i += 1
    major, info = ib >> 5, ib & 0x1F
    if info < 24:
        val = info
    elif info in (24, 25, 26, 27):
        size = 1 << (info - 24)
        if i + size > len(data):
            raise PasskeyError("That passkey answer was not readable.")
        val = int.from_bytes(data[i:i + size], "big")
        i += size
    else:
        raise PasskeyError("That passkey answer was not readable.")
    if major == 0:
        return val, i
    if major == 1:
        return -1 - val, i
    if major in (2, 3):
        if val > 8192 or i + val > len(data):
            raise PasskeyError("That passkey answer was not readable.")
        chunk = bytes(data[i:i + val])
        try:
            return (chunk if major == 2 else chunk.decode("utf-8")), i + val
        except UnicodeDecodeError as exc:
            raise PasskeyError("That passkey answer was not readable.") from exc
    if major == 4:
        if val > 64:
            raise PasskeyError("That passkey answer was not readable.")
        out = []
        for _ in range(val):
            x, i = cbor(data, i, depth + 1)
            out.append(x)
        return out, i
    if major == 5:
        if val > 64:
            raise PasskeyError("That passkey answer was not readable.")
        out = {}
        for _ in range(val):
            k, i = cbor(data, i, depth + 1)
            v, i = cbor(data, i, depth + 1)
            if isinstance(k, (list, dict)):
                raise PasskeyError("That passkey answer was not readable.")
            out[k] = v
        return out, i
    if major == 7 and info in (20, 21, 22, 23):
        return {20: False, 21: True, 22: None, 23: None}[info], i
    raise PasskeyError("That passkey answer was not readable.")


# --- P-256 and RSA, verification only --------------------------------------------
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
A = P - 3
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
     0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)


def on_curve(pt) -> bool:
    x, y = pt
    return 0 <= x < P and 0 <= y < P and (y * y - (x * x * x + A * x + B)) % P == 0


def _add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    (x1, y1), (x2, y2) = p1, p2
    if x1 == x2:
        if (y1 + y2) % P == 0:
            return None
        lam = (3 * x1 * x1 + A) * pow(2 * y1, -1, P) % P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    return x3, (lam * (x1 - x3) - y1) % P


def mul(k: int, pt):
    out = None
    while k:
        if k & 1:
            out = _add(out, pt)
        pt = _add(pt, pt)
        k >>= 1
    return out


def der_sig(sig: bytes) -> tuple[int, int]:
    """(r, s) off an ASN.1 DER ECDSA signature, strictly."""
    if len(sig) < 8 or len(sig) > 72 or sig[0] != 0x30 or sig[1] != len(sig) - 2:
        raise PasskeyError("That passkey's signature was not readable.")
    i, out = 2, []
    for _ in range(2):
        if i + 2 > len(sig) or sig[i] != 0x02:
            raise PasskeyError("That passkey's signature was not readable.")
        n = sig[i + 1]
        v = sig[i + 2:i + 2 + n]
        if n == 0 or n > 33 or len(v) != n:
            raise PasskeyError("That passkey's signature was not readable.")
        out.append(int.from_bytes(v, "big"))
        i += 2 + n
    if i != len(sig):
        raise PasskeyError("That passkey's signature was not readable.")
    return out[0], out[1]


def es256_ok(pub, msg: bytes, sig: bytes) -> bool:
    try:
        r, s = der_sig(sig)
    except PasskeyError:
        return False
    if not (1 <= r < N and 1 <= s < N) or not on_curve(pub):
        return False
    z = int.from_bytes(hashlib.sha256(msg).digest(), "big")
    w = pow(s, -1, N)
    pt = _add(mul(z * w % N, G), mul(r * w % N, pub))
    return pt is not None and pt[0] % N == r


_SHA256_INFO = bytes.fromhex("3031300d060960864801650304020105000420")


def rs256_ok(pub, msg: bytes, sig: bytes) -> bool:
    n, e = pub
    k = (n.bit_length() + 7) // 8
    if len(sig) != k or int.from_bytes(sig, "big") >= n:      # RFC 8017 §5.2.2: below the modulus
        return False
    em = pow(int.from_bytes(sig, "big"), e, n).to_bytes(k, "big")
    want = (b"\x00\x01" + b"\xff" * (k - 3 - len(_SHA256_INFO) - 32) + b"\x00"
            + _SHA256_INFO + hashlib.sha256(msg).digest())
    return hmac.compare_digest(em, want)


def key_of(cose: dict) -> tuple[str, dict]:
    """("ES256" | "RS256", the key's numbers as hex) off a COSE key map."""
    if not isinstance(cose, dict):
        raise PasskeyError("That passkey's key was not readable.")
    kty, alg = cose.get(1), cose.get(3)
    if kty == 2 and alg == ES256 and cose.get(-1) == 1:
        x, y = cose.get(-2), cose.get(-3)
        if not (isinstance(x, bytes) and isinstance(y, bytes) and len(x) == len(y) == 32):
            raise PasskeyError("That passkey's key was not readable.")
        pt = (int.from_bytes(x, "big"), int.from_bytes(y, "big"))
        if not on_curve(pt):
            raise PasskeyError("That passkey's key is not on its curve.")
        return "ES256", {"x": x.hex(), "y": y.hex()}
    if kty == 3 and alg == RS256:
        n, e = cose.get(-1), cose.get(-2)
        if not (isinstance(n, bytes) and isinstance(e, bytes)):
            raise PasskeyError("That passkey's key was not readable.")
        N_, E_ = int.from_bytes(n, "big"), int.from_bytes(e, "big")
        if N_.bit_length() < 2048 or E_ < 3 or E_ % 2 == 0:
            raise PasskeyError("That passkey's key is too weak to keep.")
        return "RS256", {"n": n.hex(), "e": e.hex()}
    raise PasskeyError("That kind of passkey isn't one this site can check yet.")


def verify(alg: str, key: dict, msg: bytes, sig: bytes) -> bool:
    if alg == "ES256":
        return es256_ok((int(key["x"], 16), int(key["y"], 16)), msg, sig)
    if alg == "RS256":
        return rs256_ok((int(key["n"], 16), int(key["e"], 16)), msg, sig)
    return False


# --- the authenticator's data ------------------------------------------------------------
def auth_data(ad: bytes) -> dict:
    """The fields of WebAuthn's authenticator data (§6.1)."""
    if len(ad) < 37 or len(ad) > MAX_AUTH_DATA:
        raise PasskeyError("That passkey answer was not readable.")
    flags = ad[32]
    out = {"rp_hash": bytes(ad[:32]), "up": bool(flags & 0x01), "uv": bool(flags & 0x04),
           "at": bool(flags & 0x40), "count": int.from_bytes(ad[33:37], "big")}
    if out["at"]:
        if len(ad) < 55:
            raise PasskeyError("That passkey answer was not readable.")
        n = int.from_bytes(ad[53:55], "big")
        if n == 0 or n > MAX_CRED_ID or 55 + n > len(ad):
            raise PasskeyError("That passkey answer was not readable.")
        out["cred_id"] = bytes(ad[55:55 + n])
        out["cose"], _end = cbor(ad, 55 + n)
    return out


# --- storage -------------------------------------------------------------------------------
def ensure_tables(conn) -> None:
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS passkeys (
        cred_id    TEXT PRIMARY KEY,
        user_id    INTEGER NOT NULL,
        alg        TEXT NOT NULL,
        pubkey     TEXT NOT NULL,
        sign_count INTEGER NOT NULL DEFAULT 0,
        name       TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        last_used  REAL
      );
      CREATE INDEX IF NOT EXISTS passkeys_user ON passkeys (user_id);
      CREATE TABLE IF NOT EXISTS passkey_challenges (
        challenge  TEXT PRIMARY KEY,
        user_id    INTEGER NOT NULL DEFAULT 0,
        kind       TEXT NOT NULL,
        created_at REAL NOT NULL
      );
      -- The handle a passkey carries for its account: random, not the id.
      CREATE TABLE IF NOT EXISTS passkey_users (
        user_id INTEGER PRIMARY KEY,
        handle  TEXT NOT NULL UNIQUE
      );
    """)
    conn.commit()


def _challenge(conn, user_id: int, kind: str, now: float) -> str:
    conn.execute("DELETE FROM passkey_challenges WHERE created_at<?", (now - CHALLENGE_S,))
    c = b64u(secrets.token_bytes(32))
    conn.execute("INSERT INTO passkey_challenges (challenge, user_id, kind, created_at) VALUES (?,?,?,?)",
                 (c, int(user_id), kind, now))
    conn.commit()
    return c


def _take_challenge(conn, challenge: str, kind: str, user_id: int, now: float) -> None:
    """The challenge the browser signed: ours, for this ceremony (and this
    account, when adding a passkey), unexpired, and spent now."""
    row = conn.execute("SELECT user_id, kind, created_at FROM passkey_challenges WHERE challenge=?",
                       (str(challenge),)).fetchone()
    conn.execute("DELETE FROM passkey_challenges WHERE challenge=?", (str(challenge),))
    conn.commit()
    if row is None or row[1] != kind or now - float(row[2]) > CHALLENGE_S or int(row[0]) != int(user_id):
        raise PasskeyError("That passkey request ran out. Try again.")


def _handle(conn, user_id: int) -> str:
    row = conn.execute("SELECT handle FROM passkey_users WHERE user_id=?", (int(user_id),)).fetchone()
    if row:
        return str(row[0])
    h = b64u(secrets.token_bytes(16))
    conn.execute("INSERT OR IGNORE INTO passkey_users (user_id, handle) VALUES (?,?)", (int(user_id), h))
    conn.commit()
    return str(conn.execute("SELECT handle FROM passkey_users WHERE user_id=?", (int(user_id),)).fetchone()[0])


def _client(cdj_b64: str, kind: str, origin: str) -> tuple[dict, bytes]:
    raw = unb64u(cdj_b64, MAX_CLIENT_DATA)
    try:
        cd = json.loads(raw.decode("utf-8"))
        assert isinstance(cd, dict)
    except Exception as exc:                                  # noqa: BLE001
        raise PasskeyError("That passkey answer was not readable.") from exc
    if cd.get("type") != kind:
        raise PasskeyError("That passkey answer was for something else.")
    if str(cd.get("origin") or "") != origin:
        raise PasskeyError("That passkey was made for another site.")
    # Our pages refuse to be framed (frame-ancestors 'none'), so a ceremony
    # run inside another site's frame is not ours to take.
    if cd.get("crossOrigin") is True:
        raise PasskeyError("That passkey was asked for from inside another site.")
    return cd, raw


def _check_auth(ad: dict, rp_id: str) -> None:
    if not hmac.compare_digest(ad["rp_hash"], hashlib.sha256(rp_id.encode()).digest()):
        raise PasskeyError("That passkey belongs to another site.")
    if not (ad["up"] and ad["uv"]):
        raise PasskeyError("That passkey didn't check it was you (Face ID, a fingerprint or the phone's code).")


# --- the four steps ------------------------------------------------------------------------
def register_options(conn, user_id: int, email: str, rp_id: str, now: float | None = None) -> dict:
    """What navigator.credentials.create needs, for a signed-in account."""
    ensure_tables(conn)
    now = time.time() if now is None else now
    have = [r[0] for r in conn.execute("SELECT cred_id FROM passkeys WHERE user_id=?", (int(user_id),))]
    if len(have) >= MAX_PER_ACCOUNT:
        raise PasskeyError(f"This account has {MAX_PER_ACCOUNT} passkeys already. Remove one to add another.")
    name = str(email or "Your account")[:64]
    return {"challenge": _challenge(conn, user_id, "create", now), "rp": {"id": rp_id, "name": "Qellys Book"},
            "user": {"id": _handle(conn, user_id), "name": name, "displayName": name},
            "pubKeyCredParams": [{"type": "public-key", "alg": ES256}, {"type": "public-key", "alg": RS256}],
            "authenticatorSelection": {"residentKey": "required", "requireResidentKey": True,
                                       "userVerification": "required"},
            "attestation": "none", "timeout": CHALLENGE_S * 1000,
            "excludeCredentials": [{"type": "public-key", "id": c} for c in have]}


def register(conn, user_id: int, body: dict, rp_id: str, origin: str, now: float | None = None) -> dict:
    """Keep the passkey the browser just made: the checks of §7.1."""
    ensure_tables(conn)
    now = time.time() if now is None else now
    cd, _raw = _client(body.get("clientDataJSON"), "webauthn.create", origin)
    _take_challenge(conn, cd.get("challenge"), "create", user_id, now)
    att, _end = cbor(unb64u(body.get("attestationObject"), MAX_ATTESTATION))
    if not isinstance(att, dict) or not isinstance(att.get("authData"), bytes):
        raise PasskeyError("That passkey answer was not readable.")
    ad = auth_data(att["authData"])
    _check_auth(ad, rp_id)
    if not ad["at"]:
        raise PasskeyError("That passkey answer carried no key.")
    alg, key = key_of(ad["cose"])
    cred = b64u(ad["cred_id"])
    if conn.execute("SELECT 1 FROM passkeys WHERE cred_id=?", (cred,)).fetchone():
        raise PasskeyError("That passkey is already on an account.")
    if conn.execute("SELECT COUNT(*) FROM passkeys WHERE user_id=?", (int(user_id),)).fetchone()[0] >= MAX_PER_ACCOUNT:
        raise PasskeyError(f"This account has {MAX_PER_ACCOUNT} passkeys already.")
    name = re.sub(r"\s+", " ", str(body.get("name") or "")).strip()[:NAME_MAX] or "Passkey"
    conn.execute("INSERT INTO passkeys (cred_id, user_id, alg, pubkey, sign_count, name, created_at) "
                 "VALUES (?,?,?,?,?,?,?)", (cred, int(user_id), alg, json.dumps(key), ad["count"], name, now))
    conn.commit()
    return {"id": cred, "name": name}


def login_options(conn, rp_id: str, now: float | None = None) -> dict:
    """What navigator.credentials.get needs: a challenge, and any passkey
    this site made (the device lists them; nobody is named first)."""
    ensure_tables(conn)
    now = time.time() if now is None else now
    return {"challenge": _challenge(conn, 0, "get", now), "rpId": rp_id, "userVerification": "required",
            "timeout": CHALLENGE_S * 1000, "allowCredentials": []}


def login(conn, body: dict, rp_id: str, origin: str, now: float | None = None) -> int:
    """The account a signed answer proves: the checks of §7.2."""
    ensure_tables(conn)
    now = time.time() if now is None else now
    cred = str(body.get("rawId") or body.get("id") or "")
    if not cred or len(cred) > MAX_CRED_ID * 4 // 3 + 4 or not _B64U.match(cred):
        raise PasskeyError("That passkey isn't one this site knows.")
    row = conn.execute("SELECT user_id, alg, pubkey, sign_count FROM passkeys WHERE cred_id=?", (cred,)).fetchone()
    cd, raw = _client(body.get("clientDataJSON"), "webauthn.get", origin)
    _take_challenge(conn, cd.get("challenge"), "get", 0, now)
    if row is None:
        raise PasskeyError("That passkey isn't one this site knows. It may have been removed.")
    handle = str(body.get("userHandle") or "")
    if handle:
        mine = conn.execute("SELECT handle FROM passkey_users WHERE user_id=?", (int(row[0]),)).fetchone()
        if not mine or not hmac.compare_digest(str(mine[0]), handle):
            raise PasskeyError("That passkey isn't one this site knows.")
    ad_raw = unb64u(body.get("authenticatorData"), MAX_AUTH_DATA)
    ad = auth_data(ad_raw)
    _check_auth(ad, rp_id)
    sig = unb64u(body.get("signature"), MAX_SIGNATURE)
    if not verify(str(row[1]), json.loads(row[2]), ad_raw + hashlib.sha256(raw).digest(), sig):
        raise PasskeyError("That passkey's signature didn't check out.")
    stored = int(row[3] or 0)
    # A count that went back is a copied key; a device that keeps none says 0.
    if (ad["count"] or stored) and ad["count"] <= stored:
        raise PasskeyError("That passkey looks copied, so it can't sign you in. Remove it and add it again.")
    conn.execute("UPDATE passkeys SET sign_count=?, last_used=? WHERE cred_id=?", (ad["count"], now, cred))
    conn.commit()
    return int(row[0])


def mine(conn, user_id: int) -> list:
    ensure_tables(conn)
    return [{"id": r[0], "name": r[1], "made": r[2], "used": r[3]}
            for r in conn.execute("SELECT cred_id, name, created_at, last_used FROM passkeys WHERE user_id=? "
                                  "ORDER BY created_at", (int(user_id),))]


def remove(conn, user_id: int, cred_id: str) -> bool:
    ensure_tables(conn)
    cur = conn.execute("DELETE FROM passkeys WHERE cred_id=? AND user_id=?", (str(cred_id), int(user_id)))
    conn.commit()
    return bool(cur.rowcount)
