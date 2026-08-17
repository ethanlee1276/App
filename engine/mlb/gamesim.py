"""Play tonight's game twenty thousand times, and read every prop off the
same simulated games.

WHY THIS EXISTS, WHEN CLOSED-FORM PRICING ALREADY WORKS

It does not price a prop better. `build_mlb_projection` already produces a
mean and a standard deviation per prop, tuned and calibrated against years
of logs, and nothing here improves on that number. What it produces that a
per-prop distribution structurally cannot is the JOINT: the chance two props
in the same game both land.

That matters because the Parlay Zone currently gets leg correlation from
priors fitted against our own history (task #52) — a reasonable estimate of
how two markets move together on average. A shared game sim does not
estimate it. Both legs come out of the same simulated innings, so if a
leadoff hitter's extra plate appearance is what gives the cleanup hitter his
fifth, the sim knows, because it dealt both.

THE INVERSION, WHICH IS THE WHOLE DESIGN

The obvious way to build this is a new batter-versus-pitcher model, and it
is the wrong way: it would produce a second set of marginals that disagree
with the first, and a page showing two numbers for one question has a defect
rather than a feature.

So the rates are INVERTED out of the projections we already trust. Given a
hitter's projected hits, total bases and home runs per game, plus how many
plate appearances his lineup spot gets, there is a per-PA outcome table that
reproduces exactly those three means. Solve for it and the sim agrees with
the pricing engine by construction — leaving the joint distribution as the
only new information, which is the only new information wanted.

WHAT IS NOT MODELLED, ON PURPOSE

Base-out state, pitcher fatigue as a function of pitch count, pinch hitters,
and the fact that a rally gives the whole lineup an extra turn are all real.
Only the last is captured, and it is captured because it falls out of the
inning loop for free rather than because it was modelled. Everything else
would need evidence this repo does not have, and a simulation that invents
detail is a simulation that invents correlation.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .models import HITS, HOME_RUNS, TOTAL_BASES

#: Plate appearances by lineup spot, for a nine-inning game. The leadoff
#: spot bats about three quarters of a turn more than the ninth over a
#: season, and using one flat number for all nine would hand the bottom of
#: the order the top's playing time — which inflates exactly the cheap props
#: a longshot board is most tempted by.
PA_BY_SPOT = {1: 4.65, 2: 4.55, 3: 4.45, 4: 4.35, 5: 4.25,
              6: 4.15, 7: 4.05, 8: 3.95, 9: 3.85}
PA_DEFAULT = 4.2

#: Share of non-home-run hits that are triples. Triples are not projected
#: separately anywhere in this engine and are too rare to infer per hitter,
#: so they take a league constant; doubles then absorb whatever total-bases
#: the solve still needs. Getting this wrong moves a hitter's total bases by
#: hundredths.
TRIPLE_SHARE = 0.022

#: A batter has to reach base without it being a hit sometimes, or the sim
#: ends innings faster than baseball does and everyone loses plate
#: appearances. Walk rate is not projected per hitter either; league average
#: is the honest default.
LEAGUE_BB_RATE = 0.085

#: Innings in a simulated game. Extras exist and are ignored: they occur in
#: under a tenth of games and add a partial inning to both teams, which
#: moves a per-game mean by less than the sampler's own noise.
INNINGS = 9

#: THE SHARED GAME LATENT, and the measurement that set it.
#:
#: The first working version of this module held every rate fixed across
#: trials, so the only thing two hitters shared was lineup turnover: more
#: baserunners, more plate appearances for everyone. That is a real channel
#: and it produced a real, positive correlation — phi ≈ +0.034 across
#: same-lineup pairs.
#:
#: It is also about a third of the truth. `engine/parlays.py` carries a
#: MEASURED lineup_stack rho of +0.186 fitted on 27,613 real games, and run
#: through this engine's own copula at these marginals that implies phi in
#: the region of +0.11. A sim reproducing +0.034 is not capturing something
#: baseball does.
#:
#: What it was missing is the thing parlays.py already names: "same-game
#: correlation runs through one shared latent (game script, pace…)". Holding
#: the pitcher fixed across trials assumes he is equally good every night.
#: He is not, and neither is the wind or the zone — and every hitter in the
#: lineup is exposed to the same draw. So each trial scales the whole
#: lineup's reaching rates by one shared factor.
#:
#: The magnitude is SOLVED, not chosen: `calibrate_env_sd` sweeps it until
#: the sim reproduces the measured correlation. That is the point — the
#: dependence here is anchored to 27,613 games rather than invented by a
#: simulation that would happily produce any number asked of it.
#:
#: The sweep, at 20,000 trials against a target phi of +0.1152 — the phi
#: that the measured rho of +0.186 implies at these marginals, through this
#: engine's own copula:
#:
#:     env_sd   phi       |err|    gate
#:      0.00   +0.0434   0.0717   pass     (lineup turnover alone)
#:      0.15   +0.0624   0.0528   pass
#:      0.25   +0.0998   0.0153   pass
#:      0.30   +0.1257   0.0105   pass
#:      0.35   +0.1441   0.0289   pass
#:      0.40   +0.1646   0.0494   pass
#:
#: 0.30 is the closest on absolute error, and 0.25 is the value, because the
#: two miss in opposite directions and this engine has already decided which
#: direction it accepts. `engine/parlays.py`, CONSERVATISM: "Understating
#: correlation understates the joint, which raises the required price, which
#: makes the screen pickier. When the numbers are guesses, that is the
#: direction to be wrong in." 0.30 overstates; 0.25 understates by about 13%.
#:
#: Worth recording because the first version of this comment said 0.30 was
#: unavailable because it FAILED the reconciliation gate. That was true
#: against a gate which compared a flat relative tolerance and so was
#: accidentally strict on rare markets — a 0.05-per-game home-run rate moves
#: several percent between seeds. Once the gate learned to forgive the
#: sampler's own noise, 0.30 passed, and the real reason to decline it
#: turned out to be doctrine rather than arithmetic.
#:
#: Re-swept after FIT_DAMP changed the fitting step this sweep runs
#: through. Every phi above reproduces within sampler noise (0.25 → +0.1024,
#: 0.30 → +0.1250), so neither the value nor the argument for it moves. One
#: verdict did: 0.40 now FAILS the gate where it passed before. It was
#: never a candidate, and the direction is the expected one — a shock that
#: wide is where a lineup-wide rescale has the least chance of landing all
#: nine hitters at once.
ENV_SD = 0.25

#: Clamp on the shared draw. A game where nobody can reach at all, or where
#: every rate doubles, is not a bad night — it is a broken sample, and at
#: the tails a multiplicative shock stops describing baseball.
ENV_CLAMP = (0.35, 1.75)


@dataclass
class BatterRates:
    """One hitter's per-plate-appearance outcome probabilities.

    They sum to 1. ``out`` absorbs everything that is not a walk or a hit,
    strikeouts included — the sim does not need to tell a strikeout from a
    groundout for any hitter market this engine prices.
    """

    out: float
    bb: float
    single: float
    double: float
    triple: float
    hr: float
    name: str = ""
    spot: int = 0
    #: Was the projected (hits, total bases, home runs) triple valid
    #: baseball? False means the three means cannot coexist — most often
    #: total bases too low for the hits and homers claimed, e.g. a game
    #: shape like "2 hits, 4 TB, 1 HR", which leaves zero bases for the
    #: non-HR hit. The inversion clamps to the nearest VALID table, so the
    #: rates are usable — but they cannot reproduce all three means, and a
    #: reconciliation gate that includes them is grading the sim on a
    #: question no table could answer. The flag exists so the caller can
    #: route the finding where it belongs: at the projection engine.
    consistent: bool = True

    def cumulative(self) -> list[float]:
        """Cumulative thresholds, in the order the sim draws them."""
        acc, out = 0.0, []
        for p in (self.out, self.bb, self.single, self.double,
                  self.triple, self.hr):
            acc += p
            out.append(acc)
        return out


def expected_pa(spot: int) -> float:
    return PA_BY_SPOT.get(spot, PA_DEFAULT)


def rates_from_means(hits: float, total_bases: float, home_runs: float,
                     pa: float, bb_rate: float = LEAGUE_BB_RATE) -> BatterRates:
    """Invert three projected per-game means into one per-PA outcome table.

    ``hits``, ``total_bases`` and ``home_runs`` are per GAME (what
    build_mlb_projection produces); ``pa`` is how many plate appearances the
    hitter's lineup spot gets. The solve:

        hr/PA          = home_runs / pa
        hit/PA         = hits / pa
        non-HR hits    = hit/PA - hr/PA
        bases from     = (total_bases - 4*home_runs) / pa
          non-HR hits
        triples        = TRIPLE_SHARE of non-HR hits
        singles+doubles, and singles+2*doubles+3*triples, then solve.

    Every clamp below is a place the arithmetic can be handed something
    baseball cannot do — a total-bases projection lower than the hits
    projection, say, which implies negative doubles. Clamping keeps the
    table a valid distribution; the caller finds out via ``consistent``.
    """
    pa = max(float(pa), 1e-6)
    p_hr = max(0.0, home_runs / pa)
    p_hit = max(0.0, hits / pa)
    consistent = home_runs <= hits + 1e-9
    p_hr = min(p_hr, p_hit)                    # a homer is a hit
    nonhr = max(0.0, p_hit - p_hr)
    bases_nonhr = max(0.0, (total_bases - 4.0 * home_runs) / pa)
    # Each non-HR hit is worth at least one base, and at most what THIS
    # table can actually deliver. That ceiling is not three.
    #
    # A single is one base and a double is two, so an order made entirely
    # of doubles reaches 2.0; only triples go past it, and triples are a
    # league constant here (TRIPLE_SHARE) because they are too rare to
    # infer per hitter. With doubles capped at every remaining non-HR hit,
    # the most the solve below can produce is
    #     2*(nonhr - p_3b) + 3*p_3b  =  nonhr * (2 + TRIPLE_SHARE)
    # and the bound used to read 3.0. Everything in between was reported
    # as valid baseball and then quietly under-delivered: measured, a
    # hitter projected for 2.5 bases per non-HR hit came out 19% light on
    # total bases, and 30% at 2.9. The gate would then report a
    # disagreement neither model caused.
    #
    # Above the ceiling is not a sim finding either. Reaching it needs most
    # of a hitter's extra-base hits to be triples, which no projection
    # should be claiming — so it is flagged like every other impossible
    # triple and routed at the projection engine.
    #
    # Nothing on the board reaches it today: `reconcile_triple` already
    # caps total bases at MAX_BASES_PER_NONHR_HIT = 1.9, comfortably under
    # 2.022, so every triple arriving here through the pricing path is
    # already inside this bound. The gap was for callers that invert raw
    # projections directly, and it is closed here rather than left to be
    # rediscovered if that cap ever moves.
    max_bases_per_hit = 2.0 + TRIPLE_SHARE
    if (bases_nonhr < nonhr - 1e-9
            or bases_nonhr > max_bases_per_hit * nonhr + 1e-9):
        consistent = False
    p_3b = nonhr * TRIPLE_SHARE
    # singles + doubles = nonhr - p_3b
    # singles + 2*doubles = bases_nonhr - 3*p_3b
    p_2b = (bases_nonhr - 3.0 * p_3b) - (nonhr - p_3b)
    p_2b = min(max(p_2b, 0.0), max(0.0, nonhr - p_3b))
    p_1b = max(0.0, nonhr - p_3b - p_2b)
    p_bb = max(0.0, min(bb_rate, 1.0 - p_hit - 1e-9))
    p_out = 1.0 - (p_bb + p_1b + p_2b + p_3b + p_hr)
    if p_out < 0.0:
        # More on-base events than plate appearances. Scale the reaching
        # outcomes down together rather than picking one to sacrifice.
        scale = (1.0 - 1e-6) / (p_bb + p_1b + p_2b + p_3b + p_hr)
        p_bb, p_1b, p_2b = p_bb * scale, p_1b * scale, p_2b * scale
        p_3b, p_hr = p_3b * scale, p_hr * scale
        p_out = 1.0 - (p_bb + p_1b + p_2b + p_3b + p_hr)
    return BatterRates(out=p_out, bb=p_bb, single=p_1b, double=p_2b,
                       triple=p_3b, hr=p_hr, consistent=consistent)


@dataclass
class GameSim:
    """Simulated per-batter outcome tallies, and the joints between them."""

    trials: int
    names: list[str] = field(default_factory=list)
    #: name -> market -> {threshold: times cleared}
    over: dict = field(default_factory=dict)
    #: (name_a, market_a, line_a, name_b, market_b, line_b) -> times both hit
    both: dict = field(default_factory=dict)
    pa_mean: dict = field(default_factory=dict)
    mean: dict = field(default_factory=dict)
    #: Standard ERROR of each simulated mean. The gate needs it: a flat
    #: relative tolerance is accidentally strict on a rare market, where a
    #: 0.05-per-game home-run rate moves several percent on sampler noise
    #: alone, and accidentally loose on a common one.
    se: dict = field(default_factory=dict)

    def p_over(self, name: str, market: str, line: float) -> float | None:
        d = (self.over.get(name) or {}).get(market)
        if not d:
            return None
        return d.get(_key(line), 0) / self.trials

    def p_both(self, a: tuple, b: tuple) -> float | None:
        """``a``/``b`` are (name, market, line). Order-independent."""
        k = _pair_key(a, b)
        v = self.both.get(k)
        return None if v is None else v / self.trials

    def correlation(self, a: tuple, b: tuple) -> float | None:
        """Phi coefficient between two legs — the number the Parlay Zone
        currently takes from a fitted prior."""
        pa_ = self.p_over(*a)
        pb = self.p_over(*b)
        pab = self.p_both(a, b)
        if pa_ is None or pb is None or pab is None:
            return None
        denom = (pa_ * (1 - pa_) * pb * (1 - pb)) ** 0.5
        if denom <= 0:
            return None
        return (pab - pa_ * pb) / denom


def _key(line: float) -> str:
    return f"{float(line):.1f}"


def _pair_key(a: tuple, b: tuple) -> tuple:
    ka = (a[0], a[1], _key(a[2]))
    kb = (b[0], b[1], _key(b[2]))
    return (ka, kb) if ka <= kb else (kb, ka)


#: What each outcome is worth, for the markets read off the sim.
_BASES = (0, 0, 1, 2, 3, 4)          # out, bb, 1B, 2B, 3B, HR
_IS_HIT = (0, 0, 1, 1, 1, 1)


def simulate_lineup(rates: list[BatterRates], legs: list[tuple],
                    trials: int = 20000, seed: int | None = 7,
                    innings: int = INNINGS, env_sd: float = ENV_SD) -> GameSim:
    """Bat one lineup ``trials`` times and tally the requested legs.

    ``legs`` are (name, market, line) triples — the props actually on the
    board. Only those are tallied, and every unordered pair of them gets a
    joint count, because the joint is the reason this exists.

    Seeded like the season simulator, and for the same reason: a page whose
    numbers jitter every refresh reads as noise even when the model is
    stable, and nobody can tell a real move from the sampler.
    """
    rng = random.Random(seed)
    order = list(rates)
    n = len(order)
    if not n:
        return GameSim(trials=0)
    base = [b.cumulative() for b in order]
    cums = base
    idx_of = {b.name: i for i, b in enumerate(order)}

    # EVERYTHING CONSTANT ABOUT A LEG IS COMPUTED ONCE, HERE. What used to
    # be in the trial loop was `_key(line)` — an f-string — twice per live
    # leg and four more times per live PAIR, which on a real board is 107
    # million string formats and 46 million `_pair_key` calls for numbers
    # that never change. The loop now counts into flat lists indexed by leg,
    # and the dict shapes are assembled from those counts at the end.
    #
    # The leg ids are assigned in the SAME order the trial loop discovers
    # them (`want` in insertion order, each list in order), so `live` comes
    # out ascending and every pair is (smaller, larger) without sorting.
    want: dict[int, list[tuple]] = {}
    leg_of: list[tuple] = []             # leg id -> (name, market, line)
    for name, market, line in legs:
        i = idx_of.get(name)
        if i is None:
            continue
        want.setdefault(i, []).append((market, float(line)))
    # Market codes, so the loop compares ints instead of building a dict of
    # three entries per hitter per trial. Anything the sim does not tally
    # scores 0, which is what `got.get(market, 0)` did.
    _CODE = {HITS: 0, TOTAL_BASES: 1, HOME_RUNS: 2}
    plan: list[tuple] = []               # (batter idx, code, line, leg id)
    for i, wants in want.items():
        for market, line in wants:
            plan.append((i, _CODE.get(market, -1), line, len(leg_of)))
            leg_of.append((order[i].name, market, line))
    n_legs = len(leg_of)
    leg_key = [_key(line) for _name, _m, line in leg_of]
    pair_key_of = [[None] * n_legs for _ in range(n_legs)]
    for x in range(n_legs):
        for y in range(x + 1, n_legs):
            pair_key_of[x][y] = _pair_key(leg_of[x], leg_of[y])
    over_counts = [0] * n_legs
    pair_counts = [[0] * n_legs for _ in range(n_legs)]

    sim = GameSim(trials=trials, names=[b.name for b in order])
    hit_counts = [0] * n
    tb_counts = [0] * n
    hr_counts = [0] * n
    pa_counts = [0] * n
    hit_sq = [0] * n
    tb_sq = [0] * n
    hr_sq = [0] * n
    over = {b.name: {} for b in order}
    both: dict = {}

    lo_env, hi_env = ENV_CLAMP
    # Locals, not globals/attributes, for the two loops below — they run
    # ~130 million times on a full board, and an attribute lookup per pass
    # is the kind of cost that only shows up at that count.
    #
    # `reaching` carries each hitter's five non-out rates plus their sum,
    # summed in exactly the order the old expression used. That matters more
    # than it looks: `g_i` divides `reach` back by `g` rather than using the
    # sum directly, and `(s * g) / g` is not always `s` to the last bit. The
    # sum is hoisted; the arithmetic around it is left alone, so the draws
    # and the tables stay identical.
    rand = rng.random
    gauss = rng.gauss
    is_hit, bases = _IS_HIT, _BASES
    reaching = [(b.bb, b.single, b.double, b.triple, b.hr,
                 b.bb + b.single + b.double + b.triple + b.hr) for b in order]
    innings_range = range(innings)
    for _ in range(trials):
        if env_sd > 0:
            # One draw for the whole lineup: tonight's starter, tonight's
            # wind, tonight's zone. Scaling the REACHING outcomes and
            # letting `out` absorb the remainder keeps each table a valid
            # distribution, and because the draw is centred on 1.0 the
            # per-game means it produces stay put — checked by `reconcile`,
            # which runs with the shock on.
            g = min(hi_env, max(lo_env, gauss(1.0, env_sd)))
            cums = []
            for bb, s1, s2, s3, s4, s in reaching:
                reach = s * g
                if reach >= 1.0:
                    g_i = (1.0 - 1e-9) / (reach / g)
                else:
                    g_i = g
                # Unrolled, and a tuple rather than a list: this rebuilds
                # every hitter's table on every trial, so the six appends
                # and the throwaway tuple of products were ~100 allocations
                # a trial for six numbers. The additions happen in the same
                # order they did, which is what keeps the thresholds — and
                # therefore the draws they are compared against — identical.
                c0 = 1.0 - s * g_i
                c1 = c0 + bb * g_i
                c2 = c1 + s1 * g_i
                c3 = c2 + s2 * g_i
                c4 = c3 + s3 * g_i
                cums.append((c0, c1, c2, c3, c4, c4 + s4 * g_i))
        g_h = [0] * n
        g_tb = [0] * n
        g_hr = [0] * n
        g_pa = [0] * n
        spot = 0
        for _inning in innings_range:
            outs = 0
            while outs < 3:
                # The order wraps by hand rather than by `spot % n`. It is
                # the same index either way; a modulo per plate appearance
                # is simply ~130 million of them on a full board.
                i = spot
                spot += 1
                if spot == n:
                    spot = 0
                g_pa[i] += 1
                r = rand()
                c = cums[i]
                # Linear scan over six buckets beats bisect at this size and
                # keeps the hot loop free of a function call.
                k = 0
                while k < 5 and r >= c[k]:
                    k += 1
                if k == 0:
                    outs += 1
                    continue
                g_h[i] += is_hit[k]
                g_tb[i] += bases[k]
                if k == 5:
                    g_hr[i] += 1
        for i in range(n):
            hit_counts[i] += g_h[i]
            tb_counts[i] += g_tb[i]
            hr_counts[i] += g_hr[i]
            pa_counts[i] += g_pa[i]
            hit_sq[i] += g_h[i] * g_h[i]
            tb_sq[i] += g_tb[i] * g_tb[i]
            hr_sq[i] += g_hr[i] * g_hr[i]

        # Which of tonight's actual legs cleared, this trial. Counted by leg
        # id into flat lists; the names, the ".1f" keys and the canonical
        # pair keys are all attached once, after the loop.
        live = []
        for i, code, line, leg in plan:
            if (g_h[i] if code == 0 else
                    g_tb[i] if code == 1 else
                    g_hr[i] if code == 2 else 0) > line:
                live.append(leg)
                over_counts[leg] += 1
        for x in range(len(live)):
            lx = live[x]
            row = pair_counts[lx]
            for y in range(x + 1, len(live)):
                row[live[y]] += 1

    # Fold the flat counts back into the shapes callers read. Accumulated
    # with `+=` rather than assigned, because two legs can canonicalise onto
    # one slot — the same board asking for the same (player, market, line)
    # twice — and the loop this replaced added them together.
    for leg in range(n_legs):
        c = over_counts[leg]
        if not c:
            continue
        name, market, _line = leg_of[leg]
        d = over[name].setdefault(market, {})
        k = leg_key[leg]
        d[k] = d.get(k, 0) + c
    for x in range(n_legs):
        row = pair_counts[x]
        keys = pair_key_of[x]
        for y in range(x + 1, n_legs):
            c = row[y]
            if c:
                k2 = keys[y]
                both[k2] = both.get(k2, 0) + c
    sim.over = over
    sim.both = both
    for i, b in enumerate(order):
        sim.pa_mean[b.name] = pa_counts[i] / trials
        sim.mean[b.name] = {
            HITS: hit_counts[i] / trials,
            TOTAL_BASES: tb_counts[i] / trials,
            HOME_RUNS: hr_counts[i] / trials,
        }
        sim.se[b.name] = {
            m: _stderr(tot, sq, trials) for m, tot, sq in (
                (HITS, hit_counts[i], hit_sq[i]),
                (TOTAL_BASES, tb_counts[i], tb_sq[i]),
                (HOME_RUNS, hr_counts[i], hr_sq[i]))}
    return sim


def _stderr(total: int, sq: int, trials: int) -> float:
    if trials < 2:
        return 0.0
    mean = total / trials
    var = max(0.0, sq / trials - mean * mean)
    return (var / trials) ** 0.5


def _scale_reaching(b: BatterRates, k: float) -> BatterRates:
    """One hitter's table with every reaching outcome scaled by ``k``."""
    reach = (b.bb + b.single + b.double + b.triple + b.hr) * k
    if reach >= 1.0:
        k *= (1.0 - 1e-9) / reach
    return BatterRates(
        out=1.0 - (b.bb + b.single + b.double + b.triple + b.hr) * k,
        bb=b.bb * k, single=b.single * k, double=b.double * k,
        triple=b.triple * k, hr=b.hr * k, name=b.name, spot=b.spot,
        consistent=b.consistent)


#: A league-average filler bat, in per-game means. Only ever used to
#: complete a short order — never graded, never priced.
FILLER_MEANS = (0.85, 1.38, 0.11)


def pad_to_nine(rates: list[BatterRates]) -> list[BatterRates]:
    """Complete a short batting order with league-average filler.

    A real lineup always has nine batters. When only eight are projected
    — a pitcher's spot, a name the feed could not match — simulating the
    eight we have cycles the order 9/8 too fast and hands every remaining
    hitter about 12% more plate appearances than his spot actually gets.
    Measured on a live slate: an eight-man Dodgers lineup put Ohtani at
    5.24 PA against the 4.65 his spot assumes, and the whole lineup then
    failed the reconcile gate for reasons that had nothing to do with the
    projections.

    The filler is deliberately absent from ``targets``, so it shapes the
    turnover without ever being graded or bet.
    """
    have = {int(getattr(b, "spot", 0) or 0) for b in rates}
    out = list(rates)
    for spot in range(1, 10):
        if spot in have:
            continue
        f = rates_from_means(*FILLER_MEANS, expected_pa(spot))
        f.name, f.spot = f"_filler{spot}", spot
        out.append(f)
    return sorted(out, key=lambda b: b.spot or 9)


#: UNDER-RELAXATION on the fitting step, and the measurement that set it.
#:
#: The naive step is `k = target / simulated`: the hitter's number came in
#: 10% light, so scale his reaching outcomes up 10%. That step assumes the
#: response is linear, and it is not — which is the same fact this whole
#: function exists because of. Scaling a hitter's reaching rates by k does
#: not move his total bases by k, because reaching base also lengthens the
#: inning, which hands the WHOLE lineup another turn. The response is
#: nearer k**(1+eps), so a full-gain step overshoots by roughly eps times
#: the error it was correcting, and when eps approaches 1 the loop stops
#: contracting and starts ringing.
#:
#: eps grows with how often the lineup reaches, so this is invisible on an
#: average order and severe on a good one. Measured as the TRUE post-fit
#: bias in mean total bases, 150,000 trials per cell, a nine-man order
#: scaled off league average (1.00), and `damp` as the exponent applied to
#: the step, k = (target/simulated) ** damp:
#:
#:     lineup   damp 1.0/3   damp 0.8/3   damp 0.7/3   damp 0.6/3   0.6/6
#:      0.65      -0.9%        +0.1%        -0.0%        +0.0%      +0.0%
#:      0.80      -0.4%        -0.1%        +0.1%        +0.5%      +0.2%
#:      1.00      +0.2%        +0.1%        +0.2%        +0.3%      +0.4%
#:      1.15      -0.9%        -0.4%        -0.8%        -0.0%      -0.2%
#:      1.30      -5.0%        +0.5%        -0.1%        -0.6%      +0.0%
#:      1.50      -6.8%        -0.9%        -0.8%        +0.7%      -0.3%
#:
#: The first column is what shipped, and the bottom two rows are the bug:
#: a strong lineup went into the fit 17.8% hot and came out 5.0% COLD,
#: having been corrected past the target and left there. That is what the
#: live gate was reporting — a dozen real lineups failing with every one of
#: a hitter's three markets off by the same percentage in the same
#: direction, which is the signature of a single rescale applied to his
#: whole table rather than anything wrong with the projections.
#:
#: Three RAGGED orders — every spot scaled independently, since a real
#: lineup is not one flat multiple of league average — were run through the
#: same sweep and are the reason the top rows are in the table at all. A
#: previous attempt at this same failure was reverted because it repaired
#: the strong lineup by breaking a balanced one, so a control is not
#: optional here. Worst |mean| over all nine cases: 6.8% at damp 1.0/3,
#: 0.4% at 0.6/6.
#:
#: 0.6 is the fitted optimum where it matters: backing the observed
#: contraction out of the 1.30 row gives eps around 0.65, and the exact
#: step for that is 1/(1+eps) = 0.61. Milder damping also works over the
#: range measured, and 0.6 is preferred because it stays comfortable on
#: extrapolation — at an eps of 1.2, beyond anything tested here, 0.8 is
#: still barely converging while 0.6 is nowhere near the boundary.
FIT_DAMP = 0.6

#: Rounds of the fitting loop. Raised with the damping, and by it: a damped
#: step deliberately corrects less per round, so the regimes with weak
#: feedback — where the old full-gain step was already fine — need more
#: passes to walk in. Six is chosen off the same sweep, where 0.6/6 is the
#: only column with no cell worse than 0.4%.
FIT_ROUNDS = 6

#: Trials per fitting round, and the reason it is not smaller.
#:
#: Every round computes its step from a SAMPLED mean, so it scales a
#: hitter's whole table by that round's sampler error as well as by the
#: correction — and the last round's is never re-measured. The noise
#: therefore lands in the shipped rates. It is worst exactly where it is
#: least affordable: a hitter projected for 0.119 total bases a game is
#: measured ten times less precisely, in relative terms, than one at 1.9,
#: so the bottom of a real batting order absorbs the most.
#:
#: This ran at 8,000, and the live gate found it. With the overshoot fixed,
#: four lineups still failed, and `sim_diagnose.py` on the dump reported
#: the same cause for all four — re-fitting at 60,000 trials a round took
#: the offending hitters from -0.066/+0.106/-0.063/-0.068 to
#: -0.016/+0.016/-0.037/-0.031, every one of them inside the gate.
#:
#: 60,000 is not the value, because it is 7.5x the cost for no gain over
#: the knee. Sweeping trials per round against the TRUE post-fit bias in
#: total bases (250,000-trial evaluation, averaged over three fit seeds,
#: worst hitter in the lineup) — where "thin" carries the real sub-.100
#: bats the live failures were found on:
#:
#:     trials/round   total cost   ordinary    thin     hot
#:        8,000          48,000      0.020    0.043    0.018
#:       16,000          96,000      0.011    0.018    0.011
#:       25,000         150,000      0.014    0.020    0.014
#:       40,000         240,000      0.012    0.021    0.009
#:
#: Everything from 16,000 up is one plateau; 8,000 is the only row off it,
#: and only the thin lineup notices, which is precisely the shape that was
#: failing. Doubling buys the whole improvement available.
FIT_TRIALS = 16000


def calibrate(rates: list[BatterRates], targets: dict,
              trials: int = FIT_TRIALS, seed: int | None = 7,
              env_sd: float = ENV_SD, rounds: int = FIT_ROUNDS,
              damp: float = FIT_DAMP) -> list[BatterRates]:
    """Re-centre the rate tables so the SIMULATED means hit the projections.

    The inversion in `rates_from_means` is exact per plate appearance, and
    that is not the same as exact per game, for a reason worth stating: a
    hitter's plate-appearance count is not a constant, it is a consequence.
    Reaching base gives the whole lineup another turn, so a mean-1.0 shock
    on the rates produces a mean-ABOVE-1.0 effect on counting stats, and the
    drift grows with the shock. Measured: at ENV_SD 0.25 the marginals ran
    7% hot, which fails `reconcile` — the sim quietly disagreeing with the
    pricing engine, which is exactly the failure the gate exists to catch.

    So the rates are fitted rather than derived: simulate, compare, scale
    each hitter's reaching outcomes toward target/simulated, repeat. The
    step is DAMPED rather than full-gain, because the same feedback that
    makes the fit necessary also makes the obvious step overshoot — see
    FIT_DAMP, which carries the measurement.

    Each round is coarser than the production run, but not as coarse as it
    once was, and the reason is worth naming: the step is computed from a
    SAMPLED mean, so every round scales a hitter's whole table by that
    round's sampler error as well as by the correction, and the last
    round's is never re-measured. Damping attenuates the noise it injects
    along with the overshoot, but it does not remove it, and the cheapest
    remaining lever is simply measuring better — see FIT_TRIALS, which
    carries what the live gate cost before it was raised.
    """
    cur = list(rates)
    for _ in range(max(1, rounds)):
        sim = simulate_lineup(cur, [], trials=trials, seed=seed, env_sd=env_sd)
        nxt = []
        for b in cur:
            got = sim.mean.get(b.name) or {}
            want = targets.get(b.name) or {}
            # Total bases carries the most information about the table's
            # shape — it weights every outcome — so it drives the rescale.
            have = got.get(TOTAL_BASES)
            aim = want.get(TOTAL_BASES)
            if not have or not aim:
                nxt.append(b)
                continue
            step = (aim / have) ** damp
            nxt.append(_scale_reaching(b, min(2.0, max(0.5, step))))
        cur = nxt
    return cur


def calibrate_env_sd(rates: list[BatterRates], targets: dict,
                     legs: list[tuple], pairs: list[tuple],
                     target_phi: float, trials: int = 20000,
                     seed: int | None = 7,
                     grid: tuple = (0.0, 0.1, 0.2, 0.3, 0.4)) -> dict:
    """Find the shared-latent width that reproduces a MEASURED correlation.

    This is the honest anchor for the whole module. A simulation will
    produce whatever dependence its parameters imply, so a correlation read
    off one is worth nothing unless the parameter was set by something
    outside the simulation. Here that something is
    `engine/parlays.py` MEASURED["lineup_stack"] — 27,613 real games.

    Returns the best grid point and the curve, so a caller can see whether
    the target sat inside the range swept or the sweep ran out of room.
    """
    out = []
    for sd in grid:
        fitted = calibrate(rates, targets, env_sd=sd, seed=seed)
        sim = simulate_lineup(fitted, legs, trials=trials, seed=seed, env_sd=sd)
        phis = [p for p in (sim.correlation(a, b) for a, b in pairs)
                if p is not None]
        if not phis:
            continue
        got = sum(phis) / len(phis)
        out.append({"env_sd": sd, "phi": round(got, 4),
                    "err": round(abs(got - target_phi), 4),
                    "reconcile": reconcile(sim, targets)})
    if not out:
        return {"best": None, "curve": []}
    best = min(out, key=lambda d: d["err"])
    return {"best": best, "curve": out, "target_phi": target_phi}


#: How many standard errors of sampler noise the gate forgives before it
#: calls a gap real. Two sigma: a difference smaller than that is a
#: measurement about the trial count, not about the model.
RECONCILE_SIGMA = 2.5


def reconcile(sim: GameSim, targets: dict, tol: float = 0.06) -> dict:
    """THE GATE. Do the sim's marginals match the projections it was built
    from?

    Nothing downstream may read a joint from a sim that fails this. Two
    numbers for the same question on one page is a defect, and reconciling
    them is also the cheapest way to find a bug in either model — the sim
    disagreeing with the closed-form projection means one of them is wrong,
    and which one is a question worth being forced to answer.

    ``targets`` is name -> market -> projected per-game mean. ``tol`` is a
    RELATIVE tolerance; the default is loose enough to absorb sampler noise
    at 20,000 trials and the lineup-turnover effect (a hitter's realised
    plate appearances depend on how often his team-mates reach, which the
    per-spot constant only approximates), and tight enough that a genuine
    inversion bug cannot hide behind it.

    ``worst_rel_error`` is the largest RAW relative gap, forgiven ones
    included, so it can legitimately exceed ``tol`` on a passing lineup —
    which looks like a broken tool unless the reason is to hand. So
    ``noise_rel`` comes back too: the sampler's own relative error on the
    market where it is largest, at this trial count. A worst error under
    that is a statement about how long the simulation ran, not about
    either model. Both numbers are needed to read the verdict, because
    the verdict is a comparison between them.
    """
    worst = 0.0
    noise_rel = 0.0
    offenders = []
    for name, markets in targets.items():
        got = sim.mean.get(name) or {}
        for market, want in markets.items():
            have = got.get(market)
            if have is None or want is None:
                continue
            scale = max(abs(want), 0.05)
            rel = abs(have - want) / scale
            noise_rel = max(noise_rel, RECONCILE_SIGMA * (
                sim.se.get(name, {}).get(market) or 0.0) / scale)
            # Forgive whichever is larger: the relative tolerance, or the
            # sampler's own noise. Without the second term this gate is
            # accidentally strict on rare markets — a 0.05-per-game home-run
            # rate moves several percent between seeds at 6,000 trials, and
            # failing on that reports the trial count as a model defect.
            noise = RECONCILE_SIGMA * (sim.se.get(name, {}).get(market) or 0.0)
            worst = max(worst, rel)
            if abs(have - want) > max(tol * scale, noise):
                offenders.append({"player": name, "market": market,
                                  "projected": round(want, 4),
                                  "simulated": round(have, 4),
                                  "rel_error": round(rel, 4)})
    return {"ok": not offenders, "worst_rel_error": round(worst, 4),
            "noise_rel": round(noise_rel, 4),
            "tol": tol, "offenders": offenders}
