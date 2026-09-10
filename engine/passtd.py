"""Passing touchdowns — the quarterback's own market.

Ethan, 2026-09-10: "when we search a QB, we are not showing passing
touchdown stats at all, and we also don't display that as a pick in the
edge bets or most likely bets so we need too fix that now."

He is right on both counts, and the second had three separate causes,
each of which alone was enough:

  * `sources.oddsapi.ODDS_TO_MARKET` never asked for `player_pass_tds`,
    so no book quote for it has ever entered this system;
  * `sources.nflverse.POSITION_MARKETS` built a quarterback exactly one
    prop — passing yards — so there was no `Prop` for a quote to attach
    to even if one had arrived;
  * nothing projected the market, so there was nothing to price a quote
    against.

WHAT THIS MODULE IS. The projection, and the measurement that decides
what the boards are allowed to claim about it.

THE MEASUREMENT, run 2026-09-10 against this box's own
`player_game_logs` — 3,423 quarterback games across 2021-2025, 138
passers. Every feature is knowable before kickoff; the first cut of this
measurement scaled the rate by the game's OWN pass attempts and scored
0.7624, which is not a projection, it is the answer read off the game
being predicted.

    fitted on 2021-2024, measured on HELD-OUT 2025

    1+ passing TD      AUC 0.6870   (n = 647)
    2+ passing TDs     AUC 0.6471   (n = 647)

    the same fit, in sample (2021-24)
    1+ passing TD      AUC 0.7149   (n = 2,387)
    2+ passing TDs     AUC 0.6804   (n = 2,387)

    career rate alone, no grid search at all, on 2025
    1+ passing TD      AUC 0.6739
    2+ passing TDs     AUC 0.6344

Two things follow and both are written into the numbers above rather
than into a claim. The blend beats the naive career rate out of sample,
so the window is doing work rather than fitting noise — and it beats it
by 0.013, so the work it is doing is small. And the honest figure to
publish is the HELD-OUT 0.687, not the in-sample 0.715: `likely.RANK_AUC`
carries 0.687 for exactly that reason.

0.687 clears `likely.MIN_RANK_AUC` (0.60) comfortably and sits just under
the anytime-touchdown board's 0.721, which is the right neighbourhood —
they are the same kind of question about the same kind of event.

WHAT IT DOES NOT SAY. Ranking is not edge. This measures whether the
model can sort quarterbacks by how likely they are to throw one; it says
nothing about whether it beats a book's price, and `quality.MARKET_TIER`
already files `pass_td` as Tier 3 with the 6% post-haircut minimum that
quarantines the touchdown markets. A card here earns its way onto the
edge board the same way an anytime-TD card does, or it does not appear
on it.
"""

from __future__ import annotations

import math

#: The league's own passing touchdowns per quarterback-game, measured
#: over the same 3,423 games. The anchor a thin log is pulled toward.
LEAGUE_PASS_TD = 1.211

#: The recency window and the prior weight, both chosen on 2021-2024 and
#: then measured on 2025 (see the module note). The grid was flat —
#: every setting tried scored between 0.697 and 0.709 in sample — so this
#: pair is a reasonable choice rather than a discovery, and nothing
#: downstream should treat the exact numbers as load-bearing.
RECENT_GAMES = 8
PRIOR_GAMES = 2

#: Below this many logged games a quarterback's own rate is not a rate.
#: The blend still runs — it is mostly the league anchor at that point —
#: but the row says its history is thin so a card can decline to price it.
MIN_GAMES = 3


def projection(values, league: float = LEAGUE_PASS_TD,
               recent: int = RECENT_GAMES, prior: int = PRIOR_GAMES) -> float:
    """Expected passing touchdowns, from his own most-recent-first log.

    Career and last-`recent` averaged, then shrunk toward the league
    anchor by `prior` notional games. An empty log is the league mean:
    a quarterback with nothing behind him is an average one until he is
    not, which is a weaker claim than any number his own zero games
    could support.
    """
    vals = [float(v) for v in (values or ()) if v is not None]
    if not vals:
        return float(league)
    career = sum(vals) / len(vals)
    window = vals[:max(1, recent)]
    blend = (career + sum(window) / len(window)) / 2.0
    return (blend * len(vals) + league * prior) / (len(vals) + prior)


def at_least(rate: float, line: float) -> float:
    """P(passing TDs > line) for a Poisson arm at `rate`.

    POISSON, and the same reasoning `longshots.prob_at_least_one` sets
    out for scorers: a count of rare independent-ish events in a fixed
    window is what Poisson is for, and a normal approximation near one
    or two touchdowns is visibly wrong at the tails that matter.

    NO OVERDISPERSION SHRINK, for the reason that module measured on
    scoring and this one has not re-measured on passing: adding one here
    would be borrowing a correction from a different market. The line is
    a book's half-number (0.5, 1.5, 2.5), so `line` is read as "strictly
    more than", which is what an OVER settles as.
    """
    lam = max(0.0, float(rate))
    need = int(math.floor(float(line))) + 1        # 1.5 -> needs 2
    if need <= 0:
        return 1.0
    # P(X >= need) = 1 - P(X <= need-1)
    cum, term = 0.0, math.exp(-lam)
    for k in range(need):
        if k:
            term *= lam / k
        cum += term
    return max(0.0, min(1.0, 1.0 - cum))


def form(values) -> dict:
    """The six windows the prop page draws, over passing touchdowns."""
    def avg(xs):
        xs = [float(v) for v in xs if v is not None]
        return round(sum(xs) / len(xs), 3) if xs else None
    vals = list(values or ())
    return {"last1": avg(vals[:1]), "last3": avg(vals[:3]),
            "last5": avg(vals[:5]), "last10": avg(vals[:10]),
            "season": avg(vals), "career": None, "vs_opponent": None}
