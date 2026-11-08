"""The two-leg backtest pairs again only the days whose graded picks
changed (engine/twoleg.backtest's ``memo``; engine/ledger._two_leg_backtest).

The record export's sampler at 20:21 on Saturday 7 November: 154.7 seconds,
55.8 of them the two-leg record, its backtest rerun over every day of the
record once its hour was up, every pair of every day's picks priced again
when only that day's had changed. A day's parlays are a function of its own
picks. What these hold:

  * a run with a memo gives exactly what a run without one gives, to the
    last digit, on a record of many days, sports and both pools;
  * the next run pairs again only the day whose picks changed, and still
    matches a full run;
  * the memo keeps only the days the run read, and a changed rule (another
    per_kind) is never served from it;
  * the export keeps the memo beside its cache, and whose journal it is.

Run directly: `python3 tests/test_the_two_leg_backtest_pairs_only_the_days_that_changed.py`
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger, twoleg as T                             # noqa: E402

TEAMS = (("DET", "MIN"), ("BUF", "MIA"), ("KC", "LV"), ("SF", "LA"), ("PHI", "DAL"), ("BAL", "CIN"))


def _journal(days=12):
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    for d in range(1, days + 1):
        day = f"2099-10-{d:02d}"
        for sport in ("nba", "nfl"):
            for i, (team, _opp) in enumerate(TEAMS):
                for cat, odds, p in (("likely", -180 - i * 10, 0.74 - i * 0.01),
                                     ("main", 110 + i * 15, 0.52 + i * 0.01)):
                    won = (d + i + (cat == "main")) % 3 != 0
                    conn.execute(
                        "INSERT INTO bets (ts, sport, date, game_day, player, team, market, side, line, book,"
                        " odds, hit_prob, grade, stake_units, stake_dollars, status, pnl_units, category)"
                        " VALUES ('t',?,?,?,?,?,'points','OVER',10.5,'DK',?,?,'Play',0.5,5,?,?,?)",
                        (sport, day, day, f"{sport}{cat}{i}", team, odds, p,
                         "won" if won else "lost", 0.5 if won else -0.5, cat))
    conn.commit()
    games = {}
    for d in range(1, days + 1):
        for sport in ("nba", "nfl"):
            for team, opp in TEAMS:
                games[(sport, f"2099-10-{d:02d}", team)] = opp
                games[(sport, f"2099-10-{d:02d}", opp)] = team
    return conn, games


def test_a_run_with_a_memo_is_a_full_run_to_the_digit():
    conn, games = _journal()
    full = T.backtest(conn, since="2099-01-01", games=games)
    memo = {}
    first = T.backtest(conn, since="2099-01-01", games=games, memo=memo)
    assert first == full and full["rows"], full
    assert len(memo) >= 20, len(memo)
    again = T.backtest(conn, since="2099-01-01", games=games, memo=memo)
    assert again == full


def test_the_next_run_pairs_again_only_the_changed_day():
    conn, games = _journal()
    memo = {}
    T.backtest(conn, since="2099-01-01", games=games, memo=memo)
    conn.execute("UPDATE bets SET status='lost', pnl_units=-0.5 WHERE date='2099-10-07' AND sport='nba'")
    conn.commit()
    paired = []
    real = T._group_tickets

    def counting(sport, pool, legs, min_lift, per_kind):
        paired.append((sport, legs[0]["game_date"] if legs else None, pool))
        return real(sport, pool, legs, min_lift, per_kind)
    T._group_tickets = counting
    try:
        got = T.backtest(conn, since="2099-01-01", games=games, memo=memo)
    finally:
        T._group_tickets = real
    assert paired and {(s, d) for s, d, _p in paired} == {("nba", "2099-10-07")}, paired
    assert got == T.backtest(conn, since="2099-01-01", games=games)


def test_the_memo_keeps_what_the_run_read_and_a_changed_rule_is_not_served():
    conn, games = _journal()
    memo = {"nba|1999-01-01|likely": {"fp": "stale", "t": [["same_game", 9.9, [9.9], 1]]}}
    T.backtest(conn, since="2099-10-06", games=games, memo=memo)
    assert all(k.split("|")[1] >= "2099-10-06" for k in memo), "only the window's days"
    assert "nba|1999-01-01|likely" not in memo
    one = T.backtest(conn, since="2099-10-06", games=games, memo=memo, per_kind=1)
    assert one == T.backtest(conn, since="2099-10-06", games=games, per_kind=1)


def test_the_export_keeps_the_memo_beside_its_cache():
    src = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
    i = src.index("def _two_leg_backtest(")
    body = src[i:src.index("\ndef ", i + 1)]
    assert 'memo_path = cache.with_name("two_leg_days.json")' in body
    assert "twoleg.backtest(conn, since=RECORD_EPOCH, games=games, memo=memo)" in body
    assert 'held_memo.get("db") == dbfile' in body and 'held_memo.get("v") == twoleg.BACKTEST_VERSION' in body
    json.dumps({"ok": True})


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
