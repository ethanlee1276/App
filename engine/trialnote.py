"""The free trial's reminder: one email about a day before it turns into a charge.

    python3 -m engine.trialnote            # who is due a reminder now (no addresses printed)
    python3 -m engine.trialnote --send     # and send them — the billing sweep does this every 30 min

The trial (engine/billing TRIAL_DAYS, the monthly plan only) takes a card up
front and charges it when the three days are up. The Terms say so in full
(§5.3); this is the other half of saying it plainly. About a day before the
charge, the member gets ONE email: when the trial ends, what is charged
then, and the button that cancels it. It is about money they are about to
be charged, not a sales email, so it carries no unsubscribe — and it goes
once per trial, which is what makes that fair.

WHO GETS ONE: a `trialing` subscription whose trial ends within
REMIND_WITHIN_S and that is not already set to cancel (cancelling during a
trial means no charge, so there is nothing to remind them of).
`subscriptions.trial_noted` holds the trial end the row was last reminded
about, so the next sweep does not send it again, and a trial end that
Stripe moves gets its own. A phone account (engine/smsverify) has no
address: it is marked and skipped, and the Live tab's line (js/chat.js
lvmTrialHTML) still tells them.

AND ON THE PHONE (Ethan, 2026-10-29: members 21 to 35 read their
notifications, not their email): the same warning goes to every phone the
member is signed in on (engine/lifecycle.trial_push, the account topic),
once, mail relay or not.

Marked once it reached them by either: without a mail relay and with no
phone signed in, nothing is marked, so the reminder still goes if a relay
is set before the trial ends. An email that fails is not marked, push or
no push (a queued push is not a delivered one: a paused phone never shows
it); the next sweep tries the email again, and the push is not repeated.

Standard library only. The address is never printed or logged.
"""
from __future__ import annotations

import html as _html
import time

#: How long before the charge the reminder goes. A day, and the sweep runs
#: every 30 minutes (launch.BILLING_SWEEP_S), so it lands 23½–24 hours out.
REMIND_WITHIN_S = 24 * 3600

#: The most one sweep sends. Far above any real day; a bound on a loop
#: that talks to a mail relay.
MAX_PER_SWEEP = 200

ACCOUNT_PATH = "/#account"
ET = "America/New_York"
_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def due(conn, now: float | None = None) -> list[dict]:
    """The rows owed a reminder now: ``{user_id, period_end, plan, email}``."""
    now = time.time() if now is None else float(now)
    rows = conn.execute(
        "SELECT s.user_id, s.period_end, s.plan, u.email FROM subscriptions s "
        "JOIN users u ON u.id = s.user_id "
        "WHERE s.status = 'trialing' AND s.period_end > ? AND s.period_end <= ? "
        "AND COALESCE(s.cancel_at_end, 0) = 0 "
        "AND (s.trial_noted IS NULL OR s.trial_noted != s.period_end) "
        "ORDER BY s.period_end LIMIT ?",
        (now, now + REMIND_WITHIN_S, MAX_PER_SWEEP)).fetchall()
    return [dict(r) for r in rows]


def mark(conn, user_id: int, period_end: float) -> None:
    conn.execute("UPDATE subscriptions SET trial_noted=? WHERE user_id=?",
                 (float(period_end), int(user_id)))
    conn.commit()


def when(period_end: float, now: float | None = None) -> tuple[str, str]:
    """``("tomorrow", "tomorrow, Tue Oct 27, at 8:14 PM ET")`` — the day
    word for the subject, and the full time for the body, in Eastern time
    like every kickoff on the site."""
    import datetime as _dt
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(ET)
    end = _dt.datetime.fromtimestamp(float(period_end), tz)
    today = _dt.datetime.fromtimestamp(time.time() if now is None else float(now), tz).date()
    gap = (end.date() - today).days
    day = "today" if gap <= 0 else "tomorrow" if gap == 1 else _DAYS[end.weekday()]
    clock = f"{(end.hour + 11) % 12 + 1}:{end.minute:02d} {'AM' if end.hour < 12 else 'PM'} ET"
    date = f"{_DAYS[end.weekday()][:3]} {end.strftime('%b')} {end.day}"
    return day, (f"{day}, {date}, at {clock}" if gap in (0, 1) else f"{date} at {clock}")


def message(period_end: float, plan: str | None, site: str,
            now: float | None = None) -> tuple[str, str, str]:
    """``(subject, text, html)`` for one member's reminder."""
    from . import billing as BI
    p = BI.PLANS.get(plan or "") or BI.PLANS[BI.TRIAL_PLAN]
    price = f"${p['cents'] / 100:,.2f}"
    every = {1: "every month", 6: "every 6 months", 12: "every year"}.get(int(p["months"]), "each term")
    day, full = when(period_end, now)
    link = site.rstrip("/") + ACCOUNT_PATH
    subject = f"Your free trial ends {day}"
    paras = [
        f"Your {BI.TRIAL_DAYS}-day free trial of Qellys Book ends {full}.",
        f"Then your card is charged {price} for the {p['name']} plan, and {every} after that until you cancel.",
        "To keep it, there is nothing to do.",
        "To cancel, open your account page and press Manage billing, then Cancel. "
        "Cancel before the trial ends and you are charged nothing.",
    ]
    foot = ("You are getting this because you started a free trial. It is the one reminder we send about it.\n"
            "This is analysis, not advice. No bets are taken here.")
    text = "\n\n".join(paras) + f"\n\nYour account page: {link}\n\n—\n" + foot + "\n"
    esc = lambda s: _html.escape(str(s), quote=True)                  # noqa: E731
    body = "".join(f"<p>{esc(x)}</p>" for x in paras)
    body += f'<p><a href="{esc(link)}" style="color:#e8b64c">Open your account page</a></p>'
    html = ('<div style="background:#0b0906;color:#f5efe6;padding:26px;'
            'font-family:system-ui,-apple-system,sans-serif;max-width:600px">'
            '<p style="color:#e8b64c;font-weight:700;letter-spacing:.04em">QELLYS BOOK</p>'
            f"{body}"
            '<hr style="border:0;border-top:1px solid #2a2622;margin:22px 0">'
            '<p style="color:#8b8178;font-size:12px">You are getting this because you started a free trial. '
            "It is the one reminder we send about it.<br>"
            "This is analysis, not advice. No bets are taken here.</p></div>")
    return subject, text, html


def run(conn, send=None, now: float | None = None, site: str | None = None, log=print) -> int:
    """Send every reminder that is due; how many went. ``send(to, subject,
    text, html)`` defaults to engine.mailer.send, and to nothing at all when
    no relay is configured."""
    from . import billing as BI
    from . import lifecycle as LC
    from . import smsverify as SV
    BI.init(conn)
    if send is None:
        from . import mailer
        send = mailer.send if mailer.configured() else None
    if site is None:
        from . import accounts as A
        site = A.site_url()
    sent = 0
    for r in due(conn, now):
        # PHONE FIRST (Ethan, 2026-10-29: "they'll just check their actual
        # phone notifications more"): the same warning on every phone they
        # are signed in on (engine/lifecycle), mail relay or not.
        pushed = LC.trial_push(conn, r["user_id"], r["period_end"], r.get("plan"), now=now)
        to = str(r.get("email") or "").strip()
        mailed = False
        if send and to and not SV.is_placeholder(to):
            subject, text, html = message(r["period_end"], r.get("plan"), site, now)
            try:
                send(to, subject, text, html)
                mailed = True
            except Exception as e:                    # noqa: BLE001 — the next sweep tries again
                # Not marked, push or no push: a queued push is not a
                # delivered one (a paused phone never shows it), and the
                # email is the warning in writing. The push went once (its
                # id); the next sweep tries the email again.
                log(f"trial reminder: one send failed ({type(e).__name__}); trying again next sweep")
                continue
        # Marked once it reached them either way; a phone account's that
        # reached neither still has the Live tab's line.
        if pushed or mailed or (send and (not to or SV.is_placeholder(to))):
            sent += int(pushed or mailed)
            mark(conn, r["user_id"], r["period_end"])
    return sent


def _cli(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python3 -m engine.trialnote",
                                 description="The free trial's day-before reminder.")
    ap.add_argument("--send", action="store_true", help="send the reminders that are due")
    a = ap.parse_args(argv)
    from . import accounts as A
    from . import billing as BI
    from . import mailer
    from . import secrets as _local
    _local.load_local_secrets()
    conn = A.connect()
    try:
        BI.init(conn)
        rows = due(conn)
        print(f"{len(rows)} trial{'s' if len(rows) != 1 else ''} end within "
              f"{REMIND_WITHIN_S // 3600} hours and are owed a reminder.")
        for r in rows:
            print(f"  account {r['user_id']}: ends {when(r['period_end'])[1]}")
        if mailer.configured():
            print("Mail relay: configured.")
        elif _local.system_env_hidden():
            print("Mail relay: not visible to this user (the settings file is root's; the service has it). "
                  "Names only: cd /srv/qellys && sudo ./deploy/setenv.sh --show")
        else:
            print("Mail relay: NOT configured — nothing will send (docs/EMAIL.md).")
        if a.send:
            print(f"Sent {run(conn)}.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
