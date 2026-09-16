"""Replay the Pick of the Day over stored closes: would it have paid?

Ethan, 2026-09-16: "you should not stop until you confirm that the Pick
of the Day we show every day is elite and worth betting on." That is a
measurement, not a feature, and nothing in this repository made it. The
sharp-anchor replay (`backtest_sharp_anchor`) grades the METHOD — every
price disagreement it can find, a few hundred bets a season. This grades
the PRODUCT: one pick a day, chosen by `potd.choose` under its own band,
its own EV floor and its own evidence ladder, locked for the day the way
`ledger.log_pick_of_the_day` locks it, and settled by the final score.

WHY THE TWO CAN DISAGREE, and why the second number is the one that
matters. The method's measured edge on this box's MLB data runs
BACKWARDS in EV: bets under 4% EV returned +29.3% and bets over 8%
returned -16.8%. The Pick of the Day does not take every bet — it takes
the single best one per day, ranked on the witness first and the edge
second (`potd.rank_key`), which is a different sample of the same pool
and can land anywhere in that spread. Grading the method and calling it
the product's number would be assuming the answer.

WHAT THIS CAN AND CANNOT SEE
  * MONEYLINES ONLY. It needs a sharp book's two-way close AND a soft
    book's price for the same side; `odds_history` stores that pair for
    the moneyline. Spreads and totals are stored as closes
    (`game_line_closes`) but without a sharp pair to de-vig, so the
    evidence tier they would reach here is not the tier they reach in
    production. Including them would measure a different selector.
  * NO EXCHANGE TIER. Kalshi is read live and never stored, so the top
    rung of `potd.EVIDENCE` cannot appear in a replay. Production ranks
    an exchange row ABOVE a sharp one, so a day this replay gives to a
    sharp row may in production have gone to an exchange row. The
    replay is therefore a floor on the selector, not a copy of it.
  * CLOSE AGAINST CLOSE. Both sides of every comparison are closing
    numbers, and soft books have mostly converged to sharp ones by
    then. The live board acts earlier, when the gaps are wider. Same
    caveat `backtest_sharp_anchor` carries, for the same reason.
  * `bettable` IS ASSUMED. In production that is `calibrate.is_reliable`
    for the market, evaluated at build time against the store as it was
    that day. It cannot be reconstructed, so every replayed row is
    admitted as reliable and the count of days is an UPPER bound.

None of those make the number useless. They make it a floor with the
reasons written down, which is the only kind of backtest worth reading.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .odds import american_to_decimal, devig_two_way
from .gamebacktest import close_for, moneyline_closes


@dataclass
class PotdReplay:
    """One sport's replay, and everything needed to argue with it."""
    sport: str = "mlb"
    sharp: str = "Pinnacle"
    rank_auc: float | None = None
    auc_supplied: bool = False   # the caller asked a what-if; see `replay_potd`
    games_seen: int = 0
    games_priced: int = 0        # had both a sharp pair and a soft price
    days_seen: int = 0           # days with at least one priced game
    days_with_pick: int = 0
    days_with_only_a_lean: int = 0
    days_blank: int = 0
    n_bets: int = 0
    wins: int = 0
    staked: float = 0.0
    net: float = 0.0
    fair_sum: float = 0.0        # what the fairs said would happen
    ev_sum: float = 0.0
    census: dict = field(default_factory=dict)
    tiers: dict = field(default_factory=dict)
    prices: dict = field(default_factory=dict)
    gains: list = field(default_factory=list)
    # THE COUNTERFACTUAL, SETTLED SEPARATELY. On a day nothing cleared,
    # `build` still shows the best row on the board and calls it a lean.
    # Ethan asked for a pick every single day; the open question is
    # whether betting those leans makes money or gives back what the
    # qualifying picks earn. Kept in its own counters and never mixed
    # into the headline, because the product does not bet them.
    lean_bets: int = 0
    lean_wins: int = 0
    lean_net: float = 0.0
    lean_gains: list = field(default_factory=list)
    lean_why: dict = field(default_factory=dict)

    # --- the numbers a reader actually wants ---------------------------
    @property
    def hit_rate(self) -> float | None:
        return None if not self.n_bets else self.wins / self.n_bets

    @property
    def roi(self) -> float | None:
        return None if not self.staked else self.net / self.staked

    @staticmethod
    def _stderr(gains) -> float | None:
        """The standard error of the mean of `gains`, or None under two
        samples. Shared so the qualifying picks and the counterfactual
        are quoted to the same precision."""
        n = len(gains)
        if n < 2:
            return None
        mean = sum(gains) / n
        var = sum((g - mean) ** 2 for g in gains) / (n - 1)
        return math.sqrt(var / n)

    @property
    def roi_stderr(self) -> float | None:
        """The standard error of the ROI, off the realised per-bet
        returns.

        PRINTED BESIDE EVERY ROI IN THIS FILE, because the sample is
        small by construction — one bet a day — and an ROI quoted alone
        invites a reader to treat +9% over 90 bets as a fact about the
        world. It is about 1.3 standard errors from zero, which is a
        different sentence.
        """
        return self._stderr(self.gains)

    @property
    def calibration(self) -> tuple | None:
        """(what the fairs predicted, what happened), in wins.

        The selector's own honesty check and the one number that is not
        about money: if the picks were priced at fairs averaging 57% and
        won 44%, the ROI is an accident either way.
        """
        if not self.n_bets:
            return None
        return (self.fair_sum, float(self.wins))

def _row(sport, date, team, opp, home, away, fair_p, odds, auc):
    """One board row in the shape `potd.choose` selects on.

    EVERY FIELD IS EITHER HARVESTED OR STATED. `sharp_anchored` and
    `sharp_fair` are the de-vigged pair from the sharp book, which is
    exactly what `betting.sharp_anchor_for` sets in production;
    `rank_auc` is the production figure from `likely.measured_auc`;
    `book` is the shopped-best aggregate the harvest stores, which is
    what production shops. `bettable` is the one assumption and it is
    named in the report's caveats.

    NO `kickoff`, deliberately. `potd._started` reads the schedule clock
    and a blank one answers False (`rules.clock_says_started`), which is
    the honest answer for a game whose kickoff time was never harvested
    — and it keeps the replay from refusing every historical row for
    having started years ago.
    """
    return {"kind": "game", "market": "moneyline", "market_label": "Moneyline",
            "player": f"{team} ML", "team": team, "opponent": opp,
            "matchup": f"{away}@{home}", "side": "", "line": None,
            "book": "best", "odds": int(odds),
            "sharp_anchored": True, "sharp_fair": float(fair_p),
            "model_prob": None, "rank_auc": auc, "bettable": True,
            "injury_status": "", "game_date": str(date), "kickoff": ""}


def replay_potd(conn, sport: str = "mlb", sharp: str = "Pinnacle",
                rank_auc=None) -> PotdReplay:
    """Run `potd.choose` over every stored day and settle what it picked.

    ONE PICK PER DAY, AND ONLY A QUALIFYING ONE. `build` shows a lean
    when nothing clears and `ledger.log_pick_of_the_day` refuses to
    journal it, so a lean is not a bet and is not settled here — it is
    counted, under `days_with_only_a_lean`, because "how often does this
    product have nothing to sell" is half of what Ethan is asking.

    THE SELECTOR IS IMPORTED, NEVER RESTATED. Every bar in this replay
    is `potd.disqualify`, `potd.shortfall` and `potd.rank_key` as they
    ship. A backtest that reimplements the thing it is grading measures
    the reimplementation, and that is how a selector comes to look
    better on paper than it is in the field.
    """
    from . import likely, potd
    # `rank_auc` IS AN ANSWER, NOT A KNOB. Left alone it is the figure
    # this box has actually measured for the sport’s moneyline, which is
    # the number `shortfall` will hold a live row to. Passing one asks a
    # what-if — "if this market measured 0.60, what would the selector
    # have done" — and the summary says which of the two it used, so a
    # report cannot quietly be a hypothetical.
    r = PotdReplay(sport=sport, sharp=sharp,
                   rank_auc=(likely.measured_auc(sport, "moneyline")
                             if rank_auc is None else float(rank_auc)),
                   auc_supplied=rank_auc is not None)
    sharp_closes = moneyline_closes(conn, sport, book=sharp)
    soft_closes = moneyline_closes(conn, sport, book="best")

    games = conn.execute(
        "SELECT season, period, date, home, away, home_score, away_score "
        "FROM games WHERE sport=? AND home_score IS NOT NULL "
        "AND away_score IS NOT NULL ORDER BY season, period", (sport,)).fetchall()

    by_day: dict = {}
    for g in games:
        r.games_seen += 1
        period, home, away = g["period"], g["home"], g["away"]
        hs, as_ = float(g["home_score"]), float(g["away_score"])
        sp = close_for(sharp_closes, {}, g["season"], period, home, away,
                       date=g["date"]) or {}
        soft = close_for(soft_closes, {}, g["season"], period, home, away,
                         date=g["date"]) or {}
        if home not in sp or away not in sp:
            continue
        if home not in soft and away not in soft:
            continue
        r.games_priced += 1
        # The day a bet would have been placed on. `games.date` where the
        # ingest filled it, else the period — which IS a date for every
        # sport whose period is one, and for the NFL is a week number, so
        # an NFL replay locks one pick per WEEK. Said in the summary
        # rather than silently.
        day = str(g["date"] or period)[:10]
        fair_home, fair_away = devig_two_way(int(sp[home]), int(sp[away]))
        for team, opp, fair_p, won in ((home, away, fair_home, hs > as_),
                                       (away, home, fair_away, as_ > hs)):
            odds = soft.get(team)
            if odds is None:
                continue
            row = _row(sport, day, team, opp, home, away, fair_p, odds,
                       r.rank_auc)
            by_day.setdefault(day, []).append((row, won))

    for day in sorted(by_day):
        rows = by_day[day]
        r.days_seen += 1
        pick, near, census = potd.choose([row for row, _ in rows])
        for why, n in census.items():
            r.census[why] = r.census.get(why, 0) + n
        if pick is None:
            if near is None:
                r.days_blank += 1
                continue
            r.days_with_only_a_lean += 1
            # Settled into the counterfactual's own books — see the
            # `lean_*` fields. The product does not place this bet.
            won = next(w for row, w in rows if row is near)
            odds = int(near["odds"])
            gain = (american_to_decimal(odds) - 1.0) if won else -1.0
            r.lean_bets += 1
            r.lean_wins += 1 if won else 0
            r.lean_net += gain
            r.lean_gains.append(gain)
            why = potd.shortfall(near)
            b = r.lean_why.setdefault(why, {"n": 0, "wins": 0, "net": 0.0})
            b["n"] += 1
            b["wins"] += 1 if won else 0
            b["net"] += gain
            continue
        r.days_with_pick += 1
        won = next(w for row, w in rows if row is pick)
        odds = int(pick["odds"])
        gain = (american_to_decimal(odds) - 1.0) if won else -1.0
        r.n_bets += 1
        r.wins += 1 if won else 0
        r.staked += 1.0
        r.net += gain
        r.gains.append(gain)
        r.fair_sum += float(potd.fair_prob(pick) or 0.0)
        r.ev_sum += float(potd.edge(pick) or 0.0)
        for bucket, key in ((r.tiers, potd.evidence(pick)),
                            (r.prices, "favourite" if odds < 0 else "underdog")):
            b = bucket.setdefault(key, {"n": 0, "wins": 0, "net": 0.0})
            b["n"] += 1
            b["wins"] += 1 if won else 0
            b["net"] += gain
    return r

def _pct(x, places=1):
    return "n/a" if x is None else f"{x * 100:.{places}f}%"


def summarize(r: PotdReplay) -> str:
    """The replay as a paragraph an operator can act on.

    NEVER RETURNS AN EMPTY REPORT. A replay that priced nothing is a
    fact about the harvest, not a reason to print a blank — so the
    funnel is printed either way and the last section says which rung
    emptied. This is `SharpAnchorReport.diagnosis`'s lesson applied
    here: a zero that cannot say why it is zero costs an evening.
    """
    from . import potd
    out = [f"Pick of the Day replay · {r.sport.upper()} · "
           f"{r.sharp} as the sharp witness",
           f"  band {potd.MIN_ODDS} to +{potd.MAX_ODDS}, "
           f"EV floor {_pct(potd.MIN_EV)}, fair floor {_pct(potd.MIN_FAIR, 0)}, "
           f"ranking bar {potd.MIN_RANK_AUC}",
           f"  {'SUPPLIED' if r.auc_supplied else 'measured'} moneyline AUC "
           f"for this sport: "
           f"{'never measured' if r.rank_auc is None else f'{r.rank_auc:.3f}'}"
           + ("   ← a what-if, not this box’s measurement"
              if r.auc_supplied else ""),
           "",
           f"  games seen        {r.games_seen}",
           f"  games priced      {r.games_priced}   "
           f"(a sharp pair AND a soft price)",
           f"  days priced       {r.days_seen}"]
    if r.days_seen:
        out += [f"  days with a pick  {r.days_with_pick}   "
                f"({r.days_with_pick / r.days_seen * 100:.0f}% of days)",
                f"  days with a lean  {r.days_with_only_a_lean}   "
                f"(shown, not recorded, not bet here)",
                f"  days with nothing {r.days_blank}"]
    if not r.n_bets:
        out += ["", "  NO PICK WAS EVER MADE. Which rung emptied:"]
        if not r.games_priced:
            out.append("    nothing priced — the harvest has no game with "
                       "both a sharp pair and a soft price for this sport")
        for why, n in sorted(r.census.items(), key=lambda kv: -kv[1])[:8]:
            out.append(f"    {n:>5}  {why}")
        if r.rank_auc is None:
            out.append("    the moneyline has never been measured for this "
                       "sport, and `shortfall` refuses an unmeasured market")
        return "\n".join(out)

    se = r.roi_stderr
    out += ["",
            f"  picks bet         {r.n_bets}",
            f"  won               {r.wins}   ({_pct(r.hit_rate)})",
            f"  staked            {r.staked:.1f}u",
            f"  net               {r.net:+.2f}u",
            f"  ROI               {_pct(r.roi)}"
            + ("" if se is None else
               f"   ± {se * 100:.1f}% (1 s.e.)   "
               f"{abs((r.roi or 0) / se):.1f} s.e. from zero")]
    fair, got = r.calibration
    out += [f"  the fairs said    {fair:.1f} wins out of {r.n_bets}; "
            f"{got:.0f} happened",
            f"  average edge at selection {_pct(r.ev_sum / r.n_bets)}"]
    if r.tiers:
        out.append("  by witness:")
        for tier in potd.EVIDENCE:
            b = r.tiers.get(tier)
            if b:
                out.append(f"    {tier:<9} {b['n']:>4} bets  "
                           f"{b['wins']:>4} won  {b['net']:+7.2f}u")
    if r.prices:
        out.append("  by price:")
        for side in ("favourite", "underdog"):
            b = r.prices.get(side)
            if b:
                out.append(f"    {side:<9} {b['n']:>4} bets  "
                           f"{b['wins']:>4} won  {b['net']:+7.2f}u")
    if r.census:
        out.append("  what the selector turned away, per day summed:")
        for why, n in sorted(r.census.items(), key=lambda kv: -kv[1])[:6]:
            out.append(f"    {n:>6}  {why}")
    if r.lean_bets:
        # THE COUNTERFACTUAL, AND IT IS THE ANSWER TO A REAL QUESTION.
        # "Always have a pick of the day" is a product ask; this is what
        # it would have cost. A negative number here is the argument for
        # leaving leans off the record, and a positive one is the
        # argument for a second, labelled tier — either way it is
        # measured rather than argued.
        lse = r._stderr(r.lean_gains)
        out += ["",
                f"  IF THE LEANS HAD BEEN BET TOO (they are not, and "
                f"`log_pick_of_the_day` refuses them):",
                f"    {r.lean_bets} bets, {r.lean_wins} won "
                f"({_pct(r.lean_wins / r.lean_bets)}), "
                f"{r.lean_net:+.2f}u, ROI {_pct(r.lean_net / r.lean_bets)}"
                + ("" if lse is None else f" ± {lse * 100:.1f}%"),
                f"    combined with the picks: "
                f"{r.n_bets + r.lean_bets} bets, "
                f"{r.net + r.lean_net:+.2f}u, "
                f"ROI {_pct((r.net + r.lean_net) / (r.n_bets + r.lean_bets))}",
                "    the leans, by the bar each one missed:"]
        for why, b in sorted(r.lean_why.items(), key=lambda kv: -kv[1]["n"])[:5]:
            out.append(f"      {b['n']:>4} bets  {b['wins']:>4} won  "
                       f"{b['net']:+7.2f}u  {why}")
    out += ["",
            "  READ THIS BEFORE THE ROI. Closing price against closing "
            "price, moneylines only, no exchange tier, `bettable` assumed "
            "— see this module's header. A floor, with the reasons "
            "written down."]
    return "\n".join(out)
