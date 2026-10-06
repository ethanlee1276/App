"""The forecast chain's outside witness (engine/witness): OpenTimestamps
proofs for the chain head, the public export, the wiring. Fixtures only —
no calendar, no webhook, no box.

Ethan, 2026-10-06: "we're not actually placing bets, but the bets can
still be tracked … and our record could be verified from recommending
those bets."

Run directly: `python3 tests/test_the_record_has_an_outside_witness.py`
"""
import datetime as dt
import hashlib
import os
import sqlite3
import sys
import tempfile
import urllib.error
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import witness as W                                # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NOW = dt.datetime(2026, 10, 11, 15, 0, tzinfo=dt.timezone.utc)
CAL = "https://a.pool.opentimestamps.org"


def vb(b: bytes) -> bytes:
    return W.varint(len(b)) + b


def pending_ts(nonce=b"\x01" * 8, uri=CAL) -> bytes:
    """append(nonce) → sha256 → pending attestation, as a calendar answers."""
    return b"\xf0" + vb(nonce) + b"\x08" + b"\x00" + W.PENDING_TAG + vb(vb(uri.encode()))


def bitcoin_ts(height=870000, nonce=b"\x01" * 8) -> bytes:
    """The upgraded form: the same ops, then a fork — the pending receipt
    kept beside the Bitcoin block attestation."""
    pend = b"\x00" + W.PENDING_TAG + vb(vb(CAL.encode()))
    btc = b"\x00" + W.BITCOIN_TAG + vb(W.varint(height))
    return b"\xf0" + vb(nonce) + b"\x08" + b"\xff" + pend + btc


def test_varints_and_the_ots_file_layout():
    for n in (0, 1, 127, 128, 300, 70000):
        assert W._read_varint(W.varint(n), 0) == (n, len(W.varint(n)))
    digest = hashlib.sha256(b"x").digest()
    f = W.ots_file(digest, pending_ts())
    assert f.startswith(W.MAGIC + b"\x01\x08" + digest) and f.endswith(pending_ts())


def test_walk_reads_pending_and_bitcoin_attestations_and_forks():
    assert W.walk(pending_ts()) == {"pending": [CAL], "bitcoin": [], "ok": True}
    got = W.walk(bitcoin_ts(870123))
    assert got["bitcoin"] == [870123] and got["pending"] == [CAL] and got["ok"]
    bad = W.walk(b"\x99\x00")
    assert bad["ok"] is False and "unknown op" in bad["error"]


# ─── a ledger with a forecast chain, and a calendar that answers ───────────

def _ledger(dates):
    d = tempfile.mkdtemp()
    conn = sqlite3.connect(Path(d) / "ledger.db")
    conn.row_factory = sqlite3.Row
    conn.executescript("""CREATE TABLE forecast_log (seq INTEGER PRIMARY KEY AUTOINCREMENT,
        sealed_ts TEXT, bet_id INTEGER, ts TEXT, sport TEXT, date TEXT, player TEXT, market TEXT, side TEXT,
        line REAL, odds INTEGER, hit_prob REAL, category TEXT, lead_min REAL, v INTEGER, prev_hash TEXT, hash TEXT)""")
    prev = "0" * 64
    for i, day in enumerate(dates):
        h = hashlib.sha256(f"{prev}{i}".encode()).hexdigest()
        conn.execute("INSERT INTO forecast_log (sealed_ts, bet_id, ts, sport, date, player, market, side, line, odds, "
                     "hit_prob, category, lead_min, v, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,2,?,?)",
                     ("2026-10-11T12:00:00Z", i + 1, "2026-10-11T11:59:00Z", "nfl", day, f"P{i}", "rec_yds", "OVER",
                      50.5, -110, 0.6, "main", 300.0, prev, h))
        prev = h
    conn.commit()
    return conn, Path(d)


class FakeCalendar:
    def __init__(self, upgraded=False, down=False):
        self.upgraded, self.down, self.calls = upgraded, down, []

    def __call__(self, method, url, body=None):
        self.calls.append((method, url))
        if self.down:
            raise OSError("no route to host")
        if method == "POST":
            assert url.endswith("/digest") and len(body) == 32
            return pending_ts()
        if not self.upgraded:
            raise urllib.error.HTTPError(url, 404, "Pending", {}, None)
        return bitcoin_ts()


def test_an_anchor_is_made_when_the_head_moves_and_the_gap_has_passed():
    conn, d = _ledger(["2026-10-10", "2026-10-10"])
    store = W.connect(d / "witness.db")
    cal, posts = FakeCalendar(), []
    post = lambda s: posts.append(s) or True
    out = W.anchor(conn, store, NOW, http=cal, post=post, out_dir=d / "ots")
    head, seq = W.chain_head(conn)
    assert out["anchored"] and out["head"] == head and out["seq_to"] == 2 and seq == 2
    assert (d / "ots" / f"{head}.ots").read_bytes() == W.ots_file(bytes.fromhex(head), pending_ts())
    assert len(posts) == 1 and head in posts[0] and "#2" in posts[0]
    row = store.execute("SELECT * FROM anchors").fetchone()
    assert row["status"] == "pending" and row["posted"] == 1 and row["calendar"] == CAL
    # Same head: nothing. New row inside the gap: nothing. Past the gap: a second anchor.
    assert W.anchor(conn, store, NOW, http=cal, post=post, out_dir=d / "ots")["why"] == "the head has not moved"
    conn.execute("INSERT INTO forecast_log (sealed_ts, bet_id, sport, date, player, market, side, prev_hash, hash) "
                 "VALUES ('2026-10-11T12:10:00Z', 3, 'nfl', '2026-10-11', 'P2', 'rec_yds', 'OVER', ?, ?)",
                 (head, hashlib.sha256(b"3").hexdigest()))
    conn.commit()
    soon = NOW + dt.timedelta(minutes=5)
    assert W.anchor(conn, store, soon, http=cal, post=post, out_dir=d / "ots")["why"] == "inside the gap"
    later = NOW + dt.timedelta(minutes=45)
    assert W.anchor(conn, store, later, http=cal, post=post, out_dir=d / "ots")["anchored"]
    assert store.execute("SELECT COUNT(*) FROM anchors").fetchone()[0] == 2 and len(posts) == 2


def test_a_dead_calendar_costs_the_anchor_not_the_seal():
    conn, d = _ledger(["2026-10-10"])
    store = W.connect(d / "witness.db")
    out = W.anchor(conn, store, NOW, http=FakeCalendar(down=True), post=lambda s: True, out_dir=d / "ots")
    assert out["anchored"] is False and "calendars unreachable" in out["why"]
    assert store.execute("SELECT COUNT(*) FROM anchors").fetchone()[0] == 0


def test_a_pending_anchor_is_upgraded_to_its_bitcoin_block_once_the_calendar_has_it():
    conn, d = _ledger(["2026-10-10"])
    store = W.connect(d / "witness.db")
    cal = FakeCalendar()
    W.anchor(conn, store, NOW, http=cal, post=lambda s: True, out_dir=d / "ots")
    assert W.upgrade_pending(store, NOW + dt.timedelta(minutes=10), http=cal, out_dir=d / "ots") == 0, "too young"
    assert W.upgrade_pending(store, NOW + dt.timedelta(hours=2), http=cal, out_dir=d / "ots") == 0, "still pending"
    cal.upgraded = True
    assert W.upgrade_pending(store, NOW + dt.timedelta(hours=3), http=cal, out_dir=d / "ots") == 1
    row = store.execute("SELECT * FROM anchors").fetchone()
    assert row["status"] == "bitcoin" and row["height"] == 870000
    head = row["head"]
    assert W.walk((d / "ots" / f"{head}.ots").read_bytes()[len(W.MAGIC) + 2 + 32:])["bitcoin"] == [870000]


def test_the_export_reveals_picks_only_for_days_whose_games_are_over():
    conn, d = _ledger(["2026-10-10", "2026-10-11", "2026-10-12"])     # yesterday, today (ET), tomorrow
    store = W.connect(d / "witness.db")
    W.anchor(conn, store, NOW, http=FakeCalendar(), post=lambda s: True, out_dir=d / "ots")
    p = W.export_payload(conn, store, NOW)
    assert p["seq"] == 3 and len(p["anchors"]) == 1 and p["anchors"][0]["status"] == "pending"
    days = {x["date"]: x for x in p["days"]}
    assert days["2026-10-10"]["picks"][0]["player"] == "P0" and days["2026-10-10"]["anchored"] == 1
    assert days["2026-10-11"]["n"] == 1 and days["2026-10-11"]["picks"] == [], "today's picks are counted, not shown"
    assert days["2026-10-12"]["picks"] == []
    assert [x["date"] for x in p["days"]] == ["2026-10-12", "2026-10-11", "2026-10-10"]
    out = W.export(conn, store, NOW, path=d / "witness.json")
    assert (d / "witness.json").exists() and out["head"] == p["head"]


def test_run_does_all_three_and_survives_an_empty_chain():
    conn, d = _ledger([])
    store = W.connect(d / "witness.db")
    out = W.run(conn, store, NOW, http=FakeCalendar(), post=lambda s: True)
    assert out["anchored"] is False and "empty" in out["why"] and out["upgraded"] == 0


def test_the_sweep_calls_the_witness_after_the_heads_and_the_page_is_wired():
    src = (ROOT / "launch.py").read_text()
    assert src.index("_led.record_heads(conn)") < src.index("_wit.run(conn)") < src.index("forecast log   : +")
    app = (ROOT / "web" / "js" / "app.js").read_text()
    html = (ROOT / "web" / "index.html").read_text()
    assert '"verify"' in app.split("const VIEW_ORDER = [", 1)[1].split("];", 1)[0]
    assert 'if (name === "verify") renderVerify();' in app and "async function renderVerify()" in app
    assert 'id="view-verify"' in html and 'id="verify-body"' in html
    from engine import gate
    assert "witness.json" in gate.FREE_FILES


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
