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

from .gamebets import SHARP_SUSPECT_EV, sharp_anchor_two_way
from .odds import american_to_decimal
from .gamebacktest import close_for, moneyline_closes


@dataclass
class PotdReplay:
    """One sport's replay, and everything needed to argue with it."""
    sport: str = "mlb"
    sharp: str = "Pinnacle"
    rank_auc: float | None = None
    auc_supplied: bool = False   # the caller asked a what-if; see `replay_potd`
    #: The EV floor this replay ran under. None means `potd.MIN_EV`, the
    #: live product's bar; anything else is a sweep asking where the bar
    #: SHOULD sit, and the report marks it so a what-if cannot be read as
    #: the shipped setting.
    min_ev: float | None = None
    #: The confidence floor this replay ran under. None means
    #: `potd.MIN_FAIR`. Swept by `sweep_conf`, which is the table that
    #: answers "how confident can the day's pick actually be".
    min_fair: float | None = None
    #: On a day with no pick, which bar turned the best row away. Counted
    #: across days so a sweep can say what lowering the EV floor actually
    #: buys — usually less than it looks, because another bar takes over.
    binding: dict = field(default_factory=dict)
    games_seen: int = 0
    games_priced: int = 0        # had both a sharp pair and a soft price
    one_sided: int = 0           # soft quote on one side only — ungateable
    gate_refused: int = 0        # `sharp_anchor_two_way` said no
    suspect: int = 0             # past SHARP_SUSPECT_EV; production Passes it
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
    # WHERE THE PICKS SIT ON THE EDGE THEY WERE CHOSEN FOR.
    #
    # `potd.rank_key` sorts by tier and then by the BIGGEST edge, so
    # every day goes to the loudest disagreement in the strongest tier.
    # Its own docstring says why that is dangerous — "the loudest
    # disagreements come from the weakest witness" — but it applies the
    # thought ACROSS tiers and not WITHIN one.
    #
    # The droplet's first honest run put the average selected edge at
    # 8.6%, above `SHARP_SUSPECT_EV`, so the typical Pick of the Day is
    # a bet the pricer itself would grade Pass; and
    # `backtest_sharp_anchor` measured that same 8-15% band at -16.8%.
    # Theory says the selector is fishing in the losing bucket. These
    # counters are how we find out instead of arguing.
    ev_buckets: dict = field(default_factory=dict)
    #: The same split over the LEANS. Since `potd.MAX_EV` landed
    #: (2026-09-16) no bet can sit in the suspect band — the selector
    #: refuses it — so `ev_buckets` can no longer answer "what is the
    #: ceiling costing us?". The leans can: they are exactly the rows it
    #: now turns away, settled.
    lean_ev_buckets: dict = field(default_factory=dict)
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

#: The edge bands the picks and the leans are both split across, in
#: report order. Split at `SHARP_SUSPECT_EV` rather than a round number:
#: the question is not "is the edge big" but "is it past the point
#: production stops believing it".
BANDS = ("under 4%", "4-7%",
         f"{SHARP_SUSPECT_EV * 100:.0f}-15% (suspect)")


def _band(ev: float) -> str:
    """Which edge band a selection at `ev` was chosen in."""
    return (BANDS[0] if ev < 0.04
            else BANDS[1] if ev < SHARP_SUSPECT_EV
            else BANDS[2])


def _tally(bucket: dict, key: str, won: bool, gain: float) -> None:
    """One settled row into a named bucket. Shared by the tier, price,
    edge-band and lean-reason splits so they cannot drift apart."""
    b = bucket.setdefault(key, {"n": 0, "wins": 0, "net": 0.0})
    b["n"] += 1
    b["wins"] += 1 if won else 0
    b["net"] += gain


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
                rank_auc=None, min_ev=None, min_fair=None) -> PotdReplay:
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
                   auc_supplied=rank_auc is not None,
                   min_ev=None if min_ev is None else float(min_ev),
                   min_fair=None if min_fair is None else float(min_fair))
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
        # THE PRODUCTION GATE, CALLED RATHER THAN RESTATED.
        #
        # `sharp_anchor_two_way` is what decides, live, whether a sharp
        # disagreement becomes a card at all: it de-vigs the pair, takes
        # the better side, and returns None unless the EV lands inside
        # [SHARP_MIN_EV, SHARP_MAX_EV]. That ceiling is the point — "a
        # disagreement this big between books usually means the sharp
        # side repriced on news and this quote is stale, not free money".
        #
        # THE FIRST VERSION COMPUTED THE EV ITSELF and skipped the
        # ceiling, so it replayed bets production would never have made.
        # On the droplet, 2026-09-16: the MLB run reported an average
        # edge at selection of 29.5%, against a 15% cap and a
        # grade-it-Pass line at 7%, and printed +25.6% ROI for a book the
        # live site refuses by construction.
        #
        # This file's own first test says the selector must be imported
        # and never restated. That was true of `potd.choose` and false of
        # the row it was handed, which is the more expensive half.
        both = (soft.get(home), soft.get(away))
        if both[0] is None or both[1] is None:
            # The real gate compares both sides, so a one-sided soft
            # quote cannot be run through it — and inventing the missing
            # price is the restatement above. Counted, never guessed.
            r.one_sided += 1
            continue
        pick = sharp_anchor_two_way(int(sp[home]), int(sp[away]),
                                    int(both[0]), int(both[1]))
        if pick is None:
            r.gate_refused += 1
            continue
        i, fair_p, ev = pick
        team, opp = (home, away) if i == 0 else (away, home)
        won = (hs > as_) if i == 0 else (as_ > hs)
        row = _row(sport, day, team, opp, home, away, fair_p,
                   int(both[i]), r.rank_auc)
        # SUSPECT BUT NOT REFUSED, exactly as production leaves it: a gap
        # past `SHARP_SUSPECT_EV` still becomes a card, graded Pass at a
        # stake of zero. Recorded so the summary can say how much of the
        # book rides on quotes the pricer itself distrusts.
        if ev > SHARP_SUSPECT_EV:
            row["suspect_gap"] = True
            r.suspect += 1
        by_day.setdefault(day, []).append((row, won))

    for day in sorted(by_day):
        rows = by_day[day]
        r.days_seen += 1
        pick, near, census = potd.choose([row for row, _ in rows],
                                         min_ev=min_ev, min_fair=min_fair)
        # WHICH BAR WAS BINDING on a day that produced nothing. The
        # census already counts every refusal; what a sweep needs is the
        # ONE reason that stood between this day and a pick, which is the
        # reason attached to the best row that got closest.
        if not pick:
            why = ""
            if near:
                why = potd.shortfall(near, min_ev, min_fair) or ""
            if not why and census:
                why = max(census.items(), key=lambda kv: kv[1])[0]
            if why:
                r.binding[why] = r.binding.get(why, 0) + 1
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
            _tally(r.lean_why, why, won, gain)
            _tally(r.lean_ev_buckets,
                   _band(float(potd.edge(near) or 0.0)), won, gain)
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
        ev_at_pick = float(potd.edge(pick) or 0.0)
        r.fair_sum += float(potd.fair_prob(pick) or 0.0)
        r.ev_sum += ev_at_pick
        _tally(r.ev_buckets, _band(ev_at_pick), won, gain)
        _tally(r.tiers, potd.evidence(pick), won, gain)
        _tally(r.prices, "favourite" if odds < 0 else "underdog", won, gain)
    return r

def _pct(x, places=1):
    return "n/a" if x is None else f"{x * 100:.{places}f}%"


#: The EV floors a sweep tries, lowest first. 2% is the shipped bar; 0%
#: is "any edge at all"; below that is not swept, because a negative EV
#: floor admits a bet the price says we lose on and no sample size makes
#: that a good idea.
SWEEP_FLOORS = (0.0, 0.005, 0.01, 0.015, 0.02, 0.03, 0.04)


def sweep_ev(conn, sport: str = "mlb", sharp: str = "Pinnacle",
             floors=SWEEP_FLOORS, rank_auc=None) -> str:
    """Where should the EV floor sit? One table, settled results. (#207-adj)

    Ethan, 2026-09-16, on a day the card led with NO BET: "we need to be
    confident in our pick, and if that's a good pick, then we need to say
    to bet it." Lowering the bar is the change he asked for; this is the
    number it should be lowered TO, rather than a guess.

    WHAT THE TABLE IS FOR, and it is not only the ROI. A lower floor buys
    more days with a pick — but usually fewer than it looks, because the
    EV bar stops binding and ANOTHER bar takes over, and the days it does
    buy are by construction the thinnest edges in the sample. So the
    table prints three things together: how many days got a pick, what
    those picks returned, and which bar was binding on the days that
    still got nothing. Read them in that order.

    A FLOOR IS NOT CHOSEN BY THE BEST ROI IN THIS TABLE. Picking the
    best cell of seven on one sample is how a bar gets fitted to noise —
    the trap `calibrate`'s bake-off exists to refuse. What this is good
    for is the SHAPE: a floor where ROI falls off a cliff is a real
    signal, and a floor where nothing changes says the bar was never the
    thing holding the product back.
    """
    from . import potd
    rows = []
    for f in floors:
        r = replay_potd(conn, sport, sharp=sharp, rank_auc=rank_auc, min_ev=f)
        roi = (r.net / r.staked * 100.0) if r.staked else None
        rows.append((f, r, roi))
    out = [f"EV floor sweep · {sport.upper()} · {sharp} as the sharp witness",
           f"  {rows[0][1].days_seen} days with at least one priced game",
           "",
           f"  {'floor':>6}  {'days w/ pick':>12}  {'bets':>5}  {'W-L':>9}  "
           f"{'ROI':>8}   binding when nothing cleared",
           "  " + "-" * 82]
    for f, r, roi in rows:
        losses = r.n_bets - r.wins
        top = ""
        if r.binding:
            why, n = max(r.binding.items(), key=lambda kv: kv[1])
            top = f"{why} ({n})"
        out.append(f"  {_pct(f):>6}  {r.days_with_pick:>12}  {r.n_bets:>5}  "
                   f"{r.wins}-{losses:<7}  "
                   f"{'n/a' if roi is None else f'{roi:+.1f}%':>8}   {top[:40]}")
    shipped = next((r for f, r, _ in rows if abs(f - potd.MIN_EV) < 1e-9), None)
    out += ["",
            f"  The shipped floor is {_pct(potd.MIN_EV)}"
            + (f" — {shipped.days_with_pick} of {shipped.days_seen} days"
               if shipped else ""),
            "  Read the SHAPE, not the best cell: one sample's best floor is a",
            "  floor fitted to noise. A cliff is a signal; a flat table says the",
            "  EV bar was never what was holding the product back."]
    return "\n".join(out)


#: Confidence floors a sweep tries. Stops at 75% because 75% is -300,
#: where one loss costs three wins — past there the product is selling
#: chalk it cannot pay for, and that is a different argument from "how
#: confident can we be".
CONF_FLOORS = (0.55, 0.58, 0.60, 0.62, 0.65, 0.68, 0.70, 0.75)


def sweep_conf(conn, sport: str = "mlb", sharp: str = "Pinnacle",
               floors=CONF_FLOORS, rank_auc=None) -> str:
    """How confident can the day's pick actually be? (2026-09-16)

    Ethan: "I don't care about the edge a bet has when it comes to the
    pick of the day. I care about if the pick is going to hit or not."
    So this table leads with the HIT RATE, which is the number he is
    asking about, and prints the units beside it — because those two move
    in opposite directions and the whole decision lives in that trade.

    THE TRADE, PLAINLY. Confidence is bought with price. A 71% pick is
    -250, so it pays 0.40u and one loss costs two and a half wins. Raise
    the floor and the hit rate goes up while the money each win brings in
    goes down; there is a floor somewhere where the hit rate stops
    keeping up with the price, and that is the number this looks for.

    CLAIMED vs LANDED is the column that says whether the floor means
    anything. A floor of 65% is worth nothing if the picks it admits land
    at 55% — that is not a confident pick, it is a confident-sounding
    one, and the gap between the two columns is the honest measure of
    whether the model has earned the word.
    """
    from . import potd
    rows = []
    for f in floors:
        r = replay_potd(conn, sport, sharp=sharp, rank_auc=rank_auc, min_fair=f)
        hit = (r.wins / r.n_bets) if r.n_bets else None
        roi = (r.net / r.staked * 100.0) if r.staked else None
        rows.append((f, r, hit, roi))
    out = [f"Confidence floor sweep · {sport.upper()} · "
           f"{sharp} as the sharp witness",
           f"  {rows[0][1].days_seen} days with at least one priced game",
           "",
           f"  {'floor':>6}  {'days':>5}  {'bets':>5}  {'W-L':>9}  "
           f"{'HIT RATE':>9}  {'units':>8}  {'ROI':>8}",
           "  " + "-" * 70]
    for f, r, hit, roi in rows:
        out.append(f"  {_pct(f, 0):>6}  {r.days_with_pick:>5}  {r.n_bets:>5}  "
                   f"{r.wins}-{r.n_bets - r.wins:<7}  "
                   f"{'n/a' if hit is None else f'{hit:.1%}':>9}  "
                   f"{r.net:>+8.2f}  "
                   f"{'n/a' if roi is None else f'{roi:+.1f}%':>8}")
    out += ["",
            f"  Shipped floor: {_pct(potd.MIN_FAIR, 0)}. Band {potd.MIN_ODDS} "
            f"to +{potd.MAX_ODDS}, so the most confident price reachable "
            f"implies {_pct(abs(potd.MIN_ODDS) / (abs(potd.MIN_ODDS) + 100.0), 1)}.",
            "  A floor above what the band can reach selects nothing — raise",
            "  both together or neither.",
            "  HIT RATE is the number being asked for; units is what it costs.",
            "  A floor whose picks land well under it has not earned the word."]
    return "\n".join(out)


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
           f"EV floor {_pct(potd.MIN_EV if r.min_ev is None else r.min_ev)}"
           + ("" if r.min_ev is None
              else f"   ← SWEPT, not the shipped {_pct(potd.MIN_EV)}")
           + f", fair floor {_pct(potd.MIN_FAIR, 0)}, "
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
           f"  one-sided soft    {r.one_sided}   "
           f"(the real gate needs both prices)",
           f"  gate refused      {r.gate_refused}   "
           f"(`sharp_anchor_two_way`: under 2% EV, or past the 15% "
           f"broken-price cap)",
           f"  days priced       {r.days_seen}",
           # IN BOTH BRANCHES, deliberately. Since `potd.MAX_EV` a day
           # can price a card, refuse it as a suspect gap and bet
           # nothing — and the reader of a zero needs this number to
           # tell that apart from a day that priced nothing at all.
           f"  suspect gaps      {r.suspect}   (past "
           f"{SHARP_SUSPECT_EV:.0%} — production grades these Pass and "
           f"stakes nothing, and `potd.MAX_EV` keeps every one of them "
           f"out of the picks; they settle as leans)"]
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
    if r.ev_buckets:
        # THE CUT THAT DECIDES WHETHER `rank_key` IS FISHING IN THE
        # LOSING BUCKET. If the money is in the narrowest band and the
        # widest one loses, the selector's edge-first sort is choosing
        # against the evidence and the fix is to stop ranking on edge
        # size. The band names live in `BANDS` and nowhere else, so the
        # picks and the leans below cannot be cut at different places.
        out.append("  by the edge it was chosen for:")
        for band in BANDS:
            b = r.ev_buckets.get(band)
            if b:
                roi = b["net"] / b["n"]
                out.append(f"    {band:<16} {b['n']:>4} bets  "
                           f"{b['wins']:>4} won  {b['net']:+7.2f}u  "
                           f"ROI {roi * 100:+.1f}%")
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
        if r.lean_ev_buckets:
            # WHAT THE CEILING IS BUYING, AND IT CAN ONLY BE READ HERE.
            # `MAX_EV` means the suspect band is empty among the picks by
            # construction, so the split above can no longer show whether
            # refusing those gaps was right. These are the refused rows,
            # settled: a negative suspect line is the ceiling earning its
            # keep, a positive one is it costing money.
            out.append("    the leans, by the edge they were refused at:")
            for band in BANDS:
                b = r.lean_ev_buckets.get(band)
                if b:
                    out.append(f"      {band:<16} {b['n']:>4} bets  "
                               f"{b['wins']:>4} won  {b['net']:+7.2f}u  "
                               f"ROI {b['net'] / b['n'] * 100:+.1f}%")
    out += ["",
            "  READ THIS BEFORE THE ROI. Closing price against closing "
            "price, moneylines only, no exchange tier, `bettable` assumed "
            "— see this module's header. A floor, with the reasons "
            "written down."]
    return "\n".join(out)
