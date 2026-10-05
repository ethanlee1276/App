"""Walk-forward backtest for the GENERIC engine — every sport that prices
through ``engine.projection`` + ``engine.betting`` (NFL today; any log-based
sport that adopts the shared prop model tomorrow).

The mirror of ``engine/mlb/backtest.py``, built for the same reason: the
self-tuning fitters (temperature, recency dial, player memory) all score
candidates by walking a player's game log forward — game i projected only
from games [:i], settled against what actually happened — and MLB was the
only sport that had the harness. Neutral game context (no weather, average
defense), so this measures the FORM MODEL + calibration, exactly like its
MLB sibling; matchup/weather angles are validated on top with live context.

The three fitter hooks are the same contract as MLB's:
  ``form_weights``   — explicit window curve (the recency-dial fitter's
                       candidates; None = the live store/default path)
  ``player_adjust``  — per-player multiplier callable (playerfit's causal
                       walk; an explicit ``lambda n: 1.0`` is the baseline
                       that keeps every store out of the measurement)
  ``player_record``  — accumulates the RAW blend's (projected, actual)
"""

from __future__ import annotations

from .backtest import SettledProp, evaluate, BacktestReport
from .models import (Prop, Game, Team, GameLog, DefenseProfile, Weather,
                     SportsbookLine, PASS_INT)
from .projection import build_projection
from .betting import evaluate_prop

#: Position by market, so the projection's role logic stays sensible.
_POSITION = {"pass_yds": "QB", "rush_yds": "RB",
             "rec_yds": "WR", "receptions": "WR",
             "pass_att": "QB", "pass_cmp": "QB", "pass_int": "QB", "rush_att": "RB"}

#: A count market is hung at the book's one number, not a trailing
#: average: every book posts a pick thrown at 0.5, and the walk should
#: score the question the board will actually be asked.
COUNT_LINE = {PASS_INT: 0.5}

#: The companion stat a market is built from, when it is not built from
#: its own log alone (engine/passint: picks ride on attempts).
COMPANION = {PASS_INT: "pass_att"}


class Entries(list):
    """A list of walk entries that carries what the walk needs beside
    them (``aux``): for interceptions, every defence's game-by-game
    picks forced (`db.allowed_timeline`) so the walk can rate the
    opponent as `engine/defensevs` rates it. A plain list walks as it
    always did; `walk` reads ``aux`` off this one, so the fitters that
    call `walk(sport, entries, market, …)` need no new argument."""
    aux: dict = {}


def load_entries(conn, sport: str, market: str, min_games: int = 8,
                 seasons: list[int] | None = None) -> Entries:
    """The one door the fitters and the rank walk load a market's
    entries through. Interceptions come paired with attempts and with
    the defences' timeline; everything else is `db.entries_for_market`."""
    from . import db as _db
    companion = COMPANION.get(market)
    if companion:
        got = Entries(_db.entries_with_companion(conn, sport, market, companion,
                                                 min_games=min_games, seasons=seasons))
        got.aux = {"allowed": _db.allowed_timeline(conn, sport, market, seasons=seasons)}
        return got
    got = Entries(_db.entries_for_market(conn, sport, market, min_games=min_games, seasons=seasons))
    got.aux = {}
    return got


def _neutral() -> tuple[Game, Team]:
    game = Game(home="HOME", away="AWAY", weather=Weather(dome=True))
    opp = Team(abbr="AWAY", name="Away",
               defense=DefenseProfile(team="AWAY"))
    return game, opp


def _round_half(x: float) -> float:
    return round(x * 2) / 2.0


def _naive_line(prior_recent: list[float]) -> float:
    base = sum(prior_recent) / len(prior_recent)
    return max(0.5, _round_half(base) - 0.5)


def _week_of(period: str, first: str | None) -> int:
    """A period as a week: the zero-padded week the NFL stores, or the
    date college stores counted from the season's first date."""
    p = str(period or "")
    if p.isdigit():
        return int(p)
    try:
        import datetime as _dt
        return (_dt.date.fromisoformat(p[:10]) - _dt.date.fromisoformat(str(first)[:10])).days // 7 + 1
    except (TypeError, ValueError):
        return 0


class _Defences:
    """What each defence allowed in a market, rated for any game the
    walk prices exactly as `engine/defensevs.ratings` rates it live:
    this season's games BEFORE that week, shrunk toward last season's
    full-season rating. Cached per (season, week)."""

    def __init__(self, allowed, stat: str, column: str, position: str):
        from collections import defaultdict
        self.stat, self.column, self.position = stat, column, position
        by_season: dict = defaultdict(list)
        for season, period, opp, value in allowed or ():
            by_season[int(season)].append((str(period), str(opp), float(value)))
        self.rows: dict = {}
        self.first: dict = {}
        for season, games in by_season.items():
            first = min(p for p, _o, _v in games)
            self.first[season] = first
            self.rows[season] = [{"week": _week_of(p, first), "opponent_team": o,
                                  "position": position, "season_type": "REG", column: v}
                                 for p, o, v in games]
        self._cache: dict = {}
        self._prior: dict = {}

    def _season_prior(self, season: int):
        from . import defensevs as D
        if season not in self._prior:
            rows = self.rows.get(season - 1)
            self._prior[season] = D.ratings(rows, 99) if rows else None
        return self._prior[season]

    def ratings(self, season: int, period: str) -> dict:
        from . import defensevs as D
        rows = self.rows.get(int(season))
        if not rows:
            return {}
        wk = _week_of(period, self.first.get(int(season)))
        key = (int(season), wk)
        if key not in self._cache:
            self._cache[key] = D.ratings(rows, wk, prior=self._season_prior(int(season)))
        return self._cache[key]


def settled_props_from_logs(entries: list[dict], market: str,
                            sport: str = "nfl", min_history: int = 4,
                            limit: int = 30,
                            form_weights: dict | None = None,
                            player_adjust=None, player_record=None,
                            allowed=None,
                            ) -> list[SettledProp]:
    """``entries`` = [{"name", "values": [chronological per-game values]}].
    Same walk as MLB's: project game i from games [:i], settle against
    ``values[i]``, price against the trailing-average naive line.

    INTERCEPTIONS WALK THE PRODUCTION MODEL (engine/passint): each game's
    prop carries the attempts of the games before it (``"companion"``),
    the league's rate over every entry, the book's 0.5, and the
    opponent's takeaway rating built from ``allowed`` — so the AUC the
    store keeps is the number the board will put up, opponent and all."""
    game, opp = _neutral()
    settled: list[SettledProp] = []
    companion = COMPANION.get(market)
    defences = None
    league = None
    if companion:
        from . import passint as _pi
        from . import defensevs as D
        stat = D.stat_for("QB", market) or ""
        column = D.STATS[stat][1][0].split("|")[0] if stat in D.STATS else market
        if allowed is None:
            allowed = getattr(entries, "aux", {}).get("allowed")
        defences = _Defences(allowed, stat, column, _POSITION.get(market, "QB"))
        league = _pi.league_rate([a for e in entries for a in e.get("companion", [])],
                                 [v for e in entries for v in e.get("values", [])])

    for e in entries:
        vals = e.get("values", [])
        comp = e.get("companion") or []
        for i in range(min_history, len(vals)):
            prior = vals[:i][::-1][:limit]          # most-recent-first
            actual = float(vals[i])
            logs = [GameLog(week=len(prior) - j, opponent="", value=float(v))
                    for j, v in enumerate(prior)]
            career = sum(vals[:i]) / i
            line = COUNT_LINE.get(market) or _naive_line(prior[:8])
            aux: dict = {}
            game_i, opp_i = game, opp
            if companion and len(comp) >= i:
                prior_att = comp[:i][::-1][:limit]
                aux = {"pass_att": [GameLog(week=len(prior_att) - j, opponent="", value=float(v))
                                    for j, v in enumerate(prior_att)],
                       "league_int_rate": league}
                opps, seasons, dates = e.get("opps") or [], e.get("seasons") or [], e.get("dates") or []
                if defences is not None and i < len(opps) and i < len(seasons) and i < len(dates):
                    name = opps[i] or "AWAY"
                    rating = defences.ratings(seasons[i], dates[i]).get(name) or {}
                    opp_i = Team(abbr=name, name=name, defense=DefenseProfile(team=name, ratings=rating))
                    game_i = Game(home="HOME", away=name, weather=Weather(dome=True))
            prop = Prop(
                player=e["name"], team="HOME", opponent=opp_i.abbr,
                position=_POSITION.get(market, "WR"), market=market,
                logs=logs, career_avg=career, vs_opponent_avg=None,
                lines=[SportsbookLine("proxy", line, -110, -110)],
                aux=aux,
            )
            mult = player_adjust(e["name"]) if player_adjust else None
            proj = build_projection(prop, game_i, opp_i, sport=sport,
                                    form_weights=form_weights,
                                    player_mult=mult)
            if player_record is not None:
                player_record(e["name"], proj.mean / (mult or 1.0), actual)
            rec = evaluate_prop(prop, proj, allow_synthetic_line=True,
                                game=game_i, sport=sport)
            settled.append(SettledProp(
                player=e["name"], market=market, line=line, odds=rec.odds,
                hit_prob=rec.hit_prob, projection=rec.projection,
                actual=actual, recommended=(rec.grade != "Pass"),
                stake_units=rec.stake_units, side=rec.side, basis="naive",
                grade=rec.grade,
            ))
    return settled


def backtest_from_logs(entries: list[dict], market: str, sport: str = "nfl",
                       min_history: int = 4, limit: int = 30,
                       form_weights: dict | None = None,
                       player_adjust=None, player_record=None,
                       allowed=None,
                       ) -> BacktestReport:
    """Walk forward and aggregate — see ``settled_props_from_logs``."""
    settled = settled_props_from_logs(
        entries, market, sport=sport, min_history=min_history, limit=limit,
        form_weights=form_weights, player_adjust=player_adjust,
        player_record=player_record, allowed=allowed)
    report = evaluate(settled)
    report.total_priced = len(settled)
    return report


def walk(sport: str, entries: list[dict], market: str,
         min_history: int | None = None, **hooks) -> BacktestReport:
    """One door for every fitter, whichever sport it is fitting.

    MLB walks through its own engine (park/ump/Statcast context lives
    there); everything else walks through the generic one. The fitters
    (formfit, playerfit, calibrate) call this instead of choosing a
    harness themselves, so adding a sport's harness is one branch here
    rather than an edit in three fitters."""
    if sport == "mlb":
        from .mlb.backtest import backtest_from_logs as mlb_bt
        return mlb_bt(entries, market,
                      min_history=8 if min_history is None else min_history,
                      **hooks)
    # What `load_entries` loaded beside the entries rides along unasked.
    for k, v in (getattr(entries, "aux", None) or {}).items():
        hooks.setdefault(k, v)
    return backtest_from_logs(entries, market, sport=sport,
                              min_history=4 if min_history is None else min_history,
                              **hooks)
