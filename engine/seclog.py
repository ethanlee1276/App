"""One JSON line per security-relevant outcome.

Audit 2026-09-30, E-5 (roadmap #28). Logins, failed passwords, owner-token
refusals, webhook signature failures, redeem refusals and rate-limit hits
were recorded nowhere: a password-spraying run, a forged webhook or a
brute-forced promo code would have left no trace but a 4xx in Caddy's
access log, with nothing to tell one from a typo.

WHAT A LINE CARRIES, AND WHAT IT NEVER DOES. The kind, the outcome, the
time, the caller's network (IPv4 to /24, IPv6 to /48 — enough to see one
source hammering, not enough to identify a household) and, for account
events, a short one-way tag of the email so repeated attempts on one
account line up without the log holding anyone's address. Never a
password, a token, a code or a raw email: `event` drops any field whose
name says it is one, whatever the caller passes.

Never raises. Losing a log line must not cost the request it describes.

    data/logs/security.jsonl   (QB_SECLOG to move it), rotated at 5 MB to .1
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import ipaddress
import json
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "logs" / "security.jsonl"
MAX_BYTES = 5 * 1024 * 1024
_LOCK = threading.Lock()

#: Field names that must never be written, whoever passes them.
_SECRET = ("password", "token", "secret", "code", "cookie", "authorization", "email")


def path() -> Path:
    return Path(os.environ.get("QB_SECLOG") or DEFAULT_PATH)


def mask_ip(ip) -> str | None:
    try:
        a = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return None
    net = ipaddress.ip_network(f"{a}/{24 if a.version == 4 else 48}", strict=False)
    return str(net)


def who_tag(email) -> str | None:
    e = str(email or "").strip().lower()
    return hashlib.sha256(e.encode()).hexdigest()[:12] if e else None


def event(kind: str, outcome: str, ip=None, email=None, **extra) -> None:
    try:
        line = {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                "kind": str(kind), "outcome": str(outcome)}
        net = mask_ip(ip) if ip else None
        if net:
            line["net"] = net
        tag = who_tag(email)
        if tag:
            line["who"] = tag
        for k, v in extra.items():
            if any(s in k.lower() for s in _SECRET):
                continue
            if isinstance(v, (str, int, float, bool)) or v is None:
                line[k] = v if not isinstance(v, str) else v[:120]
        p = path()
        with _LOCK:
            p.parent.mkdir(parents=True, exist_ok=True)
            try:
                if p.stat().st_size > MAX_BYTES:
                    os.replace(p, p.with_suffix(p.suffix + ".1"))
            except OSError:
                pass
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, separators=(",", ":")) + "\n")
    except Exception:                                         # noqa: BLE001
        pass
