"""Your games in your calendar: a feed a phone's calendar subscribes to.

    python3 -m engine.calfeed            # how many members have made a link, sending nothing

Ethan, 2026-10-24: "build everything ... including all the ideas" — docs/
IDEAS.md 12, "an .ics feed of the games you have picks on". The games a
member has something on are theirs to know, so the feed is theirs:

  - every game in a parlay they saved to My Bets that is still open (the
    slip watch's own list, engine/slipwatch.pending_slips), titled with the
    game and "your parlay" and, in the notes, their own legs;
  - every game on this week's slates for the teams they follow (Settings,
    the ★ beside a team) — the schedule every board already publishes.

NEVER A PICK. Nothing from the paid half travels: the schedule is the
boards' free `games`, the legs are the member's own ticket.

A CALENDAR CANNOT SIGN IN. Apple Calendar, Google Calendar and Outlook fetch
a feed by its address alone, every few hours, so the address carries the
key: /api/calendar/<user>.<mac>.ics, the mac an HMAC over (member, this
link's own salt) under the box's link key (engine/digest — the key the
unsubscribe links use, with a different label). Making a new link changes
the salt and the old address stops answering, which is the whole of
revoking it. Nothing at rest opens a calendar for anybody.

Standard library only; the boards and the accounts database are handed in
or read from where the box keeps them.
"""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import hmac
import json
import re
import secrets
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
#: How long each league's game runs, for the calendar block.
LENGTH_MIN = {"nfl": 195, "cfb": 210, "nba": 150, "wnba": 135, "mlb": 180, "nhl": 150}
_TOKEN = re.compile(r"(\d{1,12})\.([A-Za-z0-9_-]{24,64})")
PRODID = "-//Qellys Book//Your games//EN"


def ensure_tables(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS calendar_links (user_id INTEGER PRIMARY KEY, salt TEXT NOT NULL, "
                 "made REAL NOT NULL)")
    conn.commit()


def _mac(user_id: int, salt: str) -> str:
    from engine import digest as DG
    mac = hmac.new(DG._unsub_key(), f"calendar:{int(user_id)}:{salt}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")[:32]


def token_for(conn, user_id: int, new: bool = False) -> str:
    """The member's calendar token, made on first ask; ``new`` makes a fresh
    one and the old address stops answering."""
    ensure_tables(conn)
    row = conn.execute("SELECT salt FROM calendar_links WHERE user_id = ?", (int(user_id),)).fetchone()
    if row is None or new:
        salt = secrets.token_urlsafe(16)
        conn.execute("INSERT INTO calendar_links (user_id, salt, made) VALUES (?,?,?) "
                     "ON CONFLICT(user_id) DO UPDATE SET salt = excluded.salt, made = excluded.made",
                     (int(user_id), salt, time.time()))
        conn.commit()
    else:
        salt = row[0]
    return f"{int(user_id)}.{_mac(user_id, salt)}"


def user_for(conn, token: str) -> int | None:
    """The member a calendar address belongs to, or None."""
    m = _TOKEN.fullmatch(str(token or "").strip())
    if not m:
        return None
    ensure_tables(conn)
    uid = int(m.group(1))
    row = conn.execute("SELECT salt FROM calendar_links WHERE user_id = ?", (uid,)).fetchone()
    if row is None or not hmac.compare_digest(_mac(uid, row[0]), m.group(2)):
        return None
    return uid


# --- the games --------------------------------------------------------------
def _boards(web: Path = WEB) -> dict:
    """Each league's public board: only its free `games` are read."""
    from engine import pushalerts as PA
    out = {}
    for sport, file, label in PA.LEAGUES:
        try:
            got = json.loads((Path(web) / "data" / file).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(got, dict) and isinstance(got.get("games"), list):
            out[sport] = {"label": label, "games": [g for g in got["games"] if isinstance(g, dict)]}
    return out


def _start(date: str, kickoff: str) -> _dt.datetime | None:
    """A board's Eastern date and kickoff as a UTC moment, or None."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(date or "").strip())
    k = re.match(r"^(\d{1,2}):(\d{2})", str(kickoff or "").strip())
    if not (m and k):
        return None
    try:
        local = _dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(k.group(1)), int(k.group(2)))
    except ValueError:
        return None
    try:
        from zoneinfo import ZoneInfo
        return local.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(_dt.timezone.utc)
    except Exception:                                               # noqa: BLE001
        # No time-zone database: Eastern daylight from mid-March to early
        # November, standard otherwise — the hour a calendar would show.
        edt = (3, 10) < (local.month, local.day) < (11, 3)
        return (local + _dt.timedelta(hours=4 if edt else 5)).replace(tzinfo=_dt.timezone.utc)


def _leg_teams(leg: dict) -> set:
    row = leg.get("row") if isinstance(leg.get("row"), dict) else {}
    names = {leg.get("team"), leg.get("opponent"), row.get("home"), row.get("away"), row.get("team")}
    for part in re.split(r"\s+(?:@|at|vs\.?)\s+", str(leg.get("game") or "")):
        names.add(part.strip())
    return {str(n).strip().upper() for n in names if n and str(n).strip()}


def events(conn, user_id: int, boards: dict, now: _dt.datetime | None = None) -> list[dict]:
    """The member's games, soonest first: [{uid, start, minutes, title, notes, url}]."""
    from engine import slipwatch as SW
    from engine import accounts as A
    now = now or _dt.datetime.now(_dt.timezone.utc)
    floor = now - _dt.timedelta(hours=6)
    found: dict = {}

    def add(sport, g, why, note=""):
        start = _start(g.get("date"), g.get("kickoff"))
        if start is None or start < floor:
            return
        key = f"{sport}-{g.get('date')}-{g.get('away')}-{g.get('home')}".replace(" ", "")
        ev = found.setdefault(key, {"uid": f"{key}@qellysbook.com", "start": start,
                                    "minutes": LENGTH_MIN.get(sport, 180), "sport": sport,
                                    "game": f"{g.get('away')} @ {g.get('home')}", "why": [], "notes": []})
        if why not in ev["why"]:
            ev["why"].append(why)
        if note and note not in ev["notes"]:
            ev["notes"].append(note)

    for r in SW.pending_slips(conn, user_id=user_id):
        for leg in r["bet"].get("legs") or []:
            if not isinstance(leg, dict):
                continue
            sport = str(leg.get("league") or leg.get("sport") or "").lower()
            teams = _leg_teams(leg)
            for g in (boards.get(sport) or {}).get("games") or []:
                if teams & {str(g.get("home") or "").upper(), str(g.get("away") or "").upper()}:
                    add(sport, g, "your parlay", str(leg.get("text") or "")[:80])
    settings = (A.get_sections(conn, user_id).get("settings") or {}).get("data") or {}
    for tag in settings.get("teams") or []:
        sport, _, abbr = str(tag).partition(":")
        for g in (boards.get(sport) or {}).get("games") or []:
            if abbr and abbr in (g.get("home"), g.get("away")):
                add(sport, g, "your team")
    out = []
    for ev in sorted(found.values(), key=lambda e: e["start"]):
        label = " · ".join(ev["why"])
        notes = ("Your legs: " + "; ".join(ev["notes"]) + ". ") if ev["notes"] else ""
        out.append({"uid": ev["uid"], "start": ev["start"], "minutes": ev["minutes"],
                    "title": f"{ev['game']} — {label}",
                    "notes": notes + "Live score and your ticket on the Live tab.",
                    "url": f"/?sport={ev['sport']}#live"})
    return out


# --- the file ---------------------------------------------------------------
def _esc(text: str) -> str:
    return (str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r", "").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """RFC 5545 3.1: lines longer than 75 octets continue on the next,
    which starts with a space; never split inside a character."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def ics(evs: list[dict], site: str = "", now: _dt.datetime | None = None) -> str:
    stamp = (now or _dt.datetime.now(_dt.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    fmt = lambda d: d.strftime("%Y%m%dT%H%M%SZ")                    # noqa: E731
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:Qellys — your games", "REFRESH-INTERVAL;VALUE=DURATION:PT3H", "X-PUBLISHED-TTL:PT3H"]
    for e in evs:
        lines += ["BEGIN:VEVENT", f"UID:{e['uid']}", f"DTSTAMP:{stamp}", f"DTSTART:{fmt(e['start'])}",
                  f"DTEND:{fmt(e['start'] + _dt.timedelta(minutes=e['minutes']))}",
                  f"SUMMARY:{_esc(e['title'])}", f"DESCRIPTION:{_esc(e['notes'])}"]
        if site:
            lines.append(f"URL:{site.rstrip('/')}{e['url']}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


def feed(conn, token: str, web: Path = WEB, site: str = "", now: _dt.datetime | None = None) -> str | None:
    """The calendar for an address, or None when the address is not one."""
    uid = user_for(conn, token)
    if uid is None:
        return None
    return ics(events(conn, uid, _boards(web), now=now), site=site, now=now)


def main(argv=None) -> int:
    import sqlite3
    from engine import accounts
    try:
        conn = sqlite3.connect(f"file:{accounts.DB_PATH}?mode=ro", uri=True)
        try:
            n = conn.execute("SELECT COUNT(*) FROM calendar_links").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error:
        n = 0
    print(f"Calendar links made: {n}. Boards with a schedule: {', '.join(sorted(_boards())) or 'none on disk'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
