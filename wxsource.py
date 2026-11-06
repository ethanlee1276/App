"""The boards' forecast source: the National Weather Service against Open-Meteo.

    python3 wxsource.py --compare      # read-only: every NFL stadium, the next three days (FETCHES)

Ethan, 6 November 2026: "move the weather to the NWS". The boards read either
source through one switch (``QB_WEATHER_SOURCE``, `engine.sources.nws`), and
the NWS answer comes back in Open-Meteo's own table, so nothing downstream
changes. This reads both, for every NFL stadium (every one is in the US), at
the same six hours over the next three days, the hours a board reads a
kickoff at (`engine.cfb.wx.nearest_hour`), and says:

  * per stadium, the two readings side by side (temperature, wind, chance of
    rain);
  * a verdict: SWITCH when the NWS answered for the stadiums and its numbers
    sit where a second forecast's should (temperature and wind within a few
    degrees and miles an hour of Open-Meteo's at the middle, no bias the size
    of a unit slip), else CHECK, naming what to look at.

Writes nothing. On SWITCH the boards change source with one setting and a
restart (runbook KY); members then read the NWS.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.cfb.wx import nearest_hour                               # noqa: E402

#: The hours compared, from now: a board's kickoffs within the NWS's six and
#: a half days, the nearer ones twice as often.
OFFSETS_H = (6, 12, 24, 36, 48, 72)
#: Where two honest forecasts' middles sit apart (°F, mph); a unit slip
#: (°C as °F, km/h as mph) is many times these.
TEMP_BAND = 4.0
WIND_BAND = 4.0
#: How far one source may lean against the other on average before it reads
#: as a slip rather than a difference of opinion.
BIAS_BAND = 3.0
#: Of the stadiums asked, how many must the NWS answer.
COVERAGE = 0.9

OPEN_METEO = ("https://api.open-meteo.com/v1/forecast?latitude={lat:.4f}&longitude={lon:.4f}"
              "&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,precipitation_probability"
              "&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=UTC&forecast_days=4")


def sample_hours(now: _dt.datetime, offsets=OFFSETS_H) -> list[str]:
    """The UTC instants compared, on the hour, as a kickoff is written."""
    base = now.astimezone(_dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    return [(base + _dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ") for h in offsets]


def reading(table: dict, at: str) -> dict | None:
    """``{temp, wind, rain}`` at the hour nearest ``at``, as a board reads it."""
    i = nearest_hour(table, at)
    if i is None:
        return None
    hourly = (table or {}).get("hourly") or {}

    def col(key):
        vals = hourly.get(key) or []
        return vals[i] if i < len(vals) else None
    temp, wind = col("temperature_2m"), col("wind_speed_10m")
    if temp is None or wind is None:
        return None
    return {"temp": float(temp), "wind": float(wind), "rain": float(col("precipitation_probability") or 0.0)}


def compare(places: dict, hours: list[str], nws_of, om_of) -> dict:
    """Both sources at every place and hour. ``nws_of`` and ``om_of`` take
    ``(lat, lon)`` and return an hourly table; a failure is a place the
    source did not answer."""
    rows, answered, asked = [], 0, 0
    for name, (lat, lon) in sorted(places.items()):
        asked += 1
        try:
            n = nws_of(lat, lon)
        except Exception:                                 # noqa: BLE001
            n = None
        try:
            o = om_of(lat, lon)
        except Exception:                                 # noqa: BLE001
            o = None
        pairs = []
        for at in hours:
            a, b = reading(n, at) if n else None, reading(o, at) if o else None
            pairs.append((at, a, b))
        if any(a for _at, a, _b in pairs):
            answered += 1
        rows.append((name, pairs))
    dt_ = [a["temp"] - b["temp"] for _n, ps in rows for _at, a, b in ps if a and b]
    dw = [a["wind"] - b["wind"] for _n, ps in rows for _at, a, b in ps if a and b]
    dr = [a["rain"] - b["rain"] for _n, ps in rows for _at, a, b in ps if a and b]
    return {"rows": rows, "asked": asked, "answered": answered, "pairs": len(dt_),
            "temp_mid": statistics.median([abs(x) for x in dt_]) if dt_ else None,
            "wind_mid": statistics.median([abs(x) for x in dw]) if dw else None,
            "temp_bias": statistics.fmean(dt_) if dt_ else None,
            "wind_bias": statistics.fmean(dw) if dw else None,
            "rain_mid": statistics.median([abs(x) for x in dr]) if dr else None}


def verdict(got: dict) -> str:
    """One line: SWITCH, or CHECK and what to look at."""
    if not got["asked"] or got["answered"] / got["asked"] < COVERAGE:
        return (f"CHECK: the NWS answered for {got['answered']} of {got['asked']} stadiums; the box "
                f"may not reach api.weather.gov, or the API refused it (the probe's lines above say)")
    if not got["pairs"]:
        return "CHECK: Open-Meteo answered for none of them, so there is nothing to compare against"
    why = []
    if got["temp_mid"] > TEMP_BAND or abs(got["temp_bias"]) > BIAS_BAND:
        why.append(f"temperature {got['temp_mid']:.1f}°F apart at the middle, NWS {got['temp_bias']:+.1f} on average")
    if got["wind_mid"] > WIND_BAND or abs(got["wind_bias"]) > BIAS_BAND:
        why.append(f"wind {got['wind_mid']:.1f} mph apart at the middle, NWS {got['wind_bias']:+.1f} on average")
    if why:
        return "CHECK: " + "; ".join(why) + ": paste this back before switching"
    return (f"SWITCH: the NWS answered for {got['answered']} of {got['asked']} stadiums and sits within "
            f"{got['temp_mid']:.1f}°F and {got['wind_mid']:.1f} mph of Open-Meteo at the middle, "
            f"{got['temp_bias']:+.1f}°F and {got['wind_bias']:+.1f} mph on average (the board's wind bands "
            f"were fitted on Open-Meteo's forecasts), rain chance {got['rain_mid']:.0f} points apart: "
            f"the boards can read it")


def report(got: dict) -> list[str]:
    out = [f"NWS against Open-Meteo, {got['asked']} NFL stadiums, {len(got['rows'][0][1]) if got['rows'] else 0} "
           f"hours each over the next three days ({got['pairs']} pairs read by both):"]
    for name, pairs in got["rows"]:
        cells = []
        for at, a, b in pairs:
            if a and b:
                cells.append(f"{at[5:13]}Z {a['temp']:.0f}/{b['temp']:.0f}°F {a['wind']:.0f}/{b['wind']:.0f}mph "
                             f"{a['rain']:.0f}/{b['rain']:.0f}%")
            else:
                cells.append(f"{at[5:13]}Z {'nws' if a else '-'}/{'om' if b else '-'}")
        out.append(f"  {name:<4} " + "  ".join(cells[:3]))
    out.append("  (each cell: NWS/Open-Meteo)")
    out.append(verdict(got))
    return out


def _nws(lat, lon):
    from engine.sources import nws
    return nws.forecast(lat, lon, ttl=3600)


def _om(lat, lon):
    from engine.sources.fetch import fetch_json
    return fetch_json(OPEN_METEO.format(lat=lat, lon=lon), f"wxcompare_om_{lat:.2f}_{lon:.2f}.json", ttl=3600)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--compare", action="store_true",
                    help="every NFL stadium, both sources, the next three days (read-only; about 100 requests)")
    args = ap.parse_args()
    if not args.compare:
        ap.print_help()
        return
    # Not "which source the boards read": a shell run by hand cannot see the
    # service's settings (`sudo ./deploy/setenv.sh --show` can).
    from engine.stadiums import STADIUM_COORDS
    got = compare(dict(STADIUM_COORDS), sample_hours(_dt.datetime.now(_dt.timezone.utc)), _nws, _om)
    for line in report(got):
        print(line)


if __name__ == "__main__":
    main()
