"""Forward lines and defence pairs, read off shared ice time.

Ethan, 2026-10-03: "do all of them" (line combinations). Coaches post
lines at the morning skate and nobody keyless republishes them; what the
league does publish is every shift of every game (engine/sources/nhlshifts),
and a line is simply the three forwards who are on the ice together most.

THE METHOD, all counting. For each pair of a team's skaters, the seconds
their shifts overlap, summed over the team's newest games (the newest
weighted most — coaches shuffle lines, last night's are the best guess).
Forwards are grouped greedily: the forward with the most ice time and the
two forwards he shared the most ice with are line one; the same again from
who is left gives lines two to four. Defence the same in pairs. A line
carries how much of its members' ice they spent together (``together``),
so a reader can see a settled line from a shuffled one.

WHAT IT CANNOT SEE: tonight's changes (an injury, a call-up, a coach's
blender) until a game is played with them, and special-teams units, which
the power-play role reads instead (engine/nhl/xg.power_play). Positions
come from our own logs; a skater we have no position for is left out
rather than guessed onto a line.
"""
from __future__ import annotations

FORWARD_LINES, DEFENCE_PAIRS = 4, 3
#: Weight of each older game against the newest (newest = 1).
DECAY = 0.5


def overlap(a: list, b: list) -> int:
    """Seconds two players' shift lists overlap."""
    a, b = sorted(a), sorted(b)
    i = j = tot = 0
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if hi > lo:
            tot += hi - lo
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return tot


def _group(names: list, toi: dict, pair: dict, size: int, count: int) -> list:
    left, groups = sorted(names, key=lambda n: -toi.get(n, 0)), []
    while left and len(groups) < count:
        lead = left.pop(0)
        mates = sorted(left, key=lambda n: -pair.get(frozenset((lead, n)), 0))[:size - 1]
        for m in mates:
            left.remove(m)
        members = [lead] + mates
        shared = min((pair.get(frozenset((x, y)), 0) for k, x in enumerate(members)
                      for y in members[k + 1:]), default=0)
        own = min((toi.get(x, 0) for x in members), default=0)
        groups.append({"players": members, "together": round(shared / own, 2) if own else 0.0})
    return groups


def build(games: list[dict], positions: dict) -> dict:
    """``games`` = parse_shifts results for one team's newest games, newest
    first ({player: [(start, end)]} each). ``positions`` = {player: "C" /
    "L" / "R" / "D" / "G"}. → {"forwards": [...], "defence": [...],
    "games": n}, each group {"players", "together"}."""
    toi: dict = {}
    pair: dict = {}
    for i, g in enumerate(games):
        w = DECAY ** i
        names = [n for n in g if positions.get(n) and positions[n] != "G"]
        for n in names:
            toi[n] = toi.get(n, 0) + w * sum(e - s for s, e in g[n])
        for k, a in enumerate(names):
            for b in names[k + 1:]:
                if (positions[a] == "D") != (positions[b] == "D"):
                    continue
                key = frozenset((a, b))
                pair[key] = pair.get(key, 0) + w * overlap(g[a], g[b])
    fwd = [n for n in toi if positions.get(n) not in ("D", "G")]
    dmen = [n for n in toi if positions.get(n) == "D"]
    return {"forwards": _group(fwd, toi, pair, 3, FORWARD_LINES),
            "defence": _group(dmen, toi, pair, 2, DEFENCE_PAIRS), "games": len(games)}


def slot_of(lines: dict, player: str) -> dict | None:
    """{"unit": "F1".."F4" / "D1".."D3", "mates": [...], "together"} for one
    player, or None when he is on no line."""
    for kind, tag in (("forwards", "F"), ("defence", "D")):
        for i, grp in enumerate((lines or {}).get(kind) or [], 1):
            if player in grp["players"]:
                return {"unit": f"{tag}{i}", "mates": [p for p in grp["players"] if p != player],
                        "together": grp["together"]}
    return None
