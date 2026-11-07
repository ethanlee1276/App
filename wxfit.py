#!/usr/bin/env python3
"""Re-measure what wind, cold and rain do to NFL props (engine/wxfit.py).

    python3 wxfit.py                     # 2016-2025
    python3 wxfit.py --seasons 2019-2025
    python3 wxfit.py --scale             # forecast wind vs the reported wind (FETCHES)
    python3 wxfit.py --totals            # forecast rain vs the closing total, 2022-2025 (FETCHES)
    python3 wxfit.py --college           # college's own carries in rain, 2022-2025 (FETCHES)

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


#: The same archive, with the chance of rain the board reads at kickoff.
PAST_RAIN = ("https://historical-forecast-api.open-meteo.com/v1/forecast"
             "?latitude={lat:.4f}&longitude={lon:.4f}"
             "&hourly=temperature_2m,wind_speed_10m,precipitation_probability"
             "&wind_speed_unit=mph&temperature_unit=fahrenheit&timezone=UTC"
             "&start_date={start}&end_date={end}")


def rain_rows(schedule: list[dict], seasons, fetch=None) -> list[dict]:
    """``[{season, chance, actual, close}]`` for every played outdoor game
    with a closing total: one archived-forecast request per home stadium per
    season, the kickoff hour picked the way the board picks it."""
    from engine.cfb.wx import pick_hour
    from engine.fatigue import kickoff_instant
    from engine.stadiums import STADIUM_COORDS
    fetch = fetch or (lambda lat, lon, start, end: _get_json(
        PAST_RAIN.format(lat=lat, lon=lon, start=start, end=end)))
    by: dict = {}
    for g in schedule:
        if (str(g.get("game_type") or "REG") == "REG" and int(g["season"]) in seasons
                and str(g.get("roof") or "").lower() in ("outdoors", "open")
                and g.get("total_line") not in (None, "") and g.get("home_score") not in (None, "")
                and str(g.get("location") or "") != "Neutral"):
            by.setdefault((g["home_team"], int(g["season"])), []).append(g)
    out = []
    for (home, season), games in sorted(by.items()):
        coords = STADIUM_COORDS.get(home)
        if not coords:
            continue
        days = sorted(g["gameday"] for g in games)
        try:
            payload = fetch(coords[0], coords[1], days[0], days[-1])
        except Exception as exc:                              # noqa: BLE001
            print(f"  {home} {season}: {type(exc).__name__}: {exc}")
            continue
        for g in games:
            ko = kickoff_instant(g["gameday"], g.get("gametime") or "")
            got = pick_hour(payload, ko) if ko else None
            if got is None:
                continue
            out.append({"season": season, "chance": got["precip_chance"],
                        "actual": float(g["home_score"]) + float(g["away_score"]),
                        "close": float(g["total_line"])})
    return out


#: COLLEGE'S OWN WEATHER (2026-11-06): Open-Meteo's archive of what fell, at
#: the venue, hour by hour — ERA5 reanalysis, free and keyless. One request
#: per venue per season.
COLLEGE_ARCHIVE = ("https://archive-api.open-meteo.com/v1/archive"
                   "?latitude={lat:.4f}&longitude={lon:.4f}"
                   "&hourly=temperature_2m,precipitation,snowfall,wind_speed_10m"
                   "&wind_speed_unit=mph&temperature_unit=fahrenheit&timezone=UTC"
                   "&start_date={start}&end_date={end}")


def college_weather(games: list[dict], fetch=None, pause: float = 0.15) -> dict:
    """``{(season, game_id): engine.wxfit.game_weather}`` for every outdoor
    game: one archive request per venue per season, its dates spanning the
    season's games there (a day past the last, for a late kickoff's window)."""
    import datetime as _dt
    import time as _time
    fetch = fetch or (lambda lat, lon, start, end: _get_json(
        COLLEGE_ARCHIVE.format(lat=lat, lon=lon, start=start, end=end)))
    by: dict = {}
    for g in games:
        if not g["roofed"]:
            by.setdefault((round(g["lat"], 4), round(g["lon"], 4), g["season"]), []).append(g)
    out, failed = {}, 0
    for (lat, lon, season), gs in sorted(by.items()):
        days = sorted(g["kickoff"][:10] for g in gs)
        end = (_dt.date.fromisoformat(days[-1]) + _dt.timedelta(days=1)).isoformat()
        try:
            payload = fetch(lat, lon, days[0], end)
        except Exception as exc:                              # noqa: BLE001
            failed += 1
            if failed <= 5:
                print(f"  {lat},{lon} {season}: {type(exc).__name__}: {exc}")
            continue
        for g in gs:
            w = F.game_weather(payload, g["kickoff"])
            if w:
                out[(season, g["game_id"])] = w
        if pause:
            _time.sleep(pause)
    if failed:
        print(f"  {failed} of {len(by)} venue-seasons did not answer")
    return out


def college_carries(conn, seasons) -> dict:
    """``{(season, game_id, team): carries}`` from the box's college logs."""
    seasons = [int(s) for s in seasons]
    q = ("SELECT season, game_id, team, SUM(value) FROM player_game_logs "
         "WHERE sport='cfb' AND market='rush_att' AND season IN (%s) "
         "GROUP BY season, game_id, team" % ",".join("?" * len(seasons)))
    return {(int(s), str(g), str(t)): float(v or 0.0) for s, g, t, v in conn.execute(q, seasons)}


def college_games_all(seasons) -> list[dict]:
    """Every season's placed FBS games off the mirror, venues from CFBD."""
    from engine import cfbteams
    from engine.cfb import wx
    from engine.sources.cfbfastr import SCHEDULE_URL
    from engine.sources.fetch import fetch_csv
    ids = cfbteams.load_ids() or None
    venues = wx.venue_index(wx.fetch_venues())
    games = []
    for s in seasons:
        rows = fetch_csv(SCHEDULE_URL.format(season=int(s)), f"cfb_schedules_{int(s)}.csv",
                         ttl=86400 * 7)
        games += F.college_games(rows, int(s), ids, venues)
    return games


def college_verdict(v: dict | None, nfl: float | None) -> str:
    """One line: what college's own games say beside the NFL's rain step."""
    if not v:
        return "TOO FEW: not enough wet college games with carries to say; the NFL's step stands"
    step = f"the NFL's ×{nfl:.3f}" if nfl else "no NFL step"
    near = nfl is not None and abs(v["mult"] - nfl) <= 2 * v["se"]
    if F.clears(v):
        if near or nfl is None:
            return (f"AGREES: college's own carries in rain ×{v['mult']:.3f} ± {v['se']:.3f} clears, "
                    f"in line with {step}; the step college reads stands")
        return (f"DIFFERS: college's own ×{v['mult']:.3f} ± {v['se']:.3f} clears and is not {step}; "
                f"worth college's own step, as its own change")
    if near:
        return (f"NOT ENOUGH: college's own ×{v['mult']:.3f} ± {v['se']:.3f} neither clears nor "
                f"contradicts {step}; the step college reads stands")
    return (f"CONTRADICTS: college's own games say ×{v['mult']:.3f} ± {v['se']:.3f}, not {step}; "
            f"college should drop the step, as its own change")


def college_report(seasons=F.COLLEGE_SEASONS, games=None, weather=None, carries=None) -> list[str]:
    """What --college prints. Each input is fetched when not handed in."""
    games = college_games_all(seasons) if games is None else games
    weather = college_weather(games) if weather is None else weather
    if carries is None:
        from engine import db as _db
        carries = college_carries(_db.connect(), seasons)
    outdoor = [g for g in games if not g["roofed"]]
    read = [weather[(g["season"], g["game_id"])] for g in outdoor
            if (g["season"], g["game_id"]) in weather]
    got = F.college_measure(games, weather, carries)
    lines = [f"college {seasons[0]}-{seasons[-1]}: {len(games)} FBS games placed "
             f"({len(games) - len(outdoor)} indoors); {len(read)} outdoor with a reading at kickoff, "
             f"{sum(1 for w in read if w['precip'] == 'rain')} wet, "
             f"{sum(1 for w in read if w['precip'] == 'snow')} snowy; "
             f"{len(carries)} team-games with carries in the box's logs",
             "  a team's carries (every rusher) against its own earlier games, over the same "
             "in domes or dry, still, mild games:"]
    names = {"rain": "rain", "snow": "snow", "freeze": "freezing, dry",
             "8-12": "wind 8-12 mph", "12-18": "wind 12-18 mph", "18+": "wind 18+ mph"}
    for tier, label in names.items():
        v = got.get(tier)
        if v:
            per = " ".join(f"{s}:{x:.3f}" for s, x in v["per"].items())
            lines.append(f"  {label:<16} ×{v['mult']:.3f} ± {v['se']:.3f}  n {v['n']:<4} {per}"
                         + ("   CLEARS" if F.clears(v) else ""))
    lines.append(college_verdict(got.get("rain"), W.RAIN.get(("rush_att", "RB"))))
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default=f"{F.SEASONS[0]}-{F.SEASONS[-1]}")
    ap.add_argument("--scale", action="store_true",
                    help="compare Open-Meteo's archived kickoff-hour forecasts with the "
                         "reported wind, 2023-2025 (fetches ~75 small files)")
    ap.add_argument("--totals", action="store_true",
                    help="games forecast wet at kickoff against the closing total, 2022-2025 "
                         "(fetches about 110 small files of Open-Meteo's archived forecasts)")
    ap.add_argument("--college", action="store_true",
                    help="college's own carries in rain, 2022-2025: the mirror's kickoffs, CFBD's "
                         "venues, Open-Meteo's archive (one request a venue a season) and the box's "
                         "college logs")
    args = ap.parse_args()
    if args.college:
        for line in college_report():
            print(line)
        return
    if args.totals:
        rows = rain_rows(N.load_schedules(), range(2022, 2026))
        got = F.totals_by_forecast(rows)
        verdict = got.pop("verdict")
        print(f"outdoor games 2022-2025 with a forecast at kickoff: {len(rows)}; "
              f"points minus the closing total, by the forecast's chance of rain")
        for name, _lo in reversed([(n, lo) for lo, n in F.TOTAL_BUCKETS]):
            r = got.get(name)
            if r:
                print(f"  {name:<10} n {r['n']:<4} {r['mean']:+.2f} ± {r['se']:.2f}   "
                      + " ".join(f"{s}:{x:+.1f}" for s, x in r["per"].items()))
        print(verdict)
        return
    if args.scale:
        pairs = wind_pairs(N.load_schedules(), range(2023, 2026))
        got = F.scale(pairs)
        rows = got.pop("by_forecast", [])
        print("forecast wind against the reported wind, 2023-2025 outdoor games:", got)
        for r in rows:
            print(f"  forecast {r['forecast']:<6} mph  n {r['n']:<4} reported median "
                  f"{r['reported_median']:.0f}  same band once converted {r['same_band_converted']:.0%}")
        # The question that matters: at each forecast, is the cut the board
        # gives the cut the games say? Not a ratio of winds — on 2026-09-23
        # the median ratio said ×0.714 and that was a calm-day artifact.
        table = {**W.WIND, ("anytime_td", "pass"): W.TD_WIND["pass"]}
        rows = F.effect_by_forecast(pairs, table, W.forecast_cut)
        print("\nthe cut at each forecast — measured (over the reported winds) / what the board gives")
        for row in rows:
            print(f"  forecast {row['forecast']:<6} n {row['n']:<4} " + "  ".join(
                f"{m} {g} {t:.3f}/{b:.3f}" for (m, g), (t, b) in row["markets"].items()))
        off = max((abs(t - b) for row in rows for t, b in row["markets"].values()), default=0.0)
        if off <= F.FORECAST_TOLERANCE:
            print(f"the board's forecast table matches (largest gap {off:.3f}) — nothing to change")
        else:
            print(f"CHANGE — a range is off by {off:.3f}; engine/weather.WIND_FORECAST measured now:")
            for key in table:
                print(f"    {key}: " + "{" + ", ".join(
                    f'"{row["forecast"]}": {row["markets"][key][0]:.3f}' for row in rows) + "},")
        return
    a, _, b = args.seasons.partition("-")
    seasons = range(int(a), int(b or a) + 1)
    cond = F.conditions(N.load_schedules(), skies(seasons))
    pts, tds = [], []
    for s in seasons:
        rows = N.load_weekly_stats(s)
        pts += F.samples(s, rows, cond) + F.team_samples(s, rows, cond)
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
