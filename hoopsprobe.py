#!/usr/bin/env python3
"""What does ESPN's live NBA game file carry for the new play-by-play page? Read-only, on the box.

    cd /srv/qellys && sudo -u qellys python3 hoopsprobe.py                  # a game in progress
    cd /srv/qellys && sudo -u qellys python3 hoopsprobe.py --prefer post    # the newest final instead
    cd /srv/qellys && sudo -u qellys python3 hoopsprobe.py --event 401810001

Ethan, 2026-10-15, with two renders of a new NBA play-by-play screen: "figure
out what live data we can get to make it look like an actual play by play
screen like ball tracking or possessions". The league's own feed (which has
possession, timeouts and the bonus on every action) answers the box 403
(runbook step 103), so ESPN's game summary is the source. This prints, for
one game, what the page can stand behind:

  1. THE SCORER'S TABLE — whether ESPN carries a `situation` block for
     basketball (timeouts left, team fouls, the bonus, the ball), on the
     scoreboard and in the summary, and what the parser makes of it. The
     page draws no dots and no arrow without it.
  2. THE COURT — how many shots carry a spot on the floor, where the rim
     sits by them (dunks and layups should be within a few feet of the
     basket the parser assumes), and which other plays carry a spot.
  3. WHO IS ON THE FLOOR — the box score's starters, and whether ESPN lists
     a substitution's man coming IN first or going OUT first. Both orders
     are played forward from the starters; the order with no impossible step
     (a man entering who is already on, or leaving who is not) is ESPN's.
  4. WHAT THE DEEP FILE WILL CARRY — the keys and counts the page will read.

Key names, counts, numbers and ESPN's short type labels only. A play's
written text is never printed. Nothing is stored.
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

#: A short upper-case code (BONUS, DOUBLE_BONUS) is printed as itself; any
#: other string only by its length, so no sentence can reach the screen.
def _scalar(v) -> str:
    if isinstance(v, bool) or v is None or isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    if len(s) <= 16 and s.replace("_", "").isalnum() and (s.isupper() or s.isdigit()):
        return s
    return f"str({len(s)})"


def _flat(block, prefix="", depth=0) -> list[str]:
    """A situation block's keys and values, two levels deep."""
    out = []
    if not isinstance(block, dict):
        return [f"{prefix}{_scalar(block)}"]
    for k in sorted(block):
        v = block[k]
        if isinstance(v, dict) and depth < 2:
            out += _flat(v, f"{prefix}{k}.", depth + 1)
        elif isinstance(v, list):
            out.append(f"{prefix}{k} = list({len(v)})")
        else:
            out.append(f"{prefix}{k} = {_scalar(v)}")
    return out


def on_floor_order(starters: dict, subs: list) -> dict:
    """``{"in_first": conflicts, "out_first": conflicts}`` — each order of a
    substitution's two names played forward from the starters. ``starters``
    is ``{team: set(ids)}``; ``subs`` is ``[(team, first_id, second_id)]``
    in game order. A conflict is a man entering who is already on the floor
    or leaving who is not."""
    result = {}
    for name, flip in (("in_first", False), ("out_first", True)):
        floor = {t: set(ids) for t, ids in starters.items()}
        bad = 0
        for team, a, b in subs:
            if team not in floor:
                continue
            enter, leave = (b, a) if flip else (a, b)
            if enter in floor[team] or leave not in floor[team]:
                bad += 1
            floor[team].discard(leave)
            floor[team].add(enter)
        result[name] = bad
    return result


def report(scoreboard: dict, payload: dict, event: str) -> list[str]:
    from engine.sources import espnplays as E
    import livescore_build as B
    out = []
    ev = next((e for e in (scoreboard or {}).get("events") or [] if str(e.get("id")) == str(event)), {})
    comp = ((ev.get("competitions") or [{}])[:1] or [{}])[0]
    out.append("\n=== 1. the scorer's table ===")
    for where, block in (("scoreboard competitions[0].situation", comp.get("situation")),
                         ("summary header.competitions[0].situation",
                          ((((payload.get("header") or {}).get("competitions")) or [{}])[0] or {}).get("situation")),
                         ("summary top-level situation", payload.get("situation"))):
        if not block:
            out.append(f"  {where}: ABSENT")
            continue
        out.append(f"  {where}:")
        out += [f"      {line}" for line in _flat(block)]
    sit = E.hoops_situation(payload, "nba")
    out.append(f"  the parser reads: {sit or 'nothing (the page draws no timeouts, bonus or ball arrow)'}")

    plays = [p for p in payload.get("plays") or [] if isinstance(p, dict)]
    shots = [p for p in plays if p.get("shootingPlay") and (p.get("pointsAttempted") or 0) in (2, 3)]
    spotted = [(p, E._floor_spot(p.get("coordinate"))) for p in shots]
    spotted = [(p, s) for p, s in spotted if s]
    out.append("\n=== 2. the court ===")
    out.append(f"  plays {len(plays)}; field-goal attempts {len(shots)}; with a spot on the floor {len(spotted)}")
    rim = [math.hypot(s[0] - 25, s[1]) for p, s in spotted
           if any(w in str((p.get("type") or {}).get("text") or "").lower() for w in ("dunk", "layup"))]
    threes = [math.hypot(s[0] - 25, s[1]) for p, s in spotted if (p.get("pointsAttempted") or 0) == 3]
    if rim:
        out.append(f"  dunks and layups: median {statistics.median(rim):.1f} ft from (25, 0) "
                   f"({'ok' if statistics.median(rim) <= 4 else 'CHECK — the basket is not where the page puts it'})")
    if threes:
        out.append(f"  threes: median {statistics.median(threes):.1f} ft, shortest {min(threes):.1f} "
                   f"({'ok' if 22 <= statistics.median(threes) <= 27.5 else 'CHECK'})")
    for p, s in spotted[:3]:
        out.append(f"  e.g. {str((p.get('type') or {}).get('text') or '')[:28]:<28} made={bool(p.get('scoringPlay'))!s:<5} "
                   f"x={s[0]:5.1f} y={s[1]:5.1f}")
    others = Counter(str((p.get("type") or {}).get("text") or "")[:28] for p in plays
                     if not p.get("shootingPlay") and E._floor_spot(p.get("coordinate")))
    out.append(f"  other plays with a spot: {dict(others.most_common(6)) or 'none'}")

    out.append("\n=== 3. who is on the floor ===")
    sides = {}
    for c in comp.get("competitors") or (((payload.get("header") or {}).get("competitions")) or [{}])[0].get("competitors") or []:
        sides[str((c.get("team") or {}).get("id") or "")] = (c.get("team") or {}).get("abbreviation") or c.get("homeAway")
    starters: dict = {}
    for block in ((payload.get("boxscore") or {}).get("players")) or []:
        tid = str((block.get("team") or {}).get("id") or "")
        for grp in block.get("statistics") or []:
            for ath in grp.get("athletes") or []:
                if ath.get("starter") is True:
                    starters.setdefault(tid, set()).add(str((ath.get("athlete") or {}).get("id") or ""))
    out.append(f"  starters marked in the box: {({sides.get(t, t): len(v) for t, v in starters.items()}) or 'NONE'}")
    subs = []
    shape = Counter()
    for p in plays:
        if "substitution" not in str((p.get("type") or {}).get("text") or "").lower():
            continue
        ids = [str(((q or {}).get("athlete") or {}).get("id") or "") for q in p.get("participants") or []]
        shape[len(ids)] += 1
        if len(ids) == 2:
            subs.append((str((p.get("team") or {}).get("id") or ""), ids[0], ids[1]))
    out.append(f"  substitutions {sum(shape.values())}; names per substitution {dict(shape) or '-'}")
    if starters and subs:
        got = on_floor_order(starters, subs)
        verdict = ("ESPN lists the man coming IN first" if got["in_first"] == 0 < got["out_first"]
                   else "ESPN lists the man going OUT first" if got["out_first"] == 0 < got["in_first"]
                   else "neither order holds — the page will not draw who is on the floor")
        out.append(f"  impossible steps: in-first {got['in_first']}, out-first {got['out_first']} → {verdict}")
    timeouts = Counter(sides.get(str((p.get("team") or {}).get("id") or ""), "no team") for p in plays
                       if "timeout" in str((p.get("type") or {}).get("text") or "").lower())
    out.append(f"  timeouts in the plays, by side: {dict(timeouts) or 'none'}")
    fouls = Counter(str((p.get("type") or {}).get("text") or "")[:28] for p in plays
                    if "foul" in str((p.get("type") or {}).get("text") or "").lower())
    out.append(f"  foul labels: {dict(fouls.most_common(8)) or 'none'}")

    out.append("\n=== 4. what the deep file will carry ===")
    home = next((c for c in comp.get("competitors") or [] if c.get("homeAway") == "home"), {})
    away = next((c for c in comp.get("competitors") or [] if c.get("homeAway") == "away"), {})
    g = {"event_id": str(event), "home": (home.get("team") or {}).get("abbreviation") or "",
         "away": (away.get("team") or {}).get("abbreviation") or "", "live": {}}
    doc = B.pbp_doc("nba", g, payload, sides={str((home.get("team") or {}).get("id") or ""): g["home"],
                                               str((away.get("team") or {}).get("id") or ""): g["away"]})
    rows = doc.get("plays") or []
    out.append(f"  keys: {', '.join(sorted(doc))}")
    out.append(f"  plays {len(rows)}; with a spot {sum(1 for r in rows if 'x' in r)}; "
               f"with more than one name {sum(1 for r in rows if r.get('players'))}")
    out.append(f"  quarters: {doc.get('linescores') or 'none'}; venue: {doc.get('venue') or 'none'}")
    box_starters = sum(1 for b in doc.get("box") or [] for grp in b["groups"] for r in grp["rows"] if r.get("starter"))
    out.append(f"  box rows marked as starters: {box_starters}")
    return out


def main(argv=None) -> int:
    from espnprobe import _get, pick_event
    from engine.sources.livescores import ESPN_SCOREBOARD
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--event", default="")
    ap.add_argument("--prefer", default="in", choices=("in", "post", "any"))
    ap.add_argument("--date", default="", help="YYYYMMDD: that day's scoreboard instead of today's")
    a = ap.parse_args(argv)
    event, state = (a.event, "asked for") if a.event else pick_event("nba", a.prefer, a.date)
    print(f"NBA event {event}  state {state}")
    scoreboard = _get(ESPN_SCOREBOARD["nba"] + (f"?dates={a.date}" if a.date else ""))
    payload = _get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={event}")
    for line in report(scoreboard, payload, event):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
