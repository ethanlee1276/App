"""The game reports' parlays, followed while their games are played (20 November 2026).

Ethan, 2026-11-19: "do any other work and ideas you think will help the site in any way ... ive been coming up
with so many ideas and adding and you havent done any ideas. i just want some help", in the same message that
asks for the parlays to win. A member who played a report's ticket had nowhere to watch it. The Live tab follows
the Edge and Most Likely picks (engine/livepicks.TRACKER_CATEGORIES) and the slips a reader saved
(engine/sliplive.room_tickets); a game report's tickets were neither, so the one bet the site builds for every
game was the one it went quiet on at kickoff.

WHAT IT READS: nothing new is fetched or bought. The tickets are the board's own (`game_parlays`, where a started
game's stay as they stood before the start: engine/reportkeep). Each leg's number is engine/sliplive.live_state,
off the twelve-second scoreboard and the box files the live loop already writes, in every league that has them.

WHAT IT SAYS. For each game under way, and each one that has ended while its tickets are still on the board:
every posted ticket with its legs, the number each has so far, what each still needs in one plain line, and where
the ticket stands (alive with how many legs are in, down to its last leg, won, or lost at the first leg that
missed). A ticket held on paper is not a bet the site offers, so it is not listed.

A MEMBER'S, as the tickets are (`game_parlays` is a paid key, engine/gate): the server gates the endpoint, and a
reader without the membership is told how many tickets are being followed and nothing else (`counts`). Pure
assembly over boards and files the caller names; never raises out of `snapshot`.
"""
from __future__ import annotations

import math
import time

from . import gameparlays as GP
from .sliplive import SCORER_MARKETS, live_state

#: The board's lists a game's posted tickets sit in, with the kind `gameparlays.card` titles each by, in the
#: order the Report Picks page draws them (js/report.js gameTickets: the two-leg tickets lead).
LISTS = (("twos", "two"), ("threes", "three"), ("scorers", "scorers"))
#: The live states a ticket is followed in.
FOLLOWED = ("live", "final")
#: Seconds one snapshot is served for: the scoreboard it reads is written every twelve.
CACHE_S = 8.0

_CACHE: dict = {"at": 0.0, "key": None, "doc": None}


def _num(v) -> str:
    return f"{float(v):g}"


def need_words(side: str, line, cur) -> str:
    """A leg in play, in one plain line: how many more an over needs, how many an under can still give up, or
    that it is already decided. A whole-number line pushes at the number, so an over needs one past it. The
    page's own words for a saved slip's leg (js/slip.js needWords), written here for the report's tickets."""
    try:
        line, cur = float(line), float(cur)
    except (TypeError, ValueError):
        return ""
    under = side in ("under", "no")
    if line == 0.5:
        if cur >= 1:
            return "Lost: one already" if under else "Done: has one"
        return "Holding: none yet" if under else "Needs one"
    first, last = math.floor(line) + 1, math.ceil(line) - 1     # the first number an over wins at, the last an under does
    if not under:
        return "Cleared" if cur >= first else f"Needs {_num(first - cur)} more"
    if cur == line:
        return "On the number: a push now, one more loses"
    return "Past the number" if cur > last else f"Can give up {_num(last - cur)} more"


def standing(legs: list) -> dict:
    """Where a ticket stands from its legs' results: lost at the first leg that missed, won when every leg that
    counted is in, else alive with how many are in and how many are still to be decided."""
    res = [l.get("result") for l in legs]
    lost, won = res.count("lost"), res.count("won")
    left = sum(1 for r in res if r not in ("won", "lost", "push"))
    state = "lost" if lost else "alive" if left else "won" if won else "push"
    out = {"state": state, "won": won, "left": left, "of": len(legs)}
    if state == "lost":
        miss = next(l for l in legs if l.get("result") == "lost")
        out["words"] = f"Lost: {miss.get('player') or 'a leg'} missed"
    elif state == "won":
        out["words"] = f"Won: {'both' if len(legs) == 2 else 'all ' + str(len(legs))} legs hit" if won == len(legs) \
            else f"Won: {won} of {len(legs)} legs hit, the other pushed"
    elif state == "push":
        out["words"] = "Every leg landed on its number: a push"
    elif left == 1 and len(legs) > 1:
        last = next(l for l in legs if l.get("result") not in ("won", "lost", "push"))
        out["words"] = f"One leg to go: {last.get('player') or 'the last one'}"
    else:
        out["words"] = f"Alive: {won} of {len(legs)} legs in" if won else "Alive: no leg in yet"
    return out


def _leg(sport: str, g: dict, raw: dict, said: dict, fast_dir, now) -> dict:
    market = raw.get("market")
    side = str(raw.get("side") or "").lower()
    st = live_state({"league": sport, "player": raw.get("player"), "market": market, "side": side,
                     "line": raw.get("line"), "row": {"home": g.get("home"), "away": g.get("away")}},
                    fast_dir, now) or {}
    line = 0.5 if market in SCORER_MARKETS else raw.get("line")
    out = {"player": raw.get("player") or "", "team": raw.get("team") or "", "pick": said.get("pick") or "",
           "market": market or "", "side": side, "line": line}
    if raw.get("headshot"):
        out["headshot"] = raw["headshot"]
    cur = st.get("current")
    if cur is not None:
        out["current"] = cur
        if st.get("state") == "live" and not st.get("result"):
            out["need"] = need_words(side, line, cur)
    if st.get("result"):
        out["result"] = st["result"]
    elif st.get("note"):
        out["note"] = st["note"]
    return out


def game_tickets(sport: str, g: dict, fast_dir=None, now: float | None = None) -> dict | None:
    """One game's posted tickets with each leg's live number, or None when the game is not under way or over on
    the live scoreboard, or has no posted ticket."""
    if not isinstance(g, dict) or not g.get("home") or not g.get("away"):
        return None
    if not any(g.get(key) for key, _kind in LISTS):
        return None
    st = live_state({"league": sport, "row": {"home": g["home"], "away": g["away"]}}, fast_dir, now) or {}
    if st.get("state") not in FOLLOWED:
        return None
    tickets = []
    for key, kind in LISTS:
        for n, t in enumerate(g.get(key) or [], 1):
            raw = [l for l in (t or {}).get("legs") or [] if isinstance(l, dict)]
            if not raw:
                continue
            said = GP.card(t, n, kind, sport)
            legs = [_leg(sport, g, l, c, fast_dir, now) for l, c in zip(raw, said["legs"])]
            tickets.append({"kind": kind, "title": said["title"], "chance": round(float(t.get("joint") or 0), 4),
                            "legs": legs, **standing(legs)})
    if not tickets:
        return None
    return {"away": g["away"], "home": g["home"], "date": g.get("date") or "", "state": st["state"],
            "clock": st.get("clock") or "", "away_score": st.get("away_score"), "home_score": st.get("home_score"),
            "tickets": tickets}


def league(sport: str, board: dict | None, fast_dir=None, now: float | None = None) -> list:
    """Every followed game of one league's board, the ones still being played first."""
    gp = (board or {}).get("game_parlays")
    games = []
    for g in (gp.get("games") if isinstance(gp, dict) else None) or []:
        try:
            got = game_tickets(sport, g, fast_dir, now)
        except Exception as exc:                                 # noqa: BLE001
            print(f"  ⚠️ a game's live tickets not read for {sport} ({type(exc).__name__}: {exc})")
            got = None
        if got:
            games.append(got)
    games.sort(key=lambda x: x["state"] != "live")
    return games


def snapshot(boards, fast_dir=None, now: float | None = None) -> dict:
    """``{"at", "leagues": [{"league", "games"}], "live", "tickets"}``; a league with nothing followed is left
    out. ``boards`` is ``{sport: board}`` or a function that returns it: every member's Live tab asks, the
    scoreboard under the answer is written every twelve seconds, so one answer is served from memory for
    CACHE_S and the boards are only loaded when it has to be made again."""
    now = time.time() if now is None else now
    where = str(fast_dir or "")
    if _CACHE["doc"] is not None and _CACHE["key"] == where and 0 <= now - _CACHE["at"] < CACHE_S:
        return _CACHE["doc"]
    loaded = boards() if callable(boards) else boards
    leagues = [{"league": sp, "games": games} for sp, b in (loaded or {}).items()
               if (games := league(sp, b, fast_dir, now))]
    every = [g for x in leagues for g in x["games"]]
    doc = {"at": int(now), "leagues": leagues, "live": sum(1 for g in every if g["state"] == "live"),
           "tickets": sum(len(g["tickets"]) for g in every)}
    _CACHE.update(at=now, key=where, doc=doc)
    return doc


def forget() -> None:
    """Drop the answer kept in memory (a test's two snapshots of two sets of boards)."""
    _CACHE.update(at=0.0, key=None, doc=None)


def counts(doc: dict) -> dict:
    """What a reader without the membership is told: how many tickets are followed in how many games."""
    games = [g for x in doc.get("leagues") or [] for g in x.get("games") or []]
    return {"locked": True, "at": doc.get("at"), "live": doc.get("live") or 0, "games": len(games),
            "tickets": doc.get("tickets") or 0}
