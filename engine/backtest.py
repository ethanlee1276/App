"""Backtesting & calibration harness.

Answers the only question that matters for a betting model: *is it actually
right?* Given settled props (each with the model's projection and hit
probability plus the real outcome), it reports:

  - projection accuracy (MAE / RMSE of projected mean vs actual);
  - probability calibration (are "70%" picks really hitting ~70%?) via
    reliability bins and Expected Calibration Error, plus a Brier score;
  - betting performance of the *recommended* bets (win rate, units, ROI), and
    closing-line value when closing lines are supplied.

``evaluate()`` is pure and unit-tested. ``backtest_from_stats()`` drives it over
real nflverse weeks (needs weekly stats — release-gated, so it uses the same
local-CSV fallback as the rest of the engine).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .odds import american_to_decimal, american_to_prob

# Display order for the per-grade P&L breakdown of the market-relative
# segment. If Strong picks don't beat Lean picks, the model's conviction
# carries no signal and no threshold tuning will conjure one.
GRADE_ORDER = ("Strong Play", "Strong", "Play", "Lean")


def _norm(name: str) -> str:
    s = name.lower().replace("-", " ").replace(".", " ").replace("'", "")
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class SettledProp:
    player: str
    market: str
    line: float
    odds: int
    hit_prob: float          # model's probability that THE BET IT MADE wins
    projection: float        # model's projected mean
    actual: float            # what actually happened
    recommended: bool = False
    stake_units: float = 1.0
    closing_line: float | None = None
    # Which side the model backed. This matters everywhere: ``hit_prob`` is the
    # probability the *chosen side* wins, so scoring it against "did the over
    # hit" grades every UNDER backwards — both the calibration bins and the P&L.
    side: str = "OVER"
    # What priced this prop: "book" (a real harvested line) or "naive" (the
    # baseline). Only the book-priced subset says anything about beating the
    # market, so P&L is reported per basis rather than blended out of sight.
    basis: str = "naive"
    # The grade the pipeline attached at bet time (Strong/Play/Lean). Lets the
    # market-relative P&L answer "do higher-conviction picks actually win
    # more?" in the product's own vocabulary.
    grade: str = ""

    @property
    def over_hit(self) -> int | None:
        """1 if the Over hit, 0 if it missed, None on a push (actual == line)."""
        if self.actual > self.line:
            return 1
        if self.actual < self.line:
            return 0
        return None

    @property
    def outcome(self) -> int | None:
        """1 if **the bet** won, 0 if it lost, None on a push."""
        over = self.over_hit
        if over is None:
            return None
        return over if (self.side or "OVER").upper() == "OVER" else 1 - over


@dataclass
class CalibrationBin:
    lo: float
    hi: float
    n: int
    mean_pred: float
    hit_rate: float


@dataclass
class BacktestReport:
    n: int = 0
    # projection accuracy
    mae: float = 0.0
    rmse: float = 0.0
    # probability quality
    brier: float = 0.0
    ece: float = 0.0
    bins: list[CalibrationBin] = field(default_factory=list)
    # betting performance (recommended bets only)
    n_bets: int = 0
    wins: int = 0
    pushes: int = 0
    win_rate: float = 0.0
    units_staked: float = 0.0
    net_units: float = 0.0
    roi: float = 0.0
    avg_clv: float | None = None
    # (predicted probability, 0/1 outcome) for every decided prop — the input
    # the calibration fitter needs (pushes excluded).
    pairs: list = field(default_factory=list)
    # How many props were priced against a real harvested book line rather than
    # the naive baseline. ROI only means "would this have beaten the book" to
    # the extent this is high, so it's reported rather than left implicit.
    used_real_lines: int = 0
    total_priced: int = 0
    # Betting P&L split by pricing basis ("book" vs "naive"). The blended ROI
    # buries the only market-relative number inside the baseline noise; this
    # keeps the subset that actually answers "did we beat the book" visible.
    segments: dict = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"Backtest over {self.n} settled props",
            f"  Projection  MAE {self.mae:.2f}   RMSE {self.rmse:.2f}",
            f"  Calibration Brier {self.brier:.4f}   ECE {self.ece:.3f}",
        ]
        for b in self.bins:
            if b.n:
                lines.append(f"    p {b.lo:.1f}-{b.hi:.1f}: predicted {b.mean_pred:.0%} "
                             f"→ actual {b.hit_rate:.0%}  (n={b.n})")
        if self.n_bets:
            lines.append(
                f"  Bets        {self.n_bets} placed, {self.wins} won "
                f"({self.win_rate:.1%})  ROI {self.roi:+.1%}  net {self.net_units:+.2f}u")
            # The book-priced subset is the only market-relative P&L; break it
            # out so it can't hide inside the baseline-priced majority.
            if len(self.segments) > 1 or "book" in self.segments:
                labels = {"book": "vs REAL book lines", "naive": "vs naive baseline"}
                for basis in ("book", "naive"):
                    g = self.segments.get(basis)
                    if not g or not g["n_bets"]:
                        continue
                    lines.append(
                        f"    {labels.get(basis, basis):18} {g['n_bets']:>4} bets, "
                        f"{g['wins']} won ({g['win_rate']:.1%})  "
                        f"ROI {g['roi']:+.1%}  net {g['net']:+.2f}u")
                    # Side split for the market-relative subset only — the
                    # first place a real pocket of edge would show itself.
                    if basis == "book" and len(g.get("sides", {})) > 1:
                        for sd_name in ("OVER", "UNDER"):
                            sd = g["sides"].get(sd_name)
                            if sd and sd["n_bets"]:
                                lines.append(
                                    f"        {sd_name:5} {sd['n_bets']:>4} bets, "
                                    f"{sd['wins']} won  ROI {sd['roi']:+.1%}")
                    # Grade split: does the model's own conviction (what the
                    # site labels Strong/Play/Lean) predict realized ROI?
                    if basis == "book" and len(g.get("grades", {})) > 1:
                        names = [n for n in GRADE_ORDER if n in g["grades"]]
                        names += sorted(set(g["grades"]) - set(GRADE_ORDER))
                        for gr_name in names:
                            gr = g["grades"][gr_name]
                            if gr["n_bets"]:
                                lines.append(
                                    f"        {gr_name:6} {gr['n_bets']:>4} bets, "
                                    f"{gr['wins']} won  ROI {gr['roi']:+.1%}")
            if self.avg_clv is not None:
                lines.append(f"  Closing-line value  {self.avg_clv:+.2f} pts avg")
        # Say plainly what the ROI above is measured against — an ROI beating a
        # naive baseline is a far weaker claim than one beating real book prices.
        if self.total_priced:
            share = self.used_real_lines / self.total_priced
            if self.used_real_lines == 0:
                lines.append("  Priced vs a NAIVE baseline line — this shows predictive "
                             "skill, NOT an edge over the market")
            elif share < 0.999:
                lines.append(f"  Priced vs real book lines on {self.used_real_lines}"
                             f"/{self.total_priced} ({share:.0%}); the rest used the "
                             f"naive baseline")
            else:
                lines.append("  Priced vs REAL book lines — this ROI is a genuine "
                             "market-relative result")
        return "\n".join(lines)


def _calibration(settled: list[SettledProp], n_bins: int = 5) -> tuple[list[CalibrationBin], float, float]:
    """Reliability bins, Brier score and Expected Calibration Error over props
    that had a decision (no push)."""
    decided = [s for s in settled if s.outcome is not None]
    if not decided:
        return [], 0.0, 0.0

    brier = sum((s.hit_prob - s.outcome) ** 2 for s in decided) / len(decided)

    bins: list[CalibrationBin] = []
    ece = 0.0
    for i in range(n_bins):
        lo, hi = i / n_bins, (i + 1) / n_bins
        # last bin is inclusive of 1.0
        members = [s for s in decided if (lo <= s.hit_prob < hi) or (i == n_bins - 1 and s.hit_prob == 1.0)]
        if not members:
            bins.append(CalibrationBin(lo, hi, 0, 0.0, 0.0))
            continue
        mean_pred = sum(s.hit_prob for s in members) / len(members)
        hit_rate = sum(s.outcome for s in members) / len(members)
        bins.append(CalibrationBin(lo, hi, len(members), mean_pred, hit_rate))
        ece += (len(members) / len(decided)) * abs(mean_pred - hit_rate)

    return bins, brier, ece


def evaluate(settled: list[SettledProp], n_bins: int = 5) -> BacktestReport:
    r = BacktestReport(n=len(settled))
    if not settled:
        return r

    # Projection accuracy.
    errs = [s.projection - s.actual for s in settled]
    r.mae = sum(abs(e) for e in errs) / len(errs)
    r.rmse = math.sqrt(sum(e * e for e in errs) / len(errs))

    # Calibration.
    r.bins, r.brier, r.ece = _calibration(settled, n_bins)
    # Calibration pairs are stated on the OVER side, always.
    #
    # ``hit_prob`` is the probability of whichever side the model backed,
    # but the fitted correction is applied to P(over the line) inside
    # each evaluator. On a two-sided market the model picks both sides
    # roughly evenly and the mismatch washes out; on a one-sided market
    # it does not. Home runs are the pathological case: the model backs
    # the under on essentially every prop, so the fit learned "the UNDER
    # probability is understated" and then applied that to the OVER —
    # leaving P(home run) 2.8× too high and the fitted ECE stuck at 0.16.
    # Restating both sides as "did the over hit" makes the thing fitted
    # and the thing corrected the same quantity.
    r.pairs = [(s.hit_prob if (s.side or "OVER").upper() == "OVER"
                else 1.0 - s.hit_prob, s.over_hit)
               for s in settled if s.over_hit is not None]

    # Betting performance on recommended bets, overall and per pricing basis.
    bets = [s for s in settled if s.recommended]
    staked = won = net = 0.0
    wins = pushes = 0
    clvs = []
    seg: dict[str, dict] = {}
    for s in bets:
        g = seg.setdefault((s.basis or "naive"),
                           {"n_bets": 0, "wins": 0, "pushes": 0,
                            "staked": 0.0, "net": 0.0, "sides": {},
                            "grades": {}})
        side = seg[s.basis or "naive"]["sides"].setdefault(
            (s.side or "OVER").upper(),
            {"n_bets": 0, "wins": 0, "staked": 0.0, "net": 0.0})
        gbucket = g["grades"].setdefault(
            s.grade or "ungraded",
            {"n_bets": 0, "wins": 0, "staked": 0.0, "net": 0.0})
        g["n_bets"] += 1
        side["n_bets"] += 1
        gbucket["n_bets"] += 1
        oc = s.outcome
        if oc is None:
            pushes += 1
            g["pushes"] += 1
            continue
        stake = s.stake_units if s.stake_units > 0 else 1.0
        staked += stake
        g["staked"] += stake
        side["staked"] += stake
        gbucket["staked"] += stake
        if oc == 1:
            wins += 1
            g["wins"] += 1
            side["wins"] += 1
            gbucket["wins"] += 1
            payout = (american_to_decimal(s.odds) - 1.0) * stake
            net += payout
            g["net"] += payout
            side["net"] += payout
            gbucket["net"] += payout
        else:
            net -= stake
            g["net"] -= stake
            side["net"] -= stake
            gbucket["net"] -= stake
        if s.closing_line is not None:
            # On an over you want the line to rise after you bet it; on an under
            # you want it to fall. Same sign convention would score unders
            # backwards, exactly as the outcome bug did.
            move = s.closing_line - s.line
            clvs.append(move if (s.side or "OVER").upper() == "OVER" else -move)

    graded_bets = len(bets) - pushes
    r.n_bets = len(bets)
    r.wins = wins
    r.pushes = pushes
    r.win_rate = (wins / graded_bets) if graded_bets else 0.0
    r.units_staked = staked
    r.net_units = net
    r.roi = (net / staked) if staked else 0.0
    for basis, g in seg.items():
        g["roi"] = (g["net"] / g["staked"]) if g["staked"] else 0.0
        graded = g["n_bets"] - g["pushes"]
        g["win_rate"] = (g["wins"] / graded) if graded else 0.0
        for sd in g["sides"].values():
            sd["roi"] = (sd["net"] / sd["staked"]) if sd["staked"] else 0.0
        for gr in g["grades"].values():
            gr["roi"] = (gr["net"] / gr["staked"]) if gr["staked"] else 0.0
    r.segments = seg
    r.avg_clv = (sum(clvs) / len(clvs)) if clvs else None
    return r


# --- real-data driver -------------------------------------------------------
def settle_recommendations(recommendations: list[dict],
                           actuals: dict[tuple[str, str], float]) -> list[SettledProp]:
    """Pair pipeline recommendation dicts with actual results.

    ``actuals`` maps (normalized player, market) -> the stat the player posted.
    """
    out = []
    for rec in recommendations:
        key = (_norm(rec["player"]), rec["market"])
        if key not in actuals:
            continue
        out.append(SettledProp(
            player=rec["player"],
            market=rec["market"],
            line=rec["line"],
            odds=rec["odds"],
            hit_prob=rec["hit_prob"],
            projection=rec["projection"],
            actual=actuals[key],
            recommended=rec["recommended"],
            stake_units=rec.get("stake_units", 1.0),
            side=rec.get("side", "OVER"),
            grade=rec.get("grade", ""),
        ))
    return out


def backtest_from_stats(season: int, weeks, config=None, model=None) -> BacktestReport:
    """Walk-forward backtest over real nflverse weeks.

    For each week, projections are built from prior weeks only, then settled
    against that week's actual box score. Requires weekly stats; lines are the
    engine's recent-form proxy unless an odds history is wired in, so betting
    ROI is measured against that proxy market (projection accuracy and
    calibration are source-independent).
    """
    from .sources.nflverse import (
        build_slate, load_weekly_stats, MARKET_COLUMNS, _s, _f,
    )
    from .pipeline import run_slate
    from .rules import RuleConfig

    config = config or RuleConfig()
    stats = load_weekly_stats(season)

    all_settled: list[SettledProp] = []
    for w in weeks:
        try:
            slate = build_slate(season, w, upto_week=w)
        except Exception:
            continue
        result = run_slate(slate, config, model=model, allow_synthetic_line=True)

        actuals: dict[tuple[str, str], float] = {}
        for row in stats:
            if int(_f(row, "week", default=0)) != w:
                continue
            name = _s(row, "player_display_name", "player_name", "full_name")
            for market, cols in MARKET_COLUMNS.items():
                actuals[(_norm(name), market)] = _f(row, *cols)

        all_settled.extend(settle_recommendations(result["recommendations"], actuals))

    return evaluate(all_settled)
