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
    the days in WINBACK_DAYS after it ended, then never again;
  * the season bridge: anybody whose followed teams' leagues have all just
    finished their seasons hears, once, which leagues are on.

All three are promotional: a reached weekly limit or a pause silences them
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
#: A longer plan's renewal is told this many days before it: inside the
#: 15 to 45 days that state automatic-renewal laws ask of a yearly plan
#: (California's among them), with a margin for a pass that runs late.
#: It was 15, which the first pass to see it could miss by hours.
RENEW_DAYS = 21
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
                # Not marked: the email is tried again next pass (the push
                # went once already, by its id). A queued push is not a
                # delivered one: a paused phone never shows it.
                log(f"renewal notice: one email failed ({type(exc).__name__})")
                continue
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


# ---- a season's end and its start ----------------------------------------------------------
#: A league is ON with a game on its board in the next BRIDGE_AHEAD_DAYS.
BRIDGE_AHEAD_DAYS = 7
#: It has just FINISHED when nothing is ahead, its last game was
#: BRIDGE_QUIET_DAYS to BRIDGE_RECENT_DAYS ago, and the month is one its
#: season ends in. Ten quiet days outlast every break in a season's last
#: months (the Super Bowl's bye is two weeks, and by its tenth day the game
#: itself is in the week ahead; college's semifinals to its final, ten or
#: eleven); the months keep out the long breaks that come earlier (the
#: Olympics, the All-Star weeks).
BRIDGE_QUIET_DAYS = 10
BRIDGE_RECENT_DAYS = 24
BRIDGE_END_MONTHS = {"mlb": (10, 11), "nba": (5, 6, 7), "nhl": (5, 6, 7), "wnba": (9, 10, 11),
                     "nfl": (2, 3), "cfb": (1, 2)}
BRIDGE_LEAGUES = ("nfl", "cfb", "nba", "wnba", "nhl", "mlb")
#: It is BACK when it is on again after OPENER_GAP_DAYS off, and the note
#: goes out over the OPENER_DAYS after, to members away AWAY_DAYS or more.
OPENER_GAP_DAYS = 30
OPENER_DAYS = 7
AWAY_DAYS = 7


def _marks(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS season_marks (league TEXT PRIMARY KEY, last_on REAL NOT NULL, "
                 "last_game REAL NOT NULL DEFAULT 0, back_at REAL NOT NULL DEFAULT 0)")


def _in_window(lg: str, t: float) -> bool:
    """Inside the league's season window (engine/seasons), a week wider than its schedule."""
    from engine import seasons as SE
    day = _dt.datetime.fromtimestamp(t, ET).date()
    for start in (day.year - 1, day.year):
        try:
            a, b = SE.window(lg, start)
        except ValueError:
            return False
        if a <= day.isoformat() <= b:
            return True
    return False


def seasons(data_dir: Path, now: float | None = None, conn=None) -> tuple:
    """(leagues on, leagues just finished, leagues back after a break), off
    each public board's games. Given the accounts database it also keeps what
    it has seen of each league (season_marks: when it was last on, its last
    game, when it came back), so a board emptied after a final still knows
    when that final was, and a league's return is a change it saw."""
    from engine import pickem as PK
    t = time.time() if now is None else float(now)
    month = _dt.datetime.fromtimestamp(t, ET).month
    if conn is not None:
        _marks(conn)
    on, done, back = set(), set(), set()
    for lg in BRIDGE_LEAGUES:
        ks = [g["kickoff"] for g in PK.board_games(lg, Path(data_dir))]
        is_on = any(t <= k <= t + BRIDGE_AHEAD_DAYS * 86400 for k in ks)
        last = max([k for k in ks if k < t], default=0.0)
        if conn is not None:
            row = conn.execute("SELECT last_on, last_game, back_at FROM season_marks WHERE league = ?",
                               (lg,)).fetchone()
            if row is None:
                # FIRST SIGHT: inside its season, take it as on until now (no
                # "back" for a league already playing the day this ships).
                row = (t if _in_window(lg, t) else 0.0, 0.0, 0.0)
                conn.execute("INSERT INTO season_marks (league, last_on, last_game, back_at) VALUES (?,?,?,?)",
                             (lg, *row))
            last_on, last_game, back_at = (float(x or 0) for x in row)
            last = max(last, last_game)
            if is_on and t - last_on >= OPENER_GAP_DAYS * 86400:
                back_at = t
            conn.execute("UPDATE season_marks SET last_on = ?, last_game = ?, back_at = ? WHERE league = ?",
                         (t if is_on else last_on, last, back_at, lg))
            if is_on and back_at and t - back_at < OPENER_DAYS * 86400:
                back.add(lg)
        if is_on:
            on.add(lg)
        elif last and BRIDGE_QUIET_DAYS * 86400 <= t - last <= BRIDGE_RECENT_DAYS * 86400 \
                and month in BRIDGE_END_MONTHS.get(lg, ()):
            done.add(lg)
    if conn is not None:
        conn.commit()
    return on, done, back


def _and(words: list) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + f" and {words[-1]}"


def season_bridge(conn, now: float | None = None, web: Path = WEB) -> int:
    """The second paper's season bridge ("when a user's sport ends, suggests
    players to follow in the next one") and the report's "one note at a
    season's start" for the dormant, both by "When I've been away":

      * a member whose followed teams are all in leagues that just finished
        hears, once, which leagues are on and that following a team there
        brings its games, big moments and finals;
      * a member away AWAY_DAYS or more who follows a team in a league just
        back hears, once a season, that it is back and when their team
        plays first.

    Leagues, never players: a player to follow would be a pick by another
    name. Both share the away alert's one a week."""
    from engine import engagement as E
    from engine import kickoffs as KO
    from engine import pickem as PK
    from engine import pushmine as PM
    ensure_tables(conn)
    t = time.time() if now is None else float(now)
    on, done, back = seasons(Path(web) / "data", t, conn)
    if not on:
        return 0
    name = lambda lg: E.LEAGUE_NAME.get(lg, lg.upper())                 # noqa: E731
    playing = [name(lg) for lg in BRIDGE_LEAGUES if lg in on]
    year = _dt.datetime.fromtimestamp(t, ET).year
    firsts: dict = {}
    if back:
        for lg in back:
            for g in sorted(PK.board_games(lg, Path(web) / "data"), key=lambda g: g["kickoff"]):
                if g["kickoff"] >= t:
                    for us, them in ((g["home"], g["away"]), (g["away"], g["home"])):
                        firsts.setdefault((lg, KO.DV.canonical(lg, us.upper())), (us.upper(), them.upper(),
                                                                                 g["kickoff"]))
    told = 0
    # Only accounts with a phone that asked for "When I've been away" (a
    # team followed by a watch alone counts too: kickoffs.follows reads both).
    rows = conn.execute("SELECT DISTINCT u.id, u.last_seen, u.created_at FROM push_subs s JOIN users u "
                        "ON u.id = s.user_id WHERE (',' || s.topics || ',') LIKE ?", (f"%,{AWAY_TOPIC},%",)).fetchall()
    for uid, seen, created in rows:
        mine = KO.follows(conn, uid)
        leagues = {lg for lg, _abbr in mine}
        if not leagues or not _week_ok(conn, uid, t):
            continue
        msg = None
        if done and not leagues & on and leagues & done:
            ended = [name(lg) for lg in BRIDGE_LEAGUES if lg in leagues & done]
            title = f"{' and '.join(ended)} {'is' if len(ended) == 1 else 'are'} done for the season"
            msg = (f"away:bridge:{'-'.join(sorted(leagues & done))}:{year}", title,
                   f"{_and(playing)} {'is' if len(playing) == 1 else 'are'} on: follow a team there for its "
                   "games, big moments and final scores.")
        elif leagues & back and t - float(seen or created or t) >= AWAY_DAYS * 86400:
            lg = next(x for x in BRIDGE_LEAGUES if x in leagues & back)
            first = min((firsts[k] for k in mine if k in firsts and k[0] == lg), key=lambda f: f[2], default=None)
            body = (f"{first[0]} play {first[1]} {_day(first[2])}, {E._clock(first[2])}: the slate, the chats "
                    "and Call it are on the Live tab." if first else
                    "The slate, the chats and Call it are on the Live tab.")
            msg = (f"away:back:{lg}:{year}", f"The {name(lg)} is back", body)
        if msg and PM.tell(conn, uid, msg[0], AWAY_TOPIC, msg[1][:1].upper() + msg[1][1:], msg[2], "/#live",
                           ttl="away", now=t):
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
