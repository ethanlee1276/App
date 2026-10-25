"""What the iPhone widget shows: the record, last night, and tonight's boards.

    python3 -m engine.widgetfeed         # the widget's JSON, as the box would serve it

Ethan, 2026-10-24: "build everything ... including all the ideas" — docs/
IDEAS.md 11, Apple Sports' best thing: a Home Screen widget. The widget
(deploy/ios/native/QellysWidget.swift) asks GET /api/widget every half hour
and draws what this returns.

PUBLIC BY DESIGN. A widget cannot sign in (it runs outside the app, on a
schedule iOS picks), so it shows only what the site gives everybody: the
record (free, engine/ledger), last night's line (the same one the email and
the alerts read, engine/digest.last_night), and how many picks each league
has up today — a count, as the "picks are up" alert says it, never a pick.

YOUR PLAYERS ON THE WIDGET AND THE LOCK SCREEN (2026-10-25). The second
widget (deploy/ios/native/Widget/YourPlayersWidget.swift) shows the account's
followed players with their lines right now (engine/yourplayers). A widget
still cannot sign in, so the app hands it a key: the member turns it on in
Settings inside the iPhone app, the app asks POST /api/widget/key and puts
the answer in the App Group the widget reads, and the widget asks
GET /api/widget/mine?k=<key>. The key is calfeed's shape — ``<user>.<mac>``,
an HMAC over this link's own salt under the box's link key, labelled apart
— so nothing at rest opens anyone's widget, a new key stops the old one,
and turning it off deletes the row. Signing out in the app clears it from
the phone. What it carries is public box scores and the member's own
follows; never a pick.

Standard library only; reads the boards where the box writes them.
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
_KEY = re.compile(r"(\d{1,12})\.([A-Za-z0-9_-]{24,64})")
#: The most players one widget carries (the medium size shows four).
WIDGET_PLAYERS = 6


def _load(path: Path) -> dict:
    try:
        got = json.loads(Path(path).read_text(encoding="utf-8"))
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def build(web: Path = WEB, today: _dt.date | None = None) -> dict:
    from engine import digest, gate, pushalerts as PA
    web = Path(web)
    today = today or _dt.date.today()
    rec = _load(web / "data" / "record_head.json") or _load(web / "data" / "record.json")
    ov = rec.get("overall") or {}
    record = None
    if ov.get("settled"):
        record = {"w": int(ov.get("wins") or 0), "l": int(ov.get("losses") or 0), "p": int(ov.get("pushes") or 0),
                  "units": round(float(ov.get("net_units") or 0), 1), "roi": round(float(ov.get("roi") or 0) * 100, 1)}
    night = digest.last_night(web)
    tonight = []
    for sport, file, label in PA.LEAGUES:
        board = PA._load(gate.board_source(web / "data" / file))
        n, date = PA._picks(board), str(board.get("date") or "")
        if n and date and not (len(date) == 10 and date < today.isoformat()):
            tonight.append({"league": label, "sport": sport, "picks": n, "url": f"/?sport={sport}#recommended"})
    return {"record": record,
            "last_night": ({"date": night["date"], "w": night["w"], "l": night["l"], "p": night["p"],
                            "units": night["net_u"]} if night and (night["w"] or night["l"]) else None),
            "tonight": tonight,
            "updated": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "url": "/#recommended"}


# --- the key and the account's own widget ------------------------------------
def ensure_tables(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS widget_links (user_id INTEGER PRIMARY KEY, salt TEXT NOT NULL, "
                 "made REAL NOT NULL)")
    conn.commit()


def _mac(user_id: int, salt: str) -> str:
    from engine import digest as DG
    mac = hmac.new(DG._unsub_key(), f"widget:{int(user_id)}:{salt}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")[:32]


def key_for(conn, user_id: int, new: bool = False) -> str:
    """The account's widget key, made on first ask; ``new`` replaces it."""
    ensure_tables(conn)
    row = conn.execute("SELECT salt FROM widget_links WHERE user_id = ?", (int(user_id),)).fetchone()
    if row is None or new:
        salt = secrets.token_urlsafe(16)
        conn.execute("INSERT INTO widget_links (user_id, salt, made) VALUES (?,?,?) "
                     "ON CONFLICT(user_id) DO UPDATE SET salt = excluded.salt, made = excluded.made",
                     (int(user_id), salt, time.time()))
        conn.commit()
    else:
        salt = row[0]
    return f"{int(user_id)}.{_mac(user_id, salt)}"


def key_off(conn, user_id: int) -> None:
    ensure_tables(conn)
    conn.execute("DELETE FROM widget_links WHERE user_id = ?", (int(user_id),))
    conn.commit()


def user_for(conn, key: str) -> int | None:
    """The account a widget key belongs to, or None."""
    m = _KEY.fullmatch(str(key or "").strip())
    if not m:
        return None
    ensure_tables(conn)
    uid = int(m.group(1))
    row = conn.execute("SELECT salt FROM widget_links WHERE user_id = ?", (uid,)).fetchone()
    if row is None or not hmac.compare_digest(_mac(uid, row[0]), m.group(2)):
        return None
    return uid


def mine(conn, key: str, idx: dict | None = None) -> dict | None:
    """What the account's widget draws: its followed players with their
    lines right now, live first, and how many it follows. None for a key
    that is not one (or was replaced or turned off)."""
    from engine import alerts as AL, yourplayers as YP
    uid = user_for(conn, key)
    if uid is None:
        return None
    watches = AL.list_watches(conn, uid)
    lines = YP.mine(watches, idx)[:WIDGET_PLAYERS]
    return {"players": [{"player": r["player"], "team": r["team"], "opp": r.get("opp") or "",
                         "line": r["line"], "status": r["status"], "live": r["state"] == "live",
                         "url": f"/#pbp/{r['league']}/{r['event_id']}"} for r in lines],
            "following": sum(1 for w in watches if w.get("kind") == "player"),
            "updated": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}


def main(argv=None) -> int:
    print(json.dumps(build(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
