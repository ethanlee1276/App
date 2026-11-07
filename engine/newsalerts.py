"""Injury news for the players a member follows or has a bet on (topic
"news", its own switch in Alerts).

Ethan's research (2026-10-29), the notification plan: "Lineup/injury news —
confirmed lineup or status change for followed player or bet player ... On
... unbatched (high value)", the most time-sensitive edge a bettor has. The
league injury boards are already on disk every half hour
(injuries_build.py → web/data/injuries.json, ESPN's keyless feed); this
reads them against each member's own players — the player watches on their
Alerts page and the players in their open saved slips — and tells them when
one's status CHANGES ("Questionable → Out"). The first sight of a player's
status is only remembered: a status that was already true when they
followed him is not news.

Public facts only, never a pick. Held through the member's quiet hours like
the other news kinds (engine/pushmine.HELD). What is kept, per member and
player: the last status seen, so a change can be told once — deleted with
the account. Standard library only.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from engine import pushmine as PM

TOPIC = "news"
#: Statuses worth a line when a player moves into or out of them.
STATUSES = ("OUT", "DOUBTFUL", "QUESTIONABLE", "GTD", "IR", "DAY-TO-DAY", "ACTIVE", "PROBABLE", "SUSPENSION")


def ensure_tables(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS news_seen (
        user_id INTEGER NOT NULL, player TEXT NOT NULL, status TEXT NOT NULL, at REAL NOT NULL,
        PRIMARY KEY (user_id, player))""")


def _key(name) -> str:
    from engine.sliplive import _key as k
    return k(name)


def board(data_dir: Path) -> dict:
    """{player key: (league, player, team, status, injury)} off the injury boards."""
    try:
        doc = json.loads((Path(data_dir) / "injuries.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for lg, rows in ((doc or {}).get("sports") or {}).items():
        for r in rows if isinstance(rows, list) else []:
            name = str(r.get("player") or "").strip()
            if name:
                out[_key(name)] = (lg, name, str(r.get("team") or ""), str(r.get("status") or "").upper(),
                                   str(r.get("injury") or ""))
    return out


def players(conn, user_id) -> dict:
    """{player key: why} — the member's player watches and the players in
    their open saved slips."""
    from engine import alerts as AL
    from engine import slipwatch as SW
    out = {}
    for w in AL.list_watches(conn, user_id):
        if w.get("kind") == "player" and w.get("value"):
            out[_key(w["value"])] = "you follow him"
    for r in SW.pending_slips(conn, user_id=user_id):
        for leg in r["bet"].get("legs") or []:
            if isinstance(leg, dict) and leg.get("player"):
                out[_key(leg["player"])] = "he is in your open bet"
    return out


def news_pass(conn, data_dir: Path | None = None, now: float | None = None) -> int:
    """Tell each member whose phone carries "news" about a status change of
    one of their players. Returns how many were told."""
    PM.ensure_tables(conn)
    ensure_tables(conn)
    t = time.time() if now is None else float(now)
    users = conn.execute("SELECT DISTINCT user_id FROM push_subs WHERE user_id IS NOT NULL "
                         "AND (',' || topics || ',') LIKE ?", (f"%,{TOPIC},%",)).fetchall()
    if not users:
        return 0
    inj = board(Path(data_dir) if data_dir else PM.WEB / "data")
    if not inj:
        return 0
    told = 0
    for (uid,) in users:
        try:
            mine = players(conn, uid)
        except Exception:                                     # noqa: BLE001 — no slips or watches table yet
            mine = {}
        for key, why in mine.items():
            hit = inj.get(key)
            if not hit:
                continue
            lg, name, team, status, injury = hit
            row = conn.execute("SELECT status FROM news_seen WHERE user_id = ? AND player = ?", (uid, key)).fetchone()
            conn.execute("INSERT INTO news_seen (user_id, player, status, at) VALUES (?,?,?,?) "
                         "ON CONFLICT(user_id, player) DO UPDATE SET status = excluded.status, at = excluded.at",
                         (uid, key, status, t))
            if row is None or row[0] == status:
                continue                                      # first sight, or no change
            was = row[0].title() if row[0] else "no status"
            told += PM.tell(conn, uid, f"news:{key}:{status}:{int(t // 3600)}", TOPIC,
                            f"{name}{' (' + team + ')' if team else ''}: {was} → {status.title()}"[:120],
                            (f"{injury}. " if injury else "") + f"News: {why}.", f"/?sport={lg}#injuries", now=t)
    conn.commit()
    return told
