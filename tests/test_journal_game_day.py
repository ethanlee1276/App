"""A journal row with no calendar day can never be settled.

Ethan, 2026-09-11: "None of the nfl bets from the past 2 nights for the
most likely or the edge bets have settled."

`bets.date` is the SETTLE KEY, and for football it is a week — "2026-W01".
Every reader that windows the journal by calendar therefore reads
`game_day` (`ledger.day_expr`), and `maintenance._open_bet_days` builds
the settle window from it. A row with no `game_day` falls back to the week
label, which sorts after every digit and so is inside no window that
function can build.

Measured on the droplet that morning:

    open NFL rows by (date, game_day)
        ("2026-W01", None)         52 of the 60 most recent
        ("2026-W01", "2026-09-13")  8
    bucketed under "2026-W01"     134 open rows, OUTSIDE every window
    categories stranded           stale, likely, longshot
    the results were there        NE@SEA 13-10, SF@LA 7-27,
                                  268 Week 1 player game logs

Two defects, both of the shape this codebase keeps producing — a rule
honoured in some places and not the rest:

  1. eleven inserts write this table and only three filled `game_day`;
     the Most Likely board, the stale flags and the long shots were
     among the eight that did not;
  2. `likely._row_from` copied the game's day from `row["date"]`, and a
     prop row has no `date` — `pipeline._rec_to_dict` puts the kickoff
     day in `game_date`. So even the inserts that DID stamp had nothing
     to stamp from on a prop-derived row.

Fixing one without the other fixes nothing, which is why both are here.
"""

import re
import sys
import datetime as dt
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger, likely, maintenance                # noqa: E402

LEDGER_SRC = (ROOT / "engine" / "ledger.py").read_text()


def _ledger():
    db = Path(tempfile.mkdtemp()) / "l.db"
    conn = ledger.connect(db)
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1)
    return conn


def _prop(**kw):
    """A prop row the shape `pipeline._rec_to_dict` publishes: the day
    lives in `game_date`, and there is no `date` key at all."""
    row = {"player": "Josh Allen", "team": "BUF", "opponent": "NYJ",
           "market": "pass_yds", "market_label": "Passing Yards",
           "side": "OVER", "line": 240.5, "book": "fanduel", "odds": -115,
           "hit_prob": 0.62, "raw_prob": 0.62, "implied_prob": 0.56,
           "projection": 262.0, "game_date": "2026-09-13",
           "kickoff": "13:00", "has_market": True,
           "logs": [], "recent_values": []}
    row.update(kw)
    return row


def test_every_journal_insert_stamps_the_calendar_day():
    """THE RULE, CHECKED WHERE IT IS BROKEN — at the inserts themselves.

    Eight of eleven forgot this column. A test that only exercised the
    Most Likely path would have passed while the stale flags and the long
    shots went on stranding rows, so this reads the source and holds every
    insert to the same rule, including ones written after today.
    """
    stmts = re.findall(r"INSERT OR IGNORE INTO bets \(([^\)]*)\)", LEDGER_SRC)
    assert len(stmts) >= 8, f"only {len(stmts)} inserts found — did the shape change?"
    missing = [s for s in stmts if "game_day" not in s]
    assert not missing, (
        f"{len(missing)} insert(s) into bets never write game_day, so their "
        f"rows can never enter a settle window: {[m[:60] for m in missing]}")


def test_a_likely_row_carries_the_props_own_game_day():
    """`row["date"]` is not where a prop keeps its day, and reading it
    there put an empty string on every prop-derived likelihood row."""
    row = likely.from_prop(_prop(), lambda m: True, sport="nfl")
    assert row, "the fixture no longer produces a likelihood row"
    assert row.get("game_date") == "2026-09-13", row.get("game_date")


def test_a_game_row_still_reads_its_own_date():
    """A game bet keeps its day in `date`, and that path must not move."""
    assert ledger.game_day_for({"date": "2026-09-13"}) == "2026-09-13"
    assert ledger.game_day_for({"game_date": "2026-09-14",
                                "date": "2026-09-13"}) == "2026-09-14"
    assert ledger.game_day_for({"date": "2026-W01"}, "") == ""


def test_the_most_likely_board_stamps_a_football_row():
    conn = _ledger()
    row = likely.from_prop(_prop(), lambda m: True, sport="nfl")
    assert ledger.log_most_likely(conn, {"most_likely": [row]},
                                  ) == 1
    got = conn.execute("SELECT date, game_day, category FROM bets").fetchone()
    assert got["game_day"] == "2026-09-13", dict(got)
    assert got["category"] == "likely", dict(got)


def test_the_stamped_row_is_inside_the_settle_window():
    """THE WHOLE POINT. `_open_bet_days` is what decides whether the
    settler looks at a night at all — and it returns EARLY on an empty
    list, so an unstamped row does not merely go ungraded, it stops the
    results ingest that would have graded it."""
    conn = _ledger()
    row = likely.from_prop(_prop(), lambda m: True, sport="nfl")
    ledger.log_most_likely(conn, {"most_likely": [row]})
    days = maintenance._open_bet_days(conn, dt.date(2026, 9, 13), 3)
    assert days == ["2026-09-13"], days


def test_an_unstamped_row_is_the_failure_this_prevents():
    """The before-picture, written by hand so the window's behaviour is
    pinned rather than assumed: a week label is inside no window."""
    conn = _ledger()
    conn.execute(
        "INSERT INTO bets (ts, sport, date, game_day, player, market, side, "
        "line, odds, stake_units, status, category) "
        "VALUES ('2026-09-11T00:00:00','nfl','2026-W01',NULL,'X','pass_yds',"
        "'OVER',240.5,-115,0.1,'open','likely')")
    conn.commit()
    assert maintenance._open_bet_days(conn, dt.date(2026, 9, 13), 3) == []


def test_a_daily_sport_is_untouched():
    """Baseball's slate label already IS the day; the stamp must agree
    with it rather than introduce a second answer."""
    conn = _ledger()
    row = likely.from_prop(
        _prop(market="hits", line=0.5, game_date="2026-09-11"),
        lambda m: True, sport="mlb")
    if not row:                     # market not ranked for baseball here
        assert ledger.game_day_for({"game_date": "2026-09-11"},
                                   "2026-09-11") == "2026-09-11"
        return
    ledger.log_most_likely(conn, {"most_likely": [row]}, )
    got = conn.execute("SELECT date, game_day FROM bets").fetchone()
    assert got["game_day"] == "2026-09-11", dict(got)


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
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
