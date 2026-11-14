"""Row counts of an append-only tape, kept running between builds.

The prediction-markets build printed how many trades and price snapshots
its tapes hold by counting them, every ten minutes: on 9 November its
"tape counts" step was 76 of its 122 seconds (every Polymarket trade ever
recorded, counted twice), and the Kalshi step ended on a count of every
snapshot. Nothing deletes from these tables, so the last count plus the
rows added since is the same number: the rows past the counted top (a
rowid range, only the new rows) and, for a distinct count, the values
among them that no counted row has (one seek of that column's index
each). A table is counted in full again once a week, when its top is below
the counted one (a restored or rebuilt file), and the first time.

Standard library only.
"""
from __future__ import annotations

import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS tape_counts (
    name TEXT PRIMARY KEY, rows INTEGER, distinct_n INTEGER,
    top_rowid INTEGER, counted_at INTEGER
);
"""

#: A full count at least this often, whatever the running one says.
RECOUNT_S = 7 * 86400

#: The tables (and the column counted distinct) this may count. Table and
#: column names cannot be bound as parameters, so only these are spoken.
TAPES = {"pm_trades": "wallet", "kalshi_snapshots": None}


def kept(conn, table: str, now: float | None = None) -> dict:
    """``{"rows", "distinct", "added", "how"}`` for ``table`` (one of
    TAPES): what ``COUNT(*)`` and ``COUNT(DISTINCT col)`` give, ``added``
    since the last count, ``how`` "kept" or "counted" (in full)."""
    if table not in TAPES:
        raise ValueError(f"not a tape: {table}")
    col = TAPES[table]
    now = time.time() if now is None else float(now)
    conn.executescript(SCHEMA)
    began = False
    if not conn.in_transaction:
        # One read snapshot, so a count and the top it stops at agree.
        conn.execute("BEGIN")
        began = True
    try:
        top = int(conn.execute(f"SELECT MAX(rowid) FROM {table}").fetchone()[0] or 0)
        was = conn.execute("SELECT rows, distinct_n, top_rowid, counted_at FROM tape_counts "
                           "WHERE name=?", (table,)).fetchone()
        full = (was is None or was[0] is None or was[2] is None or was[3] is None
                or (col and was[1] is None) or int(was[2]) > top
                or now - int(was[3]) > RECOUNT_S)
        if full:
            rows = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            distinct = (int(conn.execute(f"SELECT COUNT(DISTINCT {col}) FROM {table}").fetchone()[0])
                        if col else None)
            added, counted_at = rows, int(now)
        else:
            since = int(was[2])
            added = int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE rowid > ?",
                                     (since,)).fetchone()[0])
            rows, counted_at = int(was[0]) + added, int(was[3])
            distinct = None
            if col:
                fresh = int(conn.execute(
                    f"SELECT COUNT(DISTINCT n.{col}) FROM {table} AS n WHERE n.rowid > ?1 "
                    f"AND NOT EXISTS (SELECT 1 FROM {table} AS o "
                    f"WHERE o.{col} = n.{col} AND o.rowid <= ?1)", (since,)).fetchone()[0])
                distinct = int(was[1]) + fresh
    finally:
        if began:
            conn.commit()
    try:
        conn.execute("INSERT OR REPLACE INTO tape_counts (name, rows, distinct_n, top_rowid, "
                     "counted_at) VALUES (?, ?, ?, ?, ?)", (table, rows, distinct, top, counted_at))
        conn.commit()
    except sqlite3.OperationalError:
        # A locked file keeps the old row; the next build adds from there.
        conn.rollback()
    return {"rows": rows, "distinct": distinct, "added": added,
            "how": "counted" if full else "kept"}
