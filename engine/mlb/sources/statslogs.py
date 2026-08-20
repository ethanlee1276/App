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
    TOTAL_BASES, HITS, HOME_RUNS, STRIKEOUTS, OUTS,
)
from .mlbstats import (
    STATS_BASE, _get_json, TEAM_ID_ABBR, VENUE_PARK, PARK_COORDS, park_weather,
    headshot_url, fetch_many,
)

# Which stat group + per-game stat field feeds each market.
MARKET_GROUP = {
    TOTAL_BASES: "hitting", HITS: "hitting", HOME_RUNS: "hitting",
    "pa": "hitting",
    STRIKEOUTS: "pitching",
    OUTS: "pitching",
}
MARKET_STAT = {
    TOTAL_BASES: "totalBases", HITS: "hits", HOME_RUNS: "homeRuns",
    STRIKEOUTS: "strikeOuts",
    # Outs recorded is innings pitched x 3, and the API reports it
    # directly — no reconstructing 6.1 IP into 19 outs and getting the
    # thirds wrong.
    OUTS: "outs",
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


def fetch_linescore(game_pk: int) -> dict:
    """The live situation: inning, outs, count, runners, batter/pitcher.
    Short TTL — this is the payload that changes pitch to pitch."""
    return _get_json(f"{STATS_BASE}/game/{game_pk}/linescore",
                     f"mlb_line_{game_pk}.json", ttl=60)


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
def _park_of(sched_game: dict) -> str:
    """Our park key for one schedule entry, or "generic".

    Pulled out of pass 1 so the warm pass below can ask which parks tonight
    needs weather for without re-deriving it differently and warming the
    wrong ones.
    """
    venue = ((sched_game.get("venue") or {}).get("name") or "").lower()
    return next((k for frag, k in VENUE_PARK.items() if frag in venue), "generic")


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

    THE WARM PASSES ARE WHY THIS RETURNS IN UNDER A MINUTE. Measured on the
    production droplet 2026-08-16, this took 7m39s of wall clock against
    effectively zero CPU — it was not computing, it was waiting, one request
    at a time, roughly 600 of them. They are independent of one another, so
    the two ``fetch_many`` waves below ask for them a few at a time and the
    passes that follow read the answers off disk.

    NOTHING BELOW THEM CHANGED, and that is the point. `_get_json` already
    dedupes on the cache file, so a warmed request is a disk read when the
    real pass asks for it again. A warm pass that fails leaves this function
    exactly as correct as it was — and exactly as slow. No projection, no
    price and no prop ordering depends on one.
    """
    season = season or int(date[:4])
    sched = _get_json(
        f"{STATS_BASE}/schedule?sportId=1&date={date}"
        f"&hydrate=probablePitcher,venue",
        f"mlb_schedule_{date}.json", ttl=600)

    # Warm pass A: what the schedule alone already knows how to ask for —
    # one boxscore per game and one forecast per park. Pass 1 below reads
    # both back off disk.
    #
    # THE PROBABLE STARTERS ARE NOT HERE even though their ids are in this
    # payload, and the reason is a doubleheader: props are built for exactly
    # one leg of a pair, so warming both legs' starters costs two game-log
    # requests for a game that is never priced. Which leg wins is not known
    # until the bookkeeping below has run, so the pitchers wait for pass B.
    #
    # `or {}` throughout rather than `.get(k, {})`: this runs before anything
    # else reads the payload, and a warm-up is the last thing that should be
    # first to trip over a null field.
    pks: list = []
    parks: list = []
    for day in (sched.get("dates") or []):
        for g in (day.get("games") or []):
            if g.get("gamePk"):
                pks.append(g["gamePk"])
            park = _park_of(g)
            if park in PARK_COORDS:
                parks.append(park)
    fetch_many(fetch_boxscore, [(pk,) for pk in pks])
    fetch_many(park_weather, [(p,) for p in parks])

    games: list[MLBGame] = []
    props: list[MLBProp] = []
    # Kept, not swallowed — see _add_prop and the check below.
    refusals: list = []

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
            park = _park_of(g)

            pitchers = {}
            for side, ab in (("home", home_ab), ("away", away_ab)):
                pp = teams.get(side, {}).get("probablePitcher")
                if pp:
                    pitchers[ab] = Pitcher(
                        name=pp.get("fullName", "TBD"),
                        throws=pp.get("pitchHand", {}).get("code", "R"))

            # GUARDED, like the boxscore three lines down and like the same
            # call in `mlbstats.build_games` — this one alone was bare, so a
            # single Open-Meteo hiccup raised out of the whole build and
            # `mlb_build.py` exited 2 with no board at all. Fifteen forecasts
            # now leave together, which makes one of them failing likelier
            # rather than rarer.
            weather = None
            if park in PARK_COORDS:
                try:
                    weather = park_weather(park)
                except DataUnavailable:
                    weather = None
            box = {}
            try:
                box = fetch_boxscore(game_pk) if game_pk else {}
            except DataUnavailable:
                box = {}
            # BOTH cards, not just the home one. This flag is the §5 hold on
            # every hitter in the game, and pass 2 below fills an unposted
            # side from `projected_lineup` — last game's order. Reading only
            # the home side meant that the moment the home card posted, every
            # AWAY hitter cleared the gate on a projected spot with nothing
            # official behind it: `lineup_spot != 0` because we guessed it,
            # `lineups_confirmed` True because the other dugout was ready.
            _cards = box.get("teams", {})
            lineups_confirmed = all(
                bool(_cards.get(side, {}).get("battingOrder"))
                for side in ("home", "away"))

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
    # Stamp the schedule's own state onto the game. It was already being read
    # here and then thrown away, so the only consumer that knew whether a
    # game was over was this function. The ingest's "don't store a partial
    # stat line from a game in progress" guard reads g.live, which is filled
    # by attach_live — called only by the site build — so in the ingest it
    # was always None and the guard never fired once. Every in-progress line
    # went into the history DB and the settler graded live bets against it.
    for g, game, *_rest in raw:
        game.sched_state = str(
            (g.get("status", {}) or {}).get("abstractGameState") or "").lower()
    for pair, legs in by_pair.items():
        pg = next((x for x in legs if not finals.get(id(x))), legs[0])
        prop_games.add(id(pg))

    # Warm pass B: the hitters, and the big one — roughly 270 of them on a
    # full slate, one `people` call and one game log each, which is most of
    # what a cold build asks for. Their ids are not in the schedule: they
    # come out of a boxscore, or out of `projected_lineup` when a card has
    # not posted yet, so this is the first moment the list can exist.
    cards: list = []                     # every batting order we will price
    project: list = []                   # the sides that need a guess instead
    arms: list = []                      # the starters we will actually price
    for g, game, box, teams, home, away in raw:
        if id(game) not in prop_games:
            continue
        for side in ("home", "away"):
            entries = parse_lineup(box, side)
            tid = (home if side == "home" else away).get("id")
            if entries:
                cards.append(entries)
            elif tid:
                project.append((tid, date))
            pp = (teams.get(side) or {}).get("probablePitcher")
            if include_pitchers and pp and pp.get("id"):
                arms.append((pp["id"], "pitching", season))
    # `projected_lineup` is the one chain in this build that cannot be
    # flattened — its boxscore request needs the gamePk that its schedule
    # request returns. So it goes into the pool whole: concurrent across
    # teams, sequential within one, which is the shape the dependency has.
    #
    # ITS ANSWER IS THROWN AWAY, deliberately. Pass 2 below calls
    # `projected_lineup` itself, exactly as it always did, and by then both
    # of its requests are on disk — two cache reads. Keeping the real call
    # where it was is what keeps this a warm pass: if this whole block
    # vanished, pass 2 would still project the same lineups off the same
    # feed. Consuming the pooled answer here instead would have made the
    # block load-bearing, and `fetch_many` turns a fault into None — which
    # would have quietly deleted a team's hitters rather than slowing them.
    cards.extend(e for e in fetch_many(projected_lineup, project) if e)

    # `if m in MARKET_GROUP` because an unregistered market must fail where
    # it always failed — in `_add_prop`, with the prop it belongs to — and
    # not here, taking the whole board down before a line is priced.
    groups = sorted({MARKET_GROUP[m] for m in hitter_markets
                     if m in MARKET_GROUP})
    people: list = []
    hit_logs: list = []
    for entries in cards:
        for entry in entries:
            people.append((entry.person_id,))
            for group in groups:
                hit_logs.append((entry.person_id, group, season))
    fetch_many(fetch_person, people)
    fetch_many(fetch_game_log, hit_logs + arms)

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
                              log_limit=limit, game_number=prop_gn,
                              refusals=refusals)

        # Pitcher strikeout props from probable starters.
        if include_pitchers:
            for team_ab, opp_ab in ((home_ab, away_ab), (away_ab, home_ab)):
                pp = teams.get("home" if team_ab == home_ab else "away", {}).get("probablePitcher")
                if not pp:
                    continue
                # Both pitcher markets, from one starter and one game log
                # fetch. Registering OUTS in the market tables was not enough
                # on its own — no prop was ever built for it, so the market
                # existed everywhere except where it had to: on the slate.
                for mkt in (STRIKEOUTS, OUTS):
                    _add_prop(props, pp.get("id"), pp.get("fullName", "TBD"),
                              team_ab, opp_ab, "SP", mkt, season,
                              lineup_spot=1, bats="R",
                              throws=pp.get("pitchHand", {}).get("code", "R"),
                              log_limit=limit, game_number=prop_gn,
                              refusals=refusals)

    # AN EMPTY BOARD THE WIRE REFUSED IS NOT AN EMPTY BOARD. Publishing
    # one looks identical to a quiet slate and reports success, which is
    # how "0 props" reached launch.py's log as a healthy build. A slate
    # with nothing on it AND a wire that said no is a failure, and it
    # says so loudly enough that the caller cannot record it as fine.
    if refusals and not props:
        codes = sorted({str(c) for _, _, c in refusals})
        raise DataUnavailable(
            f"{len(refusals)} game-log request(s) were refused "
            f"(HTTP {', '.join(codes)}) and no prop survived. This is a "
            f"refused board, not a quiet one — publishing it would hide a "
            f"rate limit behind an empty slate. Retry when the wire lets us; "
            f"QB_MLB_WORKERS=1 slows the pool if it keeps happening.",
            status=refusals[0][2])

    return MLBSlate(date=date, games=games, props=props)


#: HTTP statuses that mean "the host refused us", not "there is no such
#: record". A 429 is the wire asking us to slow down and a 5xx is the wire
#: being broken; both come back later with real data, and both used to be
#: indistinguishable here from a rookie with no game log.
REFUSAL_STATUSES = frozenset({429, 500, 502, 503, 504})


def _add_prop(props, person_id, name, team, opp, position, market, season,
              lineup_spot, bats, throws="R", log_limit: int | None = 15,
              game_number: int = 0, refusals: list | None = None):
    if not person_id:
        return
    group = MARKET_GROUP[market]
    try:
        raw = fetch_game_log(person_id, group, season)
        logs = parse_game_log(raw, market, limit=log_limit)
        # The SAME response, uncapped. `career_avg` used to be the mean of
        # the fifteen logs directly above it — the identical sample the
        # form blend was about to weight, so it carried no information the
        # blend did not already have, and MLB_WINDOW_WEIGHTS gave it a
        # weight of zero accordingly. That left nothing anchoring a thin
        # log: a hitter with three quiet games projected at three quiet
        # games, and the live sim gate found several at batting averages
        # under .100 — one at .014.
        #
        # gameLog always returns season-to-date, so the anchor was already
        # in hand and being thrown away. Parsing the cached response a
        # second time costs no request.
        season_logs = parse_game_log(raw, market, limit=None)
    except DataUnavailable as exc:
        # A REFUSAL IS NOT AN ABSENCE. This used to `return` on any
        # DataUnavailable, which made a rate-limited wire look exactly
        # like a slate of players who happen to have no game logs:
        # reproduced with every game log answering 429, the build handed
        # back 15 games and 0 props, raised nothing, and launch.py
        # recorded a successful build over an empty board. Nobody
        # downstream could tell, because by then the information was
        # gone. It is kept now and the caller decides.
        if refusals is not None and getattr(exc, "status", None) in REFUSAL_STATUSES:
            refusals.append((name, market, exc.status))
        return
    if len(logs) < 3:
        return
    recent = [g.value for g in logs[:5]]
    baseline = sum(recent) / len(recent)
    season_vals = [g.value for g in season_logs] or [g.value for g in logs]
    props.append(MLBProp(
        player=name, team=team, opponent=opp, position=position, market=market,
        logs=logs,
        career_avg=round(sum(season_vals) / len(season_vals), 3),
        career_games=len(season_vals),
        vs_pitcher_avg=None,
        lines=[SportsbookLine(book="proxy", line=_proxy_line(baseline, market),
                              over_odds=-110, under_odds=-110)],
        bats=bats, throws=throws, lineup_spot=lineup_spot,
        person_id=int(person_id), game_number=game_number,
        # The field has been on this record since MLB shipped and nothing
        # ever filled it, so every MLB prop drew initials while the id that
        # addresses the photo sat one line above.
        headshot=headshot_url(person_id),
    ))
