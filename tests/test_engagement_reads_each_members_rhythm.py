"""The engagement model and what acts on it (engine/engagement, the "away"
alert, engine/pushalerts.IGNORED_N; docs/RETENTION.md §6).

Ethan, 2026-10-29: "look at other apps' algorithms and what they do ... and
let's start implementing that stuff." What these hold:

  * stages read each member's OWN rhythm: a Sunday-only fan is not lapsing
    on Friday, a daily reader is after a week; dormant at 30 days, gone at 60;
  * the best hour is the member's most engaged one among the hours an alert
    may go, never a quiet one;
  * the BG/BB visit model (Fader, Hardie and Shang 2010) is right: its
    "comes back in 28 days" and "days in the next 28" match simulation, and
    the fit recovers a known population; it is kept only when it beats the
    stage rule on members it never saw;
  * the owner's report has stages with revenue at risk, the power-user
    curve, DAU/MAU, signup-week cohorts, the model, ARPU and lifetime
    value; the demo runs on a made-up population;
  * "while you were away" goes to a lapsing member with the switch on, at
    their own hour, made of their own things (their team's game, then what
    shipped since they left, then their league's slate), once a week, never
    after three unanswered until they come back, never to the gone, never
    while activity is off;
  * a phone that never opens the picks-up and last-night alerts hears them
    once a day at most, and only while its member's activity is known.

Run directly: `python3 tests/test_engagement_reads_each_members_rhythm.py`
"""
import datetime as dt
import json
import os
import random
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("QB_ACTIVITY", None)

from engine import activity as ACT                                # noqa: E402
from engine import engagement as E                                # noqa: E402
from engine import pushalerts as PA                               # noqa: E402
from engine import pushmine as PM                                 # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
TODAY = dt.date(2026, 10, 29)
NOW = 1_793_304_000.0                                             # 2026-10-29 16:00 Eastern
EIGHT_PM = NOW + 4 * 3600


def _et(days=0, hour=20, minute=0) -> float:
    """An Eastern wall-clock time `days` after TODAY, as epoch seconds (the
    clocks change on November 1st, so a week is not always 604,800 seconds)."""
    from zoneinfo import ZoneInfo
    d = TODAY + dt.timedelta(days=days)
    return dt.datetime(d.year, d.month, d.day, hour, minute, tzinfo=ZoneInfo("America/New_York")).timestamp()


def _iso(days=0, hour=20, minute=20) -> str:
    return dt.datetime.fromtimestamp(_et(days, hour, minute), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Locks:
    def __enter__(self):
        self.old = (os.environ.get(ACT.ENV), ACT.POLICY)
        os.environ[ACT.ENV] = "1"
        p = Path(tempfile.mkdtemp()) / "privacy.html"
        p.write_text('<h3 id="your-activity">Your activity</h3>')
        ACT.POLICY = p
        return self

    def __exit__(self, *exc):
        env, ACT.POLICY = self.old
        if env is None:
            os.environ.pop(ACT.ENV, None)
        else:
            os.environ[ACT.ENV] = env


def _rows(days_ago, hour=20, sport="nfl", secs=600, taps=0):
    out = []
    for d in sorted(days_ago, reverse=True):
        hrs = [0] * 24
        hrs[hour] = secs
        out.append({"day": (TODAY - dt.timedelta(days=d)).isoformat(), "seconds": secs, "visits": 1, "taps": taps,
                    "views": {"live": secs}, "sports": {sport: secs}, "hours": hrs})
    return out


def _f(days_ago, signup_ago=120, **kw):
    return E.features(_rows(days_ago, **kw), TODAY - dt.timedelta(days=signup_ago), TODAY)


def test_stages_read_each_members_own_rhythm():
    weekly = _f([d for d in range(4, 90, 7)])                    # once a week, the last one 4 days ago
    assert weekly["usual_gap"] == 7 and E.stage(weekly) == "casual", weekly
    weekly_late = _f([d for d in range(12, 90, 7)])               # 12 days: inside 2.5 x 7
    assert E.stage(weekly_late) == "casual"
    weekly_gone = _f([d for d in range(19, 90, 7)])               # 19 days: past 17.5
    assert E.stage(weekly_gone) == "lapsing"
    daily = _f(list(range(8, 60)))                                 # every day, then 8 days away
    assert daily["usual_gap"] == 1 and E.stage(daily) == "lapsing", "a daily reader is drifting after a week"
    assert E.stage(_f(list(range(0, 20)))) == "power"
    assert E.stage(_f(list(range(0, 28, 3)))) == "regular"
    assert E.stage(_f(list(range(35, 90)))) == "dormant"
    assert E.stage(_f(list(range(61, 90)))) == "gone"
    assert E.stage(_f([1, 2], signup_ago=3)) == "new"
    never = E.features([], TODAY - dt.timedelta(days=40), TODAY, since=TODAY - dt.timedelta(days=20))
    assert never["recency"] == 20 and E.stage(never) == "lapsing", "away since the log began, not since signup"
    fresh = E.features([], TODAY - dt.timedelta(days=40), TODAY, since=None)
    assert fresh["recency"] == 0, "no log at all: nothing says they were away"


def test_the_best_hour_is_theirs_and_never_a_quiet_one():
    hours = [0] * 24
    hours[2], hours[20], hours[13] = 9000, 3000, 2000
    assert E.best_hour(hours) == 20, "2 a.m. is quiet hours: the next most engaged"
    assert E.best_hour([0] * 24) is None
    assert _f([1, 2, 3], hour=13)["best_hour"] == 13


def test_the_visit_model_matches_simulation():
    rnd = random.Random(3)
    true = (0.9, 2.2, 0.35, 6.0)
    rows = []
    for _ in range(3000):
        n = rnd.randint(5, 100)
        p, th = rnd.betavariate(*true[:2]), rnd.betavariate(*true[2:])
        alive, act = True, []
        for day in range(1, n + 29):
            if alive and rnd.random() < th:
                alive = False
            if alive and rnd.random() < p:
                act.append(day)
        past = [d for d in act if d <= n]
        fut = sum(1 for d in act if d > n)
        x, tx = len(past), (max(past) if past else 0)
        rows.append((E.p_back(true, x, tx, n), E.expected_days(true, x, tx, n), int(fut > 0), fut,
                     E.p_alive(true, x, tx, n)))
    rows.sort()
    k = len(rows) // 5
    for i in range(5):
        chunk = rows[i * k:(i + 1) * k]
        mean = lambda j: sum(r[j] for r in chunk) / len(chunk)        # noqa: E731
        assert abs(mean(0) - mean(2)) < 0.05, (i, mean(0), mean(2))
        assert abs(mean(1) - mean(3)) < 0.1 + 0.08 * mean(3), (i, mean(1), mean(3))
    assert all(0 <= r[4] <= 1 for r in rows)
    # Recency matters: the same three visits, the last one recent or long ago.
    assert E.p_alive(true, 3, 58, 60) > 0.9 > 0.2 > E.p_alive(true, 3, 10, 60)


def test_the_fit_recovers_a_known_population():
    rnd = random.Random(11)
    true = (0.9, 2.2, 0.35, 6.0)
    data = []
    for _ in range(1500):
        n = rnd.randint(1, 110)
        p, th = rnd.betavariate(*true[:2]), rnd.betavariate(*true[2:])
        alive, act = True, []
        for day in range(1, n + 1):
            if alive and rnd.random() < th:
                alive = False
            if alive and rnd.random() < p:
                act.append(day)
        data.append((len(act), max(act) if act else 0, n))
    a, b, g, d = E.fit_bgbb(data)
    assert abs(a / (a + b) - 0.29) < 0.03, (a, b)
    assert abs(g / (g + d) - 0.055) < 0.02, (g, d)


def _db():
    path = Path(tempfile.mkdtemp()) / "accounts.db"
    conn = sqlite3.connect(str(path))
    conn.executescript("""CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE,
                            verifier TEXT NOT NULL, created_at REAL NOT NULL, last_seen REAL);
                          CREATE TABLE user_data (user_id INTEGER NOT NULL, section TEXT NOT NULL, ts INTEGER NOT NULL,
                            payload TEXT NOT NULL, PRIMARY KEY (user_id, section));""")
    ACT.ensure_tables(conn)
    return conn


def _member(conn, uid, signup_ago, days_ago, yes=True, **kw):
    created = NOW - signup_ago * 86400
    conn.execute("INSERT INTO users (id, email, verifier, created_at) VALUES (?, ?, 'x', ?)",
                 (uid, f"m{uid}@example.com", created))
    if yes:                                       # they said yes (engine/activity: consent first)
        conn.execute("INSERT INTO activity_prefs (user_id, off, at) VALUES (?, 0, ?)", (uid, created))
    for r in _rows(days_ago, **kw):
        conn.execute("INSERT INTO activity_days (user_id, day, seconds, visits, taps, views, sports, hours) "
                     "VALUES (?,?,?,?,?,?,?,?)", (uid, r["day"], r["seconds"], r["visits"], r["taps"],
                                                  json.dumps(r["views"]), json.dumps(r["sports"]),
                                                  ",".join(map(str, r["hours"]))))
    conn.commit()


def _population(conn, n, seed=5):
    rnd = random.Random(seed)
    for uid in range(1, n + 1):
        signup = rnd.randint(30, 115)
        p, th = rnd.betavariate(0.9, 2.2), rnd.betavariate(0.35, 6.0)
        days, alive = [signup], True
        for k in range(signup - 1, -1, -1):
            if alive and rnd.random() < th:
                alive = False
            if alive and rnd.random() < p:
                days.append(k)
        _member(conn, uid, signup, days, hour=rnd.choice([12, 19, 20, 21]), sport=rnd.choice(["nfl", "nba"]))


def test_the_model_is_kept_only_when_it_beats_the_rule_held_out():
    conn = _db()
    few = E.heldout(conn, NOW)
    assert few["ok"] is False and "too few" in few["why"]
    _population(conn, 260)
    got = E.heldout(conn, NOW)
    assert got["ok"] and 0 <= got["brier_model"] <= 1 and 0 <= got["brier_rule"] <= 1, got
    assert got["holds"] == (got["brier_model"] < got["brier_rule"])
    path = Path(tempfile.mkdtemp()) / "model.json"
    saved = E.fit(conn, NOW, save=True, path=path)
    assert saved["saved"] == got["holds"] == path.exists(), saved
    if path.exists():
        doc = E.load_model(path)
        assert len(doc["params"]) == 4 and doc["heldout"]["brier_model"] == got["brier_model"]
    assert not E.fit(conn, NOW, save=False, path=Path(tempfile.mkdtemp()) / "no.json")["saved"]


def test_the_report_says_what_it_is():
    conn = _db()
    with _Locks():
        assert "Nothing has been kept yet" in E.report(conn, now=NOW)
        _population(conn, 80)
        _member(conn, 81, 60, list(range(1, 50)), yes=False)
        conn.execute("CREATE TABLE subscriptions (user_id INTEGER PRIMARY KEY, status TEXT, plan TEXT, "
                     "updated_at REAL NOT NULL, period_end REAL)")
        conn.executemany("INSERT INTO subscriptions (user_id, status, plan, updated_at) VALUES (?,?,?,?)",
                         [(u, "active", "monthly" if u % 2 else "yearly", NOW) for u in range(1, 21)]
                         + [(u, "canceled", "monthly", NOW - 86400) for u in range(21, 25)])
        rep = E.report(conn, now=NOW)
    for line in ("Activity: ON.", "members by stage", "revenue at risk", "the power-user curve", "DAU/MAU",
                 "new members by signup week", "visit model: not fitted yet", "paying members: 20",
                 "lifetime value", "(1 have not said yes to keeping their activity, or said no, and are not counted)"):
        assert line in rep, (line, rep)
    assert "Activity: OFF" in E.report(conn, now=NOW), "the switch's state is the first line"
    demo = E.demo(n=150)
    assert "DEMO" in demo and "the fit found" in demo and "members by stage" in demo


def _subscribe_away(conn, uid, topics="away"):
    PA.ensure_tables(conn)
    PA.subscribe(conn, "cd" * 32, kind="apns", user_id=uid, topics=topics.split(","))


def _board(games):
    d = Path(tempfile.mkdtemp())
    (d / "live_nfl.json").write_text(json.dumps({"games": games}))
    return d


def _game(event="401", away="DEN", home="KC", start="2026-10-30T00:20:00Z", state="pre"):
    return {"event_id": event, "away": away, "home": home, "live": {"state": state, "start_time": start}}


def _queued(conn, uid):
    return conn.execute("SELECT id, kind, title, body, url FROM push_mine WHERE user_id=? ORDER BY at",
                        (uid,)).fetchall()


def test_while_you_were_away_is_theirs_at_their_hour_and_stops():
    conn = _db()
    _member(conn, 1, 90, list(range(10, 80)), hour=20)               # daily, then ten days away: lapsing
    conn.execute("INSERT INTO user_data (user_id, section, ts, payload) VALUES (1, 'settings', 1, ?)",
                 (json.dumps({"teams": ["nfl:KC"]}),))
    _subscribe_away(conn, 1)
    board = lambda days: _board([_game(event=f"40{days}", start=_iso(days))])     # noqa: E731
    no_log = Path(tempfile.mkdtemp()) / "none.json"
    assert E.away_pass(conn, board(0), _et(0), changelog=no_log) == 0, "activity off: nothing"
    with _Locks():
        assert E.away_pass(conn, board(0), _et(0, 16), changelog=no_log) == 0, "16:00 is not their hour"
        assert E.away_pass(conn, board(0), _et(0), changelog=no_log) == 1
        (mid, kind, title, body, url), = _queued(conn, 1)
        assert kind == "away" and title == "DEN @ KC today, 8:20 PM ET" and url == "/#pbp/nfl/400", title
        for never in ("bet now", "miss you", "streak"):
            assert never not in (title + body).lower()
        assert E.away_pass(conn, board(0), _et(0, 20, 30), changelog=no_log) == 0, "once a week"
        assert E.away_pass(conn, board(7), _et(7), changelog=no_log) == 1, "a week on, at 8 p.m. Eastern again"
        assert E.away_pass(conn, board(14), _et(14), changelog=no_log) == 1
        assert E.away_pass(conn, board(21), _et(21), changelog=no_log) == 0, "three unanswered: stop"
        assert conn.execute("SELECT sent_n FROM engagement_away WHERE user_id=1").fetchone()[0] == 3
        # They come back on day 22: not away any more, and the count starts again.
        conn.execute("INSERT INTO activity_days (user_id, day, seconds, visits, hours) VALUES (1, ?, 60, 1, ?)",
                     ((TODAY + dt.timedelta(days=22)).isoformat(), ",".join(["0"] * 20 + ["60"] + ["0"] * 3)))
        assert E.away_pass(conn, board(23), _et(23), changelog=no_log) == 0
        assert conn.execute("SELECT sent_n FROM engagement_away WHERE user_id=1").fetchone()[0] == 0


def test_the_hook_is_their_own_things_in_order():
    conn = _db()
    _member(conn, 2, 90, list(range(10, 80)), hour=20, sport="nfl")
    _subscribe_away(conn, 2)
    log = Path(tempfile.mkdtemp()) / "changelog.json"
    log.write_text(json.dumps({"entries": [
        {"date": "2026-10-28", "kind": "ship", "title": "x", "body": "y" * 50, "alert": "Pick'em with friends.",
         "url": "/#feed/pickem/nfl"},
        {"date": "2026-10-01", "kind": "ship", "title": "old", "body": "y" * 50, "alert": "Old news.", "url": "/"}]}))
    f = E.features(ACT.rows(conn, 2, now=NOW), TODAY - dt.timedelta(days=90), TODAY)
    games = [("nfl", str(i), "A", "B", EIGHT_PM + 600) for i in range(4)]
    assert E.away_hook(conn, 2, f, games, EIGHT_PM, log)[0] == "New since you were here", "no team of theirs plays"
    assert E.away_hook(conn, 2, f, games, EIGHT_PM, log)[1] == "Pick'em with friends."
    old = Path(tempfile.mkdtemp()) / "changelog.json"
    old.write_text(json.dumps({"entries": [{"date": "2026-10-01", "kind": "ship", "title": "o", "body": "y" * 50,
                                            "alert": "Old news.", "url": "/"}]}))
    assert E.away_hook(conn, 2, f, games, EIGHT_PM, old) == (
        "4 NFL games today", "Scores, the game chats and Call it, all in one place.", "/?sport=nfl#live"), \
        "nothing shipped since they left: their league's slate"
    assert E.away_hook(conn, 2, f, games[:2], EIGHT_PM, old) is None, "nothing of theirs: no alert at all"


def test_never_to_the_gone():
    conn = _db()
    _member(conn, 3, 120, list(range(61, 100)), hour=20)
    conn.execute("INSERT INTO user_data (user_id, section, ts, payload) VALUES (3, 'settings', 1, ?)",
                 (json.dumps({"teams": ["nfl:KC"]}),))
    _subscribe_away(conn, 3)
    with _Locks():
        assert E.away_pass(conn, _board([_game(start=_iso(0))]), _et(0), changelog=Path("/nonexistent")) == 0


def test_a_phone_that_never_opens_them_hears_them_once_a_day():
    conn = sqlite3.connect(":memory:")
    ACT.ensure_tables(conn)
    PA.ensure_tables(conn)
    PA.subscribe(conn, "ab" * 32, kind="apns", user_id=8)
    sent = []
    apns = lambda e, m, cfg: sent.append(m["kind"]) or 200                   # noqa: E731
    msg = {"id": "settled:d", "kind": "settled", "league": "", "title": "t", "body": "b", "url": "/"}
    kw = dict(apns=apns, apns_cfg={"x": 1}, vapid={"x": 1})
    PA.send(conn, [msg], now_s=NOW, **kw)
    assert conn.execute("SELECT unopened FROM push_subs").fetchone()[0] == 0, "activity off: nothing counted"
    with _Locks():
        PA.send(conn, [dict(msg, id="settled:d2")], now_s=NOW + 30, **kw)
        assert conn.execute("SELECT unopened FROM push_subs").fetchone()[0] == 0, "no yes from them: nothing counted"
        ACT.set_off(conn, 8, False, NOW)
        conn.execute("UPDATE push_subs SET unopened = ?", (PA.IGNORED_N - 1,))
        PA.send(conn, [dict(msg, id="settled:e")], now_s=NOW + 60, **kw)
        assert conn.execute("SELECT unopened FROM push_subs").fetchone()[0] == PA.IGNORED_N
        st = PA.send(conn, [dict(msg, id="settled:f")], now_s=NOW + 3600, **kw)
        assert st.get("quieted") == 1 and len(sent) == 3, (st, sent)
        st = PA.send(conn, [dict(msg, id="settled:g")], now_s=NOW + 60 + PA.IGNORED_GAP_S + 1, **kw)
        assert st["sent"] == 1 and len(sent) == 4, "a day later it goes"
        ACT.beat(conn, 8, {"s": 5, "n": 1, "a": 1}, NOW + 2 * PA.IGNORED_GAP_S)
        assert conn.execute("SELECT unopened FROM push_subs").fetchone()[0] == 0, "they opened one"
        ACT.set_off(conn, 8, True)
        conn.execute("UPDATE push_subs SET unopened = 99")
        st = PA.send(conn, [dict(msg, id="settled:h")], now_s=NOW + 2 * PA.IGNORED_GAP_S + 60, **kw)
        assert st["sent"] == 1 and "quieted" not in st, "turned off: their phone is not judged on it"


def test_wired_into_the_alerts():
    assert "away" in PA.PERSONAL and PM.TTL_S["away"] == 3 * 3600
    src = READ("engine", "pushmine.py")
    assert "away" in PM.HELD, "held through quiet hours"
    assert "_en.away_pass(conn, Path(web) / \"data\", now=t)" in src
    acct = READ("web", "js", "account.js")
    assert 'pushRemember(await pushOn(PUSH_ASK_TOPICS.concat(away), pushAskLeagues()));' in acct
    assert 'const away = _pwStatus && _pwStatus.activity_switch ? ["away"] : [];' in acct
    for src in (READ("web", "js", "app.js"), acct):
        assert 't === "finals" || t === "lineup" || t === "away"' in src, "a member's own topic"
    log = json.loads(READ("web", "changelog.json"))
    hooks = [e for e in log["entries"] if e.get("alert")]
    assert hooks and all(e["kind"] == "ship" and e["url"].startswith("/") and len(e["alert"]) <= 100 for e in hooks)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
