"""Interceptions thrown — the quarterback's third count market.

Ethan, 2026-10-05: "For the most likely bets, we need too implement picks
for QB interceptions, QB Pass Attempts, QB Completions … Like for
interceptions in general, knowing who the QB is throwing too the most and
also knowing who is guarding that person and light the path of if an
interception bet is good or not."

WHAT WAS MEASURED BEFORE THIS WAS BUILT, and why the shape below is the
shape it is. A quarterback's own interception COUNT does not sort the
next game: 0.540 ± 0.028 on the NFL's held-out 2025 (marketfit.py,
2026-09-27) and 0.494 ± 0.014 on college's (cfbmarketfit.py, 2026-10-05)
— coins. Two things carry the signal, and both are in the number here:

  * HIS RATE PER ATTEMPT, TIMES THE ATTEMPTS HE WILL THROW. A passer is
    at risk once per throw; a count per game folds his volume into his
    carelessness and loses both. The rate is career and last-eight
    averaged, each shrunk toward the league's by PRIOR_ATTEMPTS notional
    throws (about three games of a starter), and the attempts are the
    board's own attempts projection — the market this engine already
    ranks at 0.707 (NFL).
  * THE DEFENCE HE IS THROWING AT. The opponent's interceptions forced
    per game, rated the way every other matchup on this board is rated
    (engine/defensevs: this season shrunk toward last), lifted college
    from 0.494 to 0.611 ± 0.014 in the harness. It reaches the number
    through the matchup step at the strength `defensevs.TRANSFER` /
    `TRANSFER_CFB` carries for ("pass_int", "QB") — measured per league,
    never borrowed across them — and the card shows it either way.

What the harness also scored and this file does NOT apply: FTN's
interception-worthy-throw rate (`marketfit.py` arms `pass_int+iw`,
`+iw+own`), which needs the box's charting cache to measure. It is shown
on the card as a fact beside the number until a held-out run says it
belongs inside it.

POISSON, like passing touchdowns (engine/passtd): a count of rare,
roughly independent events in a fixed window, priced at the book's
half-number with `at_least`. Everything else about the row — the matchup
card, weather (unmeasured for this market: ×1.0), injuries, the lineup
step, player memory, calibration — is the same chain every market on
the board runs through (engine/projection.build_projection), which is
the point: the interception number is the board's number with a better
base, not a side model.

RANKING IS NOT EDGE. `quality.MARKET_TIER` files this market at Tier 3
with the 6% post-haircut bar that quarantines the touchdown markets;
the Most Likely board takes it only where the league's own walk clears
`likely.MIN_RANK_AUC` (NFL: a `RANK_AUC` constant from the box's
marketfit run; college: the box's `engine.rankfit` store). Nothing here
grants either.
"""

from __future__ import annotations

from .passtd import at_least  # noqa: F401  (the Poisson tail, shared)

#: Interceptions per attempt are shrunk toward the league's by this many
#: notional attempts — the harness's INT_PRIOR_ATT (marketfit.py).
PRIOR_ATTEMPTS = 120.0

#: The league's picks per attempt when a prop arrives without its own
#: anchor (a hand-built slate, a test). Every real build computes the
#: anchor from the season's own quarterback rows (`league_rate`) and
#: carries it on `Prop.aux["league_int_rate"]`; these are the rounded
#: figures the cached 2022-2025 college play files (0.0206) and the
#: NFL's published seasons (about one pick in 45 throws) give, so a prop
#: without an anchor is an average passer rather than a zero.
FALLBACK_LEAGUE_RATE = {"nfl": 0.022, "cfb": 0.021}

#: The recency window, as passtd's: career and the last eight averaged.
RECENT_GAMES = 8

#: Fewest games with attempts before his own rate is a rate at all. Under
#: it the league's rate stands in — a rookie is an average passer until
#: he is not.
MIN_GAMES = 3

#: A passer-game counts toward the league's rate only when he threw it:
#: nflverse.QB_START_ATTEMPTS, so relief snaps do not pull the anchor down.
LEAGUE_MIN_ATTEMPTS = 15.0


def league_rate(att_values, int_values) -> float | None:
    """The league's interceptions per attempt over paired game values
    (any order, same games), counting a game only where the passer threw
    LEAGUE_MIN_ATTEMPTS or more. None when there is nothing to count."""
    a = i = 0.0
    for att, picked in zip(att_values or (), int_values or ()):
        try:
            att, picked = float(att), float(picked)
        except (TypeError, ValueError):
            continue
        if att >= LEAGUE_MIN_ATTEMPTS:
            a += att
            i += picked
    return (i / a) if a > 0 else None


def rate_per_attempt(att_values, int_values, league: float,
                     prior: float = PRIOR_ATTEMPTS, recent: int = RECENT_GAMES) -> float:
    """His interceptions per attempt, most-recent-first logs paired game
    for game: career and the last ``recent`` averaged, each shrunk toward
    ``league`` by ``prior`` notional attempts. Fewer than MIN_GAMES paired
    games is the league's rate."""
    pairs = []
    for att, picked in zip(att_values or (), int_values or ()):
        try:
            pairs.append((float(att), float(picked)))
        except (TypeError, ValueError):
            continue
    league = max(0.0, float(league))
    if len(pairs) < MIN_GAMES:
        return league
    a_all, i_all = sum(a for a, _ in pairs), sum(p for _, p in pairs)
    win = pairs[:max(1, recent)]
    a_rec, i_rec = sum(a for a, _ in win), sum(p for _, p in win)
    career = (i_all + league * prior) / (a_all + prior)
    window = (i_rec + league * prior) / (a_rec + prior)
    return (career + window) / 2.0


def expected(rate: float, attempts: float) -> float:
    """The arm: expected interceptions = his rate × the attempts projected."""
    return max(0.0, float(rate)) * max(0.0, float(attempts))


def words(rate: float, league: float, attempts: float, lam: float) -> str:
    """One sentence for the card: the rate as a bettor reads it."""
    def every(r: float) -> str:
        return f"one every {round(1.0 / r):d} throws" if r > 0 else "none on record"
    return (f"Interception rate: {every(rate)} (league {every(league)}) × "
            f"{attempts:.0f} projected attempts = {lam:.2f} expected")


def form(values) -> dict:
    """The six windows the prop page draws, over interceptions thrown."""
    def avg(xs):
        xs = [float(v) for v in xs if v is not None]
        return round(sum(xs) / len(xs), 3) if xs else None
    vals = list(values or ())
    return {"last1": avg(vals[:1]), "last3": avg(vals[:3]),
            "last5": avg(vals[:5]), "last10": avg(vals[:10]),
            "season": avg(vals), "career": None, "vs_opponent": None}
