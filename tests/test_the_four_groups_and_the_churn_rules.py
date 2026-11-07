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
import re
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


def _bet(c, uid, logged_day, date=None):
    at = int(dt.datetime.combine(logged_day, dt.time(19), tzinfo=dt.timezone(dt.timedelta(hours=-4))).timestamp() * 1000)
    row = c.execute("SELECT payload FROM user_data WHERE user_id = ? AND section = 'mybets'", (uid,)).fetchone()
    rows = json.loads(row[0])["rows"] if row else []
    rows.append({"id": f"{at}1234", "date": (date or logged_day).isoformat()})
    c.execute("INSERT OR REPLACE INTO user_data VALUES (?, 'mybets', 1, ?)", (uid, json.dumps({"rows": rows})))


def _yes(c, uid):
    c.execute("INSERT INTO activity_prefs (user_id, off, at) VALUES (?, 0, 0)", (uid,))


def test_the_north_star_counts_live_games_watched_with_a_stake_in_them():
    """The first paper's North Star, weekly active sweaters: a live game's
    page opened in the week, with a bet that week or a team followed."""
    c = _db()
    for uid in range(1, 6):
        _user(c, uid, 0)
        if uid != 4:
            _yes(c, uid)
    c.execute("INSERT INTO activity_prefs (user_id, off, at) VALUES (4, 1, 0)")
    _rows(c, 1, [0], views={"pbp": 300})                 # this week, follows a team
    c.execute("INSERT INTO user_data VALUES (1, 'settings', 1, ?)", (json.dumps({"teams": ["nfl:KC"]}),))
    _rows(c, 2, [8], views={"pbp": 300})                 # last week, with a bet that week
    _bet(c, 2, TODAY - dt.timedelta(days=8))
    _rows(c, 3, [0], views={"pbp": 300})                 # no bet, no team: watching, not sweating
    _rows(c, 4, [0], views={"pbp": 300})                 # said no
    c.execute("INSERT INTO user_data VALUES (4, 'settings', 1, ?)", (json.dumps({"teams": ["nfl:KC"]}),))
    _rows(c, 5, [0], views={"live": 300})                # the Live tab is not a game's page
    c.execute("INSERT INTO user_data VALUES (5, 'settings', 1, ?)", (json.dumps({"teams": ["nfl:KC"]}),))
    assert E.north_star(E.members(c, NOW), TODAY, c) == [1, 1, 0, 0]


def test_the_aha_moment_is_a_test_with_both_sides():
    c = _db()
    for uid, ago in ((6, 40), (7, 40), (8, 30), (9, 10)):
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (uid, f"u{uid}@example.com", NOW - ago * DAY, NOW))
        _yes(c, uid)
    _rows(c, 6, [40, 15], views={"pbp": 300})             # watched and logged on day one, here on day 25
    _bet(c, 6, TODAY - dt.timedelta(days=40))
    _rows(c, 7, [40], views={"live": 300})                # neither, and gone
    _rows(c, 8, [29], views={"pbp": 300})                 # both on day two, gone
    _bet(c, 8, TODAY - dt.timedelta(days=29), date=TODAY - dt.timedelta(days=28))
    _rows(c, 9, [10], views={"pbp": 300})                 # too new to tell
    _bet(c, 9, TODAY - dt.timedelta(days=10))
    assert E.aha(E.members(c, NOW), TODAY, c) == {"n": 3, "aha": 2, "kept_aha": 1, "kept_rest": 0}
    rep = "\n".join(E._body(E.members(c, NOW), TODAY, None, 28, None, c, NOW))
    assert "3 members signed up 4 to 12 weeks ago, too few to test yet" in rep, "under ten, no share"
    assert "north star, weekly active sweaters" in rep and "recency by frequency" in rep


def test_recency_by_frequency_with_the_money_in_each_cell():
    ms = {1: {"status": "active", "plan": "monthly"}, 2: {"status": "", "plan": ""},
          3: {"status": "active", "plan": "yearly"}, 4: {"status": "active", "plan": "monthly"}}
    fs = {1: {"l28": 2, "recency": 1}, 2: {"l28": 5, "recency": 8}, 3: {"l28": 15, "recency": 0},
          4: {"l28": 0, "recency": 40}}
    head, *rows = E.rfm_lines(ms, fs)
    assert re.split(r"\s{2,}", head.strip()) == ["1-3 days", "4-11 days", "12+ days"], head
    cells = [re.split(r"\s{2,}", r.strip())[1:] for r in rows]
    assert cells == [["1 (1)", "0 (0)", "1 (1)"], ["0 (0)", "1 (0)", "0 (0)"], ["0 (0)", "0 (0)", "0 (0)"]], cells


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
