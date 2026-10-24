#!/usr/bin/env python3
"""What does the NHL's own live feed carry for the new hockey page? Read-only, on the box.

    cd /srv/qellys && sudo -u qellys python3 rinkprobe.py                  # a game in progress
    cd /srv/qellys && sudo -u qellys python3 rinkprobe.py --prefer post    # the newest final instead
    cd /srv/qellys && sudo -u qellys python3 rinkprobe.py --game 2026020123

Ethan, 2026-10-15, with two renders of an NHL play-by-play screen: "figure
out what data we can use for the live play by play screen for nhl like live
posetions and puck tracking". This sandbox cannot reach the league's hosts;
this prints, for one game, what the page can stand behind:

  1. THE EVENTS — how many plays, of which kinds, how many carry a spot on
     the ice, and the detail keys each kind carries (the names
     `engine/sources/nhlrink` reads).
  2. THE ENDS — whether `homeTeamDefendingSide` agrees with where the home
     team's shots went, period by period (every row is turned so home
     attacks the right-hand net), and whose side a blocked shot's
     `eventOwnerTeamId` names: the shooter's or the blocker's.
  3. THE SCORER'S TABLE — the situation codes seen, and the feed's own
     power-play block (the side and the time left) if it carries one.
  4. WHO IS ON THE ICE — whether the shift charts are kept up during a
     game: how many players each side has on a shift at the latest play's
     time. Six a side means the chart is live; fewer means it lags.
  5. PUCK TRACKING — the goal visualizer's tracked positions for the latest
     goal (the seconds before each goal, nhl.com's own feed): its answer
     and its shape, key names and counts only.
  6. WHAT THE DEEP FILE WILL CARRY — the rink block's keys and counts.

Key names, counts, numbers and the league's short codes only; nothing is
stored.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

SPRITES = "https://wsr.nhle.com/sprites/{season}/{game}/ev{event}.json"
SHIFTS = "https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={game}"


def _get(url: str):
    """GET JSON with urllib's own agent (see espnprobe._get)."""
    import urllib.request
    with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _clock(text) -> int | None:
    try:
        m, s = str(text).split(":")
        return int(m) * 60 + int(s)
    except (ValueError, AttributeError):
        return None


def _shape(v, depth=0) -> str:
    """A value's shape: key names and lengths, two levels, never a string's text."""
    if isinstance(v, dict):
        if depth >= 2:
            return f"dict({len(v)})"
        return "{" + ", ".join(f"{k}: {_shape(v[k], depth + 1)}" for k in list(v)[:12]) + ("…" if len(v) > 12 else "") + "}"
    if isinstance(v, list):
        return f"list({len(v)})" + (f" of {_shape(v[0], depth + 1)}" if v and depth < 2 else "")
    if isinstance(v, bool) or v is None:
        return repr(v)
    if isinstance(v, (int, float)):
        return type(v).__name__
    return f"str({len(str(v))})"


def events_report(pbp: dict) -> list[str]:
    out = ["\n=== 1. the events ==="]
    from engine.sources import nhlrink
    plays = [p for p in pbp.get("plays") or [] if isinstance(p, dict)]
    code = lambda v: nhlrink._code(v) or (f"<not a code, {len(str(v))} chars>" if v else "")
    kinds = Counter(code(p.get("typeDescKey")) for p in plays)
    out.append(f"  plays {len(plays)}; top-level keys: {', '.join(sorted(pbp))}")
    out.append(f"  kinds: {dict(kinds.most_common())}")
    keys: dict = {}
    spots: Counter = Counter()
    for p in plays:
        k = code(p.get("typeDescKey"))
        d = p.get("details") or {}
        keys.setdefault(k, set()).update(d)
        if isinstance(d.get("xCoord"), (int, float)) and isinstance(d.get("yCoord"), (int, float)):
            spots[k] += 1
    for k, n in kinds.most_common():
        out.append(f"  {k:<18} {n:>4}  with a spot {spots[k]:>4}  keys: {', '.join(sorted(keys.get(k) or [])) or '-'}")
    # The league's short codes, and only the length of anything else.
    reasons = Counter(code((p.get("details") or {}).get("reason")) for p in plays
                      if str(p.get("typeDescKey") or "") in ("stoppage", "missed-shot")
                      and (p.get("details") or {}).get("reason"))
    out.append(f"  stoppage and miss reasons: {dict(reasons.most_common(10))}")
    return out


def ends_report(pbp: dict) -> list[str]:
    out = ["\n=== 2. the ends ==="]
    hid = (pbp.get("homeTeam") or {}).get("id")
    plays = [p for p in pbp.get("plays") or [] if isinstance(p, dict)]
    team_of = {str(r.get("playerId")): r.get("teamId") for r in pbp.get("rosterSpots") or [] if isinstance(r, dict)}
    by_period: dict = {}
    for p in plays:
        per = (p.get("periodDescriptor") or {}).get("number")
        side = str(p.get("homeTeamDefendingSide") or "")
        d = p.get("details") or {}
        row = by_period.setdefault(per, {"side": Counter(), "right": 0, "left": 0})
        if side:
            row["side"][side] += 1
        if str(p.get("typeDescKey") or "") in ("shot-on-goal", "missed-shot", "goal") \
                and d.get("eventOwnerTeamId") == hid and isinstance(d.get("xCoord"), (int, float)):
            row["right" if d["xCoord"] > 0 else "left"] += 1
    for per, row in sorted(by_period.items(), key=lambda kv: kv[0] or 0):
        said = row["side"].most_common(1)[0][0] if row["side"] else "ABSENT"
        expect = "right" if said == "left" else "left" if said == "right" else "?"
        verdict = ("ok" if (expect == "right" and row["right"] >= row["left"]) or (expect == "left" and row["left"] >= row["right"])
                   else "CHECK" if said != "ABSENT" else "inferred from the shots")
        out.append(f"  period {per}: home defends {said}; home shots at the right end {row['right']}, "
                   f"at the left {row['left']} → {verdict}")
    owner = Counter()
    for p in plays:
        if str(p.get("typeDescKey") or "") != "blocked-shot":
            continue
        d = p.get("details") or {}
        o, shooter, blocker = d.get("eventOwnerTeamId"), team_of.get(str(d.get("shootingPlayerId"))), team_of.get(str(d.get("blockingPlayerId")))
        owner["the shooter's side" if o == shooter and o is not None else "the blocker's side" if o == blocker and o is not None else "neither / unknown"] += 1
    out.append(f"  a blocked shot's eventOwnerTeamId names: {dict(owner) or 'no blocked shots'}")
    return out


def table_report(pbp: dict) -> list[str]:
    from engine.sources import nhlrink
    out = ["\n=== 3. the scorer's table ==="]
    codes = Counter(str(p.get("situationCode") or "") for p in pbp.get("plays") or [] if isinstance(p, dict))
    out.append(f"  situation codes: {dict(codes.most_common(8))}")
    block = pbp.get("situation")
    out.append(f"  the feed's own situation block: {_shape(block) if block else 'ABSENT (no power play right now, or never carried)'}")
    home, away = pbp.get("homeTeam") or {}, pbp.get("awayTeam") or {}
    out.append(f"  the parser reads: {nhlrink._sit_block(block, str(home.get('abbrev') or ''), str(away.get('abbrev') or '')) or 'nothing'}")
    out.append(f"  clock: {_shape(pbp.get('clock'))}; gameState {pbp.get('gameState')!r}")
    return out


def ice_report(pbp: dict, shifts) -> list[str]:
    out = ["\n=== 4. who is on the ice ==="]
    if isinstance(shifts, Exception):
        return out + [f"  shift charts: {type(shifts).__name__}"]
    rows = [r for r in (shifts or {}).get("data") or [] if isinstance(r, dict)]
    plays = [p for p in pbp.get("plays") or [] if isinstance(p, dict) and p.get("timeInPeriod")]
    if not plays:
        return out + [f"  shift rows {len(rows)}; no plays to time them against"]
    last = plays[-1]
    per = int((last.get("periodDescriptor") or {}).get("number") or 0)
    t = _clock(last.get("timeInPeriod"))
    open_rows = sum(1 for r in rows if r.get("endTime") in (None, ""))
    on: dict = {}
    for r in rows:
        if r.get("typeCode") not in (None, 517) and str(r.get("typeCode")) != "517":
            continue
        if int(r.get("period") or 0) != per:
            continue
        a, b = _clock(r.get("startTime")), _clock(r.get("endTime"))
        if a is not None and t is not None and a <= t and (b is None or b > t):
            on.setdefault(str(r.get("teamAbbrev") or "?"), set()).add(str(r.get("playerId") or ""))
    ends = [(_clock(r.get("endTime")) or 0) for r in rows if int(r.get("period") or 0) == per]
    out.append(f"  shift rows {len(rows)}; rows with no end yet {open_rows}; latest play P{per} {last.get('timeInPeriod')}; "
               f"latest shift end this period {max(ends) // 60 if ends else '-'}:{(max(ends) % 60 if ends else 0):02d}")
    counts = {k: len(v) for k, v in on.items()}
    verdict = ("the chart is live: the men on the ice can be drawn" if counts and all(5 <= n <= 7 for n in counts.values()) and len(counts) == 2
               else "the chart lags the game: the page will not say who is on the ice")
    out.append(f"  on a shift at that moment: {counts or 'nobody'} → {verdict}")
    return out


def tracking_report(pbp: dict, fetch=_get) -> list[str]:
    out = ["\n=== 5. puck tracking (the goal visualizer) ==="]
    goals = [p for p in pbp.get("plays") or [] if isinstance(p, dict) and p.get("typeDescKey") == "goal"]
    if not goals:
        return out + ["  no goal yet in this game: run it again after one"]
    url = SPRITES.format(season=pbp.get("season"), game=pbp.get("id"), event=goals[-1].get("eventId"))
    out.append(f"  latest goal event {goals[-1].get('eventId')}: {url.split('/sprites/')[0]}/sprites/…")
    try:
        got = fetch(url)
    except Exception as exc:                                  # noqa: BLE001
        code = getattr(exc, "code", "")
        return out + [f"  answer: {type(exc).__name__} {code}".rstrip()]
    out.append(f"  answer: {_shape(got)}")
    frames = got if isinstance(got, list) else (got.get("frames") or got.get("data") or []) if isinstance(got, dict) else []
    if frames and isinstance(frames[0], dict):
        out.append(f"  frames {len(frames)}; a frame: {_shape(frames[0])}")
        objs = frames[0].get("onIce") or {}
        if isinstance(objs, dict) and objs:
            first = next(iter(objs.values()))
            out.append(f"  objects on the ice in a frame {len(objs)}; one: {_shape(first)}")
    return out


def report(pbp: dict, box: dict | None, shifts, fetch=_get) -> list[str]:
    from engine.sources import nhlrink
    lines = events_report(pbp) + ends_report(pbp) + table_report(pbp) + ice_report(pbp, shifts) + tracking_report(pbp, fetch)
    lines.append("\n=== 6. what the deep file will carry ===")
    doc = nhlrink.rink_doc(pbp, box, None)
    ev = doc.get("events") or []
    lines.append(f"  keys: {', '.join(sorted(doc))}")
    lines.append(f"  events {len(ev)}; with a spot {sum(1 for r in ev if 'x' in r)}; with no team "
                 f"{sum(1 for r in ev if not r.get('team') and r['kind'] not in ('start', 'end', 'stoppage'))}; "
                 f"players {len(doc.get('players') or {})}")
    lines.append(f"  box: {({t: (len(b['skaters']), len(b['goalies'])) for t, b in (doc.get('box') or {}).items()}) or 'none'}")
    lines.append(f"  venue: {doc.get('venue') or 'none'}; clock: {doc.get('clock') or 'none'}")
    return lines


def pick_game(prefer: str) -> tuple[str, str]:
    from engine.sources import nhldata
    from livescore_build import _et_today
    day = _et_today()
    rows = []
    for d in (day, day - _dt.timedelta(days=1)):
        try:
            rows += nhldata.parse_score_day(_get(f"{nhldata.API}/score/{d.isoformat()}"))
        except Exception:                                    # noqa: BLE001
            continue
    live = [r for r in rows if r.get("state") in ("LIVE", "CRIT")]
    done = [r for r in rows if r.get("final")]
    order = (live + done) if prefer == "in" else (done + live) if prefer == "post" else rows
    if not order:
        return "", "no game today or yesterday"
    return order[0]["game_id"], order[0]["state"]


def main(argv=None) -> int:
    from engine.sources import nhldata
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--game", default="")
    ap.add_argument("--prefer", default="in", choices=("in", "post", "any"))
    a = ap.parse_args(argv)
    game, state = (a.game, "asked for") if a.game else pick_game(a.prefer)
    print(f"NHL game {game or '-'}  state {state}")
    if not game:
        return 1
    pbp = _get(f"{nhldata.API}/gamecenter/{game}/play-by-play")
    try:
        box = _get(f"{nhldata.API}/gamecenter/{game}/boxscore")
    except Exception:                                        # noqa: BLE001
        box = None
    try:
        shifts = _get(SHIFTS.format(game=game))
    except Exception as exc:                                  # noqa: BLE001
        shifts = exc
    for line in report(pbp, box, shifts):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
