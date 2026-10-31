"""Each forward line's and defence pair's expected goals for and against, on the ice together.

Ethan, 2026-10-15, from the brainstorm he asked to have built: NHL line
matchups — the lines and pairs with their xGF and xGA. The board already
reads each team's lines off the shift charts of its newest games
(engine/nhl/lines); this reads the same games' play-by-play and counts,
for every unblocked attempt at even strength, which of the team's units
had every member on the ice at that second. Our own xG model
(engine/nhl/xg) prices each attempt.

CONTEXT ONLY. It moves no number: a line's on-ice record over two games
is a handful of attempts, and the card prints the count beside the rate so
nobody reads 1.40 xGF from four shots as a finding.

WHAT IT CANNOT SEE: power-play and penalty-kill time (left out on
purpose — a unit's even-strength record is the one about the unit), a shot
whose second the feed did not give, and any game whose play-by-play or
shift chart would not load (that game is skipped, never guessed).
"""

from __future__ import annotations

#: Unblocked attempts — what xG prices (engine/nhl/xg.UNBLOCKED).
UNBLOCKED = ("goal", "sog", "miss")


def on_ice(chart: dict, players: list, t: int) -> bool:
    """Every one of ``players`` has a shift covering second ``t``.

    A shift that ends at ``t`` counts and one that starts at ``t`` does
    not, so a shot at a change is credited to the unit that was out
    there for it."""
    for p in players:
        if not any(s < t <= e for s, e in chart.get(p) or ()):
            return False
    return True


def unit_xg(units: list, games: list, team: str, price) -> list:
    """``units``: [{"players": [...], "together": f}] (one team's lines or
    pairs). ``games``: [(chart, shots)] — that team's shift chart
    ({player: [(start_s, end_s)]}) and the game's parsed shots, each with
    ``t`` (seconds from the opening face-off), ``team``, ``kind``,
    ``strength`` and ``empty_net``. ``price(shot)`` is its xG.

    Returns the units with ``xgf``, ``xga`` (sums), ``att_for``,
    ``att_against`` (counts) and ``games`` added."""
    out = [dict(u, xgf=0.0, xga=0.0, att_for=0, att_against=0, games=0) for u in units]
    for chart, shots in games:
        if not chart:
            continue
        for u in out:
            if all(p in chart for p in u["players"]):
                u["games"] += 1
        for s in shots or ():
            if s.get("kind") not in UNBLOCKED or s.get("strength") != "EV" or s.get("empty_net"):
                continue
            t = s.get("t")
            if not isinstance(t, (int, float)):
                continue
            mine = s.get("team") == team
            for u in out:
                if on_ice(chart, u["players"], t):
                    x = float(price(s) or 0.0)
                    if mine:
                        u["xgf"] += x
                        u["att_for"] += 1
                    else:
                        u["xga"] += x
                        u["att_against"] += 1
    for u in out:
        u["xgf"], u["xga"] = round(u["xgf"], 2), round(u["xga"], 2)
        tot = u["xgf"] + u["xga"]
        u["xgf_pct"] = round(u["xgf"] / tot, 3) if tot > 0 else None
    return out


def team_units(lines: dict, games: list, team: str, price) -> dict:
    """``lines`` as engine/nhl/lines.build returns it ({"forwards": [...],
    "defence": [...]}) with each unit's on-ice record added."""
    out = dict(lines or {})
    for key in ("forwards", "defence"):
        if out.get(key):
            out[key] = unit_xg(out[key], games, team, price)
    out["xg_games"] = sum(1 for c, _s in games if c)
    return out
