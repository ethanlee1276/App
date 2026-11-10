"""Each player's name and each snapshot stamp's slate day are worked out once
(engine/sources/oddsapi.normalize_name's cache; engine/linemoves._slate_day's
``memo``, kept by `LineCloses`, `OddsCloses`, `closebook.SameBookCloses` and
`closing_books_by_date`).

The settle pass, 22:55 on 9 November: 48 seconds of grading, 42 of them the
snapshot read. On a file of a million wanted rows each row's name was
normalised three times over (2.8 µs a call) and its game's Eastern day
worked out twice over (2.5 µs), for names and starts that repeat on every
row of a pull; the two close readers' share of the read halved with both
kept. What these hold:

  * a cached name is the name worked out fresh, for every shape a feed
    writes (accents, both apostrophes, suffixes, dots and dashes, spacing),
    and a bad argument fails as it did; the cache is bounded;
  * a day from the memo is the day worked out fresh, across the autumn
    clock change and either side of Eastern midnight, for a start given as
    a number or as text, and a row with no start keeps the machine's day
    under its own key, never a start's;
  * a stamp that cannot be read fails as it did, memo or not;
  * each reader keeps one entry a stamp, whatever the rows.

Run directly: `python3 tests/test_each_name_and_stamp_is_worked_out_once.py`
"""
import datetime as dt
import os
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import closebook, linemoves as LM                        # noqa: E402
from engine.sources.oddsapi import normalize_name                   # noqa: E402

ET = ZoneInfo("America/New_York")
NAMES = ("Amon-Ra St. Brown", "A.J. Brown", "Ronald Acuña Jr.", "A’ja Wilson", "A'ja Wilson",
         "JaʼMarr Chase", "D'Angelo Russell", "Bobby Witt Jr.", "Ken Griffey III", "  Luka   Dončić ",
         "Kenneth Walker III", "T.J. Hockenson", "JOSH ALLEN", "josh allen", "", "Shaquille O'Neal Sr.",
         "Jaren Jackson Jr.", "Gary Payton II", "C.J. Stroud", "Nikola Jokić")


def test_a_cached_name_is_the_name_worked_out_fresh():
    fresh = normalize_name.__wrapped__
    for name in NAMES:
        assert normalize_name(name) == fresh(name), name
        assert normalize_name(name) == fresh(name), name                  # and again, from the cache
    assert normalize_name("Amon-Ra St. Brown") == "amon ra st brown"
    assert normalize_name("Ronald Acuña Jr.") == "ronald acuna"
    assert normalize_name("A’ja Wilson") == normalize_name("A'ja Wilson") == "aja wilson"


def test_the_name_cache_is_bounded_and_fails_as_before():
    info = normalize_name.cache_info()
    assert info.maxsize and info.maxsize <= 1 << 16, info
    for bad in (None, 5):
        try:
            normalize_name(bad)
        except TypeError:
            pass
        else:
            raise AssertionError(f"normalize_name({bad!r}) should raise TypeError")
    try:
        normalize_name(["a list"])
    except TypeError:
        pass
    else:
        raise AssertionError("an unhashable name should raise TypeError")


def _stamps():
    """Starts either side of Eastern midnight and of the clock change of
    1 November 2026 (2:00 EDT → 1:00 EST), as numbers and as text."""
    out = []
    for day, hh, mm, ss in ((dt.date(2026, 10, 31), 23, 59, 59), (dt.date(2026, 11, 1), 0, 0, 0),
                            (dt.date(2026, 11, 1), 1, 30, 0), (dt.date(2026, 11, 1), 23, 59, 59),
                            (dt.date(2026, 11, 2), 0, 0, 1), (dt.date(2026, 11, 9), 20, 15, 0)):
        t = dt.datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=ET).timestamp()
        out += [t, t + 0.25, int(t), str(t)]
    out.append(dt.datetime(2026, 11, 1, 5, 30, tzinfo=dt.timezone.utc).timestamp())  # 01:30 EDT
    out.append(dt.datetime(2026, 11, 1, 6, 30, tzinfo=dt.timezone.utc).timestamp())  # 01:30 EST
    return out


def test_a_day_from_the_memo_is_the_day_worked_out_fresh():
    memo: dict = {}
    for st in _stamps() * 2:
        r = {"ts": 1793000000.0, "start_ts": st}
        assert LM._slate_day(r, memo) == LM._slate_day(r), st
    assert len(memo) == len({float(x) for x in _stamps()})


def test_a_row_without_a_start_keeps_the_machines_day_under_its_own_key():
    saved = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    time.tzset()
    try:
        t = dt.datetime(2026, 11, 10, 2, 0, tzinfo=dt.timezone.utc).timestamp()   # 21:00 ET the 9th
        memo: dict = {}
        stamped, bare = {"ts": 1.0, "start_ts": t}, {"ts": t}
        assert LM._slate_day(stamped, memo) == "2026-11-09"
        assert LM._slate_day(bare, memo) == "2026-11-10", "the machine's own day, not the start's"
        assert LM._slate_day(stamped, memo) == "2026-11-09"
        assert LM._slate_day(bare, memo) == LM._slate_day(bare) == "2026-11-10"
    finally:
        if saved is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = saved
        time.tzset()


def test_a_stamp_that_cannot_be_read_fails_as_it_did():
    for r in ({"ts": 1.0, "start_ts": "soon"}, {"ts": "late"}, {"start_ts": None}):
        errors = []
        for memo in (None, {}):
            try:
                LM._slate_day(r, memo)
            except Exception as exc:                                        # noqa: BLE001
                errors.append(type(exc))
            else:
                errors.append(None)
        assert errors[0] is not None and errors[0] == errors[1], (r, errors)


def _rows():
    t0 = dt.datetime(2026, 11, 9, 12, 0, tzinfo=ET).timestamp()
    starts = [dt.datetime(2026, 11, 9, h, 0, tzinfo=ET).timestamp() for h in (19, 20, 22)]
    rows = []
    for i in range(30):
        for k, st in enumerate(starts):
            for p in ("Jalen Brunson", "Mikal Bridges", "OG Anunoby"):
                for b in ("DraftKings", "FanDuel"):
                    rows.append({"ts": t0 + i * 600, "player": p, "market": "points", "book": b,
                                 "line": 20.5 + k, "over_odds": -110, "under_odds": -110, "start_ts": st})
    rows.append({"ts": t0, "player": "Old Row", "market": "points", "book": "DraftKings", "line": 9.5,
                 "over_odds": -110, "under_odds": -110})
    return rows, len(starts)


def test_each_reader_keeps_one_entry_a_stamp():
    rows, n_starts = _rows()
    lines, odds = LM.LineCloses(), LM.OddsCloses()
    for r in rows:
        lines.add(r)
        odds.add(r)
    assert len(lines._days) == len(odds._days) == n_starts + 1, (lines._days, odds._days)
    assert LM.closing_lines_by_date(rows) == lines.index()
    sb = closebook.SameBookCloses(None, snapshots=rows)
    sb.prepare([{"player": "Jalen Brunson", "market": "points", "line": 20.5 + k} for k in range(n_starts)])
    assert len(sb._slate_days) == n_starts, sb._slate_days      # its bets' rows only, a game a line


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
