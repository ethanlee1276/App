"""Build engine Slates from real nflverse data.

Feed availability from a standard egress environment:

  Reachable now (served from the git tree via raw.githubusercontent.com):
    - schedules  → real games, kickoff weather (roof/temp/wind), spread & total
    - rosters    → player → team / position

  Requires GitHub *release* access (blocked by some egress policies):
    - weekly player stats → per-player game logs and computed defense profiles

The weekly-stats loader tries the nflverse release URLs and, failing that, a CSV
you drop at ``data/cache/player_stats_<season>.csv`` (export it once from
nflverse / nfl_data_py). Everything downstream is identical regardless of source.
"""

from __future__ import annotations

from dataclasses import dataclass

from .fetch import fetch_csv, load_local_csv, CACHE_DIR, DataUnavailable
from ..models import (
    Team, DefenseProfile, Weather, Game, Prop, GameLog, SportsbookLine,
    PASS_YDS, RUSH_YDS, REC_YDS, RECEPTIONS,
)
from ..data_loader import Slate

# --- source URLs ------------------------------------------------------------
SCHEDULES_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
ROSTERS_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/rosters.csv"

# Candidate release URLs for weekly player stats (naming has changed over time).
def _weekly_stats_urls(season: int) -> list[str]:
    base = "https://github.com/nflverse/nflverse-data/releases/download"
    return [
        f"{base}/player_stats/stats_player_week_{season}.csv",
        f"{base}/player_stats/player_stats_{season}.csv",
        f"{base}/player_stats/player_stats_{season}.csv.gz",
    ]


# Which stat column feeds each market, with fallbacks across schema versions.
MARKET_COLUMNS = {
    PASS_YDS: ("passing_yards",),
    RUSH_YDS: ("rushing_yards",),
    REC_YDS: ("receiving_yards",),
    RECEPTIONS: ("receptions",),
}


def _f(row: dict, *keys, default=0.0) -> float:
    for k in keys:
        v = row.get(k)
        if v not in (None, "", "NA"):
            try:
                return float(v)
            except ValueError:
                pass
    return default


def _s(row: dict, *keys, default="") -> str:
    for k in keys:
        v = row.get(k)
        if v not in (None, "", "NA"):
            return v
    return default


# --- schedules & weather ----------------------------------------------------
def load_schedules() -> list[dict]:
    return fetch_csv(SCHEDULES_URL, "games.csv")


def weather_from_row(row: dict) -> Weather:
    """Map an nflverse game row to the engine's Weather.

    roof ∈ {dome, closed, outdoors, open}. dome/closed are climate-controlled;
    outdoors/open use the reported temp and wind (often blank for fair days).
    nflverse schedules carry no precipitation, so rain/snow default to False —
    wire a weather API for precip in a later phase.
    """
    roof = _s(row, "roof").lower()
    if roof in ("dome", "closed"):
        return Weather(dome=True, temp_f=70.0, wind_mph=0.0)
    temp = _f(row, "temp", default=60.0)
    wind = _f(row, "wind", default=6.0)
    return Weather(dome=False, temp_f=temp, wind_mph=wind)


def build_games(season: int, week: int) -> list[Game]:
    """Real games for a season/week with weather, spread and total.

    nflverse ``spread_line`` is positive when the *home* team is favored; the
    engine's ``Game.spread`` is negative when home is favored, so we negate.
    """
    games = []
    for r in load_schedules():
        if _s(r, "season") != str(season) or _s(r, "week") != str(week):
            continue
        games.append(Game(
            home=_s(r, "home_team"),
            away=_s(r, "away_team"),
            weather=weather_from_row(r),
            injuries=[],  # injury feed is a separate (release-gated) source
            spread=-_f(r, "spread_line"),
            total=_f(r, "total_line", default=44.0),
            roof=_s(r, "roof"),
            surface=_s(r, "surface", default="grass"),
        ))
    return games


# --- weekly player stats ----------------------------------------------------
def load_weekly_stats(season: int) -> list[dict]:
    """Weekly player stats for a season, from release URLs or a local CSV."""
    local = CACHE_DIR / f"player_stats_{season}.csv"
    if local.exists():
        return load_local_csv(local)

    last_err = None
    for url in _weekly_stats_urls(season):
        try:
            return fetch_csv(url, f"player_stats_{season}.csv")
        except DataUnavailable as exc:
            last_err = exc
    raise DataUnavailable(
        f"Weekly player stats for {season} are unavailable here (GitHub release "
        f"access is blocked by this environment's egress policy). Export them "
        f"once and save to {local} — e.g. in Python:\n"
        f"    import nfl_data_py as nfl\n"
        f"    nfl.import_weekly_data([{season}]).to_csv('{local}', index=False)\n"
        f"(last error: {last_err})"
    )


def _regular_season(rows: list[dict]) -> list[dict]:
    return [r for r in rows if _s(r, "season_type", "game_type", default="REG") in ("REG", "")]


def player_game_logs(rows: list[dict], player: str, market: str,
                     upto_week: int) -> list[GameLog]:
    """Most-recent-first game logs for one player and market."""
    cols = MARKET_COLUMNS[market]
    out = []
    for r in rows:
        name = _s(r, "player_display_name", "player_name", "full_name")
        if name != player:
            continue
        wk = int(_f(r, "week", default=0))
        if wk <= 0 or wk >= upto_week:
            continue
        out.append(GameLog(
            week=wk,
            opponent=_s(r, "opponent_team", "opponent"),
            value=_f(r, *cols),
            home=True,
        ))
    out.sort(key=lambda g: g.week, reverse=True)
    return out


def career_average(rows: list[dict], player: str, market: str) -> float:
    cols = MARKET_COLUMNS[market]
    vals = [
        _f(r, *cols) for r in rows
        if _s(r, "player_display_name", "player_name", "full_name") == player
    ]
    return sum(vals) / len(vals) if vals else 0.0


# --- defensive profiles (yards allowed vs league average) -------------------
def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def build_defense_profiles(rows: list[dict], upto_week: int) -> dict[str, DefenseProfile]:
    """Aggregate what each defense allows per game, relative to league average.

    A value > 1.0 means the defense is more generous than average (good for the
    offense). Built from weekly box scores keyed on ``opponent_team``.
    """
    rows = [r for r in _regular_season(rows) if 0 < int(_f(r, "week", default=0)) < upto_week]

    # allowed[team][bucket] = list of per-player-week values conceded
    buckets = ("qb_pass", "wr_rec", "te_rec", "rb_rush", "rb_recv")
    allowed: dict[str, dict[str, list[float]]] = {}

    for r in rows:
        deff = _s(r, "opponent_team", "opponent")
        if not deff:
            continue
        pos = _s(r, "position", "position_group").upper()
        d = allowed.setdefault(deff, {b: [] for b in buckets})
        if pos == "QB":
            d["qb_pass"].append(_f(r, "passing_yards"))
        if pos == "WR":
            d["wr_rec"].append(_f(r, "receiving_yards"))
        if pos == "TE":
            d["te_rec"].append(_f(r, "receiving_yards"))
        if pos == "RB":
            d["rb_rush"].append(_f(r, "rushing_yards"))
            d["rb_recv"].append(_f(r, "receiving_yards"))

    # League averages per bucket (mean of each team's mean-allowed).
    team_means = {
        team: {b: _mean(vals[b]) for b in buckets}
        for team, vals in allowed.items()
    }
    league = {b: _mean([tm[b] for tm in team_means.values()]) for b in buckets}

    def factor(team: str, b: str) -> float:
        base = league[b]
        return (team_means[team][b] / base) if base > 0 else 1.0

    # Rank teams by rush yards allowed to RBs (1 = toughest, 32 = softest).
    rush_order = sorted(team_means, key=lambda t: team_means[t]["rb_rush"])
    rush_rank = {t: i + 1 for i, t in enumerate(rush_order)}

    profiles = {}
    for team in team_means:
        wr = factor(team, "wr_rec")
        profiles[team] = DefenseProfile(
            team=team,
            vs_qb=factor(team, "qb_pass"),
            vs_wr1=wr, vs_wr2=wr, vs_slot=wr,   # no alignment split in box scores
            vs_te=factor(team, "te_rec"),
            vs_rb_rush=factor(team, "rb_rush"),
            vs_rb_recv=factor(team, "rb_recv"),
            rush_rank=rush_rank.get(team, 16),
            pass_rank=16,
        )
    return profiles


# --- slate assembly ---------------------------------------------------------
# Default markets to build per position when auto-selecting players.
POSITION_MARKETS = {
    "QB": [(PASS_YDS, "starter")],
    "RB": [(RUSH_YDS, "rb1")],
    "WR": [(REC_YDS, "wr1")],
    "TE": [(RECEPTIONS, "te")],
}


def _round_half(x: float) -> float:
    return round(x * 2) / 2.0


def _recent_mean(logs: list[GameLog], n: int = 5) -> float:
    vals = [g.value for g in logs[:n]]
    return sum(vals) / len(vals) if vals else 0.0


@dataclass
class PlayerSpec:
    player: str
    market: str
    usage_role: str


def top_players_for_week(rows: list[dict], teams: set[str], upto_week: int,
                         per_team: int = 3) -> list[PlayerSpec]:
    """Auto-pick this week's likely prop players: the highest-volume skill guys
    on each participating team from the season so far."""
    prior = [r for r in _regular_season(rows) if 0 < int(_f(r, "week", default=0)) < upto_week]

    # Aggregate a simple opportunity volume per player to rank starters.
    agg: dict[tuple, dict] = {}
    for r in prior:
        team = _s(r, "recent_team", "team")
        if team not in teams:
            continue
        pos = _s(r, "position", "position_group").upper()
        if pos not in POSITION_MARKETS:
            continue
        name = _s(r, "player_display_name", "player_name", "full_name")
        if not name:
            continue
        key = (team, pos, name)
        a = agg.setdefault(key, {"vol": 0.0, "games": 0})
        a["vol"] += _f(r, "attempts") + _f(r, "carries") + _f(r, "targets")
        a["games"] += 1

    specs: list[PlayerSpec] = []
    for team in teams:
        for pos, markets in POSITION_MARKETS.items():
            cands = [(k, v) for k, v in agg.items() if k[0] == team and k[1] == pos]
            cands.sort(key=lambda kv: kv[1]["vol"], reverse=True)
            take = 1 if pos in ("QB",) else per_team
            for (t, p, name), _v in cands[:take]:
                for market, role in markets:
                    specs.append(PlayerSpec(name, market, role))
    return specs


def build_slate(season: int, week: int, upto_week: int | None = None,
                specs: list[PlayerSpec] | None = None) -> Slate:
    """Assemble a real Slate for a season/week.

    Requires weekly stats (for game logs and defense profiles). Since nflverse
    carries no player-prop lines, each prop gets a *proxy* line at the player's
    recent-form baseline, so the pipeline surfaces how far the matchup/weather/
    injury model moves the projection off that baseline. Swap in an odds feed to
    price against real books.
    """
    upto_week = upto_week or week
    games = build_games(season, week)
    if not games:
        raise DataUnavailable(f"No scheduled games found for {season} week {week}.")

    stats = load_weekly_stats(season)
    defenses = build_defense_profiles(stats, upto_week)

    participating = {g.home for g in games} | {g.away for g in games}
    opponent_of = {}
    for g in games:
        opponent_of[g.home] = g.away
        opponent_of[g.away] = g.home

    if specs is None:
        specs = top_players_for_week(stats, participating, upto_week)

    def team_of(player: str) -> str:
        for r in stats:
            if _s(r, "player_display_name", "player_name", "full_name") == player:
                return _s(r, "recent_team", "team")
        return ""

    # Official headshot URLs, when the stats feed carries them.
    headshots: dict[str, str] = {}
    for r in stats:
        url = _s(r, "headshot_url", "headshot")
        if url:
            headshots.setdefault(
                _s(r, "player_display_name", "player_name", "full_name"), url)

    props: list[Prop] = []
    for spec in specs:
        team = team_of(spec.player)
        if team not in opponent_of:
            continue
        logs = player_game_logs(stats, spec.player, spec.market, upto_week)
        if len(logs) < 3:
            continue  # not enough history to project
        baseline = _recent_mean(logs)
        if baseline <= 0:
            continue
        line = _round_half(baseline) - 0.5  # a touch under baseline, like a book
        pos = {PASS_YDS: "QB", RUSH_YDS: "RB", REC_YDS: "WR", RECEPTIONS: "TE"}[spec.market]
        props.append(Prop(
            player=spec.player,
            team=team,
            opponent=opponent_of[team],
            position=pos,
            market=spec.market,
            logs=logs,
            career_avg=career_average(stats, spec.player, spec.market),
            vs_opponent_avg=None,
            lines=[SportsbookLine(book="proxy", line=line, over_odds=-110, under_odds=-110)],
            usage_role=spec.usage_role,
            headshot=headshots.get(spec.player, ""),
        ))

    # Teams dict for every participating side, using computed or neutral defense.
    teams: dict[str, Team] = {}
    for abbr in participating:
        teams[abbr] = Team(
            abbr=abbr,
            name=abbr,
            defense=defenses.get(abbr, DefenseProfile(team=abbr)),
        )

    return Slate(date=f"{season}-W{week:02d}", teams=teams, games=games, props=props)
