"""MLB weather engine.

Wind direction relative to the park is the headline effect: wind blowing out
lifts home-run and total-base props, wind blowing in suppresses them. Heat
adds carry, cold kills it, humidity helps slightly (humid air is less dense).
A closed roof neutralises everything; high precipitation risk is surfaced as a
postponement warning rather than a projection change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import MLBWeather, TOTAL_BASES, HITS, HOME_RUNS, STRIKEOUTS


@dataclass
class WeatherEffect:
    multipliers: dict[str, float]
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def evaluate_weather(w: MLBWeather) -> WeatherEffect:
    mult = {TOTAL_BASES: 1.0, HITS: 1.0, HOME_RUNS: 1.0, STRIKEOUTS: 1.0}
    reasons: list[str] = []
    warnings: list[str] = []

    if w.roof_closed:
        reasons.append("Roof closed — weather-neutral conditions")
        return WeatherEffect(mult, reasons, warnings)

    # Wind relative to the park.
    if w.wind_mph >= 10:
        if w.wind_dir_rel == "out":
            hr_boost = 1.0 + min(0.20, (w.wind_mph - 8) * 0.014)
            mult[HOME_RUNS] *= hr_boost
            mult[TOTAL_BASES] *= 1.0 + (hr_boost - 1.0) * 0.5
            reasons.append(f"Wind blowing out {w.wind_mph:.0f} mph — "
                           f"HR probability up ~{(hr_boost - 1) * 100:.0f}%")
        elif w.wind_dir_rel == "in":
            hr_cut = 1.0 - min(0.18, (w.wind_mph - 8) * 0.013)
            mult[HOME_RUNS] *= hr_cut
            mult[TOTAL_BASES] *= 1.0 + (hr_cut - 1.0) * 0.5
            mult[STRIKEOUTS] *= 1.02
            reasons.append(f"Wind blowing in {w.wind_mph:.0f} mph — "
                           f"fly balls die (~{(1 - hr_cut) * 100:.0f}% HR haircut)")

    # Temperature: carry rises with heat.
    if w.temp_f >= 85:
        mult[HOME_RUNS] *= 1.06
        mult[TOTAL_BASES] *= 1.03
        reasons.append(f"Hot ({w.temp_f:.0f}°F) — ball carries farther")
    elif w.temp_f <= 45:
        mult[HOME_RUNS] *= 0.92
        mult[TOTAL_BASES] *= 0.96
        mult[STRIKEOUTS] *= 1.02
        reasons.append(f"Cold ({w.temp_f:.0f}°F) — reduced exit velocity and carry")

    # Humid air is less dense → slightly more carry.
    if w.humidity >= 0.70 and w.temp_f >= 70:
        mult[HOME_RUNS] *= 1.02
        reasons.append("High humidity — slightly better carry")

    if w.precip_chance >= 0.5:
        warnings.append(f"Rain risk {w.precip_chance:.0%} — "
                        f"postponement/shortened-game exposure")

    return WeatherEffect(mult, reasons, warnings)
