"""Kickoff weather for the NFL slate.

WHAT WAS THERE BEFORE, and it was not a forecast. The board's weather
came from the nflverse schedule's `temp` and `wind` columns, which
nflverse fills from the game's OWN box score — so every outdoor game on
a forward board arrived blank and took the engine's mild-day prior of
60°F and 6 mph. On 2026-08-26 that prior was flagged as one
(`Weather.measured`) so it could stop posing as a reading, and the card
started saying "weather not pulled". This is the other half: actually
pulling it.

COLLEGE HAS DONE THIS SINCE 2026-08-24 and this is deliberately the same
machine. `engine/cfb/wx.fetch_forecast`, `pick_hour` and `compass` take
a latitude, a longitude, a date and a kickoff instant and return
temp/wind/direction at the nearest hour; none of that is college-shaped,
and re-implementing it here would be two copies of one join drifting
apart. What the NFL needed was the two things college gets from its own
feeds — WHERE the stadium is and WHEN the ball is kicked:

  * WHERE comes from `engine.stadiums.STADIUM_COORDS`, a table checked
    against two others already in this repo rather than taken on trust
    (see its own note, and tests/test_nflwx.py).
  * WHEN comes from `engine.fatigue.kickoff_instant`, which joins the
    board's bare Eastern "20:20" to the game's own date. That join was
    written for capture lag and this is its second reader — the reason
    the NFL could not ask for a forecast at the kickoff HOUR before it
    existed was that the NFL had no kickoff hour, only a clock.

A MISS IS A MISS, which is the rule the whole weather layer now runs on.
An unknown stadium, a refused forecast, a kickoff too far out for the
16-day board: the game keeps the prior and keeps `measured=False`, the
card keeps saying "weather not pulled", and nothing is invented. A dome
is answered without asking anybody — climate control is a fact about a
building.

Standard library; the fetcher is injectable so the join tests offline,
exactly as the college one does.
"""

from __future__ import annotations

from .fatigue import kickoff_instant
from .models import Weather
from .stadiums import STADIUM_COORDS

#: Roof values that mean the weather is indoors. `open` is a retractable
#: roof that is OPEN — outdoor weather — and reading it as a dome would
#: skip a forecast for a game being played in the rain.
INDOOR_ROOFS = ("dome", "closed")

#: The precipitation chance at which the board's own layers already call
#: it rain (`engine/weather.py` reads `w.rain or w.precip_chance >= 0.6`),
#: and the temperature below which that precipitation is snow.
PRECIP_LIKELY = 0.6
FREEZING_F = 32.0


def _default_forecast(lat, lon, date, kickoff):
    from .cfb.wx import fetch_forecast, pick_hour
    return pick_hour(fetch_forecast(lat, lon, date), kickoff)


def coords_for(team: str):
    """The stadium the HOME team plays in, or None.

    A neutral site never takes the home team's stadium — a London or
    Munich game given New Jersey's weather would be invented. It finds
    its own through `venue_coords`, or keeps the prior.
    """
    return STADIUM_COORDS.get(str(team or "").upper())


#: The international sites the schedule names at a neutral game, keyed by
#: a word of the schedule's own `stadium` text (nflverse, 2019-2026:
#: "Maracana Stadium", "Tottenham Stadium", "Allianz Arena", "FC Bayern
#: Munich Stadium", "Estadio Banorte" — the Azteca renamed …). 2026-09-23:
#: Ravens at Cowboys in Rio was the one outdoor game on the week-3 board
#: without a forecast, because the location column says only "Neutral".
NEUTRAL_VENUES = (
    ("maracana", (-22.912, -43.230)),
    ("tottenham", (51.604, -0.066)),
    ("wembley", (51.556, -0.280)),
    ("allianz", (48.219, 11.625)),
    ("bayern", (48.219, 11.625)),
    ("deutsche bank park", (50.069, 8.646)),
    ("frankfurt", (50.069, 8.646)),
    ("olympiastadion", (52.515, 13.239)),
    ("corinthians", (-23.545, -46.474)),
    ("neo quimica", (-23.545, -46.474)),
    ("azteca", (19.303, -99.150)),
    ("banorte", (19.303, -99.150)),
    ("bernabeu", (40.453, -3.688)),
    ("croke", (53.361, -6.251)),
    ("stade de france", (48.924, 2.360)),
    ("melbourne cricket", (-37.820, 144.983)),
)


def venue_coords(name: str):
    """A neutral site's coordinates from the schedule's stadium name, or None."""
    import unicodedata
    key = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    return next((c for word, c in NEUTRAL_VENUES if word in key), None)


def attach(games, forecast=None) -> int:
    """Stamp a real forecast on every game we can honestly answer for.

    Mutates each ``Game``'s ``weather`` and returns how many were
    stamped. Domes count: they are answered, just not by asking.
    """
    fc = forecast or _default_forecast
    stamped = 0
    for g in games or []:
        roof = str(getattr(g, "roof", "") or "").strip().lower()
        w = getattr(g, "weather", None)
        if roof in INDOOR_ROOFS or (w is not None and w.dome):
            # Answered without asking anybody — climate control is a fact
            # about a building. The flag is SET here rather than assumed
            # from the source: a Game handed in from anywhere else would
            # otherwise be indoors and unmeasured at the same time, which
            # is two different sentences on the same card.
            g.weather = Weather(dome=True, temp_f=70.0, wind_mph=0.0,
                                measured=True)
            stamped += 1
            continue
        coords = (venue_coords(getattr(g, "venue", "")) if getattr(g, "neutral_site", False)
                  else coords_for(getattr(g, "home", "")))
        if not coords:
            continue
        when = getattr(g, "kickoff", "") or ""
        # A full ISO kickoff (a live feed stamped it) is already an
        # instant; the schedule's bare Eastern clock needs its own date.
        if len(str(when)) <= 5:
            when = kickoff_instant(getattr(g, "date", "") or "", when) or ""
        if not when:
            continue
        try:
            got = fc(coords[0], coords[1], str(when)[:10], when)
        except Exception:                                 # noqa: BLE001
            got = None                     # a refused forecast is a miss
        if not got:
            continue
        temp = float(got.get("temp_f", 60.0))
        precip = float(got.get("precip_chance") or 0.0)
        # RAIN AND SNOW ARE DERIVED, and narrowly. `engine/weather.py`
        # and `engine/touchdowns.py` both read these booleans and both
        # already treat `precip_chance >= 0.6` as rain themselves, so the
        # threshold is theirs rather than a new one invented here; snow
        # is that same precipitation at or below freezing. Open-Meteo's
        # hourly board carries a precipitation TYPE we do not request —
        # if these two ever need to be better than an inference, that is
        # the field to ask for rather than a cleverer rule.
        likely = precip >= PRECIP_LIKELY
        g.weather = Weather(
            dome=False,
            temp_f=temp,
            wind_mph=float(got.get("wind_mph", 0.0)),
            wind_dir=str(got.get("wind_dir") or ""),
            precip_chance=precip,
            rain=likely and temp > FREEZING_F,
            snow=likely and temp <= FREEZING_F,
            measured=True,
            forecast=True,
        )
        stamped += 1
    return stamped
