"""A game-log row given twice under one key is written once, as the last of
them (engine/db.last_per_key, upsert_player_logs; engine/boxsettle's settle
ingest checks the rows the table would keep).

The settle pass from about half past midnight on 10 November: the college
logs' generation count rose by 124 with every pass, no game on, so every kept
college read (engine/logcache) said "rows changed" and read its rows again.
The table's key names a player by name alone, not by team, so a box score
listing one name on both sides of a game gave two rows one key: the write
stored the first and replaced it with the second, the next pass's check found
the first not on file, and both went in again. What these hold:

  * the second pass over a summary with one name on both sides writes
    nothing, and counts the game unchanged; without the fix it changes two
    rows a shared key, every pass;
  * the table keeps what the last row said, as it did, and the write still
    returns how many rows it was given;
  * a row missing a key part is kept as given (SQLite never treats two
    NULLs in a key as one row), and keys compare as the table compares
    them (a season "2026" is 2026, a period 7 is "7").

Run directly: `python3 tests/test_one_name_on_both_sides_is_written_once.py`
"""
import datetime as dt
import inspect
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import boxsettle as B, db, ledger                     # noqa: E402

YESTERDAY = (dt.date.today() - dt.timedelta(days=1)).isoformat()


def _team(abbr, tid, name):
    return {"abbreviation": abbr, "id": tid, "displayName": name}


MICH, OSU = _team("MICH", "130", "Michigan Wolverines"), _team("OSU", "194", "Ohio State Buckeyes")


def _ath(name, stats, pos=None):
    who = {"displayName": name}
    if pos:
        who["position"] = {"abbreviation": pos}
    return {"athlete": who, "stats": stats}


def _payload():
    """Each side a TEAM rushing line and a receiver called Jordan Smith."""
    rush = ["CAR", "YDS", "AVG", "TD", "LONG"]
    rec = ["REC", "YDS", "AVG", "TD", "LONG"]
    return {"boxscore": {"players": [
        {"team": MICH, "statistics": [
            {"name": "rushing", "labels": rush,
             "athletes": [_ath("Donovan Edwards", ["18", "112", "6.2", "2", "41"], "RB"),
                          _ath("TEAM", ["2", "-3", "-1.5", "0", "0"])]},
            {"name": "receiving", "labels": rec,
             "athletes": [_ath("Jordan Smith", ["4", "51", "12.8", "1", "22"], "WR")]}]},
        {"team": OSU, "statistics": [
            {"name": "rushing", "labels": rush,
             "athletes": [_ath("TEAM", ["1", "-1", "-1.0", "0", "0"])]},
            {"name": "receiving", "labels": rec,
             "athletes": [_ath("Jordan Smith", ["2", "9", "4.5", "0", "6"], "TE"),
                          _ath("Some Receiver", ["5", "60", "12.0", "0", "20"], "WR")]}]}]}}


def _college_game():
    from engine.sources.cfbdata import _team_key
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = db.connect(t / "h.db")
    L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, "
              "stake_units, stake_dollars, status, category) VALUES (?, 'cfb', ?, ?, "
              "'Some Receiver', 'receptions', 'OVER', 6.5, -110, 1, 10, 'open', 'main')",
              (f"{YESTERDAY}T12:00:00", YESTERDAY, YESTERDAY))
    L.commit()
    H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, "
              "away_score, extra) VALUES ('cfb', 2026, ?, '401999', ?, ?, ?, 24, 20, ?)",
              (YESTERDAY, YESTERDAY, _team_key(MICH), _team_key(OSU),
               json.dumps({"espn_game_id": "401999"})))
    H.commit()
    return L, H


def _gen(H):
    r = H.execute("SELECT gen FROM log_generations WHERE sport='cfb' AND season=2026").fetchone()
    return r[0] if r else 0


def _passes(H, L, n):
    fs = lambda lg, eid: _payload()                                    # noqa: E731
    fr = lambda lg: []                                                 # noqa: E731
    return [B.ingest_for_open(L, H, "cfb", log=lambda *a: None, fetch_rows=fr, fetch_summary=fs)
            for _ in range(n)]


def test_the_second_pass_over_one_name_on_both_sides_writes_nothing():
    L, H = _college_game()
    shared = [r for r in B.cfb_rows(_payload(), dict(H.execute("SELECT * FROM games").fetchone()))
              if r["player"] in ("TEAM", "Jordan Smith")]
    keys = {(r["player"], r["market"]) for r in shared}
    assert len(shared) > len(keys) >= 8, "the summary does carry one name on both sides"
    first, = _passes(H, L, 1)
    assert first["games"] == 1, first
    gen, before = _gen(H), H.total_changes
    second, third = _passes(H, L, 2)
    assert second["games"] == 0 and second["unchanged"] == 1 and second["rows"] == 0, second
    assert third["unchanged"] == 1, third
    assert _gen(H) == gen and H.total_changes == before, "not one row written again"


def test_without_it_every_pass_changes_two_rows_a_shared_key():
    L, H = _college_game()
    keep = db.last_per_key
    db.last_per_key = lambda rows: list(rows)                         # the code before
    try:
        _passes(H, L, 1)
        gen = _gen(H)
        _passes(H, L, 2)
        moved = _gen(H) - gen
    finally:
        db.last_per_key = keep
    shared = {(r["player"], r["market"]) for r in
              B.cfb_rows(_payload(), dict(H.execute("SELECT * FROM games").fetchone()))
              if r["player"] in ("TEAM", "Jordan Smith")}
    assert moved == 2 * 2 * len(shared), (moved, len(shared))


def test_the_table_keeps_what_the_last_row_said_and_the_count_given():
    t = Path(tempfile.mkdtemp())
    H = db.connect(t / "h.db")
    base = {"sport": "cfb", "season": 2026, "period": "2026-11-07", "game_id": "401-box",
            "market": "rec_yds", "position": "WR"}
    rows = [dict(base, player="Jordan Smith", team="MICH", opponent="OSU", home=1, value=51.0),
            dict(base, player="Jordan Smith", team="OSU", opponent="MICH", home=0, value=9.0),
            dict(base, player="Some Receiver", team="OSU", opponent="MICH", home=0, value=60.0)]
    assert db.upsert_player_logs(H, rows) == 3, "the rows given, as before"
    H.commit()
    got = H.execute("SELECT team, value FROM player_game_logs WHERE player='Jordan Smith'").fetchall()
    assert [tuple(x) for x in got] == [("OSU", 9.0)], "the last row given, as the table kept before"
    gen = _gen(H)
    assert gen == 2, "two keys stored once each"
    db.upsert_player_logs(H, rows)
    H.commit()
    assert _gen(H) == gen, "the same rows again change nothing"


def test_a_row_missing_a_key_part_is_kept_and_keys_compare_as_the_table_does():
    a = {"sport": "cfb", "season": 2026, "period": "7", "game_id": "g", "player": None,
         "market": "rec_yds", "value": 1.0}
    b = dict(a, value=2.0)
    assert db.last_per_key([a, b]) == [a, b], "two NULL keys are two rows to SQLite"
    c = dict(a, player="P", season="2026", period=7, value=3.0)
    d = dict(a, player="P", season=2026, period="7", value=4.0)
    e = dict(a, player="Q", value=5.0)
    assert db.last_per_key([c, e, d]) == [d, e], "one key, in the order it first came, the last row"


def test_the_settle_ingest_checks_the_rows_the_table_would_keep():
    src = inspect.getsource(B.ingest_for_open)
    assert src.index("rows = _db.last_per_key(rows)") < src.index("if on_file(hconn, rows):")
    assert "last_per_key(rows)" in inspect.getsource(db.upsert_player_logs)


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
