"""closecheck.py: the picks that lost the close, sized, listed and flagged.

Ethan's box run of the loss audit, 2026-09-29: Most Likely picks that lost
the close hit 18% and 12% where we claimed 62%. closecheck.py buckets the
close by the size of the move, lists every lost-the-close bet with its final
number, flags a scratch graded zero, says whether the final sat nearer the
close than our line, and counts which markets never get a close. Offline,
on a fixture ledger in a temp directory — never the box's.

Run directly: `python3 tests/test_the_close_check_tells_a_scratch_from_news_from_a_bad_close.py`
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import closecheck as CC                                        # noqa: E402
from engine import ledger                                      # noqa: E402


def _fixture(path):
    conn = ledger.connect(path)
    rows = [
        # (cat, sport, date, player, market, side, line, odds, closing_line, closing_odds, actual, status)
        # THE SCRATCH: 5.5 receptions, books dropped it to 2.5 and he logged 0 — graded lost.
        ("likely_live", "nfl", "2026-W03", "Scratch Guy", "receptions", "OVER", 5.5, -150, 2.5, -140, 0.0, "lost"),
        # THE NEWS: 4.5 → 3.5, he caught 3 — the final sat nearer the close.
        ("likely_live", "nfl", "2026-W03", "News Guy", "receptions", "OVER", 4.5, -160, 3.5, -130, 3.0, "lost"),
        # THE BAD CLOSE: 60.5 yards closing 20.5 (?) and he ran for 58 — nearer OUR line.
        ("likely_live", "nfl", "2026-W03", "Bad Close", "rush_yds", "OVER", 60.5, -150, 20.5, None, 58.0, "lost"),
        # Lost the close by 2+ and still won.
        ("likely_live", "nfl", "2026-W02", "Lucky Guy", "rec_yds", "OVER", 50.5, -150, 48.0, None, 70.0, "won"),
        # Beat the close by a point, won.
        ("likely_live", "nfl", "2026-W02", "Good Bet", "receptions", "OVER", 4.5, -150, 5.5, -170, 6.0, "won"),
        # A home run over: the line cannot move, the price did (+400 → +300) — beat on price only.
        ("likely_live", "mlb", "2026-09-20", "Slugger", "home_runs", "OVER", 0.5, 400, 0.5, 300, 1.0, "won"),
        # An under that lost the close: line fell? no — for an under the line RISING is adverse.
        ("likely_live", "mlb", "2026-09-20", "Under Man", "total_bases", "UNDER", 1.5, -130, 2.5, None, 3.0, "lost"),
        # No close captured, twice — one market never gets one.
        ("likely_live", "mlb", "2026-09-21", "No Close A", "hits", "OVER", 0.5, -200, None, None, 1.0, "won"),
        ("likely_live", "mlb", "2026-09-21", "No Close B", "hits", "OVER", 0.5, -200, None, None, 0.0, "lost"),
        # A 0 on a low line is an ordinary night, not a scratch.
        ("likely_live", "mlb", "2026-09-22", "Oh For Four", "hits", "OVER", 0.5, -200, 0.5, -180, 0.0, "lost"),
        # Same as the close.
        ("likely_live", "nfl", "2026-W02", "Same Guy", "rec_yds", "OVER", 40.5, -150, 40.5, None, 45.0, "won"),
        # Another book: the one board, one lost-the-close row with a tier.
        ("board", "nfl", "2026-W03", "Board Guy", "rush_yds", "OVER", 45.5, -140, 44.0, None, 30.0, "lost"),
        # Not settled, not counted.
        ("likely_live", "nfl", "2026-W04", "Open Guy", "receptions", "OVER", 4.5, -150, None, None, None, "open"),
        ("likely_live", "nfl", "2026-W03", "Void Guy", "receptions", "OVER", 4.5, -150, 1.5, None, None, "void"),
    ]
    for cat, sport, date, player, market, side, line, odds, cl, co, actual, status in rows:
        pnl = 0.1 * (100 / abs(odds) if odds < 0 else odds / 100) if status == "won" else -0.1 if status == "lost" else 0
        conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, odds, hit_prob, stake_units, "
                     "status, actual, pnl_units, closing_line, closing_odds, category, grade) VALUES "
                     "('t',?,?,?,?,?,?,?,0.62,0.1,?,?,?,?,?,?,'Strong')",
                     (sport, date, player, market, side, line, odds, status, actual, pnl, cl, co, cat))
    conn.commit()
    conn.close()


def _report(**kw):
    path = Path(tempfile.mkdtemp()) / "ledger.db"
    _fixture(path)
    return CC.check(CC.open_ledger(path), **kw), path


def test_the_ledger_is_opened_read_only():
    _rep, path = _report()
    conn = CC.open_ledger(path)
    try:
        conn.execute("UPDATE bets SET status='won'")
        raise AssertionError("the check's connection wrote to the ledger")
    except sqlite3.OperationalError as exc:
        assert "readonly" in str(exc).replace(" ", "").lower()


def test_the_close_is_bucketed_by_the_size_of_the_move():
    rep, _ = _report()
    bk = rep["books"]["Most Likely, staked"]
    b = bk["buckets"]
    assert b["lost the close by 2+ pts"]["n"] == 3          # Scratch Guy, Bad Close, Lucky Guy
    assert b["lost the close by 2+ pts"]["w"] == 1          # Lucky Guy won it anyway
    assert "lost the close by under 1 pt" not in b           # an empty bucket is not printed
    assert b["lost the close by 1-1.9 pts"]["n"] == 2       # News Guy, and the under whose line rose a point
    assert b["beat the close by 1-1.9 pts"]["n"] == 1       # Good Bet
    assert b["beat the close on price only"]["n"] == 1      # Slugger
    assert b["lost the close on price only"]["n"] == 1      # Oh For Four: 0.5 → 0.5, but -200 closed -180
    assert b["same as the close"]["n"] == 1                 # Same Guy
    assert b["no close captured"]["n"] == 2
    # Only settled bets: the open and the void are not counted anywhere.
    assert sum(s["n"] for s in b.values()) == 11
    assert "The one board" in rep["books"] and rep["books"]["The one board"]["total"]["n"] == 1


def test_a_scratch_is_flagged_and_an_ordinary_zero_is_not():
    rep, _ = _report()
    bk = rep["books"]["Most Likely, staked"]
    names = {b["player"] for b in bk["scratch"]}
    assert names == {"Scratch Guy"}, names
    # 0 hits on a 0.5 line is a night, not a scratch; 3 catches on 4.5 is a loss.
    assert "Oh For Four" not in names and "News Guy" not in names
    assert CC.SCRATCH_LINE == 2.5


def test_the_final_number_says_whether_the_market_knew():
    rep, _ = _report()
    bk = rep["books"]["Most Likely, staked"]
    # Of the five lost-the-close bets with a line move: Scratch Guy (0 is nearer 2.5),
    # News Guy (3 nearer 3.5), Under Man (3 nearer 2.5) say the market knew;
    # Bad Close (58 nearer 60.5) and Lucky Guy (70 nearer 50.5) say our line.
    assert bk["judged"] == 5 and bk["knew"] == 3
    assert CC.nearer_the_close({"line": 60.5, "closing_line": 20.5, "actual": 58.0}) is False
    assert CC.nearer_the_close({"line": 4.5, "closing_line": 4.5, "actual": 3.0}) is None


def test_the_lost_bets_are_listed_and_the_markets_without_a_close_are_counted():
    rep, _ = _report()
    text = CC.render(rep)
    assert "Scratch Guy" in text and "SCRATCH?" in text
    assert "5.5 → 2.5" in text and "-150 → -140" in text and "final      0  lost" in text
    assert "60.5 → 20.5" in text
    assert "MLB hits" in text and "2 / 3" in text and " 67%" in text   # two of three hits bets had no close
    assert "lost the close: 1 bet\n" in text                          # the one board's row, singular
    assert "lost the close: 6 bets" in text
    # The cap holds and lifts.
    assert "… and" not in text
    short = CC.render(rep, cap=2)
    assert "… and 4 more (--all lists them)" in short


def test_main_prints_and_never_writes():
    _rep, path = _report()
    before = path.read_bytes()
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = CC.main(["--db", str(path)])
    assert rc == 0 and "CLOSE CHECK" in buf.getvalue() and "=== Most Likely, staked" in buf.getvalue()
    assert path.read_bytes() == before
    with contextlib.redirect_stdout(io.StringIO()):
        assert CC.main(["--db", str(path.parent / "nothere.db")]) == 1


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
    print(f"{len(fns)} tests passed.")
