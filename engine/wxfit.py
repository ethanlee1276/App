"""Weather, measured: what wind, cold and rain do to a player's number.

Ethan, 2026-09-23: "if it was a wind game it would should make passing
props lower so it doesn't seem like the model is tracking the weather and
shit correctly either idk, it seems weird so figure all that out."

WHAT WAS THERE. engine/weather.py's bands (×0.95 passing at 12 mph, ×0.90
at 18, ×0.82 at 25, a rushing LIFT in wind, a rain and a cold haircut)
were written from the spec, never measured — and the forecast they were
meant to read never reached them: nfl_build.show_games stamped it on its
own list of games and build_slate read the schedule again, so every
outdoor game a projection saw was the 60°F / 6 mph prior (fixed the same
day; see nflverse.build_slate's ``games``).

THE MEASUREMENT, per player-game from week 4 on with three earlier games
(a quarterback's games with fewer than 15 throws left out, as the board
does):

    expected = the projection's own starting point: engine/form
               .compute_form over his earlier games that season
    y        = what he did

and the multiplier for a condition is actual/expected in it over
actual/expected in games without it — the arithmetic engine/qbfit and
engine/matefit ship with (`qbfit.measure`). The conditions come from the
played games: nflverse's schedule (roof, temperature, wind at kickoff) and
the game book's kickoff sky, which nflverse's play-by-play carries as text
("Rain Temp: 58° F, Humidity: 84%, Wind: East 11 mph").

Each condition is measured where the others are absent, so a cold windy
game is not counted twice when the board multiplies the two:

    wind    games above freezing without rain or snow; base = roofed or
            under 8 mph
    freeze  games under 12 mph without rain or snow; base = roofed or
            above 32°F
    rain    games under 12 mph and above freezing; base = roofed or dry
    snow    games under 12 mph; base = roofed or dry

TOUCHDOWNS are measured on the anytime-TD model's own terms. It starts
from the book's implied team total (touchdowns.py), and the total already
carries some of the wind, so the question there is touchdowns PER IMPLIED
POINT — passing touchdowns for the pass catchers, rushing touchdowns for
the backs — against the same bases.

THE RULE: applied where the multiplier sits two standard errors from 1.0
AND more than half of the seasons that hold the condition point the same
way (qbfit's "three of four", for ten seasons) AND at least forty games
stand behind it. A wind band that does not
clear on its own takes the band below it when that one cleared — wind
does not help a passing game more as it strengthens; 18 mph and up is
about ten games a season, too few to clear alone for every market.

Standard library only; nothing here reads the network (wxfit.py does).
"""
from __future__ import annotations

import math
import re
from collections import defaultdict

from .qbfit import measure

SEASONS = tuple(range(2016, 2026))
#: Lower edges, strongest first. Under 8 mph is calm.
WIND_EDGES = ((18.0, "18+"), (12.0, "12-18"), (8.0, "8-12"))
BANDS = ("8-12", "12-18", "18+")
FREEZE_F = 32.0
#: The cold, rain and snow cells are measured on games under this wind.
STILL_MPH = 12.0
FIRST_WEEK = 4
MIN_GAMES = 3
QB_ATTEMPTS = 15
#: Fewer games than this is a handful however far it sits from 1.0: a
#: quarterback's snow starts over ten seasons are 22 (×0.85), and the
#: backs' snow touchdowns (×1.77) stand on 26 team-games.
MIN_N = 40

#: position -> ((market, stat column(s), form floor), ...)
MARKETS = {
    "QB": (("pass_yds", ("passing_yards",), 120.0), ("pass_td", ("passing_tds",), 0.3)),
    "WR": (("rec_yds", ("receiving_yards",), 15.0), ("receptions", ("receptions",), 1.5)),
    "TE": (("rec_yds", ("receiving_yards",), 15.0), ("receptions", ("receptions",), 1.5)),
    "RB": (("rush_yds", ("rushing_yards",), 15.0), ("rec_yds", ("receiving_yards",), 8.0),
           ("receptions", ("receptions",), 1.0)),
}
#: Receivers and tight ends are measured as one group, as the board prices them.
GROUP = {"QB": "QB", "WR": "WRTE", "TE": "WRTE", "RB": "RB"}

_PRECIP = re.compile(r"rain|shower|drizzle|snow|sleet|flurr|flake", re.I)
_SNOW = re.compile(r"snow|sleet|flurr|flake", re.I)
#: "Chance of rain", "rain expected later": a forecast in the sky line, not the sky.
_NOT_NOW = re.compile(r"chance|possible|later|expected|forecast", re.I)
_WIND = re.compile(r"wind:?\s*(?:[a-z ]+?\s)?(\d+)\s*mph", re.I)
_TEMP = re.compile(r"temp:?\s*(-?\d+)", re.I)


def _f(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def band(wind: float) -> str:
    for edge, name in WIND_EDGES:
        if wind >= edge:
            return name
    return "calm"


def precip_of(sky: str) -> str | None:
    """"rain", "snow" or None from the game book's kickoff sky."""
    sky = sky or ""
    if not _PRECIP.search(sky) or _NOT_NOW.search(sky):
        return None
    return "snow" if _SNOW.search(sky) else "rain"


def conditions(schedule: list[dict], skies: dict | None = None) -> dict:
    """``{(season, week, team): {"roofed", "wind", "temp", "precip", "implied"}}``.

    ``schedule`` is nflverse's games.csv (regular season kept); ``skies``
    is ``{game_id: sky text}`` from the play-by-play. The schedule's wind
    and temperature win; the sky text fills a blank (2022 left 91 outdoor
    games without a wind reading).
    """
    skies = skies or {}
    out = {}
    for g in schedule:
        if str(g.get("game_type") or "REG") != "REG":
            continue
        season, week = int(g["season"]), int(g["week"])
        sky = skies.get(g.get("game_id") or "", "")
        roofed = str(g.get("roof") or "").lower() in ("dome", "closed")
        wind = _f(g.get("wind"))
        if wind is None and (m := _WIND.search(sky)):
            wind = float(m.group(1))
        temp = _f(g.get("temp"))
        if temp is None and (m := _TEMP.search(sky)):
            temp = float(m.group(1))
        total, spread = _f(g.get("total_line")), _f(g.get("spread_line"))
        for team, sign in ((g.get("home_team"), 1.0), (g.get("away_team"), -1.0)):
            out[(season, week, team)] = {
                "roofed": roofed, "wind": wind, "temp": temp,
                "precip": None if roofed else precip_of(sky),
                "implied": (total + sign * spread) / 2.0
                if total is not None and spread is not None else None}
    return out


def _outdoor_known(c: dict) -> bool:
    return c["wind"] is not None and c["temp"] is not None


def tier_wind(c: dict) -> str | None:
    if c["roofed"]:
        return "base"
    if not _outdoor_known(c) or c["precip"] or c["temp"] <= FREEZE_F:
        return None
    b = band(c["wind"])
    return "base" if b == "calm" else b


def tier_freeze(c: dict) -> str | None:
    if c["roofed"]:
        return "base"
    if not _outdoor_known(c) or c["precip"] or c["wind"] >= STILL_MPH:
        return None
    return "freeze" if c["temp"] <= FREEZE_F else "base"


def tier_rain(c: dict) -> str | None:
    if c["roofed"]:
        return "base"
    if not _outdoor_known(c) or c["wind"] >= STILL_MPH or c["temp"] <= FREEZE_F \
            or c["precip"] == "snow":
        return None
    return "rain" if c["precip"] == "rain" else "base"


def tier_snow(c: dict) -> str | None:
    if c["roofed"]:
        return "base"
    if not _outdoor_known(c) or c["wind"] >= STILL_MPH or c["precip"] == "rain":
        return None
    return "snow" if c["precip"] == "snow" else "base"


TIERS = {"wind": tier_wind, "freeze": tier_freeze, "rain": tier_rain, "snow": tier_snow}


def _n(r: dict, k: str) -> float:
    return _f(r.get(k)) or 0.0


def samples(season: int, rows, cond: dict) -> list[dict]:
    """Player-game points for one season: {season, m, g, e, y, c}."""
    from .form import compute_form
    from .models import GameLog
    games: dict = defaultdict(dict)
    for r in rows:
        if str(r.get("season_type") or "REG") not in ("REG", ""):
            continue
        pos = str(r.get("position") or "").upper()
        if pos in MARKETS:
            games[(r.get("player_display_name"), pos)][int(_n(r, "week"))] = r
    out = []
    for (_name, pos), g in games.items():
        for wk in sorted(g):
            if wk < FIRST_WEEK:
                continue
            row = g[wk]
            if pos == "QB" and _n(row, "attempts") < QB_ATTEMPTS:
                continue
            c = cond.get((season, wk, row.get("team") or row.get("recent_team")))
            if c is None:
                continue
            prev = [g[w] for w in sorted(g) if w < wk
                    and (pos != "QB" or _n(g[w], "attempts") >= QB_ATTEMPTS)]
            if len(prev) < MIN_GAMES:
                continue
            for m, cols, floor in MARKETS[pos]:
                vals = [sum(_n(p, k) for k in cols) for p in prev]
                logs = [GameLog(week=len(vals) - j, opponent="", value=v)
                        for j, v in enumerate(reversed(vals))]
                e = compute_form(logs, sum(vals) / len(vals), None).mean
                if e < floor or e <= 0:
                    continue
                out.append({"season": season, "m": m, "g": GROUP[pos], "e": e,
                            "y": sum(_n(row, k) for k in cols), "c": c})
    return out


#: A BACK'S CARRIES ARE HIS SHARE OF HIS TEAM'S (2026-11-06). Ethan, the
#: Thursday night it poured in Jacksonville, on Derrick Henry's rushing
#: under: "with that rain, I feel like it pushes more towards his over than
#: his under". Measured, 2016-2025, the way the rest of this file is, and on
#: the TEAM: its backs' carries in a team-game against the team's own
#: average over its earlier games that season. A back's share does not move
#: in rain (the lead back's share of his team's backs' carries: ×0.99 of a
#: dry day's, 2016-2026), so his carries rise and fall with his team's, and
#: the team's number is the same fact with every back's game in it once,
#: not one noisy back at a time — a single back in rain measured ×1.04 ±
#: .04 (the lead backs ×1.06 ± .04), inside the noise. The team's: ×1.069 ±
#: .030 over 140 team-games, nine of ten seasons up. Held out by season, the
#: step took 2.6% off the squared error of a lead back's carries in rain.
#: YARDS ARE NOT IN IT, on purpose: per carry they fell in rain in eight of
#: eleven seasons, and a back's rushing yards measured nothing clear (above)
#: — the extra carries do not reliably add yards. The one-cell conditions
#: only (freeze, rain, snow): the board reads wind off a forecast through
#: engine/weather.WIND_FORECAST, which would need the droplet's forecast
#: archive to measure for carries.
TEAM_MARKETS = {("rush_att", "RB"): ("carries",)}
TEAM_KEYS = tuple(sorted(TEAM_MARKETS))


def team_samples(season: int, rows, cond: dict) -> list[dict]:
    """Team-game points for one season: the backs' carries against the team's
    own average over its earlier games that season (week 4 on, three games
    before). {season, m, g, e, y, c}, measured with the player points."""
    out = []
    for (m, g), cols in TEAM_MARKETS.items():
        by: dict = defaultdict(float)
        for r in rows:
            if str(r.get("season_type") or "REG") not in ("REG", ""):
                continue
            if str(r.get("position") or "").upper() != g:
                continue
            by[(int(_n(r, "week")), r.get("team") or r.get("recent_team"))] += sum(_n(r, k) for k in cols)
        for team in sorted({t for _w, t in by if t}):
            weeks = sorted(w for w, t in by if t == team)
            for i, wk in enumerate(weeks):
                if wk < FIRST_WEEK or i < MIN_GAMES:
                    continue
                prev = [by[(w, team)] for w in weeks[:i]]
                e = math.fsum(prev) / len(prev)
                c = cond.get((season, wk, team))
                if c is None or e <= 0:
                    continue
                out.append({"season": season, "m": m, "g": g, "e": e, "y": by[(wk, team)], "c": c})
    return out


def td_samples(season: int, rows, cond: dict) -> list[dict]:
    """Team-game points for one season: passing and rushing touchdowns and
    the book's implied points."""
    tds: dict = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        if str(r.get("season_type") or "REG") not in ("REG", ""):
            continue
        k = (season, int(_n(r, "week")), r.get("team") or r.get("recent_team"))
        tds[k][0] += _n(r, "passing_tds")
        tds[k][1] += _n(r, "rushing_tds")
    out = []
    for k, (p, ru) in tds.items():
        c = cond.get(k)
        if c and c["implied"] and c["implied"] > 0:
            out.append({"season": season, "pass": p, "rush": ru, "implied": c["implied"], "c": c})
    return out


def measure_all(pts: list[dict]) -> dict:
    """{condition: qbfit.measure result} — {(market, group, tier): {mult, se, n, per}}."""
    out = {}
    for name, fn in TIERS.items():
        tagged = []
        for p in pts:
            t = fn(p["c"])
            if t is not None:
                tagged.append({**p, "tier": None if t == "base" else t})
        out[name] = measure(tagged)
    return out


def measure_td(pts: list[dict]) -> dict:
    """{condition: {(kind, tier): {mult, se, n, per}}}, kind "pass" or "rush":
    touchdowns per implied point in the condition over the same in its base."""
    out = {}
    for name, fn in TIERS.items():
        by: dict = defaultdict(list)
        for p in pts:
            t = fn(p["c"])
            if t is not None:
                by[t].append(p)
        res = {}
        base = by.get("base") or []
        for kind in ("pass", "rush"):
            def ratio(lst):
                imp = sum(x["implied"] for x in lst)
                return sum(x[kind] for x in lst) / imp if imp else 0.0
            b = ratio(base)
            if not b:
                continue
            for tier, lst in by.items():
                if tier == "base" or len(lst) < 2:
                    continue
                vals = [x[kind] / x["implied"] for x in lst]
                mu = sum(vals) / len(vals)
                se = math.sqrt(sum((v - mu) ** 2 for v in vals) / (len(vals) - 1)) / math.sqrt(len(vals)) / b
                per = {}
                for s in sorted({x["season"] for x in lst}):
                    bs = ratio([x for x in base if x["season"] == s])
                    if bs:
                        per[s] = round(ratio([x for x in lst if x["season"] == s]) / bs, 3)
                res[(kind, tier)] = {"mult": round(ratio(lst) / b, 3), "se": round(se, 3),
                                     "n": len(lst), "per": per}
        out[name] = res
    return out


def clears(v: dict) -> bool:
    """THE RULE: two standard errors from 1.0, more than half of the
    seasons that hold the condition on the same side, and at least
    ``MIN_N`` games behind it."""
    per = list(v["per"].values())
    side = [x for x in per if (x < 1.0) == (v["mult"] < 1.0) and x != 1.0]
    return (v["n"] >= MIN_N and abs(v["mult"] - 1.0) >= 2 * v["se"]
            and 2 * len(side) > len(per))


def wind_table(result: dict, keys) -> dict:
    """``{key: {band: mult}}`` for the wind bands, carried up: a band that
    does not clear takes the band below it when that one did."""
    out = {}
    for key in keys:
        row, below = {}, 1.0
        for b in BANDS:
            v = result.get((*key, b))
            got = v["mult"] if v and clears(v) else None
            below = got if got is not None else below
            if below != 1.0:
                row[b] = below
        if row:
            out[key] = row
    return out


def single(result: dict, tier: str, keys) -> dict:
    """``{key: mult}`` for a one-cell condition (freeze, rain, snow)."""
    out = {}
    for key in keys:
        v = result.get((*key, tier))
        if v and clears(v):
            out[key] = v["mult"]
    return out


PROP_KEYS = tuple(sorted({(m, GROUP[p]) for p, ms in MARKETS.items() for m, _c, _f in ms}))
TD_KEYS = (("pass",), ("rush",))


def shipped(props: dict, tds: dict) -> dict:
    """Everything the rule applies, in engine/weather.py's shape. The team's
    carries (TEAM_KEYS) in the one-cell conditions only (see TEAM_MARKETS)."""
    cell = PROP_KEYS + TEAM_KEYS
    return {
        "wind": wind_table(props["wind"], PROP_KEYS),
        "freeze": single(props["freeze"], "freeze", cell),
        "rain": single(props["rain"], "rain", cell),
        "snow": single(props["snow"], "snow", cell),
        "td_wind": {k[0]: v for k, v in wind_table(tds["wind"], TD_KEYS).items()},
        "td_freeze": {k[0]: v for k, v in single(tds["freeze"], "freeze", TD_KEYS).items()},
        "td_rain": {k[0]: v for k, v in single(tds["rain"], "rain", TD_KEYS).items()},
        "td_snow": {k[0]: v for k, v in single(tds["snow"], "snow", TD_KEYS).items()},
    }


#: THE TOTAL IN RAIN, AGAINST THE CLOSE (2026-11-06). Read off the game
#: book's kickoff sky, 2016-2026: a team in a rain game scored 1.96 points
#: under the closing line's implied team total (252 team-games), where a
#: dry outdoor team scored 0.27 over — about 2.2 points a team, 4.5 a game,
#: and below the dry games in ten of eleven seasons. But the sky at kickoff
#: is not what anyone knew when they bet: the close may have priced the
#: rain that was forecast, and missed only the rain that was not. So the
#: question the board needs is asked of the FORECAST: games forecast wet at
#: the kickoff hour (Open-Meteo's own archive of its past forecasts, the
#: same family the board reads, kept from 2022) against the closing total.
#: `totals_by_forecast` is that table; wxfit.py --totals fetches and prints
#: it on the droplet. Nothing prices it until it says so.
TOTAL_BUCKETS = ((0.6, "60%+"), (0.3, "30-60%"), (0.0, "under 30%"))


def total_bucket(chance: float) -> str:
    return next(name for lo, name in TOTAL_BUCKETS if float(chance or 0.0) >= lo)


def totals_by_forecast(rows) -> dict:
    """``rows``: [{season, chance, actual, close}] for outdoor games, the
    forecast's chance of rain at kickoff and the game's points against its
    closing total. Returns {bucket: {n, mean, se, per: {season: mean}}} and
    "verdict": whether games forecast 60%+ wet went under the close by more
    than the dry ones, by two standard errors of the difference, with more
    than half of the seasons the same way."""
    by: dict = defaultdict(list)
    for r in rows:
        by[total_bucket(r["chance"])].append(r)
    out: dict = {}
    for name, lst in by.items():
        d = [r["actual"] - r["close"] for r in lst]
        mu = math.fsum(d) / len(d)
        se = (math.sqrt(math.fsum((x - mu) ** 2 for x in d) / (len(d) - 1)) / math.sqrt(len(d))
              if len(d) > 1 else 0.0)
        per = {}
        for s in sorted({r["season"] for r in lst}):
            ds = [r["actual"] - r["close"] for r in lst if r["season"] == s]
            per[s] = round(math.fsum(ds) / len(ds), 2)
        out[name] = {"n": len(lst), "mean": round(mu, 2), "se": round(se, 2), "per": per}
    wet, dry = out.get("60%+"), out.get("under 30%")
    verdict = "too few games forecast wet to say"
    if wet and dry and wet["n"] >= MIN_N:
        gap = wet["mean"] - dry["mean"]
        se = math.sqrt(wet["se"] ** 2 + dry["se"] ** 2)
        seasons = [s for s in wet["per"] if s in dry["per"]]
        under = sum(1 for s in seasons if wet["per"][s] < dry["per"][s])
        if gap <= -2 * se and 2 * under > len(seasons):
            verdict = (f"UNDER-PRICED: games forecast 60%+ wet went {abs(gap):.1f} points further under "
                       f"the close than dry ones (± {se:.1f}; {under} of {len(seasons)} seasons) — "
                       f"worth a rain step on the board's totals")
        else:
            verdict = (f"priced: games forecast wet went {gap:+.1f} points against the dry ones "
                       f"(± {se:.1f}; {under} of {len(seasons)} seasons under) — the close already "
                       f"knows the forecast, nothing to add")
    out["verdict"] = verdict
    return out


# --- COLLEGE, ASKED OF ITS OWN GAMES (2026-11-06) -----------------------------
# Ethan, 6 November: "dive into the weather factor for NFL and college
# football games". College reads the NFL's table (engine/weather.RAIN). This
# asks college's own games the NFL's question, the same way: each team's
# carries against its own earlier games that season, in rain over the same in
# the base games (domes, or dry, still and above freezing), by `team_samples`,
# `measure_all` and the house rule (`clears`). The carries are the box's own
# college logs (the mirror's play-by-play, engine/sources/cfbstats); the
# weather is Open-Meteo's archive (ERA5: free, no key) at the venue CFBD
# places (engine/cfb/wx.venue_index), over the kickoff hour and the two after.

#: The seasons asked: the mirror's kickoff times and the box's college logs
#: both cover them.
COLLEGE_SEASONS = (2022, 2023, 2024, 2025)
#: Millimetres over the game's first WINDOW_H hours that make it wet: a
#: steady light rain, not a passing sprinkle the reanalysis smears.
RAIN_MM = 1.0
WINDOW_H = 3


def college_games(rows, season: int, id_to_abbr: dict | None, venues: dict) -> list[dict]:
    """``[{game_id, season, kickoff, home, away, lat, lon, roofed}]``: the
    mirror's completed regular-season FBS-vs-FBS games with a known kickoff
    hour at a venue CFBD places. ``game_id`` is the mirror's own number and
    the teams are keyed as the box keys them (engine/sources/cfbfastr), which
    is how the box's college logs store them (engine/sources/cfbstats)."""
    from .sources.cfbdata import name_key
    from .sources.cfbfastr import _blank, _flag, team_key
    out = []
    for r in rows or []:
        if str(r.get("season_type") or "regular").strip().lower() != "regular":
            continue
        if not _flag(r.get("completed")) or _flag(r.get("start_time_tbd")):
            continue
        if any(str(r.get(f"{s}_division") or "").strip().lower() != "fbs" for s in ("home", "away")):
            continue
        v = venues.get(name_key(str(r.get("venue") or "")))
        gid, ko = str(r.get("game_id") or "").strip(), str(r.get("start_date") or "").strip()
        if not v or _blank(gid) or len(ko) < 13:
            continue
        home = team_key(r.get("home_id"), id_to_abbr) or team_key(r.get("home_id"), None)
        away = team_key(r.get("away_id"), id_to_abbr) or team_key(r.get("away_id"), None)
        if not home or not away or home == away:
            continue
        out.append({"game_id": gid, "season": int(season), "kickoff": ko, "home": home,
                    "away": away, "lat": float(v["lat"]), "lon": float(v["lon"]),
                    "roofed": bool(v.get("dome"))})
    return out


def game_weather(payload: dict, kickoff: str) -> dict | None:
    """``{temp, wind, precip}`` at kickoff from an Open-Meteo archive payload
    (hours in UTC): ``precip`` is "rain", or "snow" when it fell as snow or
    below freezing, once RAIN_MM fell over WINDOW_H hours from the kickoff
    hour; else None. None when no reading sits within two hours of kickoff."""
    from .cfb.wx import nearest_hour
    i = nearest_hour(payload, kickoff)
    if i is None:
        return None
    hourly = (payload or {}).get("hourly") or {}

    def col(key, j):
        vals = hourly.get(key) or []
        return vals[j] if j < len(vals) else None
    temp, wind = col("temperature_2m", i), col("wind_speed_10m", i)
    if temp is None or wind is None:
        return None
    wet = math.fsum(float(col("precipitation", j) or 0.0) for j in range(i, i + WINDOW_H))
    snowed = math.fsum(float(col("snowfall", j) or 0.0) for j in range(i, i + WINDOW_H))
    precip = None
    if wet >= RAIN_MM:
        precip = "snow" if snowed > 0 or float(temp) <= FREEZE_F else "rain"
    return {"temp": float(temp), "wind": float(wind), "precip": precip}


def college_conditions(games: list[dict], weather: dict) -> tuple[dict, dict]:
    """``(cond, number)``. ``cond`` is ``{(season, n, team): {roofed, wind,
    temp, precip, implied}}`` the tiers read, ``n`` the team's game number
    that season by kickoff; ``number`` is ``{(season, game_id, team): n}``.
    ``weather`` is ``{(season, game_id): game_weather}``; an outdoor game
    with no reading has no condition (it is in no tier)."""
    by: dict = defaultdict(list)
    for g in games:
        for team in (g["home"], g["away"]):
            by[(g["season"], team)].append(g)
    cond, number = {}, {}
    for (season, team), gs in by.items():
        for n, g in enumerate(sorted(gs, key=lambda x: x["kickoff"]), start=1):
            number[(season, g["game_id"], team)] = n
            if g["roofed"]:
                cond[(season, n, team)] = {"roofed": True, "wind": None, "temp": None,
                                           "precip": None, "implied": None}
                continue
            w = weather.get((season, g["game_id"]))
            if w:
                cond[(season, n, team)] = {"roofed": False, "wind": w["wind"], "temp": w["temp"],
                                           "precip": w["precip"], "implied": None}
    return cond, number


def college_rows(carries: dict, number: dict) -> dict:
    """``{season: rows}`` for `team_samples`, one row per team-game: its
    carries under position RB (the one group `TEAM_MARKETS` reads), in the
    game-number order of `college_conditions`. ``carries`` is ``{(season,
    game_id, team): n}``; a team-game outside ``number`` (an FCS opponent, a
    venue CFBD does not place) is left out."""
    out: dict = defaultdict(list)
    for (season, gid, team), n in carries.items():
        k = number.get((season, str(gid), team))
        if k is not None:
            out[season].append({"season_type": "REG", "position": "RB", "week": k,
                                "team": team, "carries": float(n)})
    return dict(out)


def college_measure(games: list[dict], weather: dict, carries: dict) -> dict:
    """``{tier: {mult, se, n, per} or None}`` for rain, snow, wind (each band)
    and freeze: a college team's carries, measured as the NFL's are."""
    cond, number = college_conditions(games, weather)
    rows = college_rows(carries, number)
    pts = []
    for season in sorted(rows):
        pts += team_samples(season, rows[season], cond)
    got = measure_all(pts)
    out = {}
    for name, res in got.items():
        for (m, g, tier), v in (res or {}).items():
            if (m, g) == ("rush_att", "RB") and tier:
                out[tier] = v
    return out


#: The forecast ranges engine/weather.WIND_FORECAST is kept in, low edges.
FORECAST_RANGES = ((13.0, "13+"), (10.0, "10-13"), (7.0, "7-10"), (4.0, "4-7"), (0.0, "0-4"))


def forecast_range(mph: float) -> str:
    return next(name for lo, name in FORECAST_RANGES if float(mph or 0.0) >= lo)


def effect_by_forecast(pairs, table: dict, board=None) -> list[dict]:
    """What a forecast in each range is worth, against what the board gives it.

    ``table`` is {key: band multipliers} (engine/weather.WIND, the touchdown
    row beside it). For every (reported, forecast) pair the multiplier the
    MEASUREMENT gives the reported wind; per forecast range and key, its
    mean — the cut a forecast in that range has been worth — beside
    ``board(key, forecast)``, what the board applies (default: the band of
    the forecast itself).
    """
    board = board or (lambda key, f: table[key].get(band(f), 1.0))
    by: dict = {}
    for a, b in pairs:
        by.setdefault(forecast_range(b), []).append((a, b))
    rows = []
    for _lo, name in reversed(FORECAST_RANGES):
        cell = by.get(name)
        if not cell:
            continue
        row = {"forecast": name, "n": len(cell), "markets": {}}
        for key, bands in table.items():
            truth = sum(bands.get(band(a), 1.0) for a, _b in cell) / len(cell)
            given = sum(board(key, b) for _a, b in cell) / len(cell)
            row["markets"][key] = (round(truth, 3), round(given, 3))
        rows.append(row)
    return rows


#: The board's forecast table is behind when any range's cut is off by more.
FORECAST_TOLERANCE = 0.01


def scale(pairs) -> dict:
    """Does the forecast read wind on the scale the bands were measured on?

    ``pairs`` is ``[(reported mph, forecast mph)]`` for played outdoor
    games: the game book's kickoff wind (what the bands were measured on)
    and Open-Meteo's forecast for the kickoff hour (what the board reads,
    engine/nflwx.py). Returns the median forecast/reported ratio, the mean
    gap, and the share of games both put in the same band.
    """
    pairs = [(float(a), float(b)) for a, b in pairs if a is not None and b is not None]
    if not pairs:
        return {"n": 0}
    ratios = sorted(b / a for a, b in pairs if a > 0)
    mid = ratios[len(ratios) // 2] if ratios else None
    out = {"n": len(pairs),
           "median_ratio": round(mid, 3) if mid is not None else None,
           "mean_gap": round(sum(b - a for a, b in pairs) / len(pairs), 2),
           "same_band": round(sum(1 for a, b in pairs if band(a) == band(b)) / len(pairs), 3)}
    # By forecast range: the median reported wind behind each, and how
    # often the converted forecast lands in the reported wind's band — so a
    # ratio that holds at 6 mph and not at 14 shows, rather than averaging
    # away.
    if mid:
        rows = []
        for lo, hi in ((0, 4), (4, 7), (7, 10), (10, 13), (13, 99)):
            cell = [(a, b) for a, b in pairs if lo <= b < hi]
            if cell:
                rep = sorted(a for a, _b in cell)
                rows.append({"forecast": f"{lo}-{hi if hi < 99 else ''}", "n": len(cell),
                             "reported_median": rep[len(rep) // 2],
                             "same_band_converted": round(sum(1 for a, b in cell
                                                              if band(a) == band(b / mid)) / len(cell), 2)})
        out["by_forecast"] = rows
        out["same_band_converted"] = round(sum(1 for a, b in pairs if band(a) == band(b / mid)) / len(pairs), 3)
    return out
