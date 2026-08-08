"""The Correlation Engine — §9 of docs/NFL_MODEL.md.

Two jobs, both about bets relating to each other:

1. FLAG relationships between recommended plays so the reader sees them:
   a QB Over and his receiver's Over are one passing game wearing two
   jerseys; two same-team receivers share one ball; a QB Under next to his
   receiver's Over is incoherent — the lower-graded half of that pair is
   rejected, not footnoted.
2. COUNT correlated bets as combined exposure against the §10 bankroll
   caps: max 5u per game and 15u per slate (1u = 1% bankroll). Over the
   cap means FEWER BETS, not smaller ones: the weakest are dropped until
   the rest fit at the size Kelly asked for. See `_trim` for what this
   replaced and why it had to go.
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


_GRADE_RANK = {"A+": 3, "A": 2, "B+": 1}


def _strength(r: dict) -> tuple:
    """Sort key, weakest first. Highest is the last thing to be dropped."""
    return (float(r.get("quality") or 0.0),
            _GRADE_RANK.get(r.get("grade") or "", 0),
            float(r.get("edge") or 0.0))


def _trim(rows: list[dict], cap: float) -> tuple[float, list[dict]]:
    """Drop the weakest bets until the rest fit at FULL size.

    Returns (exposure asked for, bets dropped).

    THIS REPLACED PROPORTIONAL SCALING, and the difference is the whole
    point. Scaling multiplied every stake by cap/total and re-rounded,
    which had three problems:

      * it walked straight through `staking.MIN_STAKE_UNITS`. Ethan found
        it on the board: a +106 winner that returned 0.05u had been
        staked 0.047u, a number the sizing path cannot produce.
      * it punished bets for their neighbours. A game with four legs got
        each leg cut to a quarter; the same bet alone in a quiet game
        kept full size. Nothing about the bet changed.
      * it is the wrong answer to being over budget. Fifteen bets at a
        third of their proper size is not a smaller version of the right
        portfolio, it is a worse one — the edge per bet is unchanged and
        the variance per unit staked is higher.

    Ethan chose this, 2026-08-08: bet the best spots properly and skip
    the rest, rather than betting every spot badly.

    The strongest bet is never dropped. If it alone busts the cap it is
    clamped to the cap instead — unreachable with today's constants (a
    single stake maxes at the A+ cap of 2u against a 5u game cap) and
    written anyway, because the constants are the kind of thing that
    moves.
    """
    from .staking import MIN_STAKE_UNITS

    live = [r for r in rows
            if r.get("recommended") and (r.get("stake_units") or 0) > 0]
    asked = sum(r["stake_units"] for r in live)
    if asked <= cap or not live:
        return asked, []

    dropped: list[dict] = []
    order = sorted(live, key=_strength)          # weakest first
    running = asked
    for r in order[:-1]:                          # never the strongest
        if running <= cap:
            break
        running -= r["stake_units"]
        dropped.append(r)
    keeper = order[-1]
    if running > cap:
        # Only the strongest is left and it still does not fit.
        if cap < MIN_STAKE_UNITS:
            dropped.append(keeper)
        else:
            keeper["stake_units"] = round(cap, 2)
    return asked, dropped


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

    Over budget means FEWER BETS, not smaller ones. See `_trim`. Mutates
    in place; returns human-readable notes.
    """
    notes: list[str] = []

    by_game: dict = {}
    for r in recs:
        if r.get("recommended"):
            by_game.setdefault(_game_key(r), []).append(r)
    for b in game_bets or []:
        if b.get("recommended"):
            key = tuple(sorted((b.get("home", ""), b.get("away", "")))) + (b.get("date", ""),)
            by_game.setdefault(key, []).append(b)

    for key, rows in by_game.items():
        names = "/".join(sorted({k for k in key[:2] if k})) or "this game"
        asked, dropped = _trim(rows, GAME_CAP_U)
        for r in dropped:
            _reject(r, f"Game cap — {names} wanted {asked:.1f}u across its "
                       f"bets against a {GAME_CAP_U:.0f}u limit, and this was "
                       f"the weakest of them. The ones that stayed are at "
                       f"full size rather than all of them at a fraction.")
        if dropped:
            kept = sum(r.get("stake_units", 0) for r in rows
                       if r.get("recommended"))
            notes.append(f"Game cap: {names} asked {asked:.1f}u against "
                         f"{GAME_CAP_U:.0f}u — {len(dropped)} bet(s) dropped, "
                         f"{kept:.1f}u kept at full size")

    # The slate cap runs on what SURVIVED the game caps, so a bet cannot
    # be charged twice for the same crowding.
    everything = ([r for r in recs if r.get("recommended")]
                  + [b for b in (game_bets or []) if b.get("recommended")])
    asked, dropped = _trim(everything, SLATE_CAP_U)
    for r in dropped:
        _reject(r, f"Slate cap — the night's recommended bets totalled "
                   f"{asked:.1f}u against a {SLATE_CAP_U:.0f}u limit, and "
                   f"this was the weakest of them. Bankroll rules cut the "
                   f"number of bets, not the size of the good ones.")
    if dropped:
        kept = sum(r.get("stake_units", 0) for r in everything
                   if r.get("recommended"))
        notes.append(f"Slate cap: asked {asked:.1f}u against "
                     f"{SLATE_CAP_U:.0f}u — {len(dropped)} bet(s) dropped, "
                     f"{kept:.1f}u kept at full size")
    return notes
