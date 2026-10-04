"""The accounts schema runs once per process, not once per request.

Audit 2026-09-30, F-9 (roadmap #15). accounts.connect(), billing.init and
redeem.init ran `CREATE ... IF NOT EXISTS` on every request. A CREATE INDEX
takes the write lock even when the index is there, so signed-in board polls
queued behind each other and, under load, waited out the 10-second busy
timeout. And the anonymous GET /api/streak/leaders folded every streak —
a write — on every read.
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class _Counting:
    """A connection wrapper that counts executescript calls."""

    def __init__(self, conn):
        self._c, self.scripts = conn, 0

    def executescript(self, s):
        self.scripts += 1
        return self._c.executescript(s)

    def __getattr__(self, n):
        return getattr(self._c, n)


def test_accounts_init_runs_once_per_file():
    from engine import accounts as A
    p = Path(tempfile.mkdtemp()) / "accounts.db"
    A.connect(p).close()
    raw = sqlite3.connect(str(p))
    c = _Counting(raw)
    A._init(c)
    assert c.scripts == 0, "the second request re-ran the schema"
    raw.close()


def test_a_recreated_file_is_initialised_again():
    from engine import accounts as A
    p = Path(tempfile.mkdtemp()) / "accounts.db"
    A.connect(p).close()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(str(p) + suffix)
        except FileNotFoundError:
            pass
    conn = A.connect(p)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert {"users", "sessions", "user_data"} <= names, names
    conn.close()


def test_billing_and_redeem_init_once_too():
    from engine import accounts as A, billing as B, redeem as R
    p = Path(tempfile.mkdtemp()) / "accounts.db"
    conn = A.connect(p)
    once_r = A.once_per_db(R.init)      # redeem stays stdlib-only; the server memoises it
    B.init(conn); once_r(conn)
    c = _Counting(conn)
    B.init(c); A.once_per_db(R.init)(c)
    assert c.scripts == 0
    conn.close()
    src = (ROOT / "server.py").read_text()
    assert "RD.init(conn)" not in src.replace("once_per_db(RD.init)(conn)", ""), \
        "a server call site runs redeem's schema on every request"


def test_an_in_memory_db_is_always_initialised():
    from engine import billing as B
    for _ in range(2):
        raw = sqlite3.connect(":memory:")
        raw.executescript("CREATE TABLE users (id INTEGER PRIMARY KEY);")
        c = _Counting(raw)
        B.init(c)
        assert c.scripts == 1


def test_the_public_leaders_read_folds_at_most_once_a_minute():
    src = (ROOT / "server.py").read_text()
    i = src.index("S.fold_all(conn, slate)")
    before = src[i - 600:i]
    assert "_STREAK_FOLDED[0] > 60" in before, "the anonymous read writes every time"


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
