"""An exchange's ladder rung never becomes a prop's closing line.

The public receipts, 2026-11-05: 1,062 of 2,537 settled NBA picks carried
a close 3 or more away from their own line. Zach Edey's rebounds at 9.5
and 10.5 "closed" at 19.5; Davion Mitchell's threes at 0.5 and 1.5 closed
at 3.5. An exchange (Novig, ProphetX) posts a LADDER under its main
market where a sportsbook posts one number (`odds.is_exchange`), and both
close readers let the ladder in:

  * the purchased history (`db.closing_odds_by_date`) kept the day's last
    row, from whichever book wrote last. The prop tape writes a book only
    when its number moves, and an exchange moves most;
  * our own snapshots (`linemoves.closing_lines_by_date`) took the median
    of every quote at the last pre-game instant, rungs and all.

The board already refuses a rung (tests/test_an_exchange_rung_never_prices_
the_row.py). What these hold for the close:

  * each book's last pre-game quote counts once, and the close is the
    sportsbooks' number (`odds.market_centre`), however late a rung was
    written;
  * an exchange alone is still a market;
  * a settled NBA bet banks the sportsbooks' close, not the rung.

Run directly: `python3 tests/test_an_exchange_rung_never_sets_the_close.py`
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())

from engine import db, ledger, linemoves                           # noqa: E402
from engine.sources.oddsapi import normalize_name                   # noqa: E402

DAY = (dt.date.today() - dt.timedelta(days=2)).isoformat()
EDEY = normalize_name("Zach Edey")


def _hist():
    return db.connect(Path(tempfile.mkdtemp()) / "h.db")


def _quotes(H, rows, day=DAY):
    db.upsert_odds_history(H, [{
        "sport": "nba", "taken_at": f"{day}T{hh}:00:00Z", "event_id": "e1", "home": "MEM", "away": "LAL",
        "player": EDEY, "market": "reb", "book": book, "line": line,
        "over_odds": over, "under_odds": under} for hh, book, line, over, under in rows])
    H.commit()


def test_the_purchased_close_is_the_sportsbooks_number_however_late_a_rung_was_written():
    H = _hist()
    _quotes(H, [("22", "DraftKings", 9.5, -115, -105),
                ("22", "FanDuel", 9.5, -110, -110),
                ("23", "Novig", 19.5, 900, -2000)])          # the ladder's top rung, written last
    close = db.closing_odds_by_date(H, "nba", "reb")[(EDEY, DAY)]
    assert close["line"] == 9.5 and close["book"] in ("DraftKings", "FanDuel"), close


def test_each_books_last_quote_counts_and_the_closest_to_even_sets_the_number():
    H = _hist()
    _quotes(H, [("20", "DraftKings", 8.5, -120, 100),
                ("22", "DraftKings", 9.5, -110, -110),      # DraftKings moved: its later quote stands
                ("22", "FanDuel", 10.5, 140, -170),
                ("23", "ProphetX", 4.5, -900, 600)])
    close = db.closing_odds_by_date(H, "nba", "reb")[(EDEY, DAY)]
    assert (close["line"], close["book"]) == (9.5, "DraftKings"), close


def test_an_exchange_alone_is_still_a_market():
    H = _hist()
    _quotes(H, [("22", "Novig", 9.5, -110, -110)])
    assert db.closing_odds_by_date(H, "nba", "reb")[(EDEY, DAY)]["line"] == 9.5
    assert db.close_quote([{"book": "Novig", "line": 9.5, "over_odds": -110, "under_odds": -110,
                            "taken_at": "t"}])["line"] == 9.5


def _snap(ts, book, line):
    return {"ts": ts, "player": "Zach Edey", "market": "reb", "book": book, "line": line,
            "over_odds": -110, "under_odds": -110}


def test_the_snapshot_close_is_the_sportsbooks_median_not_the_ladders():
    t = dt.datetime.fromisoformat(f"{DAY}T23:00:00+00:00").timestamp()
    rows = [_snap(t, "DraftKings", 9.5), _snap(t, "FanDuel", 9.5),
            _snap(t, "Novig", 12.5), _snap(t, "Novig", 15.5), _snap(t, "Novig", 19.5)]
    closes = linemoves.closing_lines_by_date(rows)
    (key, val), = closes.items()
    assert val == 9.5, f"every quote's median would be 12.5: {closes}"
    only = linemoves.closing_lines_by_date([_snap(t, "Novig", 12.5), _snap(t, "ProphetX", 13.5)])
    assert list(only.values()) == [13.0], "with no sportsbook quoting, the exchanges are the market"


def test_the_dry_run_names_the_books_at_the_snapshot_close():
    """The snapshot half of the dry run's explanation: the books at the day's
    last pre-game read, the exchange's rungs listed apart."""
    t = dt.datetime.fromisoformat(f"{DAY}T23:00:00+00:00").timestamp()
    rows = [_snap(t - 600, "DraftKings", 8.5), _snap(t, "DraftKings", 9.5), _snap(t, "FanDuel", 10.5),
            _snap(t, "Novig", 12.5), _snap(t, "Novig", 19.5)]
    books = linemoves.closing_books_by_date(rows)
    key = (EDEY, "reb", linemoves._slate_day(rows[0]))
    assert set(books) == set(linemoves.closing_lines_by_date(rows)), "the same keys as the close"
    assert books[key] == (t, [("DraftKings", 9.5), ("FanDuel", 10.5), ("Novig", 12.5), ("Novig", 19.5)])
    b = {"sport": "nba", "market": "reb", "leg": None}
    why = ledger._snapshot_why(books, b, [key[2]], EDEY)
    assert why.startswith("snapshots, last pre-game read ") and "DraftKings 9.5, FanDuel 10.5" in why, why
    assert why.endswith("; exchange, left out: Novig 12.5, Novig 19.5"), why
    assert ledger._snapshot_why(books, b, ["2001-01-01"], EDEY).startswith("snapshots: this bet's"), \
        "a day with no read says so"
    lone = linemoves.closing_books_by_date([_snap(t, "Novig", 12.5)])
    assert ledger._snapshot_why(lone, b, [key[2]], EDEY).endswith("no sportsbook; exchange only: Novig 12.5")


def test_a_settled_nba_bet_banks_the_sportsbooks_close():
    t = Path(tempfile.mkdtemp())
    saved = ledger.DEFAULT_DB
    ledger.DEFAULT_DB = str(t / "l.db")
    try:
        L = ledger.connect(t / "l.db")
        ledger.configure_bankroll(L, starting=1000, unit_pct=1)
        H = db.connect(t / "h.db")
        L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, "
                  "stake_units, stake_dollars, status, category, team, book) VALUES "
                  "(?, 'nba', ?, ?, 'Zach Edey', 'reb', 'OVER', 9.5, -110, 1, 10, 'open', 'likely', "
                  "'MEM', 'DraftKings')", (f"{DAY}T12:00:00", DAY, DAY))
        L.commit()
        H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, "
                  "away_score) VALUES ('nba', 2026, ?, 'g1', ?, 'MEM', 'LAL', 110, 104)", (DAY, DAY))
        db.upsert_player_logs(H, [{"sport": "nba", "season": 2026, "period": DAY, "game_id": "g1",
                                   "player": "Zach Edey", "team": "MEM", "opponent": "LAL",
                                   "position": "C", "home": 1, "market": m, "value": v}
                                  for m, v in (("reb", 12.0), ("min", 31.0))])
        H.commit()
        _quotes(H, [("22", "DraftKings", 9.5, -115, -105),
                    ("22", "FanDuel", 9.5, -110, -110),
                    ("23", "Novig", 19.5, 900, -2000)])
        assert ledger.settle_from_history(L, H) == 1
        b = L.execute("SELECT status, actual, closing_line FROM bets").fetchone()
        assert (b["status"], b["actual"]) == ("won", 12.0), dict(b)
        assert b["closing_line"] == 9.5, f"the rung's 19.5 banked as the close: {dict(b)}"
    finally:
        ledger.DEFAULT_DB = saved


def _settled(closing_line):
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, stake_units, "
              "stake_dollars, status, category, team, book, actual, pnl_units, closing_line) VALUES "
              "(?, 'nba', ?, ?, 'Zach Edey', 'reb', 'OVER', 9.5, -110, 1, 10, 'won', 'likely', 'MEM', "
              "'DraftKings', 12, 0.91, ?)", (f"{DAY}T12:00:00", DAY, DAY, closing_line))
    L.commit()
    return L, db.connect(t / "h.db")


def test_the_repair_rereads_a_settled_close_at_the_sportsbooks_number():
    L, H = _settled(19.5)                          # what the old reader banked
    _quotes(H, [("22", "DraftKings", 9.5, -115, -105),
                ("22", "FanDuel", 9.5, -110, -110),
                ("23", "Novig", 19.5, 900, -2000)])
    dry = ledger.repair_closing_lines(L, apply=False, hist_conn=H, sport="nba")
    assert (dry["overwritten"], dry["agreed"], dry["applied"]) == (1, 0, False), dry
    assert dry["overwritten_sample"][0][-2:] == (19.5, 9.5), dry["overwritten_sample"]
    # The dry run names the books behind the new close (6 November), and
    # how far the closes move, by market.
    why = dry["overwritten_why"][0]
    assert why.startswith(f"harvest {DAY}: DraftKings 9.5 (-115/-105), FanDuel 9.5 (-110/-110)*"), why
    assert why.endswith("Novig 19.5 (+900/-2000) [exchange]"), why
    assert dry["moves"] == {"reb": (1, 10.0)}, dry["moves"]
    assert L.execute("SELECT closing_line FROM bets").fetchone()[0] == 19.5, "a dry run writes nothing"
    done = ledger.repair_closing_lines(L, apply=True, hist_conn=H, sport="nba")
    assert done["overwritten"] == 1 and done["applied"], done
    assert done["overwritten_why"] == [], "the write reads nothing more"
    row = L.execute("SELECT closing_line, status, pnl_units FROM bets").fetchone()
    assert (row["closing_line"], row["status"], row["pnl_units"]) == (9.5, "won", 0.91), \
        "the close changes, the grade and the money never do"
    again = ledger.repair_closing_lines(L, apply=False, hist_conn=H, sport="nba")
    assert (again["agreed"], again["overwritten"]) == (1, 0), again


def test_a_close_the_repair_cannot_find_is_kept():
    L, H = _settled(7.5)
    r = ledger.repair_closing_lines(L, apply=True, hist_conn=H, sport="nba")
    assert (r["unchecked"], r["overwritten"], r["filled"]) == (1, 0, 0), r
    assert L.execute("SELECT closing_line FROM bets").fetchone()[0] == 7.5


def test_settling_and_the_line_repair_read_one_rule():
    import inspect
    settle = inspect.getsource(ledger.settle_from_history)
    repair = inspect.getsource(ledger.repair_closing_lines)
    assert "_close_line_of(" in settle and "_close_line_of(" in repair
    launch = (Path(__file__).resolve().parents[1] / "launch.py").read_text(encoding="utf-8")
    assert '"--repair-close-lines"' in launch and 'repair_close_lines(apply="--apply" in argv' in launch
    i = launch.index("def repair_close_lines(")
    assert '_backed_up("repair-close-lines", history=False)' in launch[i:i + 1500], \
        "an --apply that edits the journal backs it up first (the journal alone: it never writes history.db)"


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
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
