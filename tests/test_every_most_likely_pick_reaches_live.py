"""Every Most Likely pick the board posts is journaled, so it is on Live.

Ethan, 2026-09-25, Falcons-Packers in the first quarter, the Live tab
open: "We are also not showing all the most likely bets in the live page
either ... I remember seeing us recommending a most likely pick for the
Green Bay game ... one of the Green Bay running backs to have over 9.5
rushing yards, but yet it's not showing on the live page ... it's still
an issue that you have not solved."

The Live tab lists the journal, and the journal took the board's top ten
rows. The board is one list in probability order across the whole NFL
week, so on a Thursday with Sunday priced the ten likeliest rows of the
week were journaled and a Thursday pick sitting 25th was on the page, in
no book, and not on Live. A pick posted under that cut and later locked
was skipped too, on the grounds it "was journaled when it went up".
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import ledger                                        # noqa: E402
from engine import likely as K                                   # noqa: E402
from engine.livepicks import TRACKER_CATEGORIES, open_bets_for   # noqa: E402

WEEK = "2026-W03"


def _pick(player, team, prob, game_date="2099-09-27", kickoff="13:00", **kw):
    r = {"player": player, "team": team, "market": "rush_yds", "side": "over", "line": 40.5,
         "odds": -200, "book": "DraftKings", "model_prob": prob, "implied_prob": 0.66,
         "projection": 60.0, "game_date": game_date, "kickoff": kickoff}
    r.update(kw)
    return r


def _week():
    """Forty Sunday picks likelier than Thursday's, and Thursday's Packers
    back 25th on the list, the way the board sorts them."""
    rows = [_pick(f"Sunday {i}", "KC", 0.80 - i * 0.002) for i in range(24)]
    rows.append(_pick("Emanuel Wilson", "GB", 0.72, game_date="2099-09-24", kickoff="20:15",
                      line=9.5, odds=-240))
    rows += [_pick(f"Sunday {i}", "KC", 0.70 - i * 0.002) for i in range(24, 40)]
    return rows


def test_a_pick_far_down_the_week_is_journaled():
    conn = ledger.connect(":memory:")
    n = ledger.log_most_likely(conn, {"sport": "nfl", "date": WEEK, "most_likely": _week()})
    assert n == 41, n
    got = conn.execute("SELECT player, line, odds FROM bets WHERE player='Emanuel Wilson'").fetchone()
    assert got and (got["line"], got["odds"]) == (9.5, -240)


def test_it_is_on_the_live_tab():
    conn = ledger.connect(":memory:")
    ledger.log_most_likely(conn, {"sport": "nfl", "date": WEEK, "most_likely": _week()})
    today, _near = open_bets_for(conn, "nfl", WEEK)
    assert "Emanuel Wilson" in {r["player"] for r in today}
    assert set(ledger.LIKELY_BOOKS) <= set(TRACKER_CATEGORIES)


def test_every_refresh_republishes_and_nothing_doubles():
    conn = ledger.connect(":memory:")
    board = {"sport": "nfl", "date": WEEK, "most_likely": _week()}
    first = ledger.log_most_likely(conn, board)
    again = ledger.log_most_likely(conn, board)
    assert (first, again) == (41, 0)


def test_a_pick_locked_after_the_old_cut_journals_now():
    posted = _pick("Emanuel Wilson", "GB", 0.72, line=9.5, odds=-240)
    lock = K._locked(posted, "number moved", "2099-09-24T20:00:00Z")
    conn = ledger.connect(":memory:")
    assert ledger.log_most_likely(conn, {"sport": "nfl", "date": WEEK, "most_likely": [lock]}) == 1


def test_a_paper_pick_is_not_journaled_again_when_staked():
    """The key carries the category, and the breaker can move a band
    between the paper and staked books between builds. One pick is one
    row, whichever book it landed in."""
    conn = ledger.connect(":memory:")
    board = {"sport": "nfl", "date": WEEK, "most_likely": [_pick("Emanuel Wilson", "GB", 0.72)]}
    real = ledger.likely_is_staked
    ledger.likely_is_staked = lambda sport: False
    try:
        assert ledger.log_most_likely(conn, board) == 1
    finally:
        ledger.likely_is_staked = real
    assert ledger.log_most_likely(conn, board) == 0
    assert conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 1


def test_a_reserve_row_is_still_not_a_pick():
    conn = ledger.connect(":memory:")
    board = {"sport": "nfl", "date": WEEK,
             "most_likely": [_pick("Below Bar", "GB", 0.52, reserve=True)]}
    assert ledger.log_most_likely(conn, board) == 0


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
