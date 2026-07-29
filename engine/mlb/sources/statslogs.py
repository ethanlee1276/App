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
    "pa": "hitting",
    STRIKEOUTS: "pitching",
}
MARKET_STAT = {
    TOTAL_BASES: "totalBases", HITS: "hits", HOME_RUNS: "homeRuns",
    STRIKEOUTS: "strikeOuts",
    # Plate appearances: not a prop market — ingested so the opportunity
    # model can learn each hitter's real volume per game.
    "pa": "plateAppearances",
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


def parse_officials(boxscore: dict) -> str:
    """The home-plate umpire's name from a boxscore, or "".

    Assignments are announced a few hours before first pitch — one of the
    late-breaking inputs that move strikeout props before books fully adjust.
    """
    for o in boxscore.get("officials", []) or []:
        if (o.get("officialType") or "").lower() == "home plate":
            return (o.get("official", {}) or {}).get("fullName", "") or ""
    return ""


def last_final_game(sched_json: dict, team_id: int) -> tuple[int, str] | None:
    """From a team-scoped schedule response, the most recent FINAL game as
    ``(gamePk, side)`` where side is which bench this team occupied — or
    ``None`` if nothing has gone final in the window."""
    best: tuple[str, int, str] | None = None
    for day in sched_json.get("dates", []) or []:
        for g in day.get("games", []) or []:
            state = ((g.get("status") or {}).get("abstractGameState") or "")
            pk = g.get("gamePk")
            if state != "Final" or not pk:
                continue
            home_id = (((g.get("teams") or {}).get("home") or {})
                       .get("team") or {}).get("id")
            side = "home" if home_id == team_id else "away"
            key = (day.get("date") or "", int(pk), side)
            if best is None or key > best:
                best = key
    return (best[1], best[2]) if best else None


def parse_game_log(stats_json: dict, market: str, limit: int | None = 15,
                   id_to_abbr: dict | None = None) -> list[MLBGameLog]:
    """Most-recent-first game logs for one market from a ``gameLog`` response.

    gameLog splits are chronological (oldest first); we reverse and take the
    most recent ``limit`` games. ``limit=None`` keeps the whole season — the
    API always returns season-to-date, so a capped window here is why a
    day-by-day historical ingest kept re-storing the same 15 games."""
    id_to_abbr = id_to_abbr or TEAM_ID_ABBR
    field = MARKET_STAT[market]
    stat_blocks = stats_json.get("stats") or []
    splits = stat_blocks[0].get("splits", []) if stat_blocks else []
    recent = list(reversed(splits))
    if limit is not None:
        recent = recent[:limit]

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
                               home=bool(sp.get("isHome", True)),
                               date=(sp.get("date") or "")[:10]))
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


def projected_lineup(team_id: int, date: str) -> list[LineupEntry]:
    """The team's batting order from its last completed game — tonight's best
    guess until the official lineup posts.

    Books hang home-run prices hours before lineups are announced; gating
    every hitter prop on the official card left the board empty all morning
    while FanDuel had a full HR menu. A projected order is right far more
    often than not (regulars play), and everything built from it carries a
    "not confirmed yet" caveat while the rules engine holds recommendations.
    """
    import datetime as _dt
    try:
        d = _dt.date.fromisoformat(date)
        sched = _get_json(
            f"{STATS_BASE}/schedule?sportId=1&teamId={team_id}"
            f"&startDate={(d - _dt.timedelta(days=3)).isoformat()}"
            f"&endDate={(d - _dt.timedelta(days=1)).isoformat()}",
            f"mlb_teamsched_{team_id}_{date}.json", ttl=21600)
        last = last_final_game(sched, team_id)
        if not last:
            return []
        return parse_lineup(fetch_boxscore(last[0]), last[1])
    except (DataUnavailable, ValueError):
        return []


# --- orchestrator -----------------------------------------------------------
def _round_half(x: float) -> float:
    return round(x * 2) / 2.0


def _proxy_line(mean: float, market: str) -> float:
    if market == HOME_RUNS:
        return 0.5
    return max(0.5, _round_half(mean) - 0.5)


def build_live_slate(date: str, season: int | None = None,
                     hitter_markets=(TOTAL_BASES, HITS, HOME_RUNS),
                     include_pitchers: bool = True,
                     limit: int | None = 15) -> MLBSlate:
    """Assemble a live MLB slate for ``date`` (YYYY-MM-DD).

    Hitter props come from confirmed lineups (held by the rules engine if a
    lineup isn't posted yet); pitcher strikeout props come from the probable
    starters. Every prop carries real game logs and a recent-form proxy line.

    ``limit`` caps each player's game log at the most recent N games — right
    for a live slate (recent form), wrong for ingestion: pass ``None`` to keep
    the full season so a backtest can replay every game.
    """
    season = season or int(date[:4])
    sched = _get_json(
        f"{STATS_BASE}/schedule?sportId=1&date={date}"
        f"&hydrate=probablePitcher,venue",
        f"mlb_schedule_{date}.json", ttl=600)

    games: list[MLBGame] = []
    props: list[MLBProp] = []

    # Pass 1: games. Props are built in a second pass because doubleheaders
    # need the full day known first — the same pair twice must be numbered,
    # and props must attach to exactly ONE leg (see below).
    raw: list[tuple] = []                # (schedule json, game, box, teams json)
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
                           pitchers=pitchers, lineups_confirmed=lineups_confirmed,
                           plate_umpire=parse_officials(box),
                           game_number=int(g.get("gameNumber") or 1),
                           doubleheader=(g.get("doubleHeader") or "N") != "N",
                           game_pk=int(game_pk or 0))
            if weather is not None:
                game.weather = weather
            games.append(game)
            raw.append((g, game, box, teams, home, away))

    # Doubleheader bookkeeping: number the legs by first pitch even when the
    # feed's own fields are missing, and pick each pair's PROP game — the
    # first leg that isn't final. Books post props for the next game to be
    # played; building props for both legs would double every hitter's rows
    # and merge two different games' prices under one line.
    by_pair: dict[tuple, list[MLBGame]] = {}
    for _, game, *_rest in raw:
        by_pair.setdefault((game.home, game.away), []).append(game)
    prop_games: set[int] = set()
    for pair, legs in by_pair.items():
        if len(legs) > 1:
            legs.sort(key=lambda x: x.kickoff or "")
            for i, leg in enumerate(legs):
                leg.game_number = i + 1
                leg.doubleheader = True
    finals = {id(game): (g.get("status", {}).get("abstractGameState") == "Final")
              for g, game, *_rest in raw}
    for pair, legs in by_pair.items():
        pg = next((x for x in legs if not finals.get(id(x))), legs[0])
        prop_games.add(id(pg))

    # Pass 2: props — only from each pair's prop game.
    for g, game, box, teams, home, away in raw:
        if id(game) not in prop_games:
            continue
        home_ab, away_ab = game.home, game.away
        prop_gn = game.game_number if game.doubleheader else 0

        # Hitter props from confirmed lineups — or, before lineups post,
        # from each team's LAST batting order (projected; flagged via
        # game.lineups_confirmed=False, which holds recommendations and
        # caveats the HR board).
        for side, team_ab, opp_ab in (("home", home_ab, away_ab),
                                      ("away", away_ab, home_ab)):
            entries = parse_lineup(box, side)
            if not entries:
                tid = (home if side == "home" else away).get("id")
                entries = projected_lineup(tid, date) if tid else []
            for entry in entries:
                try:
                    person = parse_person(fetch_person(entry.person_id))
                except DataUnavailable:
                    person = {"bats": "R"}
                for market in hitter_markets:
                    _add_prop(props, entry.person_id, entry.name, team_ab,
                              opp_ab, entry.position or person.get("position", ""),
                              market, season, entry.spot, person.get("bats", "R"),
                              log_limit=limit, game_number=prop_gn)

        # Pitcher strikeout props from probable starters.
        if include_pitchers:
            for team_ab, opp_ab in ((home_ab, away_ab), (away_ab, home_ab)):
                pp = teams.get("home" if team_ab == home_ab else "away", {}).get("probablePitcher")
                if not pp:
                    continue
                _add_prop(props, pp.get("id"), pp.get("fullName", "TBD"),
                          team_ab, opp_ab, "SP", STRIKEOUTS, season,
                          lineup_spot=1, bats="R",
                          throws=pp.get("pitchHand", {}).get("code", "R"),
                          log_limit=limit, game_number=prop_gn)

    return MLBSlate(date=date, games=games, props=props)


def _add_prop(props, person_id, name, team, opp, position, market, season,
              lineup_spot, bats, throws="R", log_limit: int | None = 15,
              game_number: int = 0):
    if not person_id:
        return
    group = MARKET_GROUP[market]
    try:
        logs = parse_game_log(fetch_game_log(person_id, group, season), market,
                              limit=log_limit)
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
        person_id=int(person_id), game_number=game_number,
    ))
