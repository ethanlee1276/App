"""A teammate out at his position: the model moves the number, measured.

Ethan, 2026-09-23: "make sure everything we pull, all the data we use is
actually being projected to the pick ... if we need to say it under the
card ... but we also need our model to adjust accordingly."

Since 2026-09-14 a card said "Pacheco out — Hunt absorbed +11% of the
carries" (engine/redistribute) and the projection did not move, because
engine/ripplefit asked the edge board's question — does it beat the
closing line — and the answer was no. The Most Likely board asks whether
it predicts what the player DOES, and nothing this model reads predicts
more: a back whose starter was just ruled out ran for 65% more than his
own form (engine/matefit.py, `python3 matefit.py`, 2022-2025, every
season).

HOW IT READS A GAME (nfl_build, after the injury report and the reset):
the depth order at each position is the per-game volume ranking the
fitter measured on (matefit.ranked: top three with three games), a
teammate is out when the report or the live board rules him out, and the
case is whether he ranks ABOVE or BELOW the player and whether he played
last week ("new" — the player's recent games do not know yet) or was
already out ("cont" — they partly do; and not at all for a player the
reset rule already re-projected from his games since the change).
"""
from __future__ import annotations

from .matefit import GROUPS, MIN_GAMES, TOP, case_for, volume

#: {(market, group, case): multiplier} — engine/matefit.shipped() on
#: 2022-2025, 2026-09-23. Per-season values in docs/NFL_MODEL.md.
EFFECT = {
    ("rush_yds", "RB", "above_new"): 1.647,      # ± .161  n 103
    ("rush_yds", "RB", "above_cont"): 1.337,     # ± .076  n 237
    ("rush_yds", "RB", "below_new"): 1.102,      # ± .040  n 372
    ("receptions", "RB", "above_new"): 1.636,    # ± .140  n 51
    ("receptions", "RB", "below_new"): 1.126,    # ± .047  n 270
    ("receptions", "TE", "above_new"): 1.452,    # ± .151  n 68
    ("receptions", "TE", "above_cont"): 1.201,   # ± .067  n 143
    ("receptions", "WR", "above_new"): 1.180,    # ± .063  n 196
    ("receptions", "WR", "above_cont"): 1.091,   # ± .034  n 428
    ("rec_yds", "WR", "above_cont"): 1.107,      # ± .045  n 432
}
#: The words for each case, on the card.
CASE_WORDS = {"above_new": "just ruled out ahead of him", "above_cont": "out ahead of him",
              "below_new": "just ruled out behind him", "below_cont": "out behind him"}


def _norm(name: str) -> str:
    from .sources.oddsapi import normalize_name
    return normalize_name(str(name or ""))


def depth_table(stats: list[dict], teams, upto_week: int) -> dict:
    """{"order": {"TEAM|POS": [[name, per-game volume, games, last week]]},
    "last": {team: the team's last week before this one}} — matefit.ranked
    over this season's rows, the order the multipliers were measured on."""
    from .sources.nflverse import _f, _s, _regular_season
    from .matefit import ranked
    games: dict = {}
    last: dict = {}
    for r in _regular_season(stats or []):
        wk = int(_f(r, "week", default=0))
        if wk <= 0 or wk >= upto_week:
            continue
        team = _s(r, "recent_team", "team")
        if teams and team not in teams:
            continue
        last[team] = max(last.get(team, 0), wk)
        pos = _s(r, "position", "position_group").upper()
        if pos in GROUPS:
            games.setdefault((team, pos, _s(r, "player_display_name", "player_name", "full_name")), {})[wk] = r
    order = {}
    for team in {t for t, _p, _n in games}:
        for pos in GROUPS:
            got = ranked(games, team, pos, upto_week)
            if got:
                order[f"{team}|{pos}"] = [[n, round(v, 2), g, lw] for n, v, g, lw in got]
    return {"order": order, "last": last}


def stamp(slate, depth: dict, injuries, reset_players=()) -> dict:
    """Put each game's depth orders and ruled-out names on it, and mark the
    props the reset rule re-projected. Returns {team: [names out]}."""
    from .injuries import RULED_OUT
    out: dict = {}
    for i in injuries or []:
        if getattr(i, "status", "") in RULED_OUT:
            out.setdefault(i.team, set()).add(_norm(i.player))
    reset = {_norm(p) for p in reset_players or ()}
    for p in slate.props:
        if _norm(p.player) in reset:
            p.reset_applied = True
    order = (depth or {}).get("order") or {}
    last = (depth or {}).get("last") or {}
    for g in slate.games:
        g.lineup = {t: {"order": {pos: order.get(f"{t}|{pos}") or [] for pos in GROUPS},
                        "out": sorted(out.get(t, ())), "last": last.get(t, 0)}
                    for t in (g.home, g.away)}
    return {t: sorted(v) for t, v in out.items()}


def effect(prop, game) -> tuple:
    """(multiplier, reason, card) for one prop from its game's lineup."""
    pos = str(getattr(prop, "position", "") or "").upper()
    lu = ((getattr(game, "lineup", None) or {}).get(getattr(prop, "team", "")) or {})
    order = (lu.get("order") or {}).get(pos) or []
    if pos not in GROUPS or not order:
        return 1.0, "", None
    out = set(lu.get("out") or [])
    names = [o[0] for o in order]
    if _norm(prop.player) not in {_norm(n) for n in names}:
        return 1.0, "", None
    me = next(n for n in names if _norm(n) == _norm(prop.player))
    playing = {n for n in names if _norm(n) not in out}
    case = case_for([tuple(o) for o in order], me, playing, int(lu.get("last") or 0))
    if not case:
        return 1.0, "", None
    who = [n for n in names if n not in playing and n != me]
    mult = EFFECT.get((prop.market, pos, case), 1.0)
    held = mult != 1.0 and case.endswith("_cont") and getattr(prop, "reset_applied", False)
    if held:
        mult = 1.0
    words = CASE_WORDS[case]
    head = f"{' and '.join(who)} {words} at {pos}"
    if mult != 1.0:
        note = (f"Measured over four seasons: a {pos} in this spot produced "
                f"{abs(round((mult - 1) * 100))}% {'more' if mult > 1 else 'less'} than his own form — applied (×{mult:.2f})")
        reason = f"Teammate out: {head} — measured (×{mult:.2f})"
    elif held:
        note = "His games since the change already carry it (the sample was reset to them), so nothing is added"
        reason = ""
    else:
        note = "Shown for you. Over four seasons this did not move this bet enough to price it"
        reason = ""
    return mult, reason, {"team": prop.team, "out": who, "case": case, "headline": head,
                          "applied": round(mult, 3), "note": note}
