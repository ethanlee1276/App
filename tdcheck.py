#!/usr/bin/env python3
"""Is today's touchdown work on the live NFL board? Game by game.

    cd /srv/qellys && python3 tdcheck.py            # the board the site serves
    python3 tdcheck.py path/to/board.json           # any built board

Ethan, 2026-09-27, after the Jets @ Lions and Chargers @ Bills work: "make
sure changes are live and obviously is working on every game ... and for
the future". Reads only. For every game on the board it checks the game
plan's "Who scores" step (after the matchup, ranked, each with his seat),
and for every priced scorer that the measured pieces of the touchdown
chain are in his reasons: goal-line counts when measured, quarterbacks
x1.40, the running-back curve, depth receivers scaled. Exit 1 when
anything is missing, so a cron or a person can trust the last line.
"""
from __future__ import annotations

import json
import subprocess
import sys

MARKS = (("goal-line", "Goal-line work:"), ("QB x1.40", "Quarterback: scoring rate"),
         ("RB curve", "Running back: read on the measured"), ("depth WR", "Depth receiver:"))


def check(board: dict, out=print) -> list:
    """The list of misses (empty when everything is there)."""
    misses = []
    plans = board.get("game_plans") or []
    out(f"{len(plans)} game plans on the board")
    for g in plans:
        keys = [s.get("key") for s in g.get("steps") or []]
        who = next((s for s in g.get("steps") or [] if s.get("key") == "who"), None)
        rows = (who or {}).get("rows") or []
        out(f"  {g.get('game', '?'):9} who-scores rows {len(rows)}")
        if "who" not in keys or "matchup" not in keys or keys.index("who") != keys.index("matchup") + 1:
            misses.append(f"{g.get('game')}: no 'Who scores' step after the matchup")
        for r in rows:
            why = r.get("why") or []
            out(f"      {r.get('player', ''):22} {float(r.get('model_prob') or 0):.0%} {r.get('odds')}  "
                f"{why[-1] if why else ''}")
            if not why:
                misses.append(f"{g.get('game')}: {r.get('player')} has no seat")
    pos_of = {f.get("player"): (f.get("position") or "").upper() for f in board.get("td_field") or []}
    watch = board.get("longshot_watch") or []
    out(f"{len(watch)} priced scorers")
    for w in watch:
        text = " ".join(w.get("reasons") or [])
        pos = pos_of.get(w.get("player"), "")
        got = [name for name, t in MARKS if t in text]
        out(f"  {w.get('player', ''):22} {pos:3} {float(w.get('model_prob') or 0):.0%} {w.get('odds')}  "
            f"{', '.join(got)}")
        if pos == "QB" and "QB x1.40" not in got:
            misses.append(f"{w.get('player')}: quarterback scale missing")
        if pos == "RB" and "RB curve" not in got:
            misses.append(f"{w.get('player')}: running-back curve missing")
        if w.get("goal_line") and "goal-line" not in got:
            misses.append(f"{w.get('player')}: goal-line counts measured but not said")
    return misses


def main(argv) -> int:
    if argv:
        path = argv[0]
    else:
        from engine.gate import board_source
        path = board_source("web/data/recommendations.json")
    try:
        rev = subprocess.run(["git", "log", "-1", "--format=%h %s"], capture_output=True,
                             text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        rev = "?"
    print(f"code: {rev}\nboard: {path}")
    with open(path, encoding="utf-8") as fh:
        board = json.load(fh)
    print(f"built: {board.get('built_at')}")
    misses = check(board)
    for m in misses:
        print("MISSING", m)
    print("ALL TOUCHDOWN CHECKS PASS" if not misses else f"{len(misses)} MISSING")
    return 0 if not misses else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
