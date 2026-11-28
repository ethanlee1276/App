"""The NFL's Pick of the Day: Thursday, Sunday and Monday, and only on its day.

Ethan, Tuesday 2026-09-29: "the NFL pick of the day from yesterday is
still showing today, even though that game has ended ... we should only
be showing pick of the days for NFL. Only on Mondays Thursdays and
Sundays."

Two things held Monday night's pick (PHI@CHI under 41.5, journaled at
00:06 UTC — 8:06 PM Monday in the East) on the page all of Tuesday, and
both compared UTC calendar days:
  * the lock (`ledger.relock_potd`) looked up "today's locked pick" by
    the journal's UTC date — Tuesday, for an evening pick in the East;
  * `potd.carry` compared the UTC dates of two cards' `decided_at`, so a
    Tuesday build that found nothing carried the 00:06 UTC card forward.
Both now read the Eastern day, the lock only shows a pick on its game's
day, and the NFL names no pick at all on its off days.

Fixture ledger in a temp file — never the box's.

Run directly: `python3 tests/test_the_nfl_pick_is_thursday_sunday_monday_only.py`
"""
import datetime as dt
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger, potd                                   # noqa: E402

UTC = dt.timezone.utc


def _at(iso):
    return dt.datetime.fromisoformat(iso).replace(tzinfo=UTC)


def test_the_nfl_picks_on_thursday_sunday_and_monday_only():
    assert potd.PICK_WEEKDAYS["nfl"] == (0, 3, 6)
    for day in ("2026-09-28", "2026-10-01", "2026-10-04"):          # Mon, Thu, Sun
        assert potd.off_day("nfl", day) is None, day
    tue = potd.off_day("nfl", "2026-09-29")
    assert tue["next_day"] == "2026-10-01"
    assert "No NFL Pick of the Day on a Tuesday" in tue["note"] and "Next: Thursday." in tue["note"]
    assert potd.off_day("nfl", "2026-10-02")["next_day"] == "2026-10-04"   # Friday → Sunday
    assert potd.off_day("nfl", "2026-10-03")["next_day"] == "2026-10-04"   # Saturday → Sunday
    assert potd.off_day("mlb", "2026-09-29") is None, "other leagues pick any day they play"
    assert potd.off_day("cfb", "2026-09-29") is None


def test_an_off_day_card_names_no_pick_and_says_when_the_next_is():
    # 14:00 UTC Tuesday = 10 AM Eastern Tuesday.
    card = potd.build([], "nfl", "2026-W04", now=_at("2026-09-29T14:00:00"))
    assert card["pick"] is None and card["off_day"] is True
    assert card["next_day"] == "2026-10-01"
    assert card["verdict"]["call"] == "no bet"
    # 02:00 UTC Tuesday is still Monday night in the East: a pick day.
    card = potd.build([], "nfl", "2026-W03", now=_at("2026-09-29T02:00:00"))
    assert not card.get("off_day")


def test_carry_compares_eastern_days_not_utc_ones():
    monday_pick = {"sport": "nfl", "decided_at": "2026-09-29T00:06:00Z",   # 8:06 PM Mon ET
                   "pick": {"player": "PHI@CHI", "market": "total"}, "open_candidates": 1}
    tuesday = {"sport": "nfl", "decided_at": "2026-09-29T13:00:00Z",       # 9 AM Tue ET
               "pick": None, "open_candidates": 0}
    assert potd.carry(tuesday, monday_pick) is tuesday, "Monday's pick carried into Tuesday"
    late_monday = {"sport": "nfl", "decided_at": "2026-09-29T03:30:00Z",   # 11:30 PM Mon ET
                   "pick": None, "open_candidates": 0}
    assert potd.carry(late_monday, monday_pick)["pick"]["player"] == "PHI@CHI", \
        "the same Eastern day still keeps its call"
    off = {"sport": "nfl", "decided_at": "2026-09-29T03:30:00Z", "pick": None, "off_day": True}
    assert potd.carry(off, monday_pick) is off


def _ledger_with_monday_pick():
    path = Path(tempfile.mkdtemp()) / "ledger.db"
    conn = ledger.connect(path)
    conn.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, "
                 "hit_prob, edge, stake_units, status, category) VALUES "
                 "('2026-09-29T00:06:00Z','nfl','2026-W03','2026-09-28','PHI@CHI','total','UNDER',"
                 "41.5,102,0.51,0.02,1.0,'open',?)", (ledger.POTD_CATEGORY,))
    conn.commit()
    return conn


def test_the_lock_shows_a_pick_only_on_its_games_eastern_day():
    conn = _ledger_with_monday_pick()
    fresh = {"sport": "nfl", "date": "2026-W04", "pick": None, "note": "No pick today"}
    # Tuesday: the lock sits under UTC 2026-09-29, but its game was Monday.
    got = ledger.relock_potd(dict(fresh), [], conn=conn, day="2026-09-29")
    assert got.get("pick") is None, got
    # Monday evening Eastern (the UTC date has already turned): it holds.
    got = ledger.relock_potd(dict(fresh), [], conn=conn, day="2026-09-28")
    assert (got.get("pick") or {}).get("locked") is True, got
    assert got["pick"]["player"] == "PHI@CHI"
    # An off-day card is never re-pointed at anything.
    off = {"sport": "nfl", "date": "2026-W04", "pick": None, "off_day": True}
    assert ledger.relock_potd(dict(off), [], conn=conn, day="2026-09-28").get("pick") is None


def test_the_lock_reader_carries_the_games_day():
    conn = _ledger_with_monday_pick()
    got = ledger.locked_potd_picks(conn, "2026-09-29")["nfl"]
    assert got["game_day"] == "2026-09-28" and got["game_date"] == "2026-W03"


def test_the_page_draws_an_off_day_as_one_line():
    app = (ROOT / "web" / "js" / "app.js").read_text()
    i = app.index("async function renderPickOfTheDay()")
    body = app[i:i + 6000]
    assert "if (got.off_day) {" in body and "potd-offday" in body


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
