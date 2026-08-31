"""nflverse injury-report adapter.

Feeds the engine's injury module with real weekly injury reports:
  * primarily, the **own-player hold** — props on players listed
    Questionable/Doubtful/Out are suppressed by the rules engine;
  * secondarily, knock-on matchup effects (an opposing DT or tackle ruled out
    shifts run/pass projections).

Like weekly stats, nflverse injuries live in GitHub *release* assets, which some
egress policies block. The loader falls back to a local CSV at
``data/cache/injuries_<season>.csv`` — export it once with nfl_data_py.

A caveat worth stating: the injury report carries only a player's position, not
depth-chart or coverage detail. So knock-on effects treat a ruled-out starter at
a position generically — distinguishing an *elite* CB from a depth CB, or LT
from RT, needs a depth-chart / player-grades source (a later phase). The
own-player hold, which is the most important rule, needs none of that.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .fetch import (fetch_csv, load_local_csv, CACHE_DIR, DataUnavailable,
                    release_unavailable)
from .nflverse import _s  # shared "first non-empty key" helper
from ..models import Injury


def _injuries_urls(season: int) -> list[str]:
    base = "https://github.com/nflverse/nflverse-data/releases/download"
    return [
        f"{base}/injuries/injuries_{season}.csv",
        f"{base}/injuries/injuries_{season}.csv.gz",
    ]


# nflverse report_status -> engine status.
STATUS_MAP = {
    "out": "OUT",
    "doubtful": "DOUBTFUL",
    "questionable": "QUESTIONABLE",
    "injured reserve": "IR",
    "ir": "IR",
}

# Position -> engine "role" for knock-on effects (see module docstring caveat).
# Only positions the injury engine reasons about are mapped; others pass through
# lowercased and simply won't trigger a knock-on rule.
POSITION_ROLE = {
    "T": "OT", "OT": "OT", "LT": "LT", "RT": "OT",
    "DT": "dt", "NT": "nt",
    "CB": "cb1", "DB": "cb1",
}


def load_injuries(season: int) -> list[dict]:
    """Weekly injury reports for a season, from release URLs or a local CSV."""
    local = CACHE_DIR / f"injuries_{season}.csv"
    # No exists() short-circuit — the worst place of all for the freeze
    # test_roster_freshness documents: injury reports change DAILY in
    # season, and a file cached in Week 1 would apply Week 1's OUT list
    # to every board for the rest of the year. fetch_csv's TTL decides.
    last_err = None
    for url in _injuries_urls(season):
        try:
            return fetch_csv(url, f"injuries_{season}.csv")
        except DataUnavailable as exc:
            last_err = exc
    raise release_unavailable(
        "injury reports", season, local,
        f"nfl.import_injuries([{season}]).to_csv('{local}', index=False)",
        _injuries_urls(season), last_err)


def _map_status(raw: str) -> str:
    return STATUS_MAP.get(raw.strip().lower(), "")


def injuries_for_week(rows: list[dict], week: int) -> list[Injury]:
    """Parse the feed into engine Injury objects for one week.

    Rows with no actionable game status (blank report_status) are skipped — they
    are practice-report noise, not game designations.
    """
    out: list[Injury] = []
    for r in rows:
        if _s(r, "week", default="") != str(week):
            continue
        status = _map_status(_s(r, "report_status", "game_status", "status"))
        if not status:
            continue
        player = _s(r, "full_name", "player_name", "player_display_name")
        if not player:
            continue
        position = _s(r, "position", default="").upper()
        out.append(Injury(
            player=player,
            team=_s(r, "team", "recent_team"),
            position=position,
            role=POSITION_ROLE.get(position, position.lower()),
            status=status,
        ))
    return out


@dataclass
class InjuryAttachResult:
    total: int = 0
    holds: list[str] = field(default_factory=list)   # props suppressed by own injury
    by_status: dict = field(default_factory=dict)


def attach_injuries_to_slate(slate, season: int, week: int) -> InjuryAttachResult:
    """Populate each game's injuries from the real feed and report which of the
    slate's prop players are themselves dinged (and will be held)."""
    rows = load_injuries(season)
    week_injuries = injuries_for_week(rows, week)

    by_team: dict[str, list[Injury]] = {}
    for inj in week_injuries:
        by_team.setdefault(inj.team, []).append(inj)

    for g in slate.games:
        g.injuries = by_team.get(g.home, []) + by_team.get(g.away, [])

    # Which prop players carry an injury designation of their own?
    from ..injuries import player_injury_status
    result = InjuryAttachResult(total=len(week_injuries))
    for inj in week_injuries:
        result.by_status[inj.status] = result.by_status.get(inj.status, 0) + 1
    for prop in slate.props:
        game = next((g for g in slate.games
                     if prop.team in (g.home, g.away)
                     and prop.opponent in (g.home, g.away)), None)
        if game and player_injury_status(prop, game.injuries):
            result.holds.append(prop.player)
    return result
