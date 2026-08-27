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
# segment. If higher grades don't beat lower ones, the model's conviction
# carries no signal and no threshold tuning will conjure one. The letter
# grades are the current ladder (docs/NFL_MODEL.md §10); the word grades
# cover historical journal entries from before the regrade.
GRADE_ORDER = ("A+", "A", "B+", "Strong Play", "Strong", "Play", "Lean")

#: Bets behind a grade band before its calibration is worth printing.
#: Under this, "claimed 68% → landed 50%" is two coin flips.
GRADE_MIN_N = 20

#: How far a band may land under what it claimed before it is called
#: overconfident. Five points is larger than ordinary sampling noise at
#: GRADE_MIN_N and smaller than a gap that would cost real money.
OVERCONFIDENT = 0.05


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
    #: The model's UNTEMPERED probability for the side it backed. The
    #: calibration fitter must learn on this, not on hit_prob — see the
    #: pairs comment in evaluate(). None means "not recorded" (an older
    #: caller, a fixture), NOT a probability of zero — the same
    #: distinction that made the home-run prior read a measured .000
    #: career as a missing one.
    raw_prob: float | None = None
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
    #: Calibration per grade band — {grade: {n, claimed, landed, gap}}.
    #: Needs no harvested line, so it is the only reading of the grade
    #: ladder available on a database with no stored prop closes.
    grade_calibration: dict = field(default_factory=dict)

    # Betting P&L split by pricing basis ("book" vs "naive"). The blended ROI
    # buries the only market-relative number inside the baseline noise; this
    # keeps the subset that actually answers "did we beat the book" visible.
    segments: dict = field(default_factory=dict)

    def skill(self) -> dict | None:
        """Brier is meaningless without the number it has to beat.

        "Brier 0.2373" reads like a score out of something. It is not. The
        bar is what you would score by ignoring the model entirely and
        predicting the base rate every time — p(1−p) — and on a 57% market
        that is 0.245. Beating it by 0.008 is a very different claim from
        the one "Brier 0.2373, ECE 0.024" appears to make.

        SHARPNESS is the other half, and calibration hides it completely. A
        model that answers "about 50%" to everything is perfectly
        calibrated and perfectly useless, and it shows up here as a large
        share of forecasts hugging the base rate. That matters directly for
        betting: an unsharp model disagrees with a confident market by a
        lot, in both directions, and every one of those disagreements looks
        like an edge without being one.
        """
        pairs = [(p, o) for p, o in self.pairs if p is not None and o is not None]
        if len(pairs) < 100:
            return None
        base = sum(o for _, o in pairs) / len(pairs)
        base_brier = base * (1 - base)
        if base_brier <= 0:
            return None
        near = sum(1 for p, _ in pairs if abs(p - base) <= 0.05)
        return {"n": len(pairs), "base_rate": base, "base_brier": base_brier,
                "skill": 1 - self.brier / base_brier,
                "hedged": near / len(pairs)}

    def summary(self) -> str:
        lines = [
            f"Backtest over {self.n} settled props",
            f"  Projection  MAE {self.mae:.2f}   RMSE {self.rmse:.2f}",
            f"  Calibration Brier {self.brier:.4f}   ECE {self.ece:.3f}",
        ]
        sk = self.skill()
        if sk:
            lines.append(
                f"  Skill       base rate {sk['base_rate']:.1%} → "
                f"always-guess Brier {sk['base_brier']:.4f}; "
                f"model beats it by {sk['skill']:+.1%}")
            lines.append(
                f"  Sharpness   {sk['hedged']:.0%} of forecasts sit within "
                f"5pts of the base rate"
                + ("  ← hedging, not forecasting" if sk["hedged"] > 0.5 else ""))
        for b in self.bins:
            if b.n:
                lines.append(f"    p {b.lo:.1f}-{b.hi:.1f}: predicted {b.mean_pred:.0%} "
                             f"→ actual {b.hit_rate:.0%}  (n={b.n})")
        # DOES CONVICTION MEAN ANYTHING — printed above the P&L, because
        # it is the reading that survives having no harvested lines, and
        # on a database without them it is the ONLY examination the grade
        # ladder gets. A band that lands well under what it claimed is
        # overconfident, and it sits at the top of the board.
        if self.grade_calibration:
            names = [n for n in GRADE_ORDER if n in self.grade_calibration]
            names += sorted(set(self.grade_calibration) - set(GRADE_ORDER))
            shown = [(n, self.grade_calibration[n]) for n in names
                     if self.grade_calibration[n]["n"] >= GRADE_MIN_N]
            if shown:
                lines.append("  Conviction  claimed vs landed, by grade "
                             "(no book line needed)")
                for name, g in shown:
                    flag = ("  ⚠️  overconfident"
                            if g["gap"] <= -OVERCONFIDENT else "")
                    lines.append(
                        f"    {name:12} {g['n']:>4} bets   claimed "
                        f"{g['claimed']:.1%} → landed {g['landed']:.1%}   "
                        f"{g['gap']:+.1%}{flag}")
                if len(shown) > 1:
                    top, bottom = shown[0][1], shown[-1][1]
                    if top["landed"] <= bottom["landed"]:
                        lines.append(
                            f"    ⚠️  the top band lands no more often than "
                            f"the bottom one — this ladder is a ranking, "
                            f"not a conviction")
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


def _grade_calibration(bets: list) -> dict:
    """``{grade: {n, claimed, landed, gap}}`` over settled recommendations.

    ``claimed`` is the mean probability the model attached to the side it
    backed; ``landed`` is how often that side actually won. A grade whose
    gap is strongly negative is overconfident — it promises more than it
    delivers, and it sits at the TOP of the board where it does the most
    damage.

    Pushes are dropped rather than counted as halves: a push is not a
    wrong forecast and averaging it in drags every band toward 50%.
    """
    out: dict = {}
    for s in bets:
        decided = s.outcome
        if decided is None:
            continue
        g = out.setdefault(s.grade or "ungraded",
                           {"n": 0, "claimed": 0.0, "wins": 0})
        g["n"] += 1
        g["claimed"] += float(s.hit_prob)
        g["wins"] += int(decided)
    for g in out.values():
        g["claimed"] = round(g["claimed"] / g["n"], 4) if g["n"] else 0.0
        g["landed"] = round(g["wins"] / g["n"], 4) if g["n"] else 0.0
        g["gap"] = round(g["landed"] - g["claimed"], 4)
    return out


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
    # Calibration pairs are the model's RAW probability, stated on the
    # OVER side, always. Both halves of that matter and each was a bug.
    #
    # The SIDE half: hit_prob is the probability of whichever side the
    # model backed, while the fitted correction is applied to P(over the
    # line) inside each evaluator. On a two-sided market the model picks
    # both sides roughly evenly and the mismatch washes out; on a
    # one-sided market it does not.
    #
    # The RAW half: hit_prob is also the TEMPERED probability — shrunk
    # toward the market by temper_edge — and the correction is applied to
    # the untempered one. Home runs are the pathological case for both.
    # The model backs the under on essentially every prop, and against
    # the backtest's synthetic 0.5 fair a raw 0.90 under shrinks to 0.62
    # at the Tier 3 rate, which restates to P(over) = 0.38 against a real
    # rate near 0.10. The fitter saw a 22-point optimistic lean that the
    # projection did not have, pinned the temperature at the floor of its
    # search range, and reported the market unreliable — while
    # hr_diagnose, reading the raw probability directly, measured the
    # same engine at 1.1x. Two tools disagreeing about one model was the
    # tell: the fit was learning on a quantity nobody prices.
    def _raw_over(s):
        # `is None` = not recorded, so fall back to the tempered number
        # rather than dropping the row. A raw 0.0 is a probability.
        p = s.hit_prob if s.raw_prob is None else s.raw_prob
        return p if (s.side or "OVER").upper() == "OVER" else 1.0 - p

    r.pairs = [(_raw_over(s), s.over_hit)
               for s in settled if s.over_hit is not None]

    # DOES CONVICTION MEAN ANYTHING? Calibration per grade band, and
    # unlike the P&L split below this does NOT need a harvested book
    # line: it asks whether a pick the board calls elite actually lands
    # more often than one it calls ordinary, and whether it lands as
    # often as it CLAIMED. Both are facts about outcomes, not prices.
    #
    # It matters most exactly where the P&L cannot reach. On a database
    # with no harvested props every bet is priced against the naive
    # baseline, the market-relative segment is empty, and the grade
    # ladder goes completely unexamined — which is the state this
    # machine was in when the question "are we ready to fire on elite
    # picks" was asked. A ladder nobody has checked is a ranking, not a
    # conviction.
    r.grade_calibration = _grade_calibration(
        [s for s in settled if s.recommended])

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
            raw_prob=rec.get("raw_prob"),
            projection=rec["projection"],
            actual=actuals[key],
            recommended=rec["recommended"],
            stake_units=rec.get("stake_units", 1.0),
            side=rec.get("side", "OVER"),
            grade=rec.get("grade", ""),
            # THE BOOK NAME DECIDES THE BASIS, rather than a flag carried
            # alongside it. `build_slate` stamps "proxy" on the recent-form
            # line it invents; a harvested close carries the real book's
            # name. Reading the basis off the line the pipeline ACTUALLY
            # priced against means the two cannot drift apart — there is
            # no second place to forget to update.
            basis=_basis_of(rec.get("book")),
        ))
    return out


#: What `engine.sources.nflverse.build_slate` stamps on the recent-form
#: line it invents when no book has posted.
PROXY_BOOK = "proxy"


def _basis_of(book) -> str:
    return "naive" if (not book or str(book) == PROXY_BOOK) else "book"


def apply_real_lines(slate, real_lines: dict) -> int:
    """Reprice a slate's props against harvested closes. Returns the count.

    THE STEP THAT WAS MISSING, and it made the purchase pointless. The
    NFL walk-forward has always priced against `build_slate`'s proxy — a
    recent-form baseline at a synthetic -110 — and its own docstring said
    "swap in an odds feed to price against real books" as though somebody
    had. Nobody had: `backtest_from_stats` had no parameter to pass one
    through, so 11,772 purchased `receptions` closes could sit in
    `odds_history` with nothing able to read them.

    Keyed on the GAME'S DATE, taken from the week's schedule rather than
    guessed from the week number: a week holds a Thursday, a Sunday and a
    Monday, they are three different closes, and only the days actually
    harvested should join.

    A prop with no harvested close KEEPS ITS PROXY and stays `basis:
    naive` — the report segments the two apart, so a partial harvest
    produces a smaller honest book-priced sample beside the baseline
    rather than a blend that is neither.
    """
    from .models import SportsbookLine
    from .odds import pair_is_sane
    if not real_lines:
        return 0
    date_of: dict[str, str] = {}
    for g in getattr(slate, "games", ()) or ():
        if getattr(g, "date", ""):
            date_of[g.home] = g.date
            date_of[g.away] = g.date
    swapped = 0
    for prop in getattr(slate, "props", ()) or ():
        date = date_of.get(prop.team)
        if not date:
            continue
        quote = real_lines.get((_norm(prop.player), prop.market, date))
        if not quote:
            continue
        try:
            line = float(quote["line"])
        except (KeyError, TypeError, ValueError):
            continue
        over = int(quote.get("over_odds") or 0)
        under = int(quote.get("under_odds") or 0)
        if not over:
            # 0 is the parser's word for "not quoted". Inventing the
            # missing side at -110 is what put phantom edges on markets
            # nobody could bet — see engine.mlb.backtest.
            continue
        if under and not pair_is_sane(over, under):
            under = 0
        prop.lines = [SportsbookLine(book=str(quote.get("book") or "book"),
                                     line=line, over_odds=over,
                                     under_odds=under)]
        swapped += 1
    return swapped


def backtest_from_stats(season: int, weeks, config=None, model=None,
                        use_team_context: bool = False,
                        team_context_mode: str = "level",
                        real_lines: dict | None = None) -> BacktestReport:
    """Walk-forward backtest over real nflverse weeks.

    For each week, projections are built from prior weeks only, then settled
    against that week's actual box score. Requires weekly stats.

    ``real_lines`` maps ``(normalized player, market, YYYY-MM-DD)`` to a
    harvested close (`engine.db.closing_odds_by_date`, one market at a
    time). Props it covers are priced against the real book number and
    counted `basis: book`; everything else keeps `build_slate`'s
    recent-form proxy at a synthetic -110 and counts `basis: naive`. The
    report segments the two, because only the first says anything about
    beating a market and blending them would hide which is which.

    Without it — which is every call this function had until 2026-08-27 —
    the ROI is measured against that proxy. Projection accuracy and
    calibration are source-independent and stand either way.
    """
    from .sources.nflverse import (
        build_slate, load_weekly_stats, MARKET_COLUMNS, _s, _f,
    )
    from .pipeline import run_slate
    from .rules import RuleConfig

    config = config or RuleConfig()
    stats = load_weekly_stats(season)

    # NFL Phase 2. Team context is rebuilt for EVERY week from weeks
    # STRICTLY BEFORE it. Reusing one season-average profile across the
    # loop would let week 8 price itself with week 15's numbers — the
    # backtest would look excellent and none of it would survive contact
    # with a live Sunday, because in week 8 those games have not happened.
    ctx_by_week: dict[int, dict] = {}
    if use_team_context:
        from . import db as _db
        from .teamcontext import league_means, profiles_through
        _hc = _db.connect()
        for w in weeks:
            profs = profiles_through(_hc, season, f"{int(w):03d}")
            if profs:
                ctx_by_week[w] = {"profiles": profs,
                                  "league": league_means(profs),
                                  "mode": team_context_mode}
                if team_context_mode == "drift":
                    from .teamcontext import drift_reference
                    ctx_by_week[w]["baseline"] = drift_reference(
                        _hc, season, f"{int(w):03d}")

    all_settled: list[SettledProp] = []
    repriced = props_seen = 0
    for w in weeks:
        try:
            slate = build_slate(season, w, upto_week=w)
        except Exception:
            continue
        # getattr, because this is BOOKKEEPING and bookkeeping must never
        # be the thing that kills a measurement. If a slate really lost
        # its props the run reports n=0 and says so loudly; a crash here
        # would only obscure that.
        props_seen += len(getattr(slate, "props", ()) or ())
        repriced += apply_real_lines(slate, real_lines or {})
        result = run_slate(slate, config, model=model, allow_synthetic_line=True,
                           team_context=ctx_by_week.get(w))

        actuals: dict[tuple[str, str], float] = {}
        for row in stats:
            if int(_f(row, "week", default=0)) != w:
                continue
            name = _s(row, "player_display_name", "player_name", "full_name")
            for market, cols in MARKET_COLUMNS.items():
                actuals[(_norm(name), market)] = _f(row, *cols)

        all_settled.extend(settle_recommendations(result["recommendations"], actuals))

    report = evaluate(all_settled)
    report.used_real_lines, report.total_priced = repriced, props_seen
    return report
