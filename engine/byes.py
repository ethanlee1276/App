"""Which week each team does not play.

Ethan, 2026-08-20: "continue on what was still on your list with the bye
week shit."

A bye is the one piece of draft context that is a FACT rather than a
projection — the schedule is published, nobody disputes it, and it decides
whether the roster you just drafted has three starters missing in week
eleven. Every mock draft simulator worth copying shows it and ours had no
idea it existed.

DERIVED, NOT LISTED. A hard-coded table of thirty-two bye weeks is a table
that is silently wrong the moment the schedule moves, and it moves every
year. The schedule is already ingested for everything else, so a bye is
just the regular-season week a team appears in neither column — read off
the same rows the model grades itself against.

REGULAR SEASON ONLY. Post-season weeks would give every team that missed
the play-offs a fistful of phantom byes, and the eighteen-week regular
season is the only part a fantasy league plays in anyway.
"""

from __future__ import annotations

#: A team with no bye, or more than one, means the schedule we hold is
#: partial — mid-ingest, or a season that has not been published in full.
#: Reporting nothing for that team is right: a wrong bye week is worse
#: than a missing one, because a missing one shows up as a blank and a
#: wrong one quietly clears a conflict that is real.
#: A regular-season week runs at least this share of the busiest week's
#: games. Used instead of "week <= 18", because that constant is only true
#: of the current era — the regular season was seventeen weeks until 2021
#: and will change again — and a cutoff wrong by one turns every
#: eliminated team's January into a fistful of phantom byes.
#:
#: RELATIVE, not a game count. An absolute floor is a league size in
#: disguise: eight games is most of an NFL week and more than a whole
#: round of a sixteen-team league, so the first version of this returned
#: nothing at all for anything but the NFL. A share of the busiest week
#: holds whatever the league's size. Play-off rounds halve each time, so
#: the gap either side of this is wide.
REG_WEEK_SHARE = 0.6


def bye_weeks(conn, season: int, sport: str = "nfl") -> dict[str, int]:
    """``{team: week}`` for every team whose schedule is complete."""
    rows = conn.execute(
        "SELECT period, home, away FROM games WHERE sport = ? AND season = ?",
        (sport, season)).fetchall()
    if not rows:
        return {}
    per_week: dict[int, int] = {}
    for r in rows:
        try:
            w = int(r["period"])
        except (TypeError, ValueError):
            continue
        per_week[w] = per_week.get(w, 0) + 1
    busiest = max(per_week.values())
    weeks = {w for w, n in per_week.items() if n >= busiest * REG_WEEK_SHARE}
    if not weeks:
        return {}
    played: dict[str, set] = {}
    for r in rows:
        try:
            w = int(r["period"])
        except (TypeError, ValueError):
            continue
        if w not in weeks:
            continue
        for side in ("home", "away"):
            if r[side]:
                played.setdefault(r[side], set()).add(w)
    out = {}
    for team, seen in played.items():
        missing = weeks - seen
        if len(missing) == 1:
            out[team] = missing.pop()
    return out


def attach(board: list[dict], byes: dict[str, int]) -> int:
    """Stamp ``bye`` on every row we can. Returns how many got one, so a
    build can say so rather than the absence being invisible."""
    n = 0
    for r in board:
        w = byes.get(r.get("team"))
        if w:
            r["bye"] = w
            n += 1
    return n
