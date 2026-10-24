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


# ---------------------------------------------------------------------------
# The two uses the first test did not cover (Ethan, 2026-09-28: "feels like
# we are missing out not using number 2"): the DEFENCE's side of the same
# numbers, and the numbers themselves shown on a read.

#: nflverse's schedule spells the Rams "LA"; Next Gen Stats spells them "LAR".
TEAM_FIX = {"LAR": "LA"}
VOLUME = {"receiving": "targets", "rushing": "rush_attempts", "passing": "attempts"}
#: Who ranks: the least of the season's volume for a place in the order.
RANK_MIN = {"receiving": 8, "rushing": 12, "passing": 25}
#: Lower is better for these two (yards run per yard gained; seconds).
LOWER_BETTER = {"efficiency", "avg_time_to_throw"}


def _team(t: str) -> str:
    return TEAM_FIX.get(str(t or ""), str(t or ""))


def _opponents(schedules) -> dict:
    """{(season, week, team): opponent} from nflverse's schedule rows."""
    out = {}
    for g in schedules or []:
        try:
            s, w = int(g.get("season") or 0), int(g.get("week") or 0)
        except (TypeError, ValueError):
            continue
        h, a = _team(g.get("home_team")), _team(g.get("away_team"))
        if s and w and h and a:
            out[(s, w, h)], out[(s, w, a)] = a, h
    return out


def defense_weeks(rows, schedules=None, metrics=("avg_separation", "avg_cushion")) -> dict:
    """{defence: [(season, week, {"targets", "<metric>_x": Σ metric × targets}), …]}
    — what each defence allowed the receivers it faced, target-weighted,
    from the receiving rows and the schedule (the rows carry no
    opponent). A pooled prior is Σx / Σtargets (engine/sources/ftn.rate_prior)."""
    if schedules is None:
        from .nflverse import load_schedules
        schedules = load_schedules()
    opp_of = _opponents(schedules)
    acc: dict = defaultdict(lambda: defaultdict(float))
    for r in rows:
        try:
            s, w = int(r.get("season") or 0), int(r.get("week") or 0)
        except (TypeError, ValueError):
            continue
        opp = opp_of.get((s, w, _team(r.get("team_abbr"))))
        tg = _f(r.get("targets"))
        if not opp or not tg:
            continue
        a = acc[(opp, s, w)]
        a["targets"] += tg
        for m in metrics:
            v = _f(r.get(m))
            if v is not None:
                a[f"{m}_x"] += v * tg
    out: dict = defaultdict(list)
    for (team, s, w), counts in sorted(acc.items(), key=lambda kv: (kv[0][1], kv[0][2])):
        out[team].append((s, w, dict(counts)))
    return dict(out)


def season_tables(season: int, before_week=None, rows_by_kind=None) -> dict:
    """The season to date per player, volume-weighted, with his place among
    the men at his position who have the volume: ``{"season", "receivers":
    {(team, name): {"avg_separation": 2.9, "avg_separation_rank": 12, …,
    "targets": 31, "n_ranked": 95}}, "rushers": …, "passers": …}``.
    Keyed by team and display name; the scan matches on its own key."""
    out = {"season": int(season), "receivers": {}, "rushers": {}, "passers": {}}
    table_of = {"receiving": "receivers", "rushing": "rushers", "passing": "passers"}
    for kind in KINDS:
        rows = (rows_by_kind or {}).get(kind) if rows_by_kind else None
        if rows is None:
            try:
                rows = fetch(kind)
            except Exception:                                # noqa: BLE001
                rows = []
        vol = VOLUME[kind]
        acc: dict = {}
        for r in rows:
            try:
                s, w = int(r.get("season") or 0), int(r.get("week") or 0)
            except (TypeError, ValueError):
                continue
            if s != int(season) or (before_week is not None and w >= int(before_week)):
                continue
            n = _f(r.get(vol)) or 0.0
            if n <= 0:
                continue
            key = (_team(r.get("team_abbr")), str(r.get("player_display_name") or ""))
            a = acc.setdefault(key, {"n": 0.0, "pos": str(r.get("player_position") or ""), "weeks": 0,
                                     **{m: 0.0 for m in METRICS[kind]}})
            a["n"] += n
            a["weeks"] += 1
            for m in METRICS[kind]:
                v = _f(r.get(m))
                if v is not None:
                    a[m] += v * n
        table = {}
        for key, a in acc.items():
            table[key] = {m: round(a[m] / a["n"], 2) for m in METRICS[kind]}
            table[key].update({vol: int(a["n"]), "weeks": a["weeks"], "pos": a["pos"]})
        ranked = [k for k, v in table.items() if v[vol] >= RANK_MIN[kind]]
        for m in METRICS[kind]:
            order = sorted(ranked, key=lambda k: table[k][m], reverse=m not in LOWER_BETTER)
            for i, k in enumerate(order, 1):
                table[k][f"{m}_rank"] = i
        for k in ranked:
            table[k]["n_ranked"] = len(ranked)
        out[table_of[kind]] = table
    return out
