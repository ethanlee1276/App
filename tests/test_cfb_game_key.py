"""A college game row is keyed away@home, like every other sport's.

Ethan ran the college backlog clear on 2026-09-06 and nothing graded.
`--why-open` filed college TOTALS under "no stat line", which is a join
failure wearing the wrong label: a total bet stores its matchup key
("BCU@UCF") in the `player` column and `ledger._game_bet_evidence` looks
the game up by `game_id`. The NFL and MLB ingests both write
`f"{away}@{home}"`; the college feed wrote the mirror's own numeric id
("401405059") — 0 of 3,133 stored rows were joinable, so no college
total had ever settled or ever could.

Run directly: `python3 tests/test_cfb_game_key.py`
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, ingest, ledger, standings
from engine.sources import cfbfastr

ROW = {"home_division": "fbs", "away_division": "fbs", "home_points": "34",
       "away_points": "21", "home_id": "61", "away_id": "228",
       "start_date": "2026-08-29T18:00:00.000Z", "game_id": "401405059"}
IDS = {"61": "UGA", "228": "CLEM"}


def test_the_parser_writes_the_key_the_other_sports_write():
    out = cfbfastr.parse_schedule([ROW], 2026, id_to_abbr=IDS)
    assert out["games"], out["skipped"]
    g = out["games"][0]
    assert g["game_id"] == "CLEM@UGA", g
    assert (g["home"], g["away"]) == ("UGA", "CLEM")
    assert g["period"] == "2026-08-29"


def _conn():
    conn = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    return conn


def test_a_college_total_settles_once_the_key_matches():
    hist, book = _conn(), ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    db.upsert_games(hist, cfbfastr.parse_schedule([ROW], 2026, id_to_abbr=IDS)["games"])
    book.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
        "stake_units, stake_dollars, status, category) VALUES "
        "(?,'cfb','2026-08-29','CLEM@UGA','total','UNDER',59.5,'DK',-110,1.0,10.0,'open','main')",
        ("2026-08-29T12:00:00",))
    book.commit()
    assert ledger.settle_from_history(book, hist, "cfb") == 1
    row = book.execute("SELECT status, actual FROM bets").fetchone()
    assert row["status"] == "won" and row["actual"] == 55.0, dict(row)


def test_the_migration_rekeys_stored_rows():
    conn = _conn()
    db.upsert_games(conn, [{"sport": "cfb", "season": 2025, "period": "2025-09-06",
                            "game_id": "401405059", "home": "UGA", "away": "CLEM",
                            "home_score": 30, "away_score": 17}])
    got = ingest.remap_cfb_game_ids(conn)
    assert got == {"renamed": 1, "merged": 0, "left": 0}, got
    row = conn.execute("SELECT game_id, home_score FROM games").fetchone()
    assert row["game_id"] == "CLEM@UGA" and row["home_score"] == 30
    # Idempotent: a second pass finds nothing to do.
    assert ingest.remap_cfb_game_ids(conn) == {"renamed": 0, "merged": 0, "left": 0}


def test_a_rekey_that_would_collide_merges_instead_of_counting_the_game_twice():
    """game_id is part of the primary key, so a refresh under the new key
    beside the old numeric row would leave TWO rows for one game — and
    `standings.compute` counts rows, so Georgia would read 2-0 off one
    win."""
    conn = _conn()
    db.upsert_games(conn, [
        {"sport": "cfb", "season": 2025, "period": "2025-09-06",
         "game_id": "401405059", "home": "UGA", "away": "CLEM",
         "home_score": 30, "away_score": 17},
        {"sport": "cfb", "season": 2025, "period": "2025-09-06",
         "game_id": "CLEM@UGA", "home": "UGA", "away": "CLEM",
         "home_score": 30, "away_score": 17}])
    before = standings.compute(conn, "cfb", season=2025, today="2025-12-01")
    uga = [t for g in before["groups"] for t in g["teams"] if t["team"] == "UGA"][0]
    assert uga["record"] == "2-0", "the duplicate is exactly the hazard"
    got = ingest.remap_cfb_game_ids(conn)
    assert got["merged"] == 1 and got["renamed"] == 0
    assert conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1
    after = standings.compute(conn, "cfb", season=2025, today="2025-12-01")
    uga = [t for g in after["groups"] for t in g["teams"] if t["team"] == "UGA"][0]
    assert uga["record"] == "1-0", after


def test_a_row_with_no_team_names_is_left_alone():
    conn = _conn()
    db.upsert_games(conn, [{"sport": "cfb", "season": 2025, "period": "2025-09-06",
                            "game_id": "999", "home": "", "away": "",
                            "home_score": 1, "away_score": 0}])
    assert ingest.remap_cfb_game_ids(conn)["left"] == 1
    assert conn.execute("SELECT game_id FROM games").fetchone()["game_id"] == "999"


def test_the_nightly_rekeys_before_it_refreshes():
    src = (ROOT / "engine" / "maintenance.py").read_text()
    i = src.index("from .ingest import ingest_cfb_history")
    block = src[i:src.index("cfb history backfill failed", i)]
    assert "remap_cfb_game_ids(_cconn)" in block
    assert block.index("remap_cfb_game_ids(_cconn)") < block.index("res = ingest_cfb_history("), \
        "a refresh before the rekey writes good keys beside unjoinable ones"


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
