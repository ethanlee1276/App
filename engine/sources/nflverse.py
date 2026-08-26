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

from .fetch import (fetch_csv, load_local_csv, CACHE_DIR, DataUnavailable,
                    release_unavailable)
from .. import carry as _carry
from ..models import (
    Team, DefenseProfile, Weather, Game, Prop, GameLog, SportsbookLine,
    PASS_YDS, RUSH_YDS, REC_YDS, RECEPTIONS, ANYTIME_TD,
)
from ..data_loader import Slate

# --- source URLs ------------------------------------------------------------
SCHEDULES_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
ROSTERS_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/rosters.csv"

# Candidate release URLs for weekly player stats (naming has changed over time).
def _weekly_stats_urls(season: int) -> list[str]:
    base = "https://github.com/nflverse/nflverse-data/releases/download"
    return [
        # nflverse restructured releases: current seasons (2025+) live under
        # the stats_player tag with the new file naming. Verified live.
        f"{base}/stats_player/stats_player_week_{season}.csv",
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

#: How many games a touchdown log is topped up to from the PRIOR season
#: when the carry is on. Ten, because that is where the TD model's blend
#: weight saturates (w = samples/10, ceiling 0.7 — see
#: engine/touchdowns.historical_td_rate): past ten carried games the
#: model would not trust the sample any harder, so hauling a whole
#: seventeen-game season across the boundary buys nothing. The top-up
#: fires only while the CURRENT sample is thin (under the TD model's own
#: caveat line): three real games and a topped history through week 3,
#: then the season stands on its own — the same stand-down discipline
#: the yardage carry keeps.
TD_CARRY_GAMES = 10
from ..touchdowns import TD_THIN_GAMES as _TD_THIN  # noqa: E402


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
    outdoors/open use the reported temp and wind, which nflverse fills from
    the played game — so they are blank on every forward board and the
    result is flagged unmeasured rather than dressed as a forecast.
    nflverse schedules carry no precipitation, so rain/snow default to False —
    wire a weather API for precip in a later phase.
    """
    roof = _s(row, "roof").lower()
    if roof in ("dome", "closed"):
        # Climate control is a fact about the building, known in advance.
        return Weather(dome=True, temp_f=70.0, wind_mph=0.0, measured=True)
    # BLANK MEANS UNPLAYED, NOT FAIR. The docstring above used to read
    # "often blank for fair days", and that is a misreading of the feed:
    # nflverse fills these columns from the game's OWN box score, so an
    # outdoor game that has not kicked off yet is blank every time. The
    # defaults are kept — the pricing paths need a number and a mild day
    # is the right prior — but they are flagged as the prior they are,
    # so the card stops printing "60° · 6mph" as a forecast and the
    # journal stops recording a constant as the wind a bet was made in.
    have_temp = _s(row, "temp") != ""
    have_wind = _s(row, "wind") != ""
    temp = _f(row, "temp", default=60.0)
    wind = _f(row, "wind", default=6.0)
    return Weather(dome=False, temp_f=temp, wind_mph=wind,
                   measured=bool(have_temp or have_wind))


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
            date=_s(r, "gameday"),
            kickoff=_s(r, "gametime"),
            spread=-_f(r, "spread_line"),
            total=_f(r, "total_line", default=44.0),
            roof=_s(r, "roof"),
            surface=_s(r, "surface", default="grass"),
            # Rest days come precomputed in the feed, which is better than
            # deriving them: nflverse already accounts for byes, holiday
            # games and the season opener.
            home_rest=int(_f(r, "home_rest", default=0)),
            away_rest=int(_f(r, "away_rest", default=0)),
            neutral_site=_s(r, "location").lower() == "neutral",
        ))
    return games


# --- snap counts ------------------------------------------------------------
def _snap_urls(season: int) -> list[str]:
    base = "https://github.com/nflverse/nflverse-data/releases/download/snap_counts"
    return [f"{base}/snap_counts_{season}.csv.gz",
            f"{base}/snap_counts_{season}.csv"]


def load_snap_counts(season: int) -> list[dict]:
    """Per-player offensive snap shares — the cleanest measured-role signal
    the volume stats can't provide (a back can have 8 carries on 70% of
    snaps or on 20%, and those are different players to bet on)."""
    local = CACHE_DIR / f"snap_counts_{season}.csv"
    if local.exists():
        return load_local_csv(local)
    last_err = None
    for url in _snap_urls(season):
        try:
            return fetch_csv(url, f"snap_counts_{season}.csv")
        except DataUnavailable as exc:
            last_err = exc
    raise last_err or DataUnavailable(f"snap counts {season} unavailable")


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

    # 404 and "could not reach it" need opposite responses — see
    # `release_unavailable`. This used to assert the egress cause for both,
    # and told Ethan to export a file that does not exist yet.
    raise release_unavailable(
        "weekly player stats", season, local,
        f"nfl.import_weekly_data([{season}]).to_csv('{local}', index=False)",
        _weekly_stats_urls(season), last_err)


def _roster_urls(season: int) -> list[str]:
    base = "https://github.com/nflverse/nflverse-data/releases/download"
    return [f"{base}/rosters/roster_{season}.csv",
            f"{base}/rosters/roster_{season}.csv.gz"]


def load_rosters(season: int) -> list[dict]:
    """Who is on which team THIS season, before a snap has been played.

    The one feed that exists for a season that has not started — unlike
    weekly stats, which cannot exist until there are games. That is what
    makes the prior-season carry possible at all: the carry supplies the
    numbers, the roster supplies the team those numbers now belong to.

    Note this is NOT ``ROSTERS_URL`` (nfldata/rosters.csv), which stops at
    2019 and would silently return nothing for a current season.
    """
    local = CACHE_DIR / f"roster_{season}.csv"
    if local.exists():
        return load_local_csv(local)
    last_err = None
    for url in _roster_urls(season):
        try:
            return fetch_csv(url, f"roster_{season}.csv")
        except DataUnavailable as exc:
            last_err = exc
    raise DataUnavailable(
        f"Rosters for {season} are unavailable here. Export them once and "
        f"save to {local} — e.g. in Python:\n"
        f"    import nfl_data_py as nfl\n"
        f"    nfl.import_seasonal_rosters([{season}]).to_csv('{local}', "
        f"index=False)\n(last error: {last_err})"
    )


def roster_index(season: int) -> dict[str, dict]:
    """``{player: {team, position, status}}`` for the active roster.

    Only ACT survives: a player on reserve or already cut should not have
    a prop built for him off last season's numbers.
    """
    out: dict[str, dict] = {}
    for r in load_rosters(season):
        name = _s(r, "full_name", "player_name", "football_name")
        status = _s(r, "status").upper()
        if not name or (status and status != "ACT"):
            continue
        out[name] = {"team": _s(r, "team"),
                     "position": _s(r, "position", "depth_chart_position"),
                     "status": status,
                     # The roster is where a CURRENT-season face comes from.
                     # `build_slate` used to read headshots only out of the
                     # weekly stats, which do not exist until games have been
                     # played — so on a Week 1 board the only faces were
                     # whatever last season happened to carry. Measured on
                     # 2026: 2,816 roster players have a headshot and 1,071
                     # of them appear in no 2025 stat row, which is every
                     # rookie and every practice-squad promotion.
                     "headshot": _s(r, "headshot_url", "headshot")}
    return out


def headshot_map(season: int) -> dict[str, str]:
    """``{player: headshot_url}`` for everyone the roster file knows.

    Unlike ``roster_index`` this keeps EVERY status — a face on the usage
    board does not stop being his face because he moved to IR. Faces are
    polish, so an unreachable roster file is an empty map, not an error."""
    out: dict[str, str] = {}
    try:
        rows = load_rosters(season)
    except DataUnavailable:
        return out
    for r in rows:
        name = _s(r, "full_name", "player_name", "football_name")
        url = _s(r, "headshot_url", "headshot")
        if name and url:
            out.setdefault(name, url)
    return out


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


def td_game_logs(rows: list[dict], player: str, upto_week: int) -> list[GameLog]:
    """Most-recent-first touchdowns-per-game logs (rushing + receiving).

    Its own helper rather than a MARKET_COLUMNS entry because the value is
    a SUM of two columns — ``_f`` reads the first present key, so listing
    both there would silently return rushing TDs alone. The touchdown
    model blends these against the position baseline by sample size
    (engine/touchdowns.historical_td_rate), so short early-season logs
    are handled there, not here.
    """
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
            value=_f(r, "rushing_tds", default=0.0)
            + _f(r, "receiving_tds", default=0.0),
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


#: Fewest same-season games that can carry a projection on their own. Below
#: it the prior season is topped up in, when the carry is enabled.
MIN_LOGS = 3


def _carry_specs(prior_rows: list[dict], roster: dict[str, dict],
                 teams: set[str], per_team: int = 3) -> list[PlayerSpec]:
    """Who to build props for when the current season has no volume yet.

    Same ranking as ``top_players_for_week`` — highest opportunity volume
    per team and position — but read off the PRIOR season and filed under
    the player's CURRENT team, which is the whole difference. Ranking a
    traded receiver against his old team-mates would put him on the wrong
    board and leave his new team a man short.

    No ``upto_week`` here, unlike ``top_players_for_week``: the prior season
    is over, so there is no cut-off to respect and every week of it counts.
    """
    agg: dict[tuple, dict] = {}
    for r in _regular_season(prior_rows):
        name = _s(r, "player_display_name", "player_name", "full_name")
        entry = roster.get(name)
        if not name or not entry:
            continue
        team = entry.get("team") or ""
        if team not in teams:
            continue
        pos = (entry.get("position") or "").upper()
        if pos not in POSITION_MARKETS:
            continue
        a = agg.setdefault((team, pos, name), {"vol": 0.0})
        a["vol"] += _f(r, "attempts") + _f(r, "carries") + _f(r, "targets")

    specs: list[PlayerSpec] = []
    for team in teams:
        for pos, markets in POSITION_MARKETS.items():
            cands = [(k, v) for k, v in agg.items()
                     if k[0] == team and k[1] == pos]
            cands.sort(key=lambda kv: kv[1]["vol"], reverse=True)
            take = 1 if pos in ("QB",) else per_team
            for (_t, _p, name), _v in cands[:take]:
                for market, role in markets:
                    specs.append(PlayerSpec(name, market, role))
    return specs


def _merge_specs(primary: list[PlayerSpec],
                 extra: list[PlayerSpec]) -> list[PlayerSpec]:
    """``primary`` wins on any (player, market) it already covers.

    The current season is always the better evidence when it exists, so a
    mid-season call keeps its own ranking and the carry only fills gaps.
    """
    seen = {(s.player, s.market) for s in primary}
    return list(primary) + [s for s in extra
                            if (s.player, s.market) not in seen]


def build_slate(season: int, week: int, upto_week: int | None = None,
                specs: list[PlayerSpec] | None = None,
                carry: bool = False, report: dict | None = None) -> Slate:
    """Assemble a real Slate for a season/week.

    Requires weekly stats (for game logs and defense profiles). Since nflverse
    carries no player-prop lines, each prop gets a *proxy* line at the player's
    recent-form baseline, so the pipeline surfaces how far the matchup/weather/
    injury model moves the projection off that baseline. Swap in an odds feed to
    price against real books.

    ``carry`` tops a thin log up from the PREVIOUS season, which is the only
    way weeks 1-3 produce anything at all: they hold 0, 1 and 2 prior games
    against a floor of ``MIN_LOGS``, so without it the prop board is empty
    until week 4. See engine/carry.py for what was measured before it was
    built. ``report`` is filled in with what was carried, for the cards.
    """
    upto_week = upto_week or week
    games = build_games(season, week)
    if not games:
        raise DataUnavailable(f"No scheduled games found for {season} week {week}.")

    # A season that has not started has no weekly stats and cannot — the
    # file 404s because the games have not been played. That is the exact
    # case the carry exists for, so it is survivable rather than fatal.
    try:
        stats = load_weekly_stats(season)
    except DataUnavailable:
        if not carry:
            raise
        stats = []
    defenses = build_defense_profiles(stats, upto_week)

    participating = {g.home for g in games} | {g.away for g in games}
    opponent_of = {}
    for g in games:
        opponent_of[g.home] = g.away
        opponent_of[g.away] = g.home

    prior_stats: list[dict] = []
    roster: dict[str, dict] = {}
    index: dict = {}
    pos_means: dict[str, dict[str, float]] = {}
    if carry:
        try:
            prior_stats = load_weekly_stats(season - 1)
            roster = roster_index(season)
        except DataUnavailable:
            prior_stats, roster = [], {}
        if prior_stats and roster:
            index = _carry.build_index(prior_stats, roster,
                                       load_schedules(), season)
            for market in MARKET_COLUMNS:
                pos_means[market] = _carry.positional_means(prior_stats, market)

    if specs is None:
        specs = top_players_for_week(stats, participating, upto_week)
        if carry and index:
            specs = _merge_specs(specs, _carry_specs(
                prior_stats, roster, participating))

    def team_of(player: str) -> str:
        for r in stats:
            if _s(r, "player_display_name", "player_name", "full_name") == player:
                return _s(r, "recent_team", "team")
        # The roster is the authority for a season with no games yet, and
        # the ONLY place a player who changed teams is on the new one.
        return (roster.get(player) or {}).get("team", "")

    # Official headshot URLs. THREE sources, in the order a face is most
    # likely to be current: this season's stats, then the roster, then last
    # season's stats — a face does not go stale over one offseason, so an
    # older one beats none.
    #
    # The roster is the load-bearing addition and the reason this was thin.
    # Weekly stats do not exist until games have been played, so on a Week 1
    # board the first source is empty and everything fell through to last
    # season — which has no row at all for a rookie or a practice-squad
    # promotion. Measured on 2026: the roster carries 2,816 faces and 1,071
    # of those players appear in no 2025 stat row. They were drawing the
    # initials avatar with a real photograph sitting in a file already on
    # disk.
    headshots: dict[str, str] = {}
    for r in list(stats):
        url = _s(r, "headshot_url", "headshot")
        if url:
            headshots.setdefault(
                _s(r, "player_display_name", "player_name", "full_name"), url)
    for name, row in roster.items():
        if row.get("headshot"):
            headshots.setdefault(name, row["headshot"])
    for r in list(prior_stats):
        url = _s(r, "headshot_url", "headshot")
        if url:
            headshots.setdefault(
                _s(r, "player_display_name", "player_name", "full_name"), url)

    carried_report: dict = {}
    props: list[Prop] = []
    for spec in specs:
        team = team_of(spec.player)
        if team not in opponent_of:
            continue
        logs = player_game_logs(stats, spec.player, spec.market, upto_week)
        carried = None
        if carry and index and len(logs) < MIN_LOGS:
            carried = _carry.carry_for(index, prior_stats, spec.player,
                                       spec.market,
                                       pos_means.get(spec.market, {}))
        if carried is None and len(logs) < MIN_LOGS:
            continue  # not enough history to project
        if carried is not None:
            # Order matters and is not the sort order: a carried week 17
            # is OLDER than a current week 1, and compute_form reads the
            # list positionally. Current games first, always.
            logs = logs + carried["logs"]
            baseline = _carry.shrunk_mean(carried)
            carried_report[spec.player] = carried
        else:
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
            # A carried player has no current-season rows, so his career
            # anchor has to come from the season the logs came from —
            # otherwise compute_form shrinks toward a career average of 0.
            career_avg=career_average(
                prior_stats if carried is not None else stats,
                spec.player, spec.market),
            vs_opponent_avg=None,
            lines=[SportsbookLine(book="proxy", line=line, over_odds=-110, under_odds=-110)],
            usage_role=spec.usage_role,
            headshot=headshots.get(spec.player, ""),
        ))

    # ANYTIME-TOUCHDOWN PROPS, one per skill player already on the board.
    #
    # These existed only in the preseason seeder until 2026-08-25; the
    # regular-season slate built yardage props alone, so the long-shot
    # pipeline (engine/pipeline._long_shots) iterated a list that could
    # not contain its own market and the NFL board was empty by
    # construction — the odds feed and the odds window never even got a
    # say. Ethan: "Touchdown props for nfl are live now we should see
    # them showing up in the longshot spot."
    #
    # NO PROXY LINE, deliberately. A yardage prop's proxy line lets the
    # model show its lean before books post; a scorer market priced
    # against a made-up -110 would put fake edges on a longshot board.
    # `lines` stays empty until apply_odds_to_slate attaches a real
    # scorer quote, and _long_shots skips unpriced props — no odds pull,
    # no TD picks, honestly.
    seen_td: set[tuple[str, str]] = set()
    td_props: list[Prop] = []
    for p in props:
        if p.market == PASS_YDS:
            continue                 # QB passing TDs are a different market
        key = (p.team, p.player)
        if key in seen_td:
            continue
        seen_td.add(key)
        # The roster's position beats the market-derived guess: a
        # pass-catching back holds a REC_YDS prop and is still an RB at
        # the goal line, which is where this market is decided.
        pos = ((roster.get(p.player) or {}).get("position") or "").upper() \
            or p.position
        # Ethan circled the card's confession, 2026-08-26: "Thin
        # touchdown history (0 games) — position baseline used", on
        # EVERY week-1 card. These logs read the CURRENT season only,
        # so each September the model opened blind while last season's
        # touchdowns sat in prior_stats, already loaded for the yardage
        # carry. Thin logs top up from there now — regular season only,
        # the same slice the yardage carry reads — capped where the
        # blend stops trusting bigger samples anyway.
        td_logs = td_game_logs(stats, p.player, upto_week)
        if carry and prior_stats and len(td_logs) < _TD_THIN:
            prior_td = td_game_logs(_regular_season(prior_stats),
                                    p.player, 99)
            td_logs = td_logs + prior_td[:TD_CARRY_GAMES - len(td_logs)]
        td_props.append(Prop(
            player=p.player, team=p.team, opponent=p.opponent,
            position=pos, market=ANYTIME_TD,
            logs=td_logs,
            career_avg=0.0, vs_opponent_avg=None, lines=[],
            usage_role=p.usage_role, headshot=p.headshot,
        ))
    props.extend(td_props)

    # Teams dict for every participating side, using computed or neutral defense.
    teams: dict[str, Team] = {}
    for abbr in participating:
        teams[abbr] = Team(
            abbr=abbr,
            name=abbr,
            defense=defenses.get(abbr, DefenseProfile(team=abbr)),
        )

    if report is not None:
        report["carried"] = carried_report
        report["carried_n"] = len(carried_report)

    return Slate(date=f"{season}-W{week:02d}", teams=teams, games=games, props=props)
