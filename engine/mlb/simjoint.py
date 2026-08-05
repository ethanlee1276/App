"""Tonight's actual joint, for tonight's actual legs — task #60.

WHAT THIS REPLACES, AND WHY IT IS DIFFERENT IN KIND

The Parlay Zone prices a two-leg ticket through a Gaussian copula that
needs one number per pair: the latent correlation. Until now that number
came from `engine/parlays.py` MEASURED["lineup_stack"] — +0.186, fitted on
27,613 real games — which is a good estimate of how two bats in one lineup
move together ON AVERAGE.

Average is the problem. The leadoff hitter and the number-two hitter share
far more than the leadoff hitter and the number eight: they bat back to
back, so one reaching is literally what gives the other his extra turn. A
single league-wide rho prices both pairs identically, and the ticket a
bettor is actually being offered is one specific pair.

`engine/mlb/gamesim.py` deals both legs out of the same simulated innings.
It does not estimate the dependence — it observes it, on the two hitters
who are really batting tonight, at the lines really on the board. That is
the only new information the sim was ever built to produce, and this is
the module that finally hands it to the thing that needed it.

THE GATE IS THE WHOLE PRECONDITION

Nothing here may be used from a sim whose marginals disagree with the
pricing engine. A sim that cannot reproduce the projections it was
inverted from has no standing to describe their joint, and shipping one
would put two numbers for one question in front of a bettor. So every
lineup is reconciled first and a lineup that fails contributes NOTHING —
its pairs fall back to the measured prior, silently and by design.

That gate is the reason this task waited: it failed on a dozen live
lineups for weeks. It now passes on all thirty.

CONSERVATISM IS INHERITED, NOT RE-ARGUED

`parlays.py` is explicit that understating correlation is the direction to
be wrong in: it understates the joint, which raises the required price,
which makes the screen pickier. A naive reading says to clamp the sim's
number down for safety — but the sim was ALREADY tuned that way.
`gamesim.ENV_SD` is 0.25 where 0.30 fits the measured correlation more
closely, chosen precisely because 0.25 misses low and 0.30 misses high.
The understatement is baked into the sampler, so clamping again here would
be paying the same toll twice.
"""

from __future__ import annotations

from . import gamesim as G
from .models import HITS, HOME_RUNS, TOTAL_BASES

#: The markets the sim actually deals. Everything else — strikeouts, outs,
#: any game line — keeps the prior, because the sim has no opinion about it.
SIM_MARKETS = (HITS, TOTAL_BASES, HOME_RUNS)

#: A lineup below this many fully-projected hitters is not evidence. Same
#: bar the reconcile harness uses, and for the same reason: the turnover
#: dynamics the joint comes out of need most of a batting order.
MIN_HITTERS = 6

#: Trials for the published joint. Higher than the fit's per-round count
#: because this number is read by a bettor rather than used to locate a
#: fixed point.
TRIALS = 20000

#: How far the solved latent correlation may travel from the measured
#: prior. Not a fudge — a blast radius. The prior is 27,613 games of
#: evidence and the sim is one night's model; if they disagree by more than
#: this the disagreement is a finding to chase, not a number to bet, so the
#: pair keeps the prior and says so.
MAX_DRIFT = 0.35


def _key(name: str, market: str, line: float) -> tuple:
    return (str(name), str(market), round(float(line), 1))


def pair_key(a: tuple, b: tuple) -> tuple:
    """Order-independent, so a lookup cannot depend on leg order."""
    ka, kb = _key(*a), _key(*b)
    return (ka, kb) if ka <= kb else (kb, ka)


def solve_rho(p1: float, p2: float, joint: float) -> float | None:
    """The latent correlation that reproduces an OBSERVED joint.

    The sim reports P(both legs win) directly. The Parlay Zone speaks
    Gaussian-copula latent correlation. `joint_two` is continuous and
    monotone in rho over (-1, 1), so the translation is a bisection rather
    than an approximation — which matters, because the alternative is
    quoting the sim's phi as though it were a rho, and they are not the
    same number at these marginals.
    """
    from ..parlays import joint_two
    if not (0.0 < p1 < 1.0 and 0.0 < p2 < 1.0):
        return None
    lo, hi = -0.95, 0.95
    f_lo, f_hi = joint_two(p1, p2, lo), joint_two(p1, p2, hi)
    if not (f_lo <= joint <= f_hi):
        # Outside what any correlation can produce at these marginals —
        # sampler noise on a rare pair, most often. No answer beats a
        # wrong one.
        return None
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if joint_two(p1, p2, mid) < joint:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2.0, 4)


def _legs_by_team(legs: list[dict]) -> dict:
    """(team, game key) -> the legs the sim can actually deal."""
    out: dict = {}
    for leg in legs:
        market = str(leg.get("market") or "")
        if market not in SIM_MARKETS:
            continue
        if str(leg.get("side") or "").strip().upper()[:1] != "O":
            # The sim tallies "cleared the line". An UNDER is the
            # complement of a leg it counted, and the joint of two
            # complements is not the complement of the joint — so rather
            # than derive it wrongly, unders keep the prior.
            continue
        team = leg.get("team")
        line = leg.get("line")
        if not team or line is None:
            continue
        out.setdefault(team, []).append(leg)
    return {k: v for k, v in out.items() if len(v) >= 2}


def build(slate, legs: list[dict], trials: int = TRIALS) -> dict:
    """Simulate only the lineups that two candidate legs actually share.

    Returns ``{"rho": {pair_key: rho}, "lineups": {team: verdict}}``.

    Cost is the reason for the shape. Simulating all thirty lineups on
    every build would be minutes of work for joints nobody reads; a pair of
    legs on the same team is rare, so the work is proportional to what the
    Parlay Zone will actually ask about.
    """
    from .projection import build_mlb_projection, reconcile_triple

    want = _legs_by_team(legs)
    out: dict = {"rho": {}, "lineups": {}}
    if not want:
        return out

    by_game = {}
    for g in slate.games:
        gn = int(getattr(g, "game_number", 1) or 1)
        by_game[(g.home, gn)] = g
        by_game[(g.away, gn)] = g

    for team, team_legs in want.items():
        # Doubleheaders: both halves are on the board under one team, and
        # pricing a joint across two different games would be nonsense.
        gn = int(team_legs[0].get("game_number") or 1)
        game = by_game.get((team, gn))
        if game is None:
            out["lineups"][team] = "no game"
            continue

        # Every hitter in the order, not just the ones with legs: the
        # turnover that creates the dependence runs through the whole
        # lineup, and simulating two bats alone would measure a different
        # game from the one being bet.
        means: dict = {}
        spots: dict = {}
        for p in slate.props:
            if p.team != team or p.market not in SIM_MARKETS or not p.lineup_spot:
                continue
            if int(getattr(p, "game_number", 1) or 1) != gn:
                continue
            try:
                proj = build_mlb_projection(p, game)
            except Exception:                              # noqa: BLE001
                continue
            means.setdefault(p.player, {})[p.market] = proj.mean
            spots[p.player] = p.lineup_spot

        rates, targets = [], {}
        for name, mk in means.items():
            if not all(m in mk for m in SIM_MARKETS):
                continue
            hr, tb, note = reconcile_triple(mk[HITS], mk[TOTAL_BASES],
                                            mk[HOME_RUNS])
            if note:
                mk[HOME_RUNS], mk[TOTAL_BASES] = hr, tb
            spot = int(spots.get(name) or 0)
            r = G.rates_from_means(mk[HITS], mk[TOTAL_BASES], mk[HOME_RUNS],
                                   G.expected_pa(spot))
            r.name, r.spot = name, spot
            if not r.consistent:
                continue
            rates.append(r)
            targets[name] = dict(mk)

        if len(targets) < MIN_HITTERS:
            out["lineups"][team] = f"only {len(targets)} projected hitters"
            continue

        rates = G.pad_to_nine(sorted(rates, key=lambda r: r.spot or 9))
        fitted = G.calibrate(rates, targets)

        sim_legs = [(l["player"], l["market"], float(l["line"]))
                    for l in team_legs if l["player"] in targets]
        if len(sim_legs) < 2:
            out["lineups"][team] = "legs are not on projected hitters"
            continue

        sim = G.simulate_lineup(fitted, sim_legs, trials=trials)

        # THE GATE. A sim that cannot reproduce the projections it was
        # inverted from has no standing to describe their joint.
        rec = G.reconcile(sim, targets)
        if not rec["ok"]:
            out["lineups"][team] = (
                f"gate failed (worst {rec['worst_rel_error']:.3f}) — pairs "
                f"keep the measured prior")
            continue

        found = 0
        for i in range(len(sim_legs)):
            for j in range(i + 1, len(sim_legs)):
                a, b = sim_legs[i], sim_legs[j]
                p1, p2 = sim.p_over(*a), sim.p_over(*b)
                both = sim.p_both(a, b)
                if p1 is None or p2 is None or both is None:
                    continue
                rho = solve_rho(p1, p2, both)
                if rho is None:
                    continue
                out["rho"][pair_key(a, b)] = rho
                found += 1
        out["lineups"][team] = f"{found} pair(s) simulated"
    return out


def rho_for(joints: dict | None, a: dict, b: dict,
            prior: float) -> tuple[float, str] | None:
    """The simulated correlation for one pair, or None to keep the prior.

    ``prior`` is what the pair would otherwise get. A solved value further
    than MAX_DRIFT from it is refused: the prior is 27,613 games and this
    is one night's model, so a large disagreement is a finding to chase
    rather than a number to bet.
    """
    if not joints or not joints.get("rho"):
        return None
    try:
        key = pair_key(
            (a.get("player"), a.get("market"), float(a.get("line"))),
            (b.get("player"), b.get("market"), float(b.get("line"))))
    except (TypeError, ValueError):
        return None
    rho = joints["rho"].get(key)
    if rho is None:
        return None
    if abs(rho - prior) > MAX_DRIFT:
        return None
    return rho, (f"tonight's own lineup, simulated {TRIALS:,} times — both "
                 f"legs dealt out of the same innings rather than assumed to "
                 f"move like the league average ({prior:+.2f})")
