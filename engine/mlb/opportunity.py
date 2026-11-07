"""Opportunity model — price the chances BEFORE the outcome.

A prop is outcomes-per-opportunity times opportunities, and the second term
is far more predictable than the first. This module measures each hitter's
real plate-appearance volume from his own ingested per-game PA logs, then
compares it to what TONIGHT offers: his batting-order slot plus the run
environment (a high team total means the lineup turns over more).

Why this replaces the static lineup-spot bump in the matchup layer: that
bump compared tonight's slot to league average, but the form baseline is
built from the player's own recent games — which already embed his usual
volume. The real signal is tonight vs HIS norm: a nine-hole regular moved
to the two-hole in a high-total game gets a real volume boost; a leadoff
fixture batting leadoff again gets nothing, no matter how good slot 1 is.

Discipline: shrink by sample, clamp tight (volume moves a prop by a few
percent, never more), and fall back to the old static bump when a player
has no PA history yet.
"""

from __future__ import annotations

from ..statmath import clamp

MIN_GAMES = 10                    # PA history needed before a player counts
FACTOR_CLAMP = (0.90, 1.12)
NOTE_THRESHOLD = 0.03

# Baseline runs per team; totals above/below scale expected lineup turnover.
LEAGUE_TEAM_TOTAL = 4.5
ENV_PER_RUN = 0.02
ENV_CLAMP = (0.94, 1.08)


def avg_pa_by_player(conn) -> dict[str, dict]:
    """``{normalized_player: {"avg_pa": float, "n": int}}`` from ingested
    per-game plate-appearance logs (market='pa')."""
    from ..sources.oddsapi import normalize_name

    rows = conn.execute(
        "SELECT player, value FROM player_game_logs "
        "WHERE sport='mlb' AND market='pa' AND value > 0").fetchall()

    by_player: dict[str, list[float]] = {}
    for r in rows:
        by_player.setdefault(normalize_name(r["player"]), []).append(
            float(r["value"]))

    out: dict[str, dict] = {}
    for name, vals in by_player.items():
        if len(vals) < MIN_GAMES:
            continue
        out[name] = {"avg_pa": round(sum(vals) / len(vals), 2), "n": len(vals)}
    return out


def expected_pa(spot: int, team_total: float | None = None) -> float:
    """Tonight's expected plate appearances for a batting-order slot,
    scaled by the run environment (more runs = the order turns over more)."""
    from .homeruns import PA_BY_SPOT, DEFAULT_PA

    base = PA_BY_SPOT.get(spot, DEFAULT_PA)
    if team_total:
        env = clamp(1.0 + (team_total - LEAGUE_TEAM_TOTAL) * ENV_PER_RUN,
                    *ENV_CLAMP)
        base *= env
    return base


def attach_opportunity(slate, avg_pa: dict[str, dict]) -> int:
    """Set ``prop.pa_factor`` / ``pa_note`` = tonight's expected PA vs the
    player's OWN measured average. Returns props with a non-1.0 factor."""
    from ..sources.oddsapi import normalize_name

    attached = 0
    for prop in slate.props:
        if prop.position == "SP" or not prop.lineup_spot:
            continue
        rec = avg_pa.get(normalize_name(prop.player))
        if not rec or rec["avg_pa"] <= 0:
            continue
        game = slate.game_for(prop)
        team_total = (game.total / 2.0) if game and game.total else None
        exp = expected_pa(prop.lineup_spot, team_total)
        factor = round(clamp(exp / rec["avg_pa"], *FACTOR_CLAMP), 3)
        prop.pa_factor = factor
        if abs(factor - 1.0) >= NOTE_THRESHOLD:
            direction = "volume boost" if factor > 1.0 else "fewer chances"
            prop.pa_note = (f"Batting {prop.lineup_spot}{_ord(prop.lineup_spot)} "
                            f"tonight (≈{exp:.1f} PA) vs his usual "
                            f"{rec['avg_pa']:.1f} — {direction}")
        if factor != 1.0:
            attached += 1
    return attached


def _ord(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
