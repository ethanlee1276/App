"""The members' split on a game, and the members against the close —
pooled from what members log, never a person.

Ethan's second research paper (2026-10-29): "Qellys consensus. The share
of tracked bets on each side of a game" and "Users vs. the market. How
Qellys users' tracked bets did against the closing line", with its three
guardrails: "Only show a split once it covers 50+ bets so no one can be
picked out. Let users opt out of being counted. Never sell user-level
data."

TWO LOCKS, as engine/activity's: QB_SPLIT=1 (deploy/setenv.sh) AND the
Privacy Policy's own section on it (web/privacy.html, id="members-split").
It is a new use of what members log, so it waits for the wording Ethan
approves (docs/RETENTION.md §7 has the draft); the switch alone does
nothing. Then every member is counted unless they say no (Settings →
"Count my bets in the members' split", kept with their synced settings as
`split: "off"`; each change in the consent log, kind "split").

WHAT IS COUNTED. The game-line legs of members' open saved parlays — a
moneyline or a spread counts for its team, a total for over or under —
read from the synced My Bets, one leg one count, dated in the last
RECENT_DAYS. Never a player prop: a split on one player's line among a
handful of members points at somebody. A side's share is shown only once
the game has MIN_BETS legs on that market. Members against the close reads
the closing prices the box notes for saved parlays (engine/betclv): the
share of legs whose price beat the close, and the average, once MIN_BETS
legs are in.

Built at most every CACHE_S, from the accounts database; counts only, out.
Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "web" / "privacy.html"
ENV = "QB_SPLIT"
POLICY_ID = "members-split"
MIN_BETS = 50
RECENT_DAYS = 3
CLV_DAYS = 30
CACHE_S = 600
SIDES = ("moneyline", "spread")
_GAME = re.compile(r"^\s*([A-Za-z.]{2,5})\s*(?:@|vs\.?|at)\s*([A-Za-z.]{2,5})\s*$", re.I)
_policy: dict = {"key": None, "ok": False}
_cache: dict = {"at": 0.0, "key": None, "split": {}, "clv": None}


def policy_ready(path: Path | None = None) -> bool:
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
    """Both locks open: the switch, and the policy that describes it."""
    return switched() and policy_ready()


def why_off() -> str:
    if not switched():
        return f"switched off ({ENV} is not 1)"
    if not policy_ready():
        return (f"{ENV}=1, but the Privacy Policy has no section id=\"{POLICY_ID}\" yet "
                "(docs/RETENTION.md §7 has the wording to approve)")
    return ""


def counted(settings) -> bool:
    """Is this member in the split? Yes unless they said no."""
    return not (isinstance(settings, dict) and settings.get("split") == "off")


def changed(old_settings, new_settings) -> str | None:
    """The consent log's words when a member's choice moved, else None."""
    a, b = counted(old_settings), counted(new_settings)
    return None if a == b else ("counted in the members' split" if b else "not counted in the members' split")


def game_key(sport, game) -> str | None:
    """"nba:BOS@LAL" from a leg's sport and its "BOS @ LAL"."""
    m = _GAME.match(str(game or ""))
    sport = str(sport or "").lower()
    return f"{sport}:{m.group(1).upper()}@{m.group(2).upper()}" if m and sport else None


def _members(conn, now: float | None = None) -> dict:
    """{user_id: (settings, mybets rows)} for every member counted: in, and
    told of the change a week ago or more, or joined after it
    (engine/policynotice.may_count, the Privacy Policy's §13)."""
    out: dict = {}
    try:
        rows = conn.execute("SELECT user_id, section, payload FROM user_data WHERE section IN ('settings', 'mybets')"
                            ).fetchall()
    except sqlite3.Error:
        return out
    for uid, section, payload in rows:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            continue
        s, b = out.get(uid, ({}, []))
        if section == "settings":
            s = data if isinstance(data, dict) else {}
        else:
            got = data.get("rows") if isinstance(data, dict) else data
            b = got if isinstance(got, list) else []
        out[uid] = (s, b)
    out = {u: v for u, v in out.items() if counted(v[0])}
    from engine import policynotice as PN
    try:
        ok = PN.may_count(conn, out, now)
    except sqlite3.Error:
        return {}
    return {u: v for u, v in out.items() if u in ok}


def build(conn, now: float | None = None) -> dict:
    """{"nba:BOS@LAL": {"sides": {"BOS": n, ...}, "totals": {"over": n, "under": n}}} for every
    game a counted member's open saved parlay has a game-line leg on."""
    t = time.time() if now is None else float(now)
    since = (_dt.datetime.fromtimestamp(t, _dt.timezone.utc) - _dt.timedelta(days=RECENT_DAYS)).date().isoformat()
    out: dict = {}
    for _uid, (_s, bets) in _members(conn, t).items():
        for b in bets:
            if not isinstance(b, dict) or b.get("result") != "pending" or not isinstance(b.get("legs"), list):
                continue
            if str(b.get("date") or "")[:10] < since:
                continue
            for leg in b["legs"]:
                if not isinstance(leg, dict):
                    continue
                key = game_key(leg.get("sport"), leg.get("game"))
                market = str(leg.get("market") or "").lower()
                if not key:
                    continue
                g = out.setdefault(key, {"sides": {}, "totals": {}})
                if market in SIDES and leg.get("team"):
                    team = str(leg["team"]).upper()
                    g["sides"][team] = g["sides"].get(team, 0) + 1
                elif market == "total" and str(leg.get("side") or "").lower() in ("over", "under"):
                    side = str(leg["side"]).lower()
                    g["totals"][side] = g["totals"].get(side, 0) + 1
    return out


def members_clv(conn, now: float | None = None) -> dict | None:
    """{"n", "beat", "avg"} over counted members' noted legs in the last
    CLV_DAYS, once MIN_BETS legs are in; else None."""
    from engine import betclv as BC
    t = time.time() if now is None else float(now)
    who = set(_members(conn, t))
    if not who:
        return None
    try:
        rows = conn.execute("SELECT user_id, entry, best, fair FROM bet_clv WHERE at > ?",
                            (t - CLV_DAYS * 86400,)).fetchall()
    except sqlite3.Error:
        return None
    clvs = [c for uid, entry, best, fair in rows if uid in who
            for c in [BC.leg_clv(entry, fair, best)] if c is not None]
    if len(clvs) < MIN_BETS:
        return None
    return {"n": len(clvs), "beat": sum(c > 0 for c in clvs), "avg": round(sum(clvs) / len(clvs), 4)}


def _fresh(conn, now: float) -> None:
    # One build per database file every CACHE_S, however many requests ask
    # (each opens its own connection); an in-memory one is its own.
    try:
        key = conn.execute("PRAGMA database_list").fetchone()[2] or id(conn)
    except (sqlite3.Error, TypeError, IndexError):
        key = id(conn)
    if _cache["key"] != key or now - _cache["at"] >= CACHE_S:
        _cache.update(at=now, key=key, split=build(conn, now), clv=members_clv(conn, now))


def for_game(conn, sport, away, home, now: float | None = None) -> dict | None:
    """The split for one game as the page shows it: each market's shares
    and its count, only a market with MIN_BETS legs; None when neither."""
    if not enabled():
        return None
    t = time.time() if now is None else float(now)
    _fresh(conn, t)
    g = _cache["split"].get(f"{str(sport).lower()}:{str(away).upper()}@{str(home).upper()}")
    if not g:
        return None
    out = {}
    for name in ("sides", "totals"):
        n = sum(g[name].values())
        if n >= MIN_BETS:
            out[name] = {"n": n, "share": {k: round(v / n, 3) for k, v in sorted(g[name].items())}}
    return out or None


def against_the_close(conn, now: float | None = None) -> dict | None:
    """Members against the close, as the Edge Report shows it beside the reader's own."""
    if not enabled():
        return None
    _fresh(conn, time.time() if now is None else float(now))
    return _cache["clv"]
