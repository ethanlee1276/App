"""The range chips window the whole panel, not just the picture.

Ethan, 2026-08-13, from his phone with 1W lit: "when I click the 1 week
button here for the record, it still displays all the information from
our all time record. fix that so when you click the one week button it
just shows the record and chart and roi and shit only from that week."

The chips moved the chart and nothing else. The tiles under it — Net
P&L, win rate, ROI, the record, and the donut beside them — stayed
all-time, so a card with a range control on it was making two statements
about two different periods with nothing on it saying which was which.

The note in the code DEFENDED that, on the grounds that a windowed chart
over unlabelled all-time tiles is confusing. It is confusing — that was
the bug, not the argument against fixing it. The number a bettor checks
first was the one answering the wrong question.

WHAT MAKES THIS ARITHMETIC RATHER THAN A GUESS. `pnl_curve` has carried
per-day wins, losses and stake since it was written, for exactly this,
and the tiles never read them. Two fields it could NOT derive are added
here rather than approximated:

  * dollars — a paper row settles with pnl_dollars 0 by construction, so
    scaling a window's units by the all-time dollars-per-unit would run
    money through the bankroll that never existed;
  * the break-even — the mean of each bet's OWN implied rate. A week of
    −200 favourites needs 66.7% and a week of +150 dogs needs 40%.
    Carrying the all-time average into either is the same error as the
    one being fixed, one column over.
"""

import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
FN = APP[APP.index("async function renderHomePerf()"):APP.index("/* The right rail:")]


# --- the data the window is computed from ----------------------------------
def _ledger(rows):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE bets (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "date TEXT, sport TEXT, odds INTEGER, stake_units REAL, "
                 "stake_dollars REAL, status TEXT, pnl_units REAL, "
                 "pnl_dollars REAL, category TEXT)")
    conn.executemany(
        "INSERT INTO bets (date, sport, odds, stake_units, stake_dollars, "
        "status, pnl_units, pnl_dollars, category) VALUES (?,?,?,?,?,?,?,?,?)",
        rows)
    return conn


def test_the_curve_carries_a_days_own_record():
    conn = _ledger([
        ("2026-08-10", "mlb", -110, 1.0, 10.0, "won", 0.91, 9.1, "main"),
        ("2026-08-10", "mlb", -110, 1.0, 10.0, "lost", -1.0, -10.0, "main"),
        ("2026-08-11", "mlb", 150, 1.0, 10.0, "won", 1.5, 15.0, "main"),
    ])
    curve = ledger.pnl_curve(conn)
    assert [r["date"] for r in curve] == ["2026-08-10", "2026-08-11"]
    assert curve[0]["w"] == 1 and curve[0]["l"] == 1 and curve[0]["n"] == 2
    assert curve[1]["w"] == 1 and curve[1]["staked"] == 1.0


def test_dollars_ride_along_because_they_cannot_be_scaled():
    """A paper row settles with pnl_dollars 0 while its units are real.
    Deriving a window's dollars from its units would invent money."""
    conn = _ledger([
        ("2026-08-10", "mlb", -110, 1.0, 10.0, "won", 0.91, 9.1, "main"),
        ("2026-08-10", "mlb", -110, 1.0, 0.0, "won", 0.91, 0.0, "paper"),
    ])
    d = ledger.pnl_curve(conn)[0]
    assert d["day_u"] == 1.82, d
    assert d["day_d"] == 9.1, "paper dollars must not appear"


def test_each_days_break_even_is_its_own_prices():
    """−200 needs 66.7%; +150 needs 40%. A day of one must not be
    reported at the other's bar."""
    conn = _ledger([("2026-08-10", "mlb", -200, 1.0, 10.0, "won", 0.5, 5.0, "main")])
    d = ledger.pnl_curve(conn)[0]
    assert d["be_n"] == 1
    # Stored to 4 dp — the payload is read by a browser, not a solver.
    assert abs(d["be_sum"] - (200 / 300)) < 1e-4, d["be_sum"]
    conn2 = _ledger([("2026-08-10", "mlb", 150, 1.0, 10.0, "lost", -1.0, -10.0, "main")])
    assert abs(ledger.pnl_curve(conn2)[0]["be_sum"] - 0.4) < 1e-4


def test_a_push_is_counted_but_not_in_the_break_even():
    """A push had no price to beat — averaging it in would drag the bar
    toward nothing."""
    conn = _ledger([
        ("2026-08-10", "mlb", -110, 1.0, 10.0, "push", 0.0, 0.0, "main"),
        ("2026-08-10", "mlb", -110, 1.0, 10.0, "won", 0.91, 9.1, "main"),
    ])
    d = ledger.pnl_curve(conn)[0]
    assert d["n"] == 2 and d["w"] == 1 and d["l"] == 0
    assert d["be_n"] == 1, "the push was averaged into the break-even"


def test_the_window_sums_to_the_same_answer_as_the_whole_book():
    """The all-time range and the sum of every day must agree, or one of
    the two paths is wrong and the panel would contradict itself when a
    chip is clicked."""
    rows = []
    for day in range(1, 15):
        for i in range(6):
            won = (day + i) % 3 != 0
            rows.append((f"2026-08-{day:02d}", "mlb", -110, 1.0, 10.0,
                         "won" if won else "lost",
                         0.91 if won else -1.0, 9.1 if won else -10.0, "main"))
    conn = _ledger(rows)
    curve = ledger.pnl_curve(conn)
    assert sum(r["w"] for r in curve) + sum(r["l"] for r in curve) == len(rows)
    assert abs(sum(r["day_u"] for r in curve) - curve[-1]["cum_u"]) < 0.01


# --- the panel actually reading them ---------------------------------------
def test_every_tile_reads_the_windowed_block():
    """`o` used to be the all-time block. It is now the window's, and the
    all-time one is kept under its own name so the two cannot be confused
    at a glance while editing."""
    # `all` grew a scope on 2026-08-17 (Ethan: the panel "should only
    # show the performance for that specific sport") — the stored block
    # now comes from the sport's own section when it has settled picks,
    # and the whole-book one otherwise. The contract this test owns is
    # unchanged: tiles read the WINDOW'S block, all-time reads a STORED
    # block, and the two keep separate names.
    assert "const all = scopedToSport ? section.overall" \
           " : (_perfCache.overall || {});" in FN
    assert "const windowStats = (rows) =>" in FN
    for field in ("net_units", "win_rate", "roi", "wins", "losses",
                  "settled", "breakeven", "net_dollars"):
        assert field in FN.split("const windowStats")[1].split("};")[0], field


def test_the_all_time_range_still_uses_the_stored_block():
    """`performance()` is the one place that decides what the record
    MEANS. Recomputing all-time here from the curve would be a second
    definition, and the two would drift the first time one changed."""
    m = re.search(r"const o = \(([^;]*)\)\s*\n?\s*\? all : windowStats\(curve\);", FN)
    assert m, "the all-time path must fall back to the stored block"
    assert "!isFinite(days)" in m.group(1)


def test_the_donut_follows_the_window_too():
    """It sits under the same chips on the same card. A 240-bet donut
    beside an 84-bet record is the original bug with a different shape."""
    i = FN.index("const n = o.settled")
    assert "o.wins" in FN[i:i + 200] and "o.losses" in FN[i:i + 200]


def test_the_panel_says_what_it_counted():
    """The chip says which button is lit; this says what was actually
    summed, which is the part that was ambiguous. `betWord` joined on
    2026-08-17 — the sport-scoped panel counts "MLB bet(s)", the
    whole-book one plain "bet(s)" — and the sentence shape is the same."""
    assert "settled ${betWord} over" in FN and "graded day(s)" in FN
    assert "const scopeLine" in FN


def test_a_stale_record_file_costs_the_feature_not_the_truth():
    """An older record.json has no per-day dollars or break-even. Half a
    window computed from half the fields would be a wrong number rather
    than a missing one, so the panel shows the whole book and says so."""
    assert "const canWindow = full.every((r) => r.be_n != null && r.day_d != null);" in FN
    assert "rebuild the" in FN


def test_the_dashboard_deltas_are_doors_and_measurements():
    """Render 3's extras (2026-08-19): a Quick Tools row of doors to
    rooms that already exist, a Recent Results tail read off the curve
    itself, and a per-sport donut fed by the ledger's own per-sport
    export. None of the three may invent a number. The tools row moved
    to its own top-of-page renderer 2026-08-31 (Ethan's screenshot:
    "We should show this at the top of the page") — the doors are
    asserted where they live now."""
    with open(os.path.join(ROOT, "web", "js", "app.js"),
              encoding="utf-8") as f:
        app = f.read()
    qt = app[app.index("function renderQuickTools("):]
    qt = qt[:qt.index("\n}")]
    for href in ("#fantasy", "#scanner", "#mybets", "#bankroll"):
        assert f'href="{href}"' in qt, f"quick tools lost {href}"
    # Recent results are curve ROWS, and only when the rows carry the
    # per-day record — a stale file drops the block instead of guessing.
    assert "const tail = full.slice(-5).reverse();" in FN
    assert "tail.every((r) => r.w != null)" in FN
    # The donut counts the ledger's stored per-sport blocks, never a
    # recount, and needs at least two sports to be a comparison.
    assert "(_perfCache.tracked_sports || [])" in FN
    assert "sportRows.length >= 2" in FN
    i = FN.index("const sportRows")
    seg = FN[i:i + 400]
    assert "overall" in seg and "x.o.settled" in seg


def test_the_break_even_line_disappears_rather_than_printing_zero():
    """`(100 * (o.breakeven || 0))` would print "break-even 0.0%" on a
    window with no priced bets — a claim that a bet needs nothing to
    break even."""
    assert "o.breakeven != null ?" in FN


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
