"""The two emails: this morning's card, and last night's result.

Ethan, 2026-08-25: *"Comms — email makes it a company. Push
notifications make it a habit; email makes it an institution. A morning
'Today's Card' digest and a nightly settle recap, same content as the
site's anchor moments."*

WHAT THIS MODULE IS, AND WHAT IT DELIBERATELY IS NOT
---------------------------------------------------
It BUILDS the two digests and it does not send them. Sending needs
three things this repo does not have and cannot invent: a delivery
provider, DNS records on qellysbook.com (SPF, DKIM and DMARC — without
them mail from a DigitalOcean droplet is filed as spam or refused
outright, and DO blocks port 25 on new accounts anyway), and a working
unsubscribe. `engine/mailer.py` is the one-function seam where a
provider plugs in, and it refuses loudly rather than pretending. See
docs/EMAIL.md for the three steps in order.

Which means what is here is the part that is actually hard — the
content, the gate discipline and the opt-in — and the part that is
missing is a credential.

THE GATE APPLIES TO AN EMAIL, AND MORE STRICTLY THAN TO A PAGE
--------------------------------------------------------------
A page is fetched by somebody who is signed in right now. An email is a
copy of the product that leaves the building, gets forwarded, and sits
in an inbox indefinitely. So `build` takes `entitled` and an unentitled
digest carries COUNTS and free facts only — the same locked-state
honesty `gate.redact` gives a board ("14 picks behind the subscription")
rather than an empty message that looks like a quiet night.

The morning digest is the card; the nightly one is the result. The
result is free by the same rule record.json is: it is the evidence, and
a proof nobody can read persuades nobody.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import secrets
from pathlib import Path

from engine import gate

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

#: How many picks a morning digest names before it stops listing and
#: starts counting. An email is a nudge to open the site, not a
#: replacement for it — and a message with thirty rows in it is one
#: nobody reads twice.
MAX_PICKS = 5

SITE = "https://qellysbook.com"

BOARDS = (
    ("mlb", "mlb_recommendations.json", "MLB"),
    ("nfl", "recommendations.json", "NFL"),
    ("cfb", "cfb.json", "College football"),
    ("nba", "nba.json", "NBA"),
    ("wnba", "wnba.json", "WNBA"),
)


# --- the opt-in --------------------------------------------------------------

def ensure_tables(conn) -> None:
    """The mailing list, beside the accounts.

    One row per account that has asked for mail, with the token that
    turns an unsubscribe link into a single click. A LIST YOU CANNOT
    LEAVE IS NOT A LIST, it is a complaint — and in the US it is also
    illegal, which is the smaller of the two reasons.
    """
    conn.execute("""CREATE TABLE IF NOT EXISTS digest_optin (
        user_id     INTEGER PRIMARY KEY,
        morning     INTEGER NOT NULL DEFAULT 0,
        nightly     INTEGER NOT NULL DEFAULT 0,
        token       TEXT NOT NULL,
        created_at  INTEGER NOT NULL DEFAULT 0
    )""")
    conn.commit()


def optin_get(conn, user_id: int) -> dict:
    ensure_tables(conn)
    row = conn.execute("SELECT morning, nightly, token FROM digest_optin "
                       "WHERE user_id=?", (int(user_id),)).fetchone()
    if row is None:
        return {"morning": False, "nightly": False, "token": ""}
    return {"morning": bool(row["morning"]), "nightly": bool(row["nightly"]),
            "token": row["token"]}


def optin_set(conn, user_id: int, morning: bool, nightly: bool) -> dict:
    """Turn either digest on or off. Returns the stored state.

    The token is minted once and KEPT across changes: an unsubscribe
    link in a message sent last week has to keep working, and re-minting
    on every toggle would quietly break every link already delivered.
    """
    import time
    ensure_tables(conn)
    cur = optin_get(conn, user_id)
    token = cur["token"] or secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO digest_optin (user_id, morning, nightly, token, created_at) "
        "VALUES (?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
        "morning=excluded.morning, nightly=excluded.nightly",
        (int(user_id), 1 if morning else 0, 1 if nightly else 0, token,
         int(time.time())))
    conn.commit()
    return {"morning": bool(morning), "nightly": bool(nightly), "token": token}


def unsubscribe(conn, token: str) -> bool:
    """One click, no sign-in, both digests off.

    NO SIGN-IN ON PURPOSE. An unsubscribe that asks somebody to remember
    a password is an unsubscribe that becomes a spam report instead. The
    token is unguessable and can do exactly one thing.
    """
    tok = str(token or "").strip()
    if not tok or len(tok) < 16:
        return False
    ensure_tables(conn)
    cur = conn.execute("UPDATE digest_optin SET morning=0, nightly=0 "
                       "WHERE token=?", (tok,))
    conn.commit()
    return cur.rowcount > 0


def recipients(conn, kind: str) -> list[dict]:
    """Everyone who asked for this digest, with their address.

    Reads the accounts table by join rather than storing an address
    here: two copies of somebody's email is one that goes stale the day
    they change it, and the wrong one is a message delivered to an
    address they thought they had removed.
    """
    if kind not in ("morning", "nightly"):
        return []
    ensure_tables(conn)
    rows = conn.execute(
        f"SELECT u.id, u.email, d.token FROM digest_optin d "
        f"JOIN users u ON u.id = d.user_id WHERE d.{kind} = 1").fetchall()
    return [{"user_id": r["id"], "email": r["email"], "token": r["token"]}
            for r in rows]


# --- reading what the site already published ---------------------------------

def _load(path: Path) -> dict:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _board(file: str, web: Path) -> dict:
    return _load(gate.board_source(Path(web) / "data" / file))


def card_rows(web: Path = WEB) -> list[dict]:
    """Today's recommended picks across every league, best EV first."""
    out = []
    for sport, file, label in BOARDS:
        board = _board(file, web)
        for r in board.get("recommendations") or []:
            if not isinstance(r, dict) or not r.get("recommended"):
                continue
            out.append({
                "sport": sport, "league": label,
                "player": r.get("player") or "",
                "market": r.get("market_label") or r.get("market") or "",
                "side": r.get("side") or "",
                "line": r.get("line"),
                "odds": r.get("odds"),
                "book": r.get("book") or "",
                "ev": r.get("ev_per_unit"),
                "slug": f"{_slug(r.get('player'))}-{_slug(r.get('market'))}",
            })
    out.sort(key=lambda r: -(r["ev"] or 0))
    return out


def _slug(text) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", str(text or "")).strip("-").lower()
    return s


def last_night(web: Path = WEB) -> dict | None:
    """Last night's graded line, off the feed's own settle_recap event.

    The SAME event the site's anchor moment reads, deliberately: the
    email and the page must not be able to disagree about what last
    night was, and a second computation of "how did we do" is a second
    answer waiting to differ from the first.
    """
    feed = _board("feed.json", web)
    recaps = [e for e in feed.get("events") or []
              if isinstance(e, dict) and e.get("kind") == "settle_recap"]
    if not recaps:
        return None
    recaps.sort(key=lambda e: str(e.get("date") or ""))
    e = recaps[-1]
    return {"date": e.get("date"), "w": e.get("w", 0), "l": e.get("l", 0),
            "p": e.get("p", 0), "net_u": e.get("net_u", 0)}


# --- the two messages --------------------------------------------------------

def _price(odds) -> str:
    try:
        n = int(odds)
    except (TypeError, ValueError):
        return ""
    return f"+{n}" if n > 0 else str(n)


def _esc(text) -> str:
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def morning(entitled: bool = True, web: Path = WEB,
            token: str = "") -> dict | None:
    """Today's card. None when there is nothing to send.

    NOTHING TO SEND IS A REAL ANSWER. A daily email that arrives on a
    day with no picks, saying there are no picks, teaches people to
    filter it — and this model passes often enough that it would happen
    most weeks in February.
    """
    rows = card_rows(web)
    if not rows:
        return None
    n = len(rows)
    leagues = sorted({r["league"] for r in rows})
    subject = (f"Today's card: {n} pick{'' if n == 1 else 's'} "
               f"({', '.join(leagues)})")
    if not entitled:
        text = (f"{n} pick{'' if n == 1 else 's'} on the board today across "
                f"{', '.join(leagues)}.\n\n"
                "They are behind the subscription — the record that says "
                "whether they are worth it is not:\n"
                f"{SITE}/record\n")
        body = (f"<p><b>{n} pick{'' if n == 1 else 's'}</b> on the board today "
                f"across {_esc(', '.join(leagues))}.</p>"
                "<p>They are behind the subscription. The record that says "
                "whether they are worth it is not — "
                f'<a href="{SITE}/record">every pick graded in public</a>.</p>')
        return _wrap(subject, text, body, token)
    shown = rows[:MAX_PICKS]
    lines = []
    html_rows = []
    for r in shown:
        line = "" if r["line"] is None else f" {r['line']}"
        pick = f"{r['side']}{line} {r['market']}".strip()
        lines.append(f"  {r['player']} — {pick} {_price(r['odds'])}"
                     f"{'  (' + r['book'] + ')' if r['book'] else ''}")
        html_rows.append(
            f'<tr><td style="padding:6px 12px 6px 0"><b>{_esc(r["player"])}</b>'
            f'<br><span style="color:#8b8178">{_esc(r["league"])}</span></td>'
            f'<td style="padding:6px 12px 6px 0">{_esc(pick)}</td>'
            f'<td style="padding:6px 0"><b>{_esc(_price(r["odds"]))}</b></td></tr>')
    more = n - len(shown)
    text = (f"{n} pick{'' if n == 1 else 's'} on the board today.\n\n"
            + "\n".join(lines)
            + (f"\n\n  …and {more} more on the board.\n" if more else "\n")
            + f"\nThe full card, with the reasoning on every one:\n{SITE}\n")
    body = (f"<p><b>{n} pick{'' if n == 1 else 's'}</b> on the board today.</p>"
            f'<table style="border-collapse:collapse">{"".join(html_rows)}</table>'
            + (f'<p style="color:#8b8178">…and {more} more on the board.</p>'
               if more else "")
            + f'<p><a href="{SITE}">The full card, with the reasoning on every '
              "one →</a></p>")
    return _wrap(subject, text, body, token)


def nightly(web: Path = WEB, token: str = "") -> dict | None:
    """Last night, graded. Free — it is the evidence, not the product."""
    rec = last_night(web)
    if not rec:
        return None
    settled = (rec["w"] or 0) + (rec["l"] or 0) + (rec["p"] or 0)
    if not settled:
        return None
    net = rec["net_u"] or 0
    line = f"{rec['w']}-{rec['l']}" + (f"-{rec['p']}" if rec["p"] else "")
    sign = "+" if net >= 0 else ""
    subject = f"Last night: {line}, {sign}{net}u"
    text = (f"{line}, {sign}{net}u.\n\n"
            "Every one of those is journaled at the price it was published "
            "at, graded against the close as well as the result — including "
            f"the ones that lost.\n\n{SITE}/record\n")
    body = (f'<p style="font-size:22px"><b>{_esc(line)}</b> '
            f'<b>{_esc(sign + str(net))}u</b></p>'
            "<p>Every one of those is journaled at the price it was published "
            "at and graded against the close as well as the result — "
            "including the ones that lost.</p>"
            f'<p><a href="{SITE}/record">The whole record →</a></p>')
    return _wrap(subject, text, body, token)


def _wrap(subject: str, text: str, body_html: str, token: str) -> dict:
    """One message, both parts, with the unsubscribe on every copy.

    THE FOOTER IS NOT OPTIONAL and it is not decoration: an email
    without a working unsubscribe is what turns a reader into a spam
    report, and one spam report costs more deliverability than a hundred
    opens earn. It rides here rather than in each builder so a new
    digest cannot ship without it.
    """
    link = f"{SITE}/unsubscribe?t={token}" if token else f"{SITE}/account"
    foot_text = ("\n—\nYou are getting this because you asked for it on your "
                 f"Qellys Book account.\nStop these emails: {link}\n"
                 "This is analysis, not advice. No bets are taken here.\n")
    foot_html = (
        '<hr style="border:0;border-top:1px solid #2a2622;margin:22px 0">'
        '<p style="color:#8b8178;font-size:12px">You are getting this because '
        "you asked for it on your Qellys Book account. "
        f'<a href="{link}" style="color:#8b8178">Stop these emails</a>.<br>'
        "This is analysis, not advice. No bets are taken here.</p>")
    html = ('<div style="background:#0b0906;color:#f5efe6;padding:26px;'
            'font-family:system-ui,-apple-system,sans-serif;max-width:600px">'
            f'<p style="color:#e8b64c;font-weight:700;letter-spacing:.04em">'
            "QELLYS BOOK</p>"
            f"{body_html}{foot_html}</div>")
    return {"subject": subject, "text": text + foot_text, "html": html}


def build(kind: str, entitled: bool = True, web: Path = WEB,
          token: str = "") -> dict | None:
    if kind == "morning":
        return morning(entitled=entitled, web=web, token=token)
    if kind == "nightly":
        return nightly(web=web, token=token)
    return None
