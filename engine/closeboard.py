"""The members' closing-line leaderboards: whose prices the market moved toward.

Ethan, 2026-10-29: "approve all. and build leaderboards" — after the first
paper's "rank leaderboards by CLV % ... not profit", and round five's note
that an opt-in board of members' own bets needed its own wording and his
yes. Each board ranks the average closing-line value of a member's saved
parlays' legs (engine/betclv): the price taken against where the market
closed, the honest measure of a bet before its result. Never a bet, a
team, a player, a stake or a result, and never profit: a board by profit
rewards betting more, and this one does not.

WHO IS ON IT. Only a member who turned it on (Settings → Your data, or the
board's own button: the settings key KEY, each change in the consent log)
and has a Social username. A block hides both ways, as on the feed. The
Friends board is the viewer and their friends, both sides of the
friendship (engine/karma.friend_ids, as the pick'em's and the karma's).

WHAT COUNTS (engine/betclv says why). A leg whose game started with its
parlay still saved (`closed`), at the price taken but never better than the
best price the books showed when the box first saw it
(betclv.verified_entry), with a close to compare against. "This week" is
Monday to Sunday, Eastern, by when each game started, and needs
MIN["week"] such legs to be ranked; the last 90 days need MIN["90d"].

TWO LOCKS, like the members' split (engine/consensus): QB_CLOSEBOARD=1 on
the box and the Privacy Policy's section with id="close-board". With either
missing nothing is read and the page offers nothing.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "web" / "privacy.html"
ENV = "QB_CLOSEBOARD"
POLICY_ID = "close-board"
#: The member's own choice, kept with their synced settings ("on" or not).
KEY = "closeboard"
ET = ZoneInfo("America/New_York")
WINDOWS = ("week", "90d")
#: Legs a member needs in the window to be ranked.
MIN = {"week": 5, "90d": 25}
DAYS = 90
TOP = 50
_policy = {"key": None, "ok": False}


def policy_ready(path: Path | None = None) -> bool:
    """Does the Privacy Policy have its section? Read again whenever the
    file (or which file) changes."""
    p = Path(path or POLICY)
    try:
        key = (str(p), p.stat().st_mtime_ns)
    except OSError:
        return False
    if _policy["key"] != key:
        _policy.update(key=key, ok=f'id="{POLICY_ID}"' in p.read_text(encoding="utf-8"))
    return bool(_policy["ok"])


def switched() -> bool:
    return os.environ.get(ENV, "").strip() == "1"


def enabled() -> bool:
    return switched() and policy_ready()


def on(settings) -> bool:
    """Did this member put themselves on the board?"""
    return isinstance(settings, dict) and settings.get(KEY) == "on"


def changed(old_settings, new_settings) -> str | None:
    """The consent log's words when a member's choice moved, else None."""
    a, b = on(old_settings), on(new_settings)
    return None if a == b else ("on the closing-line leaderboard" if b else "off the closing-line leaderboard")


def week_start(now: float) -> float:
    """Monday 00:00, Eastern, of the week ``now`` is in."""
    d = _dt.datetime.fromtimestamp(now, ET)
    monday = (d - _dt.timedelta(days=d.weekday())).date()
    return _dt.datetime(monday.year, monday.month, monday.day, tzinfo=ET).timestamp()


def _since(window: str, now: float) -> float:
    return week_start(now) if window == "week" else now - DAYS * 86400


def opted(conn) -> set:
    """Every account that put itself on the board."""
    out = set()
    try:
        rows = conn.execute("SELECT user_id, payload FROM user_data WHERE section = 'settings'").fetchall()
    except sqlite3.Error:
        return out
    for uid, payload in rows:
        try:
            if on(json.loads(payload)):
                out.add(int(uid))
        except (TypeError, ValueError):
            continue
    return out


def lines(conn, window: str, now: float, among: set | None = None) -> dict:
    """{user_id: (legs, beat, sum of clv)} over the window's closed,
    verified legs; ``among``, just these accounts."""
    from engine import betclv as BC
    BC.ensure_tables(conn)
    out: dict = {}
    for uid, entry, best, fair, first in conn.execute(
            "SELECT user_id, entry, best, fair, first_best FROM bet_clv WHERE closed IS NOT NULL "
            "AND closed >= ? AND closed <= ?", (_since(window, now), now)):
        if among is not None and int(uid) not in among:
            continue
        clv = BC.leg_clv(BC.verified_entry(entry, first), fair, best)
        if clv is None:
            continue
        n, beat, total = out.get(int(uid), (0, 0, 0.0))
        out[int(uid)] = (n + 1, beat + (clv > 0), total + clv)
    return out


def board(conn, window: str = "week", viewer=None, scope: str = "all", now: float | None = None) -> dict:
    """One leaderboard as the page draws it: {"enabled", "window", "scope",
    "min", "rows", "players", "on", "has_handle", "me"}. ``me`` is the
    viewer's own line whether ranked or not (``need`` says how many more
    legs), so the page can say where they stand."""
    if not enabled():
        return {"enabled": False}
    from engine import karma as K
    from engine import socialfeed as SF
    SF.ensure_tables(conn)
    t = time.time() if now is None else float(now)
    window = window if window in WINDOWS else "week"
    scope = "friends" if scope == "friends" and viewer else "all"
    need = MIN[window]
    who = opted(conn)
    viewer_on = viewer is not None and int(viewer) in who
    hide = SF.blocked_ids(conn, viewer)
    pals = (K.friend_ids(conn, viewer) | {int(viewer)}) if scope == "friends" else None
    among = {u for u in who if u not in hide and (pals is None or u in pals)}
    got = lines(conn, window, t, among)
    people = {}
    if got:
        marks = ",".join("?" * len(got))
        for r in conn.execute("SELECT user_id, handle, display_name, color, fav_team, verified, founder FROM "
                              f"feed_profiles WHERE handle IS NOT NULL AND handle != '' AND user_id IN ({marks})",
                              list(got)):
            people[int(r["user_id"])] = SF._person(r)
    table = []
    for uid, (n, beat, total) in got.items():
        if uid not in people or n < need:
            continue
        table.append({**people[uid], "n": n, "beat": beat, "clv": round(total / n * 100, 1),
                      "me": viewer is not None and uid == int(viewer)})
    table.sort(key=lambda x: (-x["clv"], -x["n"], str(x["handle"]).lower()))
    rank, last = 0, None
    for i, x in enumerate(table):
        if x["clv"] != last:
            rank, last = i + 1, x["clv"]
        x["rank"] = rank
    me = next((x for x in table if x["me"]), None)
    if me is None and viewer_on:
        n, beat, total = got.get(int(viewer), (0, 0, 0.0))
        me = {"n": n, "beat": beat, "clv": round(total / n * 100, 1) if n else None, "need": max(0, need - n)}
    has_handle = viewer is not None and bool(conn.execute(
        "SELECT 1 FROM feed_profiles WHERE user_id = ? AND handle IS NOT NULL AND handle != ''",
        (int(viewer),)).fetchone())
    return {"enabled": True, "window": window, "scope": scope, "min": need, "rows": table[:TOP],
            "players": len(table), "on": viewer_on, "has_handle": has_handle, "me": me}
