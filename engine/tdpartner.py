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

NOT THE OTHER WAY ROUND. A back whose partner is ruled out tonight is the teammate-absence step's question, and
for touchdowns that measured too noisy to price (touchdowns.td_probability's mate card); it stays shown, not
priced.
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


def words(info: dict, player: str) -> str:
    """The reason line: "Backfield partner back: Kyle Monangai missed 3 of D'Andre Swift's last 6 games and plays
    tonight, so the chance is read over the 5 games both played (measured 2022-2025)"."""
    n = len(info.get("shared") or [])
    return (f"Backfield partner back: {info['partner']} missed {info['missed']} of {player}'s last "
            f"{info['window']} games and plays tonight, so the chance is read over the {n} game"
            f"{'' if n == 1 else 's'} both played (measured 2022-2025)")
