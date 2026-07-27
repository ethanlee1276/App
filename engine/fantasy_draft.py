"""Fantasy draft kit — turn last season's usage into a draft board.

The same doctrine as the rest of the fantasy engine (volume is predictive,
efficiency is noise), pointed at the one decision the season starts with.
Three ideas, each of which most draft content gets wrong:

* **Value over replacement, not points.** The 4th QB scores more than the
  20th WR, and drafting him early is still usually wrong: the QB you can
  get ten rounds later scores nearly as much, and the WR you passed on has
  no such substitute. Every player is valued against the best freely
  available body at his own position (the "replacement"), which is what
  actually decides a start/sit — and a draft pick.
* **Tiers, not ranks.** The difference between WR7 and WR9 is noise; the
  cliff between tier 2 and tier 3 is real. Tier breaks are placed where
  the projected-points gap between consecutive players is large, so the
  board says "these six are interchangeable, then it drops" instead of
  pretending rank 12 beats rank 13.
* **Projection = volume first, production second.** Where play-by-play
  xFP exists it leads the blend; actual PPR confirms. A player who scored
  above his opportunity is regression risk and the board says so.

Honesty constraints, stated because they matter at the table: everything
here is LAST season run forward. The board knows nothing about rookies
(they simply aren't on it), coaching changes, free-agency moves, or camp
news. The tiers structure the draft; picking within a tier is where your
own news-reading beats any model built on stale volume.
"""

from __future__ import annotations

from .fantasy import _weekly, _pbp_weekly, _short_key, league_rates, USAGE_MIN_WEEKS

# 12-team, 1QB / 2RB / 2WR / 1TE / 1FLEX. The flex is mostly RB/WR in
# practice, so replacement rank = starters*teams plus a flex share.
DEFAULT_TEAMS = 12
REPLACEMENT_RANK = {"QB": 12, "RB": 26, "WR": 26, "TE": 12}
# A new tier starts when the projected-PPG gap to the player above is at
# least this. Within a position, ~1.2 PPG over a season is a real cliff.
TIER_GAP = 1.2
MIN_GAMES = 6            # below this a per-game average is mostly noise
BOARD_POSITIONS = ("QB", "RB", "WR", "TE")
# xFP leads the blend where it exists (it values every opportunity by where
# it happened); actual production confirms. For QBs there is no volume
# model — attempts are shown as context and production carries the load.
XFP_WEIGHT = 0.6
SLEEPER_GAP = 1.5        # xFP above actual by this much = usage says buy


def _players(conn, season: int) -> list[dict]:
    data = _weekly(conn, season)
    rates = league_rates(conn, season)
    pbp = _pbp_weekly(conn, season)
    out = []
    for player, p in data["players"].items():
        pos = (p["position"] or "").upper()
        if pos not in BOARD_POSITIONS:
            continue
        weeks = sorted(p["weeks"])
        n = len(weeks)
        if n < USAGE_MIN_WEEKS:
            continue
        ppg = sum(m.get("fp_ppr", 0.0) for m in p["weeks"].values()) / n
        tgt = sum(m.get("targets", 0.0) for m in p["weeks"].values()) / n
        car = sum(m.get("carries", 0.0) for m in p["weeks"].values()) / n
        att = sum(m.get("pass_att", 0.0) for m in p["weeks"].values()) / n

        xfp_vals = [m["xfp"] for m in pbp.get(_short_key(player, p["team"]),
                                              {}).values() if "xfp" in m]
        rate = rates.get(pos)
        if len(xfp_vals) >= USAGE_MIN_WEEKS:
            xppg = sum(xfp_vals) / len(xfp_vals)
            basis = "xfp"
        elif pos != "QB" and rate and (tgt + car) > 0:
            xppg = rate[0] * tgt + rate[1] * car
            basis = "volume"
        else:
            # QBs (and anyone with no volume signal): production is all we
            # have. Labeled so the page can say so.
            xppg = ppg
            basis = "points"
        proj = XFP_WEIGHT * xppg + (1.0 - XFP_WEIGHT) * ppg
        out.append({
            "player": player, "team": p["team"], "position": pos,
            "games": n, "ppg": round(ppg, 1), "xppg": round(xppg, 1),
            "proj": round(proj, 1), "basis": basis,
            "targets_pg": round(tgt, 1), "carries_pg": round(car, 1),
            "pass_att_pg": round(att, 1),
            "small_sample": n < MIN_GAMES,
        })
    return out


def _assign_tiers(rows: list[dict], gap: float = TIER_GAP) -> None:
    """Tier breaks at real cliffs in projected PPG (rows already sorted
    descending). Mutates in place: adds ``tier`` (1-based)."""
    tier = 1
    for i, r in enumerate(rows):
        if i and rows[i - 1]["proj"] - r["proj"] >= gap:
            tier += 1
        r["tier"] = tier


def build_draft_kit(conn, season: int, teams: int = DEFAULT_TEAMS) -> dict:
    """The full kit: per-position tiers, a VORP-ordered overall board,
    replacement baselines, and the usage-says-buy sleepers list."""
    players = _players(conn, season)

    by_pos: dict[str, list[dict]] = {}
    for r in players:
        by_pos.setdefault(r["position"], []).append(r)

    scale = teams / DEFAULT_TEAMS
    baselines: dict[str, float] = {}
    for pos, rows in by_pos.items():
        rows.sort(key=lambda r: r["proj"], reverse=True)
        _assign_tiers(rows)
        rank = max(2, round(REPLACEMENT_RANK.get(pos, 12) * scale))
        # Replacement = the best player your league-mates can grab for free.
        # If the position is shallower than the replacement rank, the last
        # man on the list is the baseline.
        baseline = rows[min(rank, len(rows)) - 1]["proj"] if rows else 0.0
        baselines[pos] = round(baseline, 1)
        for i, r in enumerate(rows):
            r["pos_rank"] = i + 1
            r["vorp"] = round(r["proj"] - baseline, 1)

    board = sorted(players, key=lambda r: r["vorp"], reverse=True)

    # Usage says buy: expected clearly above actual — the draft-day version
    # of buy-low. (Sell-highs matter less at the table: the market already
    # prices last year's points; the board's lower proj handles it.)
    sleepers = sorted(
        (r for r in players
         if r["basis"] != "points" and r["xppg"] - r["ppg"] >= SLEEPER_GAP),
        key=lambda r: r["xppg"] - r["ppg"], reverse=True)[:10]

    return {
        "season": season, "teams": teams,
        "replacement": baselines,
        "board": board[:150],
        "tiers": {pos: rows[:40] for pos, rows in by_pos.items()},
        "sleepers": sleepers,
        "notes": [
            "Projections are last season's volume run forward — the board "
            "knows nothing about rookies (they are not on it), coaching "
            "changes, or free agency.",
            "Draft by tier, not rank: inside a tier the differences are "
            "noise, and your read on camp news beats the model's.",
            "VORP is points over the best freely-available player at the "
            "same position — it is why the 4th-best QB is worth less than "
            "the 15th-best WR.",
        ],
    }
