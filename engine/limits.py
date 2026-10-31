"""A member's own weekly limit, and the alerts it silences.

Ethan's second research paper (2026-10-29, "Data, Retention & the ESPN
Playbook") lists "Self-set limits (alert pause, weekly bet cap)" among what
members tell us — "Settings, always visible ... Responsible-play tools, and
your best legal defense" — and its checklist: "Users who set a pause or
limit get zero promotional alerts until it ends."

THE LIMIT is the member's own number of dollars staked in a week, Monday to
Sunday, Eastern, kept with their synced settings (`limit_week`, 0 = none;
Settings → Limits). We take no bets, so nothing at a book is stopped: My
Bets says where the week stands each time a bet is logged, and once the
week's logged stakes reach the number, PROMO alerts stop for that member
until Monday (engine/pushalerts.send, engine/pushmine.flush and what a
knocked phone is shown). Their own tickets, their fantasy lineup, a game
they asked to be reminded of and people talking to them still arrive.

A break from alerts (Alerts → Take a break, engine/pushalerts.pause) stops
everything on that phone already. Setting, changing or clearing the limit
goes in the consent log (engine/consent, kind "limits").

Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import json
import sqlite3
import time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
#: The most a limit can say, in dollars: anything above is a typo.
MAX = 1_000_000
#: What a reached limit silences: every alert that invites a bet or a
#: visit — picks up, last night's record, picks on their players, the
#: away and morning lines, karma and pick'em nudges, their teams' kickoff,
#: big moments, finals and close finishes.
PROMO = ("posted", "settled", "watches", "away", "today", "karma", "pickem", "kickoff", "clutch", "finals",
         "closegame")


def limit_of(settings) -> float:
    """The member's weekly limit in dollars, 0 for none or nonsense."""
    try:
        v = float((settings or {}).get("limit_week") or 0)
    except (TypeError, ValueError, AttributeError):
        return 0.0
    return v if 0 < v <= MAX else 0.0


def week_of(now: float | None = None) -> tuple[str, str]:
    """(Monday, Sunday) of the Eastern week holding ``now``, as ISO dates."""
    d = _dt.datetime.fromtimestamp(time.time() if now is None else float(now), ET).date()
    monday = d - _dt.timedelta(days=d.weekday())
    return monday.isoformat(), (monday + _dt.timedelta(days=6)).isoformat()


def staked(bets, week: tuple[str, str]) -> float:
    """Dollars staked on bets dated inside ``week``, whatever became of them."""
    lo, hi = week
    total = 0.0
    for b in bets or []:
        if not isinstance(b, dict):
            continue
        day = str(b.get("date") or "")[:10]
        try:
            s = float(b.get("stake") or 0)
        except (TypeError, ValueError):
            continue
        if lo <= day <= hi and 0 < s <= MAX:
            total += s
    return round(total, 2)


def _payload(conn, user_id, section: str):
    row = conn.execute("SELECT payload FROM user_data WHERE user_id = ? AND section = ?",
                       (int(user_id), section)).fetchone()
    try:
        return json.loads(row[0]) if row else None
    except (TypeError, ValueError):
        return None


def standing(conn, user_id, now: float | None = None) -> dict | None:
    """{"limit", "staked", "week"} for a member with a limit, else None."""
    try:
        lim = limit_of(_payload(conn, user_id, "settings"))
        if not lim:
            return None
        data = _payload(conn, user_id, "mybets")
    except sqlite3.Error:
        return None
    week = week_of(now)
    rows = data.get("rows") if isinstance(data, dict) else data
    return {"limit": lim, "staked": staked(rows if isinstance(rows, list) else [], week), "week": week}


def reached(conn, now: float | None = None, among=None) -> set:
    """The members whose logged stakes this week have reached their limit;
    ``among``: only these accounts (the ones a send is about), so the minute's
    send reads the few it is sending to, not every member's settings."""
    try:
        if among is None:
            rows = conn.execute("SELECT user_id, payload FROM user_data WHERE section = 'settings'").fetchall()
        else:
            ids = sorted({int(u) for u in among if u is not None})
            rows = []
            for i in range(0, len(ids), 500):
                part = ids[i:i + 500]
                rows += conn.execute("SELECT user_id, payload FROM user_data WHERE section = 'settings' "
                                     f"AND user_id IN ({','.join('?' * len(part))})", part).fetchall()
    except sqlite3.Error:
        return set()
    out = set()
    for uid, payload in rows:
        try:
            if not limit_of(json.loads(payload)):
                continue
        except (TypeError, ValueError):
            continue
        st = standing(conn, uid, now)
        if st and st["staked"] >= st["limit"]:
            out.add(uid)
    return out


def changed(old_settings, new_settings) -> str | None:
    """The consent log's words for a limit set, changed or cleared; None
    when the limit did not move."""
    a, b = limit_of(old_settings), limit_of(new_settings)
    if a == b:
        return None
    return f"weekly limit ${b:,.0f}" if b else "weekly limit off"
