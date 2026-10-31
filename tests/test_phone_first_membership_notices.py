"""Phone first: membership notices on every signed-in phone, and the recaps
by push (engine/lifecycle, engine/trialnote, engine/pushalerts' account
topic, the Alerts page's "When I've been away").

Ethan, 2026-10-29: "a lot of our users are between the ages of 21 and 35
... they don't check emails and they'll just check their actual phone
notifications more. So the app should be sending these type of email
notifications as well." What these hold:

  * every phone signed in to an account wants the account notices,
    whatever its Alerts list said, and nothing is added to that list; a
    phone signed out never gets one;
  * the free trial's charge warning goes to those phones too, relay or
    not, once; a member with neither a phone nor a relay is not marked;
  * a six-month or yearly plan renewing within RENEW_DAYS hears so once a
    period, on the phone and by email (unless QB_RENEW_EMAIL=0); a monthly
    plan, a plan set to cancel, or a renewal further out do not;
  * a paying member gone five days (not thirty) gets their week and the
    board's, losses included, once a week; a member whose plan ended hears
    what the board did since on days 3, 14 and 30, and never past them;
    both only in the day, both silenced by a reached limit (PROMO);
  * the Alerts page and the alerts sheet offer "When I've been away" to
    every signed-in member, and the policy says all of it.

Run directly: `python3 tests/test_phone_first_membership_notices.py`
"""
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import accounts as A                                  # noqa: E402
from engine import billing as BI                                  # noqa: E402
from engine import lifecycle as LC                                # noqa: E402
from engine import pushalerts as PA                               # noqa: E402
from engine import pushmine as PM                                 # noqa: E402
from engine import trialnote as TN                                # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
ET = ZoneInfo("America/New_York")
HOUR, DAY = 3600.0, 86400.0
NOW = dt.datetime(2026, 10, 29, 14, 0, tzinfo=ET).timestamp()     # Thursday 2 p.m. Eastern
QUIET = lambda *_: None                                           # noqa: E731


def _db(d):
    conn = A.connect(Path(d) / "a.db")
    BI.init(conn)
    PA.ensure_tables(conn)
    PM.ensure_tables(conn)
    LC.ensure_tables(conn)
    return conn


def _member(conn, email, status="active", ends_in=10 * DAY, plan="yearly", cancel=False, seen_ago=None):
    cur = conn.execute("INSERT INTO users (email, verifier, created_at, age_confirmed, terms_accepted_at, last_seen) "
                       "VALUES (?, 'x', ?, 1, ?, ?)",
                       (email, NOW - 90 * DAY, NOW - 90 * DAY, None if seen_ago is None else NOW - seen_ago))
    uid = int(cur.lastrowid)
    conn.execute("INSERT INTO subscriptions (user_id, customer_id, subscription_id, status, period_end, plan, "
                 "cancel_at_end, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                 (uid, f"cus_{uid}", f"sub_{uid}", status, NOW + ends_in, plan, int(cancel), NOW))
    conn.commit()
    return uid


def _phone(conn, uid, topics=("posted",), token=None):
    code, out = PA.subscribe(conn, token or f"{uid:02d}" * 16, kind="apns", user_id=uid, topics=list(topics))
    assert code == 200, out
    return out["topics"]


def _queued(conn, uid, kind=None):
    rows = conn.execute("SELECT id, kind, title, body, url FROM push_mine WHERE user_id = ? ORDER BY at", (uid,)).fetchall()
    return [tuple(r) for r in rows if kind is None or r[1] == kind]


def test_every_signed_in_phone_carries_the_account_topic():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _member(conn, "you@example.com")
        assert _phone(conn, uid, ["posted"]) == ["posted"], "nothing added to the phone's own list"
        assert PM.asked(conn, uid, "account") and not PM.asked(conn, uid, "away"), "but every signed-in phone wants it"
        code, out = PA.subscribe(conn, "ff" * 16, kind="apns", user_id=None, topics=["posted", "account"])
        assert code == 200 and out["topics"] == ["posted"], "never a choice in a list"
        assert not PM.asked(conn, 999, "account"), "no phone, nobody to tell"
        assert PA.ACCOUNT == LC.ACCOUNT_TOPIC and "account" not in LC_PROMO()
        assert PM.TTL_S["account"] >= 12 * HOUR and "account" in PM.HELD, "held overnight, still worth it at nine"


def LC_PROMO():
    from engine import limits as LM
    return LM.PROMO


def test_the_trial_warning_reaches_the_phone_too():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _member(conn, "trial@example.com", status="trialing", ends_in=20 * HOUR, plan="monthly")
        _phone(conn, uid)
        alone = _member(conn, "alone@example.com", status="trialing", ends_in=20 * HOUR, plan="monthly")
        os.environ.pop("QB_SMTP_HOST", None)
        n = TN.run(conn, send=None, now=NOW, site="https://example.com", log=QUIET)
        got = _queued(conn, uid, "account")
        assert n == 1 and len(got) == 1, (n, got)
        assert got[0][2].startswith("Your free trial ends") and "$25" in got[0][3] and "Cancel" in got[0][3]
        assert TN.run(conn, send=None, now=NOW + HOUR, site="https://example.com", log=QUIET) == 0, "once"
        left = {r["user_id"] for r in TN.due(conn, NOW + HOUR)}
        assert alone in left and uid not in left, "neither a phone nor a relay: not marked, so the email can still go"
        box = []
        TN.run(conn, send=lambda *a: box.append(a), now=NOW + 2 * HOUR, site="https://example.com", log=QUIET)
        assert [a[0] for a in box] == ["alone@example.com"], "the relay set later: the email goes then"


def test_a_longer_plan_hears_about_its_renewal_once():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        year = _member(conn, "year@example.com", plan="yearly", ends_in=10 * DAY)
        six = _member(conn, "six@example.com", plan="sixmonth", ends_in=14 * DAY)
        month = _member(conn, "month@example.com", plan="monthly", ends_in=10 * DAY)
        leaving = _member(conn, "leaving@example.com", plan="yearly", ends_in=10 * DAY, cancel=True)
        later = _member(conn, "later@example.com", plan="yearly", ends_in=40 * DAY)
        for u in (year, six, month, leaving, later):
            _phone(conn, u)
        box = []
        n = LC.renewals(conn, now=NOW, send=lambda *a: box.append(a), site="https://example.com", log=QUIET)
        assert n == 2 and sorted(a[0] for a in box) == ["six@example.com", "year@example.com"], box
        (mid, kind, title, body, url), = _queued(conn, year, "account")
        assert title.startswith("Your yearly plan renews") and "$225" in body and "cancel" in body and url == "/#account"
        assert not _queued(conn, month) and not _queued(conn, leaving) and not _queued(conn, later)
        assert LC.renewals(conn, now=NOW + DAY, send=lambda *a: box.append(a), log=QUIET) == 0, "once a period"
        # The next period's renewal is told again; with our email off, by phone alone.
        conn.execute("UPDATE subscriptions SET period_end = ? WHERE user_id = ?", (NOW + 365 * DAY, year))
        os.environ[LC.ENV_RENEW_EMAIL] = "0"
        try:
            box.clear()
            assert LC.renewals(conn, now=NOW + 356 * DAY, send=lambda *a: box.append(a), log=QUIET) == 1
            assert box == [], "QB_RENEW_EMAIL=0: Stripe's own email, ours off"
        finally:
            os.environ.pop(LC.ENV_RENEW_EMAIL, None)


def test_a_failed_email_is_tried_again_and_a_full_day_still_carries_the_notice():
    """The review of 2026-10-29: a queued push is not a delivered one (a
    paused phone never shows it), so a failed email is retried, push or no
    push; and the day's cap stops noise, never a charge warning."""
    def boom(*_a):
        raise OSError("relay down")
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _member(conn, "trial@example.com", status="trialing", ends_in=20 * HOUR, plan="monthly")
        _phone(conn, uid)
        assert TN.run(conn, send=boom, now=NOW, site="https://example.com", log=QUIET) == 0
        assert len(_queued(conn, uid, "account")) == 1, "the push went"
        assert uid in {r["user_id"] for r in TN.due(conn, NOW + HOUR)}, "not marked: the email is owed"
        box = []
        assert TN.run(conn, send=lambda *a: box.append(a), now=NOW + HOUR, site="https://example.com", log=QUIET) == 1
        assert [a[0] for a in box] == ["trial@example.com"] and len(_queued(conn, uid, "account")) == 1, \
            "the email went on the retry, and the push did not go twice"
        year = _member(conn, "year@example.com", plan="yearly", ends_in=10 * DAY)
        _phone(conn, year)
        assert LC.renewals(conn, now=NOW, send=boom, site="https://example.com", log=QUIET) == 0
        assert LC.renewals(conn, now=NOW + HOUR, send=lambda *a: box.append(a), site="https://example.com",
                           log=QUIET) == 1 and box[-1][0] == "year@example.com"
        # A phone whose day is used up: the promotional line waits, the notice goes.
        conn.execute("UPDATE push_subs SET day = ?, day_n = 99 WHERE user_id = ?", (PA.eastern_day(NOW), year))
        PM.tell(conn, year, "away:test", "away", "A line", "Body", "/", now=NOW) if PM.asked(conn, year, "away") else None
        conn.execute("UPDATE subscriptions SET period_end = ?, renew_noted = NULL WHERE user_id = ?",
                     (NOW + 12 * DAY, year))
        LC.renewals(conn, now=NOW + 2 * HOUR, send=lambda *a: None, site="https://example.com", log=QUIET)
        sent = []
        PM.flush(conn, apns=lambda ep, m, cfg: sent.append(m["kind"]) or 200, apns_cfg={"x": 1},
                 now=NOW + 2 * HOUR, quiet=False)
        assert sent and set(sent) == {"account"}, sent


def test_close_finishes_are_one_a_game_a_day():
    a = PM.close_id("mlb:NYY@BOS", NOW)
    assert a == PM.close_id("mlb:NYY@BOS", NOW + 2 * HOUR), "the same game, whoever says it"
    assert a != PM.close_id("mlb:NYY@BOS", NOW + DAY), "the same two teams tomorrow are a new game"
    late = dt.datetime(2026, 10, 30, 0, 40, tzinfo=ET).timestamp()
    assert PM.close_id("nba:LAL@BOS", late) == PM.close_id("nba:LAL@BOS", late - 3 * HOUR), \
        "a finish after midnight is still last night's game"
    src = READ("engine", "kickoffs.py")
    assert 'PM.close_id(f"{lg}:{away}@{home}", t)' in src


def _web(days):
    web = Path(tempfile.mkdtemp())
    (web / "data").mkdir()
    curve = [{"date": d, "w": w, "l": l, "n": w + l, "day_u": u} for d, w, l, u in days]
    (web / "data" / "record.json").write_text(json.dumps({"pooled": {"curve": curve}}))
    return web


WEEK = _web([("2026-10-22", 3, 2, 0.8), ("2026-10-25", 4, 3, -0.5), ("2026-10-28", 2, 2, 0.1),
             ("2026-10-29", 9, 0, 9.0)])


def test_a_paying_member_gone_five_days_gets_their_week_and_the_board_s():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        gone = _member(conn, "gone@example.com", seen_ago=6 * DAY)
        here = _member(conn, "here@example.com", seen_ago=1 * DAY)
        dormant = _member(conn, "dormant@example.com", seen_ago=40 * DAY)
        for u in (gone, here, dormant):
            _phone(conn, u, ["posted", "away"])
        A.save_sections(conn, gone, {"mybets": {"ts": 1, "data": {"rows": [
            {"date": "2026-10-24", "stake": 10, "odds": -110, "result": "win", "desc": "Lakers ML"},
            {"date": "2026-10-26", "stake": 10, "odds": 120, "result": "loss", "desc": "Knicks ML"}]}}})
        assert LC.payer_recaps(conn, now=NOW, web=WEEK) == 1
        (mid, kind, title, body, url), = _queued(conn, gone, "away")
        assert title == "Your week at Qellys" and "The board: 9–7, +0.4u, every loss on the Record." in body, body
        assert "You: 1–1, −$0.91." in body and "manage" in body and url == "/#mybets", body
        assert not _queued(conn, here, "away") and not _queued(conn, dormant, "away")
        assert LC.payer_recaps(conn, now=NOW + 2 * DAY, web=WEEK) == 0, "once a week, the away alert's own"
        for never in ("bet now", "miss you", "discount", "%"):
            assert never not in (title + body).lower(), never


def test_a_plan_that_ended_hears_what_the_board_did_three_times_then_never():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _member(conn, "left@example.com", status="canceled", ends_in=-3 * DAY - HOUR, plan="monthly")
        _phone(conn, uid, ["posted", "away"])
        web = _web([("2026-10-26", 6, 4, 1.2), ("2026-10-27", 2, 3, -1.4)])
        assert LC.winbacks(conn, now=NOW, web=web) == 1
        (mid, kind, title, body, url), = _queued(conn, uid, "away")
        assert title == "Since your plan ended" and "8–7, −0.2u — losses included" in body and url == "/#record"
        assert LC.winbacks(conn, now=NOW + DAY, web=web) == 0, "day 4 is not a day it speaks"
        assert LC.winbacks(conn, now=NOW + 11 * DAY, web=web) == 1, "day 14"
        assert LC.winbacks(conn, now=NOW + 27 * DAY, web=web) == 1, "day 30"
        assert LC.winbacks(conn, now=NOW + 60 * DAY, web=web) == 0, "and never again"
        thin = _web([("2026-10-26", 1, 1, 0.0)])
        conn.execute("DELETE FROM engagement_away")
        other = _member(conn, "thin@example.com", status="canceled", ends_in=-3 * DAY - HOUR, plan="monthly")
        _phone(conn, other, ["away"])
        assert LC.winbacks(conn, now=NOW, web=thin) == 0, "under five graded: no record said"


def test_the_recaps_go_in_the_day_and_the_pages_offer_them():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _member(conn, "night@example.com", seen_ago=6 * DAY)
        _phone(conn, uid, ["away"])
        night = dt.datetime(2026, 10, 29, 23, 30, tzinfo=ET).timestamp()
        LC.run(conn, now=night, web=WEEK, log=QUIET)
        assert not _queued(conn, uid, "away"), "never a buzz at night"
        LC.run(conn, now=NOW, web=WEEK, log=QUIET)
        assert _queued(conn, uid, "away")
    more = READ("web", "js", "more.js")
    assert 'box("away", "When I’ve been away: my team’s next game, what’s new or my week, once a week at most", !signedIn),' in more
    acct = READ("web", "js", "account.js")
    assert 'const away = _acctUser && _acctUser.signed_in ? ["away"] : [];' in acct
    pm = READ("engine", "pushmine.py")
    assert "told += _lc.run(conn, now=t, web=Path(web), log=log)" in pm
    priv = READ("web", "privacy.html")
    assert "every phone signed in\n      to your account also gets a notice about your own membership" in priv
    assert "<code>engagement_away</code>" in priv


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
