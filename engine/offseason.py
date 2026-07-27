"""Offseason intelligence — what changed since the season the stats came from.

Every number on the Fantasy page is computed from last season's games, and
between February and September the league quietly invalidates chunks of it:
players change teams, rookies arrive, coaches move. This module works out
what changed FROM DATA, not from anyone's memory of the news cycle:

* **Coaching changes** come from the nflverse schedule file itself. Every
  game row carries both head coaches, and the upcoming season's rows are
  stamped with each team's current staff — so "new coach" is literally a
  diff between a team's last game of last season and its first game of
  next season. No curated table to go stale.
* **Current rosters and rookies** come from Sleeper's public players feed,
  which the site already fetches for league sync. It carries every
  player's current team, depth-chart slot, and years of experience —
  trades and free-agency moves are baked into it, and rookies are simply
  ``years_exp == 0``.
* **Starting-QB changes** cross the two: last season's actual starter
  (the schedule stamps each game's QBs) against the current QB1 on
  Sleeper's depth chart.

Everything degrades gracefully: no Sleeper cache means no roster layer
(with a note saying so), never a crash and never stale claims presented
as current.
"""

from __future__ import annotations

import json
from pathlib import Path

from .sources.fetch import fetch_text, CACHE_DIR, DataUnavailable
from .fantasy import _short_key

FANTASY_POSITIONS = ("QB", "RB", "WR", "TE")
SLEEPER_PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
# Same cache file the site's Sleeper proxy writes — one daily download
# serves both.
SLEEPER_CACHE = "sleeper_players_nfl.json"

# Sleeper and nflverse disagree on a few abbreviations; stats/schedule side
# (nflverse) is canonical everywhere else in the engine.
_TEAM_ALIAS = {"LAR": "LA", "JAC": "JAX", "WSH": "WAS", "OAK": "LV",
               "SD": "LAC", "STL": "LA"}


def _canon_team(t: str | None) -> str:
    t = (t or "").upper()
    return _TEAM_ALIAS.get(t, t)


# --- schedule-derived: coaches ----------------------------------------------
def seasons_in(schedule_rows: list[dict]) -> tuple[int | None, int | None]:
    """(last completed season, upcoming season) present in the schedule.
    Completed = has at least one played game; upcoming = a later season
    that exists in the file (nflverse publishes the schedule in spring)."""
    played, all_seasons = set(), set()
    for r in schedule_rows:
        try:
            season = int(r.get("season") or 0)
        except ValueError:
            continue
        if not season:
            continue
        all_seasons.add(season)
        if (r.get("home_score") or "") != "":
            played.add(season)
    last = max(played) if played else None
    upcoming = min((s for s in all_seasons if last is None or s > last),
                   default=None)
    return last, upcoming


def _final_coaches(schedule_rows: list[dict], season: int) -> dict[str, str]:
    """Each team's coach in its LAST played game of ``season`` — the man
    who actually finished the year, so a midseason firing reads as the
    interim, which is the correct baseline for "is 2026 different"."""
    out: dict[str, str] = {}
    for r in sorted((r for r in schedule_rows
                     if str(r.get("season")) == str(season)
                     and (r.get("home_score") or "") != ""),
                    key=lambda r: r.get("gameday") or ""):
        if r.get("home_coach"):
            out[_canon_team(r.get("home_team"))] = r["home_coach"].strip()
        if r.get("away_coach"):
            out[_canon_team(r.get("away_team"))] = r["away_coach"].strip()
    return out


def _current_coaches(schedule_rows: list[dict], season: int) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in schedule_rows:
        if str(r.get("season")) != str(season):
            continue
        if r.get("home_coach"):
            out.setdefault(_canon_team(r.get("home_team")), r["home_coach"].strip())
        if r.get("away_coach"):
            out.setdefault(_canon_team(r.get("away_team")), r["away_coach"].strip())
    return out


def coach_changes(schedule_rows: list[dict]) -> list[dict]:
    """Teams whose upcoming-season coach differs from the one who finished
    last season. Pure data: both names come from the schedule file."""
    last, upcoming = seasons_in(schedule_rows)
    if last is None or upcoming is None:
        return []
    before = _final_coaches(schedule_rows, last)
    now = _current_coaches(schedule_rows, upcoming)
    out = []
    for team in sorted(now):
        a, b = before.get(team, ""), now[team]
        if a and b and a.lower() != b.lower():
            out.append({"team": team, "before": a, "now": b})
    return out


def _final_qbs(schedule_rows: list[dict], season: int) -> dict[str, str]:
    """Each team's most frequent starting QB over last season's final
    weeks — the schedule stamps the actual starter per game."""
    from collections import Counter
    starts: dict[str, Counter] = {}
    for r in schedule_rows:
        if str(r.get("season")) != str(season) or (r.get("home_score") or "") == "":
            continue
        for side in ("home", "away"):
            qb = (r.get(f"{side}_qb_name") or "").strip()
            if qb:
                starts.setdefault(_canon_team(r.get(f"{side}_team")), Counter())[qb] += 1
    return {t: c.most_common(1)[0][0] for t, c in starts.items() if c}


# --- Sleeper-derived: rosters, rookies, depth --------------------------------
def load_sleeper_players(max_age_s: int = 86400) -> dict | None:
    """The Sleeper players blob, cache-first (the proxy shares this file).
    None when unreachable — callers must treat that as "no roster layer",
    not as an empty league."""
    cached = Path(CACHE_DIR) / SLEEPER_CACHE
    try:
        body = fetch_text(SLEEPER_PLAYERS_URL, SLEEPER_CACHE, ttl=max_age_s)
        return json.loads(body)
    except (DataUnavailable, ValueError):
        try:
            return json.loads(cached.read_text())     # stale beats absent
        except Exception:
            return None


def index_players(blob: dict) -> dict:
    """Two-tier name index of fantasy-relevant players.

    The short key (first initial, last name) exists for abbreviated feeds
    ("P.Mahomes"), but on its own it is a trap: A.J. Brown and Amon-Ra
    St. Brown BOTH collapse to ("a", "brown"), both play WR, and the first
    live run of this module duly reported Amon-Ra following A.J. to New
    England. Both sides of THIS join carry full names, so the full
    normalized name is the primary key and the short key only a fallback.
    """
    from .sources.oddsapi import normalize_name
    idx: dict = {"full": {}, "short": {}}
    for p in (blob or {}).values():
        if not isinstance(p, dict):
            continue
        pos = (p.get("position") or "").upper()
        if pos not in FANTASY_POSITIONS:
            continue
        name = (p.get("full_name")
                or f"{p.get('first_name', '')} {p.get('last_name', '')}").strip()
        if not name:
            continue
        team = _canon_team(p.get("team"))
        rec = {
            "name": name, "team": team, "position": pos,
            "years_exp": p.get("years_exp"),
            "depth_pos": (p.get("depth_chart_position") or "").upper(),
            "depth_order": p.get("depth_chart_order"),
            "status": (p.get("status") or "").strip(),
            "active": bool(p.get("active", True)),
        }
        idx["full"].setdefault(normalize_name(name), []).append(rec)
        idx["short"].setdefault(_short_key(name, ""), []).append(rec)
    return idx


def _pick_candidate(cands: list, position: str | None) -> dict | None:
    if position:
        pos_match = [c for c in cands if c["position"] == position.upper()]
        if pos_match:
            cands = pos_match
    active = [c for c in cands if c["active"] and c["team"]]
    return (active or cands or [None])[0]


def _lookup(idx: dict, name: str, position: str | None = None) -> dict | None:
    from .sources.oddsapi import normalize_name
    full = idx.get("full", {}).get(normalize_name(name), [])
    if full:
        return _pick_candidate(full, position)
    return _pick_candidate(idx.get("short", {}).get(_short_key(name, ""), []),
                           position)


def rookie_board(blob: dict, limit: int = 36) -> list[dict]:
    """Active rookies at fantasy positions with a team and a depth-chart
    slot, best slots first. Deliberately UNRANKED for points: no NFL
    volume exists, so pretending to project them would be the exact
    dishonesty the rest of the site avoids."""
    rows = []
    for p in (blob or {}).values():
        if not isinstance(p, dict) or p.get("years_exp") not in (0, "0"):
            continue
        pos = (p.get("position") or "").upper()
        if pos not in FANTASY_POSITIONS or not p.get("team"):
            continue
        if not p.get("active", True):
            continue
        name = (p.get("full_name")
                or f"{p.get('first_name', '')} {p.get('last_name', '')}").strip()
        order = p.get("depth_chart_order")
        rows.append({
            "player": name, "team": _canon_team(p.get("team")), "position": pos,
            "depth_pos": (p.get("depth_chart_position") or pos).upper(),
            "depth_order": order if isinstance(order, int) else 99,
        })
    # Best depth slots first; QB before RB before WR before TE inside a slot.
    pos_rank = {p: i for i, p in enumerate(FANTASY_POSITIONS)}
    rows.sort(key=lambda r: (r["depth_order"], pos_rank[r["position"]], r["player"]))
    return rows[:limit]


def apply_current_rosters(kit: dict, idx: dict) -> list[dict]:
    """Stamp every draft-kit row with its player's CURRENT team. Returns
    the moves list (board players whose team changed since the stats).

    The projection is deliberately untouched: we know the player moved,
    we do not know what the new offense does to his volume, and silently
    "adjusting" for it would be invention. The flag is the honest output."""
    moves, seen = [], set()
    rows = list(kit.get("board", []))
    for pos_rows in (kit.get("tiers") or {}).values():
        rows += pos_rows
    rows += kit.get("sleepers", [])
    for r in rows:
        cur = _lookup(idx, r["player"], r["position"])
        if cur is None:
            continue
        if cur["team"] and cur["team"] != r["team"]:
            if r["player"] not in seen:
                seen.add(r["player"])
                moves.append({"player": r["player"], "position": r["position"],
                              "from": r["team"], "to": cur["team"]})
            r["moved_from"] = r["team"]
            r["team"] = cur["team"]
        elif not cur["team"] or not cur["active"]:
            r["roster_flag"] = "free agent" if not cur["team"] else cur["status"] or "inactive"
    moves.sort(key=lambda m: m["player"])
    return moves


def qb_changes(schedule_rows: list[dict], idx: dict) -> list[dict]:
    """Teams whose current depth-chart QB1 differs from the QB who took
    most of their snaps late last season."""
    from .sources.oddsapi import normalize_name
    last, _ = seasons_in(schedule_rows)
    if last is None or not idx:
        return []
    before = _final_qbs(schedule_rows, last)
    qb1: dict[str, str] = {}
    for cands in idx.get("full", {}).values():
        for c in cands:
            if (c["position"] == "QB" and c["active"] and c["team"]
                    and c["depth_order"] == 1):
                qb1[c["team"]] = c["name"]
    out = []
    for team, now in sorted(qb1.items()):
        was = before.get(team, "")
        if not was:
            continue
        # Same man if EITHER name form agrees — the schedule and Sleeper
        # write names differently ("Gardner Minshew II" vs "Gardner
        # Minshew"), and a false "new QB" is worse than a missed one.
        same = (normalize_name(was) == normalize_name(now)
                or _short_key(was, "") == _short_key(now, ""))
        if not same:
            out.append({"team": team, "before": was, "now": now})
    return out


def build_offseason(schedule_rows: list[dict], blob: dict | None,
                    kit: dict | None = None) -> dict:
    """The full offseason layer for the Fantasy page. Mutates ``kit`` rows
    with current teams when Sleeper data is available."""
    last, upcoming = seasons_in(schedule_rows or [])
    out = {
        "stats_season": last, "upcoming_season": upcoming,
        "coach_changes": coach_changes(schedule_rows or []),
        "rosters_live": blob is not None,
        "rookies": [], "moves": [], "qb_changes": [],
    }
    if blob is not None:
        idx = index_players(blob)
        out["rookies"] = rookie_board(blob)
        out["qb_changes"] = qb_changes(schedule_rows or [], idx)
        if kit is not None:
            out["moves"] = apply_current_rosters(kit, idx)
    return out
