"""College player props — a slate of yardage props off the ingested logs.

Ethan, twice on 2026-09-02: "make sure everything I'm telling you to do
for NFL is also being implemented for college football because I'm still
not seeing any props for college football."

WHAT WAS MISSING WAS NOT A MODEL. `engine.pipeline.price_props` prices a
football prop from a player's own game log; `projection.build_projection`
takes ``sport`` only to key its self-tuning stores; `betting.evaluate_prop`
already reads "cfb" as football for weather and fatigue. What college
never had was a SLATE — an object with `games` and `props` on it — because
its board was built from game rows and a touchdown quote, and nothing ever
turned four seasons of ingested player production into props.

This is that turn, and it is deliberately thin: it reads the logs, places
each player on a side, hangs a proxy line a touch under his recent form
the way `engine.sources.nflverse` does, and hands the slate on. Every
judgement about whether the resulting number is worth betting is made
downstream, by the same code that judges the NFL's.

THE COLLEGE-SHAPED PART IS WHO IS ON WHICH TEAM. A quarter of the players
a book quotes in college football changed schools over the summer
(`engine.cfb.tds.teams_by_name` measured 19.9% and 25.2% across the last
two transfer cycles), so "look him up under one of tonight's two teams"
drops a quarter of the board. The SIDE he plays for and the TEAM his
production is filed under are two different things, and `tds.resolve_side`
already knows the difference — this reuses it rather than growing a second
answer that can disagree with the touchdown board's.
"""

from __future__ import annotations

from ..data_loader import Slate
from ..models import (
    DefenseProfile, Game, GameLog, LiveStatus, Prop, SportsbookLine, Team,
    Weather, PASS_YDS, RUSH_YDS, REC_YDS, RECEPTIONS,
)

#: The four markets a book hangs on a college skill player, and the four
#: `engine.rankfit.MARKETS["cfb"]` measures. Kept in one order so a board
#: and its measurement can be read side by side.
MARKETS = (PASS_YDS, RUSH_YDS, REC_YDS, RECEPTIONS)

#: The market's own column in ``player_game_logs``. Identical strings
#: today — `engine.sources.cfbstats` writes the engine's own market names
#: — and written down anyway, because the day they diverge the failure is
#: a silently empty board.
_COLUMN = {PASS_YDS: "pass_yds", RUSH_YDS: "rush_yds",
           REC_YDS: "rec_yds", RECEPTIONS: "receptions"}

#: Position by market, matching `engine.sources.nflverse.build_slate`. A
#: roster position beats this wherever the mirror's roster file supplied
#: one (`tds.role_of`); this is the fallback that keeps the projection's
#: role logic sensible for a player with no label.
_POSITION = {PASS_YDS: "QB", RUSH_YDS: "RB", REC_YDS: "WR", RECEPTIONS: "TE"}

#: Games of his own before a player can be projected. The same floor the
#: walk-forward measurement uses (`engine.logwalk.settled_props_from_logs`
#: min_history), so a player the board prices is a player the AUC covered.
MIN_LOGS = 4

#: How many past games ride on a prop. `compute_form` reads last1/3/5/10
#: and the season mean, so beyond twenty the tail only slows the payload.
LOG_LIMIT = 20

#: A market a player barely touches is not a market. Below this per-game
#: mean the proxy line lands at the 0.5 floor for everyone and the board
#: fills with third-string receivers at "over 0.5 yards".
_MIN_MEAN = {PASS_YDS: 40.0, RUSH_YDS: 12.0, REC_YDS: 12.0, RECEPTIONS: 1.5}


def _round_half(x: float) -> float:
    return round(x * 2) / 2.0


def _proxy_line(values: list[float]) -> float:
    """A touch under recent form, the way a book hangs one.

    The same rule `nflverse.build_slate` uses, and it exists to be
    REPLACED: `oddsapi` overwrites it with a real number wherever a book
    has one, and `betting.evaluate_prop` refuses to call a proxy-priced
    row a market at all (`has_market`). A prop that never gets a real
    line is analysed and shown, never staked and never journaled.
    """
    base = sum(values) / len(values)
    return max(0.5, _round_half(base) - 0.5)


def _weather_of(game: dict) -> Weather:
    """The kickoff forecast `engine.cfb.wx` stamped, or an honest blank.

    ``measured`` is the field that stops a default posing as a fact — the
    same contract the NFL side carries. A game whose venue never resolved
    keeps ``weather_checked`` False and arrives here as an unmeasured
    mild day, which every consumer checks before showing or journaling.
    """
    w = game.get("weather") or {}
    if w.get("dome"):
        return Weather(dome=True, measured=True)
    if not game.get("weather_checked"):
        return Weather()
    return Weather(
        dome=False,
        temp_f=float(w.get("temp_f", 65.0)),
        wind_mph=float(w.get("wind_mph", 5.0)),
        wind_dir=str(w.get("wind_dir") or ""),
        measured=True,
    )


def _game_objects(games: list[dict]) -> tuple[dict, list]:
    """``({abbr: Team}, [Game])`` for tonight's college slate.

    Defence is LEAGUE AVERAGE on purpose. `DefenseProfile`'s fields are
    nflverse-shaped (vs_wr1, pressure_rate, a 1-32 rush rank) and college
    has no equivalent ingest; filling them with plausible numbers would
    put a matchup multiplier on every card that no measurement stands
    behind. The neutral profile is what the walk-forward AUC was measured
    under, so the live board and the measurement price the same model.
    """
    teams: dict[str, Team] = {}
    out: list[Game] = []
    for g in games or []:
        home, away = str(g.get("home") or ""), str(g.get("away") or "")
        if not home or not away:
            continue
        for abbr, name in ((home, g.get("home_name") or home),
                           (away, g.get("away_name") or away)):
            teams.setdefault(abbr, Team(abbr=abbr, name=str(name),
                                        defense=DefenseProfile(team=abbr)))
        live = g.get("live") or {}
        game = Game(
            home=home, away=away, weather=_weather_of(g),
            date=str(g.get("date") or "")[:10],
            kickoff=str(g.get("kickoff") or ""),
            spread=float(g.get("spread") or 0.0),
            total=float(g.get("total") or 44.0),
            roof="dome" if (g.get("weather") or {}).get("dome") else "outdoors",
            live=(LiveStatus(state=str(live.get("state") or "scheduled"),
                             home_score=live.get("home_score"),
                             away_score=live.get("away_score"),
                             period=str(live.get("period") or ""),
                             clock=str(live.get("clock") or ""))
                  if live else None),
            neutral_site=bool(g.get("neutral_site")),
        )
        # The book's own spelling, so `oddsapi.apply_odds_to_slate` can
        # join an event to this game without a 134-school table — the
        # rescue it grew for the WNBA and the reason SPORT_CONFIG["cfb"]
        # keeps an empty `teams` map on purpose.
        game.home_name = str(g.get("home_name") or "")
        game.away_name = str(g.get("away_name") or "")
        out.append(game)
    return teams, out


def _log_rows(conn, seasons: list[int]) -> dict:
    """``{team: {norm: {"player", "position", market: [rows newest first]}}}``.

    ONE QUERY FOR THE WHOLE BOARD, and it reads every school rather than
    tonight's two dozen — because a transfer's production is filed under
    the school he left, which is not on tonight's slate by definition.
    That is the same full-season scan `tds.usage_table` already does, for
    the same reason.

    Ordered season-then-date DESCENDING because `compute_form` reads the
    list POSITIONALLY: a carried game from last November is OLDER than
    this September's opener, the trap `engine.carry` documents on the NFL
    side. `prior` is set from the season so nothing downstream has to
    infer it — `engine.reset.apply_to_slate` excludes carried games from
    a post-reset window and needs the flag to be true.

    NOT `tds.usage_table`, which is where the first cut of this read its
    candidates from and why every pure pocket passer was missing: that
    table selects carries/receptions/rushing/receiving and the red-zone
    columns, and NOT `pass_yds`. A quarterback who never ran the ball was
    in no team's usage map and could therefore never be placed on a side,
    so the one market with a single obvious player per team was the one
    market with no players at all.
    """
    from ..sources.oddsapi import normalize_name
    if not seasons:
        return {}
    q = ("SELECT season, period, player, team, opponent, position, home, "
         "market, value FROM player_game_logs WHERE sport='cfb' "
         "AND market IN (%s) AND season IN (%s) "
         "ORDER BY season DESC, period DESC"
         % (",".join("?" * len(_COLUMN)), ",".join("?" * len(seasons))))
    args = [*(_COLUMN[m] for m in MARKETS), *(int(s) for s in seasons)]
    out: dict = {}
    newest = max(int(s) for s in seasons)
    for r in conn.execute(q, args):
        slot = out.setdefault(r["team"], {}).setdefault(
            normalize_name(r["player"]), {"player": r["player"], "position": ""})
        slot["position"] = slot["position"] or (r["position"] or "").strip().upper()
        slot.setdefault(r["market"], []).append(
            (str(r["period"] or ""), str(r["opponent"] or ""),
             bool(r["home"]), float(r["value"]),
             int(r["season"]) != newest))
    return out


def _candidates(games: list[dict], filed: dict, current: dict) -> list[tuple]:
    """``[(side, opponent, filed_team, norm)]`` — who is playable tonight.

    Enumerated from the LOGS rather than from a quote list, which is the
    difference between this and the touchdown board: there is no menu of
    priced players to walk, so the candidates are everyone with college
    production who can be placed on one of tonight's sides.

    THE SIDE AND THE FILING TEAM ARE TWO DIFFERENT ANSWERS and conflating
    them is the transfer bug `tds.resolve_side` exists to fix — the side
    decides who he plays against tonight, the filing team decides where
    his production is stored. Reused rather than re-derived so the two
    college boards can never disagree about which school a player is at.
    """
    from .tds import resolve_side

    seen: set = set()
    out: list[tuple] = []
    for g in games or []:
        home, away = str(g.get("home") or ""), str(g.get("away") or "")
        if not home or not away:
            continue
        pool = set(filed.get(home) or {}) | set(filed.get(away) or {})
        # …plus the transfers: filed elsewhere, playing here.
        pool |= {n for n, teams in (current or {}).items()
                 if teams & {home, away}}
        for norm in sorted(pool):
            side, filed_team = resolve_side(norm, home, away, filed, current)
            if not side or not filed_team:
                continue
            if (side, norm) in seen:
                continue                     # a name cannot play twice
            seen.add((side, norm))
            out.append((side, away if side == home else home,
                        filed_team, norm))
    return out


def build_props(conn, games: list[dict], season: int,
                census: dict | None = None,
                current: dict | None = None) -> list[Prop]:
    """Every college prop tonight's logs can support.

    ``census`` is filled in place with why players were dropped — the
    same discipline `tds.build_cfb_td_longshots` follows, and for the
    same reason: an empty college board has several possible causes and
    a count that only ever reached stdout is a count nobody has on the
    morning it matters.

    ``current`` overrides the transfer bridge (``{norm: {teams}}``). The
    default builds it from this season's logs plus the published
    rosters, which is a network read — injected here so the suite can
    exercise the join offline.
    """
    from .tds import merged_usage, role_of, rosters_for, teams_by_name

    census = census if census is not None else {}
    census.setdefault("candidates", 0)
    census.setdefault("transfers", 0)
    census.setdefault("no_logs", 0)
    census.setdefault("thin_history", 0)
    census.setdefault("below_volume", 0)
    census.setdefault("props", 0)

    usage_season, usage, _why = merged_usage(conn, int(season))
    census["usage_season"] = usage_season
    # Two seasons: the one being played, and the one behind it for the
    # carry. Any further back is a different roster and a different
    # coordinator. `usage_season` rides along because in August the
    # current season has no logs at all and the usage table has already
    # fallen back — the logs must fall back with it or a September board
    # prices nobody.
    seasons = sorted({usage_season, usage_season - 1, int(season),
                      int(season) - 1} - {0, -1})
    filed = _log_rows(conn, seasons)
    if not filed:
        return []
    if current is None:
        current = teams_by_name(conn, int(season))
        slate = [t for g in (games or [])
                 for t in (g.get("home"), g.get("away")) if t]
        for norm, team in rosters_for(slate, int(season)).items():
            current.setdefault(norm, set()).add(team)

    cands = _candidates(games, filed, current)
    census["candidates"] = len(cands)
    census["transfers"] = sum(1 for side, _o, ft, _n in cands if ft != side)
    if not cands:
        return []

    props: list[Prop] = []
    for side, opponent, filed_team, norm in cands:
        slot = (filed.get(filed_team) or {}).get(norm)
        if not slot:
            census["no_logs"] += 1
            continue
        # The ROLE comes from the touchdown board's usage table, which
        # carries the roster label and the carries/catches mix — one
        # answer about what a player is, shared by both college boards.
        u = (usage.get(filed_team) or {}).get(norm) or {}
        role = role_of({"carries": u.get("carries", 0.0),
                        "receptions": u.get("receptions", 0.0),
                        "position": slot.get("position") or u.get("position", "")})
        for market in MARKETS:
            rows = (slot.get(_COLUMN[market]) or [])[:LOG_LIMIT]
            if len(rows) < MIN_LOGS:
                if rows:
                    census["thin_history"] += 1
                continue
            values = [v for _p, _o, _h, v, _pr in rows]
            if sum(values) / len(values) < _MIN_MEAN[market]:
                census["below_volume"] += 1
                continue
            props.append(Prop(
                player=slot["player"], team=side, opponent=opponent,
                # A passing prop is a quarterback's whatever the usage
                # mix says — `role_of` never guesses QB, deliberately, so
                # the market itself is the better evidence here.
                position="QB" if market == PASS_YDS else (role or _POSITION[market]),
                market=market,
                logs=[GameLog(week=len(rows) - i, opponent=o, value=v,
                              home=h, prior=pr)
                      for i, (_p, o, h, v, pr) in enumerate(rows)],
                career_avg=sum(values) / len(values),
                vs_opponent_avg=None,
                lines=[SportsbookLine(book="proxy", line=_proxy_line(values),
                                      over_odds=-110, under_odds=-110)],
                usage_role="starter",
            ))
    census["props"] = len(props)
    return props


def build_slate(conn, games: list[dict], date: str, season: int,
                census: dict | None = None,
                current: dict | None = None) -> Slate:
    """Tonight's college slate, ready for `pipeline.price_props`."""
    teams, game_objs = _game_objects(games)
    props = build_props(conn, games, season, census=census, current=current)
    # A prop whose game is not on the slate would raise out of
    # `Slate.game_for` mid-loop and take the whole board with it.
    pairs = {frozenset((g.home, g.away)) for g in game_objs}
    props = [p for p in props if frozenset((p.team, p.opponent)) in pairs]
    return Slate(date=str(date), teams=teams, games=game_objs, props=props)


__all__ = ["MARKETS", "MIN_LOGS", "LOG_LIMIT", "build_props", "build_slate"]
