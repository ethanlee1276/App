"""Play-level participation: formation, personnel, box count, and COVERAGE.

    https://github.com/nflverse/nflverse-data/releases/download/
        pbp_participation/pbp_participation_{season}.csv

NFL_MODEL §6 parked two rows behind "no data exists":

    | §6 Alignment-level matchups | 📋 | Needs coverage/alignment data … |
    | §6 Coordinator profiles     | 📋 | No tendency feed …             |

**Both claims were wrong, and this file is the measurement that settles
it.** Probed 2026-08-09: the release answers 200 for every season from
2016 through 2025 — 49.7 MB for 2024, 49.1 MB for 2025, so it did not stop
in 2022 as the parked note assumed. Its columns are exactly what §6 says
we do not have:

    offense_formation        SHOTGUN / SINGLEBACK / EMPTY / I_FORM …
    offense_personnel        "1 RB, 1 TE, 3 WR"
    defenders_in_box         the box count
    number_of_pass_rushers   rushers, so blitz rate is arithmetic
    defense_man_zone_type    MAN_COVERAGE / ZONE_COVERAGE
    defense_coverage_type    COVER_0 … COVER_6
    was_pressure, time_to_throw, route, ngs_air_yards

Measured on 2022: 50,150 plays, of which 18,975 (37.8%) carry a coverage
label. That is not a gap — coverage is classified on DROPBACKS, and
dropbacks are about that share of snaps. A parser that treated the blank
rows as missing data would report the feed as two-thirds broken; the rate
below is over LABELLED plays for that reason.

WHAT THIS IS NOT. It is not a coordinator feed. Who called the plays is
still not in any free source — see `engine/reset.py`, which uses head coach
as an honest proxy and says so. What this gives is the TENDENCY, per team,
which is the thing a coordinator profile was wanted for: a defence that
plays 71% zone is a different matchup from one that plays 45%, whoever is
calling it.

NOTHING HERE PRICES ANYTHING YET. `docs/THE_INFORMATION_TEST.md`: the
claimed edge measures AUC 0.479, so a new input into the pricing path is
the exact move that finding rules out. This lands as a probe and a
measurable tendency; whether it earns a place in a grade is a question for
`stakecheck --info`, not for enthusiasm about a new feed.
"""

from __future__ import annotations

from .fetch import CACHE_DIR, DataUnavailable, fetch_csv, load_local_csv

BASE = ("https://github.com/nflverse/nflverse-data/releases/download/"
        "pbp_participation")

#: A season's file is ~49 MB, which is why this is never fetched inside a
#: board build. It is a season aggregate: pull it once, keep it on disk.
def _urls(season: int) -> list[str]:
    return [f"{BASE}/pbp_participation_{season}.csv",
            f"{BASE}/pbp_participation_{season}.csv.gz"]


def load_participation(season: int) -> list[dict]:
    """One row per play for a season, cached on disk after the first pull."""
    local = CACHE_DIR / f"pbp_participation_{season}.csv"
    if local.exists():
        return load_local_csv(local)
    last_err = None
    for url in _urls(season):
        try:
            return fetch_csv(url, f"pbp_participation_{season}.csv")
        except DataUnavailable as exc:
            last_err = exc
    raise last_err or DataUnavailable(
        f"participation {season} unavailable — nflverse publishes it from "
        f"2016; a season still being played appears week by week")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _game_teams(row) -> set:
    """The two team codes in an nflverse game id (`2022_01_BUF_LA`)."""
    parts = str(row.get("nflverse_game_id") or "").split("_")
    return set(parts[2:4]) if len(parts) >= 4 else set()


def _defends(row, team: str) -> bool:
    """Was `team` the defence on this play — in this game, without the ball."""
    return (team in _game_teams(row)
            and (row.get("possession_team") or "").strip() != team)


def coverage_rates(rows, team: str | None = None) -> dict:
    """How a DEFENCE plays: man/zone split, blitz rate, average box.

    `team` is the team on DEFENCE, and this feed makes that awkward: the
    only team column is `possession_team`, the OFFENCE. Nothing names the
    defenders.

    THE FIRST CUT OF THIS WAS WRONG IN A WAY THAT LOOKED RIGHT. It took
    every play where the named team did not have the ball — which is every
    other game in the league as well, so SF, NE and BAL all came back at
    28.6% man, 71.3% zone, 6.36 in the box. Three teams reading the league
    average to three decimals is the tell; a rate that plausible is how a
    filter bug survives review.

    The game id carries both team codes (`2022_01_BUF_LA`), so a play is
    DEFENDED by a team when it appears in that id and does not have the
    ball. That is the whole fix, and it needs the season's rows rather
    than a pre-filtered slice.

    RATES ARE OVER LABELLED PLAYS, NOT OVER ALL PLAYS. Coverage is
    classified on dropbacks only, so 62% of a season's rows carry no label
    at all; dividing by every play would report every defence as playing
    zone a third of the time and man a tenth, which is a statement about
    run-pass balance wearing a coverage label.
    """
    man = zone = 0
    rush_sum, rush_n = 0.0, 0
    box_sum, box_n = 0.0, 0
    blitz = drop = 0
    for r in rows:
        if team is not None and not _defends(r, team):
            continue
        mz = (r.get("defense_man_zone_type") or "").upper()
        if mz == "MAN_COVERAGE":
            man += 1
        elif mz == "ZONE_COVERAGE":
            zone += 1
        box = _num(r.get("defenders_in_box"))
        if box is not None:
            box_sum += box
            box_n += 1
        rushers = _num(r.get("number_of_pass_rushers"))
        if rushers is not None and rushers > 0:
            rush_sum += rushers
            rush_n += 1
            drop += 1
            # Five or more rushers is the standard definition of a blitz:
            # anything beyond the four-man front the offence expects.
            if rushers >= 5:
                blitz += 1
    labelled = man + zone
    return {
        "n_labelled": labelled,
        "man_rate": round(man / labelled, 4) if labelled else None,
        "zone_rate": round(zone / labelled, 4) if labelled else None,
        "blitz_rate": round(blitz / drop, 4) if drop else None,
        "rushers_avg": round(rush_sum / rush_n, 2) if rush_n else None,
        "box_avg": round(box_sum / box_n, 2) if box_n else None,
        "n_dropbacks": drop,
    }


def formation_rates(rows, team: str | None = None) -> dict:
    """How an OFFENCE lines up: share of snaps by formation, biggest first.

    Here `team` IS `possession_team`, the opposite of `coverage_rates`.
    The two read the same file from opposite sides, which is worth stating
    plainly because passing the same team to both and comparing the
    numbers is a mistake that produces plausible nonsense.
    """
    counts: dict = {}
    n = 0
    for r in rows:
        if team is not None and (r.get("possession_team") or "") != team:
            continue
        f = (r.get("offense_formation") or "").strip().upper()
        if not f:
            continue
        counts[f] = counts.get(f, 0) + 1
        n += 1
    return {"n": n,
            "rates": {k: round(v / n, 4)
                      for k, v in sorted(counts.items(),
                                         key=lambda kv: -kv[1])} if n else {}}


def personnel_rates(rows, team: str | None = None) -> dict:
    """Share of offensive snaps by personnel grouping ("1 RB, 1 TE, 3 WR")."""
    counts: dict = {}
    n = 0
    for r in rows:
        if team is not None and (r.get("possession_team") or "") != team:
            continue
        p = (r.get("offense_personnel") or "").strip()
        if not p:
            continue
        counts[p] = counts.get(p, 0) + 1
        n += 1
    return {"n": n,
            "rates": {k: round(v / n, 4)
                      for k, v in sorted(counts.items(),
                                         key=lambda kv: -kv[1])[:8]} if n
            else {}}


def teams_in(rows) -> list[str]:
    """Every team appearing as the offence, so a probe can list what it has."""
    return sorted({(r.get("possession_team") or "").strip()
                   for r in rows} - {""})
