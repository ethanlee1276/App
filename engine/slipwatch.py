"""The last leg of a saved slip, noticed by the box — and said by email
to a member who asked (2026-10-13).

Ethan, 2026-10-13: "add all of them", the fifth being an alert when a
slip saved to My Bets from the parlay checker is down to the one leg
that decides it: the moment the hedge calculator (slipgrade.hedge) and
the cash-out check are worth opening.

WHERE THE SLIPS ARE. A saved slip is a My Bets entry (src "slip", its
legs kept as the card resolved them), and a signed-in member's My Bets
is synced to the account store — server.merge_sections, section
"mybets", the union that never loses a bet. So the box already holds
every member's open slips and can watch them while the Live tab is
closed, which is when being told matters. launch._slip_watcher calls
`run_once` on its own clock; `sweep` grades each pending slip the way
the Live tab does (slipgrade.grade, brief: no picture, no model call,
the live files) and notes a slip whose standing says ONE LEG LEFT —
once, in `slip_alerts` — then mails it where asked.

THE EMAIL IS ONE-TO-ONE, like a password reset: the member switched it
on (the Live tab's toggle, `slip_alert_optin`), it goes to the address
on the account, and it carries their own ticket. So mailer.configured()
is enough — the site's Gmail carries one-to-one mail — where the digests
need bulk_ok. Held three ways: one email per slip, ever; MAIL_PER_DAY
across the whole box (the password resets and the owner's crash alerts
share the day's sends); and the member must be ENTITLED when it goes —
our live chance and the hedge are the paid half, and an email leaves the
building (docs/EMAIL.md). Every message carries the unsubscribe the same
doc requires: a bearer token in the body and in the List-Unsubscribe
header (mailer.message reads "Stop these emails:"), no password, and the
link turns off only THIS mail (server._unsubscribe routes the "slip-"
prefix here). The token is an HMAC over (user, this list's own salt)
under the digest's key — nothing at rest unsubscribes anybody.

NOT PUSH — the site has none, and engine/alerts says why. The Live tab
draws the same alert from its own read and buzzes once (web/js/slip.js
`lastLeg`); this is the half that works with the phone in a pocket.

THE BOX SETTLES THEM TOO (2026-10-14, Ethan: "do 1-11", the call "saved
slips settled by the server?"). A saved slip used to settle only while
somebody had the Live tab open: the page graded it once a minute and wrote
the result into My Bets. The same pass here now writes it, Live tab open or
not, by the page's own rules (`settled`, web/js/slip.js `settleOne`): lost,
won, every leg pushed, or won with a leg pushed and paid at the price
without it when every pushed leg's price is known. Won with a pushed leg
whose price is not known stays for the member to set, as the page leaves
it. The write is one member's stored My Bets row, a pending saved slip
matched by its id and nothing else touched, under accounts.one_writer —
the page's sync takes the same lock, so neither builds on a copy read
before the other's write. The page adopts it on its next sync: the merge
never lets a pending copy un-settle a graded bet (server._merge_mybets).

The clock, the boards, the live reader, the sender and the gate are all
handed in, so a test runs on a temp database and never touches the box.
"""

from __future__ import annotations

import datetime as _dt
import hmac
import json
import math
import re
import secrets
import sqlite3
import threading
import time

from . import digest as DG

#: One account's open slips the sweep reads: the newest, as the Live tab
#: follows them (server.MAX_TRACK_SLIPS).
MAX_SLIPS_PER_USER = 10
#: Emails a day, all members together. A slate night with every member's
#: parlay on its last leg at once is a few dozen; past this the alert is
#: still noted and the Live tab still says so — only the email waits.
MAIL_PER_DAY = 40
#: A noted alert is kept this long, so the table never grows with the
#: season: a slip is settled within a day of firing.
KEEP_DAYS = 30
#: The token form server._unsubscribe routes here.
PREFIX = "slip-"
#: Where the link in the email lands — the Live tab, with the hedge
#: calculator and the cash-out check.
LIVE_PATH = "/#live"

_DERIVED = re.compile(r"(\d{1,12})\.([A-Za-z0-9_-]{24,64})")
_SENT: list = []
_LOCK = threading.Lock()
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


# --- the tables ----------------------------------------------------------------

def ensure_tables(conn) -> None:
    """The alerts noted and the opt-in, beside the accounts. No address
    here: it is read by join from `users`, so it can never go stale."""
    conn.execute("""CREATE TABLE IF NOT EXISTS slip_alerts (
        user_id   INTEGER NOT NULL,
        bet_id    TEXT NOT NULL,
        fired_at  REAL NOT NULL,
        mailed    INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, bet_id)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS slip_alert_optin (
        user_id     INTEGER PRIMARY KEY,
        mail        INTEGER NOT NULL DEFAULT 0,
        salt        TEXT NOT NULL,
        created_at  INTEGER NOT NULL DEFAULT 0
    )""")
    conn.commit()


# --- the opt-in ----------------------------------------------------------------

def optin_get(conn, user_id: int) -> dict:
    ensure_tables(conn)
    row = conn.execute("SELECT mail FROM slip_alert_optin WHERE user_id=?",
                       (int(user_id),)).fetchone()
    return {"on": bool(row and row["mail"])}


def optin_set(conn, user_id: int, on: bool) -> dict:
    """On or off. The salt is minted once and KEPT across every toggle, so
    an unsubscribe link in a message sent last week keeps working — the
    digest's own rule (engine/digest.optin_set)."""
    ensure_tables(conn)
    conn.execute(
        "INSERT INTO slip_alert_optin (user_id, mail, salt, created_at) VALUES (?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET mail=excluded.mail",
        (int(user_id), 1 if on else 0, secrets.token_urlsafe(16), int(time.time())))
    conn.commit()
    return {"on": bool(on)}


def link_token(conn, user_id: int) -> str:
    """The token this member's unsubscribe link carries, or "" for one who
    never opted in: the prefix routes it, the rest is the digest's HMAC
    over (user, this list's own salt)."""
    ensure_tables(conn)
    row = conn.execute("SELECT salt FROM slip_alert_optin WHERE user_id=?",
                       (int(user_id),)).fetchone()
    if row is None or not row["salt"]:
        return ""
    return PREFIX + DG.link_token(user_id, row["salt"])


def unsubscribe(conn, token: str) -> bool:
    """One click, no sign-in: this mail off and nothing else touched. False
    for a token that is not this list's or does not verify."""
    tok = str(token or "").strip()
    if not tok.startswith(PREFIX):
        return False
    m = _DERIVED.fullmatch(tok[len(PREFIX):])
    if not m:
        return False
    ensure_tables(conn)
    uid = int(m.group(1))
    row = conn.execute("SELECT salt FROM slip_alert_optin WHERE user_id=?", (uid,)).fetchone()
    if row is None or not row["salt"] or not hmac.compare_digest(
            PREFIX + DG.link_token(uid, row["salt"]), tok):
        return False
    conn.execute("UPDATE slip_alert_optin SET mail=0 WHERE user_id=?", (uid,))
    conn.commit()
    return True


# --- the slips ------------------------------------------------------------------

def pending_slips(conn, limit: int = MAX_SLIPS_PER_USER) -> list[dict]:
    """Every member's open saved slips as ``{user_id, email, bet}`` rows —
    the newest ``limit`` per member — read from the synced My Bets
    section. A bet logged by hand (no legs, src not "slip") is not one."""
    out = []
    rows = conn.execute(
        "SELECT d.user_id, u.email, d.payload FROM user_data d "
        "JOIN users u ON u.id = d.user_id WHERE d.section = 'mybets'").fetchall()
    for r in rows:
        try:
            data = json.loads(r["payload"])
        except ValueError:
            continue
        bets = data.get("rows") if isinstance(data, dict) else None
        if not isinstance(bets, list):
            continue
        mine = [b for b in bets if isinstance(b, dict) and b.get("src") == "slip"
                and str(b.get("result") or "pending") == "pending"
                and isinstance(b.get("legs"), list) and b["legs"] and b.get("id")]
        mine.sort(key=lambda b: str(b["id"]), reverse=True)
        out.extend({"user_id": int(r["user_id"]), "email": r["email"], "bet": b}
                   for b in mine[:limit])
    return out


def noted(conn, user_id: int, bet_id: str) -> bool:
    return conn.execute("SELECT 1 FROM slip_alerts WHERE user_id=? AND bet_id=?",
                        (int(user_id), str(bet_id))).fetchone() is not None


def last_leg(card: dict) -> bool:
    """One leg left to decide an open ticket — the standing the Live tab
    draws (slipgrade.standing) says so. A pushed leg is not a leg left."""
    now = (card or {}).get("now") or {}
    return now.get("status") == "open" and int(now.get("left") or 0) == 1


def _dec(o) -> float | None:
    """American odds as a decimal price, the page's `dec`: None for no price."""
    try:
        a = float(o)
    except (TypeError, ValueError):
        return None
    if not a or not math.isfinite(a):
        return None
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


def _american(d: float) -> int:
    """A decimal price as American odds, the page's `american` (its
    Math.round: halves up)."""
    if not d > 1:
        return 0
    if d >= 2:
        return int(math.floor((d - 1) * 100 + 0.5))
    return -int(math.floor(100 / (d - 1) + 0.5))


def settled(bet: dict, card: dict) -> dict | None:
    """What the Live tab writes on a ticket the box score has settled
    (web/js/slip.js `settleOne`), field for field, or None while it is
    open — and None for a win with a pushed leg whose price is not known,
    which the page leaves for the member to set ("set the price your book
    paid"). The bet itself is never changed: a leg pushed is paid at the
    ticket's price without it, as `paid_odds`, which My Bets' profit reads."""
    if str(bet.get("result") or "pending") != "pending":
        return None
    n = (card or {}).get("now") or {}
    if n.get("status") == "lost":
        return {"result": "loss"}
    if n.get("status") != "won":
        return None
    if not n.get("push"):
        return {"result": "win"}
    if not n.get("won"):
        return {"result": "push"}
    pushed = [_dec(l.get("odds")) for l in card.get("legs") or []
              if (l.get("live") or {}).get("result") == "push"]
    whole = _dec(bet.get("odds"))
    if not whole or not pushed or not all(pushed):
        return None
    return {"result": "win", "paid_odds": _american(whole / math.prod(pushed))}


def _stamp(t: float) -> str:
    """The page's `new Date().toISOString()`: UTC, milliseconds, a Z."""
    return _dt.datetime.fromtimestamp(t, _dt.timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


def write_settles(conn, user_id: int, done: dict, at: str) -> int:
    """Settle saved slips in one member's stored My Bets: each entry a
    saved slip still pending whose id is in ``done`` takes those fields and
    the page's own marks (`settled_by` "box", `settled_at`); nothing else
    in the row is touched, and a book that would outgrow the store's cap
    is left as it is. One read and one write under accounts.one_writer.
    Returns how many were settled."""
    from . import accounts as A
    n = 0
    with A.one_writer(conn):
        row = conn.execute("SELECT payload FROM user_data WHERE user_id=? AND section='mybets'",
                           (int(user_id),)).fetchone()
        try:
            data = json.loads(row["payload"]) if row is not None else None
        except ValueError:
            data = None
        bets = data.get("rows") if isinstance(data, dict) else None
        if not isinstance(bets, list):
            return 0
        for b in bets:
            if not (isinstance(b, dict) and b.get("src") == "slip"
                    and str(b.get("result") or "pending") == "pending"):
                continue
            got = done.get(str(b.get("id")))
            if got is None:
                continue
            b.update(got)
            b["settled_by"] = "box"
            b["settled_at"] = at
            n += 1
        blob = json.dumps(data)
        if not n or len(blob) > A.MAX_SECTION_BYTES:
            return 0
        conn.execute("UPDATE user_data SET payload=? WHERE user_id=? AND section='mybets'",
                     (blob, int(user_id)))
    return n


def budget_ok(now: float | None = None) -> bool:
    """Take one send from today's allowance, or say there is none left."""
    t = time.time() if now is None else now
    with _LOCK:
        _SENT[:] = [x for x in _SENT if t - x < 86400]
        if len(_SENT) >= MAIL_PER_DAY:
            return False
        _SENT.append(t)
        return True


def boards_and_live():
    """The boards and the live reader as the Live tab's endpoint builds
    them (server._ask_track): every league's full board, parsed once per
    write of its file."""
    from . import askbot as AB
    from . import gate as GATE_
    from . import sliplive as SL
    boards, prices = {}, {}
    for league, name in AB.BOARD_FILES.items():
        path = GATE_.full_board_file(name)
        got = AB.board_at(path) if path else None
        if got:
            boards[league] = got
            prices[league] = AB.prices_at(path)
    return boards, SL.Live(prices)


def sweep(conn, boards: dict, live, *, rows: list | None = None, send=None, entitled=None,
          mail_on=None, now: float | None = None, site: str = "", log=print) -> dict:
    """One pass over every member's open saved slips. Returns the counts:
    slips read, alerts newly noted, emails sent, emails that failed, slips
    settled in My Bets. Every open slip is graded every pass, an alerted
    one too: it is open until the box score settles it.

    ``send(to, subject, text, html)`` delivers (engine.mailer.send);
    ``entitled(conn, who)`` is the site's own gate (server.account_entitled)
    — with none given nobody is mailed and the alert is only noted;
    ``mail_on`` says whether a relay exists (engine.mailer.configured)."""
    from . import slipgrade as SG
    t = time.time() if now is None else now
    ensure_tables(conn)
    conn.execute("DELETE FROM slip_alerts WHERE fired_at < ?", (t - KEEP_DAYS * 86400,))
    conn.commit()
    rows = pending_slips(conn) if rows is None else rows
    out = {"slips": len(rows), "noted": 0, "mailed": 0, "failed": 0, "settled": 0}
    if not rows:
        return out
    if mail_on is None:
        from . import mailer
        mail_on = mailer.configured()
    if send is None:
        from . import mailer
        send = mailer.send
    settles: dict = {}
    for r in rows:
        bet = r["bet"]
        bid = str(bet["id"])[:40]
        slip = SG.clean_slip({"legs": bet.get("legs"), "stake": bet.get("stake"),
                              "total_odds": bet.get("odds"), "book": bet.get("book"),
                              "is_bet_slip": True})
        if not slip["legs"]:
            continue
        try:
            card = SG.grade(slip, boards, live=live, brief=True)
        except Exception as exc:                                   # noqa: BLE001
            log(f"  slip watch: a saved slip could not be read ({type(exc).__name__}: {exc})")
            continue
        done = settled(bet, card)
        if done is not None:
            settles.setdefault(r["user_id"], {})[str(bet["id"])] = done
            continue
        if noted(conn, r["user_id"], bid) or not last_leg(card):
            continue
        conn.execute("INSERT OR IGNORE INTO slip_alerts (user_id, bet_id, fired_at, mailed) "
                     "VALUES (?,?,?,0)", (r["user_id"], bid, t))
        conn.commit()
        out["noted"] += 1
        if not (mail_on and entitled is not None and optin_get(conn, r["user_id"])["on"]):
            continue
        who = {"id": r["user_id"], "email": r["email"]}
        try:
            ok = bool(entitled(conn, who))
        except Exception as exc:                                   # noqa: BLE001
            log(f"  slip watch: the gate could not be read ({type(exc).__name__}); not mailed")
            ok = False
        if not ok or not budget_ok(t):
            continue
        base = site or _site()
        subject, text, html = message(bet, card, link=f"{base}/unsubscribe/{link_token(conn, r['user_id'])}",
                                      site=base)
        try:
            send(r["email"], subject, text, html)
        except Exception as exc:                                   # noqa: BLE001
            out["failed"] += 1
            log(f"  ⚠️  slip watch: the last-leg email failed ({type(exc).__name__})")
            continue
        conn.execute("UPDATE slip_alerts SET mailed=1 WHERE user_id=? AND bet_id=?",
                     (r["user_id"], bid))
        conn.commit()
        out["mailed"] += 1
    for uid, done in settles.items():
        try:
            out["settled"] += write_settles(conn, uid, done, _stamp(t))
        except sqlite3.Error as exc:
            log(f"  slip watch: a member's My Bets could not be written ({type(exc).__name__}); "
                f"settled next minute")
    if out["noted"]:
        log(f"  slip watch: {out['noted']} saved slip(s) down to the last leg, {out['mailed']} emailed")
    if out["settled"]:
        log(f"  slip watch: {out['settled']} saved slip(s) settled in My Bets off the box score")
    return out


def run_once(entitled=None, log=print) -> dict:
    """One sweep on the box's own accounts database. Reads no board when
    no member has a saved slip open — the common minute."""
    from . import accounts as A
    conn = A.connect()
    try:
        ensure_tables(conn)
        rows = pending_slips(conn)
        if not rows:
            return {"slips": 0, "noted": 0, "mailed": 0, "failed": 0, "settled": 0}
        boards, live = boards_and_live()
        return sweep(conn, boards, live, rows=rows, entitled=entitled, site=A.site_url(), log=log)
    finally:
        conn.close()


def _site() -> str:
    from . import accounts as A
    return A.site_url()


# --- the message ----------------------------------------------------------------

def _money(x) -> str:
    try:
        return f"${float(x or 0):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _price(o) -> str:
    try:
        o = int(o)
    except (TypeError, ValueError):
        return ""
    return f"{o:+d}" if o else ""


def _kick(s: str) -> str:
    """"2026-10-18 16:25" → "Sun 4:25 PM ET", as the page's `kick` draws it."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})", str(s or ""))
    if not m:
        return ""
    import datetime as _dt
    try:
        day = _DAYS[_dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).weekday()]
    except ValueError:
        return ""
    h = int(m.group(4))
    return f"{day} {(h + 11) % 12 + 1}:{m.group(5)} {'AM' if h < 12 else 'PM'} ET"


def open_leg(card: dict) -> dict | None:
    """The leg still to decide it: the one with no result."""
    for l in card.get("legs") or []:
        if (l.get("live") or {}).get("result") is None:
            return l
    return None


def where(leg: dict) -> str:
    """Where the leg stands, in words: the score and the clock and his
    number so far, or when it kicks off — the Live tab's own line."""
    g = leg.get("live") or {}
    bits = []
    if g.get("state") == "live":
        if g.get("home_score") is not None and g.get("away_score") is not None:
            bits.append(f"{g.get('away')} {g.get('away_score')} – {g.get('home_score')} {g.get('home')}")
        if g.get("clock"):
            bits.append(str(g["clock"]))
        market = leg.get("market")
        if g.get("current") is not None and market not in ("moneyline", "spread"):
            bits.append(f"has {g['current']} so far")
        elif market == "moneyline" and g.get("win_prob") is not None:
            bits.append(f"{float(g['win_prob']):.0%} to win now")
        elif market == "spread" and g.get("cover_by") is not None:
            cb = float(g["cover_by"])
            bits.append(f"covering by {cb:g}" if cb > 0 else f"short by {-cb:g}" if cb < 0 else "right on the number")
    elif _kick(leg.get("kickoff") or ""):
        bits.append(f"kicks off {_kick(leg.get('kickoff'))}")
    else:
        bits.append("not started yet")
    return ", ".join(bits)


def message(bet: dict, card: dict, link: str, site: str) -> tuple[str, str, str]:
    """``(subject, text, html)``: the ticket, the leg left and where it
    stands, our chance for the rest, and the hedge's numbers from the card
    itself (slipgrade.hedge) — the arithmetic the Live tab shows, not a
    second copy of it. Both parts (engine.mailer.message), the
    unsubscribe on both."""
    import html as _html
    from . import slipgrade as SG
    now = card.get("now") or {}
    hd = card.get("hedge") or {}
    leg = open_leg(card) or {}
    name = hd.get("leg") or (SG._name(leg) if leg else "the last leg")
    # The member's own words, one line each and bounded: a header never
    # takes a newline, and a subject is not a place for a paragraph.
    book = " ".join(str(bet.get("book") or "").split())[:40]
    desc = " ".join(str(bet.get("desc") or "Your saved slip").split())[:160]
    subject = f"One leg left on your {book + ' ' if book and book != 'Other' else ''}slip: {name}"
    paras = [f"{desc} ({_money(bet.get('stake'))} at {_price(bet.get('odds')) or 'its price'}) "
             f"is down to its last leg."]
    stand = where(leg) if leg else ""
    line = f"{name}: {stand}." if stand else f"{name}."
    if now.get("chance") is not None:
        line += f" Our chance for the rest: {float(now['chance']):.0%}."
    paras.append(line)
    if hd.get("other") and hd.get("odds"):
        at = (f"{hd['other']} at {_price(hd['odds'])}" + (f" ({hd['book']})" if hd.get("book") else "")
              + (" — the price we last saw" if hd.get("stale") else ""))
        rows = [f"The hedge: {at}."]
        lock, back = hd.get("lock") or {}, hd.get("back") or {}
        if lock.get("hedge") and float(lock.get("either") or 0) > 0:
            rows.append(f"Lock it: bet {_money(lock['hedge'])} and you're up {_money(lock['either'])} "
                        f"whichever way it goes.")
        else:
            rows.append("At that price no hedge locks a profit — it would cost more than the ticket can win.")
        if back.get("hedge") and float(back.get("if_hits") or 0) > 0:
            rows.append(f"Stake back: bet {_money(back['hedge'])} — up {_money(back['if_hits'])} if it hits, "
                        f"nothing lost if it misses.")
        paras.append(" ".join(rows))
    paras.append(f"The Live tab has the hedge calculator, the cash-out check and the live line: {site}{LIVE_PATH}")
    foot = ("You asked for this on the Live tab, and you can switch it off there.\n"
            f"Stop these emails: {link}\n"
            "This is analysis, not advice. No bets are taken here.")
    text = "\n\n".join(paras) + "\n\n—\n" + foot + "\n"
    esc = lambda s: _html.escape(str(s), quote=True)                  # noqa: E731
    body = "".join(f"<p>{esc(p)}</p>" for p in paras[:-1])
    body += (f'<p><a href="{esc(site + LIVE_PATH)}" style="color:#e8b64c">Open the Live tab</a> — the hedge '
             "calculator, the cash-out check and the live line.</p>")
    html = ('<div style="background:#0b0906;color:#f5efe6;padding:26px;'
            'font-family:system-ui,-apple-system,sans-serif;max-width:600px">'
            '<p style="color:#e8b64c;font-weight:700;letter-spacing:.04em">QELLYS BOOK</p>'
            f"{body}"
            '<hr style="border:0;border-top:1px solid #2a2622;margin:22px 0">'
            '<p style="color:#8b8178;font-size:12px">You asked for this on the Live tab, and you can switch '
            f'it off there. <a href="{esc(link)}" style="color:#8b8178">Stop these emails</a>.<br>'
            "This is analysis, not advice. No bets are taken here.</p></div>")
    return subject, text, html
