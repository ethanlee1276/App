"""The model-versus-market scoreboard — does this beat the closing line?

The most persuasive thing a paid product can show, and persuasive
exactly because it can come out badly. A win-loss record over a few
hundred bets is mostly variance wearing a percentage sign; closing-line
value grades the DECISION the moment the game starts and accrues on
every settled pick rather than only the winners.

What this file pins is the honesty, because every failure mode here is
a flattering one:

  * THE SAMPLE SIZE RIDES WITH EVERY NUMBER. A +0.4 over nine bets and
    a +0.4 over four hundred are different facts.
  * THE VERDICT IS GATED, THE NUMBER IS NOT. Below CLV_MIN_N the row
    still shows its average and declines to CALL it. Hiding a number
    until it looks good is the failure this page exists to refuse.
  * MISSING COVERAGE IS A ROW, NOT AN ABSENCE. A market with settled
    picks and no stored closes is one we cannot grade — it must say so
    rather than vanish, which is how the touchdown board hid a broken
    harvest for its whole existence.

Run directly: `python3 tests/test_clvboard.py`
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import clvboard, ledger                           # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


class _Book:
    def __init__(self):
        self.conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
        self.n = 0

    def bet(self, sport, market, side, line, close, status="won"):
        self.n += 1
        self.conn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line,"
            " book, odds, stake_units, stake_dollars, status, category,"
            " closing_line, pnl_units) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("2026-08-20T10:00:00", sport, "2026-08-20", f"P{self.n}", market,
             side, line, "DK", -110, 1.0, 0.0, status, "main", close,
             1.0 if status == "won" else -1.0))
        self.conn.commit()
        return self


def test_a_market_with_no_stored_closes_is_a_row_not_an_absence():
    """The exact shape of the bug the touchdown board carried for its
    whole existence: settled picks, no closes, and nothing on any page
    saying the market could not be graded."""
    b = _Book()
    for _ in range(4):
        b.bet("nfl", "anytime_td", "OVER", 0.5, None, "lost")
    row = clvboard.scoreboard(b.conn)["rows"][0]
    assert row["market"] == "anytime_td"
    assert row["settled"] == 4 and row["with_close"] == 0
    assert row["coverage"] == 0.0
    assert row["avg_clv"] is None and row["beat_rate"] is None
    assert row["ready"] is False


def test_the_verdict_is_gated_but_the_number_is_shown():
    b = _Book()
    for _ in range(6):
        b.bet("nfl", "rec_yds", "OVER", 50.0, 51.0)
    row = clvboard.scoreboard(b.conn)["rows"][0]
    assert row["avg_clv"] == 1.0, "the average was hidden below the bar"
    assert row["ready"] is False, "six bets was called a finding"
    assert row["with_close"] == 6


def test_clv_is_side_aware():
    """An over wants the line to rise; an under wants it to fall.
    Positive must always mean the market moved our way."""
    b = _Book()
    b.bet("mlb", "strikeouts", "UNDER", 6.5, 6.0)
    b.bet("mlb", "total_bases", "OVER", 1.5, 2.0)
    rows = {r["market"]: r for r in clvboard.scoreboard(b.conn)["rows"]}
    assert rows["strikeouts"]["avg_clv"] == 0.5
    assert rows["total_bases"]["avg_clv"] == 0.5


def test_rows_sort_by_evidence_not_by_how_good_they_look():
    b = _Book()
    b.bet("mlb", "hits", "OVER", 0.5, 5.0)          # one huge, flattering row
    for _ in range(8):
        b.bet("nfl", "rec_yds", "OVER", 50.0, 50.2)  # many, modest
    rows = clvboard.scoreboard(b.conn)["rows"]
    assert rows[0]["market"] == "rec_yds", \
        "the scoreboard led with its best-looking number"


def test_a_thin_row_is_flagged_rather_than_dropped():
    b = _Book()
    b.bet("mlb", "hits", "OVER", 0.5, 1.0)
    row = clvboard.scoreboard(b.conn)["rows"][0]
    assert row["thin"] is True
    assert row["settled"] == 1, "the row was dropped instead of flagged"


def test_totals_carry_the_same_gate():
    b = _Book()
    for _ in range(3):
        b.bet("nfl", "rec_yds", "OVER", 50.0, 51.0)
    tot = clvboard.scoreboard(b.conn)["totals"]
    assert tot["settled"] == 3 and tot["with_close"] == 3
    assert tot["avg_clv"] == 1.0
    assert tot["ready"] is False


def test_paper_and_unstaked_picks_stay_out():
    """The scoreboard grades what was actually bet. A zero-stake row is
    tracked on paper and does not belong in the evidence."""
    b = _Book()
    b.conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book,"
        " odds, stake_units, stake_dollars, status, category, closing_line,"
        " pnl_units) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-08-20T10:00:00", "nfl", "2026-08-20", "Zero", "rec_yds",
         "OVER", 50.0, "DK", -110, 0.0, 0.0, "won", "main", 51.0, 0.0))
    b.conn.commit()
    assert clvboard.scoreboard(b.conn)["rows"] == []


def test_an_empty_journal_is_an_empty_board_not_a_crash():
    sb = clvboard.scoreboard(_Book().conn)
    assert sb["rows"] == []
    assert sb["totals"]["settled"] == 0
    assert sb["totals"]["avg_clv"] is None


def test_the_gate_is_the_ledgers_own_number():
    assert clvboard.scoreboard(_Book().conn)["min_n"] == ledger.CLV_MIN_N, \
        "the scoreboard invented its own sample bar"


# --- the page ----------------------------------------------------------------

APP = _read("web", "js", "app.js")


def test_the_record_page_gives_it_a_room():
    assert '["market", "Model vs market",' in APP
    assert "recClvBoard(d.clv_board)" in APP
    src = _read("engine", "ledger.py")
    assert '"clv_board": _clv_board(conn, since)' in src, \
        "the scoreboard never reaches the page"


def test_the_panel_shows_the_number_it_declines_to_call():
    i = APP.index("function recClvBoard(cb)")
    body = APP[i:APP.index("\nfunction ", i + 10)]
    assert "r.ready" in body, "the verdict gate left the panel"
    assert "thin" in body, "a below-bar row is called like any other"
    assert "no closes yet" in body, \
        "an ungradeable market renders as a blank instead of saying so"
    # The sample size is on every row, not just in the header.
    assert "r.with_close}/${r.settled}" in body


def test_the_panel_does_not_borrow_the_record_boards_grid():
    """`.rb-row` is built for five columns and hides its CLV column on
    phones — borrowing it put this panel's verdict in the wrong slot and
    then made it invisible exactly where it matters most."""
    i = APP.index("function recClvBoard(cb)")
    body = APP[i:APP.index("\nfunction ", i + 10)]
    assert "rb-row" not in body and "rb-clv" not in body
    css = _read("web", "css", "styles.css")
    assert ".mvm-row {" in css and ".mvm-clv {" in css


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
