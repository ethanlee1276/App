"""nflverse depth-chart adapter.

Sharpens the injury engine's knock-on effects. The weekly injury report only
carries a player's position, so a ruled-out "T" could be the blind-side LT or a
swing tackle, and a "CB" could be the boundary starter, the slot corner, or a
practice-squad call-up. The depth chart answers both questions:

  * ``depth_position`` refines the role (LT vs RT, boundary CB vs nickel/slot);
  * ``depth_team`` (1 = starter) demotes backups so their absence stops
    triggering knock-on adjustments entirely.

What it still can't say is how *good* the starter is — "elite CB vs depth CB"
needs a grades source (PFF-style), which stays future work.

Same delivery as the other nflverse feeds: release URLs (often blocked by
egress policy) with a local ``data/cache/depth_charts_<season>.csv`` fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .fetch import fetch_csv, load_local_csv, CACHE_DIR, DataUnavailable
from .nflverse import _s, _f
from .oddsapi import normalize_name
from ..models import Injury


def _urls(season: int) -> list[str]:
    base = "https://github.com/nflverse/nflverse-data/releases/download"
    return [
        f"{base}/depth_charts/depth_charts_{season}.csv",
        f"{base}/depth_charts/depth_charts_{season}.csv.gz",
    ]


def load_depth_charts(season: int) -> list[dict]:
    local = CACHE_DIR / f"depth_charts_{season}.csv"
    if local.exists():
        return load_local_csv(local)
    last_err = None
    for url in _urls(season):
        try:
            return fetch_csv(url, f"depth_charts_{season}.csv")
        except DataUnavailable as exc:
            last_err = exc
    raise DataUnavailable(
        f"Depth charts for {season} are unavailable here (GitHub release access "
        f"is blocked by this environment's egress policy). Export them once and "
        f"save to {local} — e.g. in Python:\n"
        f"    import nfl_data_py as nfl\n"
        f"    nfl.import_depth_charts([{season}]).to_csv('{local}', index=False)\n"
        f"(last error: {last_err})"
    )


# depth_position -> engine role. Only positions the injury engine reasons
# about are mapped; anything else keeps its report-derived role.
ROLE_BY_DEPTH_POS = {
    "LT": "LT",
    "RT": "OT", "T": "OT",
    "LCB": "cb1", "RCB": "cb1", "CB": "cb1",
    "NB": "slot_cb", "NCB": "slot_cb", "SCB": "slot_cb", "SLOT": "slot_cb",
    "DT": "dt", "NT": "nt",
}

# Roles whose knock-on effects should be cancelled when the player is a backup.
KNOCK_ON_ROLES = {"LT", "OT", "cb1", "elite_cb", "slot_cb", "dt", "nt"}


def index_for_week(rows: list[dict], week: int) -> dict[tuple[str, str], tuple[str, int]]:
    """(team, normalized name) -> (depth_position, depth rank). Keeps the
    best (lowest) rank seen, since players appear in multiple formations."""
    idx: dict[tuple[str, str], tuple[str, int]] = {}
    for r in rows:
        if _s(r, "week") != str(week):
            continue
        team = _s(r, "club_code", "team")
        name = _s(r, "full_name", "player_name", "player_display_name")
        if not team or not name:
            continue
        dp = _s(r, "depth_position", "position").upper()
        rank = int(_f(r, "depth_team", "depth", default=99))
        key = (team, normalize_name(name))
        if key not in idx or rank < idx[key][1]:
            idx[key] = (dp, rank)
    return idx


@dataclass
class RefineResult:
    refined: int = 0
    demoted: int = 0
    details: list[str] = field(default_factory=list)


def refine_injury_roles(injuries: list[Injury], rows: list[dict],
                        week: int) -> RefineResult:
    """Mutate injuries in place: refine starter roles from depth position, and
    demote backups so their absence no longer triggers knock-on effects."""
    idx = index_for_week(rows, week)
    res = RefineResult()
    for inj in injuries:
        hit = idx.get((inj.team, normalize_name(inj.player)))
        if not hit:
            continue
        dp, rank = hit
        if rank > 1:
            if inj.role in KNOCK_ON_ROLES:
                res.demoted += 1
                res.details.append(f"{inj.player}: depth {rank} {dp} — backup, no knock-on")
                inj.role = "depth_" + inj.role
            continue
        new = ROLE_BY_DEPTH_POS.get(dp)
        if new and new != inj.role:
            res.details.append(f"{inj.player}: starter {dp} → {new}")
            inj.role = new
            res.refined += 1
    return res
