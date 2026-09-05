"""NFL contract-incentive tracker — December money, measured from our logs.

Late in the season a player with a stats bonus in his contract stops
being an ordinary projection: "needs 62 receiving yards for $500,000" is
information his own sideline acts on, and Week 17-18 usage bends toward
it. Books are slow to price that; a board that KNOWS the number is not.

No free feed publishes contract incentives — they surface in December
beat reporting and on the cap sites. So the table is hand-curated,
checked into the repo at ``data/nfl_incentives.json``::

    {
      "season": 2026,
      "entries": [
        {"player": "Example Receiver", "team": "KC", "stat": "rec_yds",
         "threshold": 1000, "bonus_usd": 500000,
         "source": "per beat reporting, 2026-12-14"}
      ]
    }

``stat`` must be a market our ingest actually carries — a threshold we
cannot measure would render as a guess, and this module drops it with
its reason attached rather than pretending. Everything computed here
(season total, distance, pace, games left) comes from our own ingested
game logs and finals, the same rows the model already trusts.

Authority: the tracker DISPLAYS and ANNOTATES. It appends a reason to a
matching prop card so the human sees the angle; it never moves a
probability — an unmeasured usage bump is a hypothesis, and hypotheses
go through the lab, not the pricing path.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

DATA_PATH = Path("data/nfl_incentives.json")

#: Stats the tracker can measure — exactly the NFL markets our ingest
#: writes per game. Anything else in the table is flagged, not guessed.
TRACKABLE = {
    "pass_yds": "passing yards",
    "rush_yds": "rushing yards",
    "rec_yds": "receiving yards",
    "receptions": "receptions",
}
REGULAR_SEASON_GAMES = 17


def load(path: Path | str | None = None) -> dict:
    p = Path(path if path is not None else DATA_PATH)
    try:
        raw = json.loads(p.read_text()) if p.is_file() else {}
        if not isinstance(raw, dict):
            raw = {}
    except (ValueError, OSError):
        raw = {}
    entries = [e for e in (raw.get("entries") or []) if isinstance(e, dict)]
    return {"season": raw.get("season"), "entries": entries}


def _team_games_played(hconn, team: str, season: int) -> int:
    """Finals the team has actually played, from our own games table."""
    r = hconn.execute(
        "SELECT COUNT(*) FROM games WHERE sport='nfl' AND season=? "
        "AND home_score IS NOT NULL AND (home=? OR away=?)",
        (season, team, team)).fetchone()
    return int(r[0] or 0)


def report(hconn, season: int | None = None,
           path: Path | str | None = None) -> dict:
    """The tracker: each entry measured against the ingested season.

    Status vocabulary, computed not vibed:
      * ``hit``          — threshold already reached
      * ``missed``       — season over, threshold not reached
      * ``on pace``      — per-game need ≤ his own season per-game pace
      * ``needs a push`` — per-game need within 1.75× his pace
      * ``long shot``    — needs more than 1.75× his pace, every week
      * ``collecting``   — no games on file yet to judge from
    """
    from .sources.oddsapi import normalize_name
    from .seasons import season_of
    tbl = load(path)
    season = int(season or tbl.get("season")
                 or season_of("nfl", _dt.date.today().isoformat()))
    rows, dropped = [], []
    for e in tbl["entries"]:
        stat = str(e.get("stat") or "")
        if stat not in TRACKABLE:
            dropped.append({"player": e.get("player"), "stat": stat,
                            "why": "not a market our ingest carries"})
            continue
        want = normalize_name(str(e.get("player") or ""))
        logs = [r for r in hconn.execute(
            "SELECT player, value, period, team FROM player_game_logs "
            "WHERE sport='nfl' AND season=? AND market=?", (season, stat))
            if normalize_name(r["player"]) == want]
        total = round(sum(float(r["value"] or 0) for r in logs), 1)
        played = len({r["period"] for r in logs})
        team = str(e.get("team") or (logs[-1]["team"] if logs else ""))
        team_played = _team_games_played(hconn, team, season) if team else 0
        remaining = max(0, REGULAR_SEASON_GAMES - max(team_played, played))
        threshold = float(e.get("threshold") or 0)
        need = max(0.0, round(threshold - total, 1))
        pace = round(total / played, 2) if played else None
        per_game_need = round(need / remaining, 2) if remaining else None
        if need <= 0:
            status = "hit"
        elif remaining == 0:
            status = "missed"
        elif pace is None:
            status = "collecting"
        elif per_game_need <= pace:
            status = "on pace"
        elif per_game_need <= pace * 1.75:
            status = "needs a push"
        else:
            status = "long shot"
        rows.append({
            "player": e.get("player"), "team": team, "stat": stat,
            "stat_label": TRACKABLE[stat], "threshold": threshold,
            "total": total, "need": need, "games_played": played,
            "games_left": remaining, "pace": pace,
            "per_game_need": per_game_need,
            "bonus_usd": float(e.get("bonus_usd") or 0),
            "status": status, "source": e.get("source") or "",
        })
    # Money on the line first, then closest to the wire.
    rows.sort(key=lambda r: (-r["bonus_usd"], r["need"]))
    return {"season": season, "entries": rows, "dropped": dropped,
            "note": "" if rows else (
                "No incentives on file yet — they land with December "
                "reporting. Add entries to data/nfl_incentives.json "
                "(schema in engine/incentives.py) and the tracker measures "
                "them against our own ingested logs on the next build.")}


def decorate(recommendations: list[dict], entries: list[dict]) -> int:
    """Append the incentive angle to matching prop cards.

    A reason, never a number: the card says what the sideline knows, and
    the human weighs it. Only LIVE chases decorate — a hit or missed
    incentive no longer bends anyone's usage."""
    from .sources.oddsapi import normalize_name
    live = {(normalize_name(str(e.get("player") or "")), e.get("stat")): e
            for e in entries
            if e.get("status") in ("on pace", "needs a push", "long shot")}
    if not live:
        return 0
    n = 0
    for r in recommendations:
        key = (normalize_name(str(r.get("player") or "")), r.get("market"))
        e = live.get(key)
        if not e:
            continue
        r.setdefault("reasons", []).append(
            f"Incentive watch: needs {e['need']:g} more {e['stat_label']} "
            f"in {e['games_left']} game(s) for a "
            f"${e['bonus_usd']:,.0f} bonus — his sideline knows it too")
        r["incentive"] = {k: e[k] for k in
                          ("need", "games_left", "bonus_usd", "status")}
        n += 1
    return n
