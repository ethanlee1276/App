"""The Polymarket tape's two totals are kept running between builds, and the
wallets' names are read as the page asks for them (engine/predmarket
.tape_counts, WalletNames; pm_build's "tape counts" step).

The heartbeat at 09:16 on 9 November had "tape counts" at 76 of the
prediction-markets build's 122 seconds, every ten minutes: a row count and
a distinct-wallet count over every trade ever recorded (millions), and
every display name ever harvested read for a few dozen. What these hold:

  * the kept totals are exactly what a full count gives, pull after pull,
    duplicates the tape ignores and wallets seen before included;
  * a count a week old, or one past the tape's top (a restored file),
    counts in full again, and a fresh file starts with a full count;
  * the build adds the new rows by their rowid range and finds a new
    wallet by one seek of the wallet index: it never walks the tape;
  * a wallet's name is read when asked for, once, and says what the whole
    table says; the build no longer reads either whole table.

Run directly: `python3 tests/test_the_polymarket_tape_totals_are_kept.py`
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import predmarket as pm                                # noqa: E402
from engine.db import connect                                      # noqa: E402

NOW = 1_794_230_000


def _trade(i, wallet, ts=None, name=""):
    return {"venue": "polymarket", "tx": f"t{i}", "ts": ts or (NOW - 5000 + i), "wallet": wallet,
            "slug": "s", "title": "", "outcome": "Yes", "side": "BUY", "price": 0.5, "size": 10.0,
            "usd": 5.0, "trader": name}


def _full(conn):
    return (conn.execute("SELECT COUNT(*) FROM pm_trades").fetchone()[0], pm.wallets_seen(conn))


def test_the_kept_totals_are_a_full_counts_pull_after_pull():
    conn = connect(":memory:")
    rnd = random.Random(3)
    first = pm.tape_counts(conn, now=NOW)
    assert (first["trades"], first["wallets"], first["how"]) == (0, 0, "counted"), first
    i, hows = 0, []
    for pull in range(12):
        batch = []
        for _ in range(rnd.randint(0, 40)):
            i += 1
            batch.append(_trade(i, f"0x{rnd.randint(0, 60):03x}"))
        batch += [dict(t) for t in batch[:3]]           # the tape ignores a repeat
        if pull == 5:
            batch.append(_trade(i, ""))                    # a trade with no wallet
        pm.store_trades(conn, batch)
        got = pm.tape_counts(conn, now=NOW + pull * 600)
        assert (got["trades"], got["wallets"]) == _full(conn), (pull, got, _full(conn))
        hows.append(got["how"])
    assert set(hows) == {"kept"}, hows
    assert pm.tape_counts(conn, now=NOW + 9000)["added"] == 0, "nothing new, nothing added"


def test_a_week_old_count_or_one_past_the_top_counts_again():
    conn = connect(":memory:")
    pm.store_trades(conn, [_trade(n, f"w{n % 4}") for n in range(10)])
    assert pm.tape_counts(conn, now=NOW)["how"] == "counted"
    assert pm.tape_counts(conn, now=NOW + pm.RECOUNT_S - 60)["how"] == "kept"
    assert pm.tape_counts(conn, now=NOW + pm.RECOUNT_S + 60)["how"] == "counted", "a week on"
    conn.execute("UPDATE pm_tape_counts SET top_rowid = top_rowid + 50, trades = 999")
    conn.commit()
    again = pm.tape_counts(conn, now=NOW + pm.RECOUNT_S + 120)
    assert again["how"] == "counted" and (again["trades"], again["wallets"]) == _full(conn) == (10, 4)


def test_the_build_never_walks_the_tape_for_them():
    conn = connect(":memory:")
    pm.ensure_tables(conn)
    pm.build_indexes(conn)
    pm.store_trades(conn, [_trade(n, f"w{n % 7}") for n in range(30)])
    pm.tape_counts(conn, now=NOW)
    pm.store_trades(conn, [_trade(100 + n, f"w{n % 9}") for n in range(12)])
    said = []
    conn.set_trace_callback(said.append)
    got = pm.tape_counts(conn, now=NOW + 600)
    conn.set_trace_callback(None)
    assert got["how"] == "kept" and (got["trades"], got["wallets"]) == _full(conn) == (42, 9)
    reads = [s for s in said if "FROM pm_trades" in s]
    for sql in reads:
        # Older Pythons trace the statement unexpanded: each read here
        # takes one value (the counted top), named once or twice.
        args = (0,) if "?" in sql else ()
        plan = " ".join(str(r[-1]) for r in conn.execute("EXPLAIN QUERY PLAN " + sql, args))
        assert "SCAN" not in plan.replace("SCAN CONSTANT ROW", ""), (sql, plan)
    assert any("NOT EXISTS" in s for s in reads), reads


def test_a_name_is_read_when_asked_for_once_and_says_what_the_table_says():
    conn = connect(":memory:")
    pm.store_trades(conn, [_trade(1, "0xking", name="TheKing"), _trade(2, "0xanon"),
                           _trade(3, "0xqueen", name="Queen")])
    whole = pm.wallet_names(conn)
    said = []
    conn.set_trace_callback(said.append)
    names = pm.WalletNames(conn)
    assert [s for s in said if "pm_wallets" in s and "SELECT" in s] == [], "nothing read up front"
    for w in ("0xking", "0xanon", "0xqueen", "0xnobody", "0xking"):
        assert names.get(w, "") == whole.get(w, ""), w
    conn.set_trace_callback(None)
    looked = [s for s in said if s.startswith("SELECT name FROM pm_wallets")]
    assert len(looked) == 4, ("each wallet once", looked)
    assert names.get("0xnobody", "?") == "?"


def test_the_build_reads_neither_whole_table():
    src = (ROOT / "pm_build.py").read_text()
    body = src[src.index("def main("):]
    assert "pm.tape_counts(conn)" in body and "pm.WalletNames(conn)" in body
    for gone in ('SELECT COUNT(*) FROM pm_trades', "wallets_seen(", "wallet_names("):
        assert gone not in body, gone
    at = body.index("pm.tape_counts(conn)")
    assert at < body.index('_lap("tape counts")') < body.index('"stored_total": total_trades')


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
