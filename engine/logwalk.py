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
                     SportsbookLine)
from .projection import build_projection
from .betting import evaluate_prop

#: Position by market, so the projection's role logic stays sensible.
_POSITION = {"pass_yds": "QB", "rush_yds": "RB",
             "rec_yds": "WR", "receptions": "WR"}


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


def settled_props_from_logs(entries: list[dict], market: str,
                            sport: str = "nfl", min_history: int = 4,
                            limit: int = 30,
                            form_weights: dict | None = None,
                            player_adjust=None, player_record=None
                            ) -> list[SettledProp]:
    """``entries`` = [{"name", "values": [chronological per-game values]}].
    Same walk as MLB's: project game i from games [:i], settle against
    ``values[i]``, price against the trailing-average naive line."""
    game, opp = _neutral()
    settled: list[SettledProp] = []

    for e in entries:
        vals = e.get("values", [])
        for i in range(min_history, len(vals)):
            prior = vals[:i][::-1][:limit]          # most-recent-first
            actual = float(vals[i])
            logs = [GameLog(week=len(prior) - j, opponent="", value=float(v))
                    for j, v in enumerate(prior)]
            career = sum(vals[:i]) / i
            line = _naive_line(prior[:8])
            prop = Prop(
                player=e["name"], team="HOME", opponent="AWAY",
                position=_POSITION.get(market, "WR"), market=market,
                logs=logs, career_avg=career, vs_opponent_avg=None,
                lines=[SportsbookLine("proxy", line, -110, -110)],
            )
            mult = player_adjust(e["name"]) if player_adjust else None
            proj = build_projection(prop, game, opp, sport=sport,
                                    form_weights=form_weights,
                                    player_mult=mult)
            if player_record is not None:
                player_record(e["name"], proj.mean / (mult or 1.0), actual)
            rec = evaluate_prop(prop, proj, allow_synthetic_line=True,
                                game=game, sport=sport)
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
                       player_adjust=None, player_record=None
                       ) -> BacktestReport:
    """Walk forward and aggregate — see ``settled_props_from_logs``."""
    settled = settled_props_from_logs(
        entries, market, sport=sport, min_history=min_history, limit=limit,
        form_weights=form_weights, player_adjust=player_adjust,
        player_record=player_record)
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
    return backtest_from_logs(entries, market, sport=sport,
                              min_history=4 if min_history is None else min_history,
                              **hooks)
