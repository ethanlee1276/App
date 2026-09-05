"""Weather engine.

Turns a game's weather into per-market multipliers plus a set of human-readable
reasons. The effect sizes below are directional approximations drawn from
public NFL weather studies; they are centralised here so they can be replaced
with coefficients learned from the historical database in the ML phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Weather, PASS_YDS, RUSH_YDS, REC_YDS, RECEPTIONS


@dataclass
class WeatherEffect:
    multipliers: dict[str, float]
    reasons: list[str] = field(default_factory=list)
    # §7: at 25+ mph the spec says avoid deep-passing markets ENTIRELY —
    # rules.py turns this into a hard block, not just a haircut.
    avoid_deep: bool = False


def evaluate_weather(w: Weather) -> WeatherEffect:
    """Wind in BANDS, not one cutoff (docs/NFL_MODEL.md §7): wind's effect on
    passing scales, so a single '15 mph = bad' rule both overreacts and
    underreacts. Receptions take roughly half a yardage market's hit — short
    throws still complete in wind; deep balls don't."""
    mult = {PASS_YDS: 1.0, RUSH_YDS: 1.0, REC_YDS: 1.0, RECEPTIONS: 1.0}
    reasons: list[str] = []
    avoid_deep = False

    if w.dome:
        reasons.append("Dome game — no weather impact on the passing game")
        return WeatherEffect(mult, reasons)

    wind = w.wind_mph or 0.0
    if wind >= 25:
        mult[PASS_YDS] *= 0.82
        mult[REC_YDS] *= 0.80
        mult[RECEPTIONS] *= 0.92
        mult[RUSH_YDS] *= 1.08
        avoid_deep = True
        reasons.append(f"Wind {wind:.0f} mph — deep-passing markets are "
                       f"avoided entirely at 25+ (hard rule, not a haircut)")
    elif wind >= 18:
        mult[PASS_YDS] *= 0.90
        mult[REC_YDS] *= 0.89
        mult[RECEPTIONS] *= 0.95
        mult[RUSH_YDS] *= 1.06
        reasons.append(f"Wind {wind:.0f} mph — major passing downgrade; "
                       f"totals and pass props shaded hard, rushing volume up")
    elif wind >= 12:
        mult[PASS_YDS] *= 0.95
        mult[REC_YDS] *= 0.95
        mult[RECEPTIONS] *= 0.985
        mult[RUSH_YDS] *= 1.03
        reasons.append(f"Wind {wind:.0f} mph — real passing downgrade; "
                       f"pass yardage and deep-target props shaded down")
    elif wind >= 8:
        mult[PASS_YDS] *= 0.985
        mult[REC_YDS] *= 0.985
        reasons.append(f"Wind {wind:.0f} mph — minor; slight deep-ball haircut")

    # Precipitation nudges teams toward the run and lowers catch rates.
    if w.snow:
        mult[PASS_YDS] *= 0.93
        mult[REC_YDS] *= 0.93
        mult[RUSH_YDS] *= 1.08
        reasons.append("Snow increases rushing rate and lowers passing efficiency")
    elif w.rain or w.precip_chance >= 0.6:
        mult[PASS_YDS] *= 0.96
        mult[REC_YDS] *= 0.96
        mult[RUSH_YDS] *= 1.05
        reasons.append("Rain in the forecast — expect a run-leaning script")

    # Extreme cold slightly dampens the passing game.
    if w.temp_f <= 20:
        mult[PASS_YDS] *= 0.97
        mult[REC_YDS] *= 0.97
        reasons.append(f"Cold ({w.temp_f:.0f}°F) trims passing efficiency — "
                       f"grip, kicking distance, catch rates")

    return WeatherEffect(mult, reasons, avoid_deep=avoid_deep)
