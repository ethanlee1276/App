"""Streak analysis — measured mean reversion, not the gambler's fallacy.

"He's hot, he'll cool off" and "he's due" are both clichés until they're
measured. This module checks the claim against our own ingested logs: for
every player-game in the database, classify the 5-game stretch BEFORE it as
hot / cold / normal relative to the player's own established level, then
look at what actually happened in that next game. The league-wide answer
becomes the adjustment — typically a small give-back after hot streaks and
a small bounce after cold ones, because extreme stretches are mostly
variance around the player's true level.

Discipline, as always:

* factors come from measurement, shrunk by sample size and clamped tight;
* home runs are excluded — a 5-game HR "streak" is nearly all noise, and
  Statcast xSLG regression already handles power sustainability;
* an unmeasured market or a player without enough games gets no factor.
"""

from __future__ import annotations

from ..statmath import clamp

WINDOW = 5                  # the streak window
MIN_PRIOR_GAMES = 10        # established level needed before game counts
MIN_BASE_MEAN = 0.4         # ratio tests are garbage on tiny means (HR-like)
HOT_RATIO = 1.40            # 5-game mean ≥ 140% of his level = hot
COLD_RATIO = 0.60
SHRINK_N = 400.0            # samples before the measured factor gets full weight
FACTOR_CLAMP = (0.93, 1.07)

# Markets worth streak-testing (counting stats with usable per-game means).
STREAK_MARKETS = ("total_bases", "hits", "strikeouts")


def classify(recent_mean: float, base_mean: float) -> str:
    """"hot" / "cold" / "normal" for a 5-game stretch vs the player's level."""
    if base_mean < MIN_BASE_MEAN:
        return "normal"
    ratio = recent_mean / base_mean
    if ratio >= HOT_RATIO:
        return "hot"
    if ratio <= COLD_RATIO:
        return "cold"
    return "normal"


def measure_reversion(conn, market: str) -> dict:
    """What ACTUALLY happens the game after a streak, league-wide.

    Returns ``{"hot": {"factor": f, "n": n}, "cold": {...}}`` where factor
    is the next-game output of streaking players relative to what normal-
    stretch players do — shrunk toward 1.0 by sample and clamped. A factor
    of 0.96 after hot streaks means: measured across the whole league, the
    hot 5 games gave back ~4% the next night."""
    rows = conn.execute(
        "SELECT player, period, value FROM player_game_logs "
        "WHERE sport='mlb' AND market=? ORDER BY player, period",
        (market,)).fetchall()

    by_player: dict[str, list[float]] = {}
    for r in rows:
        by_player.setdefault(r["player"], []).append(float(r["value"]))

    sums = {"hot": [0.0, 0], "cold": [0.0, 0], "normal": [0.0, 0]}
    for vals in by_player.values():
        for i in range(MIN_PRIOR_GAMES + WINDOW, len(vals)):
            base = sum(vals[:i - WINDOW]) / (i - WINDOW)
            if base < MIN_BASE_MEAN:
                continue
            recent = sum(vals[i - WINDOW:i]) / WINDOW
            state = classify(recent, base)
            sums[state][0] += vals[i] / base
            sums[state][1] += 1

    out: dict = {}
    norm_mean = (sums["normal"][0] / sums["normal"][1]) if sums["normal"][1] else 1.0
    if norm_mean <= 0:
        return out
    for state in ("hot", "cold"):
        total, n = sums[state]
        if n < 50:
            continue                       # too thin to claim anything
        raw = (total / n) / norm_mean
        shrunk = 1.0 + (raw - 1.0) * (n / (n + SHRINK_N))
        out[state] = {"factor": round(clamp(shrunk, *FACTOR_CLAMP), 3), "n": n}
    return out


def attach_streaks(slate, factors_by_market: dict[str, dict]) -> int:
    """Stamp each prop whose current 5-game stretch is hot or cold with the
    MEASURED next-game factor for that state. Returns props stamped."""
    stamped = 0
    for prop in slate.props:
        factors = factors_by_market.get(prop.market)
        if not factors:
            continue
        vals = [g.value for g in prop.logs]
        if len(vals) < MIN_PRIOR_GAMES + WINDOW:
            continue
        recent = sum(vals[:WINDOW]) / WINDOW          # logs are newest-first
        base = sum(vals[WINDOW:]) / (len(vals) - WINDOW)
        state = classify(recent, base)
        if state == "normal" or state not in factors:
            continue
        f = factors[state]
        prop.streak_factor = f["factor"]
        delta = (f["factor"] - 1.0) * 100
        if state == "hot":
            prop.streak_note = (f"Hot stretch — last {WINDOW} games {recent:.2f} vs "
                                f"his usual {base:.2f}. Measured league-wide, such "
                                f"streaks give back {abs(delta):.0f}% the next game "
                                f"({f['n']:,} cases)")
        else:
            prop.streak_note = (f"Cold stretch — last {WINDOW} games {recent:.2f} vs "
                                f"his usual {base:.2f}. Measured league-wide, such "
                                f"slumps bounce back {abs(delta):.0f}% the next game "
                                f"({f['n']:,} cases)")
        stamped += 1
    return stamped
