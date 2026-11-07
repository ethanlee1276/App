"""
NFL prop-betting analytics engine.

This package turns raw NFL data (player game logs, defensive profiles,
weather, injuries and sportsbook lines) into ranked prop recommendations
with a projection, hit probability, edge over the book, a confidence score
and a plain-English explanation.

The pipeline is deliberately split into small, testable stages so that each
real data source (nflverse stats, a weather API, an injury feed, an odds
feed) can be swapped in behind a stable interface without touching the math.
"""

from .pipeline import run_slate

__all__ = ["run_slate"]
