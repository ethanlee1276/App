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
    PASS_YDS, PASS_TD, RUSH_YDS, REC_YDS, RECEPTIONS, ANYTIME_TD,
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
    PASS_TD: ("passing_tds",),
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


def _has(row: dict, *keys) -> bool:
    """Did the row actually carry one of these fields?

    The same emptiness test `_f` uses, asked as a question instead of
    swallowed into a default — because for a spread and a total the
    default is indistinguishable from a real value.
    """
    for k in keys:
        v = row.get(k)
        if v in (None, "", "NA"):
            continue
        try:
            float(v)
            return True
        except (TypeError, ValueError):
            continue
    return False


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
            # PRESENT, NOT MERELY NON-ZERO. nflverse fills these after
            # the game is played (same as temp and wind), so a forward
            # board has neither and takes the defaults above — and 44.0
            # and 0.0 are both values a real market can hold. See
            # Game.total_measured.
            total_measured=_has(r, "total_line"),
            spread_measured=_has(r, "spread_line"),
            roof=_s(r, "roof"),
            surface=_s(r, "surface", default="grass"),
            # Rest days come precomputed in the feed, which is better than
            # deriving them: nflverse already accounts for byes, holiday
            # games and the season opener.
            home_rest=int(_f(r, "home_rest", default=0)),
            away_rest=int(_f(r, "away_rest", default=0)),
            neutral_site=_s(r, "location").lower() == "neutral",
            venue=_s(r, "stadium"),
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
    # NO local.exists() SHORT-CIRCUIT — it froze this feed forever.
    # `fetch_csv` caches at this same path with a 12-hour TTL and falls
    # back to the stale file when the network is down (and to a
    # hand-exported file when the release 404s, since that lands at the
    # same path). The exists() check that used to sit here defeated all
    # of that: the first file ever written — by a fetch OR an export —
    # was served eternally. For rosters that meant cut-day (Aug 26) and
    # every trade since never reached the board: a cut player stayed
    # ACT with props built off last season, a waiver claim did not
    # exist, a traded player kept his old team. For weekly stats it was
    # worse: a file cached in Week 1 would have frozen every projection
    # at Week 1 for the season.
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
    # See load_snap_counts — the exists() short-circuit that sat here
    # froze the file at its first write, forever.
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
    # See load_snap_counts — the exists() short-circuit that sat here
    # served the first roster ever written for the rest of the season,
    # which in roster-churn week prices teams that no longer exist.
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


def roster_teams(season: int) -> dict[str, str]:
    """``{name: team}`` for EVERY player the roster file knows, whatever
    his status — keyed by the exact name and by its folded form
    (`oddsapi.normalize_name`), so a stats feed's "Deebo Samuel Sr."
    finds a roster's "Deebo Samuel".

    WHERE A MAN PLAYS NOW. Ethan, 2026-09-15: "we are showing props for
    players not even on the team any more. Isaiah pachaceo is on the
    lions now, not the chiefs." `build_slate.team_of` read the FIRST
    stat row of the season — Week 1's team — before it ever asked the
    roster, so a player who moved after his first game stayed on his
    old team's board for the rest of the year, and the price index
    (keyed by name alone) then handed him his new team's price. This is
    the current-season roster, refreshed on the fetch layer's twelve-hour
    clock, and it is asked first. Unlike `roster_index` it keeps every
    status: a man on IR has still moved.
    """
    from .oddsapi import normalize_name
    out: dict[str, str] = {}
    for r in load_rosters(season):
        name = _s(r, "full_name", "player_name", "football_name")
        team = _s(r, "team")
        if not name or not team:
            continue
        out.setdefault(name, team)
        out.setdefault(normalize_name(name), team)
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
        # A ROSTER ROW WITH AN ESPN ID BUT NO PHOTO STILL HAS A FACE. The
        # roster file ships `headshot_url` for most of the league and an
        # `espn_id` for nearly all of it, and ESPN serves a headshot by
        # that id at a stable path — the same path `facesfill.py` already
        # uses for the hoops leagues. Ethan, 2026-09-14: "We are missing
        # head shots for a lot of NFL players." Taken second, never over a
        # real URL, so nothing that had a face changes.
        if name and not url:
            pid = _s(r, "espn_id")
            if pid:
                url = ESPN_HEADSHOT.format(pid=pid)
        if name and url:
            out.setdefault(name, url)
    return out


#: ESPN's by-id headshot path for the NFL — `facesfill.ESPN_HEADSHOT` with
#: the league filled in, kept here so the board and the backfill agree.
ESPN_HEADSHOT = "https://a.espncdn.com/i/headshots/nfl/players/full/{pid}.png"


def face_for(headshots: dict, player: str) -> str:
    """The face for `player`, exact name first and a normalised match second.

    The stats feed spells a man one way and the roster file another —
    suffixes, accents, a middle initial — and an exact-key lookup drew the
    initials avatar for every one of those with a real photograph sitting
    in the map under a spelling one apostrophe away. Same normaliser the
    settler uses to join a bet to its box score (`oddsapi.normalize_name`),
    for the same reason.
    """
    if not player:
        return ""
    hit = headshots.get(player)
    if hit:
        return hit
    from .oddsapi import normalize_name
    want = normalize_name(player)
    for name, url in headshots.items():
        if url and normalize_name(name) == want:
            return url
    return ""


def _rows_by_player(rows) -> dict:
    """{name: [his rows]} in file order, keyed as every per-player reader keys a row."""
    out: dict = {}
    for r in rows or ():
        out.setdefault(_s(r, "player_display_name", "player_name", "full_name"), []).append(r)
    return out


#: A game under this share of the player's own usual snap share is PARTIAL
#: — the rule measured on 2022-2025 (engine/models.GameLog.partial).
PARTIAL_SHARE = 0.5


def snap_table(season: int, prior_season: int | None = None) -> dict:
    """{(normalised name, season, week): offence snap share} for one or two
    seasons; {} for a season the feed cannot answer (never fatal)."""
    from .oddsapi import normalize_name
    out: dict = {}
    for s in (season, prior_season):
        if s is None:
            continue
        try:
            rows = load_snap_counts(s)
        except DataUnavailable:
            continue
        for r in rows:
            if _s(r, "game_type", default="REG") not in ("REG", ""):
                continue
            wk = int(_f(r, "week", default=0))
            pct = _f(r, "offense_pct", default=-1.0)
            if wk <= 0 or pct < 0:
                continue
            if pct > 1.0:
                pct /= 100.0
            out[(normalize_name(_s(r, "player", "player_name")), s, wk)] = pct
    return out


def stamp_snaps(logs, player: str, season: int, table: dict) -> None:
    """Put each log's snap share on it and flag the partial games (a share
    under PARTIAL_SHARE of the player's own median, which must itself be
    a starter's, 0.5 or more). In place."""
    if not table or not logs:
        return
    from .oddsapi import normalize_name
    key = normalize_name(player)
    for g in logs:
        g.snaps = table.get((key, season - 1 if getattr(g, "prior", False) else season, g.week))
    known = sorted(g.snaps for g in logs if g.snaps is not None)
    if not known:
        return
    med = known[len(known) // 2]
    if med < 0.5:
        return
    for g in logs:
        g.partial = g.snaps is not None and g.snaps < PARTIAL_SHARE * med


def _regular_season(rows: list[dict]) -> list[dict]:
    return [r for r in rows if _s(r, "season_type", "game_type", default="REG") in ("REG", "")]


#: A quarterback's passing line is projected from games he QUARTERBACKED:
#: this many attempts or more. Measured 2026-09-23 on 2022-2025
#: (Ethan: "make sure all the data we use is actually being projected to
#: the pick"): a replacement starter's average over every appearance —
#: mostly relief snaps — ran 36% under what he then threw (RMSE 110.5
#: yards); over his starts alone, 1.03 and 82.9. For regular starters with
#: an early exit in their logs, 1.149 and 79.7 fell to 0.974 and 68.6.
QB_START_ATTEMPTS = 15.0


def quarterbacked(row: dict, market: str) -> bool:
    """False for a passing row from a game he did not really play in."""
    return market not in (PASS_YDS, PASS_TD) or _f(row, "attempts") >= QB_START_ATTEMPTS


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
        if not quarterbacked(r, market):
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
def build_defense_profiles(rows: list[dict], upto_week: int,
                           prior_rows: list[dict] | None = None) -> dict[str, DefenseProfile]:
    """What each defence gives up, per game, to each position (engine/defensevs.py).

    A value > 1.0 means the defence is more generous than average (good for
    the offence). Built from weekly box scores keyed on ``opponent_team``,
    walk-forward (weeks before ``upto_week``), shrunk toward LAST season's
    rating when ``prior_rows`` (last season's weekly rows) are given and
    toward the league average when not — the version that predicted best,
    measured by engine/defensefit.py. The full per-stat ratings ride on the
    profile as ``ratings`` for the matchup model and the pick cards; the
    vs_* numbers are the same ratings, kept for everything that reads them.
    """
    from engine import defensevs as DV
    prior = DV.ratings(prior_rows, 99) if prior_rows else None
    rated = DV.ratings(rows, upto_week, prior=prior)
    profiles = {}
    for team, r in rated.items():
        f = lambda s: float(r[s]["factor"])                           # noqa: E731
        of = r["rb_rush_yds"]["of"]
        profiles[team] = DefenseProfile(
            team=team,
            vs_qb=f("qb_pass_yds"),
            vs_wr1=f("wr_rec_yds"), vs_wr2=f("wr_rec_yds"), vs_slot=f("wr_rec_yds"),   # no alignment in box scores
            vs_te=f("te_rec_yds"),
            vs_rb_rush=f("rb_rush_yds"),
            vs_rb_recv=f("rb_rec_yds"),
            # 1 = toughest (gives up the least), as these always meant.
            rush_rank=of - r["rb_rush_yds"]["rank"] + 1,
            pass_rank=of - r["qb_pass_yds"]["rank"] + 1,
            ratings=r,
        )
    return profiles


# --- slate assembly ---------------------------------------------------------
# Default markets to build per position when auto-selecting players.
POSITION_MARKETS = {
    # A QUARTERBACK HAS TWO MARKETS, not one. Passing touchdowns were
    # missing from this table, so no `Prop` existed for a quote to
    # attach to and the board could not have carried one even after the
    # odds key was added (engine/passtd.py). The role string is the same
    # — he is the starter for both.
    "QB": [(PASS_YDS, "starter"), (PASS_TD, "starter")],
    # EVERY MARKET THE BOOK IS ALREADY PAID FOR, 2026-09-23. Each position
    # had ONE market here since the first nflverse commit — a receiver got
    # receiving yards, a tight end catches, a back rushing yards — while
    # the odds request (sources.oddsapi.ODDS_TO_MARKET) has bought all four
    # stat markets for every player on every event call. So a receiver's
    # catches line, a tight end's yards and a back's receiving line were
    # paid for and thrown away on every pull, and the defence-vs-position
    # ratings measured for exactly those pairings (engine/defensevs
    # TRANSFER: TE yards 0.79, TE catches 0.86, RB catches 0.47) had
    # nothing to act on. Ethan, 2026-09-23: "make sure all the models
    # aren't being affected by issues where data isn't being used or
    # being pulled."
    #
    # MEASURED BEFORE ADDED, on one walk-forward for all of them
    # (2022-2025 box scores, each team's top three by volume, projected
    # from earlier games only, scored against a trailing-average line):
    # ranking AUC WR catches 0.599, RB catches 0.605, RB receiving yards
    # 0.556, TE receiving yards 0.544 — against 0.556 / 0.575 / 0.565 for
    # the three markets the board already carried. Each ranks as well as
    # what was already on the page. The calibrations, grading and ranking
    # figures are per market and were always fitted on every position's
    # rows (engine/ingest `nfl_usage_rows`). QB rushing yards measured
    # 0.536, the weakest of all, and stays off.
    #
    # The FIRST market in each list is the position's own; the others
    # carry a volume floor (SECONDARY_FLOOR) so a third back with one
    # catch a game does not get a line nobody hangs.
    "RB": [(RUSH_YDS, "rb1"), (RECEPTIONS, "rb1"), (REC_YDS, "rb1")],
    "WR": [(REC_YDS, "wr1"), (RECEPTIONS, "wr1")],
    "TE": [(RECEPTIONS, "te"), (REC_YDS, "te")],
}

#: The least a player's recent average may be, for a market that is not
#: his position's own, before a prop is built on it — the college board's
#: floors (engine/cfb/props._MIN_MEAN), the same question in the same
#: sport.
SECONDARY_FLOOR = {REC_YDS: 12.0, RECEPTIONS: 1.5}

#: Positions whose role says WHERE he ranks on his team — "wr2", "rb1".
#: The table's role is only the default; the depth order comes from the
#: volume ranking that picks him. Until 2026-09-23 every receiver on the
#: board was "wr1" and every back "rb1", so the injury rule for an
#: opponent's slot corner (engine/injuries: a "wr2" or "slot" receiver)
#: could never fire, and the fallback matchup could not tell a number
#: one receiver from a number three.
RANKED_ROLES = {"WR": "wr", "RB": "rb"}


def role_for(position: str, rank: int, default: str) -> str:
    """His role on his team: "wr2" for the second receiver by volume, and
    "backup" for a team's second quarterback (built only with
    ``qb_backups`` — see engine/qbchange)."""
    if position == "QB" and rank > 1:
        return "backup"
    stem = RANKED_ROLES.get(position)
    return f"{stem}{rank}" if stem else default


def position_of(market: str) -> str:
    """The position whose OWN market this is (its first in the table), else
    the first that carries it — for a spec that did not say."""
    for pos, markets in POSITION_MARKETS.items():
        if markets[0][0] == market:
            return pos
    for pos, markets in POSITION_MARKETS.items():
        if any(m == market for m, _r in markets):
            return pos
    return ""


def is_secondary(position: str, market: str) -> bool:
    """True for a market that is not the position's own (its first)."""
    own = (POSITION_MARKETS.get(position) or [(None, "")])[0][0]
    return market != own and market in SECONDARY_FLOOR


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
    #: The table row the spec was made from. A market no longer names one
    #: position (a tight end and a receiver both hold receiving yards), so
    #: the position travels with the spec rather than being looked up.
    position: str = ""
    #: The team he was ranked on: this season's stat rows, or the roster
    #: for a carried spec. `one_quarterback_each` lets a quarterback who
    #: played for a team claim its starter before one who played elsewhere.
    team: str = ""


def top_players_for_week(rows: list[dict], teams: set[str], upto_week: int,
                         per_team: int = 3, qb_backups: bool = False) -> list[PlayerSpec]:
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
    # Sorted: a set's order changes with every process, and the order of
    # this list decides ties downstream (one_quarterback_each).
    for team in sorted(teams):
        for pos, markets in POSITION_MARKETS.items():
            cands = [(k, v) for k, v in agg.items() if k[0] == team and k[1] == pos]
            cands.sort(key=lambda kv: kv[1]["vol"], reverse=True)
            take = (2 if qb_backups else 1) if pos in ("QB",) else per_team
            for rank, ((_t, _p, name), _v) in enumerate(cands[:take], 1):
                for market, role in markets:
                    specs.append(PlayerSpec(name, market, role_for(pos, rank, role), pos, team))
    return specs


#: Fewest same-season games that can carry a projection on their own. Below
#: it the prior season is topped up in, when the carry is enabled.
MIN_LOGS = 3


def _carry_specs(prior_rows: list[dict], roster: dict[str, dict],
                 teams: set[str], per_team: int = 3, qb_backups: bool = False) -> list[PlayerSpec]:
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
    for team in sorted(teams):
        for pos, markets in POSITION_MARKETS.items():
            cands = [(k, v) for k, v in agg.items()
                     if k[0] == team and k[1] == pos]
            cands.sort(key=lambda kv: kv[1]["vol"], reverse=True)
            take = (2 if qb_backups else 1) if pos in ("QB",) else per_team
            for rank, ((_t, _p, name), _v) in enumerate(cands[:take], 1):
                for market, role in markets:
                    specs.append(PlayerSpec(name, market, role_for(pos, rank, role), pos, team))
    return specs


def one_quarterback_each(specs: list[PlayerSpec], team_of) -> list[PlayerSpec]:
    """At most one starter and one backup at quarterback per team, the first
    in the list winning (the current season's ranking comes first).

    FOUND 2026-09-23 with the QB-change work: `_merge_specs` adds a
    prior-season spec for any (player, market) the current season does not
    cover, which is right for a receiver with no games yet and wrong for a
    position with one job. A team whose starter changed since last season
    got TWO starters — six teams on a 2025 week-10 rebuild, Jameis Winston
    (last season's numbers, the Giants' third quarterback) beside Jaxson
    Dart among them.

    A QUARTERBACK WHO PLAYED FOR THE TEAM CLAIMS IT FIRST. Found the same
    day by running one build twice: a quarterback ranked on his OLD team's
    rows but filed under his new one (a trade, a release) took the new
    team's starter slot whenever his old team happened to come first in a
    set's order — which changes with every process. Rebuilt 2025 week 3
    under six hash seeds, Cincinnati's starter was Joe Flacco (Cleveland's
    weeks 1-2) four times and Joe Burrow twice, and the receivers' QB-
    change drop went with it. Specs ranked on the team they are filed
    under now claim first; the rest keep their order after them."""
    here = [sp.position == "QB" and bool(sp.team) and sp.team == team_of(sp.player) for sp in specs]
    slots: dict = {}
    keep = set()
    for first in (True, False):
        for i, sp in enumerate(specs):
            if sp.position != "QB" or here[i] != first:
                continue
            slot = slots.setdefault(team_of(sp.player), {})
            role = "backup" if sp.usage_role == "backup" else "starter"
            if slot.get(role, sp.player) != sp.player:
                continue
            if role == "backup" and slot.get("starter") == sp.player:
                continue
            if role == "starter" and slot.get("backup") == sp.player:
                continue
            slot[role] = sp.player
            keep.add(i)
    return [sp for i, sp in enumerate(specs) if sp.position != "QB" or i in keep]


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
                carry: bool = False, report: dict | None = None,
                qb_backups: bool = False, games: list[Game] | None = None) -> Slate:
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

    ``games`` is the week's list when the caller already has one — the
    build passes the one `nfl_build.show_games` stamped with the kickoff
    forecast (engine/nflwx.py). Until 2026-09-23 this re-read the schedule
    instead, so every outdoor game the projections and the published
    cards saw was the 60°F / 6 mph prior and the forecast reached only
    the console.
    """
    upto_week = upto_week or week
    games = games if games else build_games(season, week)
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
    # Last season is where each defence's rating starts (engine/defensevs):
    # two games of this season are a signal and mostly noise.
    try:
        last_season = load_weekly_stats(season - 1)
    except DataUnavailable:
        last_season = None
    defenses = build_defense_profiles(stats, upto_week, last_season)

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

    # EACH PLAYER'S ROWS, ONCE. Every per-player read below filtered the
    # whole season by name — per player, per market — and on 2026-09-23
    # that was 80 of a build's 108 seconds here, several times that on
    # the droplet's one core, under a 600-second ceiling whose miss keeps
    # yesterday's board (launch.refresh_nfl, "kept last board"). Ethan:
    # "the same most likely pics that we had earlier are the same ones
    # that are there now." Handing each reader only that player's rows is
    # the same answer: every one of them keys a row by this same name.
    stats_of = _rows_by_player(stats)
    prior_of = _rows_by_player(prior_stats)
    # Snap shares, so a game a player left hurt is marked on his logs
    # (Ethan, 2026-09-23, Garrett Wilson's 0 vs CLE — 19 snaps, 39%).
    snaps = snap_table(season, season - 1 if carry else None)

    if specs is None:
        # ``qb_backups``: each team's SECOND quarterback by volume too, as
        # role "backup". engine/qbchange keeps his props only where the
        # starter is out or benched and drops them everywhere else — the
        # injury report is read after the slate is built, so the man who
        # actually starts has to exist on it before anyone knows.
        specs = top_players_for_week(stats, participating, upto_week, qb_backups=qb_backups)
        if carry and index:
            specs = _merge_specs(specs, _carry_specs(
                prior_stats, roster, participating, qb_backups=qb_backups))

    # WHERE EACH MAN PLAYS NOW — the current roster, every status. See
    # `roster_teams`. Unreachable is an empty map, and the stat rows
    # answer alone, as they always did.
    try:
        homes = roster_teams(season)
    except DataUnavailable:
        homes = {}
    from .oddsapi import normalize_name as _fold

    def team_of(player: str) -> str:
        """The team a prop is FILED under, which decides his game.

        THE ROSTER FIRST, THEN THE NEWEST STAT ROW. This used to return
        the first stat row it found — the season's Week 1 — and only
        asked the roster when there were no rows at all, so a player
        traded or claimed after his first game was built against his
        old team's opponent all year (Ethan, 2026-09-15, Pacheco on the
        Chiefs' board a week after joining the Lions). The roster is the
        one feed that says where he is today; when it does not know him,
        the LATEST week he has a row for is the next best fact, and
        never the first.
        """
        now_team = homes.get(player) or homes.get(_fold(player))
        if now_team:
            return now_team
        best: tuple | None = None
        for r in stats_of.get(player, ()):
            team = _s(r, "recent_team", "team")
            if not team:
                continue
            wk = _f(r, "week")
            if best is None or wk > best[0]:
                best = (wk, team)
        if best is not None:
            return best[1]
        # A season with no games yet: the carry's own roster view.
        return (roster.get(player) or {}).get("team", "")

    # Official headshot URLs. THREE sources, in the order a face is most
    # likely to be current: this season's stats, then THIS SEASON'S ROSTER,
    # then last season's stats — a face does not go stale over one
    # offseason, so an older one beats none.
    #
    # The roster is the load-bearing middle and the reason this was thin.
    # Weekly stats do not exist until games have been played, so on a Week 1
    # board the first source is empty and everything fell through to last
    # season — which has no row at all for a rookie or a practice-squad
    # promotion. Measured on 2026: the roster carries 2,816 faces and 1,071
    # of those players appear in no 2025 stat row. They were drawing the
    # initials avatar with a real photograph sitting in a file already on
    # disk.
    #
    # THAT MIDDLE SOURCE USED TO BE `roster`, WHICH IS FILTERED TO ACT.
    # Ethan, 2026-09-04: "I see some players on nfl don't have any and a
    # lot are last year headshots." `roster_index` exists to decide who
    # gets a prop BUILT — "a player on reserve or already cut should not
    # have a prop built for him off last season's numbers" — so it drops
    # every status but ACT. Reading faces out of it inherited that filter
    # for free, and a man on IR, PUP, the practice squad or suspended
    # therefore had no current-season face at all and fell through to last
    # season's photograph. `headshot_map` reads the SAME roster file
    # without the status filter, and its docstring has said why since it
    # was written: "a face on the usage board does not stop being his face
    # because he moved to IR". It was only ever wired to the fantasy pages.
    #
    # It is also unconditional, where `roster` is populated only under
    # `carry`. A build without that flag had no middle source whatsoever
    # and sent EVERY face to last season's file.
    headshots: dict[str, str] = {}
    for r in list(stats):
        url = _s(r, "headshot_url", "headshot")
        if url:
            headshots.setdefault(
                _s(r, "player_display_name", "player_name", "full_name"), url)
    for name, url in headshot_map(season).items():
        headshots.setdefault(name, url)
    for r in list(prior_stats):
        url = _s(r, "headshot_url", "headshot")
        if url:
            headshots.setdefault(
                _s(r, "player_display_name", "player_name", "full_name"), url)

    specs = one_quarterback_each(specs, team_of)

    carried_report: dict = {}
    thin_report: dict = {}
    props: list[Prop] = []
    for spec in specs:
        team = team_of(spec.player)
        if team not in opponent_of:
            continue
        mine, mine_before = stats_of.get(spec.player, []), prior_of.get(spec.player, [])
        logs = player_game_logs(mine, spec.player, spec.market, upto_week)
        carried = None
        if carry and index and len(logs) < MIN_LOGS:
            carried = _carry.carry_for(index, mine_before, spec.player,
                                       spec.market,
                                       pos_means.get(spec.market, {}))
        thin = None
        if carried is None and len(logs) < MIN_LOGS and carry and pos_means:
            # A rookie, or last season lost to injury: one or two games
            # and no carry. Built from them, pulled toward the position
            # (engine/carry.py, THIN SAMPLES — weeks 2-3 only).
            thin = _carry.thin_for(logs, mine_before, spec.player, spec.market,
                                   spec.position or position_of(spec.market),
                                   pos_means.get(spec.market, {}), upto_week)
        if carried is None and thin is None and len(logs) < MIN_LOGS:
            continue  # not enough history to project
        if thin is not None:
            baseline = thin["baseline"]
            thin_report[spec.player] = thin
        elif carried is not None:
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
        stamp_snaps(logs, spec.player, season, snaps)
        pos = spec.position or position_of(spec.market)
        # A market that is not his position's own is built only when he
        # actually does it: a back's catches, a receiver's catches, a
        # tight end's yards — see SECONDARY_FLOOR.
        if is_secondary(pos, spec.market) and baseline < SECONDARY_FLOOR[spec.market]:
            continue
        line = _round_half(baseline) - 0.5  # a touch under baseline, like a book
        # DERIVED FROM `POSITION_MARKETS`, NOT A SECOND COPY OF IT.
        #
        # THE OUTAGE OF 2026-09-10. This line was a hand-written literal
        # naming four markets, and `POSITION_MARKETS` twenty lines up is
        # the table that decides which markets a position actually gets.
        # Passing touchdowns were added THERE and not here, so the moment
        # a quarterback produced a second spec this raised
        # `KeyError: 'pass_td'` — out of `build_slate`, so not one prop
        # was returned, so the NFL board and the Most Likely board were
        # both empty for two hours on the Thursday of Week 1.
        #
        # Ethan, 17:58: "all the edge bets and most likely bets for nfl
        # disappeared." Player search kept working throughout, which is
        # the tell I should have read first: it reads `player_game_logs`
        # and never touches the slate.
        #
        # Carried on the spec from the one table, so a market cannot
        # diverge again — this file's own `resolve_market_keys` note
        # already says it: "THE SECOND COPY OF THIS MAP WAS THE BUG." Since
        # 2026-09-23 a market can belong to more than one position, so the
        # spec says which row made it (`PlayerSpec.position`).
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
                mine_before if carried is not None else mine,
                spec.player, spec.market),
            vs_opponent_avg=None,
            lines=[SportsbookLine(book="proxy", line=line, over_odds=-110, under_odds=-110)],
            usage_role=spec.usage_role,
            headshot=face_for(headshots, spec.player),
            form_prior=thin["anchor"] if thin and thin["weight"] < 1.0 else None,
            form_prior_n=_carry.THIN_ANCHOR_GAMES if thin else 0,
            form_prior_games=_carry.THIN_PRIOR_GAMES if thin else 0.0,
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
        td_logs = td_game_logs(stats_of.get(p.player, []), p.player, upto_week)
        if carry and prior_stats and len(td_logs) < _TD_THIN:
            prior_td = td_game_logs(_regular_season(prior_of.get(p.player, [])),
                                    p.player, 99)
            td_logs = td_logs + prior_td[:TD_CARRY_GAMES - len(td_logs)]
        stamp_snaps(td_logs, p.player, season, snaps)
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
        report["thin"] = thin_report
        # WHO EACH TEAM'S QUARTERBACKS ARE, and what they have thrown —
        # engine/qbchange reads it once the injuries are in.
        from ..qbchange import quarterbacks as _quarterbacks
        report["qb"] = _quarterbacks(specs, stats, prior_stats, upto_week, team_of)
        # THE DEPTH ORDER AT EACH POSITION, the one engine/matefit measured
        # on — engine/teammates reads it once the injuries are in.
        from ..teammates import depth_table as _depth_table
        report["depth"] = _depth_table(stats, participating, upto_week)

    return Slate(date=f"{season}-W{week:02d}", teams=teams, games=games, props=props)
