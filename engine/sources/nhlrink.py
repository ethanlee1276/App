"""Every event of an NHL game on the ice, for the live page.

Ethan, 2026-10-15, with two renders of an NHL play-by-play screen: "figure
out what data we can use for the live play by play screen for nhl like live
posetions and puck tracking". The league's own play-by-play — the keyless
host `engine/sources/nhlpbp` already reads for the expected-goals model —
places every EVENT on the ice: each faceoff, hit, takeaway, giveaway, shot,
block, goal and penalty, with x and y in feet from centre ice, who did it
and to whom, and how many skaters each side had (`situationCode`). The
roster beside it carries every man's number, position and headshot.

WHAT IS AND IS NOT THERE. Not puck tracking: the feed records where each
event happened, not where the puck is between events, and nobody publishes
continuous puck or skater positions live. The page draws the events where
they happened, newest brightest — the play's path — and names whose puck
it is only after an event that settles it (a faceoff won, a takeaway, a
giveaway). The league does publish tracked positions for the seconds
before each GOAL (nhl.com's goal visualizer); `rinkprobe.py` checks that
feed's shape on the box before anything is built on it.

THE SIDE. The feed's x runs the length of the rink in the arena's own
frame, so a team's shots switch ends every period. Every row here is turned
so the HOME team always attacks the right-hand net (x > 0) and the away
team the left — the convention the page's art and scoreboard share — by the
play's own `homeTeamDefendingSide`, or, for a period without it, by the end
the home team's shots went toward. Turning the rink end for end is a half
turn: x and y both change sign.

THE TEAM OF A PLAY is its player's, read off the roster — the shooter's
for a shot, a miss or a block (the blocker's side is `team2`), the winner's
for a faceoff, the hitter's for a hit — and not the feed's
`eventOwnerTeamId`, whose meaning for a blocked shot this box has not
confirmed (the probe reports it). The owner is the fallback when the roster
has no such man.

Pure functions, read by key name. A play it cannot place still lists,
without a spot; a code word that is not a short code is dropped.
"""
from __future__ import annotations

import re

from . import nhlpbp
from .nhldata import _saves

API = nhlpbp.API
#: The league's event types and what each is called in a row; anything
#: else lists as "other".
KINDS = {"faceoff": "faceoff", "hit": "hit", "giveaway": "giveaway", "takeaway": "takeaway",
         "shot-on-goal": "sog", "missed-shot": "miss", "blocked-shot": "block", "goal": "goal",
         "penalty": "penalty", "stoppage": "stoppage", "delayed-penalty": "delayed",
         "period-start": "start", "period-end": "end", "game-end": "end"}
#: The man whose team a play belongs to.
ACTOR = {"faceoff": "winningPlayerId", "hit": "hittingPlayerId", "giveaway": "playerId",
         "takeaway": "playerId", "sog": "shootingPlayerId", "miss": "shootingPlayerId",
         "block": "shootingPlayerId", "goal": "scoringPlayerId", "penalty": "committedByPlayerId"}
#: The second man and what he did.
SECOND = {"faceoff": ("losingPlayerId", "lost"), "hit": ("hitteePlayerId", "hit"),
          "block": ("blockingPlayerId", "blocked"), "penalty": ("drawnByPlayerId", "drawn"),
          "sog": ("goalieInNetId", "goalie"), "goal": ("goalieInNetId", "goalie")}
PERIOD_S = 1200
#: A feed spot is kept inside the boards, with a foot to spare for rounding.
HALF_LENGTH, HALF_WIDTH = 101.0, 43.5
_CODE = re.compile(r"^[a-z0-9-]{1,40}$")
_CLOCK = re.compile(r"^\d{1,2}:\d{2}$")


def _txt(v) -> str:
    return nhlpbp._txt(v)


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _code(v) -> str:
    """A short code word ("hooking", "icing", "wide-of-net") or ""."""
    s = str(v or "").strip().lower()
    return s if _CODE.match(s) else ""


def _secs(clock) -> int | None:
    s = str(clock or "")
    if not _CLOCK.match(s):
        return None
    m, sec = s.split(":")
    return int(m) * 60 + int(sec)


def situation(code) -> dict | None:
    """``{"away": skaters, "home": skaters, "pp": "home"|"away"|"", "en":
    "home"|"away"|""}`` from a four-digit code (away goalie, away skaters,
    home skaters, home goalie). A side with its goalie pulled counts its
    extra attacker as a skater but not as a power play, as nhlpbp reads it;
    ``en`` is the side whose net is empty."""
    c = str(code or "")
    if len(c) != 4 or not c.isdigit():
        return None
    ag, ask, hsk, hg = (int(ch) for ch in c)
    if not (3 <= ask <= 6 and 3 <= hsk <= 6 and ag in (0, 1) and hg in (0, 1)):
        return None
    a, h = ask - (ag == 0), hsk - (hg == 0)
    return {"away": ask, "home": hsk, "pp": "home" if h > a else "away" if a > h else "",
            "en": "away" if ag == 0 else "home" if hg == 0 else ""}


def players_of(payload: dict) -> dict:
    """``{player id: {"name", "team_id", "num", "pos", "face"}}`` off the
    feed's roster."""
    out = {}
    for r in (payload or {}).get("rosterSpots") or []:
        if not isinstance(r, dict) or not r.get("playerId"):
            continue
        face = str(r.get("headshot") or "")
        out[str(r["playerId"])] = {
            "name": f"{_txt(r.get('firstName'))} {_txt(r.get('lastName'))}".strip(),
            "team_id": r.get("teamId"), "num": _int(r.get("sweaterNumber")),
            "pos": str(r.get("positionCode") or "")[:2],
            "face": face if face.startswith("https://") else "",
        }
    return out


def _flips(plays: list, home_id) -> dict:
    """``{period: True}`` for each period the home team attacks the LEFT
    net in — by the play's `homeTeamDefendingSide`, or the mean x of the
    home team's unblocked attempts where a period never says."""
    said, shots = {}, {}
    for pl in plays:
        per = _int((pl.get("periodDescriptor") or {}).get("number")) or 0
        side = str(pl.get("homeTeamDefendingSide") or "")
        if side in ("left", "right"):
            said.setdefault(per, side == "right")
            continue
        d = pl.get("details") or {}
        if str(pl.get("typeDescKey") or "") in ("shot-on-goal", "missed-shot", "goal") \
                and d.get("eventOwnerTeamId") == home_id and _num(d.get("xCoord")) is not None:
            shots.setdefault(per, []).append(float(d["xCoord"]))
    for per, xs in shots.items():
        if per not in said and xs:
            said[per] = sum(xs) / len(xs) < 0
    return said


def rink_rows(payload: dict) -> list[dict]:
    """Every play of the game in order, turned so home attacks the right."""
    p = payload or {}
    home, away = p.get("homeTeam") or {}, p.get("awayTeam") or {}
    hid, aid = home.get("id"), away.get("id")
    abbr = {hid: str(home.get("abbrev") or ""), aid: str(away.get("abbrev") or "")}
    roster = players_of(p)
    plays = [pl for pl in p.get("plays") or [] if isinstance(pl, dict)]
    flips = _flips(plays, hid)

    def team_of(pid) -> str:
        return abbr.get((roster.get(str(pid)) or {}).get("team_id"), "") if pid else ""

    def name_of(pid) -> str:
        return (roster.get(str(pid)) or {}).get("name", "") if pid else ""

    rows = []
    for pl in plays:
        per = pl.get("periodDescriptor") or {}
        if str(per.get("periodType") or "") == "SO":
            continue
        period = _int(per.get("number")) or 0
        kind = KINDS.get(str(pl.get("typeDescKey") or ""), "other")
        d = pl.get("details") or {}
        actor = d.get(ACTOR[kind]) if kind in ACTOR else None
        team = team_of(actor) or abbr.get(d.get("eventOwnerTeamId"), "")
        inper = _secs(pl.get("timeInPeriod"))
        row = {"id": _int(pl.get("eventId")) or 0, "period": period,
               "clock": str(pl.get("timeRemaining") or "") if _CLOCK.match(str(pl.get("timeRemaining") or "")) else "",
               "elapsed": (max(period, 1) - 1) * PERIOD_S + (inper or 0), "kind": kind, "team": team}
        x, y = _num(d.get("xCoord")), _num(d.get("yCoord"))
        if x is not None and y is not None and abs(x) <= HALF_LENGTH and abs(y) <= HALF_WIDTH:
            if flips.get(period):
                x, y = -x, -y
            row["x"], row["y"] = round(x, 1), round(y, 1)
        if situation(pl.get("situationCode")):
            row["sc"] = str(pl.get("situationCode"))
        if actor:
            row["player"] = name_of(actor)
            num = (roster.get(str(actor)) or {}).get("num")
            if num is not None:
                row["num"] = num
        if kind in SECOND and d.get(SECOND[kind][0]):
            other = d.get(SECOND[kind][0])
            row["player2"], row["role2"] = name_of(other), SECOND[kind][1]
            if kind == "block":
                row["team2"] = team_of(other)
        if kind == "goal":
            row["assists"] = [n for n in (name_of(d.get("assist1PlayerId")), name_of(d.get("assist2PlayerId"))) if n]
            a, h = _int(d.get("awayScore")), _int(d.get("homeScore"))
            if a is not None and h is not None:
                row["score"] = [a, h]
        if kind in ("sog", "goal", "miss", "block") and _code(d.get("shotType")):
            row["shot"] = _code(d.get("shotType"))
        if kind == "sog":
            a, h = _int(d.get("awaySOG")), _int(d.get("homeSOG"))
            if a is not None and h is not None:
                row["sog"] = [a, h]
        if kind in ("miss", "stoppage") and _code(d.get("reason")):
            row["reason"] = _code(d.get("reason"))
        if kind == "penalty":
            if _code(d.get("descKey")):
                row["penalty"] = _code(d.get("descKey"))
            mins = _int(d.get("duration"))
            if mins is not None and 0 < mins <= 10:
                row["minutes"] = mins
            if _code(str(d.get("typeCode") or "").lower()):
                row["ptype"] = _code(str(d.get("typeCode")).lower())
        rows.append(row)
    return rows


def _xg_by_event(payload: dict, xg_fn) -> dict:
    """``{event id: our expected goals}`` for every unblocked attempt, off
    the same shot rows the model is fitted on."""
    out = {}
    for s in nhlpbp.parse_shots(payload):
        if s.get("kind") in ("goal", "sog", "miss"):
            try:
                out[int(s["event_id"])] = round(float(xg_fn(s)), 3)
            except (TypeError, ValueError, KeyError):
                continue
    return out


def box_lines(box: dict, roster: dict | None = None) -> dict:
    """``{team: {"skaters": [...], "goalies": [...]}}`` off the league's box
    score: number, name, position, ice time and the game line."""
    roster = roster or {}
    box = box or {}
    stats = box.get("playerByGameStats") or {}
    out = {}
    for side in ("awayTeam", "homeTeam"):
        team = str((box.get(side) or {}).get("abbrev") or "")
        block = stats.get(side) or {}
        if not team or not isinstance(block, dict):
            continue
        name = lambda r: (roster.get(str(r.get("playerId") or "")) or {}).get("name") or _txt(r.get("name"))
        skaters = []
        for group in ("forwards", "defense"):
            for r in block.get(group) or []:
                if not isinstance(r, dict):
                    continue
                fo = _num(r.get("faceoffWinningPctg"))
                skaters.append({
                    "pid": str(r.get("playerId") or ""), "name": name(r), "num": _int(r.get("sweaterNumber")),
                    "pos": str(r.get("position") or ("D" if group == "defense" else "F"))[:2],
                    "toi": str(r.get("toi") or "") if _CLOCK.match(str(r.get("toi") or "")) else "",
                    "g": _int(r.get("goals")) or 0, "a": _int(r.get("assists")) or 0,
                    "sog": _int(r.get("sog") if r.get("sog") is not None else r.get("shots")) or 0,
                    "pm": _int(r.get("plusMinus")) or 0, "hits": _int(r.get("hits")) or 0,
                    "blk": _int(r.get("blockedShots")) or 0, "pim": _int(r.get("pim")) or 0,
                    "fo": round(fo * 100) if fo is not None and 0 <= fo <= 1 else None,
                    "shifts": _int(r.get("shifts")),
                })
        goalies = []
        for r in block.get("goalies") or []:
            if not isinstance(r, dict):
                continue
            sv, sa = _saves(r)
            toi = str(r.get("toi") or "")
            if (not _CLOCK.match(toi) or toi in ("0:00", "00:00")) and not sa:
                continue                       # dressed as the backup, never played
            goalies.append({"pid": str(r.get("playerId") or ""), "name": name(r), "num": _int(r.get("sweaterNumber")),
                            "toi": toi if _CLOCK.match(toi) else "", "sv": int(sv), "sa": int(sa),
                            "ga": _int(r.get("goalsAgainst")) or 0, "starter": bool(r.get("starter"))})
        out[team] = {"skaters": skaters, "goalies": goalies}
    return out


def _sit_block(block, home: str, away: str) -> dict:
    """The feed's own power-play block, when it carries one: the side on
    the power play and the time left on it."""
    if not isinstance(block, dict):
        return {}
    sit = situation(block.get("situationCode"))
    left = str(block.get("timeRemaining") or "")
    if not sit or not _CLOCK.match(left):
        return {}
    return {"pp": {"home": home, "away": away}.get(sit["pp"], ""), "left": left,
            "away": sit["away"], "home": sit["home"]}


def rink_doc(payload: dict, box: dict | None = None, xg_fn=None) -> dict:
    """The block the live page reads: the events, the men, the box, the
    clock and our expected goals on each attempt when the model is on the
    box (``xg_fn`` takes one nhlpbp shot row)."""
    p = payload or {}
    home, away = p.get("homeTeam") or {}, p.get("awayTeam") or {}
    habbr, aabbr = str(home.get("abbrev") or ""), str(away.get("abbrev") or "")
    rows = rink_rows(p)
    doc = {"game_id": _int(p.get("id")) or 0, "home": habbr, "away": aabbr, "events": rows}
    if _int(p.get("season")):
        doc["season"] = _int(p.get("season"))
    if _int(p.get("gameType")) in (1, 2, 3):
        doc["game_type"] = _int(p.get("gameType"))      # 3 is the playoffs: overtime runs twenty minutes
    roster = players_of(p)
    abbr = {home.get("id"): habbr, away.get("id"): aabbr}
    doc["players"] = {pid: {"name": r["name"], "team": abbr.get(r["team_id"], ""), "num": r["num"],
                            "pos": r["pos"], "face": r["face"]} for pid, r in roster.items() if r["name"]}
    venue = _txt(p.get("venue"))
    if venue and len(venue) <= 60:
        doc["venue"] = {"name": venue}
        city = _txt(p.get("venueLocation"))
        if city and len(city) <= 40:
            doc["venue"]["city"] = city
    clock = p.get("clock") or {}
    per = p.get("periodDescriptor") or {}
    if isinstance(clock, dict) and _int(per.get("number")):
        doc["clock"] = {"period": _int(per.get("number")), "type": str(per.get("periodType") or "")[:3],
                        "left": str(clock.get("timeRemaining") or "") if _CLOCK.match(str(clock.get("timeRemaining") or "")) else "",
                        "intermission": bool(clock.get("inIntermission")), "running": bool(clock.get("running"))}
    state = str(p.get("gameState") or "")
    if state.isalpha() and len(state) <= 5:
        doc["state"] = state
    sit = _sit_block(p.get("situation"), habbr, aabbr)
    if sit:
        doc["situation"] = sit
    if box:
        try:
            doc["box"] = box_lines(box, roster)
        except Exception:                                    # noqa: BLE001
            pass                       # the events stand without the box
    if xg_fn is not None:
        try:
            got = _xg_by_event(p, xg_fn)
        except Exception:                                    # noqa: BLE001
            got = {}
        for r in rows:
            if r["id"] in got:
                r["xg"] = got[r["id"]]
        doc["xg"] = bool(got)
    return doc
