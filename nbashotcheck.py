#!/usr/bin/env python3
"""Does ESPN's play-by-play draw a true NBA shot chart? Read-only, on the box.

    cd /srv/qellys && sudo -u qellys python3 nbashotcheck.py            # the newest stored final
    cd /srv/qellys && sudo -u qellys python3 nbashotcheck.py 401810001  # one game by ESPN's id

Written 2026-10-14 (runbook step 104) with the shot chart moved onto ESPN's
game summary (`engine/nba/shots.fold_espn`), from the shape an earlier probe
recorded — field names, not ESPN's court. Where ESPN puts the basket
(`shots.ESPN_HOOP`) is the one thing that was taken on trust, so this reads
one real final the way the nightly will and holds what it folds to the
league's own shape: threes from 22 feet out and most from 23 to 27, dunks
and layups at the rim, a corner three on a fifth or so of threes, most
makes assisted, a few misses blocked. A line that says CHECK is the one
I need; nothing is stored, and a summary this read downloaded is not kept.
A play's written text is never printed.
"""

import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

#: (what, low, high) — the league's own shape, wide enough for one game.
BARS = (("median three, feet", 22.0, 27.5),
        ("shortest three, feet", 21.0, 24.5),
        ("median dunk or layup, feet", 0.0, 4.0),
        ("corner threes, share of threes", 0.05, 0.45),
        ("makes assisted, share", 0.35, 0.85),
        ("misses blocked, share", 0.0, 0.20))


def measures(rows: list) -> dict:
    """The numbers BARS holds a game's folded rows to."""
    fg = [r for r in rows if r["kind"] in ("2pt", "3pt")]
    three = [r["distance"] for r in fg if r["kind"] == "3pt" and r["distance"] is not None]
    rim = [r["distance"] for r in fg if r["distance"] is not None
           and any(w in r["shot"].lower() for w in ("dunk", "layup"))]
    threes = [r for r in fg if r["kind"] == "3pt"]
    made, missed = [r for r in fg if r["made"]], [r for r in fg if not r["made"]]
    share = lambda part, whole: round(len(part) / len(whole), 3) if whole else None  # noqa: E731
    return {"median three, feet": statistics.median(three) if three else None,
            "shortest three, feet": min(three) if three else None,
            "median dunk or layup, feet": statistics.median(rim) if rim else None,
            "corner threes, share of threes": share([r for r in threes if r["zone"] == "corner3"], threes),
            "makes assisted, share": share([r for r in made if r["assist"]], made),
            "misses blocked, share": share([r for r in missed if r["blocked"]], missed)}


def report(summary: dict, game_id: str, date: str) -> list:
    from engine.nba import shots as NS
    plays = (summary or {}).get("plays") or []
    shooting = [p for p in plays if p.get("shootingPlay")]
    out = [f"NBA SHOT CHECK  game {game_id} on {date}: {len(plays)} plays, {len(shooting)} shooting"]
    if not shooting:
        return out + ["  CHECK: no shooting plays in ESPN's summary — the chart has nothing to draw"]
    fgs = [p for p in shooting if p.get("pointsAttempted") in (2, 3)][:3]
    out.append(f"  a shot's fields: {sorted(fgs[0]) if fgs else sorted(shooting[0])}")
    for p in fgs:
        out.append(f"    pointsAttempted {p.get('pointsAttempted')}  scoring {p.get('scoringPlay')}  "
                   f"coordinate {p.get('coordinate')}  type {(p.get('type') or {}).get('text')!r}")
    ft = next((p for p in shooting if p.get("pointsAttempted") == 1), None)
    if ft:
        out.append(f"    a free throw's coordinate {ft.get('coordinate')}")
    rows = NS.fold_espn(summary, date, game_id)
    kinds = {k: sum(1 for r in rows if r["kind"] == k) for k in ("2pt", "3pt", "ft")}
    out.append(f"  folded: {len(rows)} rows — {kinds['2pt']} twos, {kinds['3pt']} threes, {kinds['ft']} free throws; "
               f"zones {dict(sorted({z: sum(1 for r in rows if r['zone'] == z) for z in {r['zone'] for r in rows if r['zone']}}.items()))}")
    got = measures(rows)
    for what, lo, hi in BARS:
        v = got[what]
        ok = v is not None and lo <= v <= hi
        out.append(f"  {'ok   ' if ok else 'CHECK'} {what}: {v}  (expected {lo}–{hi})")
    return out


def main(argv=None) -> int:
    from engine import db
    from engine.nba import shots as NS
    argv = sys.argv[1:] if argv is None else argv
    conn = db.connect()
    if argv:
        row = conn.execute("SELECT game_id, period FROM games WHERE sport='nba' AND game_id=?",
                           (argv[0],)).fetchone()
    else:
        row = conn.execute("SELECT game_id, period FROM games WHERE sport='nba' AND home_score IS NOT NULL "
                           "AND game_id GLOB '[0-9]*' ORDER BY period DESC LIMIT 1").fetchone()
    if not row:
        print("NBA SHOT CHECK  no stored NBA final to read")
        return 1
    gid, date = str(row[0]), str(row[1])[:10]
    summary = NS.read_espn(gid)
    if not summary:
        print(f"NBA SHOT CHECK  game {gid}: ESPN's summary could not be read")
        return 1
    for line in report(summary, gid, date):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
