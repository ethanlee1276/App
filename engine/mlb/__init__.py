"""MLB prop-betting analytics engine.

Mirrors the NFL engine's architecture — recent-form blending, matchup /
weather / park adjustments, a probabilistic betting model, discipline rules
and plain-English explanations — but curated for baseball:

  * **Ballpark engine** — per-park HR / run / strikeout factors, altitude
    (Coors), and roof state.
  * **Weather engine** — wind blowing in/out relative to the park, temperature
    and humidity effects on carry, and postponement risk.
  * **Matchup analyzer** — platoon splits (batter vs pitcher handedness), the
    opposing starter's quality against that side, opposing bullpen strength,
    and team strikeout rates for pitcher props.
  * **Lineup engine** — batting-order slot drives plate-appearance volume, and
    props on players not in a confirmed lineup are held.
  * **Betting model** — normal model for total bases / hits / strikeouts,
    Poisson for home runs, then the shared de-vig / edge / confidence /
    fractional-Kelly stack.

The pipeline emits the exact same JSON shape as the NFL engine so the web
dashboard renders both sports with the same components.
"""

from .pipeline import run_mlb_slate

__all__ = ["run_mlb_slate"]
