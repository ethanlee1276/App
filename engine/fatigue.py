"""NFL schedule fatigue — rest, body clock and the trip.

The model spec has carried this as §7's open item for a long time with an
unusually specific note: *"Kickoff/rest data exists in schedules; not yet
a modifier."* The data really was already there — nflverse ships
``home_rest`` / ``away_rest`` precomputed (so byes, holiday games and the
opener are handled), the ET kickoff time on every row, and a neutral-site
flag that in the NFL means an international trip. Nothing read any of it.

Three circumstances, all knowable before kickoff:

* **Short week** — four days between games. A Thursday opponent had one
  padded practice, no real installation week, and no time for the
  Sunday bumps to heal. The mirror is **off a bye**: thirteen-plus days,
  a healed roster and two weeks of preparation.
* **Body clock** — kickoff times in the feed are Eastern, so a Pacific
  team playing the 13:00 ET window is starting at 10:00 by its own
  clock, and a London game at 09:30 ET is a 06:30 body-clock kickoff
  for a West Coast side. This is the oldest scheduling angle in the
  sport and it costs nothing to compute.
* **The trip** — a neutral site is an international game here, which
  bundles the flight, the time zones and a disrupted week together.

**This ships as evidence, not as a price.** No multiplier, no gate — a
reason on the card, a warning when the circumstance is extreme, and the
number journaled so the blind-spot miner can band it, slice it under the
same false-discovery control as every other dimension, and convict it on
our own record. That order is deliberate and it is the same order the
comps, the incentive tracker and the rest watch shipped in: a signal
earns its way into pricing by being measured first. The published
effect sizes here are small and contested, which is exactly the
situation where a hand-tuned multiplier quietly becomes a permanent
guess.

Standard library only.
"""

from __future__ import annotations

import datetime as _dt

#: Hours each team's home clock sits behind Eastern. The feed's kickoff
#: times are ET, so this is all that is needed to put a game on a team's
#: own body clock. Arizona keeps mountain time year-round and does not
#: observe DST, which through the football season leaves it aligned with
#: the Pacific teams — the reason it is grouped with them rather than
#: with Denver.
TEAM_UTC_OFFSET_FROM_ET = {
    # Pacific (and Arizona, in season)
    "SEA": -3, "SF": -3, "LA": -3, "LAR": -3, "LAC": -3, "LV": -3,
    "ARI": -3,
    # Mountain
    "DEN": -2,
    # Central
    "CHI": -1, "GB": -1, "MIN": -1, "DET": 0, "KC": -1, "NO": -1,
    "DAL": -1, "HOU": -1, "TEN": -1,
    # Eastern (everything else)
    "BUF": 0, "MIA": 0, "NE": 0, "NYJ": 0, "NYG": 0, "PHI": 0, "WAS": 0,
    "PIT": 0, "CLE": 0, "CIN": 0, "BAL": 0, "IND": 0, "JAX": 0, "ATL": 0,
    "CAR": 0, "TB": 0,
}

#: Days of rest that count as a short week. Four is the Thursday game;
#: five and six happen on holiday and Saturday scheduling.
SHORT_WEEK = 4
#: …and the other end: a bye gives thirteen or more.
OFF_BYE = 13

#: A body-clock hour at or before this is the "West Coast team in the
#: early window" spot. 10:00 is the classic 13:00 ET kickoff for a
#: Pacific team; the London window pushes it earlier still.
EARLY_BODY_CLOCK = 11

#: A rest gap this wide is the mismatch worth naming — one side on a
#: short week against a rested opponent.
REST_EDGE = 3


def _kickoff_hour(kickoff: str) -> float | None:
    """The Eastern kickoff hour as a number, or None if unusable.

    The feed carries a bare "HH:MM" clock with no date and no zone. That
    is fine HERE and only here: these times are documented Eastern, and
    the hour is all the body-clock arithmetic needs. It is emphatically
    not an instant — which is why the capture-lag and closing-line layers
    refuse the same string rather than guess a date onto it.
    """
    if not kickoff:
        return None
    try:
        hh, mm = str(kickoff).strip().split(":")[:2]
        h, m = int(hh), int(mm)
    except (ValueError, AttributeError):
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h + m / 60.0


def kickoff_instant(date: str, kickoff: str) -> str | None:
    """A real instant from the schedule's own date and its Eastern clock.

    `_kickoff_hour` above says why the bare "HH:MM" a football board
    carries is fine for a body clock and emphatically not an instant:
    "which is why the capture-lag and closing-line layers refuse the same
    string rather than guess a date onto it." That refusal was right and
    it had a cost nobody had measured — `lead_min` was NULL on every NFL
    and CFB pick ever journaled, so capture lag is a dimension the
    blind-spot miner has never once been able to convict on. On a market
    that self-closes, when we took the price is not a footnote.

    Nothing has to be guessed. The DATE was never missing — it sits in
    the same game row, two keys away — and the ZONE is the documented
    Eastern the hour arithmetic already assumes. So this joins them, and
    lets the standard library carry daylight saving rather than a
    hard-coded offset that is wrong for four months of a season.

    Returns None on anything it cannot join honestly: no date, no clock,
    a clock it cannot parse, or a machine with no timezone database. A
    refusal costs the dimension; a guess would band bets into the wrong
    pocket, which is worse than not banding them at all.
    """
    hour = _kickoff_hour(kickoff)
    if hour is None or not date:
        return None
    day = str(date).strip()[:10]
    # A CALENDAR DAY, STRICTLY. `date.fromisoformat` accepts ISO WEEK
    # dates on 3.11+, and an NFL board's own `date` is "2026-W01" — the
    # slate label, which sits beside the games and is the obvious wrong
    # thing to hand this. Parsed loosely it returns the Monday of ISO
    # week 1, so a Week 1 pick would have journaled a lead time eight
    # months in the past. Caught here rather than in the journal.
    if (len(day) != 10 or day[4] != "-" or day[7] != "-"
            or not day.replace("-", "").isdigit()):
        return None
    try:
        from zoneinfo import ZoneInfo
        d = _dt.date.fromisoformat(day)
        hh = int(hour)
        stamp = _dt.datetime(d.year, d.month, d.day, hh,
                             int(round((hour - hh) * 60)),
                             tzinfo=ZoneInfo("America/New_York"))
    except Exception:                                         # noqa: BLE001
        return None
    return stamp.isoformat()


def clock_str(hour) -> str:
    """A body-clock hour as a readable time. ``%.0f`` was wrong twice over
    on a half-hour kickoff: it dropped 8.5 to "8:00" and rounded 9.5 up to
    "10:00", so the London window read an hour later than it starts."""
    try:
        h = float(hour)
    except (TypeError, ValueError):
        return "?"
    hh = int(h) % 24
    mm = int(round((h - int(h)) * 60))
    if mm == 60:
        hh, mm = (hh + 1) % 24, 0
    return f"{hh}:{mm:02d}"


def body_clock(team: str, kickoff: str) -> float | None:
    """What time it is by ``team``'s own clock when the ball is kicked."""
    hour = _kickoff_hour(kickoff)
    if hour is None:
        return None
    off = TEAM_UTC_OFFSET_FROM_ET.get((team or "").upper())
    if off is None:
        return None
    return round(hour + off, 2)


def rest_band(days) -> str | None:
    """The banded rest state — the vocabulary the miner slices on."""
    try:
        d = int(days)
    except (TypeError, ValueError):
        return None
    if d <= 0:
        return None                       # unknown, not "no rest"
    if d <= SHORT_WEEK:
        return "short week"
    if d <= 6:
        return "6 days or fewer"
    if d <= 8:
        return "normal week"
    if d < OFF_BYE:
        return "extra days"
    return "off a bye"


def state_for(game, team: str) -> dict:
    """Everything the fatigue layer knows about one team's spot tonight.

    Returns ``{}`` when the schedule carried nothing — a slate built
    without rest rows says nothing rather than inventing a normal week.
    """
    team = (team or "").upper()
    home = (getattr(game, "home", "") or "").upper()
    rest = getattr(game, "home_rest" if team == home else "away_rest", 0) or 0
    opp_rest = getattr(game, "away_rest" if team == home else "home_rest", 0) or 0
    clock = body_clock(team, getattr(game, "kickoff", "") or "")
    band = rest_band(rest)
    if band is None and clock is None:
        return {}
    out = {
        "rest_days": int(rest) or None,
        "rest_band": band,
        "body_clock": clock,
        "neutral_site": bool(getattr(game, "neutral_site", False)),
        "notes": [],
        "warnings": [],
    }
    if band == "short week":
        out["notes"].append(
            f"Short week: {int(rest)} days since the last game — one padded "
            f"practice, no installation week, and Sunday's bumps unhealed")
    elif band == "off a bye":
        out["notes"].append(
            f"Off a bye: {int(rest)} days of rest and two weeks of prep")
    if rest and opp_rest and abs(int(rest) - int(opp_rest)) >= REST_EDGE:
        ahead = int(rest) > int(opp_rest)
        out["notes"].append(
            f"Rest {'edge' if ahead else 'deficit'}: {int(rest)} days to the "
            f"opponent's {int(opp_rest)}")
        if not ahead:
            out["warnings"].append(
                f"Rest deficit: {int(rest)} days against an opponent on "
                f"{int(opp_rest)}. Volume props ride on a team that had less "
                f"time to prepare and to heal")
    if clock is not None and clock <= EARLY_BODY_CLOCK:
        out["notes"].append(
            f"Body clock: kickoff is {clock_str(clock)} by the team's own "
            f"clock — the oldest scheduling angle in the sport")
        if clock <= 10:
            out["warnings"].append(
                f"Early body clock: a {clock_str(clock)} start by this "
                f"team's home clock. Historically a spot the market "
                f"underprices in one direction or the other — journaled "
                f"here so our own record can say which")
    if out["neutral_site"]:
        out["notes"].append(
            "Neutral site: an international trip — flight, time zones and a "
            "disrupted week arrive together")
    return out


def decorate(recommendations: list[dict], games) -> dict:
    """Attach each prop's own team's fatigue state to its card.

    Reasons and warnings only — nothing here touches a probability, a
    stake or the recommendation. ``rest_days`` and ``body_clock`` ride
    along on the dict so the journal can store them and the miner can
    band them later.
    """
    by_team: dict[str, dict] = {}
    for g in games or []:
        for team in ((getattr(g, "home", "") or "").upper(),
                     (getattr(g, "away", "") or "").upper()):
            if team:
                st = state_for(g, team)
                if st:
                    by_team[team] = st
    touched = 0
    for r in recommendations:
        st = by_team.get(str(r.get("team") or "").upper())
        if not st:
            continue
        touched += 1
        r["rest_days"] = st["rest_days"]
        r["body_clock"] = st["body_clock"]
        r["rest_band"] = st["rest_band"]
        if st["notes"]:
            r.setdefault("reasons", []).extend(st["notes"])
        if st["warnings"]:
            r.setdefault("warnings", []).extend(st["warnings"])
    return {"teams": by_team, "decorated": touched}
