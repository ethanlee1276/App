"""Walk-forward moneyline backtest against harvested book prices.

The prop backtest answers "does the player model beat the book?"; this answers
the same question for the GAME model. It replays the season chronologically:
for each game with a harvested closing moneyline, team ratings are computed
from games strictly BEFORE that date (same shrinkage as
:mod:`engine.teamrates`), the production pricing (:func:`gamebets
.price_moneyline` on :func:`gamebets.mlb_win_prob` / ``nfl_win_prob``) decides
a side, and the final score settles it.

Honesty notes:
  * Harvested moneylines are the BEST price across books at the snapshot —
    slightly kinder than any single book's close.
  * Doubleheaders collapse to one row (games are keyed by date+matchup), so a
    twin bill contributes a single settled game.
  * The replayed model is ratings-only — no starting pitcher, park, or rest
    context — so this measures the floor of the game model, not the ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .gamebets import SCORING_BASELINE, mlb_win_prob, nfl_win_prob, price_moneyline
from .odds import american_to_decimal

# Same shrinkage as engine.teamrates.compute_team_ratings: early-season records
# are regressed toward league average.
SHRINK = 6.0


def moneyline_closes(conn, sport: str) -> dict:
    """``{(date, home, away): {team: best_odds}}`` — the last harvested
    snapshot on each date is that day's close."""
    q = ("SELECT taken_at, home, away, player, over_odds FROM odds_history "
         "WHERE sport=? AND market='moneyline' ORDER BY taken_at")
    out: dict = {}
    for r in conn.execute(q, (sport,)):
        date = str(r["taken_at"])[:10]
        game = out.setdefault((date, r["home"], r["away"]), {})
        # Ordered by taken_at, so later same-date snapshots overwrite.
        game[r["player"]] = r["over_odds"]
    return out


@dataclass
class MoneylineBacktest:
    sport: str = "mlb"
    games_seen: int = 0        # completed games walked over
    games_quoted: int = 0      # had a harvested price AND enough team history
    n_bets: int = 0
    wins: int = 0
    staked: float = 0.0
    net: float = 0.0
    brier: float = 0.0         # of P(home win) over every quoted game
    home_rate: float = 0.0     # how often home actually won (quoted games)
    mean_home_prob: float = 0.0
    grades: dict = field(default_factory=dict)
    prices: dict = field(default_factory=dict)   # favorite vs underdog picks

    @property
    def roi(self) -> float:
        return (self.net / self.staked) if self.staked else 0.0

    def summary(self) -> str:
        lines = [
            f"{self.sport.upper()} moneyline backtest · real harvested closes",
            f"  Games       {self.games_seen} completed, "
            f"{self.games_quoted} with a book price + team history",
        ]
        if self.games_quoted:
            lines.append(
                f"  Model       Brier {self.brier:.4f}   mean P(home) "
                f"{self.mean_home_prob:.0%} vs actual home wins {self.home_rate:.0%}")
        if self.n_bets:
            lines.append(
                f"  Bets        {self.n_bets} placed, {self.wins} won "
                f"({self.wins / self.n_bets:.1%})  ROI {self.roi:+.1%}  "
                f"net {self.net:+.2f}u")
            for name in ("Strong Play", "Play", "Lean"):
                g = self.grades.get(name)
                if g and g["n_bets"]:
                    roi = g["net"] / g["staked"] if g["staked"] else 0.0
                    lines.append(f"        {name:11} {g['n_bets']:>4} bets, "
                                 f"{g['wins']} won  ROI {roi:+.1%}")
            for name in ("favorite", "underdog"):
                g = self.prices.get(name)
                if g and g["n_bets"]:
                    roi = g["net"] / g["staked"] if g["staked"] else 0.0
                    lines.append(f"        {name:11} {g['n_bets']:>4} bets, "
                                 f"{g['wins']} won  ROI {roi:+.1%}")
        elif self.games_quoted:
            lines.append("  Bets        none graded above Pass")
        if not self.games_quoted:
            lines.append("  No games had both a harvested moneyline and enough "
                         "team history — harvest h2h odds first (harvest_odds.py "
                         "--markets h2h)")
        else:
            lines.append("  Priced vs REAL closing moneylines (best across "
                         "books) — a genuine market-relative result")
        return "\n".join(lines)


def _rating(agg: dict, team: str, baseline: float) -> float | None:
    """Net rating from running (points-for, points-against, games) sums —
    identical math to teamrates.compute_team_ratings."""
    pf, pa, n = agg.get(team, (0.0, 0.0, 0))
    if not n:
        return None
    factor = n / (n + SHRINK)
    off = (pf / n - baseline) * factor
    def_ = (pa / n - baseline) * factor
    return off - def_


def backtest_moneylines(conn, sport: str = "mlb",
                        min_team_games: int = 15) -> MoneylineBacktest:
    """Replay every completed game in the DB, betting only where a harvested
    moneyline exists and both teams have ``min_team_games`` of prior history."""
    closes = moneyline_closes(conn, sport)
    baseline = SCORING_BASELINE.get(sport, 0.0)
    win_prob = mlb_win_prob if sport == "mlb" else nfl_win_prob

    rows = conn.execute(
        "SELECT period, home, away, home_score, away_score FROM games "
        "WHERE sport=? AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "ORDER BY period", (sport,)).fetchall()

    r = MoneylineBacktest(sport=sport)
    agg: dict[str, tuple[float, float, int]] = {}
    sq_err = 0.0
    home_wins = 0
    prob_sum = 0.0

    for row in rows:
        date, home, away = row["period"], row["home"], row["away"]
        hs, as_ = float(row["home_score"]), float(row["away_score"])
        r.games_seen += 1

        quote = closes.get((date, home, away))
        h_net = _rating(agg, home, baseline)
        a_net = _rating(agg, away, baseline)
        enough = (agg.get(home, (0, 0, 0))[2] >= min_team_games
                  and agg.get(away, (0, 0, 0))[2] >= min_team_games)
        home_ml = quote.get(home) if quote else None
        away_ml = quote.get(away) if quote else None

        if enough and home_ml is not None and away_ml is not None:
            wp_home = win_prob(h_net, a_net)
            home_won = hs > as_
            r.games_quoted += 1
            sq_err += (wp_home - (1.0 if home_won else 0.0)) ** 2
            home_wins += 1 if home_won else 0
            prob_sum += wp_home

            rec = price_moneyline(home, away, wp_home,
                                  int(home_ml), int(away_ml))
            if rec.grade != "Pass":
                stake = rec.stake_units if rec.stake_units > 0 else 1.0
                won = home_won == rec.pick_is_home
                gain = ((american_to_decimal(rec.odds) - 1.0) * stake
                        if won else -stake)
                r.n_bets += 1
                r.wins += 1 if won else 0
                r.staked += stake
                r.net += gain
                for key, bucket in ((rec.grade, r.grades),
                                    ("favorite" if rec.odds < 0 else "underdog",
                                     r.prices)):
                    b = bucket.setdefault(key, {"n_bets": 0, "wins": 0,
                                                "staked": 0.0, "net": 0.0})
                    b["n_bets"] += 1
                    b["wins"] += 1 if won else 0
                    b["staked"] += stake
                    b["net"] += gain

        # Only after any bet: today's result joins each team's history.
        pf, pa, n = agg.get(home, (0.0, 0.0, 0))
        agg[home] = (pf + hs, pa + as_, n + 1)
        pf, pa, n = agg.get(away, (0.0, 0.0, 0))
        agg[away] = (pf + as_, pa + hs, n + 1)

    if r.games_quoted:
        r.brier = sq_err / r.games_quoted
        r.home_rate = home_wins / r.games_quoted
        r.mean_home_prob = prob_sum / r.games_quoted
    return r
