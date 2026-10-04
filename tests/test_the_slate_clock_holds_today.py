"""The Pick of the Day tests' kickoff clock never leaves today's slate.

See tests/_slate_clock.py: "three hours from now" is tomorrow after 9pm
Eastern, and every Pick of the Day test failed from 9 to midnight until
2026-09-22 for that reason alone. These cases walk the clock through the
hours that broke it.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _slate_clock import ET, kickoff                         # noqa: E402


def _at(h, m):
    today = dt.datetime.now(ET).date()
    return dt.datetime.combine(today, dt.time(h, m), tzinfo=ET)


def test_the_middle_of_the_day_is_untouched():
    now = _at(12, 0)
    assert kickoff(180, now) == (now.date().isoformat(), "15:00")
    assert kickoff(-45, now) == (now.date().isoformat(), "11:15")


def test_late_evening_holds_the_game_at_the_last_minute_of_the_slate():
    for h, m in ((21, 0), (21, 30), (23, 0), (23, 58)):
        now = _at(h, m)
        d, k = kickoff(180, now)
        assert d == now.date().isoformat(), (h, m, d)
        assert k == "23:59" and k > now.strftime("%H:%M"), "still ahead of the clock"


def test_just_after_midnight_a_started_game_is_still_today():
    now = _at(0, 20)
    assert kickoff(-45, now) == (now.date().isoformat(), "00:00")
    now = _at(0, 50)
    assert kickoff(-45, now) == (now.date().isoformat(), "00:05")


def test_every_pick_of_the_day_test_uses_it():
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("test_potd.py", "test_potd_full_pool.py", "test_potd_verdict.py",
                 "test_potd_report.py", "test_potd_spreads_and_totals.py", "test_potd_book.py"):
        src = open(os.path.join(here, name), encoding="utf-8").read()
        assert "from _slate_clock import kickoff as _kickoff" in src, name
        assert "dt.timedelta(minutes=minutes)" not in src and "timedelta(minutes=180)" not in src, \
            f"{name} builds its own kickoff again"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
