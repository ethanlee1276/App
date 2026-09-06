"""The postseason bracket, drawn from games that were actually played.

A bracket is the one page on this site where inventing something would be
most tempting and least forgivable. Seeds get projected, matchups get
predicted, and a chart that looks authoritative is believed. So this one
only ever draws what happened:

* a matchup exists because two teams played each other in the postseason
  window, not because a seeding rule says they should;
* a series score is the count of games each side won, so a 2-1 is a 2-1
  and an unfinished series says how many games are in the book;
* rounds are derived from the games themselves — a matchup sits in the
  round after every earlier matchup it shares a team with. That ordering
  falls out of who played whom, so it stays right through byes, reseeding
  and formats that change between leagues and years.

Before the first postseason game, there is no bracket and the page says
so. `engine.standings.conference_seeds` is where a *projection* lives, and
it is labelled as one.
"""

from __future__ import annotations

import datetime as _dt

from . import divisions
from .seasons import season_of

# When each league's postseason begins. NFL is a week number because its
# periods are weeks; the rest are dates. `next_year` marks a league whose
# postseason lands in the calendar year after the season's label.
#            (kind,   value,        next_year)
POSTSEASON = {
    "nfl":  ("week", 19, False),          # 18-week regular season
    "mlb":  ("date", (9, 30), False),     # Wild Card round, end of September
    "nba":  ("date", (4, 15), True),      # play-in and first round
    "wnba": ("date", (9, 10), False),
    # THE SEASON'S OWN DECEMBER, NOT THE NEXT ONE. This read True until
    # 2026-09-05, which dated the 2025 bowls at 2026-12-15 — so no
    # college game was ever postseason: bowls and the playoff counted
    # in the regular-season table (a 13-0 champion read 15-0) and the
    # bracket page had no college rows to draw. The NBA's True is right
    # (the 2025 season's playoffs are in April 2026); college's season
    # label is the autumn it kicked off, and its bowls start that
    # December.
    "cfb":  ("date", (12, 15), False),    # bowls and the playoff
}

ROUND_NAMES = {
    "nfl": ["Wild Card", "Divisional", "Conference Championship", "Super Bowl"],
    "mlb": ["Wild Card", "Division Series", "Championship Series",
            "World Series"],
    "nba": ["First Round", "Conference Semifinals", "Conference Finals",
            "NBA Finals"],
    "wnba": ["First Round", "Semifinals", "WNBA Finals"],
    "cfb": ["First Round", "Quarterfinals", "Semifinals",
            "National Championship"],
}


def _week_num(period: str) -> int | None:
    p = str(period or "").strip()
    if p.isdigit():
        return int(p)
    return None


def is_postseason(sport: str, season: int, period: str) -> bool:
    """Does this game belong to the postseason of that season?"""
    spec = POSTSEASON.get(sport)
    if not spec:
        return False
    kind, value, next_year = spec
    if kind == "week":
        wk = _week_num(period)
        return wk is not None and wk >= value
    try:
        d = _dt.date.fromisoformat(str(period))
    except (TypeError, ValueError):
        return False
    month, day = value
    start = _dt.date(season + (1 if next_year else 0), month, day)
    return d >= start


def _matchups(sport: str, rows) -> list[dict]:
    """One entry per pair of teams that met, with the series score."""
    by_pair: dict[tuple, dict] = {}
    for r in rows:
        home = divisions.canonical(sport, r["home"])
        away = divisions.canonical(sport, r["away"])
        key = tuple(sorted((home, away)))
        m = by_pair.setdefault(key, {
            "teams": list(key), "wins": {key[0]: 0, key[1]: 0},
            "games": 0, "first": str(r["period"]), "last": str(r["period"]),
        })
        hs, as_ = float(r["home_score"]), float(r["away_score"])
        if hs > as_:
            m["wins"][home] += 1
        elif as_ > hs:
            m["wins"][away] += 1
        m["games"] += 1
        m["first"] = min(m["first"], str(r["period"]))
        m["last"] = max(m["last"], str(r["period"]))
    return sorted(by_pair.values(), key=lambda m: (m["first"], m["teams"]))


def _rounds(matchups: list[dict]) -> None:
    """Assign each matchup a round, from who played whom.

    A matchup sits one round after every earlier matchup it shares a team
    with. Derived rather than assumed, so byes, reseeding and formats that
    differ between leagues and years all come out right without a table
    that has to be maintained.
    """
    seen: list[dict] = []
    for m in matchups:
        rnd = 1
        for prev in seen:
            if set(prev["teams"]) & set(m["teams"]):
                rnd = max(rnd, prev["round"] + 1)
        m["round"] = rnd
        seen.append(m)


def bracket(conn, sport: str, season: int | None = None,
            today: str | None = None) -> dict:
    """The postseason so far, or an honest empty answer."""
    day = today or _dt.date.today().isoformat()
    season = season if season is not None else season_of(sport, day)
    if sport not in POSTSEASON:
        return {"sport": sport, "season": season, "started": False,
                "rounds": [], "note": f"No postseason defined for {sport}."}

    rows = [r for r in conn.execute(
        "SELECT period, home, away, home_score, away_score FROM games "
        "WHERE sport=? AND season=? AND home_score IS NOT NULL "
        "AND away_score IS NOT NULL ORDER BY period", (sport, season))
        if is_postseason(sport, season, r["period"])]

    if not rows:
        return {"sport": sport, "season": season, "started": False,
                "rounds": [],
                "note": ("The postseason has not started — or its games are "
                         "not ingested yet. This chart is drawn from games "
                         "that were actually played, so it stays empty "
                         "until they are.")}

    ms = _matchups(sport, rows)
    _rounds(ms)
    names = ROUND_NAMES.get(sport, [])
    depth = max(m["round"] for m in ms)
    by_round: dict[int, list] = {}
    for m in ms:
        a, b = m["teams"]
        wa, wb = m["wins"][a], m["wins"][b]
        lead = a if wa > wb else b if wb > wa else ""
        by_round.setdefault(m["round"], []).append({
            "teams": m["teams"], "score": [wa, wb], "games": m["games"],
            "leader": lead, "first": m["first"], "last": m["last"],
            "label": f"{a} {wa}–{wb} {b}",
        })

    # Name rounds from the END of the league's list: a bracket seen at the
    # Conference Finals has two rounds in it, and calling those "Wild Card"
    # and "Divisional" would be wrong in the most visible way possible.
    rounds = []
    for i, rnd in enumerate(sorted(by_round)):
        name = ""
        if names:
            idx = len(names) - depth + i
            name = names[idx] if 0 <= idx < len(names) else f"Round {rnd}"
        rounds.append({"round": rnd, "name": name or f"Round {rnd}",
                       "matchups": by_round[rnd]})

    return {"sport": sport, "season": season, "started": True,
            "rounds": rounds, "games_counted": len(rows), "note": ""}
