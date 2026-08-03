"""What the season simulator needs, assembled from free sources.

``engine.futures`` is deliberately pure — ratings in, fixtures in,
probabilities out, no I/O and no network. This is the layer that goes and
gets them, one adapter per league, all of it keyless: statsapi for MLB, the
NBA's own CDN, nflverse for the NFL, ESPN for college football. Nothing
here touches the Odds API, so a futures board can be rebuilt as often as
anyone likes for nothing.

THE RATINGS PROBLEM, WHICH IS THE WHOLE PROBLEM IN AUGUST
---------------------------------------------------------
A simulation is only as good as the ratings it plays with, and in the
preseason there are no games this year to rate anybody on. Three of these
four leagues are in exactly that state right now.

So ratings are an explicit blend of this season and last, weighted by how
much of this season exists:

    w = played / (played + PRIOR_GAMES[sport])

At zero games that is 100% last season — a prior, and reported as one. By
the time a league has played PRIOR_GAMES it is half and half, and it keeps
tilting from there. The prior is also decayed by PRIOR_DECAY before it is
mixed in, because a team is not the team it was last year: rosters turn
over, and the further the model leans on last season the more it should
regress toward the middle rather than trusting a stale number at full
strength.

PRIOR_GAMES is per sport because a game means a different amount in each.
Twelve NFL games is most of a season; twelve MLB games is a fortnight.
"""

from __future__ import annotations

import datetime as _dt

from .futures import Fixture
from .seasons import season_of
from .teamrates import compute_team_ratings

#: Games after which this season and last carry equal weight.
PRIOR_GAMES = {"nfl": 6, "cfb": 5, "mlb": 40, "nba": 20, "wnba": 12}

#: How much of last season's rating survives into the prior. Rosters turn
#: over; leaning on a stale number at full strength is how a preseason
#: board ends up confidently wrong about a team that lost half its starters.
PRIOR_DECAY = 0.75


def blended_ratings(conn, sport: str, season: int) -> tuple[dict, float, int]:
    """(ratings, prior share, games played this season).

    Returns the prior share alongside the numbers so a caller can say how
    much of its own board is last year's opinion.
    """
    this = compute_team_ratings(conn, sport, seasons=[season])
    prior = compute_team_ratings(conn, sport, seasons=[season - 1])
    played = sum(r.games for r in this.values()) // 2 or 0
    k = PRIOR_GAMES.get(sport, 10)
    w = played / (played + k) if (played + k) else 0.0
    out: dict[str, float] = {}
    for team in set(this) | set(prior):
        a = this[team].net if team in this else 0.0
        b = (prior[team].net * PRIOR_DECAY) if team in prior else 0.0
        out[team] = w * a + (1.0 - w) * b
    return out, round(1.0 - w, 3), played


def records(conn, sport: str, season: int, conferences: dict | None = None
            ) -> dict[str, tuple[int, int]]:
    """``{team: (wins, losses)}`` for the regular season so far."""
    from . import standings
    try:
        table = standings.compute(conn, sport, season=season,
                                  conferences=conferences)
    except Exception:
        return {}
    out: dict[str, tuple[int, int]] = {}
    for group in table.get("groups", []) or []:
        for row in group.get("rows", []) or []:
            t = row.get("team")
            if t:
                out[t] = (int(row.get("wins", 0)), int(row.get("losses", 0)))
    return out


# --- remaining fixtures, one adapter per league -----------------------------
def _mlb_fixtures(season: int) -> list[Fixture]:
    """Every MLB game not yet final, from the one ranged statsapi call the
    results ingest already uses."""
    from .mlb.sources.mlbstats import TEAM_ID_ABBR, fetch_schedule
    lo, hi = f"{season}-03-01", f"{season}-11-15"
    try:
        payload = fetch_schedule(lo, hi)
    except Exception:
        return []
    out = []
    for day in payload.get("dates", []) or []:
        for g in day.get("games", []) or []:
            st = (g.get("status", {}) or {})
            if (st.get("abstractGameState") or "") == "Final":
                continue
            # Postponed and cancelled fixtures will never be played, so they
            # are not "remaining" — counting them would hand every team a
            # few phantom games and inflate its projected wins.
            if (st.get("codedGameState") or "") in {"C", "D", "T", "postponed"}:
                continue
            teams = g.get("teams", {}) or {}
            h = (teams.get("home", {}) or {}).get("team", {}) or {}
            a = (teams.get("away", {}) or {}).get("team", {}) or {}
            home = TEAM_ID_ABBR.get(h.get("id"), h.get("abbreviation", ""))
            away = TEAM_ID_ABBR.get(a.get("id"), a.get("abbreviation", ""))
            if home and away:
                out.append(Fixture(home, away))
    return out


def _nba_fixtures(season: int) -> list[Fixture]:
    from .sources.nbadata import fetch_schedule
    try:
        sched = fetch_schedule()
    except Exception:
        return []
    out = []
    for day in (sched.get("leagueSchedule", {}) or {}).get("gameDates", []) or []:
        for g in day.get("games", []) or []:
            if int(g.get("gameStatus", 1) or 1) == 3:       # 3 = final
                continue
            home = (g.get("homeTeam", {}) or {}).get("teamTricode", "")
            away = (g.get("awayTeam", {}) or {}).get("teamTricode", "")
            if home and away:
                out.append(Fixture(home, away))
    return out


def _nfl_fixtures(season: int) -> list[Fixture]:
    """nflverse carries the whole season including unplayed weeks; a game
    with no home score has not been played."""
    from .sources.nflverse import load_schedules
    try:
        rows = load_schedules()
    except Exception:
        return []
    out = []
    for r in rows:
        if str(r.get("season", "")).strip() != str(season):
            continue
        if str(r.get("game_type", "REG")).strip().upper() != "REG":
            continue
        if str(r.get("home_score", "")).strip() not in ("", "NA", "None"):
            continue
        home, away = str(r.get("home_team", "")), str(r.get("away_team", ""))
        if home and away:
            out.append(Fixture(home, away))
    return out


def _cfb_fixtures(season: int) -> list[Fixture]:
    """College football has no static conference map and no single season
    payload, so this walks the ESPN scoreboard across the season window.

    Deliberately the coarsest of the four. 134 programs realigning every
    summer means an unplayed-fixture list is the least reliable input here,
    and the page should lean on projected record rather than on a title
    number built from it.
    """
    from .sources import cfbdata
    lo = f"{season}-08-20"
    hi = f"{season}-12-15"
    try:
        games = cfbdata.load_range(lo, hi)
    except Exception:
        return []
    out = []
    for g in games:
        if g.get("home_score") is not None and g.get("away_score") is not None:
            continue
        home, away = g.get("home", ""), g.get("away", "")
        if home and away:
            out.append(Fixture(home, away))
    return out


FIXTURES = {"mlb": _mlb_fixtures, "nba": _nba_fixtures,
            "nfl": _nfl_fixtures, "cfb": _cfb_fixtures}


def build(conn, sport: str, season: int | None = None,
          conferences: dict | None = None) -> dict:
    """Everything ``futures.simulate`` needs, plus how much to trust it.

    Never raises. A futures board is an extra on every page it appears on,
    and a feed that is down must not take the sport with it — the caller
    gets an empty fixture list and a note saying why, which renders as "no
    projection" rather than as a broken page.
    """
    day = _dt.date.today().isoformat()
    season = season if season is not None else season_of(sport, day)
    ratings, prior_share, played = blended_ratings(conn, sport, season)
    recs = records(conn, sport, season, conferences=conferences)
    try:
        fixtures = FIXTURES.get(sport, lambda _s: [])(season)
    except Exception as exc:                       # noqa: BLE001
        return {"sport": sport, "season": season, "ratings": ratings,
                "records": recs, "fixtures": [], "prior_share": prior_share,
                "games_played": played,
                "note": f"schedule feed unavailable: {exc}"}
    note = ""
    if not fixtures:
        note = ("no unplayed games found — the season is over, or its "
                "schedule is not published yet")
    elif prior_share >= 0.99:
        note = ("preseason: every rating here is last season's, decayed. "
                "This is a prior, not a projection")
    elif prior_share >= 0.5:
        note = (f"{prior_share:.0%} of these ratings is still last season — "
                f"only {played} game(s) played")
    return {"sport": sport, "season": season, "ratings": ratings,
            "records": recs, "fixtures": fixtures,
            "prior_share": prior_share, "games_played": played, "note": note}


#: Fewest games a player needs this season before his rate is used at all.
#: Below it the sample is one hot week, and a season projection built on a
#: hot week is the most confident wrong number this module could produce.
MIN_GAMES_FOR_RATE = 8

#: How many of the team's remaining games a player is assumed available
#: for, when we have no injury feed to say otherwise. Taken from his own
#: appearance rate so far — which is the honest estimate, since a player
#: who has already missed a third of the year is telling us something.
DEFAULT_AVAILABILITY = 0.92


def player_season_totals(conn, sport: str, market: str, season: int | None = None,
                         team_games_left: dict | None = None,
                         lines: dict | None = None, limit: int = 40) -> list[dict]:
    """Projected season totals for one market, best first.

    ``team_games_left`` {team: games} comes from the same fixture list the
    season simulation uses, so a player's remaining games and his team's
    remaining games can never disagree.

    ``lines`` {player: number} attaches a P(over) where a line is known.
    Without one the projection still stands on its own — "48 home runs,
    give or take 6" is a claim worth publishing with no market attached,
    which is the whole point of doing this from the schedule rather than
    from a price.
    """
    from .futures import season_total
    day = _dt.date.today().isoformat()
    season = season if season is not None else season_of(sport, day)
    rows = conn.execute(
        "SELECT player, team, COUNT(*) n, SUM(value) tot, "
        "AVG(value) avg_v, AVG(value*value) avg_sq "
        "FROM player_game_logs WHERE sport=? AND season=? AND market=? "
        "GROUP BY player, team", (sport, season, market)).fetchall()
    left = team_games_left or {}
    # A team's games so far, so availability is measured against the games
    # the player COULD have played rather than against a season length.
    played = {t: n for t, n in conn.execute(
        "SELECT team, COUNT(DISTINCT period || game_id) FROM player_game_logs "
        "WHERE sport=? AND season=? GROUP BY team", (sport, season))}
    out = []
    for r in rows:
        n = int(r["n"] or 0)
        if n < MIN_GAMES_FOR_RATE:
            continue
        mu = float(r["avg_v"] or 0.0)
        var = max(0.0, float(r["avg_sq"] or 0.0) - mu * mu)
        team = r["team"] or ""
        team_n = played.get(team, 0)
        avail = (min(1.0, n / team_n) if team_n else DEFAULT_AVAILABILITY)
        st = season_total(banked=float(r["tot"] or 0.0), per_game=mu,
                          per_game_sd=var ** 0.5,
                          games_left=int(left.get(team, 0)),
                          availability=avail,
                          line=(lines or {}).get(r["player"]))
        st.player, st.team, st.market = r["player"], team, market
        st.games_played = n
        out.append(st.as_dict())
    out.sort(key=lambda d: -d["mean"])
    return out[:limit]


def games_left_by_team(fixtures: list) -> dict:
    """{team: remaining games} from the same fixture list the simulation
    plays, so the two halves of a futures board cannot disagree about how
    much season is left."""
    out: dict[str, int] = {}
    for f in fixtures:
        out[f.home] = out.get(f.home, 0) + 1
        out[f.away] = out.get(f.away, 0) + 1
    return out


def project(conn, sport: str, season: int | None = None, trials: int = 20000,
            conferences: dict | None = None) -> dict:
    """Build the inputs and run the season. The one call a builder needs."""
    from .futures import simulate
    data = build(conn, sport, season=season, conferences=conferences)
    out = simulate(sport, data["ratings"], data["records"], data["fixtures"],
                   trials=trials)
    out.update(season=data["season"], note=data["note"],
               prior_share=data["prior_share"],
               games_played=data["games_played"],
               fixtures_remaining=len(data["fixtures"]))
    return out
