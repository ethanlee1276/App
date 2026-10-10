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
the depth order at each position is the per-game ranking the fitter
measured on — SNAP SHARE over every game he took a snap in when the build
has snap counts (EFFECT_SNAPS), targets over his box-score rows when it
does not (EFFECT); top three, ranked from week 2 on the games so far
(matefit.early_min_games; 2026-09-27, Sadiq behind Mason Taylor), a
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
#: THE SAME, WITH THE DEPTH ORDER RANKED ON SNAP SHARE — what the board
#: uses whenever the build has snap counts (engine/matefit.volume). Filled
#: from `python3 matefit.py --snaps` below.
EFFECT_SNAPS = {
    ("rec_yds", "TE", "above_new"): 1.747,       # ± .248  n 37
    ("rec_yds", "WR", "above_cont"): 1.105,      # ± .048  n 355
    ("rec_yds", "WR", "above_new"): 1.222,       # ± .087  n 185
    ("receptions", "RB", "above_new"): 1.657,    # ± .163  n 44
    ("receptions", "RB", "below_new"): 1.157,
    ("receptions", "TE", "above_cont"): 1.231,   # ± .085  n 93
    ("receptions", "TE", "above_new"): 1.568,    # ± .205  n 41
    ("receptions", "WR", "above_cont"): 1.094,   # ± .036  n 345
    ("receptions", "WR", "above_new"): 1.193,    # ± .068  n 178
    ("rush_yds", "RB", "above_cont"): 1.372,     # ± .082  n 221
    ("rush_yds", "RB", "above_new"): 1.662,      # ± .162  n 95
    ("rush_yds", "RB", "below_cont"): 1.096,     # ± .033  n 598
    ("rush_yds", "RB", "below_new"): 1.142,      # ± .046  n 325
}
#: The words for each case, on the card.
CASE_WORDS = {"above_new": "just ruled out ahead of him", "above_cont": "out ahead of him",
              "below_new": "just ruled out behind him", "below_cont": "out behind him"}


def _norm(name: str) -> str:
    from .sources.oddsapi import normalize_name
    return normalize_name(str(name or ""))


def depth_table(stats: list[dict], teams, upto_week: int, snaps: list[dict] | None = None) -> dict:
    """{"order": {"TEAM|POS": [[name, per-game volume, games, last week]]},
    "last": {team: the team's last week before this one}, "basis": "snaps" |
    "targets"} — matefit.ranked over this season's games, the order the
    multipliers were measured on.

    ``snaps`` (the season's snap-count rows) ranks on snap share and counts
    every game a player took a snap in; without it, on targets over the
    box-score rows, as first measured."""
    from .sources.nflverse import _f, _s, _regular_season
    from .matefit import ranked, early_min_games, games_from_snaps
    games: dict = {}
    last: dict = {}
    basis = "targets"
    if snaps:
        got, tw = games_from_snaps([r for r in (stats or []) if 0 < int(_f(r, "week", default=0)) < upto_week],
                                   [r for r in snaps if 0 < int(_f(r, "week", default=0)) < upto_week])
        for (team, pos, name), g in got.items():
            if not teams or team in teams:
                games[(team, pos, name)] = g
        for team, weeks in tw.items():
            if weeks and (not teams or team in teams):
                last[team] = max(weeks)
        basis = "snaps" if games else "targets"
    if not games:
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
            # From week 2, on the games played so far (early_min_games):
            # until 2026-09-27 the order needed three games, so the step
            # never ran in weeks 1-3 (Sadiq, Mason Taylor out, week 3).
            got = ranked(games, team, pos, upto_week, early_min_games(upto_week))
            if got:
                order[f"{team}|{pos}"] = [[n, round(v, 2), g, lw] for n, v, g, lw in got]
    return {"order": order, "last": last, "basis": basis}


def stamp(slate, depth: dict, injuries, reset_players=()) -> dict:
    """Put each game's depth orders and ruled-out names on it, and mark the
    props the reset rule re-projected. Returns {team: [names out]}."""
    from .injuries import RULED_OUT
    out: dict = {}
    maybe: dict = {}
    for i in injuries or []:
        if getattr(i, "status", "") in RULED_OUT:
            out.setdefault(i.team, set()).add(_norm(i.player))
        elif getattr(i, "status", "") in MAYBE:
            maybe.setdefault(i.team, set()).add(_norm(i.player))
    reset = {_norm(p) for p in reset_players or ()}
    for p in slate.props:
        if _norm(p.player) in reset:
            p.reset_applied = True
    order = (depth or {}).get("order") or {}
    last = (depth or {}).get("last") or {}
    basis = (depth or {}).get("basis") or "targets"
    for g in slate.games:
        g.lineup = {t: {"order": {pos: order.get(f"{t}|{pos}") or [] for pos in GROUPS},
                        "out": sorted(out.get(t, ())), "maybe": sorted(maybe.get(t, ())),
                        "last": last.get(t, 0), "basis": basis}
                    for t in (g.home, g.away)}
    return {t: sorted(v) for t, v in out.items()}


#: A teammate who may not play: the multiplier is NOT applied (he may well
#: play), but the card says what it would be if he sits — and the moment
#: the report rules him out, `stamp` moves him to `out` and it applies.
MAYBE = {"QUESTIONABLE", "GTD"}


def table_for(lu: dict) -> dict:
    """The multipliers this lineup's depth order was measured with: college's
    own (engine/cfb/lineup, a catch-ranked order on college games) for a
    college game, snap-ranked or target-ranked for the NFL's."""
    basis = (lu or {}).get("basis")
    if basis == "cfb":
        from .cfb.lineup import mate_table
        return mate_table()
    return EFFECT_SNAPS if basis == "snaps" else EFFECT


def _measured_on(lu: dict) -> str:
    return "on college games" if (lu or {}).get("basis") == "cfb" else "over four seasons"


def if_sits(prop, lu: dict, order: list, me: str, playing: set, mult: float):
    """{"who", "mult", "case"} — what the measured effect would be if every
    questionable teammate at his position sat — or None when none of them
    would change it. Ethan, 2026-09-25: "if a WR2 or WR1 or sum is out, then
    other players will see higher usage"; a game-day question is usually a
    questionable one, and until today nothing was said until he was out.
    ``mult`` is the multiplier applied now; the one returned replaces it."""
    maybe = {n for n in playing if n != me and _norm(n) in set(lu.get("maybe") or [])}
    if not maybe:
        return None
    case = case_for([tuple(o) for o in order], me, playing - maybe, int(lu.get("last") or 0))
    pos = str(getattr(prop, "position", "") or "").upper()
    m = table_for(lu).get((prop.market, pos, case), 1.0) if case else 1.0
    if abs(m - mult) < 1e-9:
        return None
    return {"who": sorted(maybe), "mult": round(m, 3), "case": case}


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
        maybe = if_sits(prop, lu, order, me, playing, 1.0)
        if not maybe:
            return 1.0, "", None
        return 1.0, "", {"team": prop.team, "out": [], "case": None, "applied": 1.0,
                         "headline": f"{' and '.join(maybe['who'])} questionable at {pos}",
                         "note": _if_sits_note(maybe, 1.0, prop.market, lu), "if_sits": maybe}
    who = [n for n in names if n not in playing and n != me]
    mult = table_for(lu).get((prop.market, pos, case), 1.0)
    held = mult != 1.0 and case.endswith("_cont") and getattr(prop, "reset_applied", False)
    if held:
        mult = 1.0
    words = CASE_WORDS[case]
    head = f"{' and '.join(who)} {words} at {pos}"
    if mult != 1.0:
        note = (f"Measured {_measured_on(lu)}: a {pos} in this spot produced "
                f"{abs(round((mult - 1) * 100))}% {'more' if mult > 1 else 'less'} than his own form — applied (×{mult:.2f})")
        reason = f"Teammate out: {head} — measured (×{mult:.2f})"
    elif held:
        note = "His games since the change already carry it (the sample was reset to them), so nothing is added"
        reason = ""
    else:
        note = (f"Shown for you. {_measured_on(lu).capitalize()} this did not move this bet enough to price it"
                if lu.get("basis") != "cfb" or _college_measured() else
                "Shown for you. College has not been measured for this yet, so nothing is applied")
        reason = ""
    card = {"team": prop.team, "out": who, "case": case, "headline": head,
            "applied": round(mult, 3), "note": note}
    maybe = if_sits(prop, lu, order, me, playing, mult)
    if maybe:
        card["if_sits"] = maybe
        card["note"] = f"{note}. {_if_sits_note(maybe, mult, prop.market, lu)}"
    return mult, reason, card


#: The measured markets, in words.
_WORDS = {"receptions": "catches", "rec_yds": "receiving yards", "rush_yds": "rushing yards",
          "rush_att": "carries", "anytime_td": "touchdowns"}


def _if_sits_note(maybe: dict, mult: float, market: str, lu: dict | None = None) -> str:
    """The card's sentence for a questionable teammate."""
    move = maybe["mult"] / mult - 1
    who, many = " and ".join(maybe["who"]), len(maybe["who"]) > 1
    return (f"{who} {'are' if many else 'is'} questionable. If {'they sit' if many else 'he sits'}, "
            f"our projection moves {move * 100:+.0f}% on {_WORDS.get(market, market)} (measured "
            f"{_measured_on(lu)}) — not in the number yet; it goes in on its own the moment "
            f"{'they are' if many else 'he is'} ruled out")


def _college_measured() -> bool:
    from .cfb.lineup import measured
    return measured()
