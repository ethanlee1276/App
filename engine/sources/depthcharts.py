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

from .fetch import (fetch_csv, fetch_text, load_local_csv, CACHE_DIR,
                    DataUnavailable, release_unavailable)
from .nflverse import _s, _f
from .oddsapi import normalize_name
from ..models import Injury


def _urls(season: int) -> list[str]:
    base = "https://github.com/nflverse/nflverse-data/releases/download"
    return [
        f"{base}/depth_charts/depth_charts_{season}.csv",
        f"{base}/depth_charts/depth_charts_{season}.csv.gz",
    ]


#: The columns the consumers of a depth row actually read — every
#: `_s(r, ...)` / `_f(r, ...)` key in this module, both schemas. A row
#: kept with only these is indistinguishable to them from the full row.
KEEP_COLUMNS = ("dt", "week", "team", "club_code",
                "player_name", "full_name", "player_display_name",
                "depth_position", "position", "pos_abb",
                "depth_team", "depth", "pos_rank")

#: How far back from the newest snapshot the date-keyed schema is kept.
#: The furthest any reader looks is `qb1_map(week - 1, back_days=7)`;
#: three weeks is that with room, against a season file that holds six
#: months of daily snapshots nobody reads.
KEEP_DAYS = 21


def _slim(open_rows, keep_days: int | None) -> list[dict]:
    """Two passes over a CSV opened by ``open_rows()`` (a callable
    returning a fresh file-like), keeping the columns this module reads
    and, on the date-keyed schema, only the newest ``keep_days``."""
    import csv
    import datetime as _dt
    with open_rows() as fh:
        fields = csv.DictReader(fh).fieldnames or []
    fields = [f.lstrip("\ufeff") for f in fields]
    keep = [c for c in KEEP_COLUMNS if c in fields]
    cutoff = None
    if "dt" in fields and "week" not in fields and keep_days:
        latest = ""
        with open_rows() as fh:
            for row in csv.DictReader(fh):
                d = (row.get("dt") or "")[:10]
                if d > latest:
                    latest = d
        try:
            cutoff = (_dt.date.fromisoformat(latest)
                      - _dt.timedelta(days=int(keep_days))).isoformat()
        except ValueError:
            cutoff = None
    out = []
    with open_rows() as fh:
        for row in csv.DictReader(fh):
            if cutoff and (row.get("dt") or "")[:10] < cutoff:
                continue
            out.append({c: row.get(c) for c in keep})
    return out


def slim_rows(text: str, keep_days: int | None = KEEP_DAYS) -> list[dict]:
    """`_slim` over a CSV held as text — the test seam, and small files."""
    import io
    text = text.lstrip("\ufeff")
    return _slim(lambda: io.StringIO(text), keep_days)


def load_depth_charts(season: int, keep_days: int | None = KEEP_DAYS) -> list[dict]:
    """The season's depth charts, slimmed to what this module reads.

    WHY THIS IS NOT `fetch_csv`. The 2026 file is 492,320 rows — a
    snapshot of every team's every position group, every day since
    March — and `csv.DictReader` into a list turned its 47 MB into about
    550 MB of Python dicts, held for the length of the build for the
    sake of one day's rows and six columns. Measured 2026-09-02 while
    chasing the memory ceiling that was killing builds on the droplet:
    the NFL build peaked at 780 MB and this load was 500 MB of it.

    So the fetch only refreshes the cache file (`fetch_text`'s TTL and
    stale-fallback rules are unchanged — a depth chart cached in August
    must not name August's starters in November), its returned text is
    dropped on the spot, and the rows are STREAMED off the cache file
    twice: once to find the newest snapshot, once to keep the rows that
    matter, slimmed. Holding the text and two StringIO copies of it was
    itself a 490 MB spike (StringIO keeps four bytes a character).
    """
    local = CACHE_DIR / f"depth_charts_{season}.csv"
    last_err = None
    for url in _urls(season):
        try:
            # The module-level name, so the freshness suite can spy on it:
            # every depth-chart read asks the fetch layer, never exists().
            fetch_text(url, local.name)         # refresh the cache; drop the text
            return _slim(lambda: open(local, encoding="utf-8", newline=""),
                         keep_days)
        except DataUnavailable as exc:
            last_err = exc
        except OSError as exc:
            last_err = DataUnavailable(str(exc))
    raise release_unavailable(
        "depth charts", season, local,
        f"nfl.import_depth_charts([{season}]).to_csv('{local}', index=False)",
        _urls(season), last_err)


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


# TWO SCHEMAS, ONE READER. nflverse's depth-chart release changed shape:
# the legacy file was keyed by `week` and spoke `club_code / full_name /
# depth_position / depth_team`; the current file (the 2025 and 2026
# releases both) is keyed by a snapshot date `dt` and speaks `team /
# player_name / pos_abb / pos_rank`. This adapter read only the legacy
# names, so for every 2025 and 2026 chart it returned NOTHING — and the
# QB-dependency watch and the knock-on role refinement that ride
# `--depth` were silently off (NFL readiness audit, 2026-09-02: 0 rows
# for 2026 week 1 AND for 2025 week 18). Both spellings are read now.
#
# For the date-keyed file "week N" cannot be resolved without a schedule,
# so the LATEST snapshot answers for the current week and the snapshot at
# least `back_days` earlier answers for the week before — the only two
# questions asked of it.
def _week_rows(rows: list[dict], week: int, back_days: int = 0) -> list[dict]:
    if rows and "week" in rows[0]:
        return [r for r in rows if _s(r, "week") == str(week)]
    dates = sorted({_s(r, "dt")[:10] for r in rows if _s(r, "dt")})
    if not dates:
        return []
    latest = dates[-1]
    if back_days:
        import datetime as _dt
        try:
            cutoff = (_dt.date.fromisoformat(latest)
                      - _dt.timedelta(days=back_days)).isoformat()
        except ValueError:
            return []
        older = [d for d in dates if d <= cutoff]
        if not older:
            return []
        latest = older[-1]
    return [r for r in rows if _s(r, "dt")[:10] == latest]


def _position(r: dict) -> str:
    return _s(r, "depth_position", "position", "pos_abb").upper()


def _rank(r: dict) -> int:
    return int(_f(r, "depth_team", "depth", "pos_rank", default=99))


def index_for_week(rows: list[dict], week: int) -> dict[tuple[str, str], tuple[str, int]]:
    """(team, normalized name) -> (depth_position, depth rank). Keeps the
    best (lowest) rank seen, since players appear in multiple formations."""
    idx: dict[tuple[str, str], tuple[str, int]] = {}
    for r in _week_rows(rows, week):
        team = _s(r, "club_code", "team")
        name = _s(r, "full_name", "player_name", "player_display_name")
        if not team or not name:
            continue
        dp = _position(r)
        rank = _rank(r)
        key = (team, normalize_name(name))
        if key not in idx or rank < idx[key][1]:
            idx[key] = (dp, rank)
    return idx


def qb1_map(rows: list[dict], week: int, back_days: int = 0) -> dict[str, str]:
    """team -> that week's top-of-chart QB (lowest depth rank wins).

    ``back_days`` only matters for the date-keyed schema: the snapshot at
    least that many days before the latest one, for a week-over-week
    comparison."""
    best: dict[str, tuple[int, str]] = {}
    for r in _week_rows(rows, week, back_days):
        if _position(r) != "QB":
            continue
        team = _s(r, "club_code", "team")
        name = _s(r, "full_name", "player_name", "player_display_name")
        if not team or not name:
            continue
        rank = _rank(r)
        if team not in best or rank < best[team][0]:
            best[team] = (rank, name)
    return {t: n for t, (_rk, n) in best.items()}


# Designations that make the passing game's anchor unreliable — the injury
# engine's own concern set plus the ruled-out tier.
QB_CONCERN = {"QUESTIONABLE", "DOUBTFUL", "GTD", "OUT", "IR"}


def qb_dependency(rows: list[dict], week: int,
                  injuries: list[Injury]) -> dict[str, str]:
    """team -> one-line warning when the passing game's anchor is shaky.

    Fires on (a) a week-over-week QB1 change on the depth chart — a new
    starter reshuffles the whole target tree, and every pass-catcher's
    logs were earned under the old one — and (b) a concern-or-worse
    designation on this week's QB1. A warning, never a gate: the injury
    engine already blocks the QB's OWN props; this is the knock-on
    honesty for everyone whose stat line rides on his arm. When both
    fire, the injury wins the sentence — it is the sharper fact.
    """
    now = qb1_map(rows, week)
    prev = qb1_map(rows, week - 1, back_days=7) if week > 1 else {}
    status_of = {(i.team, normalize_name(i.player)): i.status
                 for i in injuries or []}
    notes: dict[str, str] = {}
    for team, qb in now.items():
        old = prev.get(team)
        if old and normalize_name(old) != normalize_name(qb):
            notes[team] = (f"QB dependency: {qb} takes over at QB1 (was "
                           f"{old}) — the target tree was earned under a "
                           f"different arm")
        status = status_of.get((team, normalize_name(qb)))
        if status in QB_CONCERN:
            notes[team] = (f"QB dependency: QB1 {qb} is {status} — every "
                           f"pass-catcher number here rides on his "
                           f"availability")
    return notes


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
