"""What each member said yes or no to, when, and under which version of the
Privacy Policy.

Ethan's research (2026-10-29, "Data, Retention & the ESPN Playbook"): "A
consent log. Store what each user agreed to, which policy version, and
when. If a demand letter arrives, documented consent records are your
strongest defense" — and "nothing fires before consent". So every choice a
member makes about their own data or our messages to them is written here
as it happens:

  terms      the age (21+) and terms confirmation, at sign-up
  activity   yes or no to keeping their own activity (engine/activity)
  alerts     alerts turned on (the kinds) or off on a phone signed in to them
  limits     a weekly bet limit or an alert break set or cleared
  split      counted, or not, in the members' pooled split (engine/consensus)

`version` is the Privacy Policy's own "Last updated" date at the moment of
the choice, read off web/privacy.html, so a record says which wording the
member saw. Rows are append-only: a change of mind is a new row, never an
edit. Deleted with the account (engine/accounts), in its export.

Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "web" / "privacy.html"
KINDS = ("terms", "activity", "alerts", "limits", "split", "closeboard")
_DATE = re.compile(r'class="legal-date">Last updated (\d{1,2} \w+ \d{4})<')
_version: dict = {"key": None, "v": ""}


def ensure_tables(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS consent_log (
        user_id INTEGER NOT NULL, kind TEXT NOT NULL, choice TEXT NOT NULL,
        version TEXT NOT NULL DEFAULT '', at REAL NOT NULL)""")
    conn.execute("CREATE INDEX IF NOT EXISTS consent_log_user ON consent_log(user_id, at)")


def policy_version(path: Path | None = None) -> str:
    """The Privacy Policy's "Last updated" date as ISO, or "" when unread."""
    p = Path(path or POLICY)
    try:
        key = (str(p), p.stat().st_mtime_ns)
    except OSError:
        return ""
    if _version["key"] != key:
        m = _DATE.search(p.read_text(encoding="utf-8"))
        try:
            v = _dt.datetime.strptime(m.group(1), "%d %B %Y").date().isoformat() if m else ""
        except ValueError:
            v = ""
        _version.update(key=key, v=v)
    return _version["v"]


def record(conn, user_id, kind: str, choice: str, now: float | None = None) -> bool:
    """Write one choice. False for an unknown kind, no account, or the same
    word as their last on this kind (a phone re-subscribing at each sign-in
    is not a new choice)."""
    if kind not in KINDS or not user_id:
        return False
    ensure_tables(conn)
    if latest(conn, user_id, kind) == str(choice)[:120]:
        return False
    conn.execute("INSERT INTO consent_log (user_id, kind, choice, version, at) VALUES (?,?,?,?,?)",
                 (int(user_id), kind, str(choice)[:120], policy_version(), time.time() if now is None else float(now)))
    return True


def history(conn, user_id) -> list[dict]:
    """Every choice this member made, oldest first."""
    ensure_tables(conn)
    return [{"kind": r[0], "choice": r[1], "policy": r[2], "at": r[3]} for r in conn.execute(
        "SELECT kind, choice, version, at FROM consent_log WHERE user_id = ? ORDER BY at, rowid", (int(user_id),))]


def latest(conn, user_id, kind: str) -> str | None:
    """The member's last word on one kind, or None."""
    ensure_tables(conn)
    row = conn.execute("SELECT choice FROM consent_log WHERE user_id = ? AND kind = ? ORDER BY at DESC, rowid DESC "
                       "LIMIT 1", (int(user_id), kind)).fetchone()
    return row[0] if row else None
