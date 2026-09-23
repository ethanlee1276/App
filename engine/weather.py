"""Weather engine.

Turns a game's weather into per-market multipliers plus a set of human-readable
reasons.

MEASURED SINCE 2026-09-23 (engine/wxfit.py, `python3 wxfit.py`, ten
seasons 2016-2025 of player-games against the projection's own form base,
each condition measured where the others are absent). Before that these
were hand-set from the spec — ×0.95 passing at 12 mph, ×0.90 at 18, ×0.82
at 25, a rushing LIFT in wind, a rain and a ≤20°F haircut — and the NFL
forecast never reached them (nflverse.build_slate's ``games``). What the
games say, and what changed:

  * wind cuts passing more than the spec had it at 12-18 mph (yards
    ×0.93, receivers ×0.92, passing touchdowns ×0.84) and the receiver cut
    starts at 8 mph; backs are untouched — the rushing lift measured
    nothing (×1.00 at 12-18, 1.05 ± .06 at 18+);
  * rain is the biggest weather effect there is — receivers ×0.87 yards
    and ×0.90 catches, quarterbacks ×0.89 yards and ×0.84 touchdowns,
    backs' catches ×0.84 — and it is applied at the FORECAST'S OWN CHANCE:
    a 70% chance of rain is 70% of the measured effect, the expected
    value over the two outcomes, never the full cut on a forecast;
  * cold on its own measured nothing clear once wind, rain and snow were
    separated (receivers ×0.95 ± .04, and the seasons split) — the ≤20°F
    haircut is gone;
  * snow cuts receivers hard (×0.83 yards, ×0.81 catches); a
    quarterback's 22 snow starts are too few to say.

Receivers and tight ends are one group; a back's receiving is his own. The
wind multipliers were measured on the reported wind at kickoff, and the
board reads Open-Meteo's forecast for the kickoff hour (engine/nflwx.py),
and a forecast takes the measured cut of its own range (WIND_FORECAST).
College reads the same table: its games are too few to measure alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Weather, PASS_YDS, PASS_TD, RUSH_YDS, REC_YDS, RECEPTIONS
from .wxfit import band as wind_band, forecast_range, FREEZE_F


@dataclass
class WeatherEffect:
    multipliers: dict[str, float]
    reasons: list[str] = field(default_factory=list)
    # §7: at 25+ mph the spec says avoid deep-passing markets ENTIRELY —
    # rules.py turns this into a hard block, not just a haircut.
    avoid_deep: bool = False


#: python3 wxfit.py, 2016-2025 — what engine/wxfit's rule applies.
#: tests/test_weather_reaches_the_number.py pins these to the fit's shape.
WIND = {
    ("pass_td", "QB"): {"12-18": 0.841, "18+": 0.841},
    ("pass_yds", "QB"): {"12-18": 0.926, "18+": 0.92},
    ("rec_yds", "WRTE"): {"8-12": 0.955, "12-18": 0.92, "18+": 0.904},
    ("receptions", "WRTE"): {"12-18": 0.953, "18+": 0.953},
}
FREEZE: dict = {}
RAIN = {
    ("pass_td", "QB"): 0.836,
    ("pass_yds", "QB"): 0.887,
    ("rec_yds", "RB"): 0.791,
    ("rec_yds", "WRTE"): 0.869,
    ("receptions", "RB"): 0.841,
    ("receptions", "WRTE"): 0.897,
}
SNOW = {
    ("rec_yds", "WRTE"): 0.834,
    ("receptions", "WRTE"): 0.805,
}
#: Touchdowns PER IMPLIED POINT — on top of the book's total, which
#: already carries part of the weather (touchdowns.py starts from it).
#: "pass" is a receiver's or tight end's score, "rush" a back's or a
#: quarterback's own.
TD_WIND = {"pass": {"12-18": 0.865, "18+": 0.865}}
TD_FREEZE: dict = {}
TD_RAIN = {"pass": 0.811}
TD_SNOW: dict = {}

#: A FORECAST IS NOT A READING, and its cut is the average of what the
#: games it turned into did. The tables above were measured on the wind the
#: game book reports at kickoff; the board reads Open-Meteo's forecast for
#: the kickoff hour, and the two differ game to game (the same band 57% of
#: the time). Measured on Ethan's droplet, 2026-09-23 (`python3 wxfit.py
#: --scale`, 492 outdoor games 2023-2025, each game's archived forecast
#: beside its reported wind): for every forecast range, the mean of the
#: measured multiplier over the reported winds those forecasts became.
#: That is the cut a forecast is worth — a calm forecast still meant a
#: breezy game book one time in five, and a 13+ forecast meant 18+ less
#: often than the band table assumes. (The same night's first try divided
#: every forecast by the median wind ratio, ×0.714, a calm-day artifact
#: that cut a 10 mph forecast as a 14 mph wind; a single scale was the
#: wrong shape of answer.) The touchdown row is read off the same games:
#: the share of each range at 12+ mph (the catches and passing-TD rows,
#: flat above 12, both give it) times the measured −13.5%.
WIND_FORECAST = {
    ("pass_td", "QB"): {"0-4": 0.988, "4-7": 0.980, "7-10": 0.951, "10-13": 0.942, "13+": 0.900},
    ("pass_yds", "QB"): {"0-4": 0.994, "4-7": 0.991, "7-10": 0.977, "10-13": 0.973, "13+": 0.953},
    ("rec_yds", "WRTE"): {"0-4": 0.985, "4-7": 0.978, "7-10": 0.962, "10-13": 0.949, "13+": 0.933},
    ("receptions", "WRTE"): {"0-4": 0.996, "4-7": 0.994, "7-10": 0.985, "10-13": 0.983, "13+": 0.970},
}
TD_WIND_FORECAST = {"pass": {"0-4": 0.989, "4-7": 0.983, "7-10": 0.958, "10-13": 0.951, "13+": 0.914}}

#: Below this forecast chance it is a dry day — the measured base, dry
#: at kickoff, holds the games that were given a small chance and stayed dry.
PRECIP_FLOOR = 0.3

MARKETS = (PASS_YDS, PASS_TD, RUSH_YDS, REC_YDS, RECEPTIONS)
_LABEL = {PASS_YDS: "passing yards", PASS_TD: "passing TDs", RUSH_YDS: "rushing yards",
          REC_YDS: "receiving yards", RECEPTIONS: "catches"}
#: The markets a position's props are priced in, and the group measured for it.
_POSITION_MARKETS = {"QB": (PASS_YDS, PASS_TD, RUSH_YDS), "WR": (REC_YDS, RECEPTIONS),
                     "TE": (REC_YDS, RECEPTIONS), "RB": (RUSH_YDS, REC_YDS, RECEPTIONS)}
_GROUP = {"QB": "QB", "WR": "WRTE", "TE": "WRTE", "RB": "RB", "FB": "RB"}
_DEFAULT_GROUP = {PASS_YDS: "QB", PASS_TD: "QB", RUSH_YDS: "RB", REC_YDS: "WRTE",
                  RECEPTIONS: "WRTE"}
_WHO = {"QB": "a quarterback's", "WRTE": "a receiver's", "RB": "a back's"}


def shipped() -> dict:
    """Everything applied, in engine/wxfit.shipped's shape (wxfit.py compares)."""
    return {"wind": WIND, "freeze": FREEZE, "rain": RAIN, "snow": SNOW,
            "td_wind": TD_WIND, "td_freeze": TD_FREEZE, "td_rain": TD_RAIN, "td_snow": TD_SNOW}


def _group(market: str, position: str | None) -> str | None:
    if position:
        return _GROUP.get(str(position).upper())
    return _DEFAULT_GROUP.get(market)


def _band_txt(b: str) -> str:
    return b.replace("-", "–")


def _pct(m: float) -> str:
    return f"{(m - 1.0) * 100:+.0f}%".replace("-", "−")


def forecast_cut(key: tuple, mph: float) -> float:
    """A forecast's measured cut for ``key`` — a (market, group) of
    WIND_FORECAST, or ("anytime_td", "pass") — at ``mph``."""
    r = forecast_range(mph)
    if key == ("anytime_td", "pass"):
        return TD_WIND_FORECAST["pass"].get(r, 1.0)
    return WIND_FORECAST.get(key, {}).get(r, 1.0)


def _pct1(m: float) -> str:
    return f"{(m - 1.0) * 100:+.1f}%".replace("-", "−")


def precip(w: Weather) -> tuple[str | None, float]:
    """(kind, chance): "rain" or "snow" and the forecast's chance of it at
    kickoff, or (None, 0.0) for a dry day. A flag without a chance (a
    source that only says "rain") is taken as certain."""
    p = float(getattr(w, "precip_chance", 0.0) or 0.0)
    if p <= 0.0 and (w.rain or w.snow):
        p = 1.0
    if p < PRECIP_FLOOR:
        return None, 0.0
    kind = "snow" if (w.snow or (w.temp_f is not None and w.temp_f <= FREEZE_F)) else "rain"
    return kind, min(1.0, p)


def at_chance(m: float, p: float) -> float:
    """The expected multiplier at a forecast chance ``p`` of the condition."""
    return 1.0 - p * (1.0 - m)


def _markets_for(position: str | None) -> tuple:
    return _POSITION_MARKETS.get(str(position or "").upper(), MARKETS) if position else MARKETS


def evaluate_weather(w: Weather, position: str | None = None) -> WeatherEffect:
    """Per-market multipliers for a player at ``position`` (every market,
    each at its usual position's measurement, when None — the game-level
    read engine/pipeline._conditions makes)."""
    mult = {m: 1.0 for m in MARKETS}
    reasons: list[str] = []

    if w.dome:
        reasons.append("Dome game — no weather impact on the passing game")
        return WeatherEffect(mult, reasons)
    if not getattr(w, "measured", False):
        # The 60°F / 6 mph prior is a number to do arithmetic on, not a
        # reading: it moves nothing and the card says so.
        reasons.append("Outdoors, no forecast pulled for this game — weather is left "
                       "out of the number")
        return WeatherEffect(mult, reasons)

    markets = _markets_for(position)
    wind = float(w.wind_mph or 0.0)
    if getattr(w, "forecast", False):
        r = forecast_range(wind)
        hit = []
        for m in markets:
            f = WIND_FORECAST.get((m, _group(m, position)), {}).get(r)
            if f and f < 1.0:
                mult[m] *= f
                hit.append(f"{_LABEL[m]} {_pct1(f)}")
        if hit:
            reasons.append(f"Wind {wind:.0f} mph forecast — games forecast at "
                           f"{_band_txt(r)} mph averaged {', '.join(hit)} (measured: the "
                           f"2016-2025 effects over the winds those forecasts turned into)")
    else:
        b = wind_band(wind)
        if b != "calm":
            hit = []
            for m in markets:
                f = WIND.get((m, _group(m, position)), {}).get(b)
                if f:
                    mult[m] *= f
                    hit.append(f"{_LABEL[m]} {_pct(f)}")
            who = _WHO.get(_GROUP.get(str(position or "").upper(), ""), "")
            if hit:
                reasons.append(f"Wind {wind:.0f} mph — measured in {_band_txt(b)} mph games "
                               f"(2016-2025): {', '.join(hit)}")
            else:
                reasons.append(f"Wind {wind:.0f} mph — no clear effect measured on "
                               f"{who or 'these'} markets at {_band_txt(b)} mph; left alone")
    avoid_deep = wind >= 25
    if avoid_deep:
        reasons.append(f"Wind {wind:.0f} mph — deep-passing markets are "
                       f"avoided entirely at 25+ (hard rule, not a haircut)")

    kind, p = precip(w)
    if kind:
        table = RAIN if kind == "rain" else SNOW
        hit, now = [], []
        for m in markets:
            f = table.get((m, _group(m, position)))
            if f:
                mult[m] *= at_chance(f, p)
                hit.append(f"{_LABEL[m]} {_pct(f)}")
                now.append(_pct(at_chance(f, p)))
        if hit:
            reasons.append(f"{kind.capitalize()} {p:.0%} likely at kickoff — measured in "
                           f"{kind} (2016-2025): {', '.join(hit)}; at a {p:.0%} chance "
                           f"that is {' and '.join(now) if len(now) < 3 else ', '.join(now)}")
        else:
            reasons.append(f"{kind.capitalize()} {p:.0%} likely at kickoff — no clear "
                           f"effect measured on these markets in {kind}; left alone")
    elif w.temp_f is not None and w.temp_f <= FREEZE_F:
        hit = []
        for m in markets:
            f = FREEZE.get((m, _group(m, position)))
            if f:
                mult[m] *= f
                hit.append(f"{_LABEL[m]} {_pct(f)}")
        reasons.append(f"{w.temp_f:.0f}°F — " + (
            f"measured below freezing: {', '.join(hit)}" if hit else
            "cold on its own measured no clear effect once wind, rain and snow "
            "are separated; left alone"))

    return WeatherEffect(mult, reasons, avoid_deep=avoid_deep)


def td_multiplier(w: Weather | None, position: str) -> tuple[float, list[str]]:
    """The weather's multiplier on an anytime-touchdown RATE that starts from
    the book's implied team total (touchdowns.py, engine/cfb/tds.py)."""
    if w is None or w.dome:
        return 1.0, ["Indoors — weather is not a factor"]
    if not getattr(w, "measured", False):
        return 1.0, ["Outdoors, no forecast pulled — weather left out"]
    kind = "pass" if str(position or "").upper() in ("WR", "TE") else "rush"
    what = "receiving touchdowns" if kind == "pass" else "rushing touchdowns"
    mult, reasons = 1.0, []
    wind = float(w.wind_mph or 0.0)
    if getattr(w, "forecast", False):
        r = forecast_range(wind)
        f = TD_WIND_FORECAST.get(kind, {}).get(r)
        if f and f < 1.0:
            mult *= f
            reasons.append(f"Wind {wind:.0f} mph forecast — {what} {_pct1(f)} beyond what the "
                           f"total already prices (measured, games forecast at {_band_txt(r)} mph)")
    else:
        b = wind_band(wind)
        if b != "calm":
            f = TD_WIND.get(kind, {}).get(b)
            if f:
                mult *= f
                reasons.append(f"Wind {wind:.0f} mph — {what} {_pct(f)} beyond what the "
                               f"total already prices (measured, {_band_txt(b)} mph)")
    p_kind, p = precip(w)
    if p_kind:
        f = (TD_RAIN if p_kind == "rain" else TD_SNOW).get(kind)
        if f:
            mult *= at_chance(f, p)
            reasons.append(f"{p_kind.capitalize()} {p:.0%} likely — {what} {_pct(f)} in "
                           f"{p_kind} beyond the total (measured), at the forecast's chance")
    elif w.temp_f is not None and w.temp_f <= FREEZE_F:
        f = TD_FREEZE.get(kind)
        if f:
            mult *= f
            reasons.append(f"{w.temp_f:.0f}°F — {what} {_pct(f)} below freezing (measured)")
    return mult, reasons
