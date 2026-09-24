"""Who covers, how, and how well — the defender-level half of the scan.

Two free nflverse releases the site had not read:

* **PFR advanced defense** (`pfr_advstats/advstats_week_def_<season>`),
  per defender per game: targets, completions, yards and touchdowns
  allowed, passer rating allowed, missed tackles, pressures, sacks. It is
  the free cousin of the coverage grades the Falcons @ Packers breakdown
  quoted ("Nixon: 10 receptions allowed, 69.7 passer rating allowed").
  Published within the week.
* **Participation** (`pbp_participation/pbp_participation_<season>`),
  per play: man or zone, the coverage shell (Cover 1, 2, 3, 4, 6, 2-man,
  0, 9), pass rushers sent, and whether the quarterback was pressured.
  nflverse publishes it a season behind, so this season's scheme reads
  come from last season's file until the current one appears — and the
  page says which season it is.

Standard library only; every loader degrades to empty on a failed fetch.
"""

from __future__ import annotations

import csv
import io

from .fetch import DataUnavailable, fetch_text

_BASE = "https://github.com/nflverse/nflverse-data/releases/download"

#: The shells that leave the middle of the field open (two high safeties
#: or none) — the breakdown's "MOFO". Cover 1 and Cover 3 close it.
MOFO_SHELLS = {"COVER_0", "COVER_2", "2_MAN", "COVER_4", "COVER_6"}
MOFC_SHELLS = {"COVER_1", "COVER_3"}


def _f(v, default=0.0):
    try:
        if v in (None, "", "NA"):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _csv(url: str, cache: str, ttl: int) -> list[dict]:
    try:
        text = fetch_text(url, cache, ttl=ttl, timeout=120)
    except DataUnavailable:
        return []
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def load_pfr_def(season: int, ttl: int = 12 * 3600) -> list[dict]:
    return _csv(f"{_BASE}/pfr_advstats/advstats_week_def_{season}.csv",
                f"pfr_def_{season}.csv", ttl)


def load_pfr_rush(season: int, ttl: int = 12 * 3600) -> list[dict]:
    return _csv(f"{_BASE}/pfr_advstats/advstats_week_rush_{season}.csv",
                f"pfr_rush_{season}.csv", ttl)


def load_participation(season: int, ttl: int = 7 * 24 * 3600) -> list[dict]:
    return _csv(f"{_BASE}/pbp_participation/pbp_participation_{season}.csv",
                f"pbp_participation_{season}.csv", ttl)


def passer_rating(att: float, cmp: float, yds: float, td: float, ints: float) -> float | None:
    """The NFL passer rating on the throws a defender was targeted on —
    computed from the season's sums, not averaged from game ratings."""
    if att <= 0:
        return None
    clip = lambda x: max(0.0, min(2.375, x))              # noqa: E731
    a = clip((cmp / att - 0.3) * 5)
    b = clip((yds / att - 3) * 0.25)
    c = clip(td / att * 20)
    d = clip(2.375 - ints / att * 25)
    return round((a + b + c + d) / 6 * 100, 1)


def defenders(rows: list[dict]) -> dict:
    """{(team, name_key): season sums and rates} from PFR's weekly rows.
    Keyed by the team he played for; `name_key` is the loose form the
    depth chart is joined on."""
    out: dict = {}
    for r in rows:
        if (r.get("game_type") or "REG") != "REG":
            continue
        key = (r.get("team") or "", name_key(r.get("pfr_player_name") or ""))
        c = out.setdefault(key, {"name": r.get("pfr_player_name") or "", "games": 0,
                                 "targets": 0.0, "cmp": 0.0, "yds": 0.0, "td": 0.0, "ints": 0.0,
                                 "tackles": 0.0, "missed": 0.0, "pressures": 0.0, "sacks": 0.0})
        c["games"] += 1
        c["targets"] += _f(r.get("def_targets"))
        c["cmp"] += _f(r.get("def_completions_allowed"))
        c["yds"] += _f(r.get("def_yards_allowed"))
        c["td"] += _f(r.get("def_receiving_td_allowed"))
        c["ints"] += _f(r.get("def_ints"))
        c["tackles"] += _f(r.get("def_tackles_combined"))
        c["missed"] += _f(r.get("def_missed_tackles"))
        c["pressures"] += _f(r.get("def_pressures"))
        c["sacks"] += _f(r.get("def_sacks"))
    for c in out.values():
        t = c["targets"]
        c["yds_per_tgt"] = round(c["yds"] / t, 1) if t else None
        c["rating"] = passer_rating(t, c["cmp"], c["yds"], c["td"], c["ints"])
    return out


def team_tackling(rows: list[dict]) -> dict:
    """{team: missed-tackle rate} — missed over attempted, the whole defence."""
    acc: dict = {}
    for r in rows:
        if (r.get("game_type") or "REG") != "REG":
            continue
        a = acc.setdefault(r.get("team") or "", [0.0, 0.0])
        a[0] += _f(r.get("def_missed_tackles"))
        a[1] += _f(r.get("def_tackles_combined")) + _f(r.get("def_missed_tackles"))
    return {t: round(m / n, 3) for t, (m, n) in acc.items() if n >= 20}


def _defense_of(game_id: str, offense: str) -> str:
    """nflverse game ids read SEASON_WEEK_AWAY_HOME."""
    parts = (game_id or "").split("_")
    if len(parts) < 4:
        return ""
    away, home = parts[2], parts[3]
    return home if offense == away else away if offense == home else ""


def scheme(rows: list[dict]) -> dict:
    """{defense: {"dropbacks", "man", "zone", "mofo", "mofc", "blitz",
    "pressure", "shells": {shell: share}}} — shares of that defence's
    charted dropbacks."""
    acc: dict = {}
    for r in rows:
        dfn = _defense_of(r.get("nflverse_game_id") or "", r.get("possession_team") or "")
        mz = r.get("defense_man_zone_type") or ""
        if not dfn or not mz:
            continue
        a = acc.setdefault(dfn, {"n": 0, "man": 0, "zone": 0, "mofo": 0, "mofc": 0,
                                 "blitz": 0, "pressure": 0, "shells": {}})
        a["n"] += 1
        a["man"] += mz == "MAN_COVERAGE"
        a["zone"] += mz == "ZONE_COVERAGE"
        shell = r.get("defense_coverage_type") or ""
        a["mofo"] += shell in MOFO_SHELLS
        a["mofc"] += shell in MOFC_SHELLS
        if shell:
            a["shells"][shell] = a["shells"].get(shell, 0) + 1
        a["blitz"] += _f(r.get("number_of_pass_rushers")) >= 5
        a["pressure"] += (r.get("was_pressure") or "").upper() == "TRUE"
    out = {}
    for team, a in acc.items():
        n = a["n"]
        if n < 50:
            continue
        out[team] = {"dropbacks": n,
                     **{k: round(a[k] / n, 3) for k in ("man", "zone", "mofo", "mofc", "blitz", "pressure")},
                     "shells": {s: round(c / n, 3) for s, c in
                                sorted(a["shells"].items(), key=lambda kv: -kv[1])[:4]}}
    return out


def receiver_splits(participation: list[dict], pbp_rows) -> dict:
    """{(team, receiver): {"man": [tgts, yds], "zone": [...], "mofo": [...],
    "mofc": [...]}} — how each receiver's targets went against each
    look. Joined on (game id, play id); ``pbp_rows`` needs game_id,
    play_id, posteam, receiver_player_name, yards_gained, complete_pass."""
    look: dict = {}
    for r in participation:
        mz = r.get("defense_man_zone_type") or ""
        if mz:
            look[(r.get("nflverse_game_id") or "", str(r.get("play_id") or ""))] = (
                mz, r.get("defense_coverage_type") or "")
    out: dict = {}
    for r in pbp_rows:
        rec = r.get("receiver_player_name") or ""
        if not rec:
            continue
        got = look.get((r.get("game_id") or "", str(r.get("play_id") or "").split(".")[0]))
        if not got:
            continue
        mz, shell = got
        yds = _f(r.get("yards_gained")) if _f(r.get("complete_pass")) == 1 else 0.0
        c = out.setdefault((r.get("posteam") or "", rec),
                           {"man": [0, 0.0], "zone": [0, 0.0], "mofo": [0, 0.0], "mofc": [0, 0.0]})
        for k in (("man" if mz == "MAN_COVERAGE" else "zone"),
                  ("mofo" if shell in MOFO_SHELLS else "mofc" if shell in MOFC_SHELLS else None)):
            if k:
                c[k][0] += 1
                c[k][1] += yds
    return out


def name_key(name: str) -> str:
    """Loose name for joining the depth chart to PFR and the play-by-play:
    lower case, letters only, suffixes dropped ("Jr.", "III")."""
    # Periods and apostrophes CLOSE UP rather than split: the injury
    # report writes "A.J. Terrell" where PFR writes "AJ Terrell", and the
    # two must be one man.
    raw = (name or "").lower().replace(".", "").replace("'", "").replace("’", "")
    parts = [p for p in "".join(ch if ch.isalpha() or ch == " " else " " for ch in raw).split()
             if p not in ("jr", "sr", "ii", "iii", "iv", "v")]
    return " ".join(parts)
