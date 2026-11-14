"""A kickoff time on TODAY'S slate, `minutes` from now — whatever the hour.

The Pick of the Day refuses a game that is not on today's Eastern slate
("the game is not today") before it asks anything else. Its tests place
their games "three hours from now", and after 9pm Eastern three hours
from now is TOMORROW — so every one of them failed, every night, from 9
to midnight, for a reason that had nothing to do with the bar each test
was written about. The mirror case is a game "45 minutes ago" just after
midnight, which lands on yesterday.

So the kickoff is held on today's date: no later than 23:59 and no
earlier than 00:00, still ahead of the clock (or behind it) as asked.
The one minute this cannot serve is 23:59 itself, when no later minute
is left on the slate.

Relative on purpose: a fixture pinned to a date is a test that expires.

Not a test module: `run_tests.py` collects `test_*.py`, so this is
imported, never collected.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def kickoff(minutes: int, now: dt.datetime | None = None) -> tuple[str, str]:
    """(date, "HH:MM") in Eastern, `minutes` from `now`, held on now's day."""
    now = now or dt.datetime.now(ET)
    t = now + dt.timedelta(minutes=minutes)
    if t.date() > now.date():
        t = now.replace(hour=23, minute=59, second=0, microsecond=0)
    elif t.date() < now.date():
        t = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return t.strftime("%Y-%m-%d"), t.strftime("%H:%M")
