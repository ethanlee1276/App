"""Ballpark engine.

Each stadium gets a profile of scoring factors; ``evaluate_park`` turns the
profile into per-market multipliers plus reasons. Factors here are directional
approximations of published multi-year park factors — like the NFL weather
coefficients, they're centralised so the ML phase can replace them with values
fit on the historical database.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import ParkProfile, TOTAL_BASES, HITS, HOME_RUNS, STRIKEOUTS

# A starter set of well-known parks (extend toward all 30 with the live layer).
PARKS: dict[str, ParkProfile] = {
    "wrigley": ParkProfile("wrigley", "Wrigley Field", "CHC",
                           hr_factor=1.04, run_factor=1.02, k_factor=1.00),
    "coors": ParkProfile("coors", "Coors Field", "COL",
                         hr_factor=1.22, run_factor=1.28, k_factor=0.92,
                         altitude_ft=5280),
    "loandepot": ParkProfile("loandepot", "loanDepot park", "MIA",
                             hr_factor=0.88, run_factor=0.92, k_factor=1.05,
                             roof="retractable"),
    "yankee": ParkProfile("yankee", "Yankee Stadium", "NYY",
                          hr_factor=1.10, run_factor=1.04, k_factor=1.00),
    "fenway": ParkProfile("fenway", "Fenway Park", "BOS",
                          hr_factor=0.96, run_factor=1.08, k_factor=0.97),
    "oracle": ParkProfile("oracle", "Oracle Park", "SF",
                          hr_factor=0.85, run_factor=0.94, k_factor=1.02),
    "petco": ParkProfile("petco", "Petco Park", "SD",
                         hr_factor=0.92, run_factor=0.93, k_factor=1.04),
    "gabp": ParkProfile("gabp", "Great American Ball Park", "CIN",
                        hr_factor=1.18, run_factor=1.06, k_factor=1.01),
    "tropicana": ParkProfile("tropicana", "Tropicana Field", "TBR",
                             hr_factor=0.94, run_factor=0.95, k_factor=1.03,
                             roof="dome", surface="turf"),
    "chase": ParkProfile("chase", "Chase Field", "ARI",
                         hr_factor=1.06, run_factor=1.05, k_factor=0.99,
                         roof="retractable"),
}

GENERIC_PARK = ParkProfile("generic", "Generic Park", "")


def get_park(key: str) -> ParkProfile:
    return PARKS.get(key, GENERIC_PARK)


@dataclass
class ParkEffect:
    multipliers: dict[str, float]
    reasons: list[str] = field(default_factory=list)


def evaluate_park(park: ParkProfile) -> ParkEffect:
    mult = {TOTAL_BASES: 1.0, HITS: 1.0, HOME_RUNS: 1.0, STRIKEOUTS: 1.0}
    reasons: list[str] = []

    # HR factor hits home-run props hardest and total bases partially.
    if abs(park.hr_factor - 1.0) >= 0.05:
        mult[HOME_RUNS] *= park.hr_factor
        mult[TOTAL_BASES] *= 1.0 + (park.hr_factor - 1.0) * 0.45
        verb = "boosts" if park.hr_factor > 1 else "suppresses"
        reasons.append(f"{park.name} {verb} home runs "
                       f"({(park.hr_factor - 1) * 100:+.0f}% vs average)")

    # Run factor lifts hits/TB generally.
    if abs(park.run_factor - 1.0) >= 0.04:
        mult[HITS] *= 1.0 + (park.run_factor - 1.0) * 0.6
        mult[TOTAL_BASES] *= 1.0 + (park.run_factor - 1.0) * 0.5
        if park.run_factor > 1:
            reasons.append(f"{park.name} plays hitter-friendly "
                           f"({(park.run_factor - 1) * 100:+.0f}% runs)")
        else:
            reasons.append(f"{park.name} plays pitcher-friendly "
                           f"({(park.run_factor - 1) * 100:+.0f}% runs)")

    # K factor moves pitcher strikeout props (and nudges hitter contact).
    if abs(park.k_factor - 1.0) >= 0.03:
        mult[STRIKEOUTS] *= park.k_factor
        if park.k_factor > 1:
            reasons.append(f"{park.name} elevates strikeouts "
                           f"({(park.k_factor - 1) * 100:+.0f}%)")

    # Altitude: thin air adds carry beyond the baked-in factors' description.
    if park.altitude_ft >= 3000:
        reasons.append(f"Altitude {park.altitude_ft:,} ft — thin air adds carry")

    return ParkEffect(mult, reasons)
