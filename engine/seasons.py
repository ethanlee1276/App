"""When each sport is actually played — so "2021-2026" means something.

Every board here except the NFL had at most one season of history, and
that is the thing quietly limiting the whole system: team ratings firm up
with games, a prop backtest can only replay games it has, calibration
needs hundreds of graded results, and the college football variance fit
refuses to run under 400 games. All of those are downstream of "how far
back does the database go".

The obstacle was never the model, it was the shape of the command. Asking
someone to remember that the WNBA runs May to October and the NBA runs
October to June and college football crosses New Year's Eve — six times,
once per season, per sport — is a chore nobody finishes. So the season
windows live here and `--seasons 2021-2026` expands into the right date
ranges by itself.

**A season is labelled by the year it STARTS.** The 2021 NBA season means
October 2021 through June 2022, and the 2021 college football season ends
in January 2022. That matches how both sports name themselves and how the
NFL data already in this database is keyed, so one convention covers all
of them.

The windows are deliberately a little wider than the schedule: an extra
week either side costs a handful of cached requests that find nothing, and
a window that is too narrow silently drops a playoff round.
"""

from __future__ import annotations

import datetime as _dt

# (start month, start day, end month, end day, ends_next_year)
SEASON_WINDOWS = {
    # Late March through the World Series in early November.
    "mlb": (3, 1, 11, 15, False),
    # Preseason mid-October through the Finals in late June.
    "nba": (10, 1, 6, 30, True),
    # May through the Finals in October. The one league that is live while
    # the NBA is dark.
    "wnba": (4, 25, 10, 31, False),
    # Week 0 in late August through the national championship in January.
    "cfb": (8, 15, 1, 20, True),
}

# Sports whose day-by-day ingest is worth warning about before it starts.
# A basketball season is ~1,200 games and each one costs a box-score
# request; six of them is an afternoon, not a coffee break.
HEAVY = {"nba", "wnba"}


def window(sport: str, season: int) -> tuple[str, str]:
    """(start, end) ISO dates for one season of one sport."""
    if sport not in SEASON_WINDOWS:
        raise ValueError(f"no season window defined for {sport!r}")
    sm, sd, em, ed, next_year = SEASON_WINDOWS[sport]
    start = _dt.date(season, sm, sd)
    end = _dt.date(season + (1 if next_year else 0), em, ed)
    return start.isoformat(), end.isoformat()


def parse_seasons(spec: str) -> list[int]:
    """'2021-2026' or '2021,2023' or '2024' → [years].

    Accepts both because both are what people type, and getting it wrong
    should not cost an hour of downloading the wrong decade.
    """
    out: list[int] = []
    for part in str(spec or "").replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            lo, hi = int(a), int(b)
            if hi < lo:
                lo, hi = hi, lo
            out += list(range(lo, hi + 1))
        else:
            out.append(int(part))
    return sorted(set(out))


def dates_for(sport: str, seasons: list[int],
              stop_at_today: bool = True) -> list[str]:
    """Every ISO date across these seasons, oldest first.

    Future dates are dropped by default: a season in progress has no
    results past today, and walking into next June would spend a thousand
    requests confirming that nothing has happened yet.
    """
    today = _dt.date.today()
    days: list[str] = []
    for season in seasons:
        start, end = window(sport, season)
        day = _dt.date.fromisoformat(start)
        last = _dt.date.fromisoformat(end)
        if stop_at_today and last > today:
            last = today
        while day <= last:
            days.append(day.isoformat())
            day += _dt.timedelta(days=1)
    return days


def describe(sport: str, seasons: list[int], days: int) -> str:
    """A one-line honest estimate, printed before the work starts."""
    if not seasons:
        return "no seasons selected"
    span = (f"{seasons[0]}" if len(seasons) == 1
            else f"{seasons[0]}-{seasons[-1]}")
    note = ""
    if sport in HEAVY:
        note = ("  This one is slow: a basketball season is ~1,200 games and "
                "each needs its own box score. Expect a long run, leave it "
                "going, and re-run it any time — days already stored are "
                "skipped.")
    elif sport == "mlb":
        note = ("  Roughly a few requests per day of the season; re-runs skip "
                "days already stored.")
    return f"{sport.upper()} seasons {span} — {days:,} date(s) to walk.{note}"
