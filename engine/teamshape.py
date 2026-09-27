"""Team shape — five measured axes per team, percentile-scaled for a radar.

Ethan, 2026-08-18 ("keep going" down the ECharts ladder): the game page
gets a two-team radar. A radar is only honest when every axis is a real
measurement on a shared scale, so each axis is computed from the games
table and then rank-scaled to a league percentile (0-100, higher =
better) within the same season:

* **offense**   — points scored per game.
* **defense**   — points ALLOWED per game, inverted: allowing fewer
  points is a bigger shape, exactly like every other axis.
* **form**      — scoring margin over the team's last FORM_GAMES games,
  the recent slice of the same signal `net` averages all season.
* **home edge** — home margin minus away margin. A team that only
  travels poorly is a different bet than a team that is simply bad.
* **steadiness** — margin standard deviation, inverted. Two 8-8 teams
  are different products when one alternates blowouts with collapses.

Percentiles are RANKS, not z-scores, so one 60-point outlier cannot
squash the rest of the league into the middle of the chart. Ties share
the mean of their positions; a league of one team has no shape at all
(``{}``) — a radar with no comparison is decoration.

THE SEASONS ARE BLENDED (2026-09-27): ``blended_shapes`` is what the
build ships — this season and last, mixed per team at the matchup scan's
own split — so the radar and the scan's ranks never tell two stories.
``team_shapes`` (one season alone) stays for the tests and the history.

Standard library only, like the rest of the ratings stack.
"""

from __future__ import annotations

import math

#: How many recent games the form axis reads. Five is the shortest slice
#: that survives one fluke; it matches the streak windows elsewhere.
FORM_GAMES = 5

#: Below this many played games a team's shape is noise wearing a chart.
MIN_GAMES = 4

AXES = ("offense", "defense", "form", "home_edge", "steadiness")
AXIS_LABELS = {
    "offense": "Offense", "defense": "Defense", "form": "Form",
    "home_edge": "Home edge", "steadiness": "Steadiness",
}


def _finals(conn, sport: str, season: int) -> list:
    try:
        return conn.execute(
            "SELECT period, home, away, home_score, away_score FROM games "
            "WHERE sport=? AND season=? AND home_score IS NOT NULL "
            "AND away_score IS NOT NULL ORDER BY period",
            (sport, season)).fetchall()
    except Exception:                                         # noqa: BLE001
        return []          # no games table is no shape, not a crash


def _percentiles(raw: dict) -> dict:
    """{team: value} -> {team: 0-100 percentile}, mean-rank on ties."""
    items = sorted(raw.items(), key=lambda kv: kv[1])
    n = len(items)
    if n < 2:
        return {}
    out: dict = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and items[j + 1][1] == items[i][1]:
            j += 1
        pct = round(100.0 * ((i + j) / 2.0) / (n - 1), 1)
        for k in range(i, j + 1):
            out[items[k][0]] = pct
        i = j + 1
    return out


def team_shapes(conn, sport: str, season: int) -> dict:
    """``{team: {"pct": {axis: 0-100}, "raw": {axis: value}, "games": n}}``.

    Empty when the season has too little played to rank — the caller
    ships nothing and the page keeps its fallback text, which is the
    same never-fatal posture every build extra takes."""
    rows = _finals(conn, sport, season)
    margins: dict = {}
    scored: dict = {}
    allowed: dict = {}
    home_m: dict = {}
    away_m: dict = {}
    for _period, home, away, hs, as_ in rows:
        hm = float(hs) - float(as_)
        for team, mine, theirs, m, side in (
                (home, hs, as_, hm, home_m), (away, as_, hs, -hm, away_m)):
            margins.setdefault(team, []).append(m)
            scored.setdefault(team, []).append(float(mine))
            allowed.setdefault(team, []).append(float(theirs))
            side.setdefault(team, []).append(m)

    teams = [t for t, ms in margins.items() if len(ms) >= MIN_GAMES]
    if len(teams) < 4:
        return {}
    mean = lambda xs: sum(xs) / len(xs)                       # noqa: E731
    raw = {
        "offense": {t: mean(scored[t]) for t in teams},
        # Negated so "higher percentile = better" holds on every axis.
        "defense": {t: -mean(allowed[t]) for t in teams},
        "form": {t: mean(margins[t][-FORM_GAMES:]) for t in teams},
        "home_edge": {t: (mean(home_m[t]) if home_m.get(t) else 0.0)
                      - (mean(away_m[t]) if away_m.get(t) else 0.0)
                      for t in teams},
        "steadiness": {t: -_sd(margins[t]) for t in teams},
    }
    pcts = {axis: _percentiles(vals) for axis, vals in raw.items()}
    out: dict = {}
    for t in teams:
        out[t] = {
            "pct": {axis: pcts[axis].get(t, 50.0) for axis in AXES},
            # Raw values ship un-negated, in the units a reader expects.
            "raw": {
                "offense": round(raw["offense"][t], 1),
                "defense": round(-raw["defense"][t], 1),
                "form": round(raw["form"][t], 1),
                "home_edge": round(raw["home_edge"][t], 1),
                "steadiness": round(-raw["steadiness"][t], 1),
            },
            "games": len(margins[t]),
        }
    return out


def _sd(xs: list) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _season_stats(rows) -> dict:
    """{team: {"scored", "allowed", "margins", "home", "away"}} lists for
    one season's finals, in period order."""
    out: dict = {}
    for _period, home, away, hs, as_ in rows:
        hm = float(hs) - float(as_)
        for team, mine, theirs, m, side in ((home, hs, as_, hm, "home"),
                                            (away, as_, hs, -hm, "away")):
            t = out.setdefault(team, {"scored": [], "allowed": [], "margins": [],
                                      "home": [], "away": []})
            t["scored"].append(float(mine))
            t["allowed"].append(float(theirs))
            t["margins"].append(m)
            t[side].append(m)
    return out


def blended_shapes(conn, sport: str, season: int, changes: dict | None = None) -> dict:
    """The radar on THIS season and last, blended the way the matchup scan
    blends its unit ranks (Ethan, 2026-09-27: "this chart should now be
    updated since it says 2025 and we use a mix of 2025 and 2026").

    Each team's offense axis leans on this season at the scan's offence
    share, defense at its defence share — gamescan.unit_share, growing
    with the season's games and faster for an offence under a new
    starting QB, as measured — and the whole-team axes (home edge,
    steadiness) at the mean of the two. Form is the last FORM_GAMES
    finals whichever season they fell in: a team three games in reads its
    three and last season's last two. Percentiles are then taken across
    the league on the blended numbers, as before.

    ``{team: {"pct", "raw", "games" (this season), "games_last",
    "blend": {"off", "def"}}}``; {} when the league cannot be ranked."""
    from .gamescan import unit_share
    now = _season_stats(_finals(conn, sport, season))
    last = _season_stats(_finals(conn, sport, season - 1))
    mean = lambda xs: sum(xs) / len(xs) if xs else None       # noqa: E731

    def mix(a, b, w):
        if a is None:
            return b
        if b is None:
            return a
        return w * a + (1 - w) * b

    teams = [t for t in set(now) | set(last)
             if len((now.get(t) or {}).get("margins", [])) + len((last.get(t) or {}).get("margins", [])) >= MIN_GAMES]
    if len(teams) < 4:
        return {}
    raw: dict = {axis: {} for axis in AXES}
    meta: dict = {}
    for t in teams:
        c, p = now.get(t) or {}, last.get(t) or {}
        g = len(c.get("margins", []))
        has_prior = bool(p.get("margins"))
        ch = (changes or {}).get(t) or {}
        w = {side: unit_share(g, has_prior, new_qb=side in (ch.get("qb") or []))
             for side in ("off", "def")}
        wt = (w["off"] + w["def"]) / 2
        raw["offense"][t] = mix(mean(c.get("scored")), mean(p.get("scored")), w["off"])
        raw["defense"][t] = -mix(mean(c.get("allowed")), mean(p.get("allowed")), w["def"])
        recent = (p.get("margins") or []) + (c.get("margins") or [])
        raw["form"][t] = mean(recent[-FORM_GAMES:])
        edge = lambda d: ((mean(d.get("home")) or 0.0) - (mean(d.get("away")) or 0.0)) if d.get("margins") else None  # noqa: E731
        raw["home_edge"][t] = mix(edge(c) if g >= 2 else None, edge(p), wt) or 0.0
        sd = lambda d: _sd(d["margins"]) if len(d.get("margins") or []) >= 2 else None  # noqa: E731
        raw["steadiness"][t] = -(mix(sd(c), sd(p), wt) or 0.0)
        meta[t] = {"games": g, "games_last": len(p.get("margins") or []),
                   "blend": {k: round(v, 2) for k, v in w.items()}}
    pcts = {axis: _percentiles(vals) for axis, vals in raw.items()}
    out: dict = {}
    for t in teams:
        out[t] = {
            "pct": {axis: pcts[axis].get(t, 50.0) for axis in AXES},
            "raw": {
                "offense": round(raw["offense"][t], 1),
                "defense": round(-raw["defense"][t], 1),
                "form": round(raw["form"][t], 1),
                "home_edge": round(raw["home_edge"][t], 1),
                "steadiness": round(-raw["steadiness"][t], 1),
            },
            **meta[t],
        }
    return out


def latest_shaped_season(conn, sport: str, today_year: int) -> int | None:
    """The most recent season whose finals can actually be ranked.

    In August the coming NFL season has zero finals, so the radar shows
    LAST season's measured shape — and says so in its label rather than
    pretending it is a preview."""
    for season in (today_year, today_year - 1):
        if team_shapes(conn, sport, season):
            return season
    return None
