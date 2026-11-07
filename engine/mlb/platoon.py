"""Platoon splits — each hitter's measured performance vs LHP / RHP.

The matchup layer's generic platoon bump (+4% for any favorable handedness)
treats every hitter identically. This module replaces it with the player's
OWN measured split, computed entirely from data we already ingest: game logs
joined to the opposing team's starter (and his handedness) on each date.

Discipline, as always:

* a split needs ``MIN_PER_SIDE`` games against a hand before it counts;
* the factor is shrunk toward 1.0 by sample size and clamped — books price
  the famous platoon bats in, so the edge is a nudge, not a lever;
* an unknown starter or an unmeasured hitter falls back to the generic bump.
"""

from __future__ import annotations

from ..statmath import clamp

MIN_PER_SIDE = 8
SHRINK = 15.0
FACTOR_CLAMP = (0.85, 1.18)

#: League platoon norms — the handicapping script (§11): a thin personal
#: split regresses "toward the league-average platoon effect for his
#: handedness, NOT toward no effect". Shrinking to 1.0 meant a hitter
#: with nine games against lefties ERASED the advantage the league says
#: exists, while a hitter with zero games kept it via the generic bump —
#: less data was treated as more information. The advantage figure is
#: the same +4% the generic bump has always used; the same-hand penalty
#: is its mirror, slightly tempered because books price the obvious side.
LEAGUE_ADV = 1.04
LEAGUE_DIS = 0.97


def league_norm(bats: str, throws: str) -> float:
    """The league-average platoon factor for this matchup direction.
    Switch hitters always hold the advantage; unknown hands claim none."""
    bats = (bats or "").upper()
    throws = (throws or "").upper()
    if throws not in ("L", "R") or bats not in ("L", "R", "S"):
        return 1.0
    if bats == "S" or bats != throws:
        return LEAGUE_ADV
    return LEAGUE_DIS

# Official-split fallback: shrink by plate appearances (a half season vs
# one hand is ~200 PA) and demand a real sample before it speaks.
OFFICIAL_SHRINK_PA = 130.0
OFFICIAL_MIN_PA = 60


def platoon_splits(conn, market: str) -> dict[str, dict]:
    """``{normalized_player: {"L": factor, "R": factor, "nL": int, "nR": int}}``

    ``factor`` = the player's mean in this market against that hand relative
    to his overall mean, shrunk and clamped. Joins each log row to the
    OPPONENT's starter that day (the pitcher the hitter actually faced)."""
    from ..sources.oddsapi import normalize_name

    rows = conn.execute(
        "SELECT l.player, l.value, s.throws FROM player_game_logs l "
        "JOIN game_starters s ON s.sport=l.sport AND s.period=l.period "
        "  AND s.team=l.opponent "
        "WHERE l.sport='mlb' AND l.market=? AND s.throws IN ('L','R')",
        (market,)).fetchall()

    by_player: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        p = by_player.setdefault(normalize_name(r["player"]), {"L": [], "R": []})
        p[r["throws"]].append(float(r["value"]))

    out: dict[str, dict] = {}
    for name, sides in by_player.items():
        all_vals = sides["L"] + sides["R"]
        if len(all_vals) < MIN_PER_SIDE * 2:
            continue
        overall = sum(all_vals) / len(all_vals)
        if overall <= 0:
            continue
        entry: dict = {"nL": len(sides["L"]), "nR": len(sides["R"])}
        for hand in ("L", "R"):
            vals = sides[hand]
            if len(vals) < MIN_PER_SIDE:
                entry[hand] = 1.0
                continue
            raw = (sum(vals) / len(vals)) / overall
            shrunk = 1.0 + (raw - 1.0) * (len(vals) / (len(vals) + SHRINK))
            entry[hand] = round(clamp(shrunk, *FACTOR_CLAMP), 3)
        out[name] = entry
    return out


def attach_platoon(slate, splits_by_market: dict[str, dict]) -> int:
    """Set ``prop.platoon_factor`` / ``platoon_note`` from tonight's opposing
    starter hand. Returns how many props got a measured (non-1.0) factor."""
    from ..sources.oddsapi import normalize_name

    attached = 0
    for prop in slate.props:
        if prop.position == "SP":
            continue
        game = slate.game_for(prop)
        starter = (game.pitchers or {}).get(prop.opponent) if game else None
        hand = (getattr(starter, "throws", "") or "").upper()
        if hand not in ("L", "R"):
            continue
        splits = splits_by_market.get(prop.market, {})
        s = splits.get(normalize_name(prop.player))
        if not s:
            continue
        factor = s.get(hand, 1.0)
        n = s.get(f"n{hand}", 0)
        # The stored factor was shrunk toward 1.0 with weight n/(n+SHRINK);
        # the script's rule is to regress toward the LEAGUE platoon norm
        # instead. Same weight, so the unclaimed (1-w) mass moves from
        # "no effect" onto the effect the league actually shows.
        norm = league_norm(getattr(prop, "bats", ""), hand)
        if norm != 1.0 and n >= MIN_PER_SIDE:
            w = n / (n + SHRINK)
            factor = round(clamp(factor + (1.0 - w) * (norm - 1.0),
                                 *FACTOR_CLAMP), 3)
        prop.platoon_factor = factor
        if abs(factor - 1.0) >= 0.03:
            verb = "hits" if factor > 1.0 else "struggles"
            prop.platoon_note = (f"Measured split: {verb} vs "
                                 f"{'lefties' if hand == 'L' else 'righties'} "
                                 f"({(factor - 1) * 100:+.0f}% vs his own "
                                 f"average, {n} games)")
        if factor != 1.0:
            attached += 1
    return attached


def attach_official_splits(slate, splits: dict[int, dict]) -> int:
    """Attach the MLB Stats API's own season splits (vs LHP / vs RHP).

    Two jobs: store the raw split on every hitter prop (the HR model reads
    the power side), and — ONLY where our own game-log split couldn't
    measure the player — derive ``platoon_factor`` from the official SLG
    split, so the generic ±4% handedness bump almost never has to fire.
    Our-log splits keep priority: they're market-specific and park-aware
    in a way a season-wide SLG line isn't."""
    attached = 0
    for prop in slate.props:
        if prop.position == "SP" or not getattr(prop, "person_id", 0):
            continue
        sp = splits.get(prop.person_id)
        if not sp:
            continue
        prop.platoon_official = sp
        attached += 1
        if prop.platoon_factor != 1.0:
            continue                      # measured from our logs — keep it
        game = slate.game_for(prop)
        starter = (game.pitchers or {}).get(prop.opponent) if game else None
        hand = (getattr(starter, "throws", "") or "").upper()
        side = sp.get("vl" if hand == "L" else "vr")
        other = sp.get("vr" if hand == "L" else "vl")
        if hand not in ("L", "R") or not side or not other:
            continue
        pa_s, pa_o = side.get("pa", 0), other.get("pa", 0)
        if pa_s < OFFICIAL_MIN_PA or pa_s + pa_o < 2 * OFFICIAL_MIN_PA:
            continue
        blended = (side["slg"] * pa_s + other["slg"] * pa_o) / (pa_s + pa_o)
        if blended <= 0:
            continue
        raw = side["slg"] / blended
        w = pa_s / (pa_s + OFFICIAL_SHRINK_PA)
        # Same regression target as the game-log path: the league norm
        # holds the weight the personal sample hasn't earned.
        norm = league_norm(getattr(prop, "bats", ""), hand)
        factor = round(clamp(norm + (raw - norm) * w, *FACTOR_CLAMP), 3)
        if factor == 1.0:
            continue
        prop.platoon_factor = factor
        verb = "slugs" if factor > 1.0 else "fades"
        prop.platoon_note = (f"Official season split: {verb} "
                             f"{'lefties' if hand == 'L' else 'righties'} "
                             f"(.{side['slg'] * 1000:03.0f} SLG in {pa_s} PA, "
                             f"{(factor - 1) * 100:+.0f}% vs his blend)")
    return attached
