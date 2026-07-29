"""The Correlation Engine — §9 of docs/NFL_MODEL.md.

Two jobs, both about bets relating to each other:

1. FLAG relationships between recommended plays so the reader sees them:
   a QB Over and his receiver's Over are one passing game wearing two
   jerseys; two same-team receivers share one ball; a QB Under next to his
   receiver's Over is incoherent — the lower-graded half of that pair is
   rejected, not footnoted.
2. COUNT correlated bets as combined exposure against the §10 bankroll
   caps: max 5u per game and 15u per slate (1u = 1% bankroll). When a
   game's recommended stakes exceed the cap, every stake in that game is
   scaled down proportionally — the alternative is quietly holding double
   the exposure the caps promise.
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


def apply_exposure_caps(recs: list[dict], game_bets: list[dict]) -> list[str]:
    """§10 circuit breakers: 5u per game, 15u per slate, correlated bets
    counted together (they are — everything in one game counts as that
    game's exposure). Scales stakes in place; returns human-readable notes."""
    notes: list[str] = []

    def _scale(rows: list[dict], factor: float) -> None:
        for r in rows:
            if r.get("recommended") and r.get("stake_units", 0) > 0:
                r["stake_units"] = round(r["stake_units"] * factor, 2)

    by_game: dict = {}
    for r in recs:
        if r.get("recommended"):
            by_game.setdefault(_game_key(r), []).append(r)
    for b in game_bets or []:
        if b.get("recommended"):
            key = tuple(sorted((b.get("home", ""), b.get("away", "")))) + (b.get("date", ""),)
            by_game.setdefault(key, []).append(b)

    for key, rows in by_game.items():
        total = sum(r.get("stake_units", 0) for r in rows)
        if total > GAME_CAP_U:
            _scale(rows, GAME_CAP_U / total)
            names = "/".join(sorted({k for k in key[:2] if k}))
            notes.append(f"Game cap: {names} stakes scaled {total:.1f}u → "
                         f"{GAME_CAP_U:.0f}u (correlated bets count together)")

    everything = ([r for r in recs if r.get("recommended")]
                  + [b for b in (game_bets or []) if b.get("recommended")])
    slate_total = sum(r.get("stake_units", 0) for r in everything)
    if slate_total > SLATE_CAP_U:
        _scale(everything, SLATE_CAP_U / slate_total)
        notes.append(f"Slate cap: total exposure scaled {slate_total:.1f}u → "
                     f"{SLATE_CAP_U:.0f}u")
    return notes
