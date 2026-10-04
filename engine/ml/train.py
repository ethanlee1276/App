"""Train the learned multiplier model from historical nflverse weeks.

Walk-forward and leakage-free: for each week, a player's recent-form baseline is
computed from prior weeks only, the game-context features come from that week,
and the target is the log-ratio of the actual result to the baseline:

    y = log((actual + .5) / (baseline + .5))

Per-market ridge regressions then learn how matchup, spread, total and weather
move production off the baseline. ``build_examples`` is pure (operates on rows +
prebuilt games) so it is fully unit-testable without the network.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..form import compute_form
from ..models import Prop, DefenseProfile, GameLog
from ..sources.nflverse import (
    build_defense_profiles, POSITION_MARKETS, MARKET_COLUMNS, _s, _f,
)
from .features import extract_features, vectorize, FEATURE_ORDER
from .model import MultiplierModel, ridge_fit


def _pseudo_prop(team: str, opp: str, market: str, role: str) -> Prop:
    return Prop(player="", team=team, opponent=opp, position="", market=market,
                logs=[], career_avg=0.0, vs_opponent_avg=None, lines=[], usage_role=role)


def build_examples(stats: list[dict], week_games: dict[int, list],
                   weeks, min_history: int = 4) -> dict[str, tuple[list, list]]:
    """Assemble per-market training data. ``week_games`` maps week -> [Game]."""
    by_player: dict[str, list[dict]] = {}
    for r in stats:
        by_player.setdefault(_s(r, "player_display_name", "player_name", "full_name"), []).append(r)

    data: dict[str, tuple[list, list]] = {}
    for w in weeks:
        gteam = {}
        for g in week_games.get(w, []):
            gteam[g.home] = g
            gteam[g.away] = g
        if not gteam:
            continue
        defenses = build_defense_profiles(stats, upto_week=w)

        for r in stats:
            if int(_f(r, "week", default=0)) != w:
                continue
            pos = _s(r, "position", "position_group").upper()
            if pos not in POSITION_MARKETS:
                continue
            name = _s(r, "player_display_name", "player_name", "full_name")
            team = _s(r, "recent_team", "team")
            opp = _s(r, "opponent_team", "opponent")
            g = gteam.get(team)
            if not g or not opp:
                continue

            prior_rows = [pr for pr in by_player.get(name, [])
                          if 0 < int(_f(pr, "week", default=0)) < w]
            if len(prior_rows) < min_history:
                continue
            prior_rows.sort(key=lambda pr: int(_f(pr, "week", default=0)), reverse=True)

            defense = defenses.get(opp) or DefenseProfile(team=opp)
            for market, role in POSITION_MARKETS[pos]:
                cols = MARKET_COLUMNS[market]
                actual = _f(r, *cols)
                vals = [_f(pr, *cols) for pr in prior_rows]
                logs = [GameLog(week=int(_f(pr, "week", default=0)), opponent="", value=v)
                        for pr, v in zip(prior_rows, vals)]
                form = compute_form(logs, sum(vals) / len(vals), None)
                baseline = form.mean
                if baseline <= 0:
                    continue
                feat = extract_features(_pseudo_prop(team, opp, market, role), g, defense)
                y = math.log((actual + 0.5) / (baseline + 0.5))
                X, Y = data.setdefault(market, ([], []))
                X.append(vectorize(feat))
                Y.append(y)
    return data


@dataclass
class TrainReport:
    per_market: dict            # market -> {n, rmse_log, coefs}

    def summary(self) -> str:
        out = ["Trained learned multiplier model"]
        for market, info in sorted(self.per_market.items()):
            out.append(f"  {market:12} n={info['n']:<5} in-sample RMSE(log)={info['rmse_log']:.4f}")
            for name, w in zip(FEATURE_ORDER, info["coefs"]):
                if name == "intercept":
                    continue
                out.append(f"      {name:8} {w:+.3f}")
        return "\n".join(out)


def fit(data: dict[str, tuple[list, list]], l2: float = 1.0,
        min_examples: int = 40) -> tuple[MultiplierModel, TrainReport]:
    coefs: dict[str, list[float]] = {}
    report: dict = {}
    for market, (X, Y) in data.items():
        if len(X) < min_examples:
            continue
        w = ridge_fit(X, Y, l2=l2)
        # in-sample fit quality
        preds = [sum(wi * xi for wi, xi in zip(w, row)) for row in X]
        rmse = math.sqrt(sum((p - y) ** 2 for p, y in zip(preds, Y)) / len(Y))
        coefs[market] = w
        report[market] = {"n": len(X), "rmse_log": rmse, "coefs": w}
    model = MultiplierModel(feature_order=FEATURE_ORDER, coefs=coefs,
                            meta={"l2": l2})
    return model, TrainReport(report)


def train(season: int, weeks, l2: float = 1.0, min_history: int = 4,
          min_examples: int = 40) -> tuple[MultiplierModel, TrainReport]:
    """Load real nflverse data and fit. Needs weekly stats (release-gated)."""
    from ..sources.nflverse import load_weekly_stats, build_games
    stats = load_weekly_stats(season)
    week_games = {w: build_games(season, w) for w in weeks}
    data = build_examples(stats, week_games, weeks, min_history=min_history)
    model, report = fit(data, l2=l2, min_examples=min_examples)
    model.meta = {"season": season, "weeks": list(weeks), "l2": l2}
    return model, report
