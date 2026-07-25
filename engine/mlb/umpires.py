"""Umpire model — the home-plate ump's measured effect on Ks and runs.

The strike zone is not called uniformly: across a season the widest-zone
umpires generate several more called strikeouts per game than the tightest,
and the assignment is announced only hours before first pitch — a genuinely
late-breaking input that books don't always fully price into strikeout props.

Profiles are computed from OUR OWN ingested history, not a third-party feed:

  * ``k_factor``  — average STARTER strikeouts in this ump's games vs the
    league average of the same sample. Starter Ks (not team Ks) because that
    is exactly the stat the strikeout prop settles on.
  * ``run_factor`` — average total runs in his games vs league average, for
    the game-total context.

Both are shrunk toward 1.0 by games worked (an ump with 4 games is mostly
league average), and clamped: even the most extreme real zones are a
single-digit-percent effect, so anything larger is treated as sample noise.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..statmath import clamp

# An ump's profile firms up over this many games behind the plate.
SHRINK_GAMES = 8.0
# Real zone effects top out around ±8-10%; beyond that is noise, not signal.
FACTOR_CLAMP = (0.90, 1.10)


@dataclass
class UmpProfile:
    name: str
    k_factor: float = 1.0
    run_factor: float = 1.0
    games: int = 0


def _shrunk_factor(values: list[float], league_avg: float, n: int) -> float:
    if not values or league_avg <= 0:
        return 1.0
    raw = (sum(values) / len(values)) / league_avg
    shrunk = 1.0 + (raw - 1.0) * (n / (n + SHRINK_GAMES))
    return round(clamp(shrunk, *FACTOR_CLAMP), 3)


def umpire_profiles(conn, sport: str = "mlb") -> dict[str, UmpProfile]:
    """``{umpire_name: UmpProfile}`` from ingested games, starters and logs."""
    # Total runs per ump-game (joined to final scores).
    runs_by_ump: dict[str, list[float]] = {}
    for r in conn.execute(
            "SELECT u.umpire, g.home_score + g.away_score AS runs "
            "FROM game_umpires u JOIN games g "
            "  ON g.sport=u.sport AND g.season=u.season "
            " AND g.period=u.period AND g.game_id=u.game_id "
            "WHERE u.sport=? AND g.home_score IS NOT NULL "
            "  AND g.away_score IS NOT NULL AND u.umpire != ''", (sport,)):
        runs_by_ump.setdefault(r["umpire"], []).append(float(r["runs"]))

    # Starter strikeouts per ump-game — the stat K props actually settle on.
    ks_by_ump: dict[str, list[float]] = {}
    for r in conn.execute(
            "SELECT u.umpire, l.value FROM game_umpires u "
            "JOIN game_starters s ON s.sport=u.sport AND s.period=u.period "
            "  AND s.game_id=u.game_id "
            "JOIN player_game_logs l ON l.sport=u.sport AND l.period=u.period "
            "  AND l.player=s.pitcher AND l.market='strikeouts' "
            "WHERE u.sport=? AND u.umpire != ''", (sport,)):
        ks_by_ump.setdefault(r["umpire"], []).append(float(r["value"]))

    all_runs = [v for vals in runs_by_ump.values() for v in vals]
    all_ks = [v for vals in ks_by_ump.values() for v in vals]
    league_runs = (sum(all_runs) / len(all_runs)) if all_runs else 0.0
    league_ks = (sum(all_ks) / len(all_ks)) if all_ks else 0.0

    out: dict[str, UmpProfile] = {}
    for name in set(runs_by_ump) | set(ks_by_ump):
        n = len(runs_by_ump.get(name, []))
        out[name] = UmpProfile(
            name=name,
            k_factor=_shrunk_factor(ks_by_ump.get(name, []), league_ks,
                                    len(ks_by_ump.get(name, [])) // 2 or n),
            run_factor=_shrunk_factor(runs_by_ump.get(name, []), league_runs, n),
            games=n,
        )
    return out


def attach_umpires(games, profiles: dict[str, UmpProfile]) -> int:
    """Set each game's ump factors from its announced plate umpire.

    Returns how many games got a non-neutral profile. Unknown or unannounced
    umps stay at 1.0 — exactly neutral, never a guess.
    """
    attached = 0
    for g in games:
        prof = profiles.get(g.plate_umpire or "")
        if prof is None:
            continue
        g.ump_k_factor = prof.k_factor
        g.ump_run_factor = prof.run_factor
        if prof.k_factor != 1.0 or prof.run_factor != 1.0:
            attached += 1
    return attached
