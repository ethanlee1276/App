"""Which addresses belong to Cloudflare.

WHY THIS EXISTS. On 2026-08-21 Ethan put the live site behind Cloudflare.
The chain became:

    browser → Cloudflare → Caddy → this app

Caddy's job is to tell the app who is really calling, and `deploy/Caddyfile`
does it by REPLACING `X-Forwarded-For` with `{remote_host}` — the peer
Caddy actually saw. Before Cloudflare that peer was the browser. After
Cloudflare it is a Cloudflare edge server, and the real visitor's address,
which Cloudflare had faithfully passed along, was being overwritten and
thrown away.

WHAT THAT BROKE. `server.rate_ok` buckets by caller. With every visitor
resolving to a handful of Cloudflare edge IPs they all shared one bucket:
300 API calls a minute and 20 sign-ins a minute for an entire city, not
per person. The comment on RATE_AUTH_PER_MIN — "nobody legitimately signs
in twenty times a minute" — is true of a person and false of a datacentre.
The failure mode is the worst kind: the site works fine while it is quiet
and starts refusing real customers exactly when traffic arrives.

WHY A LIST AND NOT A HEADER. `CF-Connecting-IP` carries the real address,
but any client can set that header, so believing it on sight would let
anyone choose their own rate-limit bucket — or somebody else's. It is
trusted only when the machine that spoke to OUR proxy was genuinely
Cloudflare, and the only way to know that is Cloudflare's published list.

FAIL CLOSED. No file, an unreadable file, an empty file, a file of
nonsense: `is_cloudflare` answers False for everything and `_client_ip`
behaves exactly as it did before any of this — the last forwarded hop. A
missing list costs accuracy behind Cloudflare. A list that was believed
without being checked would cost the guarantee.

    deploy/cfips.sh          fetches and installs the list
    deploy/cfips.sh --check  says what is installed and how old it is
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path

#: Overridable for tests and for anyone running the app somewhere other
#: than the droplet. The deploy writes the real one.
ENV_PATH = "QB_CF_IPS"
DEFAULT_PATH = "/etc/qellys/cloudflare-ips.txt"

#: Cache key is (path, mtime, size) — cheap to compute and it notices a
#: refresh without anybody restarting the service.
_CACHE: dict = {"key": None, "nets": ()}


def path() -> Path:
    return Path(os.environ.get(ENV_PATH, "") or DEFAULT_PATH)


def parse(text: str) -> tuple:
    """Every line that is a CIDR, in file order. Anything else is skipped.

    Deliberately forgiving about the FILE and strict about each LINE: a
    stray comment or a blank line must not cost us the other thirty
    ranges, and a typo'd range must not silently widen to something it
    was not meant to cover.
    """
    nets = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            nets.append(ipaddress.ip_network(line, strict=False))
        except ValueError:
            continue
    return tuple(nets)


def ranges() -> tuple:
    """The installed list, reloaded when the file changes."""
    p = path()
    try:
        st = p.stat()
        key = (str(p), st.st_mtime, st.st_size)
    except OSError:
        _CACHE["key"], _CACHE["nets"] = None, ()
        return ()
    if _CACHE["key"] == key:
        return _CACHE["nets"]
    try:
        nets = parse(p.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        nets = ()
    _CACHE["key"], _CACHE["nets"] = key, nets
    return nets


def is_cloudflare(addr: str) -> bool:
    """True when `addr` is one of Cloudflare's published edge addresses."""
    nets = ranges()
    if not nets:
        return False
    try:
        ip = ipaddress.ip_address(str(addr).strip())
    except ValueError:
        return False
    return any(ip in net for net in nets)


def visitor(header_value: str) -> str:
    """The address in `CF-Connecting-IP`, if it can be one.

    ONLY A PUBLIC ADDRESS. Cloudflare reports the internet-facing address
    of a real visitor; it has no reason to ever say 127.0.0.1, and a
    request that claims it is one is claiming something Cloudflare cannot
    have meant. `_local_only` in server.py gates granting and revoking a
    third party's access to Ethan's Yahoo account on exactly that answer,
    so an address that says "I am this machine" has to be refused here
    rather than trusted two calls later.

    Caught by tests/test_client_ip.py on the first run after the header
    was wired up, which is the whole reason the test sends nonsense.
    """
    raw = str(header_value or "").strip()
    if not raw:
        return ""
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return ""
    # is_global is false for loopback, link-local, RFC1918, multicast and
    # the documentation ranges — every category a visitor cannot be.
    return raw if ip.is_global else ""


def describe() -> dict:
    """For `--todo` and the deploy check. Never raises."""
    p = path()
    out = {"path": str(p), "exists": p.exists(), "count": 0, "age_days": None}
    nets = ranges()
    out["count"] = len(nets)
    out["v4"] = sum(1 for n in nets if n.version == 4)
    out["v6"] = sum(1 for n in nets if n.version == 6)
    try:
        import time
        out["age_days"] = round((time.time() - p.stat().st_mtime) / 86400, 1)
    except OSError:
        pass
    return out
