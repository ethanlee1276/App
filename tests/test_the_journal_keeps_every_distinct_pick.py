"""The journal's pick key keeps every distinct pick, and says what it refuses.

Audit 2026-09-30, A2-4 / A2-5 (roadmap #33). The bets table was UNIQUE on
(sport, date, player, market, category) and every writer is INSERT OR
IGNORE, so three different things collapsed into the first row with no
trace: an MLB doubleheader's second game, the other side of a market the
model turned around on later in the day, and a re-quote at a new price.
Leg and side are in the key now; a re-quote is still refused (the first
price journaled is the claim) but written to journal_dropped.jsonl. And
every repair that rewrites the journal with `--apply` takes a backup
through `_backup_before_repair` first.
"""

import datetime as dt
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger  # noqa: E402

SOON = (dt.datetime.utcnow() + dt.timedelta(days=1)).date().isoformat()

OLD_TABLE = """
CREATE TABLE bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, sport TEXT, date TEXT, player TEXT, market TEXT,
    side TEXT, line REAL, book TEXT, odds INTEGER,
    projection REAL, hit_prob REAL, edge REAL, confidence REAL, grade TEXT,
    stake_units REAL, stake_dollars REAL,
    status TEXT DEFAULT 'open', actual REAL,
    pnl_units REAL, pnl_dollars REAL, closing_line REAL,
    category TEXT DEFAULT 'main',
    game_day TEXT,
    UNIQUE (sport, date, player, market, category)
);
"""


def _old_journal():
    d = Path(tempfile.mkdtemp())
    path = d / "ledger.db"
    c = sqlite3.connect(path)
    c.executescript(OLD_TABLE)
    for i in range(1, 7):
        c.execute("INSERT INTO bets (sport, date, player, market, side, line, "
                  "odds, status, pnl_units) VALUES ('mlb', '2026-09-2' || ?, "
                  "?, 'hits', 'OVER', 0.5, -120, 'won', 0.83)", (i, f"P{i}"))
    c.execute("DELETE FROM bets WHERE id = 6")      # the sequence stays at 6
    c.commit()
    c.close()
    return d, path


def _prop(**kw):
    row = {"player": "A Judge", "team": "NYY", "opponent": "BOS",
           "market": "hits", "market_label": "Hits", "side": "OVER",
           "line": 0.5, "book": "fanduel", "odds": -140, "hit_prob": 0.66,
           "raw_prob": 0.66, "implied_prob": 0.58, "model_prob": 0.66,
           "projection": 1.1, "game_date": SOON, "date": SOON,
           "has_market": True, "recommended": True, "edge": 0.06,
           "confidence": 0.7, "grade": "A", "stake_units": 1.0,
           "logs": [], "recent_values": []}
    row.update(kw)
    return row


def _fresh():
    path = Path(tempfile.mkdtemp()) / "ledger.db"
    conn = ledger.connect(path)
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1)
    return conn, path


def _log(conn, *rows):
    ledger.log_recommendations(conn, {"sport": "mlb", "date": SOON,
                                      "recommendations": list(rows)})


# ---------------------------------------------------------------- the rebuild
def test_an_old_journal_is_rekeyed_with_every_row_id_and_the_sequence_kept():
    d, path = _old_journal()
    before = sqlite3.connect(path).execute(
        "SELECT id, player, status, pnl_units FROM bets ORDER BY id").fetchall()
    conn = ledger.connect(path)
    after = conn.execute(
        "SELECT id, player, status, pnl_units FROM bets ORDER BY id").fetchall()
    assert [tuple(r) for r in after] == before
    assert not ledger._old_pick_key(conn), "the old constraint is still there"
    idx = [r[1] for r in conn.execute("PRAGMA index_list(bets)")]
    assert "bets_pick_key" in idx, idx
    seq = conn.execute("SELECT seq FROM sqlite_sequence WHERE name='bets'").fetchone()[0]
    assert seq == 6, "a deleted top id must never be handed out again"
    trig = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert set(ledger.AUDIT_TRIGGERS) <= trig, trig
    assert conn.execute("SELECT COUNT(*) FROM bets_audit").fetchone()[0] == 0, \
        "the rebuild must not read as every bet deleted"
    assert ledger.get_cfg(conn, "pick_key_v2")
    backups = list((d / "backups").glob("ledger-pre-pick-key-*.db"))
    assert len(backups) == 1
    kept = sqlite3.connect(backups[0]).execute("SELECT COUNT(*) FROM bets").fetchone()[0]
    assert kept == 5
    conn.close()
    ledger._SCHEMA_DONE.clear()
    ledger.connect(path).close()
    assert len(list((d / "backups").glob("*.db"))) == 1, "rebuilt twice"


def test_a_fresh_journal_is_born_with_the_new_key():
    conn, _ = _fresh()
    assert not ledger._old_pick_key(conn)
    assert "UNIQUE (sport, date, player, market, category)" not in ledger._BETS_TABLE


# ------------------------------------------------------------ distinct picks
def test_doubleheader_leg_two_is_journaled():
    conn, _ = _fresh()
    _log(conn, _prop(doubleheader=True, game_number=1),
         _prop(doubleheader=True, game_number=2))
    legs = sorted(r[0] for r in conn.execute("SELECT leg FROM bets"))
    assert legs == [1, 2], legs


def test_a_single_game_and_leg_one_are_the_same_pick():
    conn, _ = _fresh()
    _log(conn, _prop())
    _log(conn, _prop(doubleheader=True, game_number=1))
    assert conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 1


def test_the_other_side_later_in_the_day_is_journaled():
    conn, _ = _fresh()
    _log(conn, _prop())
    _log(conn, _prop(side="UNDER", odds=+110))
    sides = sorted(r[0] for r in conn.execute("SELECT side FROM bets"))
    assert sides == ["OVER", "UNDER"], sides


def test_a_measurement_bucket_still_keeps_one_side_a_day():
    """The samplers are observations, not claims: both sides of one prop
    flagged on one day is the same observation twice, graded as a split.
    Their writers pass one_side=True, and the first side journaled stays
    the only one (test_td_stale_flags caught this in the gate)."""
    conn, _ = _fresh()
    scan = {"stale": [
        {"player": "R One", "market": "anytime_td", "side": "OVER", "line": 0.5,
         "odds": 200, "book": "DraftKings", "consensus": 0.3, "gap_pts": 6.0, "date": SOON},
        {"player": "R One", "market": "anytime_td", "side": "UNDER", "line": 0.5,
         "odds": -190, "book": "FanDuel", "consensus": 0.7, "gap_pts": 2.0, "date": SOON}]}
    assert ledger.log_stale_flags(conn, {"sport": "cfb", "date": SOON, "market_scan": scan}) == 1
    sides = [r[0] for r in conn.execute("SELECT side FROM bets")]
    assert sides == ["OVER"], sides
    src = (ROOT / "engine" / "ledger.py").read_text()
    for fn in ("_journal_longshot_rows", "log_priced_out", "log_near_misses",
               "log_predmarket", "log_stale_flags", "log_form_picks", "log_ufc_picks"):
        i = src.index(f"def {fn}(")
        assert "one_side=True)" in src[i:src.index("\ndef ", i + 5)], fn


def test_the_same_pick_on_the_next_cycle_is_still_one_row_and_logs_nothing():
    conn, path = _fresh()
    _log(conn, _prop())
    _log(conn, _prop())
    assert conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 1
    assert not (path.parent / ledger.DROPPED_LOG).exists()


def test_a_requote_keeps_the_first_price_and_is_written_down_once():
    conn, path = _fresh()
    ledger._DROPPED_SEEN.clear()
    _log(conn, _prop(odds=-140))
    _log(conn, _prop(odds=-118))
    _log(conn, _prop(odds=-118))                     # the next cycle, again
    rows = conn.execute("SELECT id, odds FROM bets").fetchall()
    assert [r["odds"] for r in rows] == [-140], "the first price is the claim"
    lines = (path.parent / ledger.DROPPED_LOG).read_text().splitlines()
    assert len(lines) == 1, lines
    got = json.loads(lines[0])
    assert got["odds"] == -118 and got["kept_odds"] == -140
    assert got["kept_id"] == rows[0]["id"] and got["player"] == "A Judge"


def test_every_journal_writer_goes_through_the_logged_insert():
    src = (ROOT / "engine" / "ledger.py").read_text()
    bare = src.count('conn.execute(\n            "INSERT OR IGNORE INTO bets (') \
        + src.count('conn.execute(\n        "INSERT OR IGNORE INTO bets (')
    assert bare == 0, f"{bare} writer(s) insert without _insert_bet"
    assert src.count("_insert_bet(conn,") >= 11


def test_the_insert_parser_maps_literals_and_parameters():
    got = ledger._insert_columns(
        "INSERT OR IGNORE INTO bets (sport, date, status, side, leg) "
        "VALUES (?, ?, 'open', UPPER(?), ?)", ("mlb", "2026-09-30", "over", 2))
    assert got["sport"] == "mlb" and got["status"] == "open" and got["leg"] == 2


# ---------------------------------------------------------------- repairs
def test_every_journal_repair_backs_up_before_it_writes():
    src = (ROOT / "launch.py").read_text()

    def body(marker, span=2500):
        i = src.index(marker)
        return src[i:i + span]

    closes = body("def repair_closes(")
    assert closes.index('_backed_up("repair-closes")') < closes.index("repair_closing_odds(")
    unplayed = body("def show_unplayed(", 4000)
    assert unplayed.index('_backed_up("void-unplayed")') < unplayed.index("ledger.void_unplayed(")
    resize = body('if "--resize-unstaked" in argv:')
    assert '"--apply" not in argv' in resize, "no dry run"
    assert resize.index('_backed_up("resize-unstaked")') < resize.index("ledger.resize_unstaked(")
    journal = body('if "--repair-journal" in argv:')
    assert journal.index('_backed_up("repair-journal")') < journal.index("move_longshots_out_of_main(")
    premature = body("backup = _backup_before_repair()", 600)
    assert "if not backup:" in premature


def test_the_backup_is_taken_through_sqlite_so_the_wal_comes_with_it():
    import importlib
    launch = importlib.import_module("launch")
    d = Path(tempfile.mkdtemp())
    live = d / "ledger.db"
    c = sqlite3.connect(live)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("CREATE TABLE t (x)")
    c.execute("INSERT INTO t VALUES (1)")
    c.commit()                               # still in the -wal, not the file
    old_l, old_root = ledger.DEFAULT_DB, launch.ROOT
    from engine import db as _db
    old_h = _db.DEFAULT_DB
    try:
        ledger.DEFAULT_DB, _db.DEFAULT_DB, launch.ROOT = live, d / "nohist.db", d
        out = launch._backup_before_repair("test")
    finally:
        ledger.DEFAULT_DB, _db.DEFAULT_DB, launch.ROOT = old_l, old_h, old_root
    c.close()
    assert out and out.name.startswith("pre-test-")
    got = sqlite3.connect(out / "ledger.db").execute("SELECT x FROM t").fetchall()
    assert got == [(1,)], "the backup missed a committed write still in the WAL"


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
