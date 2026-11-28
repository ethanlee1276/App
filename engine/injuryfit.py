"""How much an injured opponent (or team-mate) moves a player: measured.

engine/injuries.KNOCK_ONS says, for example, that an opponent's starting
corner ruled out lifts a receiver's catches ×1.06. This measures each rule
the way the board would have applied it, from the files the NFL build
already reads: nflverse weekly box scores, weekly injury reports and depth
charts (the build's own `injuries_for_week` + `refine_injury_roles`, so a
backup's absence counts for nothing here exactly as it counts for nothing
there).

For every regular-season player-game from week 4 on — each team's top
three by volume at the position (one quarterback), ranked on the weeks
before it, as the board picks them — with at least three earlier games:

    expected = his own average in those earlier games
    flagged  = a ruled-out player in the rule's roles on the rule's side

and the measured multiplier is the ratio of actual to expected in flagged
games over the same ratio in the rest. The SE is from the spread of the
flagged games' own ratios. Standard library only.
"""
from __future__ import annotations

import math
from collections import defaultdict

#: Stat column each market is measured on.
COLUMN = {"rec_yds": "receiving_yards", "receptions": "receptions", "rush_yds": "rushing_yards",
          "pass_yds": "passing_yards"}
#: Volume that ranks a position, as sources/nflverse.top_players_for_week does.
VOLUME = {"QB": ("attempts",), "RB": ("carries", "targets"), "WR": ("targets",), "TE": ("targets",)}
#: A player below this average is not the player the rule is about.
FLOOR = {"rec_yds": 15.0, "receptions": 1.5, "rush_yds": 15.0, "pass_yds": 150.0}
FIRST_WEEK = 4
MIN_PRIOR = 3


def _f(r: dict, k: str) -> float:
    try:
        return float(r.get(k) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _team(r: dict) -> str:
    return str(r.get("team") or r.get("recent_team") or "")


def samples(rows: list[dict], out_roles: dict, rules) -> dict:
    """{rule.key: [(expected, flagged, actual)]} for one season.

    ``out_roles`` is {week: {team: set of ruled-out roles}}."""
    games: dict = defaultdict(dict)
    for r in rows:
        if str(r.get("season_type") or "REG") != "REG":
            continue
        games[(str(r.get("player_display_name") or ""), _team(r))][int(_f(r, "week"))] = r
    got: dict = {rule.key: [] for rule in rules}
    for wk in sorted({w for g in games.values() for w in g}):
        if wk < FIRST_WEEK:
            continue
        vol: dict = defaultdict(list)
        for (name, team), g in games.items():
            prev = [g[w] for w in g if w < wk]
            if not prev:
                continue
            pos = str(prev[-1].get("position") or "").upper()
            if pos in VOLUME:
                vol[(team, pos)].append((sum(_f(p, c) for p in prev for c in VOLUME[pos]), name))
        rank = {}
        for (team, pos), lst in vol.items():
            lst.sort(reverse=True)
            for i, (_v, name) in enumerate(lst[:1 if pos == "QB" else 3], 1):
                rank[(team, name)] = (pos, i)
        roles_out = out_roles.get(wk, {})
        for (name, team), g in games.items():
            r = g.get(wk)
            if not r or (team, name) not in rank:
                continue
            pos, i = rank[(team, name)]
            prev = [g[w] for w in sorted(g) if w < wk]
            if len(prev) < MIN_PRIOR:
                continue
            usage = {"WR": f"wr{i}", "RB": f"rb{i}"}.get(pos, "")
            for rule in rules:
                if pos not in rule.positions or (rule.usage and usage not in rule.usage):
                    continue
                side = str(r.get("opponent_team") or "") if rule.side == "opp" else team
                flagged = bool(roles_out.get(side, set()) & set(rule.roles))
                for market in rule.markets:
                    col = COLUMN.get(market)
                    if not col:
                        continue
                    e = sum(_f(p, col) for p in prev) / len(prev)
                    if e < FLOOR[market]:
                        continue
                    got[rule.key].append((e, flagged, _f(r, col)))
    return got


def measure(pts: list[tuple]) -> dict:
    """The measured multiplier: flagged games' actual/expected over the rest's."""
    on = [(e, y) for e, fl, y in pts if fl]
    off = [(e, y) for e, fl, y in pts if not fl]
    if not on or not off or not sum(e for e, _y in off) or not sum(e for e, _y in on):
        return {"mult": None, "se": None, "n": len(on), "others": len(off)}
    base = sum(y for _e, y in off) / sum(e for e, _y in off)
    mult = (sum(y for _e, y in on) / sum(e for e, _y in on)) / base
    ratios = [y / e for e, y in on]
    mean = sum(ratios) / len(ratios)
    sd = math.sqrt(sum((x - mean) ** 2 for x in ratios) / (len(ratios) - 1)) if len(ratios) > 1 else None
    se = sd / math.sqrt(len(ratios)) / base if sd is not None and base else None
    return {"mult": round(mult, 4), "se": None if se is None else round(se, 4), "n": len(on), "others": len(off)}


def out_roles_by_week(injury_rows: list[dict], depth_rows: list[dict], weeks) -> dict:
    """{week: {team: ruled-out roles}}, through the build's own parsers."""
    from .injuries import RULED_OUT
    from .sources import depthcharts as D
    from .sources import injuries as I
    out: dict = {}
    for wk in weeks:
        injs = I.injuries_for_week(injury_rows, wk)
        D.refine_injury_roles(injs, depth_rows, wk)
        by: dict = defaultdict(set)
        for j in injs:
            if j.status in RULED_OUT:
                by[j.team].add(j.role)
        out[wk] = dict(by)
    return out
