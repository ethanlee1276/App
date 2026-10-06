"""Kalshi API-key signing, in the standard library.

Every authenticated Kalshi request carries three headers:

    KALSHI-ACCESS-KEY        the key id Kalshi showed when the key was made
    KALSHI-ACCESS-TIMESTAMP  milliseconds since the epoch, as text
    KALSHI-ACCESS-SIGNATURE  base64 of RSA-PSS(SHA-256) over
                             timestamp + METHOD + path  (no separators; the
                             path is /trade-api/v2/... with no query string)

WHY THIS IS WRITTEN OUT BY HAND. The engine is standard library end to end
(requirements.txt pins one package, for Ask); the box has no
`cryptography`. The signature is RSA-PSS with MGF1-SHA256 and a 32-byte
salt (RFC 8017 §9.1), which is a few dozen lines over `hashlib` and
Python's big integers. When `cryptography` IS importable it is used
instead, and the test suite signs with this code and verifies with that
library, so the hand-rolled path is checked against the reference on
every run that has it.

The private key is a PEM file: either PKCS#8 ("BEGIN PRIVATE KEY", what
Kalshi downloads) or PKCS#1 ("BEGIN RSA PRIVATE KEY"). Its path is
QB_KALSHI_KEY_FILE; the file is read, never its contents put in the
environment or printed.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import time

HASH_LEN = 32          # SHA-256
SALT_LEN = 32          # Kalshi signs with salt_length = DIGEST_LENGTH


class KeyError_(ValueError):
    """The PEM could not be read as an RSA private key."""


# ─── DER, just enough ──────────────────────────────────────────────────────

def _der(buf: bytes, pos: int = 0) -> tuple[int, bytes, int]:
    """(tag, value, next_pos) of the TLV at ``pos``."""
    tag = buf[pos]
    pos += 1
    ln = buf[pos]
    pos += 1
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(buf[pos:pos + n], "big")
        pos += n
    return tag, buf[pos:pos + ln], pos + ln


def _seq(buf: bytes) -> list[tuple[int, bytes]]:
    out, pos = [], 0
    while pos < len(buf):
        tag, val, pos = _der(buf, pos)
        out.append((tag, val))
    return out


def _int(val: bytes) -> int:
    return int.from_bytes(val, "big")


def parse_pem(pem: str | bytes) -> dict:
    """{"n", "e", "d"} out of a PKCS#8 or PKCS#1 RSA private key PEM."""
    text = pem.decode() if isinstance(pem, bytes) else pem
    m = re.search(r"-----BEGIN ([A-Z ]+)-----(.*?)-----END \1-----", text, re.S)
    if not m:
        raise KeyError_("no PEM block found")
    kind = m.group(1).strip()
    try:
        der = base64.b64decode(re.sub(r"\s+", "", m.group(2)))
    except ValueError as exc:
        raise KeyError_(f"PEM body is not base64: {exc}") from exc
    if "ENCRYPTED" in kind:
        raise KeyError_("the key is password-protected; export it without a password")
    tag, body, _ = _der(der)
    if tag != 0x30:
        raise KeyError_("the key is not a DER SEQUENCE")
    items = _seq(body)
    if kind == "PRIVATE KEY":
        # PKCS#8: version, AlgorithmIdentifier, OCTET STRING(PKCS#1 key)
        if len(items) < 3 or items[2][0] != 0x04:
            raise KeyError_("PKCS#8 key without an inner RSA key")
        tag, body, _ = _der(items[2][1])
        items = _seq(body)
    elif kind != "RSA PRIVATE KEY":
        raise KeyError_(f"unsupported key type: {kind} (Kalshi keys are RSA)")
    if len(items) < 4 or any(t != 0x02 for t, _ in items[:4]):
        raise KeyError_("not an RSA private key (expected version, n, e, d)")
    n, e, d = _int(items[1][1]), _int(items[2][1]), _int(items[3][1])
    if n.bit_length() < 2048:
        raise KeyError_(f"RSA key is only {n.bit_length()} bits")
    return {"n": n, "e": e, "d": d}


# ─── RSA-PSS (RFC 8017) ─────────────────────────────────────────────────────

def _mgf1(seed: bytes, length: int) -> bytes:
    out = b""
    for i in range((length + HASH_LEN - 1) // HASH_LEN):
        out += hashlib.sha256(seed + i.to_bytes(4, "big")).digest()
    return out[:length]


def _pss_encode(message: bytes, em_bits: int, salt: bytes) -> bytes:
    em_len = (em_bits + 7) // 8
    m_hash = hashlib.sha256(message).digest()
    if em_len < HASH_LEN + len(salt) + 2:
        raise ValueError("key too small for PSS")
    h = hashlib.sha256(b"\x00" * 8 + m_hash + salt).digest()
    ps = b"\x00" * (em_len - len(salt) - HASH_LEN - 2)
    db = ps + b"\x01" + salt
    mask = _mgf1(h, em_len - HASH_LEN - 1)
    masked = bytes(a ^ b for a, b in zip(db, mask))
    # Clear the leftmost 8*emLen - emBits bits of the first byte.
    clear = 8 * em_len - em_bits
    masked = bytes([masked[0] & (0xFF >> clear)]) + masked[1:]
    return masked + h + b"\xbc"


def sign_pure(key: dict, message: bytes, salt: bytes | None = None) -> bytes:
    n, d = key["n"], key["d"]
    mod_bits = n.bit_length()
    em = _pss_encode(message, mod_bits - 1, os.urandom(SALT_LEN) if salt is None else salt)
    s = pow(int.from_bytes(em, "big"), d, n)
    return s.to_bytes((mod_bits + 7) // 8, "big")


def verify_pure(key: dict, message: bytes, signature: bytes) -> bool:
    """RFC 8017 §9.1.2, for the test suite and for a box without
    `cryptography`; the public exponent is all it needs."""
    n, e = key["n"], key["e"]
    mod_bits = n.bit_length()
    em_bits = mod_bits - 1
    em_len = (em_bits + 7) // 8
    try:
        em = pow(int.from_bytes(signature, "big"), e, n).to_bytes(em_len, "big")
    except OverflowError:
        return False
    if em[-1] != 0xBC:
        return False
    masked, h = em[:em_len - HASH_LEN - 1], em[em_len - HASH_LEN - 1:-1]
    clear = 8 * em_len - em_bits
    if masked[0] & ~(0xFF >> clear) & 0xFF:
        return False
    db = bytes(a ^ b for a, b in zip(masked, _mgf1(h, len(masked))))
    db = bytes([db[0] & (0xFF >> clear)]) + db[1:]
    ps_len = em_len - HASH_LEN - SALT_LEN - 2
    if db[:ps_len] != b"\x00" * ps_len or db[ps_len] != 0x01:
        return False
    salt = db[ps_len + 1:]
    m_hash = hashlib.sha256(message).digest()
    return hashlib.sha256(b"\x00" * 8 + m_hash + salt).digest() == h


def sign(pem: str | bytes, message: bytes) -> bytes:
    """The signature bytes. `cryptography` when it is installed, the
    standard-library path otherwise — the same bytes either way, up to
    the random salt."""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:                                    # noqa: BLE001
        # ImportError — or a half-installed package whose Rust bindings
        # PANIC on import (a BaseException, seen in the sandbox): the
        # standard-library path either way.
        return sign_pure(parse_pem(pem), message)
    key = serialization.load_pem_private_key(
        pem.encode() if isinstance(pem, str) else pem, password=None)
    return key.sign(message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                         salt_length=padding.PSS.DIGEST_LENGTH),
                    hashes.SHA256())


def headers(key_id: str, pem: str | bytes, method: str, path: str,
            now_ms: int | None = None) -> dict:
    """The three auth headers for one request. ``path`` is the URL path
    with the /trade-api/v2 prefix and WITHOUT the query string."""
    ts = str(int(time.time() * 1000) if now_ms is None else now_ms)
    msg = (ts + method.upper() + path.split("?", 1)[0]).encode()
    return {"KALSHI-ACCESS-KEY": key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sign(pem, msg)).decode()}
