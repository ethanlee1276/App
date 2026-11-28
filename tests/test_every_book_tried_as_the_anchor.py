"""Would Caesars make a backup sharp book? Every book tried as the anchor.

Ethan, 2026-11-03, "5, yes": test Caesars as a backup reference for where
Pinnacle has no price, and change nothing unless it wins
(engine/anchortest.py). What these hold:

  * a book is one book whatever a stored row called it;
  * a close is each book's last pre-game two-way quote, dated by the game's
    own day in New York (a 10:30 p.m. tip is not the next day's game);
  * a result is dated by the games table, the period itself, or the NFL
    schedule;
  * the anchor rule is the live one: the anchor's de-vigged pair against the
    best price at another book, a bet inside the sharp bands, the anchor
    never the price it bets;
  * the bar is the one written in the module, and a book that only looks
    good on a handful of bets is not ranked;
  * it writes nothing.

Run directly: `python3 tests/test_every_book_tried_as_the_anchor.py`
"""
import inspect
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import anchortest as A                                # noqa: E402
from engine import db                                             # noqa: E402


def _conn():
    d = tempfile.mkdtemp(prefix="anchor-")
    return db.connect(os.path.join(d, "history.db"))


def _quote(conn, sport, player, market, book, line, over, under,
           taken="2026-10-20T22:00:00Z", start="2026-10-20T23:30:00Z", event="e1"):
    conn.execute(
        "INSERT OR REPLACE INTO odds_history (sport, taken_at, event_id, home, away, player, "
        "market, book, line, over_odds, under_odds, commence_time) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (sport, taken, event, "AAA", "BBB", player, market, book, line, over, under, start))


def _log(conn, sport, player, market, value, season=2026, period="2026-10-20",
         game_id="g1", team="AAA"):
    conn.execute(
        "INSERT OR REPLACE INTO player_game_logs (sport, season, period, game_id, player, team, "
        "opponent, position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (sport, season, period, game_id, player, team, "BBB", "G", 1, market, value))


# --- names and days -------------------------------------------------------------
def test_a_book_is_one_book_whatever_the_row_called_it():
    assert A.book_key("Caesars") == A.book_key("William Hill (US)") == A.book_key("williamhill_us") == "caesars"
    assert A.book_key("theScore Bet") == A.book_key("espnbet") == "thescorebet"
    assert A.book_key("DraftKings") == "draftkings"


def test_a_late_tip_is_dated_by_its_own_night():
    assert A._eastern_date("2026-11-04T02:30:00Z") == "2026-11-03"
    assert A._eastern_date("2026-11-03T23:00:00Z") == "2026-11-03"
    assert A._eastern_date(None) is None and A._eastern_date("not a date") is None


def test_a_close_is_the_last_pregame_two_way_quote_of_the_day():
    conn = _conn()
    # The 22:00 quote is replaced by the 23:00 one; the 23:45 one is in play.
    _quote(conn, "nba", "Jane Doe", "points", "Caesars", 20.5, -110, -110, taken="2026-10-20T22:00:00Z")
    _quote(conn, "nba", "Jane Doe", "points", "Caesars", 20.5, -120, 100, taken="2026-10-20T23:00:00Z")
    _quote(conn, "nba", "Jane Doe", "points", "Caesars", 20.5, -300, 220, taken="2026-10-20T23:45:00Z")
    # One side only: not a pair, not a close.
    _quote(conn, "nba", "Jane Doe", "points", "FanDuel", 20.5, -110, 0)
    # A tip after midnight UTC belongs to the night it was played.
    _quote(conn, "nba", "Jane Doe", "points", "BetMGM", 21.5, -105, -115,
           taken="2026-10-21T01:30:00Z", start="2026-10-21T02:30:00Z", event="e2")
    out = A.closes(conn, "nba", "points")
    assert out == {("jane doe", "2026-10-20"): {20.5: {"caesars": (-120, 100)},
                                                21.5: {"betmgm": (-105, -115)}}}, out


def test_a_result_is_dated_by_the_games_table_the_period_or_the_schedule():
    conn = _conn()
    _log(conn, "nba", "Jane Doe", "points", 25)                                   # the period is the date
    _log(conn, "nfl", "John Roe", "rec_yds", 70, season=2026, period="7", game_id="n1")
    conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, date) "
                 "VALUES ('nfl', 2026, '7', 'n1', 'AAA', 'BBB', '2026-10-19')")
    _log(conn, "nfl", "Jim Poe", "rec_yds", 40, season=2026, period="8", game_id="n2")   # no games row
    assert A.results(conn, "nba", "points") == {("jane doe", "2026-10-20"): 25.0}
    got = A.results(conn, "nfl", "rec_yds", nfl_dates=lambda: {(2026, 8, "AAA"): "2026-10-26"})
    assert got == {("john roe", "2026-10-19"): 70.0, ("jim poe", "2026-10-26"): 40.0}, got
    assert A.results(conn, "nfl", "rec_yds") == {("john roe", "2026-10-19"): 70.0}


# --- the anchor rule ------------------------------------------------------------------
def test_the_anchor_bets_the_best_price_at_another_book_inside_the_bands():
    """Caesars -110/-110 is a fair 50%. DraftKings' +120 over is 10% EV:
    inside 2%-15%, bet, and the over came in (+1.2 units). DraftKings as
    the anchor (+120/-150) prices the under at 56.9%, so Caesars' -110
    under is 8.6% EV: bet, and lost (-1 unit)."""
    acc = {}
    A.score_case(acc, 20.5, {"caesars": (-110, -110), "draftkings": (120, -150)}, 25.0, "2026-10-20")
    c = acc["caesars"]
    assert (c["bets"], c["won"], round(c["units"], 4)) == (1, 1, 1.2)
    d = acc["draftkings"]
    assert (d["bets"], d["won"], round(d["units"], 4)) == (1, 0, -1.0)
    assert {k: [n, round(u, 4)] for k, (n, u) in c["by_day"].items()} == {"2026-10-20": [1, 1.2]}


def test_the_anchor_is_never_the_price_it_bets_and_a_push_is_no_bet():
    acc = {}
    # Only one book: nothing else to take, so no bet.
    A.score_case(acc, 20.5, {"caesars": (-110, -110)}, 25.0, "d")
    assert acc["caesars"]["bets"] == 0
    acc = {}
    A.score_case(acc, 20.0, {"caesars": (-110, -110), "draftkings": (120, -150)}, 20.0, "d")
    assert acc == {}, "a push scores nothing"


def test_a_gap_past_the_bands_is_a_broken_price_and_not_a_bet():
    acc = {}
    A.score_case(acc, 20.5, {"caesars": (-110, -110), "draftkings": (200, -300)}, 25.0, "d")
    assert acc["caesars"]["bets"] == 0, "50% at +200 is 50% EV: past SHARP_MAX_EV"


def test_calibration_pairs_the_anchor_with_the_other_books_average():
    acc = {}
    books = {"caesars": (-150, 130), "draftkings": (-110, -110), "fanduel": (-110, -110)}
    A.score_case(acc, 20.5, books, 25.0, "d")          # the over came in
    assert acc["caesars"]["ll_n"] == 1
    assert acc["caesars"]["ll_diff"] < 0, "the anchor leaned over and was right: lower loss"
    assert acc["draftkings"]["ll_diff"] > 0


# --- the bar ------------------------------------------------------------------------
def _row(book, bets, roi, roi_t, ll_gap, ll_t):
    return {"book": book, "bets": bets, "won": 0, "lost": 0, "units": 0.0, "roi": roi,
            "roi_t": roi_t, "ll_lines": 1000, "ll_gap": ll_gap, "ll_t": ll_t}


def test_caesars_holds_only_when_every_part_of_the_bar_does():
    good = _row("caesars", 400, 0.05, 2.6, -3.0, -2.4)
    assert A.verdict([good, _row("draftkings", 400, 0.01, 0.5, 1.0, 1.0)]) == (True, "holds")
    ok, why = A.verdict([_row("caesars", 120, 0.05, 2.6, -3.0, -2.4)])
    assert not ok and "120 bets, under 200" in why
    ok, why = A.verdict([_row("caesars", 400, 0.02, 1.1, -3.0, -2.4)])
    assert not ok and "t 1.1" in why
    ok, why = A.verdict([_row("caesars", 400, 0.05, 2.6, 0.4, 0.3)])
    assert not ok and "does not beat the other books' average" in why
    ok, why = A.verdict([good, _row("fanduel", 300, 0.08, 2.1, -1.0, -1.0)])
    assert not ok and "a higher ROI as the anchor: fanduel" in why
    # A book on a handful of bets is listed, never ranked above it.
    assert A.verdict([good, _row("fliff", 12, 0.40, 1.0, -1.0, -1.0)])[0]
    assert A.verdict([])[0] is False


def test_the_bar_is_the_one_written_before_the_first_run():
    doc = A.__doc__
    assert "THE BAR, WRITTEN BEFORE ITS FIRST RUN" in doc
    assert A.MIN_BETS == 200 and A.MIN_T == 2.0
    from engine import gamebets
    src = inspect.getsource(A.score_case)
    assert "SHARP_MIN_EV <= ev <= SHARP_MAX_EV" in src, "the live bands, not new ones"
    assert gamebets.SHARP_MIN_EV == 0.02 and gamebets.SHARP_MAX_EV == 0.15


# --- end to end, and read-only ----------------------------------------------------------
def test_a_whole_run_reads_every_sport_and_says_its_verdict():
    conn = _conn()
    for i in range(6):
        day = f"2026-10-{10 + i:02d}"
        p = f"Player {i}"
        _quote(conn, "nba", p, "points", "Caesars", 20.5, -110, -110,
               taken=f"{day}T22:00:00Z", start=f"{day}T23:30:00Z", event=f"e{i}")
        _quote(conn, "nba", p, "points", "DraftKings", 20.5, 120, -150,
               taken=f"{day}T22:00:00Z", start=f"{day}T23:30:00Z", event=f"e{i}")
        _log(conn, "nba", p, "points", 25 if i % 2 == 0 else 15, period=day, game_id=f"g{i}")
    conn.commit()
    said = []
    rep = A.run(conn, say=said.append)
    nba = rep["nba"]
    assert nba["lines"] == 6
    c = next(r for r in nba["rows"] if r["book"] == "caesars")
    assert (c["bets"], c["won"], c["lost"]) == (6, 3, 3)
    assert nba["holds"] is False and "6 bets, under 200" in nba["verdict"]
    text = "\n".join(said)
    assert "nba: 6 lines with two or more books and a result" in text
    assert "Caesars as a backup anchor in nba: does not hold" in text


def test_it_writes_nothing():
    conn = _conn()
    _quote(conn, "nba", "Jane Doe", "points", "Caesars", 20.5, -110, -110)
    _log(conn, "nba", "Jane Doe", "points", 25)
    conn.commit()
    before = conn.total_changes
    A.run(conn, say=lambda _l: None)
    assert conn.total_changes == before
    src = inspect.getsource(A.main)
    assert '?mode=ro", uri=True)' in src, "the box command opens history.db read-only"


def test_the_runbook_and_the_catchup_run_it():
    line = "cd /srv/qellys && sudo -u qellys nice -n 19 python3 -m engine.anchortest"
    assert line in (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert line in (ROOT / "tools" / "catchup.sh").read_text(encoding="utf-8")
    assert "catchup.sh JU" in (ROOT / "docs" / "RUN_NEXT.md").read_text(encoding="utf-8")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
