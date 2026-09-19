"""What each football factor is actually worth, measured.

`engine.matchup`, `engine.weather` and `engine.touchdowns` all price a
game the way a bettor talks about one — a soft run defence, a team
favoured by ten leaning on the clock, wind at the lake. Every one of
those adjustments is a hand-set constant. None had been checked against
an outcome.

They are not all the same size, and one of them is not the size we
apply. Measured walk-forward over five seasons, production against the
player's own prior form, split by how generous the opponent had been to
that market so far:

    rush_yds     stingiest 1.079  ->  most generous 1.277   (+18%)
    rec_yds      stingiest 1.168  ->  most generous 1.290   (+10%)
    receptions   stingiest 0.941  ->  most generous 1.053   (+12%)

Monotone in all three, so the direction is right and the effect is real.
But `matchup._defense_factor` is clamped to (0.80, 1.25) — a 56% swing
between extremes against a measured 10-18%.

WHY THE LEVELS ALL SIT ABOVE 1.0, since it looks like a bug and is not.
The baseline is the player's mean over EARLIER weeks, and a player who
keeps getting snaps is usually one whose role is growing, so his next
game beats his own trailing average more often than not. That bias is
identical in every bucket, which is why the comparison is between
buckets and never against 1.0.

WALK-FORWARD, and it has to be. A defence's rating uses only the weeks
already played; rating it on the full season would let the yards a
player is about to gain help decide how generous his opponent was.

Standard library only. No odds are read — this asks what moves the
STAT, which is prior to what beats a price.
"""

from __future__ import annotations

#: Buckets of opponent generosity, as a ratio to the league average
#: allowed so far. Five, because ten leaves the tails too thin to read
#: on one season and three cannot show a shape.
BUCKETS = 5
BUCKET_LO, BUCKET_WIDTH = 0.85, 0.075

#: Games a defence and a player each need before the pair is scored.
MIN_PRIOR = 3

#: A bucket needs this many player-games to be reported.
MIN_BUCKET = 200

LABELS = ("stingiest", "stingy", "average", "generous", "most generous")


def defense_effect(conn, market: str, seasons=None) -> dict:
    """``{bucket: {"n", "ratio"}}`` — production against the player's own
    form, by how generous the opponent has been."""
    sql = ("SELECT season, period, player, opponent, value "
           "FROM player_game_logs WHERE sport='nfl' AND market=? "
           "AND value IS NOT NULL ")
    args: list = [market]
    if seasons:
        sql += "AND season IN (%s) " % ",".join("?" * len(seasons))
        args.extend(seasons)
    sql += "ORDER BY season, period"

    allowed: dict = {}
    played: dict = {}
    hist: dict = {}
    out: dict = {}
    season_now = None
    for r in conn.execute(sql, args):
        try:
            int(r["period"])
        except (TypeError, ValueError):
            continue
        season = int(r["season"])
        opp, player, val = r["opponent"] or "", r["player"], float(r["value"])
        if season != season_now:
            # A defence is a different team every September.
            allowed, played, hist, season_now = {}, {}, {}, season
        d_tot, d_n = allowed.get(opp, 0.0), played.get(opp, 0)
        own = hist.get(player) or []
        if d_n >= MIN_PRIOR and len(own) >= MIN_PRIOR:
            base = sum(own) / len(own)
            league = sum(allowed.values()) / max(1, sum(played.values()))
            if base > 1.0 and league > 0:
                strength = (d_tot / d_n) / league
                k = min(BUCKETS - 1,
                        max(0, int((strength - BUCKET_LO) / BUCKET_WIDTH)))
                out.setdefault(k, []).append(val / base)
        allowed[opp] = d_tot + val
        played[opp] = d_n + 1
        hist.setdefault(player, []).append(val)
    return {k: {"n": len(v), "ratio": sum(v) / len(v)}
            for k, v in out.items() if len(v) >= MIN_BUCKET}


def measured_swing(effect: dict) -> float | None:
    """Extreme to extreme, as a multiplier. ``None`` if the ends are thin."""
    if not effect:
        return None
    lo, hi = min(effect), max(effect)
    if lo == hi or not effect[lo]["ratio"]:
        return None
    return effect[hi]["ratio"] / effect[lo]["ratio"]


#: `matchup.evaluate_matchup` clamps its defensive factor to this.
DEFENSE_CLAMP = (0.80, 1.25)


def applied_swing() -> float:
    """What `matchup` PERMITS between its clamps, as the same multiplier.

    A ceiling, not a typical value. `_defense_factor` reads a defence
    profile and the clamp only bites at the ends, so this says how far
    the adjustment CAN move a projection, not how far it usually does.
    Measuring the second needs the profiles the slate builds and is a
    separate job — but a permitted range several times the measured
    effect is worth knowing about on its own, because the picks that
    reach a board are the ones an adjustment moved furthest.
    """
    lo, hi = DEFENSE_CLAMP
    return hi / lo


def report_lines(market: str, effect: dict) -> list:
    if not effect:
        return [f"  {market}: no bucket reached {MIN_BUCKET} player-games"]
    lines = [f"  {market}:"]
    for k in sorted(effect):
        lines.append(f"      {LABELS[k]:<14} n={effect[k]['n']:>6}   "
                     f"ratio {effect[k]['ratio']:.3f}")
    swing = measured_swing(effect)
    if swing is None:
        return lines
    applied = applied_swing()
    # COMPARED ON THE EFFECT, NOT ON THE MULTIPLIER. A swing of 1.10 is a
    # ten percent effect and a permitted 1.56 is a fifty-six percent one,
    # so the ratio between them is 5.6 and not 1.42. Dividing the
    # multipliers understates it badly, which is what the first version
    # of this line did.
    ratio = (applied - 1.0) / (swing - 1.0) if swing > 1.0 else None
    lines.append(f"      measured {swing - 1:+.0%} between extremes; the "
                 f"model's clamp permits {applied - 1:+.0%}")
    if ratio is not None and ratio >= 2.0:
        # THE POINT OF MEASURING. A factor pointing the right way can
        # still be applied several times too hard, and an over-applied
        # true effect moves a pick off the honest number just as surely
        # as a false one — more so, because it survives review.
        lines.append(f"      ⚠️  up to {ratio:.1f}x the effect this data "
                     f"supports (a ceiling, not a typical value)")
    return lines


#: Game-level factors the model prices, with the edges to split them on
#: and what the model does with each. Edges are chosen to put real
#: football boundaries at the splits — a touchdown of spread, a total
#: either side of the mid-forties, the wind speed at which a kicking
#: game changes — not at equal counts, because the question is what
#: happens in the conditions a bettor names.
GAME_FACTORS = {
    # The player's OWN team's spread. Negative is favoured, matching
    # engine.matchup's convention.
    "spread": {
        # n edges make n+1 buckets; five labels for five edges left the
        # last one printing as "5".
        "edges": (-9.5, -3.5, 0.0, 3.5, 9.5),
        "labels": ("big favourite", "favourite", "slight fav", "slight dog",
                   "underdog", "big underdog"),
        "applied": "SCRIPT_CLAMP, +/-5%",
    },
    "total": {
        "edges": (40.5, 44.5, 47.5, 51.5),
        "labels": ("very low", "low", "middling", "high", "very high"),
        "applied": "pace bump, stands down when teamcontext is measured",
    },
    "wind": {
        "edges": (5.0, 10.0, 15.0),
        "labels": ("calm", "breezy", "windy", "gale"),
        "applied": "engine.weather multipliers",
        "outdoor_only": True,
    },
    "temp": {
        "edges": (35.0, 50.0, 70.0),
        "labels": ("freezing", "cold", "mild", "warm"),
        "applied": "engine.weather multipliers",
        "outdoor_only": True,
    },
}


def _bucket(value: float, edges) -> int:
    k = 0
    for e in edges:
        if value >= e:
            k += 1
    return k


def game_effect(conn, market: str, factor: str, seasons=None) -> dict:
    """``{bucket: {"n", "ratio"}}`` for one game-level factor.

    Same shape as `defense_effect` and the same discipline: production
    against the player's own EARLIER form, so the comparison is within a
    player rather than between them, and a game is scored before it
    joins the history.
    """
    spec = GAME_FACTORS[factor]
    edges = spec["edges"]
    # KEYED BY TEAM AS WELL AS WEEK. Sixteen games share a period, so a
    # dict keyed on (season, period) keeps only the last one and the
    # team guard below then discards everyone in the other fifteen —
    # which showed up as buckets of two hundred where the defence
    # measurement had thousands.
    games: dict = {}
    for g in conn.execute(
            "SELECT season, period, home, away, spread, total, roof, temp, "
            "wind FROM games WHERE sport='nfl'"):
        for side in (g["home"], g["away"]):
            if side:
                games[(int(g["season"]), g["period"], side)] = g

    sql = ("SELECT season, period, player, team, value FROM player_game_logs "
           "WHERE sport='nfl' AND market=? AND value IS NOT NULL ")
    args: list = [market]
    if seasons:
        sql += "AND season IN (%s) " % ",".join("?" * len(seasons))
        args.extend(seasons)
    sql += "ORDER BY season, period"

    hist: dict = {}
    out: dict = {}
    season_now = None
    for r in conn.execute(sql, args):
        season, player, team = int(r["season"]), r["player"], r["team"] or ""
        val = float(r["value"])
        if season != season_now:
            hist, season_now = {}, season
        own = hist.get(player) or []
        g = games.get((season, r["period"], team))
        if g is not None and len(own) >= MIN_PRIOR:
            value = _factor_value(factor, spec, g, team)
            base = sum(own) / len(own)
            if value is not None and base > 1.0:
                out.setdefault(_bucket(value, edges), []).append(val / base)
        hist.setdefault(player, []).append(val)
    return {k: {"n": len(v), "ratio": sum(v) / len(v)}
            for k, v in out.items() if len(v) >= MIN_BUCKET}


def _factor_value(factor: str, spec: dict, g, team: str):
    """This game's value for the factor, from the player's side of it."""
    if spec.get("outdoor_only") and (g["roof"] or "") != "outdoors":
        return None
    if factor == "spread":
        if g["spread"] is None:
            return None
        # engine.matchup's convention: negative is favoured.
        return float(g["spread"]) if team == g["home"] else -float(g["spread"])
    raw = g[factor]
    return float(raw) if raw is not None else None


def game_lines(market: str, factor: str, effect: dict) -> list:
    spec = GAME_FACTORS[factor]
    assert len(spec["labels"]) == len(spec["edges"]) + 1, (
        f"{factor}: {len(spec['edges'])} edges make "
        f"{len(spec['edges']) + 1} buckets, not {len(spec['labels'])}")
    if not effect:
        return [f"  {market} / {factor}: no bucket reached {MIN_BUCKET} games"]
    lines = [f"  {market} / {factor}   (model applies: {spec['applied']})"]
    for k in sorted(effect):
        label = spec["labels"][k] if k < len(spec["labels"]) else str(k)
        lines.append(f"      {label:<14} n={effect[k]['n']:>6}   "
                     f"ratio {effect[k]['ratio']:.3f}")
    lo, hi = min(effect), max(effect)
    a, b = effect[lo]["ratio"], effect[hi]["ratio"]
    if not a:
        return lines
    lines.append(f"      end to end: {b / a - 1:+.0%}   "
                 f"{trend(effect)}")
    return lines


def trend(effect: dict) -> str:
    """Whether the buckets actually march, or merely differ at the ends.

    AN END-TO-END NUMBER ON A WANDERING SERIES IS NOT AN EFFECT. rush_yds
    against the spread reads +21% from big favourite to big underdog and
    goes 1.103, 1.219, 1.184, 1.104, 1.167, 1.340 getting there — the
    ends differ and nothing in between agrees. Read as an effect size
    that would license a large adjustment; read as a shape it is noise
    with two loud edges, and the edges are the thinnest buckets.

    Defence, by contrast, climbs every step in all three markets, which
    is why that one is worth acting on and this one is not.
    """
    ks = sorted(effect)
    if len(ks) < 3:
        return ""
    steps = [effect[b]["ratio"] - effect[a]["ratio"]
             for a, b in zip(ks, ks[1:])]
    ups = sum(1 for d in steps if d > 0)
    if ups == len(steps):
        return "(climbs every step)"
    if ups == 0:
        return "(falls every step)"
    # COUNTING DIRECTIONS IS NOT ENOUGH. Wind against rush_yds goes
    # 1.186, 1.116, 1.207, 1.116 — one step up and two down, which a
    # bare count called "mostly one direction" while the series plainly
    # doubles back. What matters is whether the reversals are large
    # relative to the trend, so compare the distance actually travelled
    # against the sum of the absolute steps: a clean run scores 1.0, and
    # a series that walks back most of its own progress scores near 0.
    travelled = abs(sum(steps))
    walked = sum(abs(d) for d in steps)
    ratio = travelled / walked if walked else 0.0
    if ratio >= 0.7:
        return "(mostly one direction)"
    return "⚠️  (wanders — the ends differ but the middle does not agree)"


__all__ = ["BUCKETS", "MIN_BUCKET", "LABELS", "GAME_FACTORS", "trend",
           "defense_effect", "game_effect", "game_lines",
           "measured_swing", "applied_swing", "report_lines"]
