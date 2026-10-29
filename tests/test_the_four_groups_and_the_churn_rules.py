"""The owner report's four groups and its churn rules (engine/engagement
four_groups, groups_lines, churn_flags).

Ethan's second research paper (2026-10-29): "Sort users into four groups and
treat each differently" (Champions, At-risk payers, Engaged free, Dormant)
and "Start with rules, not models. Flag a user when any of these trip". What
these hold:

  * the groups read each account's own last-seen day and its plan — no
    activity log — and the report prints them first, activity on or not,
    with the money in each and what to do;
  * the rules count only members who said yes to keeping their activity:
    gone 5+ days while their league plays, fewer bets than half their usual,
    fewer alerts opened two weeks running, paying with no pick opened in 5
    days.

Run directly: `python3 tests/test_the_four_groups_and_the_churn_rules.py`
"""
import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("QB_ACTIVITY", None)

from engine import activity as ACT                                # noqa: E402
from engine import engagement as E                                # noqa: E402

NOW = 1_793_304_000.0                                             # 2026-10-29 16:00 Eastern
DAY = 86400.0
TODAY = dt.date(2026, 10, 29)


def _db():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, created_at REAL, last_seen REAL)")
    c.execute("CREATE TABLE subscriptions (user_id INTEGER PRIMARY KEY, status TEXT, plan TEXT, updated_at REAL)")
    c.execute("CREATE TABLE user_data (user_id INTEGER, section TEXT, ts INTEGER, payload TEXT, "
              "PRIMARY KEY (user_id, section))")
    ACT.ensure_tables(c)
    return c


def _user(c, uid, seen_days_ago, status=None, plan="monthly"):
    c.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (uid, f"u{uid}@example.com", NOW - 200 * DAY,
                                                        NOW - seen_days_ago * DAY))
    if status:
        c.execute("INSERT INTO subscriptions VALUES (?, ?, ?, ?)", (uid, status, plan, NOW))


def test_the_four_groups_off_last_seen_and_the_plan():
    c = _db()
    _user(c, 1, 1, "active")                      # Champion
    _user(c, 2, 2, "trialing")                    # Champion (a trial pays nothing yet)
    _user(c, 3, 6, "active", "yearly")            # At-risk payer
    _user(c, 4, 45, "active")                     # paying and gone: still an at-risk payer, not dormant
    _user(c, 5, 3)                                # Engaged free
    _user(c, 6, 40)                               # Dormant
    _user(c, 7, 50, "canceled")                   # Dormant
    _user(c, 8, 3, "canceled")                    # paid before, here lately: everyone else
    _user(c, 9, 12)                               # free, between: everyone else
    g = E.four_groups(c, NOW)
    assert {k: v["n"] for k, v in g.items()} == {"Champions": 2, "At-risk payers": 2, "Engaged free": 1,
                                                 "Dormant": 2, "Everyone else": 2}, g
    assert g["Champions"]["monthly"] == 25 and g["At-risk payers"]["monthly"] == 25 + E.PLAN_MONTHLY["yearly"]
    rep = E.report(c, now=NOW)
    assert rep.index("the four groups") < rep.index("Nothing has been kept yet"), "first, activity log or not"
    for name, _who, do in E.GROUPS:
        assert name in rep and do in rep


def _rows(c, uid, days_ago, taps=0, views=None, sports=("nfl",)):
    for d in days_ago:
        day = (TODAY - dt.timedelta(days=d)).isoformat()
        c.execute("INSERT INTO activity_days (user_id, day, seconds, visits, taps, views, sports, hours) "
                  "VALUES (?,?,?,?,?,?,?,?)",
                  (uid, day, 300, 1, taps, json.dumps(views or {"live": 300}), json.dumps({s: 300 for s in sports}),
                   ",".join(["0"] * 24)))


def test_the_churn_rules_count_only_members_who_said_yes():
    c = _db()
    for uid in range(1, 7):
        _user(c, uid, 1, "active" if uid in (4, 5) else None)
        c.execute("INSERT INTO activity_prefs (user_id, off, at) VALUES (?, ?, 0)", (uid, 1 if uid == 6 else 0))
    _rows(c, 1, [6, 7, 8])                         # gone six days while the NFL plays
    _rows(c, 2, [0, 1], sports=("nfl",))           # here: keeps the NFL "playing"
    for d, taps in ((15, 5), (8, 3), (1, 1)):      # three weeks of alerts opened: 5, 3, 1
        _rows(c, 3, [d], taps=taps)
    _rows(c, 4, [1, 2], views={"live": 300})       # paying, no pick opened
    _rows(c, 5, [1], views={"likely": 120})        # paying, opened one
    _rows(c, 6, [9, 10])                           # said no: never counted
    bets = [{"date": (TODAY - dt.timedelta(days=d)).isoformat()} for d in (8, 9, 15, 16, 22, 23, 29, 30)]
    c.execute("INSERT INTO user_data VALUES (2, 'mybets', 1, ?)", (json.dumps({"rows": bets}),))
    ms = E.members(c, NOW)
    flags = E.churn_flags(ms, TODAY, c)
    assert flags == {"no visit in 5+ days while their league plays": 1,
                     "bets logged this week under half their 4-week average": 1,
                     "fewer alerts opened two weeks running": 1,
                     "paying, no pick opened in 5 days": 1}, flags


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
