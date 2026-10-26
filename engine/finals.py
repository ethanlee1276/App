"""Final scores by push: a game you follow ends, your phone says how.

The ideas list (2026-10-25, "the live game as a place to be", item 6,
"recap by push"): when a game of a team you follow (or a player you
follow plays in) goes final, one alert with the final score, the play of
the game and the night's best line — the game page's own "The game in 30
seconds" card (js/detail.js recapFacts / recapTop), said on the lock
screen, a tap into the game.

Topic "finals", its own switch on the Alerts page: a final score is not
the big moment the "clutch" switch was turned on for. Public facts — the
score, the box — so anyone who follows gets it, member or not, and it
carries no pick.

ONCE A GAME, AND ONLY FRESH. A game is told the first pass that finds its
deep file final (`push_final_seen`), and only when that file was written in
the last FRESH_S: a game that ended while the box was down for hours is
not news by the time it comes back. Quiet hours do not hold it (the
member's own game, like their tickets), and it is worth showing for
TTL_S.

Run from engine/pushmine.run_once's minute, after the big moments.
Standard library only.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from engine import alerts as AL
from engine import pushmine as PM

TOPIC = "finals"
#: A final written longer ago than this is not told (see above).
FRESH_S = 30 * 60
KEEP_S = 3 * 86400
_mtimes: dict = {}


def ensure_tables(conn) -> None:
    PM.ensure_tables(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS push_final_seen (game TEXT PRIMARY KEY, at REAL NOT NULL)")
    conn.commit()


def _n(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _fmt(v) -> str:
    v = _n(v)
    return str(int(v)) if v == int(v) else f"{v:g}"


def best_line(doc: dict) -> str:
    """The night's best line off the box, scored per sport as the page does
    (js/detail.js recapTop): ``"Joe Burrow (CIN): 312 pass yds, 2 TD"``."""
    league = str(doc.get("league") or "")
    rows = [r for r in doc.get("players") or [] if isinstance(r, dict)]

    def st(r, k):
        return _n((r.get("stats") or {}).get(k))

    def line(r):
        return r.get("line") or {}

    if league == "mlb":
        def score(r):
            p, b = line(r).get("pitching"), line(r).get("batting") or {}
            return 1.5 * _n(p.get("k")) if p else 3 * _n(b.get("hr")) + _n(b.get("h")) + _n(b.get("rbi"))
    elif league == "nhl":
        def score(r):
            return 3 * st(r, "goals") + 2 * st(r, "assists") + st(r, "saves") / 10
    elif league in ("nfl", "cfb"):
        def score(r):
            return (st(r, "pass_yds") / 2.5 + st(r, "rush_yds") + st(r, "rec_yds")
                    + 20 * (st(r, "pass_td") + st(r, "rush_td") + st(r, "rec_td")))
    else:
        def score(r):
            return st(r, "pts") + st(r, "reb") + st(r, "ast")
    if not rows:
        return ""
    best = max(rows, key=score)
    if score(best) <= 0:
        return ""
    s, ln = best.get("stats") or {}, line(best)
    if ln.get("batting"):
        b = ln["batting"]
        words = f"{_fmt(b.get('h'))}-for-{_fmt(b.get('ab'))}" + (f", {_fmt(b['hr'])} HR" if _n(b.get("hr")) else "") \
            + (f", {_fmt(b['rbi'])} RBI" if _n(b.get("rbi")) else "")
    elif ln.get("pitching"):
        p = ln["pitching"]
        words = f"{p.get('ip') or 0} IP, {_fmt(p.get('k'))} K"
    elif league == "nhl":
        words = f"{_fmt(s.get('saves'))} saves" if _n(s.get("saves")) else f"{_fmt(s.get('goals'))} G, {_fmt(s.get('assists'))} A"
    elif league in ("nfl", "cfb"):
        td = _n(s.get("pass_td")) + _n(s.get("rush_td")) + _n(s.get("rec_td"))
        parts = [f"{_fmt(s[k])} {w}" for k, w in (("pass_yds", "pass yds"), ("rush_yds", "rush yds"), ("rec_yds", "rec yds"))
                 if _n(s.get(k))] + ([f"{_fmt(td)} TD"] if td else [])
        words = ", ".join(parts[:3])
    else:
        words = f"{_fmt(s.get('pts'))} pts, {_fmt(s.get('reb'))} reb, {_fmt(s.get('ast'))} ast"
    return f"{best.get('player')} ({best.get('team')}): {words}"


def _rows(doc: dict) -> list:
    if doc.get("league") == "mlb":
        return [e for e in doc.get("events") or [] if isinstance(e, dict) and e.get("kind") == "atbat"]
    return [p for p in doc.get("plays") or [] if isinstance(p, dict)]


def message(doc: dict) -> tuple | None:
    """``(title, body)`` for a final deep file, or None when it has no score."""
    lv = doc.get("live") or {}
    a, h = lv.get("away_score"), lv.get("home_score")
    if not isinstance(a, (int, float)) or not isinstance(h, (int, float)):
        return None
    home, away = str(doc.get("home") or ""), str(doc.get("away") or "")
    title = f"Final: {away} {_fmt(a)}–{_fmt(h)} {home}"
    parts = []
    pog = max(_rows(doc), key=lambda r: _n(r.get("rating")), default=None)
    if pog is not None and _n(pog.get("rating")) > 0:
        _t, said = PM.clutch_line(doc, dict(pog, rating=None))
        parts.append(f"Play of the game: {said.rstrip('.')} ({_n(pog.get('rating')):.1f}).")
    top = best_line(doc)
    if top:
        parts.append(f"Best line: {top}.")
    return title, " ".join(parts) or "The game is over."


def _follows(watches: list, doc: dict) -> bool:
    sides = {str(doc.get("home") or "").upper(), str(doc.get("away") or "").upper()} - {""}
    names = {AL._fold(r.get("player")) for r in doc.get("players") or [] if isinstance(r, dict) and r.get("player")}
    for w in watches:
        if w.get("kind") == "team" and str(w.get("value") or "").upper() in sides:
            return True
        if w.get("kind") == "player" and AL._fold(w.get("value")) in names:
            return True
    return False


def finals_pass(conn, pbp_dir: Path | None = None, now: float | None = None) -> int:
    """Tell everyone following a side (or a player in the box) about each
    game that has just gone final. Returns how many were told."""
    ensure_tables(conn)
    t = time.time() if now is None else now
    conn.execute("DELETE FROM push_final_seen WHERE at < ?", (t - KEEP_S,))
    users = conn.execute("SELECT DISTINCT user_id FROM push_subs WHERE user_id IS NOT NULL "
                         "AND (',' || topics || ',') LIKE ?", (f"%,{TOPIC},%",)).fetchall()
    watching = {uid: AL.list_watches(conn, uid) for (uid,) in users}
    watching = {u: w for u, w in watching.items() if w}
    told = 0
    base = Path(pbp_dir) if pbp_dir else PM.WEB / "data" / "pbp"
    for path in sorted(base.glob("*.json")) if base.is_dir() else []:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if t - mtime > FRESH_S or _mtimes.get(str(path)) == mtime:
            continue
        try:
            doc = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        _mtimes[str(path)] = mtime
        if (doc.get("live") or {}).get("state") != "final":
            continue
        game = f"{doc.get('league')}_{doc.get('event_id')}"
        if conn.execute("SELECT 1 FROM push_final_seen WHERE game = ?", (game,)).fetchone():
            continue
        conn.execute("INSERT OR IGNORE INTO push_final_seen (game, at) VALUES (?, ?)", (game, t))
        said = message(doc)
        if said and watching:
            url = f"/#pbp/{doc.get('league')}/{doc.get('event_id')}"
            for uid, watches in watching.items():
                if _follows(watches, doc):
                    told += PM.tell(conn, uid, f"final:{game}", TOPIC, said[0], said[1], url, now=t)
        conn.commit()
    return told
