"""Two requests that migrate the same table at once: the loser must not 500.

Found by the nightly browser run, 2026-10-27. Opening every page at once
put six `/api/feed/...` calls in flight against a database that had just
been created, and one of them came back 500 with this on the server:

    File "engine/socialfeed.py", line 123, in _add
      conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    sqlite3.OperationalError: duplicate column name: last_try

Every additive migration in the tree is written the same way — read the
columns, add the ones that are missing — and that read is a FAST PATH,
NOT A LOCK. The server is a ThreadingHTTPServer with one connection per
request, so on the first pass after a deploy two requests both read the
table without the new column and both run the ALTER. SQLite has no
`ADD COLUMN IF NOT EXISTS`, so the loser raises, and a raise out of
`ensure_tables` is a 500 on a page somebody is looking at. Sixteen
threads against a fresh database: six raised out of `billing.init`
(`plan`), eight out of `digest.ensure_tables` (`salt`).

The page tests did not catch it because a failed `fetch` is not a script
error — the board renders with an empty feed and the test passes. Only
the server's own traceback said anything, and only to a terminal.

So every one of these now swallows a duplicate column — and ONLY a
duplicate column. "database is locked" is an `OperationalError` too, and
reading that as "already there" is audit 2026-09-30, F-10: the column
stays missing for the rest of the process and every insert naming it
fails. `engine.db.column_exists_or_raise` is the one place that rule
lives, and these call it.

The list below is asserted to be complete, not just long — the lesson
test_typography learned twice about stylesheets. A new module that ALTERs
a table and is not covered here fails the last test in this file.
"""

import re
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import (accounts, billing, digest, gamechat, karma, lifecycle, parlayledger,  # noqa: E402
                    pickem, predmarket, pushalerts, slipwatch, socialfeed)

#: (the file, a name for the failure, the migration to run on a connection).
#: `__wrapped__` steps past `once_per_db`, which is a memo and would skip
#: the body — the point here is to run it a second time on purpose.
MIGRATORS = (
    ("engine/accounts.py", "accounts._migrate", accounts._migrate),
    ("engine/billing.py", "billing.init", billing.init.__wrapped__),
    ("engine/digest.py", "digest.ensure_tables", digest.ensure_tables),
    ("engine/predmarket.py", "predmarket.ensure_tables", predmarket.ensure_tables),
    ("engine/parlayledger.py", "parlayledger.ensure_schema", parlayledger.ensure_schema),
    ("engine/slipwatch.py", "slipwatch.ensure_tables", slipwatch.ensure_tables),
    ("engine/socialfeed.py", "socialfeed.ensure_tables", socialfeed.ensure_tables),
    # The watch parties' column on the chat's messages (2026-10-28).
    ("engine/gamechat.py", "gamechat.ensure_tables", gamechat.ensure_tables),
    # Karma alerts' two columns on the karma settings (2026-10-28).
    ("engine/karma.py", "karma.ensure_tables", karma.ensure_tables),
    # The pick'em's Tuesday-line marker on its settings (2026-10-28).
    ("engine/pickem.py", "pickem.ensure_tables", pickem.ensure_tables),
    # A phone's last picks-are-up alert, for the three-hour gap (2026-10-29).
    ("engine/pushalerts.py", "pushalerts.ensure_tables", pushalerts.ensure_tables),
    # A longer plan's renewal notice, sent once (2026-10-29, phone first).
    ("engine/lifecycle.py", "lifecycle.ensure_tables", lifecycle.ensure_tables),
)

#: Files that ALTER a table and are covered somewhere else, with the reason.
ELSEWHERE = {
    # Both go through column_exists_or_raise already, pinned by
    # tests/test_a_locked_migration_is_not_marked_done.py.
    "engine/db.py": "test_a_locked_migration_is_not_marked_done.py",
    "engine/ledger.py": "test_a_locked_migration_is_not_marked_done.py",
    # A one-off rescale, run by hand with --apply after it has copied the
    # journal aside. One process, once, never two at a time.
    "rescale.py": "a hand-run one-off, not a request path",
}


class _StaleView:
    """A connection whose `PRAGMA table_info` is one migration behind.

    This is exactly what the losing thread sees: it read the table before
    the winner's ALTER landed, so every column it is about to add looks
    missing, and every ALTER it then runs hits a column that is already
    there. Returning no rows makes that view deterministic — no sleeps,
    no thread scheduling to hope for."""

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def execute(self, sql, *a):
        if "table_info" in sql.lower():
            return []
        return self._conn.execute(sql, *a)


class _Locked:
    """A connection whose every ALTER says the database is locked."""

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def execute(self, sql, *a):
        if "ADD COLUMN" in sql:
            raise sqlite3.OperationalError("database is locked")
        return self._conn.execute(sql, *a)


def _migrated(run):
    """A database this migration has already finished with."""
    conn = accounts.connect(Path(tempfile.mkdtemp()) / "accounts.db")
    run(conn)
    conn.commit()
    return conn


def test_the_losing_writer_does_not_raise():
    for where, name, run in MIGRATORS:
        conn = _migrated(run)
        try:
            run(_StaleView(conn))
        except sqlite3.OperationalError as exc:
            raise AssertionError(
                f"{where}: {name} raised {exc} when another writer got "
                f"there first — that is a 500 on a live page") from exc
        finally:
            conn.close()


def test_a_locked_database_still_raises():
    """The other half of F-10. Swallowing the duplicate must not widen
    into swallowing everything: if the ALTER could not run at all, the
    caller has to hear about it, or the column is missing for the rest of
    the process and every insert naming it fails."""
    for where, name, run in MIGRATORS:
        conn = _migrated(run)
        try:
            run(_Locked(_StaleView(conn)))
        except sqlite3.OperationalError as exc:
            assert "locked" in str(exc), f"{where}: {name} raised {exc}"
        else:
            raise AssertionError(
                f"{where}: {name} read 'database is locked' as "
                f"'the column is already there' (audit 2026-09-30, F-10)")
        finally:
            conn.close()


def test_sixteen_requests_at_once_on_a_new_database():
    """The failure as it actually arrived: real threads, real connections,
    a database none of them has migrated yet.

    Thread interleaving is not something a test can insist on — on a
    one-vCPU box this may never collide, and a run that does not collide
    proves nothing. That is fine: it cannot fail unless the bug is back.
    The deterministic check is the one above."""
    for where, name, run in MIGRATORS:
        path = Path(tempfile.mkdtemp()) / "accounts.db"
        accounts.connect(path).close()
        dupes = []

        def once():
            try:
                conn = accounts.connect(path)
                run(conn)
                conn.close()
            except sqlite3.OperationalError as exc:
                if "duplicate column" in str(exc).lower():
                    dupes.append(str(exc))

        threads = [threading.Thread(target=once) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not dupes, f"{where}: {name} raised {dupes[0]} under load"


def test_every_migration_in_the_tree_is_covered():
    """The enumeration, not a list.

    test_typography learned this twice: a check that names its files goes
    quietly blind the day a new file lands. So walk the tree for the
    statement itself. A new module that ALTERs a table either joins
    MIGRATORS or says in ELSEWHERE where it is covered instead."""
    covered = {where for where, _n, _r in MIGRATORS} | set(ELSEWHERE)
    missing = []
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("tests/", "research/", "deploy/")):
            continue
        if "ADD COLUMN" in path.read_text(encoding="utf-8") and rel not in covered:
            missing.append(rel)
    assert not missing, (
        f"{missing} ALTER a table and nothing checks the second writer; "
        f"add them to MIGRATORS or name their cover in ELSEWHERE")


def test_no_probe_swallows_every_error():
    """A bare `except sqlite3.OperationalError: pass` anywhere near an
    ADD COLUMN is F-10 all over again."""
    bad = []
    for where in sorted({w for w, _n, _r in MIGRATORS} | set(ELSEWHERE)):
        src = (ROOT / where).read_text(encoding="utf-8")
        for m in re.finditer(r"ADD COLUMN[^\n]*\n(?:[^\n]*\n){0,4}?"
                             r"\s*except sqlite3\.OperationalError:\n\s*pass", src):
            bad.append(f"{where}: {m.group(0)[:60]!r}")
    assert not bad, bad


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items())
           if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
