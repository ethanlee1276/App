"""Confirmed lineups + per-player game logs from the free MLB Stats API.

Endpoints (all keyless, statsapi.mlb.com):
  * ``game/{gamePk}/boxscore``            → confirmed batting order + positions
  * ``people/{id}``                       → bat side / throwing hand / position
  * ``people/{id}/stats?stats=gameLog``   → game-by-game hitting / pitching

The JSON **parsers** below are pure and unit-tested against fixtures; the
``fetch_*`` wrappers and ``build_live_slate`` orchestrator call the network and
degrade with :class:`DataUnavailable` (both hosts are blocked in some sandboxed
environments — run where statsapi.mlb.com is reachable). Since the MLB Stats
API carries no betting lines, live props get a recent-form **proxy** line, like
the NFL live path; attach an odds feed for real book edges.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...models import SportsbookLine
from ...sources.fetch import DataUnavailable
from ..data_loader import MLBSlate
from ..models import (
    MLBGame, MLBProp, MLBGameLog, Pitcher,
    TOTAL_BASES, HITS, HOME_RUNS, STRIKEOUTS,
)
from .mlbstats import (
    STATS_BASE, _get_json, TEAM_ID_ABBR, VENUE_PARK, PARK_COORDS, park_weather,
)

# Which stat group + per-game stat field feeds each market.
MARKET_GROUP = {
    TOTAL_BASES: "hitting", HITS: "hitting", HOME_RUNS: "hitting",
    STRIKEOUTS: "pitching",
}
MARKET_STAT = {
    TOTAL_BASES: "totalBases", HITS: "hits", HOME_RUNS: "homeRuns",
    STRIKEOUTS: "strikeOuts",
}


# --- pure parsers -----------------------------------------------------------
@dataclass
class LineupEntry:
    person_id: int
    name: str
    position: str
    spot: int            # 1-9 batting-order slot


def parse_lineup(boxscore: dict, side: str) -> list[LineupEntry]:
    """Confirmed starters for ``side`` ("home"/"away"), in batting order.

    The boxscore's ``battingOrder`` is the ordered list of starter person ids;
    positions live in the ``players`` map. An empty/pre-lineup boxscore yields
    an empty list (the caller then holds or skips)."""
    team = boxscore.get("teams", {}).get(side, {})
    order = team.get("battingOrder", []) or []
    players = team.get("players", {}) or {}
    out: list[LineupEntry] = []
    for spot, pid in enumerate(order, start=1):
        p = players.get(f"ID{pid}", {})
        person = p.get("person", {})
        out.append(LineupEntry(
            person_id=int(pid),
            name=person.get("fullName", ""),
            position=p.get("position", {}).get("abbreviation", ""),
            spot=spot,
        ))
    return out


def parse_person(person_json: dict) -> dict:
    """Extract handedness + position from a ``people`` response."""
    people = person_json.get("people", [])
    p = people[0] if people else {}
    return {
        "name": p.get("fullName", ""),
        "bats": p.get("batSide", {}).get("code", "R"),
        "throws": p.get("pitchHand", {}).get("code", "R"),
        "position": p.get("primaryPosition", {}).get("abbreviation", ""),
    }


def parse_game_log(stats_json: dict, market: str, limit: int = 15,
                   id_to_abbr: dict | None = None) -> list[MLBGameLog]:
    """Most-recent-first game logs for one market from a ``gameLog`` response.

    gameLog splits are chronological (oldest first); we reverse and take the
    most recent ``limit`` games."""
    id_to_abbr = id_to_abbr or TEAM_ID_ABBR
    field = MARKET_STAT[market]
    stat_blocks = stats_json.get("stats") or []
    splits = stat_blocks[0].get("splits", []) if stat_blocks else []
    recent = list(reversed(splits))[:limit]

    logs: list[MLBGameLog] = []
    n = len(recent)
    for i, sp in enumerate(recent):
        stat = sp.get("stat", {})
        raw = stat.get(field, 0)
        try:
            value = float(raw or 0)
        except (TypeError, ValueError):
            value = 0.0
        opp = sp.get("opponent", {})
        opp_ab = (opp.get("abbreviation")
                  or id_to_abbr.get(opp.get("id"))
                  or opp.get("name", ""))
        logs.append(MLBGameLog(game=n - i, opponent=opp_ab, value=value,
                               home=bool(sp.get("isHome", True))))
    return logs


# --- fetch wrappers ---------------------------------------------------------
def fetch_boxscore(game_pk: int) -> dict:
    return _get_json(f"{STATS_BASE}/game/{game_pk}/boxscore",
                     f"mlb_box_{game_pk}.json", ttl=300)


def fetch_person(person_id: int) -> dict:
    return _get_json(f"{STATS_BASE}/people/{person_id}",
                     f"mlb_person_{person_id}.json", ttl=86400)


def fetch_game_log(person_id: int, group: str, season: int) -> dict:
    url = (f"{STATS_BASE}/people/{person_id}/stats"
           f"?stats=gameLog&group={group}&season={season}")
    return _get_json(url, f"mlb_log_{group}_{person_id}_{season}.json", ttl=1800)


# --- orchestrator -----------------------------------------------------------
def _round_half(x: float) -> float:
    return round(x * 2) / 2.0


def _proxy_line(mean: float, market: str) -> float:
    if market == HOME_RUNS:
        return 0.5
    return max(0.5, _round_half(mean) - 0.5)


def build_live_slate(date: str, season: int | None = None,
                     hitter_markets=(TOTAL_BASES, HITS),
                     include_pitchers: bool = True,
                     limit: int = 15) -> MLBSlate:
    """Assemble a live MLB slate for ``date`` (YYYY-MM-DD).

    Hitter props come from confirmed lineups (held by the rules engine if a
    lineup isn't posted yet); pitcher strikeout props come from the probable
    starters. Every prop carries real game logs and a recent-form proxy line.
    """
    season = season or int(date[:4])
    sched = _get_json(
        f"{STATS_BASE}/schedule?sportId=1&date={date}"
        f"&hydrate=probablePitcher,venue",
        f"mlb_schedule_{date}.json", ttl=600)

    games: list[MLBGame] = []
    props: list[MLBProp] = []

    for day in sched.get("dates", []):
        for g in day.get("games", []):
            game_pk = g.get("gamePk")
            teams = g.get("teams", {})
            home = teams.get("home", {}).get("team", {})
            away = teams.get("away", {}).get("team", {})
            home_ab = TEAM_ID_ABBR.get(home.get("id"), home.get("abbreviation", ""))
            away_ab = TEAM_ID_ABBR.get(away.get("id"), away.get("abbreviation", ""))
            venue = (g.get("venue", {}).get("name") or "").lower()
            park = next((k for frag, k in VENUE_PARK.items() if frag in venue), "generic")

            pitchers = {}
            for side, ab in (("home", home_ab), ("away", away_ab)):
                pp = teams.get(side, {}).get("probablePitcher")
                if pp:
                    pitchers[ab] = Pitcher(
                        name=pp.get("fullName", "TBD"),
                        throws=pp.get("pitchHand", {}).get("code", "R"))

            weather = park_weather(park) if park in PARK_COORDS else None
            box = {}
            try:
                box = fetch_boxscore(game_pk) if game_pk else {}
            except DataUnavailable:
                box = {}
            lineups_confirmed = bool(box.get("teams", {}).get("home", {}).get("battingOrder"))

            game = MLBGame(home=home_ab, away=away_ab, park=park,
                           date=day.get("date", date), kickoff=g.get("gameDate", ""),
                           pitchers=pitchers, lineups_confirmed=lineups_confirmed)
            if weather is not None:
                game.weather = weather
            games.append(game)

            # Hitter props from confirmed lineups.
            for side, team_ab, opp_ab in (("home", home_ab, away_ab),
                                          ("away", away_ab, home_ab)):
                for entry in parse_lineup(box, side):
                    try:
                        person = parse_person(fetch_person(entry.person_id))
                    except DataUnavailable:
                        person = {"bats": "R"}
                    for market in hitter_markets:
                        _add_prop(props, entry.person_id, entry.name, team_ab,
                                  opp_ab, entry.position or person.get("position", ""),
                                  market, season, entry.spot, person.get("bats", "R"))

            # Pitcher strikeout props from probable starters.
            if include_pitchers:
                for team_ab, opp_ab in ((home_ab, away_ab), (away_ab, home_ab)):
                    pp = teams.get("home" if team_ab == home_ab else "away", {}).get("probablePitcher")
                    if not pp:
                        continue
                    _add_prop(props, pp.get("id"), pp.get("fullName", "TBD"),
                              team_ab, opp_ab, "SP", STRIKEOUTS, season,
                              lineup_spot=1, bats="R",
                              throws=pp.get("pitchHand", {}).get("code", "R"))

    return MLBSlate(date=date, games=games, props=props)


def _add_prop(props, person_id, name, team, opp, position, market, season,
              lineup_spot, bats, throws="R"):
    if not person_id:
        return
    group = MARKET_GROUP[market]
    try:
        logs = parse_game_log(fetch_game_log(person_id, group, season), market)
    except DataUnavailable:
        return
    if len(logs) < 3:
        return
    recent = [g.value for g in logs[:5]]
    baseline = sum(recent) / len(recent)
    props.append(MLBProp(
        player=name, team=team, opponent=opp, position=position, market=market,
        logs=logs, career_avg=round(sum(g.value for g in logs) / len(logs), 3),
        vs_pitcher_avg=None,
        lines=[SportsbookLine(book="proxy", line=_proxy_line(baseline, market),
                              over_odds=-110, under_odds=-110)],
        bats=bats, throws=throws, lineup_spot=lineup_spot,
    ))
