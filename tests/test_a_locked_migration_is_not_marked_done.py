"""A locked database is never mistaken for "the column is already there".

Audit 2026-09-30, F-10 (roadmap #16). Every `ALTER TABLE ... ADD COLUMN`
probe caught `sqlite3.OperationalError` and moved on — and "database is
locked" is an OperationalError too. The schema was then memoised as done,
so on the day the lock hit, the column was missing for the rest of the
process and every journal insert naming it failed with `no such column`.
Now only "duplicate column" is swallowed; anything else re-raises and the
memo is left unset, so the next connection tries again.
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class _Locked(sqlite3.Connection):
    def execute(self, sql, *a):
        if "ADD COLUMN" in sql:
            raise sqlite3.OperationalError("database is locked")
        return super().execute(sql, *a)


def _with_lock(fn):
    real = sqlite3.connect
    sqlite3.connect = lambda *a, **k: real(*a, factory=_Locked, **k)
    try:
        return fn()
    finally:
        sqlite3.connect = real


def test_only_a_duplicate_column_is_swallowed():
    from engine.db import column_exists_or_raise
    column_exists_or_raise(sqlite3.OperationalError("duplicate column name: leg"))
    for msg in ("database is locked", "attempt to write a readonly database",
                "no such table: bets", "disk I/O error"):
        try:
            column_exists_or_raise(sqlite3.OperationalError(msg))
        except sqlite3.OperationalError as exc:
            assert str(exc) == msg
        else:
            raise AssertionError(f"{msg!r} was read as 'already there'")


def test_the_ledger_raises_on_a_lock_and_leaves_the_memo_unset():
    from engine import db, ledger as L
    p = Path(tempfile.mkdtemp()) / "ledger.db"
    try:
        _with_lock(lambda: L.connect(p))
    except sqlite3.OperationalError as exc:
        assert "locked" in str(exc)
    else:
        raise AssertionError("a locked ALTER was swallowed")
    raw = sqlite3.connect(str(p))
    assert db.needs_schema(raw, p, L._SCHEMA_DONE), "the failed migration was memoised"
    raw.close()
    conn = L.connect(p)                       # the next connection finishes the job
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bets)")}
    assert {"leg", "evidence", "team", "game_day", "closing_fair"} <= cols
    conn.close()


def test_the_history_db_raises_on_a_lock_too():
    from engine import db
    p = Path(tempfile.mkdtemp()) / "history.db"
    try:
        _with_lock(lambda: db.connect(p))
    except sqlite3.OperationalError as exc:
        assert "locked" in str(exc)
    else:
        raise AssertionError("a locked ALTER was swallowed")
    conn = db.connect(p)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(odds_history)")}
    assert "commence_time" in cols
    conn.close()


def test_no_add_column_probe_swallows_every_error():
    import re
    for f in ("engine/db.py", "engine/ledger.py"):
        src = (ROOT / f).read_text()
        for m in re.finditer(r"ADD COLUMN[^\n]*\n(?:[^\n]*\n){0,3}?\s*except sqlite3\.OperationalError:\n\s*pass", src):
            raise AssertionError(f"{f}: {m.group(0)[:80]!r}")


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
