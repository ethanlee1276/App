"""The email our own documents promise before a change that affects a member takes effect.

The Privacy Policy's §13: "If this policy changes in a way that materially
affects you, we will say so on the Service and email the address on your
account before it takes effect." The Terms' §15: notice by email at least
30 days before a change that materially affects your rights.

The change of 29 October 2026 (NOTICE), approved by Ethan that day: the
members' split counts an existing member's saved parlays unless they turn
it off, and the Terms gained posting rules and moderation, pick'em groups,
the free games and the alerts' limits. So:

* each account made before SINCE that has an email address is emailed once
  (`run`), at most DAY_MAX an Eastern day, between HOURS, through the site's
  own relay (engine/mailer), once Ethan arms it: QB_POLICY_NOTICE set to
  NOTICE. The push loop's lifecycle pass calls it;
* the members' split counts such an account only NOTICE_DAYS after its
  email went (`may_count`, read by engine/consensus), and an account with no
  email address (a phone sign-in) only NOTICE_DAYS after the change was
  posted on the site;
* the Terms' changes apply to it 30 days after its email (web/terms.html
  says so, and keeps the earlier version beside it).

KEPT: one row per account told, and when (`policy_notices`), named in the
Privacy Policy, deleted with the account and in Download my data.

    python3 -m engine.policynotice status     # how many told, how many to go
    python3 -m engine.policynotice preview    # the email, as a member gets it
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
import time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
#: The change this notice is about: the Privacy Policy's and the Terms' date.
NOTICE = "2026-10-29"
ENV = "QB_POLICY_NOTICE"
#: Accounts made from here on read the new documents when they signed up.
SINCE = _dt.datetime(2026, 10, 30, tzinfo=ET).timestamp()
#: How long after its notice a change may count a member.
NOTICE_DAYS = 7
#: An account with no email address is told by the site alone: counted from
#: a week after the change was posted, the date the policy names (a
#: calendar date, so the clocks going back on 1 November move nothing).
PHONE_FROM = _dt.datetime(2026, 11, 6, tzinfo=ET).timestamp()
#: The Terms' changes, this long after the email (their §15).
TERMS_DAYS = 30
#: Emails a day at most, leaving the relay room for password resets.
DAY_MAX = 60
#: Eastern hours it sends in.
HOURS = (10, 20)


def ensure_tables(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS policy_notices (
        user_id INTEGER NOT NULL, notice TEXT NOT NULL, sent_at REAL NOT NULL,
        PRIMARY KEY (user_id, notice))""")


def armed() -> bool:
    return os.environ.get(ENV, "").strip() == NOTICE


def _real(email) -> bool:
    from engine import smsverify as SV
    e = str(email or "").strip()
    return bool(e) and "@" in e and not SV.is_placeholder(e)


def _day_start(now: float) -> float:
    d = _dt.datetime.fromtimestamp(now, ET)
    return _dt.datetime(d.year, d.month, d.day, tzinfo=ET).timestamp()


def pending(conn) -> list:
    """[(user_id, email)] still to be told, oldest account first."""
    ensure_tables(conn)
    rows = conn.execute("SELECT u.id, u.email FROM users u LEFT JOIN policy_notices n ON n.user_id = u.id "
                        "AND n.notice = ? WHERE n.user_id IS NULL AND u.created_at < ? ORDER BY u.id",
                        (NOTICE, SINCE)).fetchall()
    return [(int(r[0]), str(r[1])) for r in rows if _real(r[1])]


def _when(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts, ET).strftime("%-d %B %Y")


def message(now: float, site: str = "https://qellysbook.com") -> tuple:
    """(subject, text, html) for an email sent at ``now``."""
    site = site.rstrip("/")
    start, terms = _when(now + NOTICE_DAYS * 86400), _when(now + TERMS_DAYS * 86400)
    subject = "Changes to the Qellys Book Terms and Privacy Policy"
    points = [
        ("The members' split", f"From {start} at the earliest, the game-line legs of your open saved parlays may "
         "be counted with every other member's into the share on each side that a game's page shows (only once "
         "50 or more are in), and your saved parlays' closing-line value pooled into one number on the Edge "
         "Report. Never your name, never a player prop. To stay out: Settings, then Your data, then turn off "
         "\"Count my bets in the members' split\"."),
        ("Two new choices, both off unless you turn them on", "Keeping a daily record of your own time on the "
         "site, for your alerts (Settings, then Your activity), and putting your closing-line numbers on the "
         "members' leaderboard (My Bets)."),
        ("The Terms", "They now cover what may be posted and how posts are moderated, pick'em groups, the free "
         f"games, alerts, limits and the reminder before a longer plan renews. For your account they take effect "
         f"on {terms}, 30 days from this email."),
    ]
    text = ("We have updated the Qellys Book Terms of Service and Privacy Policy (29 October 2026). "
            "What changes for you:\n\n" + "\n\n".join(f"* {h}. {b}" for h, b in points) +
            f"\n\nThe Terms: {site}/terms.html\nThe Privacy Policy: {site}/privacy.html\n\n"
            "Questions, or to object: qellysbook@gmail.com\n\nQellys Book\n")
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")   # noqa: E731
    html = ("<p>We have updated the Qellys Book Terms of Service and Privacy Policy (29 October 2026). "
            "What changes for you:</p><ul>" + "".join(f"<li><b>{esc(h)}.</b> {esc(b)}</li>" for h, b in points) +
            f"</ul><p><a href=\"{site}/terms.html\">The Terms</a> · <a href=\"{site}/privacy.html\">The Privacy "
            "Policy</a></p><p>Questions, or to object: "
            "<a href=\"mailto:qellysbook@gmail.com\">qellysbook@gmail.com</a></p><p>Qellys Book</p>")
    return subject, text, html


def run(conn, now: float | None = None, send=None, site: str | None = None, log=print) -> int:
    """Email the next few accounts, inside today's allowance and hours,
    while armed. Returns how many went. A failure stops the pass (the relay
    is down, most likely); the rest go on a later one."""
    if not armed():
        return 0
    t = time.time() if now is None else float(now)
    if not HOURS[0] <= _dt.datetime.fromtimestamp(t, ET).hour < HOURS[1]:
        return 0
    if send is None:
        from engine import mailer
        if not mailer.configured():
            return 0
        send = mailer.send
    ensure_tables(conn)
    today = conn.execute("SELECT COUNT(*) FROM policy_notices WHERE notice = ? AND sent_at >= ?",
                         (NOTICE, _day_start(t))).fetchone()[0]
    room = DAY_MAX - int(today)
    if room <= 0:
        return 0
    if site is None:
        from engine import accounts as A
        site = A.site_url()
    subject, text, html = message(t, site)
    sent = 0
    for uid, email in pending(conn)[:room]:
        try:
            send(email, subject, text, html)
        except Exception as exc:                                   # noqa: BLE001 — a later pass tries again
            log(f"  policy notice: an email failed ({type(exc).__name__}); the rest wait for the next pass")
            break
        conn.execute("INSERT OR IGNORE INTO policy_notices (user_id, notice, sent_at) VALUES (?, ?, ?)",
                     (uid, NOTICE, t))
        conn.commit()
        sent += 1
    if sent:
        log(f"  policy notice: {sent} emailed, {len(pending(conn))} to go")
    return sent


def may_count(conn, uids, now: float | None = None) -> set:
    """Which of these accounts a change of NOTICE's may count yet: made
    after it, told by email NOTICE_DAYS ago or more, or with no email
    address and the change posted NOTICE_DAYS ago or more."""
    uids = {int(u) for u in uids}
    if not uids:
        return set()
    t = time.time() if now is None else float(now)
    ensure_tables(conn)
    marks = ",".join("?" * len(uids))
    told = {int(r[0]) for r in conn.execute(
        f"SELECT user_id FROM policy_notices WHERE notice = ? AND sent_at <= ? AND user_id IN ({marks})",
        [NOTICE, t - NOTICE_DAYS * 86400] + sorted(uids))}
    out = set()
    for uid, created, email in conn.execute(f"SELECT id, created_at, email FROM users WHERE id IN ({marks})",
                                            sorted(uids)):
        if float(created or 0) >= SINCE or int(uid) in told or (not _real(email) and t >= PHONE_FROM):
            out.add(int(uid))
    return out


def status(conn) -> dict:
    ensure_tables(conn)
    told = conn.execute("SELECT COUNT(*) FROM policy_notices WHERE notice = ?", (NOTICE,)).fetchone()[0]
    return {"notice": NOTICE, "armed": armed(), "told": int(told), "to_go": len(pending(conn)),
            "per_day": DAY_MAX}


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["preview"]:
        subject, text, _html = message(time.time())
        print(f"Subject: {subject}\n\n{text}")
        return 0
    from engine import accounts as A
    s = status(A.connect())
    # This shell may not see the service's settings (only root reads that
    # file), so whether it is sending is said only when it can be known.
    print(f"Notice of {s['notice']}: {s['told']} told, {s['to_go']} to go "
          f"({s['per_day']} a day at most, 10:00 to 20:00 Eastern). "
          + ("This shell has it armed." if s["armed"] else
             f"The service sends while its {ENV} is {NOTICE}: sudo ./deploy/setenv.sh --show shows it."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
