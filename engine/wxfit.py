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
    """Everything the rule applies, in engine/weather.py's shape."""
    return {
        "wind": wind_table(props["wind"], PROP_KEYS),
        "freeze": single(props["freeze"], "freeze", PROP_KEYS),
        "rain": single(props["rain"], "rain", PROP_KEYS),
        "snow": single(props["snow"], "snow", PROP_KEYS),
        "td_wind": {k[0]: v for k, v in wind_table(tds["wind"], TD_KEYS).items()},
        "td_freeze": {k[0]: v for k, v in single(tds["freeze"], "freeze", TD_KEYS).items()},
        "td_rain": {k[0]: v for k, v in single(tds["rain"], "rain", TD_KEYS).items()},
        "td_snow": {k[0]: v for k, v in single(tds["snow"], "snow", TD_KEYS).items()},
    }


def effect_by_forecast(pairs, table: dict, scale: float = 1.0) -> list[dict]:
    """What a forecast in each range is worth, against what the board gives it.

    ``table`` is engine/weather.WIND. For every (reported, forecast) pair
    the multiplier the MEASUREMENT says (the band of the reported wind) and
    the one the BOARD applies (the band of the forecast ÷ ``scale``); per
    forecast range and market, their means. The board is right where the
    two agree — whatever the scale of the two winds.
    """
    rows = []
    for lo, hi in ((0, 4), (4, 7), (7, 10), (10, 13), (13, 99)):
        cell = [(a, b) for a, b in pairs if lo <= b < hi]
        if not cell:
            continue
        row = {"forecast": f"{lo}-{hi if hi < 99 else ''}", "n": len(cell), "markets": {}}
        for key, bands in table.items():
            truth = sum(bands.get(band(a), 1.0) for a, _b in cell) / len(cell)
            board = sum(bands.get(band(b / scale), 1.0) for _a, b in cell) / len(cell)
            row["markets"][key] = (round(truth, 3), round(board, 3))
        rows.append(row)
    return rows


def miss_at(pairs, table: dict, scale: float) -> float:
    """Mean squared gap between the board's multiplier (the forecast ÷
    ``scale`` banded) and the measured one (the reported wind banded),
    pair by pair, over every market in ``table``."""
    err = sum((bands.get(band(a), 1.0) - bands.get(band(b / scale), 1.0)) ** 2
              for a, b in pairs for bands in table.values())
    return round(err / max(1, len(pairs) * max(1, len(table))), 6)


#: A scale has to beat the board's by more than this to be worth a change.
SCALE_TOLERANCE = 0.00005


def best_scale(pairs, table: dict) -> tuple[float, float]:
    """(scale, miss): the single forecast ÷ scale, 0.60 to 1.40, that puts
    the board's multiplier closest to the measured one."""
    return min(((k / 100, miss_at(pairs, table, k / 100)) for k in range(60, 141, 2)),
               key=lambda t: (t[1], abs(t[0] - 1.0)))


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
