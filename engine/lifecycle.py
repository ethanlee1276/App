"""Membership notices and recaps, phone first.

Ethan, 2026-10-29: "a lot of our users are between the ages of 21 and 35
... maybe a lot of those types of people don't check emails and they'll
just check their actual phone notifications more. So the app should be
sending these type of email notifications as well." So every message about
a member's own membership goes to their phones, and email carries only what
has to be in writing as well (the free trial's charge warning, a renewal
notice) — never instead of the phone.

THE ACCOUNT TOPIC ("account"). Notices about the member's own money: a free
trial turning into a charge tomorrow (engine/trialnote sends the email and
this sends the push), a six-month or yearly plan renewing in RENEW_DAYS.
Every phone signed in to the account wants it whatever its Alerts list
says, the way a receipt reaches you (engine/pushalerts.ACCOUNT);
it is never promotional, so a weekly limit does not silence it; a phone's
own pause and its quiet hours still hold it. Each notice goes once.

THE RECAPS (topic "away", the Alerts page's "When I've been away"). Value,
not a discount — the second research paper's churn section: "the response
is value, not a discount: send their Edge Report, or a short note on what
the model saw this week, including the losses":

  * a paying member not seen in PAYER_IDLE_DAYS (and seen in the last
    DORMANT_DAYS): their own week from My Bets and the board's, losses
    included, and that the plan is theirs to manage — once a week at most;
  * a member whose plan ended: what the board did since, win or lose, on
    the days in WINBACK_DAYS after it ended, then never again.

Both are promotional: a reached weekly limit or a pause silences them
(engine/limits.PROMO counts "away"), and they share the away alert's own
once-a-week (engine/engagement's `engagement_away`), so a member never
hears two in one week. "Seen" is the account's own last-seen day
(users.last_seen, refreshed once a day while signed in), so none of this
needs the activity log.

The board's record comes off the public Record's own curve
(web/data/record.json, `pooled.curve`): the same numbers anyone can read.
Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
ET = ZoneInfo("America/New_York")
ACCOUNT_TOPIC = "account"                # pushalerts.ACCOUNT: every signed-in phone wants it
AWAY_TOPIC = "away"
#: A longer plan's renewal is told this many days before it.
RENEW_DAYS = 15
RENEW_PLANS = ("sixmonth", "yearly")
#: Our own renewal email beside the push; QB_RENEW_EMAIL=0 leaves it to
#: Stripe's own upcoming-renewal emails when those are switched on.
ENV_RENEW_EMAIL = "QB_RENEW_EMAIL"
PAYER_IDLE_DAYS = 5
DORMANT_DAYS = 30
WINBACK_DAYS = (3, 14, 30)
#: The away alert's one a week, shared (engine/engagement.AWAY_EVERY_S).
ONCE_A_WEEK_S = 7 * 86400
#: A week's record is said once this many of the board's picks graded in it.
MIN_GRADED = 5


def ensure_tables(conn) -> None:
    from engine import billing as BI
    from engine import engagement as E
    BI.init(conn)
    E.ensure_tables(conn)
    have = {r[1] for r in conn.execute("PRAGMA table_info(subscriptions)")}
    if "renew_noted" not in have:
        from engine.db import column_exists_or_raise
        try:
            conn.execute("ALTER TABLE subscriptions ADD COLUMN renew_noted REAL")
        except sqlite3.OperationalError as exc:
            column_exists_or_raise(exc)


def _day(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts, ET).strftime("%a %b %-d")


def _money(cents) -> str:
    return f"${int(cents) / 100:,.0f}" if int(cents) % 100 == 0 else f"${int(cents) / 100:,.2f}"


def board_record(since: str, until: str, web: Path = WEB) -> dict | None:
    """{"w", "l", "p", "u"} for the board's graded picks dated since..until
    (ISO, inclusive), off the public Record's curve; None under MIN_GRADED."""
    try:
        doc = json.loads((Path(web) / "data" / "record.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    w = l = n = 0
    u = 0.0
    for pt in ((doc.get("pooled") or {}).get("curve") or []):
        d = str((pt or {}).get("date") or "")[:10]
        if since <= d <= until:
            w += int(pt.get("w") or 0)
            l += int(pt.get("l") or 0)
            n += int(pt.get("n") or 0)
            u += float(pt.get("day_u") or 0)
    if w + l < MIN_GRADED:
        return None
    return {"w": w, "l": l, "p": max(0, n - w - l), "u": round(u, 1)}


def record_words(r: dict) -> str:
    rec = f"{r['w']}–{r['l']}" + (f"–{r['p']}" if r["p"] else "")
    return f"{rec}, {'+' if r['u'] >= 0 else '−'}{abs(r['u']):.1f}u"


# ---- the account topic ----------------------------------------------------------------
def trial_push(conn, user_id, period_end: float, plan: str | None, now: float | None = None) -> bool:
    """The free trial's charge warning on the member's phones (the email's
    twin, engine/trialnote). True when it was queued."""
    from engine import billing as BI
    from engine import pushmine as PM
    cents = (BI.PLANS.get(plan or "") or BI.PLANS["monthly"])["cents"]
    return PM.tell(conn, user_id, f"account:trial:{int(period_end)}", ACCOUNT_TOPIC,
                   f"Your free trial ends {_day(period_end)}",
                   f"Then {_money(cents)} is charged. Cancel any time before in your account — no charge if you do.",
                   "/#account", ttl="account", now=now)


def renewals(conn, now: float | None = None, send=None, site: str | None = None, log=print) -> int:
    """Each six-month or yearly plan renewing within RENEW_DAYS hears so,
    once a period: on its phones, and by email unless QB_RENEW_EMAIL=0."""
    from engine import billing as BI
    from engine import pushmine as PM
    from engine import smsverify as SV
    ensure_tables(conn)
    t = time.time() if now is None else float(now)
    rows = conn.execute(
        "SELECT s.user_id, s.period_end, s.plan, u.email FROM subscriptions s JOIN users u ON u.id = s.user_id "
        "WHERE s.status = 'active' AND s.plan IN (?, ?) AND COALESCE(s.cancel_at_end, 0) = 0 "
        "AND s.period_end > ? AND s.period_end <= ? "
        "AND (s.renew_noted IS NULL OR s.renew_noted != s.period_end)",
        (*RENEW_PLANS, t, t + RENEW_DAYS * 86400)).fetchall()
    mail = os.environ.get(ENV_RENEW_EMAIL, "1").strip() != "0"
    if mail and send is None:
        from engine import mailer
        send = mailer.send if mailer.configured() else None
    told = 0
    for uid, end, plan, email in rows:
        p = BI.PLANS[plan]
        title = f"Your {p['name'].lower()} plan renews {_day(end)}"
        body = f"{_money(p['cents'])} then. Keep it, or manage and cancel it any time in your account."
        pushed = PM.tell(conn, uid, f"account:renew:{int(end)}", ACCOUNT_TOPIC, title, body, "/#account",
                         ttl="account", now=t)
        mailed = False
        to = str(email or "").strip()
        if mail and send and to and not SV.is_placeholder(to):
            link = f"{(site or _site()).rstrip('/')}/#account"
            try:
                send(to, title, f"{title}.\n\n{body}\n\nYour account: {link}\n",
                     f"<p>{title}.</p><p>{body}</p><p><a href=\"{link}\">Your account</a></p>")
                mailed = True
            except Exception as exc:                          # noqa: BLE001 — the next pass tries again
                log(f"renewal notice: one email failed ({type(exc).__name__})")
        if pushed or mailed:
            conn.execute("UPDATE subscriptions SET renew_noted = ? WHERE user_id = ?", (end, uid))
            told += 1
    conn.commit()
    return told


def _site() -> str:
    from engine import accounts as A
    return A.site_url()


# ---- the recaps (topic "away") --------------------------------------------------------
def _week_ok(conn, user_id, t: float) -> bool:
    """The away alert's own once a week, shared: not sent in the last week."""
    row = conn.execute("SELECT sent_at FROM engagement_away WHERE user_id = ?", (int(user_id),)).fetchone()
    return not row or t - float(row[0]) >= ONCE_A_WEEK_S


def _sent(conn, user_id, t: float) -> None:
    conn.execute("INSERT INTO engagement_away (user_id, sent_at, sent_n) VALUES (?, ?, 1) "
                 "ON CONFLICT(user_id) DO UPDATE SET sent_at = excluded.sent_at, sent_n = sent_n + 1",
                 (int(user_id), t))


def payer_recaps(conn, now: float | None = None, web: Path = WEB) -> int:
    """A paying member gone PAYER_IDLE_DAYS: their week and the board's, once a week."""
    from engine import pushmine as PM
    ensure_tables(conn)
    t = time.time() if now is None else float(now)
    today = _dt.datetime.fromtimestamp(t, ET).date()
    since, until = (today - _dt.timedelta(days=7)).isoformat(), (today - _dt.timedelta(days=1)).isoformat()
    board = board_record(since, until, web)
    rows = conn.execute(
        "SELECT s.user_id FROM subscriptions s JOIN users u ON u.id = s.user_id "
        "WHERE s.status IN ('active', 'trialing') AND u.last_seen IS NOT NULL AND u.last_seen <= ? AND u.last_seen > ?",
        (t - PAYER_IDLE_DAYS * 86400, t - DORMANT_DAYS * 86400)).fetchall()
    told = 0
    for (uid,) in rows:
        if not _week_ok(conn, uid, t):
            continue
        row = conn.execute("SELECT payload FROM user_data WHERE user_id = ? AND section = 'mybets'", (uid,)).fetchone()
        try:
            data = json.loads(row[0]) if row else None
        except (TypeError, ValueError):
            data = None
        mine = PM.week_summary((data or {}).get("rows") if isinstance(data, dict) else None, since, until)
        if not board and not mine:
            continue
        parts = []
        if board:
            parts.append(f"The board: {record_words(board)}, every loss on the Record.")
        if mine:
            parts.append(f"You: {mine['w']}–{mine['l']}, {'+' if mine['net'] >= 0 else '−'}{PM._money(abs(mine['net']))}.")
        parts.append("Your plan is yours to manage any time in your account.")
        week = f"{since}"
        if PM.tell(conn, uid, f"away:recap:{week}", AWAY_TOPIC, "Your week at Qellys", " ".join(parts),
                   "/#mybets" if mine else "/#record", ttl="away", now=t):
            _sent(conn, uid, t)
            told += 1
    conn.commit()
    return told


def winbacks(conn, now: float | None = None, web: Path = WEB) -> int:
    """A member whose plan ended: what the board did since, on the days in
    WINBACK_DAYS after it ended, win or lose, then never again."""
    from engine import pushmine as PM
    ensure_tables(conn)
    t = time.time() if now is None else float(now)
    today = _dt.datetime.fromtimestamp(t, ET).date()
    rows = conn.execute("SELECT user_id, period_end FROM subscriptions WHERE status = 'canceled' "
                        "AND period_end IS NOT NULL AND period_end > ? AND period_end < ?",
                        (t - (max(WINBACK_DAYS) + 1) * 86400, t)).fetchall()
    told = 0
    for uid, end in rows:
        ended = _dt.datetime.fromtimestamp(float(end), ET).date()
        days = (today - ended).days
        if days not in WINBACK_DAYS or not _week_ok(conn, uid, t):
            continue
        rec = board_record(ended.isoformat(), (today - _dt.timedelta(days=1)).isoformat(), web)
        if not rec:
            continue
        if PM.tell(conn, uid, f"away:since:{int(end)}:{days}", AWAY_TOPIC, "Since your plan ended",
                   f"The board went {record_words(rec)} — losses included, every pick on the Record.",
                   "/#record", ttl="away", now=t):
            _sent(conn, uid, t)
            told += 1
    conn.commit()
    return told


# ---- the season bridge ------------------------------------------------------------------
#: A league with no game on its board in the next BRIDGE_AHEAD_DAYS, whose
#: last game was within BRIDGE_RECENT_DAYS, has just finished its season.
BRIDGE_AHEAD_DAYS = 7
BRIDGE_RECENT_DAYS = 7
BRIDGE_LEAGUES = ("nfl", "cfb", "nba", "wnba", "nhl", "mlb")


def seasons(data_dir: Path, now: float | None = None) -> tuple:
    """(leagues playing, leagues just finished), off each public board's games."""
    from engine import pickem as PK
    t = time.time() if now is None else float(now)
    on, done = set(), set()
    for lg in BRIDGE_LEAGUES:
        ks = [g["kickoff"] for g in PK.board_games(lg, Path(data_dir))]
        if any(t <= k <= t + BRIDGE_AHEAD_DAYS * 86400 for k in ks):
            on.add(lg)
        elif ks and t - BRIDGE_RECENT_DAYS * 86400 <= max(ks) < t:
            done.add(lg)
    return on, done


def season_bridge(conn, now: float | None = None, web: Path = WEB) -> int:
    """The second paper's season bridge ("when a user's sport ends, suggests
    players to follow in the next one"): a member whose followed teams are
    all in leagues that just finished hears, once, which leagues are on
    and that following a team there brings its games, big moments and
    finals. By "When I've been away", sharing its one a week."""
    from engine import engagement as E
    from engine import pushmine as PM
    from engine import smartwall as SW
    ensure_tables(conn)
    t = time.time() if now is None else float(now)
    on, done = seasons(Path(web) / "data", t)
    if not on or not done:
        return 0
    playing = [E.LEAGUE_NAME.get(lg, lg.upper()) for lg in BRIDGE_LEAGUES if lg in on]
    words = playing[0] if len(playing) == 1 else ", ".join(playing[:-1]) + f" and {playing[-1]}"
    told = 0
    for uid, payload in conn.execute("SELECT user_id, payload FROM user_data WHERE section = 'settings'").fetchall():
        try:
            leagues = {lg for lg, _abbr in SW._teams(json.loads(payload))}
        except (TypeError, ValueError):
            continue
        if not leagues or leagues & on or not leagues & done or not _week_ok(conn, uid, t):
            continue
        ended = [E.LEAGUE_NAME.get(lg, lg.upper()) for lg in BRIDGE_LEAGUES if lg in leagues & done]
        title = f"{' and '.join(ended)} {'is' if len(ended) == 1 else 'are'} done for the season"
        if PM.tell(conn, uid, f"away:bridge:{'-'.join(sorted(leagues & done))}:{_dt.datetime.fromtimestamp(t, ET).year}",
                   AWAY_TOPIC, title[:1].upper() + title[1:],
                   f"{words[:1].upper() + words[1:]} {'is' if len(playing) == 1 else 'are'} on: follow a team "
                   "there for its games, big moments and final scores.",
                   "/#live", ttl="away", now=t):
            _sent(conn, uid, t)
            told += 1
    conn.commit()
    return told


#: The recaps go out in the day, Eastern: never a buzz at night, and inside
#: the away alert's three hours (pushmine.TTL_S) before quiet hours.
RECAP_HOURS = (11, 19)


def run(conn, now: float | None = None, web: Path = WEB, log=print) -> int:
    """The push loop's pass: renewals at any hour, the recaps in the day."""
    t = time.time() if now is None else float(now)
    steps = [lambda: renewals(conn, now=t, log=log)]
    if RECAP_HOURS[0] <= _dt.datetime.fromtimestamp(t, ET).hour < RECAP_HOURS[1]:
        steps += [lambda: payer_recaps(conn, now=t, web=web), lambda: winbacks(conn, now=t, web=web),
                  lambda: season_bridge(conn, now=t, web=web)]
    told = 0
    for step in steps:
        try:
            told += step()
        except Exception as exc:                              # noqa: BLE001 — one step never stops the others
            log(f"  ⚠️  lifecycle: {type(exc).__name__}: {exc}")
    return told
