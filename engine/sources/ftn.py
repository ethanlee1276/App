"""FTN's play charting, free by way of nflverse — what every play looked like.

Ethan, 2026-09-28: "what else can we add that's free". engine/defensevs
called FTN "paid charting"; the full product is, but nflverse publishes
FTN's per-play charting for every season from 2022 on, this one included
(`ftn_charting_{season}.csv`, weekly, a week or so behind the games):

    n_blitzers, n_pass_rushers       who came — blitz rate is arithmetic
    n_defense_box                    the box count on the snap
    is_play_action, is_rpo,          what the offence showed
    is_motion, is_screen_pass,
    is_no_huddle, is_qb_out_of_pocket
    is_catchable_ball, is_drop,      what the throw was and what the
    is_contested_ball,               receiver did with it
    is_created_reception
    is_interception_worthy,          what the quarterback did
    is_throw_away, is_qb_fault_sack

WHY IT MATTERS NOW. The participation file (man or zone, the coverage
shell — engine/sources/nflpart) ends with 2025: there is no 2026 file, so
the scan's "How it covers" line runs a season behind. This file is
current, so this season's blitz rate and box counts come from here.

THE JOIN. Every FTN row carries nflverse's game and play id, and the
play-by-play (engine/sources/nflpbp, cached per season) says who threw,
who was targeted, who ran, and which side had the ball — 47,316 of
47,316 plays matched on 2025. Players are keyed the play-by-play's way
("J.Chase", by team), the same key the scan's receiver splits use, and
by their gsis id for the fit harness.

NOTHING HERE MOVES A NUMBER on its own. chartfit.py is the information
test each of these has to pass first; the tables below are what the scan
shows and what the harness reads.
"""

from __future__ import annotations

from collections import defaultdict

from .fetch import fetch_csv

BASE = "https://github.com/nflverse/nflverse-data/releases/download/ftn_charting"
FIRST_SEASON = 2022
REG_WEEKS = 18
#: Five or more pass rushers is the blitz every charting service counts.
BLITZ_RUSHERS = 5
HEAVY_BOX, LIGHT_BOX = 8, 6

PBP_COLS = ("game_id", "play_id", "week", "posteam", "defteam", "play_type", "pass_attempt",
            "rush_attempt", "qb_dropback", "qb_scramble", "sack", "interception", "complete_pass",
            "passer_player_id", "passer_player_name", "receiver_player_id", "receiver_player_name",
            "rusher_player_id", "rusher_player_name")


def _flag(v) -> bool:
    return str(v or "").strip().upper() == "TRUE"


def _n(v, default=None):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def fetch(season: int, ttl: int = 6 * 3600) -> list[dict]:
    """A season's charted plays, regular season only, [] when nflverse has
    no file for it (before FIRST_SEASON, or a season not yet played)."""
    if int(season) < FIRST_SEASON:
        return []
    try:
        rows = fetch_csv(f"{BASE}/ftn_charting_{season}.csv", f"ftn_charting_{season}.csv", ttl=ttl)
    except Exception:                                        # noqa: BLE001
        return []
    return [r for r in rows if 0 < (_n(r.get("week"), 0) or 0) <= REG_WEEKS]


def joined(season: int, ttl: int = 6 * 3600, charted=None, plays=None) -> list[dict]:
    """The charted plays with the play-by-play's who-and-which-side fields
    on each: one dict per play that both files carry. ``charted`` and
    ``plays`` are for tests; the season's files otherwise."""
    charted = fetch(season, ttl=ttl) if charted is None else charted
    if not charted:
        return []
    if plays is None:
        from .nflpbp import load_pbp_rows
        plays = load_pbp_rows(season, columns=PBP_COLS)
    by_key = {(r.get("nflverse_game_id") or "", str(_n(r.get("nflverse_play_id"), "") or "")): r
              for r in charted}
    out = []
    for p in plays:
        key = (p.get("game_id") or "", str(p.get("play_id") or "").split(".")[0])
        c = by_key.get(key)
        if c is None:
            continue
        row = dict(c)
        for k in PBP_COLS:
            row[k] = p.get(k, "")
        out.append(row)
    return out


def _is_dropback(r) -> bool:
    return _n(r.get("qb_dropback"), 0) == 1


def _is_attempt(r) -> bool:
    return _n(r.get("pass_attempt"), 0) == 1 and _n(r.get("sack"), 0) != 1


def _is_run(r) -> bool:
    return _n(r.get("rush_attempt"), 0) == 1 and _n(r.get("qb_scramble"), 0) != 1


def _weeks(acc: dict) -> dict:
    """{key: [(season, week, counts), …]} oldest first, from {(key, season, week): counts}."""
    out: dict = defaultdict(list)
    for (key, season, week), counts in sorted(acc.items(), key=lambda kv: (kv[0][1], kv[0][2])):
        out[key].append((season, week, dict(counts)))
    return dict(out)


def qb_weeks(rows, season: int) -> dict:
    """Per passer (gsis id) per week: dropbacks, attempts, interception-worthy
    throws, throwaways, catchable balls, plays out of the pocket, sacks the
    charting blamed on him, play-action dropbacks."""
    acc: dict = defaultdict(lambda: defaultdict(int))
    for r in rows:
        pid = r.get("passer_player_id") or ""
        if not pid or not _is_dropback(r):
            continue
        a = acc[(pid, season, _n(r.get("week"), 0))]
        a["dropbacks"] += 1
        a["oop"] += _flag(r.get("is_qb_out_of_pocket"))
        a["fault_sacks"] += _flag(r.get("is_qb_fault_sack"))
        a["play_action"] += _flag(r.get("is_play_action"))
        if _is_attempt(r):
            a["attempts"] += 1
            a["iw"] += _flag(r.get("is_interception_worthy"))
            a["throwaways"] += _flag(r.get("is_throw_away"))
            a["catchable"] += _flag(r.get("is_catchable_ball"))
        a["name"] = r.get("passer_player_name") or ""
        a["team"] = r.get("posteam") or ""
    return _weeks(acc)


def receiver_weeks(rows, season: int) -> dict:
    """Per targeted receiver (gsis id) per week: targets, catchable balls,
    drops, contested targets, created receptions."""
    acc: dict = defaultdict(lambda: defaultdict(int))
    for r in rows:
        pid = r.get("receiver_player_id") or ""
        if not pid or not _is_attempt(r):
            continue
        a = acc[(pid, season, _n(r.get("week"), 0))]
        a["targets"] += 1
        a["catchable"] += _flag(r.get("is_catchable_ball"))
        a["drops"] += _flag(r.get("is_drop"))
        a["contested"] += _flag(r.get("is_contested_ball"))
        a["created"] += _flag(r.get("is_created_reception"))
        a["name"] = r.get("receiver_player_name") or ""
        a["team"] = r.get("posteam") or ""
    return _weeks(acc)


def defense_weeks(rows, season: int) -> dict:
    """Per defence per week: dropbacks faced, blitzes (five or more rushers),
    snaps with a blitzer, runs faced, heavy boxes (8+) and light boxes (6-)
    on those runs."""
    acc: dict = defaultdict(lambda: defaultdict(int))
    for r in rows:
        team = r.get("defteam") or ""
        if not team:
            continue
        a = acc[(team, season, _n(r.get("week"), 0))]
        if _is_dropback(r):
            a["dropbacks"] += 1
            a["blitz"] += (_n(r.get("n_pass_rushers"), 0) or 0) >= BLITZ_RUSHERS
            a["blitzers"] += (_n(r.get("n_blitzers"), 0) or 0) >= 1
        if _is_run(r):
            box = _n(r.get("n_defense_box"))
            if box is not None:
                a["runs"] += 1
                a["heavy_box"] += box >= HEAVY_BOX
                a["light_box"] += box <= LIGHT_BOX
    return _weeks(acc)


def offense_weeks(rows, season: int) -> dict:
    """Per offence per week: plays, dropbacks, play-action dropbacks, RPOs,
    motion, screens, no-huddle snaps."""
    acc: dict = defaultdict(lambda: defaultdict(int))
    for r in rows:
        team = r.get("posteam") or ""
        if not team or not (_is_dropback(r) or _is_run(r)):
            continue
        a = acc[(team, season, _n(r.get("week"), 0))]
        a["plays"] += 1
        a["motion"] += _flag(r.get("is_motion"))
        a["rpo"] += _flag(r.get("is_rpo"))
        a["no_huddle"] += _flag(r.get("is_no_huddle"))
        if _is_dropback(r):
            a["dropbacks"] += 1
            a["play_action"] += _flag(r.get("is_play_action"))
            a["screen"] += _flag(r.get("is_screen_pass"))
            if _is_attempt(r):
                # Whoever threw: the offence's accuracy, for the men catching.
                a["attempts"] += 1
                a["catchable"] += _flag(r.get("is_catchable_ball"))
                a["iw"] += _flag(r.get("is_interception_worthy"))
    return _weeks(acc)


def rate_prior(history, season: int, week: int, num: str, den: str, n: int = 6,
               min_den: int = 1) -> float | None:
    """``num / den`` pooled over the last ``n`` charted weeks before
    (season, week) — None until ``den`` reaches ``min_den``. Pooled, not
    averaged: a week of two targets should not weigh as much as a week
    of twelve."""
    before = [c for s, w, c in history if (s, w) < (int(season), int(week))][-n:]
    d = sum(c.get(den, 0) for c in before)
    if d < min_den or len(before) < 1:
        return None
    return sum(c.get(num, 0) for c in before) / d


#: The season-to-date shares the scan shows, (numerator, denominator) each.
DEFENSE_SHARES = {"blitz": ("blitz", "dropbacks"), "blitzers": ("blitzers", "dropbacks"),
                  "heavy_box": ("heavy_box", "runs"), "light_box": ("light_box", "runs")}
OFFENSE_SHARES = {"play_action": ("play_action", "dropbacks"), "screen": ("screen", "dropbacks"),
                  "motion": ("motion", "plays"), "rpo": ("rpo", "plays"),
                  "no_huddle": ("no_huddle", "plays")}
QB_SHARES = {"iw": ("iw", "attempts"), "catchable": ("catchable", "attempts"),
             "throwaways": ("throwaways", "attempts"), "oop": ("oop", "dropbacks"),
             "fault_sacks": ("fault_sacks", "dropbacks"), "play_action": ("play_action", "dropbacks")}
RECEIVER_SHARES = {"drops": ("drops", "catchable"), "catchable": ("catchable", "targets"),
                   "contested": ("contested", "targets"), "created": ("created", "targets")}
MIN_DROPBACKS, MIN_RUNS, MIN_ATTEMPTS, MIN_TARGETS = 40, 30, 30, 8
#: A full NFL week charts about 2,600 plays; under this many it is still in progress.
FULL_WEEK_PLAYS = 1200


def _sum_shares(weeks: list, shares: dict, before_week=None) -> dict:
    tot: dict = defaultdict(int)
    name = team = ""
    n_weeks = 0
    for _s, w, c in weeks:
        if before_week is not None and w >= int(before_week):
            continue
        n_weeks += 1
        for k, v in c.items():
            if isinstance(v, int):
                tot[k] += v
        name, team = c.get("name") or name, c.get("team") or team
    out = {k: int(v) for k, v in tot.items()}
    # The counts keep their names; each share is ``<name>_rate``.
    for key, (num, den) in shares.items():
        out[f"{key}_rate"] = round(tot[num] / tot[den], 3) if tot[den] else None
    out["weeks"] = n_weeks
    if name:
        out["name"] = name
    if team:
        out["team"] = team
    return out


def season_tables(season: int, before_week=None, rows=None) -> dict:
    """The season to date: ``{"season", "weeks", "partial", "defense":
    {team: …}, "offense": {team: …}, "qbs": {(team, "P.Mahomes"): …},
    "receivers": {(team, "J.Chase"): …}}`` — every count by its name
    ("blitz": 26) and every share as ``<name>_rate`` ("blitz_rate":
    0.388). Players keyed the play-by-play's way, by team, as the scan's
    receiver splits are. Empty tables when nflverse has no file yet."""
    rows = joined(season) if rows is None else rows
    out = {"season": int(season), "weeks": 0, "partial": None,
           "defense": {}, "offense": {}, "qbs": {}, "receivers": {}}
    if not rows:
        return out
    # A week is charted when most of its plays are; the one FTN is still
    # working through is named as partial, and its plays still count.
    per_week: dict = defaultdict(int)
    for r in rows:
        w = _n(r.get("week"), 0) or 0
        if before_week is None or w < int(before_week):
            per_week[w] += 1
    out["weeks"] = sum(1 for n in per_week.values() if n >= FULL_WEEK_PLAYS)
    partial = [w for w, n in per_week.items() if n < FULL_WEEK_PLAYS]
    out["partial"] = max(partial) if partial else None
    for team, weeks in defense_weeks(rows, season).items():
        t = _sum_shares(weeks, DEFENSE_SHARES, before_week)
        if t.get("dropbacks", 0) >= MIN_DROPBACKS or t.get("runs", 0) >= MIN_RUNS:
            out["defense"][team] = t
    for team, weeks in offense_weeks(rows, season).items():
        t = _sum_shares(weeks, OFFENSE_SHARES, before_week)
        if t.get("dropbacks", 0) >= MIN_DROPBACKS:
            out["offense"][team] = t
    for _pid, weeks in qb_weeks(rows, season).items():
        t = _sum_shares(weeks, QB_SHARES, before_week)
        if t.get("attempts", 0) >= MIN_ATTEMPTS and t.get("name"):
            out["qbs"][(t["team"], t["name"])] = t
    for _pid, weeks in receiver_weeks(rows, season).items():
        t = _sum_shares(weeks, RECEIVER_SHARES, before_week)
        if t.get("targets", 0) >= MIN_TARGETS and t.get("name"):
            out["receivers"][(t["team"], t["name"])] = t
    return out
