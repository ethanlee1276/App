"""The purchased closes are read for the open bets' days only, and answer
the same (engine/db.closing_odds_by_date, closing_odds_all_books,
_day_windows; engine/ledger._close_days, settle_from_history;
engine/closebook.SameBookCloses).

The settle pass's grading took 346 seconds of a 493-second pass on Saturday
7 November. For every sport and market it graded, it read that market's
whole purchased tape twice (its own close, then the same book's), every
season bought, in Python, to look up the few days its open bets fall on.
What these hold:

  * read for a set of days, each reader holds exactly the whole read's keys
    for those days, quote for quote, and nothing else; a day that is not
    an ISO date names no rows; None reads everything, as before;
  * only those days' rows come back from the database;
  * the days are the union of the open bets' `close_dates`: a daily
    sport's own date, an NFL week's every game day; game markets and bets
    with no player or date add none;
  * the settle pass banks the same close with the bounded reads as with
    the whole ones, and reads only its bets' days.

Run directly: `python3 tests/test_the_closes_read_only_the_open_bets_days.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, ledger                                      # noqa: E402

DAYS = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07"]


def _q(day, hour, player, book, line, over, under, start_hour=23):
    return {"sport": "nba", "taken_at": f"{day}T{hour:02d}:00:00Z", "event_id": f"e-{day}",
            "home": "NYK", "away": "BOS", "player": player, "market": "points",
            "book": book, "line": line, "over_odds": over, "under_odds": under,
            "commence_time": f"{day}T{start_hour:02d}:30:00Z"}


def _tape():
    """Five days of two players, three books, a moved line, a late quote in
    play and an exchange's rung: everything the readers choose between."""
    conn = db.connect(":memory:")
    rows = []
    for i, day in enumerate(DAYS):
        for who, base in (("jalen brunson", 26.5), ("jayson tatum", 27.5)):
            rows += [
                _q(day, 15, who, "fanduel", base, -110, -110),
                _q(day, 15, who, "draftkings", base, -112, -108),
                _q(day, 20, who, "fanduel", base + (i % 2), -120 - i, 100 + i),
                _q(day, 21, who, "draftkings", base, -115, -105),
                _q(day, 21, who, "prophetx", base + 6, 300, -400),       # an exchange's rung
                _q(day, 23, who, "fanduel", base, -300, 240, start_hour=22),  # in play
            ]
    db.upsert_odds_history(conn, rows)
    return conn


class _Counting:
    """A history connection that counts the odds rows each read hands back."""
    def __init__(self, conn):
        self.conn, self.rows = conn, 0

    def execute(self, sql, args=()):
        cur = self.conn.execute(sql, args)
        if "FROM odds_history" not in sql:
            return cur
        return self._count(cur)

    def _count(self, cur):
        for r in cur:
            self.rows += 1
            yield r


def test_read_for_some_days_each_reader_holds_the_whole_reads_keys_for_them():
    conn = _tape()
    want = {"2026-11-04", "2026-11-06"}
    for read in (db.closing_odds_by_date, db.closing_odds_all_books):
        whole = read(conn, "nba", "points")
        part = read(conn, "nba", "points", days=want)
        assert set(part) == {k for k in whole if k[1] in want}, read.__name__
        assert all(part[k] == whole[k] for k in part), read.__name__
        assert read(conn, "nba", "points", days=None) == whole
        assert read(conn, "nba", "points", days=set()) == {}
        assert read(conn, "nba", "points", days={"2026-W45", ""}) == {}
        # The exchange's rung and the in-play price stay out, as in the whole read.
        if read is db.closing_odds_by_date:
            assert part[("jalen brunson", "2026-11-04")]["book"] != "prophetx"


def test_only_those_days_rows_come_back():
    conn = _Counting(_tape())
    db.closing_odds_by_date(conn, "nba", "points")
    whole = conn.rows
    conn.rows = 0
    db.closing_odds_by_date(conn, "nba", "points", days={"2026-11-07"})
    assert whole == 60 and conn.rows == 12, (whole, conn.rows)
    conn.rows = 0
    db.closing_odds_all_books(conn, "nba", "points", days={"2026-11-03", "2026-11-07"})
    assert conn.rows == 24


def test_the_days_are_every_open_bets_close_dates():
    hist = db.connect(":memory:")
    for day in ("2026-11-02", "2026-11-03", "2026-11-06"):
        db.upsert_games(hist, [
            {"sport": "nfl", "season": 2026, "period": "010", "game_id": f"g{day}",
             "home": "KC", "away": "DEN", "home_score": None, "away_score": None,
             "spread": 0.0, "total": 44.5, "roof": "", "surface": "", "temp": None,
             "wind": None, "extra": None, "date": day}])
    led = ledger.connect(":memory:")
    for sport, date, player, market in (
            ("nba", "2026-11-07", "Jalen Brunson", "points"),
            ("nba", "2026-11-06", "Josh Hart", "points"),
            ("nba", "2026-11-07", "Josh Hart", "rebounds"),
            ("nfl", "2026-W10", "Patrick Mahomes", "pass_yds"),
            ("nba", "2026-11-07", "NYK", "moneyline"),
            ("nba", None, "Mikal Bridges", "points")):
        led.execute("INSERT INTO bets (sport, date, player, market, status, category) "
                    "VALUES (?, ?, ?, ?, 'open', 'main')", (sport, date, player, market))
    days = ledger._close_days(hist, led.execute("SELECT * FROM bets").fetchall())
    assert days == {("nba", "points"): {"2026-11-06", "2026-11-07"},
                    ("nba", "rebounds"): {"2026-11-07"},
                    ("nfl", "pass_yds"): {"2026-11-02", "2026-11-03", "2026-11-06"}}, days


def _settle_one(bounded: bool):
    hist = _tape()
    db.upsert_games(hist, [
        {"sport": "nba", "season": 2026, "period": "2026-11-06", "game_id": "BOS@NYK-1106",
         "home": "NYK", "away": "BOS", "home_score": 110, "away_score": 104, "spread": 0.0,
         "total": 220.5, "roof": "", "surface": "", "temp": None, "wind": None, "extra": None}])
    db.upsert_player_logs(hist, [
        {"sport": "nba", "season": 2026, "period": "2026-11-06", "game_id": "BOS@NYK-1106",
         "player": "Jalen Brunson", "team": "NYK", "opponent": "BOS", "position": "G",
         "home": 1, "market": name, "value": v}
        for name, v in (("points", 31.0), ("min", 36.0))])
    led = ledger.connect(":memory:")
    ledger.configure_bankroll(led, starting=1000, unit_pct=1.0)
    led.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
        "stake_units, stake_dollars, status, category) VALUES "
        "('t','nba','2026-11-06','Jalen Brunson','points','OVER',26.5,'FanDuel',-110,"
        "0.1,1.0,'open','main')")
    led.commit()
    counting = _Counting(hist)
    saved = ledger._close_days
    if not bounded:
        ledger._close_days = lambda h, bets: {}
    try:
        assert ledger.settle_from_history(led, counting) == 1
    finally:
        ledger._close_days = saved
    row = led.execute("SELECT status, closing_line, closing_odds, closing_fair FROM bets").fetchone()
    return dict(row), counting.rows


def test_the_settle_banks_the_same_close_and_reads_only_its_bets_day():
    whole, read_whole = _settle_one(bounded=False)
    part, read_part = _settle_one(bounded=True)
    assert part == whole and part["status"] == "won", (part, whole)
    assert part["closing_line"] is not None and part["closing_odds"] is not None
    # Two reads of the market (the close, then the same book's): every row
    # of the tape each time, against the one day's.
    assert read_whole == 2 * 60 and read_part == 2 * 12, (read_whole, read_part)


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
