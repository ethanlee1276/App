"""The Parlay Zone — a screen, not a builder.

Implements docs/PARLAY_MODEL.md (Ethan's all-sports parlay instruction set)
over props that have *already* earned a place on the board as singles. §14 of
that doc is the whole design brief:

    "You do not build parlays. You screen them. A candidate ticket arrives
    only after every leg has independently earned a place on the board as a
    single."

So this module never invents a leg. It takes `recommendations` from a slate
that the sport's own pipeline already approved, enumerates the pairs and
triples inside each game, and runs the seven gates. The expected output, by a
wide margin, is nothing.

--------------------------------------------------------------------------
THE ONE HONEST PROBLEM, AND WHAT THIS MODULE DOES ABOUT IT
--------------------------------------------------------------------------
§1.3's Price Test needs `dec_quoted` — the book's actual same-game-parlay
price. **We do not have it.** No odds feed we ingest carries SGP quotes, and
an SGP price is not derivable from the leg prices: the whole point of §1.2 is
that the book applies a 15-30% correlation tax that only the book knows.

There are three things one could do about that and only one of them is
honest:

  1. Multiply the leg prices and call it the quote. That is precisely the
     mistake §1.1 opens by forbidding, and it would overstate every ticket's
     edge by the entire correlation tax — 15 to 30 points.
  2. Assume a tax, print a number, and let it look like a measurement.
  3. Invert the tests and publish the PRICE THE BOOK MUST BEAT.

This module does (3). Both gates are monotonic in `dec_quoted`, so each one
inverts cleanly into a minimum acceptable decimal price, and the binding one
is simply the larger:

    Gate 5 (price):      modeled_joint - 1/dec >= threshold
                     ->  dec >= 1 / (modeled_joint - threshold)
    Gate 6 (dominance):  modeled_joint*dec - 1 > 1.25 * EV_singles
                     ->  dec >  (1 + 1.25*EV_singles) / modeled_joint

The ticket then publishes `required_price`: "bet this only at +340 or
better." That is strictly more useful than a yes/no, because the reader can
check it against their own book in five seconds — and it cannot lie, because
it never claims to know a price it cannot see.

To answer "could this realistically ever qualify?" we compare the required
price against the BEST CASE a book would plausibly offer: the naive product
less the *most generous* end of §1.2's tax band. If the ticket needs more
than that, it is dead on arrival and we say so in §12's words. That is the
§1.4 worked example's verdict, reproduced mechanically.

--------------------------------------------------------------------------
WHY A COPULA AND NOT THE OBVIOUS FORMULA
--------------------------------------------------------------------------
There is a tempting shortcut. For two Bernoullis with correlation r,

    P(A and B) = P(A)P(B) + r*sqrt(P(A)(1-P(A))P(B)(1-P(B)))

exactly. Plugging §4.1's "+0.35" straight into it is wrong in the dangerous
direction. That r is the phi coefficient of the two *binary outcomes*, while
the doc's priors are correlations between the underlying *continuous* stats —
passing yards and receiving yards, points and team total. Binarising a
continuous pair always shrinks the correlation, so the shortcut inflates the
joint probability, which inflates the edge, which is how a screen becomes a
salesman.

So the priors are treated as latent Gaussian correlations and the binary
joint comes from the normal copula: leg i wins when Z_i > z_i where
z_i = Phi^-1(1 - p_i). Two legs use the bivariate normal CDF, computed
exactly. Three legs use a one-factor structure, which is not merely a
convenient approximation — it is the mechanism §3 and §4 actually describe.
Same-game correlation runs through one shared latent (game script, pace,
passing volume); that is a single common factor by construction.

--------------------------------------------------------------------------
CONSERVATISM, STATED
--------------------------------------------------------------------------
The Appendix is explicit that the rho magnitudes "are professional estimates,
not measured constants." Every prior here is therefore read at the BOTTOM of
its published band. Understating correlation understates the joint, which
raises the required price, which makes the screen pickier. When the numbers
are guesses, that is the direction to be wrong in.

--------------------------------------------------------------------------
PROBATION (§13)
--------------------------------------------------------------------------
Tickets are graded, never staked, and the module says so on every card. The
bar is not a calendar: 100 graded tickets clearing positive flat-stake ROI,
aggregate leg-level CLV >= 0, and z >= 2 — AND the singles board clearing its
own promotion bar first. `stake_units` is always 0.0; `stake_if_promoted`
carries what an eighth-Kelly stake at the required price would have been.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

# --- §0.2 the hard ceiling, §1.3 the thresholds ------------------------------
MAX_LEGS = 3
# How many ranked constructions the page shows. One is a play (§10.2);
# the rest are the board's best available, in order, so a reader can see
# what tonight actually offered rather than only that nothing qualified.
SHORTLIST = 4
DOMINANCE_MULTIPLE = 1.25          # §1.3 Test 2, the variance premium
STAKE_CAP_U = 1.0                  # §10.2 max 1.0% of bankroll; 1u == 1%
KELLY_FRACTION = 0.125             # §10.1 eighth Kelly
KELLY_FRACTION_UFC = 0.10          # §10.1 tenth Kelly

# §1.2: "typical effective hold on a 3-leg SGP: 15-30%". The generous end is
# what we test against, because the question this answers is "could a book
# EVER price this?" — and an optimistic answer to that question is the
# conservative one for a screen whose job is to say no.
BEST_CASE_SGP_TAX = 0.15
WORST_CASE_SGP_TAX = 0.30
# §1.2 quotes 4.3-4.8% hold on sides and totals. No book prices a same-game
# ticket at better than its own correlated fair number less its ordinary
# margin, so this floors how generous the ceiling above is allowed to get on
# a strongly correlated pair, where a flat percentage of the naive product
# stops describing anything real.
MIN_BOOK_HOLD = 0.043

# §1.1 / §7.2 / §8.2 all state the same floor: any two same-game overs carry
# roughly +0.10 through shared pace and script. Nothing in one game is
# independent, so no same-game pair is ever priced at zero.
SAME_GAME_BASELINE_RHO = 0.10

# The humility clamp, applied to correlation instead of to edge.
#
# The rest of this engine never prices a raw model-vs-market disagreement: it
# shrinks it first (engine/quality.py TIER_SHRINK). The Appendix says the rho
# priors are "professional estimates, not measured constants", which is the
# same epistemic position, so they get the same treatment — the priors are
# published on the card at face value and shrunk before they touch the
# copula.
#
# 0.45 is not a taste. It is TIER_SHRINK[2], the factor this engine already
# applies to yardage markets, and it happens to reproduce the instruction
# set's only worked calibration point almost exactly. §1.4's three legs
# (0.68 / 0.65 / 0.62, "all positively correlated") are quoted there as a
# correlated joint of 0.3097. Running those legs through this copula at
# priors of +0.30 shrunk by 0.45 gives 0.3095. Taking the priors at face
# value instead gives 0.3524 — a joint 4.3 points too generous, which is 4.3
# points of edge invented out of an estimate.
RHO_SHRINK = 0.45


@dataclass(frozen=True)
class SportRules:
    """Everything the per-sport sections change about the shared spine."""

    key: str
    name: str
    max_legs: int = MAX_LEGS
    two_leg_points: float = 5.0
    three_leg_points: float = 6.0
    kelly: float = KELLY_FRACTION
    # §3 Type 4: spread at or beyond which the favourite's player props are
    # ineligible for a ticket at all. None = the pairwise screen only.
    blowout_spread: float | None = None
    cross_game: str = "dominance"   # "dominance" | "banned"
    tier3_allowed: bool = True      # §8.4 bans tier 3 in any WNBA ticket
    anchor_tier1: bool = False      # §4 NFL anchor rule
    max_per_slate: int = 1          # §10.2, tightened to 1/Saturday for CFB
    unavailable: str = ""           # non-empty = we cannot screen this sport

    def threshold(self, legs: int) -> float:
        return (self.two_leg_points if legs <= 2 else self.three_leg_points) / 100.0


RULES: dict[str, SportRules] = {
    # §4. Anchor must be a Tier 1 volume market; Tier 3 (anytime TD, longest)
    # never anchors and three of them together are banned outright.
    "nfl": SportRules("nfl", "NFL", anchor_tier1=True, blowout_spread=10.0),
    # §6. Highest bar in the system: 8 points for three legs, and one ticket
    # per Saturday against a 60-game slate.
    "cfb": SportRules("cfb", "College Football", three_leg_points=8.0,
                      blowout_spread=17.0),
    # §5. The lineup rule dominates; enforced per-leg in _leg_eligible.
    "mlb": SportRules("mlb", "MLB"),
    # §7. Scalpy 3.0 §7 governs; this adds Gate 6 and the gate ordering.
    "nba": SportRules("nba", "NBA"),
    # §8. Minutes are the whole ticket. Spread >= 9 disqualifies favourite
    # star props, Tier 3 is banned in any multi-leg ticket, and cross-game
    # tickets are banned entirely — too few simultaneous games.
    "wnba": SportRules("wnba", "WNBA", blowout_spread=9.0, cross_game="banned",
                       tier3_allowed=False),
    # §9. The ceiling is two legs in ONE fight (ML + method / distance /
    # round group). We price fight winners; we do not price method of
    # victory or distance. So there is no same-fight pair to screen, and
    # §9.1 bans every cross-fight construction. Saying that plainly beats
    # inventing a market we do not model — and §9.2 points the same way:
    # most correct MMA correlations belong in a single method bet anyway.
    "ufc": SportRules(
        "ufc", "UFC", max_legs=2, three_leg_points=8.0, kelly=KELLY_FRACTION_UFC,
        cross_game="banned",
        unavailable="§9.1 caps UFC at two legs in ONE fight, and the only "
                    "two-leg constructions §9.3 permits pair a winner with a "
                    "method, distance or round-group market. This model "
                    "prices fight winners; it does not price those markets, "
                    "so there is no same-fight pair to screen. §9.2's "
                    "direct-price rule says the same thing from the other "
                    "side: price the method market directly and take the "
                    "better number."),
}


# --- market taxonomy ---------------------------------------------------------
# A leg's FAMILY is what it competes with; its TIER is how much the ticket is
# allowed to lean on it.
FAMILY = {
    "pass_yds": "pass", "rec_yds": "catch", "receptions": "catch",
    "rush_yds": "rush", "anytime_td": "td",
    "strikeouts": "pitch", "outs": "pitch",
    "total_bases": "bat", "hits": "bat", "home_runs": "bat",
    "pts": "score", "pra": "score", "ast": "assist", "reb": "board",
    "fg3m": "three", "stl": "stops", "blk": "stops",
    # Game lines. Almost every construction the doc permits has one of these
    # in it — §4.2's passing-game stack ends on a team total, §5.2's pitcher
    # stack ends on the opposing team total, and §6.3's CFB ticket is two
    # sides and a total with no player prop at all.
    "moneyline": "side", "spread": "side",
    "team_total": "teamtotal", "total": "gametotal",
}
TIER = {
    "receptions": 1, "pass_yds": 2, "rush_yds": 2, "rec_yds": 2,
    "anytime_td": 3,
    "strikeouts": 1, "outs": 1, "total_bases": 2, "hits": 2, "home_runs": 3,
    "reb": 1, "ast": 1, "pra": 1, "pts": 2, "fg3m": 3, "stl": 3, "blk": 3,
    # Sides and totals are the most modelable markets on the board and the
    # least variance-contaminated — tier tracks beatability, and these are
    # the numbers a book prices most carefully and we price most carefully.
    "moneyline": 1, "spread": 1, "team_total": 1, "total": 1,
}
GAME_FAMILIES = {"side", "teamtotal", "gametotal"}
# §5.1: the pitcher and the hitters he faces share one set of pitches.
PITCHER_FAMILIES = {"pitch"}
HITTER_FAMILIES = {"bat"}
# §4.3 / §8.4: markets with no place inside a compounding structure. The
# slates carry a `volatility` field, but a leg missing it must not slip
# through — the whole point of the ban is that these are the legs that turn a
# process into a lottery ticket.
EXTREME_MARKETS = {"anytime_td", "home_runs", "fg3m", "stl", "blk"}


# --- §1: the maths -----------------------------------------------------------
def _phi(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _phi_inv(p: float) -> float:
    """Standard normal quantile (Acklam's rational approximation, then one
    Halley refinement — good to ~1e-15, which is far more than we need but
    costs nothing and keeps the copula tests from chasing their own noise)."""
    if p <= 0.0:
        return -8.0
    if p >= 1.0:
        return 8.0
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        x = (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    elif p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        x = -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    else:
        q, r = p - 0.5, (p - 0.5) ** 2
        x = (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
            (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    e = _phi(x) - p
    u = e * math.sqrt(2 * math.pi) * math.exp(x * x / 2)
    return x - u / (1 + x * u / 2)


# 24-point Gauss-Legendre on [-1, 1], generated once by Newton iteration on
# the Legendre polynomial. Plenty for a smooth integrand over a bounded rho.
def _gauss_legendre(n: int) -> tuple[list[float], list[float]]:
    xs, ws = [], []
    for i in range(1, n + 1):
        x = math.cos(math.pi * (i - 0.25) / (n + 0.5))
        for _ in range(100):
            p0, p1 = 1.0, 0.0
            for j in range(1, n + 1):
                p0, p1 = ((2 * j - 1) * x * p0 - (j - 1) * p1) / j, p0
            dp = n * (x * p0 - p1) / (x * x - 1)
            dx = -p0 / dp
            x += dx
            if abs(dx) < 1e-15:
                break
        xs.append(x)
        ws.append(2 / ((1 - x * x) * dp * dp))
    return xs, ws


_GL_X, _GL_W = _gauss_legendre(24)
_GL64_X, _GL64_W = _gauss_legendre(64)


def bivariate_normal(h: float, k: float, rho: float) -> float:
    """P(Z1 <= h, Z2 <= k) for standard bivariate normals with correlation rho.

    Uses the classical identity d/drho Phi2 = phi2, so

        Phi2(h,k;rho) = Phi(h)Phi(k) + integral_0^rho phi2(h,k;r) dr

    which is smooth in r for |rho| < 1 and yields ~1e-12 accuracy on 24 nodes.
    """
    rho = max(-0.999, min(0.999, rho))
    if rho == 0.0:
        return _phi(h) * _phi(k)
    half, mid = rho / 2.0, rho / 2.0
    acc = 0.0
    for x, w in zip(_GL_X, _GL_W):
        r = mid + half * x
        om = 1.0 - r * r
        dens = math.exp(-(h * h - 2 * r * h * k + k * k) / (2 * om)) / \
            (2 * math.pi * math.sqrt(om))
        acc += w * dens
    return _phi(h) * _phi(k) + half * acc


def joint_two(p1: float, p2: float, rho: float) -> float:
    """P(both legs win) under a Gaussian copula with latent correlation rho."""
    z1, z2 = _phi_inv(1 - p1), _phi_inv(1 - p2)
    # P(Z1>z1, Z2>z2) = 1 - Phi(z1) - Phi(z2) + Phi2(z1,z2)
    return 1.0 - _phi(z1) - _phi(z2) + bivariate_normal(z1, z2, rho)


def _factor_loadings(rhos: tuple[float, float, float]) -> tuple[float, float, float]:
    """Fit lambda_i so that lambda_i*lambda_j reproduces rho_ij as closely as a
    one-factor structure can, then scale DOWN so no pair is overstated.

    rhos is (r12, r13, r23). The exact solution when the structure holds is
    lambda_1 = sqrt(r12*r13/r23) and cyclic. Where it does not hold exactly,
    the final rescale guarantees every realised pairwise correlation sits at
    or below its prior — the conservative side, per the Appendix's warning
    that these magnitudes are estimates.
    """
    r12, r13, r23 = (max(0.02, r) for r in rhos)
    lam = [math.sqrt(r12 * r13 / r23), math.sqrt(r12 * r23 / r13),
           math.sqrt(r13 * r23 / r12)]
    lam = [max(0.0, min(0.95, v)) for v in lam]
    scale = 1.0
    for (i, j), target in zip(((0, 1), (0, 2), (1, 2)), rhos):
        got = lam[i] * lam[j]
        if got > max(target, 0.0) and got > 0:
            scale = min(scale, math.sqrt(max(target, 0.0) / got))
    return tuple(v * scale for v in lam)  # type: ignore[return-value]


def joint_three(ps: tuple[float, float, float],
                rhos: tuple[float, float, float]) -> float:
    """P(all three legs win) under a one-factor Gaussian copula.

    Conditional on the shared factor Z the legs are independent, so the joint
    is a single integral over Z — which is exactly §1.1's conditional chain
    with the conditioning done on the mechanism rather than on leg order.
    """
    lam = _factor_loadings(rhos)
    zs = [_phi_inv(1 - p) for p in ps]
    res = [math.sqrt(max(1e-9, 1.0 - l * l)) for l in lam]
    acc = 0.0
    for x, w in zip(_GL64_X, _GL64_W):
        z = 8.0 * x                                  # [-8, 8] covers the mass
        dens = math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
        term = dens
        for zi, l, r in zip(zs, lam, res):
            term *= 1.0 - _phi((zi - l * z) / r)
        acc += w * term
    return max(0.0, min(1.0, 8.0 * acc))


def american_to_decimal(odds: float) -> float:
    o = float(odds)
    return 1.0 + (o / 100.0 if o > 0 else 100.0 / abs(o)) if o else 1.0


def decimal_to_american(dec: float) -> int:
    if dec <= 1.0:
        return -100000
    return int(round((dec - 1) * 100)) if dec >= 2.0 else int(round(-100 / (dec - 1)))


# --- §3: the clash taxonomy --------------------------------------------------
@dataclass
class Relation:
    """How two legs relate. `clash` is the §3 type number, 0 for none."""

    rho: float
    mechanism: str
    clash: int = 0
    verdict: str = "ok"          # "ok" | "duplicate" | "kill"


def _side_up(leg: dict) -> bool:
    """True when the leg wins as the underlying quantity goes UP.

    For a side (moneyline or spread) the quantity is the backed team's
    result, and we only ever back one side — so a side leg always points up
    for the team named on it. That is what makes "leading teams run" and
    "trailing dogs throw" expressible at all.
    """
    if _family(leg) == "side":
        return True
    return str(leg.get("side", "")).strip().upper().startswith("O")


def _is_game_leg(leg: dict) -> bool:
    return _family(leg) in GAME_FAMILIES


def normalize_game_bet(b: dict, sport: str) -> dict:
    """A game bet, shaped like a prop so one screen can hold both.

    The two payloads disagree on names for the same ideas — `win_prob` vs
    `hit_prob`, `date` vs `game_date`, home/away vs team/opponent — and a
    screen that reads only one of them can never build the constructions the
    doc actually permits. This translates rather than duplicating logic.
    """
    home, away = (b.get("home") or ""), (b.get("away") or "")
    team = b.get("team") or ""
    # A game total belongs to neither side. Filing it under the home team
    # would make it look like a team leg to the same-team rules, which is
    # exactly the Type 6 confusion §3 warns about.
    opponent = (away if team == home else home) if team else ""
    return {
        "player": b.get("pick_label") or b.get("headline") or f"{away}@{home}",
        "team": team, "opponent": opponent,
        "market": b.get("market") or b.get("bet_type") or "",
        "market_label": b.get("market_label") or "",
        "side": b.get("side") or "",
        "line": b.get("line"), "odds": b.get("odds"),
        "book": b.get("book") or "",
        "hit_prob": b.get("win_prob"), "ev_per_unit": b.get("ev_per_unit"),
        "edge": b.get("edge"), "grade": b.get("grade"),
        "game_date": b.get("date") or "",
        "recommended": bool(b.get("recommended")),
        "warnings": list(b.get("warnings") or []),
        "headline": b.get("headline") or b.get("pick_label") or "",
        "home": home, "away": away,
        # The MLB game-bet layer flags its own numbers as not credible when
        # the model disagrees with the market by more than the guard allows.
        # A leg its own engine will not stand behind is not a parlay leg.
        "credible": b.get("credible", True),
        "volatility": "LOW", "tier": 1, "_game_leg": True,
    }


def _family(leg: dict) -> str:
    return FAMILY.get(leg.get("market", ""), leg.get("market", ""))


def leg_tier(leg: dict) -> int:
    m = leg.get("market", "")
    if m in TIER:
        return TIER[m]
    for key in ("tier", "market_tier"):
        if isinstance(leg.get(key), int):
            return leg[key]
    return 2


def game_key(leg: dict) -> tuple:
    """Which game a leg belongs to.

    A game TOTAL belongs to neither team, so its normalized `team` and
    `opponent` are both empty — keyed off those alone every game total on
    the slate would collide into one bucket and get screened against each
    other. Prefer the explicit home/away when the leg carries it.
    """
    if leg.get("home") or leg.get("away"):
        pair = (leg.get("home") or "", leg.get("away") or "")
    else:
        pair = (leg.get("team") or "", leg.get("opponent") or "")
    return (tuple(sorted(pair)), leg.get("game_date") or "")


def _relate_game_leg(sport, a, b, game, fa, fb, ua, ub, same_team) -> Relation | None:
    """Pairs where at least one leg is a side or a total.

    Returns None when nothing here applies, so the caller falls through to
    the player-only taxonomy. Every magnitude is the bottom of its published
    band, same as everywhere else in this module.
    """
    fams = {fa, fb}

    # --- two game lines in one game --------------------------------------
    if fa in GAME_FAMILIES and fb in GAME_FAMILIES:
        if fams == {"side"}:
            if same_team:
                # A moneyline and a spread on the same team are one opinion
                # priced twice — the shortest ticket in the world wearing two
                # legs. §3 Type 6, and an extreme case of it.
                return Relation(0.80, "a side and a spread on the same team are "
                                      "one opinion sold twice — §3 Type 6 at "
                                      "its most extreme", 6, "duplicate")
            return Relation(-0.90, "two sides of one game — they cannot both "
                                   "win; §3 Type 1", 1, "kill")
        if fams == {"teamtotal"} and not same_team:
            if ua == ub:
                # Both teams over (or both under) is the pace bet, twice.
                return Relation(0.30, "both teams' totals moving the same way "
                                      "is one pace bet — §8.2 puts a pace-up "
                                      "game at +0.30 to +0.45", 6, "duplicate")
            # §5.3, banned by name: "legs from both sides of the same game's
            # run-scoring environment (one team's total over + other team's
            # total under)".
            return Relation(-0.20, "one team's total over against the other's "
                                   "under is a bet on the same run-scoring "
                                   "environment in both directions — §5.3 "
                                   "bans it by name", 2, "kill")
        if fams == {"teamtotal", "gametotal"}:
            if ua == ub:
                return Relation(0.55, "a team total and the game total are "
                                      "near-restatements — §4.1/§5.1 put this "
                                      "at +0.55 to +0.70, so the ticket is "
                                      "really about 1.3 bets", 6, "duplicate")
            return Relation(-0.55, "a team total and the game total pointing "
                                   "opposite ways need the same game to score "
                                   "twice and not score once", 2, "kill")
        if fams == {"side", "gametotal"}:
            # §6.1's scheme-sign rule. The sign is genuinely strong in BOTH
            # directions depending on whether the favourite drains clock or
            # plays fast, and the doc says getting it backwards is the most
            # expensive CFB parlay error there is. We do not carry adjusted
            # tempo, run/pass identity by down, or 4th-down aggressiveness for
            # any league. Refusing beats guessing a sign on a large number.
            fav = (game or {}).get("favorite") or ""
            backed = a.get("team") if fa == "side" else b.get("team")
            if fav and backed and fav.upper() == str(backed).upper():
                return Relation(0.0, "a favourite covering correlates with the "
                                     "under for a clock-draining team and the "
                                     "over for a tempo team — §6.1 requires "
                                     "adjusted tempo and run/pass identity "
                                     "before a sign can be assigned, and this "
                                     "model does not carry them", 2, "kill")
            return Relation(0.20, "a dog keeping pace does it by scoring — "
                                  "§6.2 puts dog covers against the game total "
                                  "over at +0.20 to +0.35", 0, "ok")
        if fams == {"side", "teamtotal"}:
            if same_team and ua and ub:
                return Relation(0.30, "the team that scores wins — §4.1 puts a "
                                      "team total over against its own side at "
                                      "+0.30 to +0.45", 0, "ok")
            if same_team:
                return Relation(-0.30, "backing a team while betting its own "
                                       "total under — §3 Type 2, opposite "
                                       "scripts", 2, "kill")
            return Relation(-0.20, "backing one team while betting the other's "
                                   "total over is two halves of a contradiction",
                            2, "kill")
        return None

    # --- one game line, one player prop ----------------------------------
    line, prop = (a, b) if fa in GAME_FAMILIES else (b, a)
    lf = fa if fa in GAME_FAMILIES else fb
    pf = fb if fa in GAME_FAMILIES else fa
    line_up = _side_up(line)
    prop_up = _side_up(prop)
    prop_team = (prop.get("team") or "").upper()
    line_team = (line.get("team") or "").upper()
    own = bool(line_team) and line_team == prop_team

    if lf == "gametotal":
        # §5.1: strikeouts up wants fewer baserunners, the game total up wants
        # more. Type 2, and one of the doc's named script clashes.
        if sport == "mlb" and pf in PITCHER_FAMILIES and prop_up and line_up:
            return Relation(-0.15, "strikeouts up and the game total up want "
                                   "opposite innings — §5.1 Type 2", 2, "kill")
        if prop_up and line_up:
            return Relation(SAME_GAME_BASELINE_RHO,
                            "a player over and the game total over share the "
                            "same pace — §1.1's floor", 0, "ok")
        if prop_up != line_up:
            return Relation(-SAME_GAME_BASELINE_RHO,
                            "a player over against the game total under is the "
                            "pace link running the wrong way", 2, "kill")
        return None

    if lf == "teamtotal":
        # §3 Type 1, stated in the doc's own example: "team under + that
        # team's star way over". Not a correlation problem, a logic problem.
        if own and line_up != prop_up and prop_up:
            return Relation(-0.35, "a team's total under against that team's "
                                   "own player over — §3 Type 1, the two legs "
                                   "describe different games", 1, "kill")
        if own and line_up and prop_up:
            if pf in ("pass", "catch", "score", "bat", "rush"):
                return Relation(0.30, "the player's production IS the team's "
                                      "runs or points — §4.1/§5.1/§8.2 all put "
                                      "this at +0.30 or better", 0, "ok")
            return Relation(SAME_GAME_BASELINE_RHO,
                            "same team, same direction — the pace floor", 0, "ok")
        # The pitcher stack's third leg: strikeouts up, the lineup he is
        # facing held down. §5.1 calls this the cleanest MLB correlation.
        if (sport == "mlb" and pf in PITCHER_FAMILIES and prop_up
                and not line_up and line_team == (prop.get("opponent") or "").upper()):
            return Relation(0.20, "strikeouts up and the lineup he is facing "
                                  "held down — §5.1's cleanest MLB "
                                  "correlation, and §5.2's pitcher stack",
                            0, "ok")
        if not own and line_up and prop_up and line_team == (prop.get("opponent") or "").upper():
            return Relation(-0.20, "backing a player over while betting the "
                                   "opposing offence over is not one story",
                            2, "kill")
        return None

    # lf == "side": a moneyline or spread next to a player prop.
    if own:
        # §3 Type 4, the most-missed clash in every sport. Handled per-leg in
        # _leg_eligible against the slate's spread; this catches the pairing
        # where the SIDE leg is the one laying the points.
        spread = abs(float((game or {}).get("spread") or 0.0))
        bar = (RULES.get(sport) or SportRules(sport, sport)).blowout_spread
        fav = ((game or {}).get("favorite") or "").upper()
        if bar is not None and fav == line_team and spread >= bar:
            return Relation(-0.15, f"backing a favourite laying {spread:g} "
                                   f"alongside that favourite's own starter — "
                                   f"§3 Type 4, the blowout that wins leg one "
                                   f"takes leg two off the field", 4, "kill")
        if pf == "rush" and prop_up:
            return Relation(0.35, "leading teams run — §4.1 puts carries "
                                  "against the team's own side at +0.35 to "
                                  "+0.50", 0, "ok")
        if sport == "mlb" and pf in PITCHER_FAMILIES and prop_up:
            return Relation(0.20, "managers leave winners in — §5.1 puts outs "
                                  "recorded against his team's line at +0.20 "
                                  "to +0.35", 0, "ok")
        if pf in ("pass", "catch") and prop_up:
            # §4.1's trailing-dog mechanism: the script that makes the dog
            # cover CAUSES the passing volume. On a favourite the same pairing
            # is only the weak generic link.
            if fav and fav != line_team:
                return Relation(0.20, "the script that keeps a dog close is the "
                                      "script that makes it throw — §4.1 puts "
                                      "dog covers against dog pass-catcher "
                                      "overs at +0.20 to +0.35", 0, "ok")
            return Relation(SAME_GAME_BASELINE_RHO,
                            "same team, same direction — the pace floor", 0, "ok")
        if prop_up:
            return Relation(SAME_GAME_BASELINE_RHO,
                            "same team, same direction — the pace floor", 0, "ok")
        return Relation(-SAME_GAME_BASELINE_RHO,
                        "backing a team while betting its own player under",
                        2, "kill")
    # Opposite team.
    if prop_up:
        return Relation(-SAME_GAME_BASELINE_RHO,
                        "backing one team while betting the other's player "
                        "over — the two legs pull against each other", 2, "kill")
    return Relation(SAME_GAME_BASELINE_RHO,
                    "backing a team while betting the other side's player "
                    "under — the same story from both ends", 0, "ok")


def relate(sport: str, a: dict, b: dict, game: dict | None = None) -> Relation:
    """Classify a pair of legs against §3's taxonomy and §4-8's prior tables.

    Ordered most-fatal first: a pair that is both a Type 5 and a Type 3 is a
    Type 5, because that is the disposition that kills it.
    """
    same_game = game_key(a) == game_key(b)
    same_team = (a.get("team") or "_a") == (b.get("team") or "_b")
    same_player = (a.get("player") or "_a") == (b.get("player") or "_b")
    fa, fb = _family(a), _family(b)
    ua, ub = _side_up(a), _side_up(b)

    # Type 5 — single point of failure. "If he sits, everything dies."
    #
    # §3 Type 5 and §5.2 contradict each other and the contradiction has to be
    # resolved rather than picked from. Type 5 says "same-player multi-prop is
    # banned outright" and then, in its very next sentence, "two legs sharing
    # one player's availability is permitted at most once per ticket, and only
    # when the player is confirmed active with a Minutes/Usage Grade of A."
    # Meanwhile §5.2 names the pitcher stack — strikeouts over PLUS outs over,
    # one player, two markets — "the single best 3-leg construction in your
    # entire system."
    #
    # The reading that satisfies both: the ban is the default, the confirmed-
    # active exception is real, and an announced starting pitcher is the
    # cleanest instance of it in any sport. So a same-player pair survives only
    # inside the pitcher family, only when both legs run the same direction,
    # and only once per ticket (enforced in _evaluate).
    if same_player:
        if (sport == "mlb" and fa in PITCHER_FAMILIES and fb in PITCHER_FAMILIES
                and ua == ub):
            # No band is published for strikeouts-over against outs-over. Using
            # the low end of the nearest published pitcher band (§5.1's outs
            # over vs his team's ML, +0.20 to +0.35) rather than inventing a
            # larger number for the construction the doc likes most.
            return Relation(0.20, "one arm, one mechanism, two markets moving "
                                  "together — §5.2's pitcher stack, which books "
                                  "often price as if the pair were independent",
                            5, "ok")
        return Relation(0.0, "the same player twice — if he sits, everything "
                             "dies; §3 Type 5 bans it", 5, "kill")

    if not same_game:
        # §0.3: independent legs at a multiplicative price are strictly
        # dominated by singles. Priced honestly at zero and left for Gate 6
        # to kill, which is the gate that exists to kill it.
        return Relation(0.0, "different games — no shared mechanism", 0, "ok")

    # --- pairs involving a game line ----------------------------------------
    # These carry most of the doc's permitted constructions, so they are
    # classified before the player-only rules rather than falling through to
    # the same-game baseline.
    if _is_game_leg(a) or _is_game_leg(b):
        rel = _relate_game_leg(sport, a, b, game, fa, fb, ua, ub, same_team)
        if rel is not None:
            return rel

    # Type 7 — direct opposition. One leg winning IS the other losing.
    if sport == "mlb":
        pitcher, hitter = None, None
        if fa in PITCHER_FAMILIES and fb in HITTER_FAMILIES:
            pitcher, hitter = a, b
        elif fb in PITCHER_FAMILIES and fa in HITTER_FAMILIES:
            pitcher, hitter = b, a
        if pitcher is not None and hitter is not None:
            facing = (hitter.get("team") or "") == (pitcher.get("opponent") or "")
            if facing and _side_up(pitcher) and _side_up(hitter):
                return Relation(-0.25, "the same pitches cannot strike out the "
                                       "side and get hit — §5.1 puts this at "
                                       "-0.25 to -0.40", 7, "kill")
            if facing and _side_up(pitcher) and not _side_up(hitter):
                return Relation(0.20, "strikeouts up, the bats he is facing "
                                      "down — one mechanism, §5.1's cleanest "
                                      "MLB correlation", 0, "ok")
    if same_team and {fa, fb} == {"pass", "catch"} and ua != ub:
        return Relation(-0.30, "a quarterback and his own receiver need "
                               "opposite passing games — §4.1 calls this "
                               "incoherent", 7, "kill")

    # Type 2 — script clash. Each leg fine alone; together one must fail.
    # §4.3 bans a quarterback and a running back from the same team in the same
    # ticket outright, in either direction, so this does not check sides.
    if same_team and {fa, fb} == {"pass", "rush"}:
        return Relation(-0.15, "the pass game wants a trailing script and the "
                               "run game wants a leading one — §4.1 puts this "
                               "at -0.15 to -0.30 and §4.3 bans the pairing "
                               "outright", 2, "kill")
    if sport == "mlb" and {fa, fb} == {"pitch", "bat"} and ua and ub and not same_team:
        return Relation(-0.15, "strikeouts up and the game total up want "
                               "opposite innings — §5.1 Type 2", 2, "kill")

    # Type 3 — possession pie. A finite shared resource, split two ways.
    if same_team and fa == fb and ua and ub:
        if sport == "mlb":
            # Baseball's plate appearances are not rivalrous the way targets
            # are: two hitters in one lineup face the same pitcher and the
            # same innings. §5.1 puts this at +0.20 to +0.35 — a permitted
            # construction, not a clash.
            return Relation(0.20, "two bats in one lineup against one starter "
                                  "— §5.1 puts this at +0.20 to +0.35", 0, "ok")
        return Relation(-0.10, f"two teammates splitting one {fa} pie — §3 "
                               f"Type 3 cannibalisation", 3, "kill")

    # §3's Type 6 examples are all team-total-against-game-total pairings,
    # and those are classified in _relate_game_leg. A blanket player-prop
    # duplicate rule here used to shadow the rule below it and price a
    # quarterback next to his own receiver — §4.1's STRONGEST usable NFL
    # correlation and the anchor of the passing-game stack — as a
    # near-restatement to be penalised. Two players are not a restatement of
    # each other.

    # The permitted positive constructions, at the bottom of each band.
    if same_team and {fa, fb} == {"pass", "catch"} and ua and ub:
        return Relation(0.35, "one passing game wearing two jerseys — §4.1's "
                              "strongest usable NFL correlation", 0, "ok")
    if same_team and {fa, fb} == {"assist", "score"} and ua and ub:
        return Relation(0.15, "the same possessions completing — §8.2", 0, "ok")

    if ua and ub:
        return Relation(SAME_GAME_BASELINE_RHO,
                        "shared pace and script — §1.1's floor for any two "
                        "same-game overs", 0, "ok")
    if ua != ub and not same_team:
        return Relation(SAME_GAME_BASELINE_RHO,
                        "one side up and the other down across the matchup — "
                        "the pace link runs the same way", 0, "ok")
    return Relation(-SAME_GAME_BASELINE_RHO,
                    "two unders in one game share pace the wrong way for a "
                    "ticket that needs both", 2, "kill")


# --- Gate 1: standalone eligibility -----------------------------------------
def _leg_eligible(sport: str, leg: dict, game: dict | None,
                  rules: SportRules) -> str:
    """Empty string when the leg may enter a ticket; otherwise the reason.

    §2 Gate 1 is mostly satisfied by construction — every candidate is
    already `recommended`, meaning it cleared its sport's approval gate as a
    single. What is added here is the set of bans that apply to a leg
    *because* it is going inside a ticket.
    """
    if not leg.get("recommended"):
        return ("not a recommended single — §0: a leg that would not be a bet "
                "on its own is never a bet inside a parlay")
    tier = leg_tier(leg)
    if not rules.tier3_allowed and tier >= 3:
        return (f"{leg.get('market_label') or leg.get('market')} is a Tier 3 "
                f"market — §8.4 bans those from any multi-leg WNBA ticket")
    if (str(leg.get("volatility", "")).upper() == "EXTREME"
            or leg.get("market") in EXTREME_MARKETS):
        return (f"{leg.get('market_label') or leg.get('market')} is an EXTREME "
                f"volatility market — no place inside a compounding structure")
    if leg.get("warnings"):
        return f"carries a live warning: {leg['warnings'][0]}"

    g = game or {}
    # A game leg its own engine will not stand behind. The MLB game-bet
    # layer marks a price not credible when the model disagrees with the
    # market by more than the guard allows — §0's rule that a leg which
    # would not be a bet on its own is never a bet inside a parlay applies
    # to that judgement too.
    if leg.get("credible") is False:
        return ("the game-bet layer flagged this price as not credible on its "
                "own — §0: a leg that would not be a bet by itself is never a "
                "bet inside a parlay")
    # §5.4 / §4.4: weather overrides invalidate every total-linked leg, and a
    # team total is total-linked by definition. "Re-run the gates from Gate
    # 1 — do not patch a leg."
    if _family(leg) in ("teamtotal", "gametotal"):
        wind = float(((g.get("weather") or {}).get("wind_mph")) or 0.0)
        roofed = str(g.get("roof", "")).lower() in ("dome", "closed", "retractable")
        if sport == "mlb" and wind >= 12 and not roofed:
            return (f"wind {wind:g} mph in an open park — §5.4 invalidates "
                    f"every total-linked leg on the ticket")
    # §3 Type 4 does not apply to a side: laying the points IS the bet. It
    # applies to the player props standing behind it, which is checked below.
    # §5: the lineup rule dominates everything in baseball.
    if sport == "mlb" and _family(leg) in HITTER_FAMILIES:
        if not g.get("lineups_confirmed", False):
            return ("the lineup is not confirmed — §5: a parlay containing an "
                    "unconfirmed hitter is not a conditional parlay, it is not "
                    "a bet")
    # §3 Type 4 / §8.1: the blowout that pulls the starters.
    if rules.blowout_spread is not None and not _is_game_leg(leg):
        spread = abs(float(g.get("spread") or 0.0))
        fav = (g.get("favorite") or "").upper()
        if spread >= rules.blowout_spread and fav and fav == (leg.get("team") or "").upper():
            return (f"{fav} is laying {spread:g} — §3 Type 4: the blowout that "
                    f"makes the favourite cover is the blowout that takes this "
                    f"player off the field")
    # §7.3: apply the NBA blowout downgrade BEFORE Gate 1, not after.
    if float(leg.get("blowout_prob") or 0.0) > 0.25:
        return ("blowout probability over 25% — §7.3 drops the minutes grade a "
                "full step, and a degraded leg is ineligible")
    # §4.4 / §5.4: weather overrides that kill whole families outright.
    wind = float(((g.get("weather") or {}).get("wind_mph")) or 0.0)
    if sport in ("nfl", "cfb") and wind >= 15 and _family(leg) in ("pass", "catch"):
        return (f"wind {wind:g} mph — §4.4 kills passing constructions outright "
                f"regardless of edge")
    if sport == "mlb" and wind >= 12 and str(g.get("roof", "")).lower() == "open":
        if _family(leg) in HITTER_FAMILIES:
            return (f"wind {wind:g} mph in an open park — §5.4 invalidates "
                    f"total-linked legs; re-run from Gate 1, do not patch")
    # §6.4: bowl season is where CFB parlays go to die.
    if sport == "cfb" and str(g.get("date", ""))[5:7] in ("12", "01"):
        return ("December/bowl window — §6.4 bans every ticket until "
                "participation, opt-outs and coaching status are verified")
    return ""


# --- Gates 2-7 ---------------------------------------------------------------
@dataclass
class Ticket:
    sport: str
    legs: list[dict]
    pairs: list[dict] = field(default_factory=list)
    modeled_joint: float = 0.0
    independent_joint: float = 0.0
    threshold: float = 0.0
    required_dec: float = 0.0
    best_case_dec: float = 0.0
    ev_singles: float = 0.0
    parlay_type: str = "A"
    duplicate: bool = False
    verdict: str = ""
    stake_if_promoted: float = 0.0
    edge_at_ceiling: float = 0.0


def _evaluate(sport: str, legs: list[dict], rules: SportRules,
              games: dict | None = None) -> tuple[Ticket | None, str]:
    """Run gates 2 through 6 on one candidate. Returns (ticket, kill reason)."""
    n = len(legs)
    idx = list(itertools.combinations(range(n), 2))
    # The game matters. Every §3 Type 4 rule, §4.1's trailing-dog mechanism
    # and §6.1's scheme-sign refusal all turn on who the favourite is and by
    # how much — without it they silently never fire, and a ticket that
    # should be killed reads as merely uncorrelated.
    games = games or {}
    rels = [relate(sport, legs[i], legs[j], games.get(game_key(legs[i])))
            for i, j in idx]

    # Gate 2 — clash screen.
    for (i, j), rel in zip(idx, rels):
        if rel.verdict == "kill":
            return None, (f"Type {rel.clash}: {legs[i].get('player')} + "
                          f"{legs[j].get('player')} — {rel.mechanism}")

    # §3 Type 5's exception is "permitted at most once per ticket". A three-leg
    # ticket carrying two same-player pairs is three props on one player, which
    # is the banned construction wearing the exception's clothes.
    if sum(1 for r in rels if r.clash == 5) > 1:
        return None, ("Type 5: more than one same-player pair — §3 permits the "
                      "shared-availability exception once per ticket, not twice")

    # The per-sport construction bans from §4-§9. These sit AFTER the clash
    # screen deliberately. They are ticket-shape rules, not Gate 1 leg
    # eligibility, and running them first buries the answer the reader
    # actually needs: told "no Tier 1 anchor" when the real problem is that
    # the ticket pairs a quarterback with his own running back, a reader
    # learns the wrong lesson.
    # §4's anchor rule names Tier 1 VOLUME markets — receptions, attempts,
    # carries, completions. A side or a total anchors at least as well: they
    # are the lowest-variance markets on the board, and §6.3's permitted CFB
    # ticket is two sides and a total with no player prop in it at all. So
    # the rule is "something steady has to carry this", not "a player prop
    # has to carry this".
    if rules.anchor_tier1 and not any(leg_tier(l) == 1 or _is_game_leg(l)
                                      for l in legs):
        return None, ("§4 anchor rule: nothing on this ticket is a Tier 1 "
                      "volume market or a game line. Tier 3 markets never "
                      "anchor — those are the legs that turn a good process "
                      "into a lottery ticket")
    tier3 = sum(1 for l in legs if leg_tier(l) >= 3)
    if tier3 >= max(2, n if rules.tier3_allowed else 1):
        return None, (f"§4.3 / §8.4: {tier3} Tier 3 legs — high-volatility "
                      f"markets have no place inside a compounding structure")

    # Gate 3 — correlation sign. Net must be positive, and no pair may be
    # negative: §2 is explicit that a negatively correlated pair means paying
    # a tax for the privilege of betting against yourself.
    if any(r.rho < 0 for r in rels):
        return None, "Gate 3: a negatively correlated pair — never inside a ticket"
    same_game = len({game_key(l) for l in legs}) == 1
    # Gate 3's "net correlation must be positive" is a same-game rule: it is
    # about pairs that share a mechanism. A cross-game (Type B) ticket has no
    # mechanism to share and sits at zero by construction, so failing it here
    # would kill Type B on the wrong gate. §7.2 is explicit that Gate 6 is the
    # one that kills these, "correctly" — and the dominance test's reason is
    # the one a reader can act on, because it says bet the singles instead.
    if same_game and sum(r.rho for r in rels) <= 0:
        return None, "Gate 3: net correlation is not positive"

    # §3 Type 6 — a duplicate pair means the ticket is really about 1.3 bets,
    # so it is priced at the shorter ticket's bar and never counted as
    # diversification.
    duplicate = any(r.verdict == "duplicate" or r.rho > 0.50 for r in rels)

    # Gate 4 — joint probability via the conditional chain, never the product.
    ps = [float(l.get("hit_prob") or l.get("p_final") or 0.0) for l in legs]
    if min(ps) <= 0.0:
        return None, "Gate 4: a leg carries no modelled probability"
    independent = math.prod(ps)
    priced = [r.rho * RHO_SHRINK for r in rels]
    if n == 2:
        modeled = joint_two(ps[0], ps[1], priced[0])
    else:
        modeled = joint_three(tuple(ps), tuple(priced))

    # §3 Type 6 disposition: treat the ticket as a 2-leg for threshold
    # purposes, which for a 3-leg means the HIGHER bar of the two, per "count
    # as one and require the higher bar".
    eff_legs = n
    thr = rules.threshold(eff_legs)
    if duplicate and n == 3:
        thr = max(thr, rules.threshold(3))

    # Gate 5, inverted — the price the book must beat.
    if modeled <= thr:
        return None, (f"Gate 5: modelled joint {modeled:.1%} does not clear the "
                      f"{thr:.1%} threshold at any price")
    price_dec = 1.0 / (modeled - thr)

    # Gate 6, inverted. §1.3 reads EV_singles as the SUM over legs, and that
    # literal reading is what makes §0.3 true: for independent legs priced at
    # the true product, EV_parlay = prod(1+e_i) - 1, which exceeds sum(e_i)
    # only by the cross terms — never by 25%. The dominance test is
    # calibrated to kill exactly that ticket, so the sum is the reading.
    # Derived from the same p and price the joint was built on, rather than
    # read off the leg. Both sides of a comparison have to use one set of
    # numbers or the ratio measures the gap between two models instead of
    # the gap between two instruments. The stored field is the fallback.
    def _leg_ev(l: dict, p: float) -> float:
        odds = l.get("odds")
        if odds:
            return p * (american_to_decimal(odds) - 1.0) - (1.0 - p)
        return float(l.get("ev_per_unit") or l.get("ev") or 0.0)

    ev_singles = sum(_leg_ev(l, p) for l, p in zip(legs, ps))
    dom_dec = (1.0 + DOMINANCE_MULTIPLE * ev_singles) / modeled
    required = max(price_dec, dom_dec)

    naive_dec = math.prod(american_to_decimal(l.get("odds") or -110) for l in legs)
    # A cross-game ticket is a straight multiplication at every book — there
    # is no correlation to tax. That is exactly why §0.3 says singles
    # dominate it, and why the tax only comes off the same-game price.
    if not same_game:
        best_case = naive_dec
    else:
        best_case = naive_dec * (1 - BEST_CASE_SGP_TAX)
        # §1.2's flat 15-30% band describes a typical SGP, and it is the
        # right ceiling for one: a book that taxed the full correlation
        # would be quoting far shorter than 70-85% of the naive product, so
        # the band itself is evidence the book is NOT pricing correlation
        # fully. That gap is what §0.3 Type A exists to exploit, and a
        # ceiling derived from "the book knows at least as much as we do"
        # would define Type A out of existence.
        #
        # It breaks down at the top of the range. A moneyline and a spread
        # on the same team are nearly one bet, and no book pays 85% of the
        # product for a pair that cashes together almost always. Left
        # uncapped, that artifact was the ONLY two-leg ticket that ever
        # cleared this screen — its single "yes" would have been its most
        # duplicative candidate, at a price no book has ever offered.
        #
        # So the cap applies to duplicates only, where nothing is being
        # exploited and the correlation is not in dispute: a book will never
        # pay more than the correlated fair price. §3 Type 6's disposition
        # is "priced, not celebrated", and this is what pricing it means.
        if duplicate:
            fair = [r.rho for r in rels]
            j_book = (joint_two(ps[0], ps[1], fair[0]) if n == 2
                      else joint_three(tuple(ps), tuple(fair)))
            if j_book > 0:
                best_case = min(best_case, 1.0 / j_book)

    t = Ticket(sport=sport, legs=legs, modeled_joint=modeled,
               independent_joint=independent, threshold=thr,
               required_dec=required, best_case_dec=best_case,
               ev_singles=ev_singles, duplicate=duplicate,
               parlay_type="A" if same_game else "B")
    t.pairs = [{"a": legs[i].get("player"), "b": legs[j].get("player"),
                "rho": round(rel.rho, 2), "rho_priced": round(rel.rho * RHO_SHRINK, 3),
                "mechanism": rel.mechanism, "clash": rel.clash}
               for (i, j), rel in zip(idx, rels)]

    # Gate 7 — exposure, and the stake we would have made had this ticket
    # been off probation. Kelly on the joint at the required price.
    b = required - 1.0
    kelly = (modeled * required - 1.0) / b if b > 0 else 0.0
    t.stake_if_promoted = round(min(STAKE_CAP_U, max(0.0, kelly) * rules.kelly * 100), 2)

    if required > best_case:
        ceiling = (f"the most generous price a book would plausibly quote — "
                   f"the naive product less §1.2's kindest "
                   f"{BEST_CASE_SGP_TAX:.0%} correlation tax"
                   if same_game else
                   f"straight multiplication of the leg prices, which is what "
                   f"a cross-game ticket pays and is therefore the ceiling")
        t.verdict = (
            f"No qualifying parlay at current numbers. This needs "
            f"{decimal_to_american(required):+d} or better; {ceiling} is "
            f"{decimal_to_american(best_case):+d}."
            + ("" if same_game else
               f" The gate it fails is dominance: these legs are worth "
               f"{ev_singles:+.1%} bet separately, and §0.3 is not an opinion "
               f"— diversifying a fixed edge across independent bets raises "
               f"expected growth, so bet the singles."))
    else:
        t.verdict = (
            f"Bet only at {decimal_to_american(required):+d} or better. We "
            f"cannot see the book's quote for this ticket, so this is the "
            f"number to check, not a claim about what is offered.")
    return t, ""


def screen(slate: dict, sport: str, bankroll_state: str = "normal") -> dict:
    """Screen a built slate for parlays. Returns the Parlay Zone payload.

    `bankroll_state` is the drawdown circuit-breaker: §10.2 says parlays go to
    zero during a drawdown, not to half.
    """
    rules = RULES.get(sport) or SportRules(sport, sport.upper())
    out: dict = {
        "sport": sport, "date": slate.get("date", ""),
        "probation": True, "tickets": [], "considered": 0,
        "killed": [], "notes": [], "eligible_legs": 0,
        "doctrine": ("A parlay is not a bet type, it is a pricing structure. "
                     "It is only ever correct when that structure is "
                     "mispriced — never because three plays look good "
                     "together."),
        "probation_note": (
            "Parlays are graded, never staked. The bar is 100 graded tickets "
            "clearing positive flat-stake ROI, aggregate leg-level CLV at or "
            "above zero, and z of at least 2 — and the singles board has to "
            "clear its own promotion bar first. Until then every ticket here "
            "is a tracked observation worth nothing."),
        "price_note": (
            "No odds feed we ingest carries same-game-parlay prices, and an "
            "SGP price is not derivable from the leg prices — the correlation "
            "tax is the book's number, not ours. So instead of inventing a "
            "quote, each ticket publishes the price it must beat."),
    }
    if rules.unavailable:
        out["verdict"] = "No qualifying parlay at current numbers."
        out["notes"].append(rules.unavailable)
        return out

    if bankroll_state == "drawdown":
        out["verdict"] = "No qualifying parlay at current numbers."
        out["notes"].append(
            "§10.2: parlays are suspended entirely during a drawdown "
            "circuit-breaker. When stakes are halved, parlays go to zero — not "
            "half. The drawdown is the state in which reaching for variance is "
            "most tempting and most expensive.")
        return out

    games = {(tuple(sorted((g.get("away") or "", g.get("home") or ""))),
              g.get("date") or ""): g for g in slate.get("games") or []}
    # Player props AND game lines. Almost every construction §4-§8 permits
    # ends on a team total or a side, and CFB has no player props at all —
    # its §6.3 ticket is two sides and a total. Screening one list only left
    # the doc's own permitted constructions unbuildable.
    recs = [r for r in (slate.get("recommendations") or []) if r.get("recommended")]
    recs += [normalize_game_bet(b, sport)
             for b in (slate.get("game_bets") or []) if b.get("recommended")]

    pool: list[dict] = []
    for r in recs:
        g = games.get(game_key(r))
        why = _leg_eligible(sport, r, g, rules)
        if why:
            out["killed"].append({"gate": 1, "leg": r.get("headline")
                                  or r.get("player"), "reason": why})
        else:
            pool.append(r)
    out["eligible_legs"] = len(pool)

    by_game: dict = {}
    for r in pool:
        by_game.setdefault(game_key(r), []).append(r)

    # "We recommend eighteen props and cannot parlay any of them" needs an
    # answer, and the answer is usually structural rather than a judgement.
    # A correlated ticket needs two eligible legs IN ONE GAME. Baseball's
    # board is one starter per game plus hitters, and §5 holds every hitter
    # until the lineup is posted — so before first pitch each game contributes
    # exactly one leg and there is no same-game pair on the whole slate, no
    # matter how many props are recommended. That is worth saying out loud
    # instead of leaving the reader to infer it from an empty page.
    paired = sum(1 for rows in by_game.values() if len(rows) >= 2)
    out["games_with_a_pair"] = paired
    out["games_represented"] = len(by_game)
    if pool and not paired:
        out["notes"].append(
            f"Tonight's {len(pool)} eligible leg(s) come from {len(by_game)} "
            f"different game(s) — no single game has two. A correlated ticket "
            f"needs two legs sharing one game, because the correlation IS the "
            f"shared game; without that there is nothing to price but the "
            f"straight product, and §0.3 shows singles beat that every time."
            + (" In baseball this is usually the lineup rule (§5): hitters "
               "stay ineligible until the card is posted, so before first "
               "pitch each game offers only its starter." if sport == "mlb"
               else ""))

    candidates: list[list[dict]] = []
    for rows in by_game.values():
        for k in (2, min(rules.max_legs, 3)):
            if k <= len(rows):
                candidates += [list(c) for c in itertools.combinations(rows, k)]
    if rules.cross_game != "banned":
        # §7.2 / §0.3: cross-game tickets are permitted only at true
        # multiplicative pricing with a documented reason. They are screened
        # so that Gate 6 can kill them on the record rather than by omission.
        for c in itertools.combinations(pool, 2):
            if game_key(c[0]) != game_key(c[1]):
                candidates.append(list(c))
    else:
        out["notes"].append(
            f"§8.4: cross-game {rules.name} parlays are banned entirely — the "
            f"league plays too few simultaneous games for genuine independence "
            f"to be worth the tax.")

    seen: set = set()
    tickets: list[Ticket] = []
    for legs in candidates:
        sig = tuple(sorted((l.get("player") or "") + "|" + (l.get("market") or "")
                           for l in legs))
        if sig in seen:
            continue
        seen.add(sig)
        out["considered"] += 1
        t, why = _evaluate(sport, legs, rules, games)
        if t is None:
            out["killed"].append({"gate": 2, "leg": " + ".join(
                str(l.get("player")) for l in legs), "reason": why})
            continue
        tickets.append(t)

    # Rank the board, then say separately whether the top of it clears.
    #
    # These are two different questions and the page owes an answer to both.
    # "Which of tonight's props parlay together best?" always has an answer as
    # long as two legs survive the clash screen. "Does that ticket beat
    # betting them as singles?" almost never does. Collapsing the two — 
    # publishing nothing whenever the second answer is no — turns a page built
    # to rank the board into a page that refuses to look at it.
    #
    # The old ranking was worse than useless: it sorted on
    # best_case / required, and best_case has the correlation tax deducted for
    # a same-game ticket and NOT for a cross-game one. So an uncorrelated pair
    # from two different stadiums always looked closest to clearing, and the
    # page led with a rho of +0.00 and the words "no shared mechanism" — the
    # single construction §0.3 says is strictly dominated, presented as the
    # best thing on the board.
    #
    # Rank instead on the edge each ticket would have at the price a book
    # would plausibly quote. That is §1.3's Test 1 evaluated at the ceiling,
    # it is directly comparable between tickets, and it charges a same-game
    # ticket for its tax while crediting it for its correlation. Cross-game
    # tickets sort below every same-game one regardless: §0.3 is not a
    # preference, it is a proof, and a ticket with no mechanism has nothing to
    # recommend it over the same legs bet separately.
    def _edge_at_ceiling(t):
        return t.modeled_joint - (1.0 / t.best_case_dec if t.best_case_dec else 1.0)

    for t in tickets:
        t.edge_at_ceiling = _edge_at_ceiling(t)
    tickets.sort(key=lambda t: (0 if t.parlay_type == "A" else 1,
                                -t.edge_at_ceiling))
    live = [t for t in tickets if t.required_dec <= t.best_case_dec]
    # §0.2 prefers two legs to three among tickets that actually clear.
    live.sort(key=lambda t: (len(t.legs), -t.edge_at_ceiling))

    if live:
        out["verdict"] = (
            f"{len(live)} ticket{'s' if len(live) > 1 else ''} cleared all "
            f"seven gates — graded, not staked.")
        # §10.2 caps the operation at one parlay per slate, so the rest are
        # shown as ranked alternatives rather than as plays.
        chosen = live[:rules.max_per_slate]
        rest = [t for t in tickets if t not in chosen][:SHORTLIST - len(chosen)]
        chosen += rest
        if len(live) > rules.max_per_slate:
            out["notes"].append(
                f"{len(live) - rules.max_per_slate} other ticket(s) cleared "
                f"too. §10.2 caps the whole operation at one parlay per slate "
                f"across all sports, so only the first is a play; the rest are "
                f"ranked below it.")
    else:
        chosen = tickets[:SHORTLIST]
        out["verdict"] = "No qualifying parlay at current numbers."
    out["shortlist"] = len(chosen)

    out["tickets"] = [_publish(t, qualified=t.required_dec <= t.best_case_dec,
                               rank=i + 1)
                      for i, t in enumerate(chosen)]
    # The clash ledger is the most useful thing on this page: it is the record
    # of which props were fighting each other and which §3 type settled it.
    # One pair killed inside both a 2-leg and a 3-leg candidate produces the
    # same sentence twice, so collapse on the sentence itself.
    dedup, seen_reason = [], set()
    for k in out["killed"]:
        if k["reason"] in seen_reason:
            continue
        seen_reason.add(k["reason"])
        dedup.append(k)
    out["killed"] = dedup
    if not tickets:
        # Two different nothings, and conflating them is misleading. Either
        # the board never had two eligible legs in one game to begin with, or
        # it did and the clash screen took every pair. The first is a quiet
        # slate; the second is the screen doing its job.
        out["notes"].append(
            "Nothing on tonight's board can even form a candidate: §14 says a "
            "ticket arrives only after every leg has independently earned a "
            "place as a single, and no single game has two eligible legs left."
            if not out["considered"] else
            "Every candidate on tonight's board died in the screen. §14 is the "
            "reason that is the normal result: a ticket has to survive a real, "
            "positive, mechanically explainable correlation before it is worth "
            "the tax, and almost nothing does.")
    return out


def attach(slate: dict, sport: str, bankroll_state: str = "normal") -> dict:
    """Screen a slate and hang the result on it as `parlays`.

    Called from each builder immediately before the JSON is written, so the
    Parlay Zone is computed once at build time from exactly the board the
    reader is looking at — never recomputed in the browser from a subset of
    the props, which is how a page ends up recommending a ticket whose legs
    are no longer on the board.

    Never raises. A parlay screen failing must not take down a slate that is
    otherwise fine; the page renders the failure instead.
    """
    try:
        slate["parlays"] = screen(slate, sport, bankroll_state=bankroll_state)
    except Exception as exc:                       # pragma: no cover - guard
        slate["parlays"] = {
            "sport": sport, "tickets": [], "probation": True, "killed": [],
            "considered": 0, "eligible_legs": 0,
            "verdict": "No qualifying parlay at current numbers.",
            "notes": [f"The parlay screen did not run for this slate: {exc}"]}
    return slate


def _publish(t: Ticket, qualified: bool, rank: int = 1) -> dict:
    """Shape one ticket the way §12 prints it and §11 logs it."""
    naive = math.prod(american_to_decimal(l.get("odds") or -110) for l in t.legs)
    return {
        "sport": t.sport,
        "rank": rank,
        "parlay_type": t.parlay_type,
        "qualified": qualified,
        # §1.3 Test 1 evaluated at the price a book would plausibly quote —
        # the number the shortlist is ordered on, in points.
        "edge_at_ceiling_points": round(t.edge_at_ceiling * 100, 1),
        "legs": [{
            "player": l.get("player"), "team": l.get("team"),
            "opponent": l.get("opponent"),
            "market": l.get("market"),
            "market_label": l.get("market_label"),
            "side": l.get("side"), "line": l.get("line"),
            "odds": l.get("odds"), "book": l.get("book"),
            "p_final": round(float(l.get("hit_prob") or l.get("p_final") or 0), 4),
            "grade": l.get("grade"), "tier": leg_tier(l),
            "headline": l.get("headline"),
        } for l in t.legs],
        "pairs": t.pairs,
        "clash_screen": ("Types 1-7 checked · cleared"
                         if not t.duplicate else
                         "Types 1-7 checked · Type 6 duplicate priced in, not "
                         "counted as diversification"),
        "independent_joint": round(t.independent_joint, 4),
        "modeled_joint": round(t.modeled_joint, 4),
        "independent_american": decimal_to_american(1 / t.independent_joint)
        if t.independent_joint > 0 else 0,
        "modeled_american": decimal_to_american(1 / t.modeled_joint)
        if t.modeled_joint > 0 else 0,
        "threshold_points": round(t.threshold * 100, 1),
        "naive_product_dec": round(naive, 3),
        "naive_product_american": decimal_to_american(naive),
        "required_dec": round(t.required_dec, 3),
        "required_american": decimal_to_american(t.required_dec),
        "best_case_american": decimal_to_american(t.best_case_dec),
        "correlation_tax_best_case": round(BEST_CASE_SGP_TAX, 3),
        "correlation_tax_worst_case": round(WORST_CASE_SGP_TAX, 3),
        "singles_alternative_ev": round(t.ev_singles, 4),
        # How far short a ticket falls, as a number. On this board the answer
        # is almost always "short", and "short by 9%" is a far more useful
        # thing to read than a bare no — it says whether the gap is a rounding
        # error or a canyon.
        "shortfall_pct": (round((t.required_dec / t.best_case_dec - 1) * 100, 1)
                          if t.best_case_dec > 0 and t.required_dec > t.best_case_dec
                          else 0.0),
        "dominance_required": DOMINANCE_MULTIPLE,
        "stake_units": 0.0,                       # §13: graded, not staked
        "stake_if_promoted": t.stake_if_promoted,
        "verdict": t.verdict,
        "risk": _risk(t),
    }


def _risk(t: Ticket) -> str:
    """§12's last line: the honest case against, naming the leg most likely
    to kill it."""
    worst = min(t.legs, key=lambda l: float(l.get("hit_prob")
                                            or l.get("p_final") or 1.0))
    p = float(worst.get("hit_prob") or worst.get("p_final") or 0.0)
    return (f"{worst.get('player')} {worst.get('side', '')} "
            f"{worst.get('line', '')} {worst.get('market_label', '')} is the "
            f"weakest link at {p:.0%} — it fails roughly {1 - p:.0%} of the "
            f"time on its own, and it takes the whole ticket with it. Two "
            f"legs cashing and one missing pays the same as three misses.")
