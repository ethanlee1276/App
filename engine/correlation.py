"""The Correlation Engine — §9 of docs/NFL_MODEL.md.

Two jobs, both about bets relating to each other:

1. FLAG relationships between recommended plays so the reader sees them:
   a QB Over and his receiver's Over are one passing game wearing two
   jerseys; two same-team receivers share one ball; a QB Under next to his
   receiver's Over is incoherent — the lower-graded half of that pair is
   rejected, not footnoted.
2. COUNT correlated bets as combined exposure against the §10 bankroll
   caps: max 5u per game and 15u per slate (1u = 1% bankroll). Over the
   cap, ONE factor scales the whole board — which cannot change ROI,
   because net and staked move together — and any stake that falls under
   `staking.MIN_STAKE_UNITS` comes off rather than being rounded through
   it. See `_uniform_factor` for the two policies this replaced and the
   888 settled bets that decided against both.
"""

from __future__ import annotations

PASS_MARKETS = {"pass_yds"}
CATCH_MARKETS = {"rec_yds", "receptions"}
RUSH_MARKETS = {"rush_yds"}

GAME_CAP_U = 5.0
SLATE_CAP_U = 15.0


def _game_key(r: dict) -> tuple:
    return tuple(sorted((r.get("team", ""), r.get("opponent", "")))) + (r.get("game_date", ""),)


def flag_correlations(recs: list[dict]) -> dict:
    """Annotate recommended props with correlation notes; reject incoherent
    pairs. Mutates the dicts (adds ``correlations`` lists, may flip
    ``recommended`` off). Returns a small summary for the slate meta."""
    on = [r for r in recs if r.get("recommended")]
    flagged = rejected = 0

    by_game: dict = {}
    for r in on:
        by_game.setdefault(_game_key(r), []).append(r)

    for rows in by_game.values():
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if not (a.get("recommended") and b.get("recommended")):
                    continue
                same_team = a.get("team") == b.get("team")
                am, bm = a.get("market"), b.get("market")
                aside, bside = a.get("side"), b.get("side")

                if same_team:
                    qb_catch = ((am in PASS_MARKETS and bm in CATCH_MARKETS)
                                or (bm in PASS_MARKETS and am in CATCH_MARKETS))
                    if qb_catch and aside != bside:
                        # QB Under + his receiver Over (either order): the two
                        # bets describe contradictory passing games. §9 says
                        # reject the pairing — the lower grade loses.
                        loser = a if (a.get("quality", 0) <= b.get("quality", 0)) else b
                        keeper = b if loser is a else a
                        loser["recommended"] = False
                        loser["stake_units"] = 0.0
                        loser["grade"] = "Pass"
                        loser.setdefault("warnings", []).append(
                            f"Incoherent pairing with {keeper.get('player')} "
                            f"{keeper.get('side', '').title()} {keeper.get('market_label', '')} "
                            f"— the two bets need opposite passing games; the "
                            f"lower-graded one is rejected")
                        rejected += 1
                        continue
                    if qb_catch:
                        note = "same passing game — counted as one combined exposure"
                        a.setdefault("correlations", []).append(
                            f"Positively correlated with {b.get('player')} "
                            f"{b.get('side', '').title()}: {note}")
                        b.setdefault("correlations", []).append(
                            f"Positively correlated with {a.get('player')} "
                            f"{a.get('side', '').title()}: {note}")
                        flagged += 1
                    elif (am in CATCH_MARKETS and bm in CATCH_MARKETS
                          and aside == "OVER" and bside == "OVER"):
                        note = "one ball to share — mildly negative correlation"
                        a.setdefault("correlations", []).append(
                            f"{note} with {b.get('player')}")
                        b.setdefault("correlations", []).append(
                            f"{note} with {a.get('player')}")
                        flagged += 1
                elif aside == "OVER" and bside == "OVER":
                    # Overs across both teams link through pace.
                    a.setdefault("correlations", []).append(
                        f"Pace-linked with {b.get('player')} (opposite team, both Overs)")
                    b.setdefault("correlations", []).append(
                        f"Pace-linked with {a.get('player')} (opposite team, both Overs)")
                    flagged += 1

    return {"pairs_flagged": flagged, "pairs_rejected": rejected}


MLB_K_MARKET = "strikeouts"
MLB_HITTER_MARKETS = {"total_bases", "hits", "home_runs"}


def flag_mlb_correlations(recs: list[dict]) -> dict:
    """Baseball's §9 (docs/MLB_MODEL.md): the pitcher and the opposing
    hitters share one set of pitches.

    - A starter's strikeout OVER next to an opposing hitter's OVER is
      incoherent — the same pitches can't strike out the side AND get hit.
      The lower-graded half of the pair is rejected.
    - Two or more hitter OVERs from ONE offense are one bet on that offense
      wearing several jerseys — flagged as combined exposure on every card.
    Mutates the dicts; returns a summary for the slate meta."""
    on = [r for r in recs if r.get("recommended")]
    flagged = rejected = 0

    by_game: dict = {}
    for r in on:
        by_game.setdefault(_game_key(r), []).append(r)

    for rows in by_game.values():
        ks = [r for r in rows if r.get("market") == MLB_K_MARKET
              and r.get("side") == "OVER"]
        for k in ks:
            for h in rows:
                if not (k.get("recommended") and h.get("recommended")):
                    continue
                if (h.get("market") in MLB_HITTER_MARKETS
                        and h.get("side") == "OVER"
                        and h.get("team") == k.get("opponent")):
                    loser = h if (h.get("quality", 0) <= k.get("quality", 0)) else k
                    keeper = k if loser is h else h
                    loser["recommended"] = False
                    loser["stake_units"] = 0.0
                    loser["grade"] = "Pass"
                    loser.setdefault("warnings", []).append(
                        f"Incoherent pairing with {keeper.get('player')} "
                        f"{keeper.get('side', '').title()} {keeper.get('market_label', '')} "
                        f"— the same pitches can't strike out the side and get "
                        f"hit; the lower-graded bet is rejected")
                    rejected += 1
        # Offense stacks: hitters from one team, all needing big games.
        by_team: dict = {}
        for r in rows:
            if (r.get("recommended") and r.get("market") in MLB_HITTER_MARKETS
                    and r.get("side") == "OVER"):
                by_team.setdefault(r.get("team"), []).append(r)
        for team, stack in by_team.items():
            if len(stack) >= 2:
                for r in stack:
                    others = [s.get("player") for s in stack if s is not r]
                    r.setdefault("correlations", []).append(
                        f"One offense, several jerseys — stacked with "
                        f"{', '.join(others)} ({team}); counted as combined exposure")
                flagged += 1

    return {"pairs_flagged": flagged, "pairs_rejected": rejected}


def _uniform_factor(by_game: dict, live: list[dict]) -> tuple[float, str]:
    """The single scale factor that satisfies EVERY cap, and why.

    THE POINT OF DOING IT IN ONE FACTOR. Multiplying every stake on the
    slate by the same number cannot change ROI — net and staked move
    together and the ratio is untouched. Any cap policy that shrinks
    some bets more than others is choosing a different portfolio, and
    that choice needs a ranking it can defend.

    Measured 2026-08-08 on 888 settled bets, which is how we got here:

      * the old rule scaled PER GAME and then per slate, so three legs
        in one fixture were cut to a fraction while a lone bet in a
        quiet game kept full size. It also re-rounded below
        `staking.MIN_STAKE_UNITS` — Ethan spotted a +106 winner that
        returned 0.05u on a 0.047u stake, which the sizing path cannot
        emit. As staked -5.67%; at the stakes the rules asked for,
        +4.91%. Ten points, entirely from the reweighting.
      * so the caps were changed to drop the weakest bets and keep the
        rest at full size. Replayed against the same 888 bets that was
        WORSE: the 128 bets it keeps returned -11.33% and the 443 it
        drops returned +9.14%. Small (about 1.3 SE from zero) and not a
        verdict, but it is not support either — and the rule only works
        if the grade it sorts on is predictive, which is now an open
        question rather than an assumption.

    Hence uniform. It is the one policy that needs no ranking to be
    right, so it is correct whether the grade turns out to be predictive
    or inverted.

    **2026-08-12: the open question closed, and it closed the wrong way
    for any ranked policy.** `stakecheck.py` on the current era: grade A+
    returned -18.3% against grade A's -7.9%, and the largest stake
    quartile was the worst of the four (34.5% hit, -33.9%). The grade is
    not merely unproven, it is inverted — so a rule that keeps the
    highest-graded bets keeps the losers, which is exactly what the 888-bet
    replay saw. Uniform stays.

    The price ladder (engine/staking.py, same day) makes this bind less
    often rather than more: stakes no longer stack up from a Kelly that
    asked for six times the cap. When it does bind, `stake_basis` names it
    on the card, because a board of identical scaled stakes with no reason
    beside them is the thing Ethan read as random in the first place.

    The game caps and the slate cap are satisfied by taking the most
    binding of them. One crowded fixture therefore shrinks the whole
    board, which is conservative — and in practice invisible, because
    with the model asking roughly six times the slate cap it is the
    slate that binds every time.
    """
    factor, why = 1.0, ""
    for key, rows in by_game.items():
        total = sum(r.get("stake_units", 0) for r in rows
                    if r.get("recommended"))
        if total > GAME_CAP_U:
            f = GAME_CAP_U / total
            if f < factor:
                names = "/".join(sorted({k for k in key[:2] if k})) or "one game"
                factor = f
                why = (f"{names} asked {total:.1f}u against the "
                       f"{GAME_CAP_U:.0f}u game cap")
    slate_total = sum(r.get("stake_units", 0) for r in live)
    if slate_total > SLATE_CAP_U:
        f = SLATE_CAP_U / slate_total
        if f < factor:
            factor = f
            why = (f"the slate asked {slate_total:.1f}u against the "
                   f"{SLATE_CAP_U:.0f}u cap")
    return factor, why


def _reject(r: dict, why: str) -> None:
    """Take a bet off the board, the same way the incoherent-pair rule
    does — off the board, zero stake, graded Pass, and a warning saying
    so. A dropped bet that keeps its grade reads as a recommendation
    nobody sized."""
    r["recommended"] = False
    r["stake_units"] = 0.0
    r["grade"] = "Pass"
    r.setdefault("warnings", []).append(why)


def apply_exposure_caps(recs: list[dict], game_bets: list[dict]) -> list[str]:
    """§10 circuit breakers: 5u per game, 15u per slate, correlated bets
    counted together (they are — everything in one game counts as that
    game's exposure).

    ONE FACTOR, APPLIED TO EVERYTHING, then the floor enforced by
    dropping rather than rounding. See `_uniform_factor` for the two
    policies this replaced and the 888 settled bets that decided against
    both. Mutates in place; returns human-readable notes.
    """
    from .staking import MIN_STAKE_UNITS

    notes: list[str] = []

    by_game: dict = {}
    for r in recs:
        if r.get("recommended"):
            by_game.setdefault(_game_key(r), []).append(r)
    for b in game_bets or []:
        if b.get("recommended"):
            key = tuple(sorted((b.get("home", ""), b.get("away", "")))) + (b.get("date", ""),)
            by_game.setdefault(key, []).append(b)

    live = [r for r in (list(recs) + list(game_bets or []))
            if r.get("recommended") and (r.get("stake_units") or 0) > 0]
    if not live:
        return notes

    factor, why = _uniform_factor(by_game, live)
    before = sum(r["stake_units"] for r in live)
    if factor < 1.0:
        for r in live:
            r["stake_units"] = r["stake_units"] * factor

    # THE FLOOR, ENFORCED BY DROPPING. `staking.MIN_STAKE_UNITS` exists
    # because a stake below it is not a bet, it is a rounding artefact
    # with a ticket. The old rule re-rounded straight past it and put
    # 0.047u into the journal. Scaling cannot honour a floor and a cap at
    # once, so the bets that fall through it come off the board.
    #
    # This is a selection, and an honest one: it selects on the stake
    # Kelly asked for, not on the model's letter grade. That distinction
    # is the whole reason for this policy — the grade's predictiveness is
    # currently an open question and nothing here depends on the answer.
    dropped = [r for r in live if r["stake_units"] < MIN_STAKE_UNITS]
    for r in dropped:
        _reject(r, f"Exposure cap — {why}, so every stake was scaled by "
                   f"{factor:.2f} and this one fell under the "
                   f"{MIN_STAKE_UNITS}u minimum. A stake that small is a "
                   f"rounding artefact with a ticket, not a bet.")
    for r in live:
        if r.get("recommended"):
            r["stake_units"] = round(r["stake_units"], 2)
            # The scaling is the LAST word on the stake, so it is the last
            # word in the reason too. Without this the card would credit
            # Kelly for a number the slate cap actually chose — five picks
            # printing an identical 0.25u with no way to see why.
            if factor < 1.0:
                r["stake_basis"] = (
                    (r.get("stake_basis") or "sized")
                    + f", then scaled ×{factor:.2f} to fit the slate cap")

    if factor < 1.0:
        kept = sum(r["stake_units"] for r in live if r.get("recommended"))
        notes.append(f"Exposure cap: {why} — every stake scaled by "
                     f"{factor:.2f} ({before:.1f}u → {kept:.1f}u), "
                     f"{len(dropped)} bet(s) dropped under the "
                     f"{MIN_STAKE_UNITS}u minimum")
    return notes


#: Scalpy's scoring markets, for the hoops pair flags below.
HOOPS_SCORING = {"pts", "fg3m"}
HOOPS_MARKETS = {"pts", "reb", "ast", "fg3m"}


def flag_hoops_correlations(recs: list[dict]) -> dict:
    """WNBA/NBA §7: name the pair mechanisms — and price nothing.

    Baseball has a true incoherence to reject ("the same pitches can't
    strike out the side AND get hit"). Basketball does not: every hoops
    pair argument runs through pace or usage, and both cut in directions
    that depend on game script. So this flags and NEVER rejects — naming
    a mechanism is evidence, deciding it outweighs the model is pricing,
    and inventing a hoops incoherence to mirror baseball's would be
    manufacturing a rule the sport does not contain.

    Three structural pairs, each named by its mechanism:

    SAME PLAYER, two OVERs (pts + fg3m): a made three IS three points —
      one bet wearing two markets, the closest hoops gets to incoherence's
      mirror image. Flagged as near-duplicate exposure.
    SAME TEAM, two+ scoring OVERs: one offence's possessions wearing
      several jerseys — the usage side cuts AGAINST the pair (they share
      the same shots), the pace side cuts with it. Both named.
    SAME GAME, scoring OVERs on BOTH teams: one bet on a fast game.

    Mutates the dicts (``correlations`` lists); returns a slate summary.
    """
    on = [r for r in recs if r.get("recommended")]
    flagged = 0

    # Same player, several overs — a made three is three points.
    by_player: dict = {}
    for r in on:
        if r.get("side") == "OVER" and r.get("market") in HOOPS_MARKETS:
            by_player.setdefault((r.get("player"), _game_key(r)), []).append(r)
    for rows in by_player.values():
        mkts = {r.get("market") for r in rows}
        if "pts" in mkts and "fg3m" in mkts:
            for r in rows:
                if r.get("market") in ("pts", "fg3m"):
                    other = "fg3m" if r["market"] == "pts" else "pts"
                    r.setdefault("correlations", []).append(
                        "A made three IS three points — this and his "
                        f"{other} Over are one bet wearing two markets; "
                        "counted as combined exposure")
                    flagged += 1

    by_game: dict = {}
    for r in on:
        if r.get("side") == "OVER" and r.get("market") in HOOPS_SCORING:
            by_game.setdefault(_game_key(r), []).append(r)
    for rows in by_game.values():
        # One offence, several jerseys — with the usage caveat named,
        # because in hoops the same-team pair is NOT simply positive.
        by_team: dict = {}
        for r in rows:
            by_team.setdefault(r.get("team"), []).append(r)
        for team, stack in by_team.items():
            # DISTINCT PLAYERS. One player's pts + fg3m is the near-
            # duplicate pair above, not a stack — the first cut counted
            # rows and printed "stacked with A Wilson" on A Wilson's own
            # card, a flag naming the player as her own teammate.
            players = {s.get("player") for s in stack}
            if len(players) >= 2:
                for r in stack:
                    others = sorted(players - {r.get("player")})
                    r.setdefault("correlations", []).append(
                        f"One offence's possessions, several jerseys — "
                        f"stacked with {', '.join(others)} ({team}). Pace "
                        f"helps both; the same shots cannot feed both")
                    flagged += 1
        # Both sides of one game over — one bet on a fast game. Two
        # teams, not two rows: a single player double-counted above must
        # not conjure an opponent.
        if len({t for t in by_team if t}) >= 2:
            for r in rows:
                r.setdefault("correlations", []).append(
                    "Scoring Overs on both sides of one game — pace is "
                    "the shared engine; counted as combined exposure")
                flagged += 1

    return {"flagged": flagged, "rejected": 0}
