"""Next Gen Stats — the league's own tracking numbers, weekly, free.

Ethan, 2026-09-28, asked what the site was missing. nflverse publishes the
NFL's Next Gen Stats every week and the site never read them: a receiver's
separation and cushion at the throw, a back's rushing yards over what the
blocking expected, a passer's completion rate above expectation and his
time to throw. Three files, every season since 2016, one row per player
per week (week 0 is the season line):

    nextgen_stats/ngs_receiving.csv.gz   avg_separation, avg_cushion, avg_intended_air_yards,
                                         percent_share_of_intended_air_yards, avg_yac_above_expectation
    nextgen_stats/ngs_rushing.csv.gz     rush_yards_over_expected_per_att, efficiency,
                                         percent_attempts_gte_eight_defenders, avg_time_to_los
    nextgen_stats/ngs_passing.csv.gz     completion_percentage_above_expectation, avg_time_to_throw,
                                         aggressiveness, avg_intended_air_yards

A player appears in a week only past the league's own minimums (a receiver
needs a handful of targets), so a thin week is absent, never zero.

SIGNALS ONLY, on the repo's rule: an input earns a place through the
information test first (ngsfit.py — walk-forward, held out) and reaches a
projection only where it clears. Until then nothing here moves a number.
"""

from __future__ import annotations

from collections import defaultdict

from .fetch import fetch_csv, DataUnavailable                 # noqa: F401

BASE = "https://github.com/nflverse/nflverse-data/releases/download/nextgen_stats"
KINDS = ("receiving", "rushing", "passing")
#: The columns worth a look, per file — the tracking numbers, not the box score.
METRICS = {
    "receiving": ("avg_separation", "avg_cushion", "avg_intended_air_yards",
                  "percent_share_of_intended_air_yards", "avg_yac_above_expectation"),
    "rushing": ("rush_yards_over_expected_per_att", "efficiency",
                "percent_attempts_gte_eight_defenders", "avg_time_to_los"),
    "passing": ("completion_percentage_above_expectation", "avg_time_to_throw",
                "aggressiveness", "avg_intended_air_yards"),
}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch(kind: str, ttl: int = 6 * 3600) -> list[dict]:
    """Every season's weekly rows for one file (regular season, week 1+)."""
    if kind not in KINDS:
        raise ValueError(f"unknown NGS file {kind!r}")
    rows = fetch_csv(f"{BASE}/ngs_{kind}.csv.gz", f"ngs_{kind}.csv", ttl=ttl)
    return [r for r in rows if str(r.get("season_type") or "REG") == "REG" and _f(r.get("week")) and _f(r["week"]) > 0]


def by_player(rows: list[dict], kind: str) -> dict:
    """{name: [(season, week, {metric: value}), …]} oldest first, the
    metrics of that file only, a week kept when at least one is present."""
    out: dict = defaultdict(list)
    for r in rows:
        vals = {m: _f(r.get(m)) for m in METRICS[kind]}
        vals = {m: v for m, v in vals.items() if v is not None}
        if not vals:
            continue
        out[str(r.get("player_display_name") or "")].append((int(_f(r["season"])), int(_f(r["week"])), vals))
    for name in out:
        out[name].sort()
    return out


def prior(history: list, season: int, week: int, metric: str, n: int = 6) -> float | None:
    """The average of a player's last ``n`` charted weeks BEFORE (season,
    week), across the season boundary; None with fewer than 3."""
    vals = [v[metric] for s, w, v in history if (s, w) < (season, week) and metric in v]
    vals = vals[-n:]
    return sum(vals) / len(vals) if len(vals) >= 3 else None
