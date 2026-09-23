#!/usr/bin/env python3
"""Re-measure what wind, cold and rain do to NFL props (engine/wxfit.py).

    python3 wxfit.py                     # 2016-2025
    python3 wxfit.py --seasons 2019-2025
    python3 wxfit.py --scale             # forecast wind vs the reported wind (FETCHES)

Reads nflverse's schedule and weekly box scores (downloaded into
data/cache on first use), and the kickoff sky from nflverse's
play-by-play, which it downloads once (about 19 MB a season) and keeps
as data/cache/nfl_game_skies.csv. Prints every condition's multiplier,
its SE and seasons, what the rule applies, and what engine/weather.py
ships. Run it off the site's clock — it holds a season of box scores in
memory at a time.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import urllib.request
from pathlib import Path

from engine import weather as W
from engine import wxfit as F
from engine.sources import nflverse as N

ROOT = Path(__file__).resolve().parent
SKIES = ROOT / "data" / "cache" / "nfl_game_skies.csv"
PBP = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{s}.csv.gz"
#: Open-Meteo's archive of its own past forecasts — the same model family
#: the board reads for a coming game, kept from 2022 on.
PAST_FORECAST = ("https://historical-forecast-api.open-meteo.com/v1/forecast"
                 "?latitude={lat:.4f}&longitude={lon:.4f}"
                 "&hourly=temperature_2m,wind_speed_10m&wind_speed_unit=mph"
                 "&temperature_unit=fahrenheit&timezone=UTC&start_date={start}&end_date={end}")


def skies(seasons) -> dict:
    """{game_id: kickoff sky text}, cached; missing seasons are fetched."""
    have: dict = {}
    if SKIES.exists():
        with open(SKIES, newline="") as fh:
            have = {r["game_id"]: r["weather"] for r in csv.DictReader(fh)}
    got = {g[:4] for g in have}
    for s in seasons:
        if str(s) in got:
            continue
        print(f"  fetching {s} play-by-play for the kickoff sky …", flush=True)
        with urllib.request.urlopen(PBP.format(s=s), timeout=300) as resp:
            raw = resp.read()
        with gzip.open(io.BytesIO(raw), "rt", newline="") as fh:
            for r in csv.DictReader(fh):
                have.setdefault(r["game_id"], r.get("weather") or "")
    SKIES.parent.mkdir(parents=True, exist_ok=True)
    with open(SKIES, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["game_id", "weather"])
        for k in sorted(have):
            w.writerow([k, have[k]])
    return have


def _get_json(url: str) -> dict:
    import json
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wind_pairs(schedule: list[dict], seasons, fetch=None) -> list[tuple]:
    """``[(reported, forecast)]`` for every played outdoor game with a
    reported wind: one archived-forecast request per home stadium per
    season, the kickoff hour picked the way the board picks it."""
    from engine.cfb.wx import pick_hour
    from engine.fatigue import kickoff_instant
    from engine.stadiums import STADIUM_COORDS
    fetch = fetch or (lambda lat, lon, start, end: _get_json(
        PAST_FORECAST.format(lat=lat, lon=lon, start=start, end=end)))
    by: dict = {}
    for g in schedule:
        if (str(g.get("game_type") or "REG") == "REG" and int(g["season"]) in seasons
                and str(g.get("roof") or "").lower() in ("outdoors", "open")
                and g.get("wind") not in (None, "") and str(g.get("location") or "") != "Neutral"):
            by.setdefault((g["home_team"], int(g["season"])), []).append(g)
    out = []
    for (home, _s), games in sorted(by.items()):
        coords = STADIUM_COORDS.get(home)
        if not coords:
            continue
        days = sorted(g["gameday"] for g in games)
        try:
            payload = fetch(coords[0], coords[1], days[0], days[-1])
        except Exception as exc:                              # noqa: BLE001
            print(f"  {home} {_s}: {type(exc).__name__}: {exc}")
            continue
        for g in games:
            ko = kickoff_instant(g["gameday"], g.get("gametime") or "")
            got = pick_hour(payload, ko) if ko else None
            if got:
                out.append((float(g["wind"]), float(got["wind_mph"])))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default=f"{F.SEASONS[0]}-{F.SEASONS[-1]}")
    ap.add_argument("--scale", action="store_true",
                    help="compare Open-Meteo's archived kickoff-hour forecasts with the "
                         "reported wind, 2023-2025 (fetches ~75 small files)")
    args = ap.parse_args()
    if args.scale:
        got = F.scale(wind_pairs(N.load_schedules(), range(2023, 2026)))
        rows = got.pop("by_forecast", [])
        print("forecast wind against the reported wind, 2023-2025 outdoor games:", got)
        for r in rows:
            print(f"  forecast {r['forecast']:<6} mph  n {r['n']:<4} reported median "
                  f"{r['reported_median']:.0f}  same band once converted {r['same_band_converted']:.0%}")
        r = got.get("median_ratio")
        if r is not None:
            ships = W.FORECAST_WIND_SCALE
            print(f"the board converts at ×{ships:.3f}: "
                  + ("the same — nothing to change" if abs(r - ships) <= 0.03 else
                     f"MEASURED ×{r:.3f} NOW — engine/weather.FORECAST_WIND_SCALE is behind"))
        return
    a, _, b = args.seasons.partition("-")
    seasons = range(int(a), int(b or a) + 1)
    cond = F.conditions(N.load_schedules(), skies(seasons))
    pts, tds = [], []
    for s in seasons:
        rows = N.load_weekly_stats(s)
        pts += F.samples(s, rows, cond)
        tds += F.td_samples(s, rows, cond)
        del rows
    props, td = F.measure_all(pts), F.measure_td(tds)
    rule = F.shipped(props, td)
    for name, res in props.items():
        print(f"\n{name}")
        for (m, g, tier), r in sorted(res.items()):
            print(f"  {m:<11}{g:<5}{tier:<7} ×{r['mult']:.3f} ± {r['se']:.3f}  n {r['n']:<5} "
                  + " ".join(f"{s}:{x:.2f}" for s, x in r["per"].items())
                  + ("   CLEARS" if F.clears(r) else ""))
    for name, res in td.items():
        print(f"\ntouchdowns per implied point — {name}")
        for (kind, tier), r in sorted(res.items()):
            print(f"  {kind:<5}{tier:<7} ×{r['mult']:.3f} ± {r['se']:.3f}  n {r['n']:<5} "
                  + " ".join(f"{s}:{x:.2f}" for s, x in r["per"].items())
                  + ("   CLEARS" if F.clears(r) else ""))
    print("\nthe rule applies:  ", rule)
    print("weather.py ships:  ", W.shipped())
    print("same" if rule == W.shipped() else "DIFFERENT — engine/weather.py is behind this measurement")


if __name__ == "__main__":
    main()
