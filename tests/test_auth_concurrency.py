"""A burst of sign-ins must not walk the box into its memory cap.

Ethan, 2026-09-09, four sign-ups on opening day: *"we need to make sure
we're able to handle all of that ... server side and site side"*.

WHAT THE NUMBERS WERE. scrypt is memory-hard on purpose — that is why it
was chosen over PBKDF2 — and `128 * N * r` with this file's parameters is
16MB PER CALL. The server's ceiling (`server.MAX_INFLIGHT`, 64) bounds
THREADS, and the comment justifying 64 says every API call "is a sqlite
read measured in milliseconds". True of every route except these two.

Measured on the dev box, threads all calling `hash_password`:

     1 concurrent   0.06s    51 MB
     8 concurrent   0.24s   163 MB
    32 concurrent   0.79s   516 MB
    64 concurrent   1.67s   963 MB

The unit's cap is MemoryMax=1600M on a 2GB droplet, and 2026-08-17 showed
what approaching that cap does rather than hitting it: the cgroup sat at
826M of 900M and the kernel reclaimed instead of killing — three hours of
thrash, no OOM line, nothing in the journal.

The per-IP limiter upstream caps the RATE (20/min) and says nothing about
CONCURRENCY: twenty requests from one address can all be in flight in the
same second, and several addresses multiply it.

WHAT THIS FILE CHECKS. Not that a semaphore is spelled somewhere — that
a burst never has more than `AUTH_CONCURRENCY` hashes running at once.
`hashlib.scrypt` is replaced with a stub that records how many callers
are inside it simultaneously, so the check is fast and measures the
real thing: the observed peak.

    python3 tests/test_auth_concurrency.py
"""

import hashlib
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts  # noqa: E402


class _Watcher:
    """Stands in for scrypt and remembers the high-water concurrency."""

    def __init__(self, hold=0.01):
        self.lock = threading.Lock()
        self.now = 0
        self.peak = 0
        self.calls = 0
        self.hold = hold

    def __call__(self, *a, **kw):
        with self.lock:
            self.now += 1
            self.calls += 1
            self.peak = max(self.peak, self.now)
        try:
            time.sleep(self.hold)
            return b"\x00" * 32
        finally:
            with self.lock:
                self.now -= 1


def _burst(fn, n, hold=0.01):
    w = _Watcher(hold)
    real = hashlib.scrypt
    hashlib.scrypt = w
    try:
        ts = [threading.Thread(target=fn) for _ in range(n)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
    finally:
        hashlib.scrypt = real
    return w


def test_hashing_a_password_is_bounded_under_a_burst():
    w = _burst(lambda: accounts.hash_password("a-password"), 40)
    assert w.calls == 40, w.calls
    assert w.peak <= accounts.AUTH_CONCURRENCY, (
        f"{w.peak} hashes ran at once against a limit of "
        f"{accounts.AUTH_CONCURRENCY} — at 16MB each that is "
        f"{w.peak * 16}MB of transient memory")


def test_verifying_a_password_is_bounded_too():
    """Sign-IN is the busier of the two, and the one a burst lands on."""
    stored = "scrypt$16384$8$1$" + ("aa" * 16) + "$" + ("00" * 32)
    w = _burst(lambda: accounts.verify_password(stored, "guess"), 40)
    assert w.calls == 40, w.calls
    assert w.peak <= accounts.AUTH_CONCURRENCY, w.peak


def test_the_two_share_one_budget():
    """A mixed burst — some signing up, some signing in — is the real
    shape of a busy minute, and two separate limits would let it reach
    twice the memory either one allows."""
    stored = "scrypt$16384$8$1$" + ("aa" * 16) + "$" + ("00" * 32)

    def mixed(i=[0]):
        with threading.Lock():
            i[0] += 1
            n = i[0]
        if n % 2:
            accounts.hash_password("x")
        else:
            accounts.verify_password(stored, "x")

    w = _burst(mixed, 40)
    assert w.peak <= accounts.AUTH_CONCURRENCY, w.peak


def test_a_slot_is_returned_when_hashing_raises():
    """A leaked slot is worse than no limit: the budget shrinks by one
    per failure until sign-in stops answering at all. `verify_password`
    swallows a bad verifier, which is exactly the path a garbage row or
    a truncated column takes."""
    for _ in range(accounts.AUTH_CONCURRENCY * 3):
        assert accounts.verify_password("not-a-verifier", "x") is False
        assert accounts.verify_password("scrypt$x$y$z$q$r", "x") is False
    # If slots leaked, this blocks for ever rather than failing.
    done = []
    t = threading.Thread(target=lambda: done.append(accounts.hash_password("still-works")))
    t.start()
    t.join(timeout=30)
    assert done, "the budget leaked — hashing no longer completes"


def test_the_limit_is_tunable_without_an_edit():
    """A box with more memory should be able to raise it, and a smaller
    one lower it, without a code change."""
    src = open(os.path.join(ROOT, "engine", "accounts.py"), encoding="utf-8").read()
    assert 'os.environ.get("QB_AUTH_CONCURRENCY"' in src
    assert accounts.AUTH_CONCURRENCY >= 1


def test_the_ceiling_is_lower_than_the_servers_thread_ceiling():
    """If it were not, it would never bind and the memory it exists to
    cap would be spent anyway."""
    import server
    assert accounts.AUTH_CONCURRENCY < server.MAX_INFLIGHT, (
        f"auth budget {accounts.AUTH_CONCURRENCY} does not bind under a "
        f"thread ceiling of {server.MAX_INFLIGHT}")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
