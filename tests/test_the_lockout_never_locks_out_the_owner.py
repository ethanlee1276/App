"""A lockout stops the guesser, not the owner; the PIN store is no oracle.

Audit 2026-09-30, E-3 / E-4 (roadmap #29). Eight wrong guesses from
anywhere refused the account owner's CORRECT password for fifteen minutes,
and a spray of throwaway addresses evicted a target's counter. The legacy
name+PIN store answered 404 for a missing name and 403 for a wrong PIN (a
name oracle), had no lockout, and sat on the 300/min read bucket.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _acct():
    from engine import accounts as A
    A._fails.clear()
    conn = A.connect(Path(tempfile.mkdtemp()) / "a.db")
    A.create_user(conn, "owner@example.com", "correct horse battery", confirmed=True)
    return A, conn


def test_guesses_from_one_network_do_not_lock_the_owner_elsewhere():
    A, conn = _acct()
    for _ in range(A.MAX_FAILS + 2):
        A.authenticate(conn, "owner@example.com", "wrong guess", where="198.51.100.0/24")
    code, _ = A.authenticate(conn, "owner@example.com", "correct horse battery",
                             where="198.51.100.0/24")
    assert code == 429, "the guessing network is locked out"
    code, out = A.authenticate(conn, "owner@example.com", "correct horse battery",
                               where="203.0.113.0/24")
    assert code == 200 and out["email"] == "owner@example.com", "the owner is never refused"


def test_a_spray_of_throwaway_keys_does_not_forgive_the_target():
    A, conn = _acct()
    target = "owner@example.com|198.51.100.0/24"
    for _ in range(A.MAX_FAILS):
        A._note_fail(target)
    for i in range(5000):
        A._note_fail(f"spray{i}@x.com|10.0.{i % 250}.0/24")
    assert len(A._fails.get(target, [])) == A.MAX_FAILS, "the target's count was evicted"
    assert len(A._fails) <= 4096


def test_the_server_keys_the_lockout_on_the_network():
    src = (ROOT / "server.py").read_text()
    i = src.index("code, out = A.authenticate(")
    assert "where=_net_of(self._client_ip())" in src[i:i + 200]


def test_the_pin_store_gives_one_answer_and_locks_a_guesser():
    import server
    d = Path(tempfile.mkdtemp())
    real = server.PROFILE_DIR if hasattr(server, "PROFILE_DIR") else None
    if real is None:
        return
    server.PROFILE_DIR = d
    from engine import accounts as A
    A._fails.clear()
    try:
        code, _ = server.profile_sync("ethan", "1234", {}, where="198.51.100.0/24")
        assert code == 200
        missing = server.profile_get("nobody", "1234", where="198.51.100.0/24")
        wrong = server.profile_get("ethan", "9999", where="198.51.100.0/24")
        assert missing == wrong == (403, {"error": server._PROFILE_REFUSED}), "a name oracle"
        for _ in range(A.MAX_FAILS):
            server.profile_get("ethan", "0000", where="198.51.100.0/24")
        assert server.profile_get("ethan", "1234", where="198.51.100.0/24")[0] == 429
        assert server.profile_get("ethan", "1234", where="203.0.113.0/24")[0] == 200
    finally:
        server.PROFILE_DIR = real


def test_the_pin_store_rides_the_auth_bucket_and_can_be_retired():
    import server
    src = (ROOT / "server.py").read_text()
    for route in ('if parsed.path.startswith("/api/profile/"):',
                  'if not parsed.path.startswith("/api/profile/"):'):
        i = src.index(route)
        assert "self._rate_limited(RATE_AUTH_PER_MIN, \"auth\")" in src[i:i + 600]
        assert "legacy_profiles_on()" in src[i:i + 600]
    old = os.environ.get("QB_LEGACY_PROFILES")
    try:
        os.environ["QB_LEGACY_PROFILES"] = "off"
        assert server.legacy_profiles_on() is False
        os.environ.pop("QB_LEGACY_PROFILES")
        assert server.legacy_profiles_on() is True
    finally:
        if old is not None:
            os.environ["QB_LEGACY_PROFILES"] = old


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
