"""The Pick of the Day's own book, and the wiring that fills it.

Ethan, 2026-09-15: "We will record the 'Pick of the day' record on the
record page correlated too the sport, and it will have its own spot on
the record page so we can see how it's doing."

Three rules make that record mean something, and each is a test here:

  * a row the SELECTOR refused is never recorded, so the book answers
    "how do our picks do" rather than "how does our best guess do on
    the days we had nothing";
  * the FIRST qualifying pick of the day is the day's pick, so a board
    that rebuilds all day cannot keep re-picking until the grader runs;
  * a game already under way is refused, like every other book since
    the KC-DEN rows.

The fourth thing guarded is the wiring: five builds and one hook, so
the bar cannot drift between leagues.

Run directly: `python3 tests/test_potd_book.py`
"""

import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gate, ledger, potd                         # noqa: E402

ET = ZoneInfo("America/New_York")


def _et(minutes):
    t = dt.datetime.now(ET) + dt.timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%d"), t.strftime("%H:%M")


def _conn():
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))


def _pick(**kw):
    d, k = _et(180)
    p = {"kind": "prop", "player": "A Player", "team": "AAA",
         "opponent": "BBB", "market": "receptions", "market_label": "Receptions",
         "side": "OVER", "line": 3.5, "book": "DraftKings", "odds": -140,
         "model_prob": 0.64, "implied_prob": 0.583, "below_bar": "",
         "game_date": d, "kickoff": k}
    p.update(kw)
    return p


def _payload(sport="nfl", date="2026-W02", **kw):
    return {"sport": sport, "date": date, "pick": _pick(**kw)}


# --- the three rules ---------------------------------------------------------
def test_a_qualifying_pick_is_recorded_in_its_own_book():
    conn = _conn()
    assert ledger.log_pick_of_the_day(conn, _payload()) == 1
    row = conn.execute(
        "SELECT sport, player, market, side, line, odds, stake_units, "
        "stake_dollars, category, grade, status, hit_prob FROM bets").fetchone()
    assert row["category"] == ledger.POTD_CATEGORY == "potd"
    assert row["stake_units"] == ledger.POTD_STAKE == 1.0
    assert row["stake_dollars"] == 0.0, "the showcase book carries no dollars"
    assert row["grade"] == "Pick of the Day"
    assert (row["sport"], row["player"], row["market"]) == ("nfl", "A Player", "receptions")
    assert row["status"] == "open" and row["hit_prob"] == 0.64


def test_a_row_the_selector_refused_is_never_recorded():
    """`potd.build` still returns the best available on a thin day so
    the page is never blank. That row is shown and not booked."""
    conn = _conn()
    assert ledger.log_pick_of_the_day(
        conn, _payload(below_bar="under the confidence floor")) == 0
    assert conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 0


def test_the_first_qualifying_pick_of_the_day_is_the_days_pick():
    """The boards rebuild all day. Without the lock a sport could churn
    picks until settle time and the record would keep whichever one was
    showing when the grader ran — choosing after seeing how the day was
    going."""
    conn = _conn()
    assert ledger.log_pick_of_the_day(conn, _payload()) == 1
    assert ledger.log_pick_of_the_day(conn, _payload(player="Someone Else")) == 0
    assert conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 1
    # The lock is per sport: another league still gets its own pick.
    assert ledger.log_pick_of_the_day(conn, _payload(sport="cfb", date="2026-09-19")) == 1


def test_a_game_already_under_way_is_never_recorded():
    conn = _conn()
    d, k = _et(-45)
    assert ledger.log_pick_of_the_day(
        conn, _payload(game_date=d, kickoff=k)) == 0
    assert ledger.log_pick_of_the_day(conn, _payload(live=True)) == 0


def test_an_invented_price_is_never_recorded():
    conn = _conn()
    assert ledger.log_pick_of_the_day(conn, _payload(book="proxy")) == 0
    assert ledger.log_pick_of_the_day(conn, _payload(odds=0)) == 0


def test_nothing_to_record_is_zero_and_not_a_crash():
    conn = _conn()
    for payload in ({}, {"sport": "nfl"}, {"sport": "nfl", "pick": None},
                    {"pick": _pick()}):
        assert ledger.log_pick_of_the_day(conn, payload) == 0, payload


# --- a game row is stored in the shape the grader already reads --------------
def test_a_moneyline_pick_is_stored_the_way_the_grader_reads_one():
    conn = _conn()
    d, k = _et(180)
    ledger.log_pick_of_the_day(conn, {
        "sport": "nfl", "date": "2026-W02",
        "pick": {"kind": "game", "bet_type": "moneyline", "market": "moneyline",
                 "team": "KC", "player": "KC ML", "book": "FanDuel", "odds": -150,
                 "model_prob": 0.64, "implied_prob": 0.60, "below_bar": "",
                 "game_date": d, "kickoff": k}})
    row = conn.execute("SELECT player, market, side, line FROM bets").fetchone()
    assert (row["player"], row["market"], row["side"], row["line"]) == \
        ("KC", "moneyline", "OVER", 0.5), tuple(row)


def test_a_spread_pick_is_stored_negated_like_every_other_book():
    conn = _conn()
    d, k = _et(180)
    ledger.log_pick_of_the_day(conn, {
        "sport": "nfl", "date": "2026-W02",
        "pick": {"kind": "game", "bet_type": "spread", "market": "spread",
                 "team": "KC", "player": "KC -3.5", "line": -3.5,
                 "book": "FanDuel", "odds": -110, "model_prob": 0.62,
                 "implied_prob": 0.524, "below_bar": "",
                 "game_date": d, "kickoff": k}})
    row = conn.execute("SELECT player, market, side, line FROM bets").fetchone()
    assert (row["player"], row["side"], row["line"]) == ("KC", "OVER", 3.5), tuple(row)


def test_the_game_row_shapes_come_from_one_helper():
    """`log_most_likely` and this book both need the same twenty lines.
    A second copy is how the negated spread ends up right in one book
    and wrong in another."""
    import inspect
    src = inspect.getsource(ledger.log_most_likely)
    assert "game_row_keys(" in src, "the likelihood book grew its own copy back"
    assert ledger.game_row_keys({"bet_type": "moneyline", "team": "KC"}, "moneyline") \
        == ("KC", "moneyline", "OVER", 0.5)
    assert ledger.game_row_keys({"bet_type": "nonsense"}, "nonsense") is None


# --- the record page gets it -------------------------------------------------
def test_the_record_file_carries_the_book_pooled_and_per_sport():
    conn = _conn()
    ledger.log_pick_of_the_day(conn, _payload())
    out = os.path.join(tempfile.mkdtemp(), "record.json")
    ledger.export_json(conn, out)
    blob = json.load(open(out))
    for key in ("potd", "potd_by_sport", "potd_recent"):
        assert key in blob, key
    assert blob["potd"]["open"] >= 1, blob["potd"]
    assert "nfl" in blob["potd_by_sport"], blob["potd_by_sport"]


def test_the_pick_is_behind_the_paywall():
    """One pick at the top of the page is the single most valuable row
    the site publishes that day. A free copy is the product given away."""
    assert "pick_of_the_day" in gate.PAID_KEYS


def test_the_book_never_bleeds_into_the_headline_record():
    """The edge book is money; this one is a published claim being
    scored. `performance` defaults to BOOK, which must not include it."""
    assert ledger.POTD_CATEGORY not in ledger.BOOK
    conn = _conn()
    ledger.log_pick_of_the_day(conn, _payload())
    assert ledger.performance(conn)["open"] == 0, "a Pick of the Day reached the money book"
    assert ledger.performance(conn, category=ledger.POTD_CATEGORY)["open"] == 1


# --- the wiring --------------------------------------------------------------
def test_every_sport_that_builds_a_likelihood_board_also_picks_a_day():
    """One hook, called from each build, so the bar cannot drift between
    leagues — the lesson `livepicks.attach_tracker` was written for."""
    for fn in ("nfl_build.py", "cfb_build.py", "mlb_build.py", "nba_build.py"):
        src = (ROOT / fn).read_text()
        assert "_potd.attach(" in src, f"{fn} publishes no Pick of the Day"
        assert "ledger.log_pick_of_the_day(" in src, f"{fn} records no Pick of the Day"


def test_the_hook_survives_a_board_that_cannot_produce_one():
    """A build that has already priced everything else must not die here,
    and the failure has to reach the JSON rather than only a log the
    launcher swallows."""
    res = {"date": "2026-W02", "most_likely": [{"model_prob": "not a number"}]}
    note = potd.attach(res, "nfl")
    assert "pick_of_the_day" in res or "pick_of_the_day_error" in res, res
    assert note, "a silent hook is the failure this codebase keeps hitting"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
