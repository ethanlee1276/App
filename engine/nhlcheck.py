"""Why does the NHL board have no picks? — one command, one answer.

    cd /srv/qellys && sudo -u qellys python3 -m engine.nhlcheck

Ethan, 2026-10-06: "hockey (nhl) has not had any most likely pick or edge
picks." The build posts nothing for several honest reasons and one or two
broken ones; this reads each in the order the build meets them and names
the first that stops it:

  1. the schedule — preseason (game type 1) is skipped on purpose;
  2. the history — no stored NHL games means no props to price;
  3. the odds — a slate with no prices has no Edge pick (the launcher buys
     them only on the cycle after it first sees tonight's games);
  4. the rank store — Most Likely ranks only markets rankfit measured;
  5. the gates — every prop priced and every one refused (the census).
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verdict(board: dict, schedule: list[dict] | None, logs: int, rank_keys: list[str]) -> list[str]:
    """Plain lines, the stopping reason first. ``schedule`` is today's NHL
    games with their type (None = the feed could not be read)."""
    out = []
    recs = [r for r in board.get("recommendations") or [] if r.get("recommended")]
    ml = board.get("most_likely") or []
    games = board.get("games") or []
    out.append(f"Board {board.get('date') or '?'} built {board.get('generated_at') or '?'}: "
               f"status {board.get('status') or '?'}, {len(games)} game(s), {len(recs)} Edge pick(s), "
               f"{len(ml)} Most Likely")
    if board.get("note"):
        out.append(f"  note: {board['note']}")
    if board.get("odds_note"):
        out.append(f"  odds: {board['odds_note']}")
    if schedule is None:
        out.append("STOP — the NHL schedule feed could not be read from this box.")
        return out
    kinds = {}
    for g in schedule:
        kinds[g.get("type")] = kinds.get(g.get("type"), 0) + 1
    words = {1: "preseason", 2: "regular season", 3: "playoffs"}
    out.append("  today's schedule: " + (", ".join(f"{n} {words.get(t, f'type {t}')}" for t, n in kinds.items())
                                         or "no games"))
    if not any(g.get("type") in (2, 3) for g in schedule):
        out.append("NO PICKS EXPECTED — " + ("preseason only; the board waits for the regular season."
                                             if kinds.get(1) else "no NHL games today."))
        return out
    if logs == 0:
        out.append("STOP — no NHL games stored. Fix: python3 ingest.py nhl --seasons 2023-2025")
        return out
    out.append(f"  stored NHL player-game rows: {logs:,}")
    nhl_rank = sorted(k for k in rank_keys if k.startswith("nhl:"))
    out.append(f"  rankfit NHL markets: {', '.join(nhl_rank) or 'none'}")
    if not games:
        out.append("STOP — there are games today and the board has none: the board is stale "
                   "(the build has not run since the schedule changed). Check the launcher log.")
        return out
    priced = sum(1 for r in board.get("recommendations") or [] if r.get("odds") not in (None, ""))
    out.append(f"  priced props: {priced}")
    if not priced:
        out.append("STOP — no prices on tonight's props. The launcher buys NHL odds only once the board "
                   "shows games, and only when the pacer allows; see 'odds:' above and the launcher log.")
    if not nhl_rank:
        out.append("STOP (Most Likely) — no NHL market measured to rank. "
                   "Fix: sudo -u qellys python3 -m engine.rankfit measure nhl")
    census = board.get("gate_census") or {}
    if priced and not recs and census:
        top = sorted(census.items(), key=lambda kv: -kv[1])[:6]
        out.append("Every priced prop was refused. The top reasons: "
                   + "; ".join(f"{k} ×{v}" for k, v in top))
    if recs or ml:
        out.append("Picks are on the board.")
    return out


def main(argv=None) -> int:
    from . import gate
    path = Path(gate.board_source(ROOT / "web" / "data" / "nhl.json"))
    try:
        board = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        print(f"no NHL board at {path}: {exc}")
        board = {}
    day = board.get("date") or _dt.date.today().isoformat()
    try:
        from .sources import nhldata
        schedule = nhldata.parse_score_day(nhldata.fetch_score(day))
    except Exception as exc:                                 # noqa: BLE001
        print(f"schedule: {exc}")
        schedule = None
    try:
        from .db import connect
        logs = connect().execute("SELECT COUNT(*) FROM player_game_logs WHERE sport='nhl'").fetchone()[0]
    except Exception as exc:                                 # noqa: BLE001
        print(f"history: {exc}")
        logs = 0
    from .rankfit import load
    for ln in verdict(board, schedule, logs, list(load())):
        print(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
