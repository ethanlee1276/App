"""MLB weather engine.

Wind direction relative to the park is the headline effect: wind blowing out
lifts home-run and total-base props, wind blowing in suppresses them. Heat
adds carry, cold kills it, humidity helps slightly (humid air is less dense).
A closed roof neutralises everything; high precipitation risk is surfaced as a
postponement warning rather than a projection change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..statmath import clamp as clampf
from .models import (MLBWeather, TOTAL_BASES, HITS, HOME_RUNS, STRIKEOUTS,
                     OUTS)


#: The neutral point and slope of the temperature ramp (script §6). The
#: slope lands the endpoints where the old steps sat in spirit: 90°F is
#: +9%, 45°F is -11%, and the April cold trap finally gets priced on
#: the 50-something nights the steps ignored.
TEMP_NEUTRAL_F = 70.0
TEMP_HR_PER_F = 0.0045


@dataclass
class WeatherEffect:
    multipliers: dict[str, float]
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def evaluate_weather(w: MLBWeather) -> WeatherEffect:
    mult = {TOTAL_BASES: 1.0, HITS: 1.0, HOME_RUNS: 1.0, STRIKEOUTS: 1.0,
            OUTS: 1.0}
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

    # Temperature: carry rises with heat, CONTINUOUSLY. This was two
    # steps (>=85 hot, <=45 cold) with a 40-degree dead zone between
    # them — a 78°F July night and a 52°F April night priced identically.
    # The handicapping script (§6): each 10°F adds ~2.5 ft of fly-ball
    # carry, ~half a run between 60°F and 90°F, "concentrated in home
    # run rate". Half a run on a ~4.25 team total via HRs is ~14% HR
    # rate over 30°F ≈ 0.45%/°F, ramped from a 70°F neutral point and
    # capped where the old steps' spirit was.
    dt = clampf(w.temp_f, 40.0, 100.0) - TEMP_NEUTRAL_F
    if abs(dt) >= 3.0:
        hr_t = 1.0 + clampf(dt * TEMP_HR_PER_F, -0.15, 0.14)
        mult[HOME_RUNS] *= hr_t
        mult[TOTAL_BASES] *= 1.0 + (hr_t - 1.0) * 0.5
        if dt > 0:
            reasons.append(f"Warm ({w.temp_f:.0f}°F) — thin air adds "
                           f"~{(hr_t - 1) * 100:.0f}% to HR carry")
        else:
            mult[STRIKEOUTS] *= 1.02 if dt <= -20 else 1.01
            reasons.append(f"Cold ({w.temp_f:.0f}°F) — dense air cuts "
                           f"carry ~{(1 - hr_t) * 100:.0f}%")

    # Humid air is less dense → slightly more carry.
    if w.humidity >= 0.70 and w.temp_f >= 70:
        mult[HOME_RUNS] *= 1.02
        reasons.append("High humidity — slightly better carry")

    if w.precip_chance >= 0.5:
        warnings.append(f"Rain risk {w.precip_chance:.0%} — "
                        f"postponement/shortened-game exposure")

    return WeatherEffect(mult, reasons, warnings)
