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

TWO SOURCES SINCE 2026-09-07, and the reason is a roster move. The
weekly report is the club's filed designation for the game: Questionable,
Doubtful, Out. It is filed Wednesday to Friday, nflverse republishes it
on its own schedule, and this box re-downloads it twice a day. It does
NOT list a man placed on injured reserve — he is off the active roster
and files nothing — and it cannot list a Saturday move at all. Ethan,
2026-09-07: "RB2 Isiah Pacheco is now out till October 11th ... make
sure we are adjusting if needed and reading this data and adjusting
everything live." The site had been reading that news since August —
ESPN's keyless current-status board feeds the injuries page and the
news tape — but nothing carried it to the model. `live_injuries` turns
that board into the same `Injury` objects, `merge_injuries` lays it over
the weekly report (a man on both keeps the more severe designation), and
`attach_injuries_to_slate` takes the merged list. The live board is
cache-served inside `espninjuries.INJURY_TTL`, so the model is at most
ten minutes plus one build behind ESPN.
"""

from __future__ import annotations

import time
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
    #: How many designations each source contributed, and how many the
    #: live board added that the weekly report did not have — the number
    #: that says whether the second source is doing anything.
    weekly: int = 0
    live: int = 0
    live_added: int = 0
    #: Set when the weekly report could not be fetched and the live board
    #: carried the slate alone. None when the weekly report was read.
    weekly_error: str | None = None


# --- the live board -----------------------------------------------------------

# ESPN status -> engine status. The exact strings the NFL board uses; the
# substring rules in `_map_live_status` catch the reserve lists ESPN
# spells several ways. "Day-To-Day" is deliberately unmapped: on the NFL
# board it is a practice note, not a game designation, and holding every
# prop on it would empty the board every Wednesday.
LIVE_STATUS_MAP = {
    "out": "OUT",
    "doubtful": "DOUBTFUL",
    "questionable": "QUESTIONABLE",
    "injured reserve": "IR",
}

#: A Questionable or Doubtful designation is a statement about ONE game.
#: The feed keeps re-filing a current one, so a row older than this is
#: last week's and is dropped. OUT and IR are standing statuses — a man
#: on reserve stays listed, correctly, for as long as he is on it.
LIVE_DESIGNATION_DAYS = 7

#: Which designation wins when the weekly report and the live board both
#: list a man. The hold is conservative by design: it lifts when
#: inactives confirm, not when one feed sounds cheerier than the other.
SEVERITY = {"IR": 3, "OUT": 3, "DOUBTFUL": 2, "QUESTIONABLE": 1}


def _map_live_status(raw) -> str:
    k = (raw or "").strip().lower()
    if k in LIVE_STATUS_MAP:
        return LIVE_STATUS_MAP[k]
    if "reserve" in k or "unable to perform" in k or "non-football" in k:
        return "IR"
    if "suspen" in k:
        return "OUT"
    return ""


def live_injuries(rows: list[dict], now: float | None = None) -> list[Injury]:
    """ESPN's NFL board (`espninjuries.parse_injuries` rows) as engine
    `Injury` objects, keyed the way the slate keys teams.

    Newest filing per player, return notices unmapped, team names folded
    to the slate's abbreviations (a team the table cannot key is dropped
    rather than guessed), game-week designations aged out after
    `LIVE_DESIGNATION_DAYS`, and an undated Questionable dropped outright
    — with no date it can never age out, which is the standing-claim trap
    the injuries page already closes for return notices.
    """
    from .espninjuries import current_rows, _parse_iso_ts
    from .oddsapi import TEAM_ABBR
    cutoff = (now if now is not None else time.time()) - LIVE_DESIGNATION_DAYS * 86400
    out: list[Injury] = []
    for r in current_rows(rows):
        # A cleared-to-play notice carries status "Active", which maps
        # to nothing below — the page's `is_return` test is not needed
        # here, and a second guard doing the same job would be one more
        # rule announced in prose and enforced in two places.
        status = _map_live_status(r.get("status"))
        if not status:
            continue
        team = TEAM_ABBR.get(r.get("team") or "")
        if not team:
            continue
        if status in ("QUESTIONABLE", "DOUBTFUL"):
            stamp = _parse_iso_ts(r.get("date"))
            if stamp is None or stamp < cutoff:
                continue
        position = (r.get("pos") or "").upper()
        out.append(Injury(player=r.get("player") or "", team=team,
                          position=position,
                          role=POSITION_ROLE.get(position, position.lower()),
                          status=status))
    return [i for i in out if i.player]


def load_live_injuries() -> list[Injury]:
    """Fetch (cache-served inside `espninjuries.INJURY_TTL`) and parse the
    live NFL board. Raises whatever the fetch raises when there is no
    cache to fall back on; the caller decides what a missing live board
    costs, and for the build it costs a note, never the board."""
    from .espninjuries import fetch_injuries, parse_injuries
    return live_injuries(parse_injuries(fetch_injuries("nfl")))


def merge_injuries(weekly: list[Injury], live: list[Injury]) -> tuple[list[Injury], int]:
    """The weekly report with the live board laid over it: one row per
    (team, player); a man on both keeps the more severe designation, on
    the weekly row (whose role the depth charts may already have refined).
    Returns ``(merged, added)`` where ``added`` counts rows only the live
    board had."""
    from .oddsapi import normalize_name
    by: dict[tuple[str, str], Injury] = {}
    for inj in weekly:
        by[(inj.team, normalize_name(inj.player))] = inj
    added = 0
    for inj in live:
        key = (inj.team, normalize_name(inj.player))
        prev = by.get(key)
        if prev is None:
            by[key] = inj
            added += 1
        elif SEVERITY.get(inj.status, 0) > SEVERITY.get(prev.status, 0):
            prev.status = inj.status
    return list(by.values()), added


def _spell_like_slate(injuries: list[Injury], slate) -> None:
    """The hold compares names exactly (`injuries.player_injury_status`),
    and the weekly report and the slate spell names from the same nflverse
    universe, so that was always safe. A live-board row is spelled ESPN's
    way; where a prop on the slate normalises to the same man on the same
    team, the row takes the slate's spelling so the hold can see it."""
    from .oddsapi import normalize_name
    want = {(p.team, normalize_name(p.player)): p.player for p in slate.props}
    for inj in injuries:
        hit = want.get((inj.team, normalize_name(inj.player)))
        if hit and hit != inj.player:
            inj.player = hit


def attach_injuries_to_slate(slate, season: int, week: int,
                             live: list[Injury] | None = None) -> InjuryAttachResult:
    """Populate each game's injuries from the real feed and report which of the
    slate's prop players are themselves dinged (and will be held).

    ``live`` is the live board (`live_injuries`), merged over the weekly
    report when given. With a live board in hand a weekly report that
    cannot be fetched — nflverse's file is a 404 until it publishes a
    season's first week — no longer empties the slate: the live board
    carries it alone and `weekly_error` says so. With no live board the
    weekly failure raises as it always did.
    """
    weekly_error = None
    try:
        rows = load_injuries(season)
        week_injuries = injuries_for_week(rows, week)
    except DataUnavailable as exc:
        if live is None:
            raise
        week_injuries, weekly_error = [], str(exc)
    n_weekly = len(week_injuries)
    week_injuries, added = merge_injuries(week_injuries, live or [])
    if live:
        _spell_like_slate(week_injuries, slate)

    by_team: dict[str, list[Injury]] = {}
    for inj in week_injuries:
        by_team.setdefault(inj.team, []).append(inj)

    for g in slate.games:
        g.injuries = by_team.get(g.home, []) + by_team.get(g.away, [])

    # Which prop players carry an injury designation of their own?
    from ..injuries import player_injury_status
    result = InjuryAttachResult(total=len(week_injuries), weekly=n_weekly,
                                live=len(live or []), live_added=added,
                                weekly_error=weekly_error)
    for inj in week_injuries:
        result.by_status[inj.status] = result.by_status.get(inj.status, 0) + 1
    for prop in slate.props:
        game = next((g for g in slate.games
                     if prop.team in (g.home, g.away)
                     and prop.opponent in (g.home, g.away)), None)
        if game and player_injury_status(prop, game.injuries):
            result.holds.append(prop.player)
    return result
