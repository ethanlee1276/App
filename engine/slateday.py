"""The baseball day: the date a night's slate belongs to, rolling at 5 AM Eastern.

ONE DEFINITION, because two drifted. `launch._slate_date` has rolled the
board, the tracker and the journal at 5 AM Eastern since 2026-09-01 —
west-coast games run past midnight, and flipping on the calendar tick
"yanked still-live bets off the Live tab in the 7th inning". The live
scoreboard (`live_build.py`) and the per-bet sweat (`engine/sweat.py`)
still read `date.today()`: the service runs on Eastern time, so at
midnight they fetched TOMORROW's schedule while the board and its bets
were still on tonight's. Ethan, 2026-09-24, 12:13 AM, Padres at Dodgers
in the top of the 6th: "mlbs bets will show they are live but the games
won't show up on the live tab" — the bets from the board, the Live list
from a schedule for a day with nothing on it, and no final ever arriving
to move a finished bet off the page.
"""
from __future__ import annotations

import datetime as _dt

#: Eastern hour at which the night's slate hands over to the next day's.
ROLL_HOUR = 5


def baseball_day(now: _dt.datetime | None = None) -> str:
    """ISO date of the slate being played at ``now`` (Eastern when omitted)."""
    if now is None:
        from zoneinfo import ZoneInfo
        now = _dt.datetime.now(ZoneInfo("America/New_York"))
    return (now - _dt.timedelta(hours=ROLL_HOUR)).date().isoformat()
