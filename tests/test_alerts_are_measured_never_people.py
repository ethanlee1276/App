"""Alerts are measured as daily totals, never people (engine/analytics
push_sent and the "alert" source; docs/RETENTION.md §5).

What these hold:

  * each alert that reaches a phone adds one to that day's count for its
    kind (a picks-up, a final score...), and nothing at all while analytics
    is switched off;
  * a visit an alert opened is counted under the source "alert": the
    worker and the iOS app mark the address, the page reads the mark before
    anything rewrites it and takes it back off;
  * the report says alerts sent, visits from tapping one and the share, by
    kind, and who came back after day 1, 7 and 30; the privacy policy names
    both counts.

Run directly: `python3 tests/test_alerts_are_measured_never_people.py`
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import analytics as AN                                      # noqa: E402
from engine import pushalerts as PA                                     # noqa: E402

FCM = "https://fcm.googleapis.com/fcm/send/abc123:APA91bHxyz"
READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")         # noqa: E731


def _send(db, on):
    old_env, old_db = os.environ.get(AN.ENV), AN.DB_PATH
    os.environ[AN.ENV] = "1" if on else "0"
    AN.DB_PATH = Path(db)
    try:
        c = sqlite3.connect(":memory:")
        PA.ensure_tables(c)
        PA.subscribe(c, FCM)
        PA.subscribe(c, FCM + "b")
        msgs = [{"id": "posted:nba:d", "kind": "posted", "league": "nba", "label": "NBA", "n": 3,
                 "title": "t", "body": "b", "url": "/"},
                {"id": "settled:d", "kind": "settled", "league": "", "title": "t", "body": "b", "url": "/"}]
        PA.send(c, msgs, knock=lambda e, k, topic="": 201, vapid={"x": 1}, apns_cfg=False, now_s=1.0)
        return AN.report(7, path=db, accounts_path=os.path.join(os.path.dirname(db), "none.db"))
    finally:
        AN.DB_PATH = old_db
        if old_env is None:
            os.environ.pop(AN.ENV, None)
        else:
            os.environ[AN.ENV] = old_env


def test_an_alert_that_reached_a_phone_is_a_count_by_kind():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "analytics.db")
    rep = _send(db, on=True)
    rows = dict(((e, p), n) for e, p, n in sqlite3.connect(db).execute(
        "SELECT event, page, SUM(n) FROM counts GROUP BY event, page"))
    assert rows == {("push_sent", "posted"): 2, ("push_sent", "settled"): 2}, rows
    cols = [r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(counts)")]
    assert cols == ["day", "event", "page", "source", "who", "n"], "no column could name a person"
    assert "alerts sent: 4; visits from tapping one: 0 (0%)" in rep, rep


def test_nothing_is_counted_while_analytics_is_off():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "analytics.db")
    _send(db, on=False)
    assert not os.path.exists(db) or not sqlite3.connect(db).execute("SELECT COUNT(*) FROM counts").fetchone()[0]


def test_a_visit_an_alert_opened_is_counted_as_one():
    assert "alert" in AN.SOURCES and "push_sent" in AN.SERVER_EVENTS
    assert AN.clean("visit", "home", "alert", "member") == ("visit", "home", "alert", "member")
    sw = READ("web", "sw.js")
    at = sw.index('self.addEventListener("notificationclick"')
    assert 'u.searchParams.set("from", "alert");' in sw[at:at + 900]
    app = READ("web", "js", "app.js")
    assert "const _anAlert = /[?&]from=alert(?:&|$)/.test(location.search);" in app
    assert 'q.delete("from");' in app[app.index("const _anAlert"):][:600], "the mark comes back off"
    src = app[app.index("function anSource("):app.index("\n}\n", app.index("function anSource("))]
    assert src.index('if (_anAlert) return "alert";') < src.index("utm_source"), "read first"
    native = app[app.index('PN.addListener("pushNotificationActionPerformed"'):][:500]
    assert 'x.searchParams.set("from", "alert");' in native, "the iPhone app marks it too"


def test_the_report_and_the_policy_say_it():
    rep = AN.report(7, path=os.path.join(tempfile.mkdtemp(), "none.db"),
                    accounts_path=os.path.join(tempfile.mkdtemp(), "none.db"))
    assert "Switched" in rep
    src = READ("engine", "analytics.py")
    assert "for after in (1, 7, 30):" in src, "day 30 too"
    priv = READ("web", "privacy.html")
    assert "or one of our alerts" in priv and "how many alerts reached phones, by kind" in priv


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
