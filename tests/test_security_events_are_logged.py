"""Every security-relevant outcome leaves one JSON line, and no secret.

Audit 2026-09-30, E-5 (roadmap #28). Sign-ins, failed passwords, owner-
token refusals, forged webhooks, refused promo codes and rate-limit hits
were recorded nowhere: a password-spraying run would have looked like a
handful of 4xx lines in Caddy's access log.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SERVER = (ROOT / "server.py").read_text()


def _with_log(fn):
    p = Path(tempfile.mkdtemp()) / "sec.jsonl"
    old = os.environ.get("QB_SECLOG")
    os.environ["QB_SECLOG"] = str(p)
    try:
        fn()
    finally:
        if old is None:
            os.environ.pop("QB_SECLOG", None)
        else:
            os.environ["QB_SECLOG"] = old
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_a_line_names_the_event_and_never_the_secret():
    from engine import seclog
    lines = _with_log(lambda: seclog.event(
        "login", "fail", "203.0.113.77", email="Someone@Example.com", status=401,
        password="hunter2", token="abc", code="PROMO", session_cookie="x"))
    assert len(lines) == 1
    l = lines[0]
    assert l["kind"] == "login" and l["outcome"] == "fail" and l["status"] == 401
    assert l["net"] == "203.0.113.0/24", "the network, not the household"
    assert l["who"] == seclog.who_tag("someone@example.com") and len(l["who"]) == 12
    flat = json.dumps(l).lower()
    for secret in ("hunter2", "abc", "promo", "someone@example.com", "203.0.113.77"):
        assert secret not in flat, secret


def test_ipv6_is_masked_to_a_48():
    from engine import seclog
    assert seclog.mask_ip("2001:db8:abcd:12::1") == "2001:db8:abcd::/48"
    assert seclog.mask_ip("not an ip") is None


def test_it_never_raises_and_rotates():
    from engine import seclog
    old = seclog.MAX_BYTES
    seclog.MAX_BYTES = 200
    try:
        def many():
            for i in range(20):
                seclog.event("rate_limit", "blocked", "10.0.0.1", bucket="auth", n=i)
        lines = _with_log(many)
    finally:
        seclog.MAX_BYTES = old
    assert 0 < len(lines) < 20, "the file rotated"
    os.environ["QB_SECLOG"] = "/proc/definitely/not/writable"
    try:
        seclog.event("login", "ok")          # must not raise
    finally:
        os.environ.pop("QB_SECLOG", None)


def test_every_outcome_the_audit_named_is_logged():
    for kind in ('_seclog("rate_limit", "blocked"', '_seclog(path, "ok" if code == 200 else "fail"',
                 '_seclog("password_change"', '_seclog("account_delete", "wrong_password"',
                 '_seclog("redeem", "refused"', '_seclog("webhook", "bad_signature"'):
        assert kind in SERVER, kind
    # Three owner doors, each logging a refusal: Zeno's tickets, Zeno's
    # import, and the research-picks check (2026-10-04) both its routes share.
    assert SERVER.count('_seclog("owner_token", "refused"') == 3, "every owner door"
    # The login line carries the account as a tag, never the password.
    i = SERVER.index('_seclog(path, "ok" if code == 200 else "fail"')
    assert "password" not in SERVER[i:i + 200]


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
