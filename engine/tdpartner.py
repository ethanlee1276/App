"""A BACK'S TOUCHDOWN CHANCE WITH THE BACKFIELD PARTNER BACK (step AIE, 27 November 2026).

Ethan's own Bears at Lions research, which won, split D'Andre Swift's touchdowns by whether Kyle Monangai played:
"Swift scored in only 2 of the 5 games both were active"; "7 of his 10 rushing TDs came in the 4 games without
Monangai". Our touchdown chance for a back reads the back's recent games whole: the share of the team's work
(pipeline._opportunity_shares), the red-zone touches (nflusage.red_zone_usage) and the touchdown history. When the
partner missed some of those games and plays tonight, all three count games the back had the backfield alone.

MEASURED BEFORE ANYTHING MOVED, the way the other teammate steps are (engine/matefit). On nflverse play-by-play,
2017-2026, a back whose partner (the team's other back with the most carries, 20 or more) missed one or more of
the back's last six games and played the next one got 0.86 of the red-zone touches the back's recent share said
(1,420 games), against 1.01 for a back whose partner played throughout; counted over only the games both played,
0.99. Replayed through this module's chain (touchdowns.td_probability, with the live board's own inputs), each
season held out and calibrated on the others, 2022-2025, 695 such games: the backs scored in 26.6% of them, our
number said 30.4%, and read over the games both played 28.1%; log-loss 0.5192 -> 0.5140, better in three of the
four seasons (the bar matefit's deflation clears: better overall, at most one season the wrong way). The more of
the window the partner missed, the higher the number had run: 3.1 points with one game missed, 3.7 with two, 5.3
with three or more; read over the games both played, 0.8 to 1.7.

THE RULE. An NFL back whose top teammate back (the lineup's own ranking, engine/teammates) is on tonight's slate,
not ruled out, and missed one or more of the back's last RZ_WEEKS games: the share, the red-zone touches and this
season's touchdown history are read over the back's most recent RZ_WEEKS games with the partner there (at least
MIN_SHARED of them; fewer and nothing changes). Last season's games stay as they are. College is not measured.

THE OTHER WAY ROUND, ONE CASE OF IT (step AIG, 27 November 2026). A back whose partner is ruled out ran LOW:
in 656 such games those backs scored 34.6% and our number said 30.4%. Reading the back's games without the partner
did not hold (better in one season of four), and the teammate step's measured carries lift on the touchdown inputs
(its share and red-zone carries, teammates.EFFECT_SNAPS rush_att RB) holds in one case only: the back ahead is
out tonight and was out for the team's last game too ("above_cont"), and played at least one of this back's last
RZ_WEEKS games, so the back's window still counts games behind him. There, 173 games over 2022-2025: scored 30.6%,
our number 21.3%, lifted 25.3%; log-loss 0.5622 -> 0.5378, better in all four seasons. Where the back ahead has
been out the whole window (13 games) the window already reads the new role and the lift overshot, and where the
back ahead was just ruled out ("above_new", 168 games) the lift overshot too (27.0% said against 24.4%) and held
in two seasons of four; neither is lifted. A back behind ruled out moved nothing (`stepped_up`).
"""
from __future__ import annotations

from dataclasses import replace

#: The fewest of the back's games with the partner there that the chance is read over.
MIN_SHARED = 2


def _weeks(entry) -> list:
    try:
        return sorted(int(w) for w in (entry[4] if len(entry) > 4 else []) or [])
    except (TypeError, ValueError):
        return []


def find(prop, game, playing=None) -> dict | None:
    """{"partner", "shared" (the back's games this season with the partner there, the newest RZ_WEEKS, oldest
    first), "missed" (how many of the back's last RZ_WEEKS games the partner missed), "window"} for an NFL back
    whose top teammate back plays tonight (on ``playing``, the team's names on tonight's slate, when given, and not
    ruled out) and missed one or more of the back's last RZ_WEEKS games. None otherwise."""
    from .nflusage import RZ_WEEKS
    from .teammates import _norm
    if str(getattr(prop, "position", "") or "").upper() != "RB":
        return None
    lu = ((getattr(game, "lineup", None) or {}).get(getattr(prop, "team", "")) or {})
    if not lu or lu.get("basis") == "cfb":
        return None
    seen = (lu.get("seen") or {}).get("RB") or []
    me = _norm(getattr(prop, "player", "") or "")
    mine = next((s for s in seen if s and _norm(s[0]) == me), None)
    partner = next((s for s in seen if s and _norm(s[0]) != me), None)
    if mine is None or partner is None:
        return None
    out = {_norm(n) for n in lu.get("out") or []}
    if _norm(partner[0]) in out:
        return None
    if playing is not None and _norm(partner[0]) not in {_norm(n) for n in playing}:
        return None                     # not on tonight's slate: cut, traded or on a reserve list
    pw = set(_weeks(partner))
    my_weeks = _weeks(mine)
    window = my_weeks[-RZ_WEEKS:]
    missed = [w for w in window if w not in pw]
    if not missed:
        return None
    shared = [w for w in my_weeks if w in pw][-RZ_WEEKS:]
    if len(shared) < MIN_SHARED:
        return None
    return {"partner": partner[0], "shared": shared, "missed": len(missed), "window": len(window)}


def chance_prop(prop, shared):
    """The touchdown prop with this season's games cut to ``shared``; last season's stay."""
    keep = {int(w) for w in shared}
    logs = [g for g in getattr(prop, "logs", None) or []
            if getattr(g, "prior", False) or _int(getattr(g, "week", None)) in keep]
    return replace(prop, logs=logs)


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def volume(props, shared=None) -> float:
    """A player's volume the way pipeline._opportunity_shares reads it (his rushing yards, receiving yards or
    catches a game, the largest), with this season's games cut to ``shared`` when given; last season's stay."""
    keep = {int(w) for w in shared} if shared is not None else None
    best = 0.0
    for p in props:
        vals = [g.value for g in getattr(p, "logs", None) or []
                if keep is None or getattr(g, "prior", False) or _int(getattr(g, "week", None)) in keep]
        if vals:
            best = max(best, sum(vals) / len(vals))
    return best


def stepped_up(prop, game) -> dict | None:
    """{"kind": "out", "partner" (the back or backs ahead, out), "lift", "with" (of this back's last RZ_WEEKS games,
    how many the back ahead played), "window"} for an NFL back whose teammate ahead at the position is out tonight
    and missed the team's last game too (matefit.case_for "above_cont"), and played at least one of this back's
    last RZ_WEEKS games. ``lift``: the carries lift the teammate step measured for that spot. None otherwise."""
    from .matefit import case_for
    from .nflusage import RZ_WEEKS
    from .teammates import _norm, table_for
    if str(getattr(prop, "position", "") or "").upper() != "RB":
        return None
    lu = ((getattr(game, "lineup", None) or {}).get(getattr(prop, "team", "")) or {})
    if not lu or lu.get("basis") == "cfb":
        return None
    order = [tuple(o) for o in ((lu.get("order") or {}).get("RB") or []) if o]
    names = [o[0] for o in order]
    me = next((n for n in names if _norm(n) == _norm(getattr(prop, "player", "") or "")), None)
    if me is None:
        return None
    out = {_norm(n) for n in lu.get("out") or []}
    playing = {n for n in names if _norm(n) not in out}
    if case_for(order, me, playing, int(lu.get("last") or 0)) != "above_cont":
        return None
    ahead = [n for n in names[:names.index(me)] if n not in playing]
    seen = {_norm(s[0]): set(_weeks(s)) for s in (lu.get("seen") or {}).get("RB") or [] if s}
    window = sorted(seen.get(_norm(me)) or [])[-RZ_WEEKS:]
    with_them = [w for w in window if any(w in seen.get(_norm(a), set()) for a in ahead)]
    if not window or not with_them:
        return None                    # out the whole window: the window already reads the new role
    lift = float(table_for(lu).get(("rush_att", "RB", "above_cont"), 1.0))
    if lift <= 1.0:
        return None
    return {"kind": "out", "partner": " and ".join(ahead), "lift": lift, "with": len(with_them),
            "window": len(window)}


def up_words(info: dict, player: str) -> str:
    """The reason line: "Backfield partner out: Lead Back has been out since before the team's last game and is
    out tonight; Second Back's last 6 games include 3 with Lead Back, and a back moving up in this spot has carried
    about 33% more, so the chance counts those carries that way (measured 2022-2025)"."""
    return (f"Backfield partner out: {info['partner']} has been out since before the team's last game and is out "
            f"tonight; {player}'s last {info['window']} games include {info['with']} with {info['partner']}, and a "
            f"back moving up in this spot has carried about {round((float(info['lift']) - 1.0) * 100)}% more, so "
            f"the chance counts those carries that way (measured 2022-2025)")


def words(info: dict, player: str) -> str:
    """The reason line: "Backfield partner back: Kyle Monangai missed 3 of D'Andre Swift's last 6 games and plays
    tonight, so the chance is read over the 5 games both played (measured 2022-2025)"."""
    n = len(info.get("shared") or [])
    return (f"Backfield partner back: {info['partner']} missed {info['missed']} of {player}'s last "
            f"{info['window']} games and plays tonight, so the chance is read over the {n} game"
            f"{'' if n == 1 else 's'} both played (measured 2022-2025)")
