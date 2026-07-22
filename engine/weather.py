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


def evaluate_weather(w: Weather) -> WeatherEffect:
    mult = {PASS_YDS: 1.0, RUSH_YDS: 1.0, REC_YDS: 1.0, RECEPTIONS: 1.0}
    reasons: list[str] = []

    if w.dome:
        reasons.append("Dome game — no weather impact on the passing game")
        return WeatherEffect(mult, reasons)

    # Wind is the single biggest passing suppressor.
    if w.wind_mph >= 20:
        factor = 1.0 - min(0.18, (w.wind_mph - 20) * 0.01 + 0.08)
        mult[PASS_YDS] *= factor
        mult[REC_YDS] *= factor
        mult[RECEPTIONS] *= (1.0 - (1.0 - factor) * 0.5)
        mult[RUSH_YDS] *= 1.05
        reasons.append(
            f"Wind {w.wind_mph:.0f} mph cuts deep passing (~{(1 - factor) * 100:.0f}% "
            f"projection haircut); rushing volume rises"
        )
    elif w.wind_mph >= 15:
        mult[PASS_YDS] *= 0.96
        mult[REC_YDS] *= 0.96
        mult[RUSH_YDS] *= 1.02
        reasons.append(f"Breezy at {w.wind_mph:.0f} mph — mild passing drag")

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
        reasons.append(f"Cold ({w.temp_f:.0f}°F) trims passing efficiency")

    return WeatherEffect(mult, reasons)
