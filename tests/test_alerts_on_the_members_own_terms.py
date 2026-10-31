"""Alerts on the member's own terms (engine/pushalerts DAY_CAP, pause,
quiet_for; engine/pushmine.flush; the Alerts page's Take a break).

Ethan's research, 2026-10-29: "a hard cap of 5 pushes a day for free users
and 8 for paid ... quiet hours from midnight to 8 AM local ... a one-tap
'pause alerts for 24h/7d'", and from its legal section, "add self-limits on
alerts, a 'quiet mode,' and links to self-exclusion resources." What these
hold:

  * a phone paused for a day or a week hears nothing from either sender
    until it runs out; on again at once; only a day or a week;
  * a phone hears at most DAY_CAP alerts an Eastern day (five, eight on a
    plan), every kind counted, the count starting again the next day;
  * the alerts held at night are held in the member's own zone (their
    Settings' time zone, Eastern when they named none);
  * the page offers the pause, says the limits and the helpline; the
    research's events are counted as totals where they happen.

Run directly: `python3 tests/test_alerts_on_the_members_own_terms.py`
"""
import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import analytics as AN                                # noqa: E402
from engine import pushalerts as PA                               # noqa: E402
from engine import pushmine as PM                                 # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
NOW = 1_793_304_000.0                                             # 2026-10-29 16:00 Eastern
FCM = "https://fcm.googleapis.com/fcm/send/abc123:APA91bHxyz"


def _et(day=0, hour=16):
    from zoneinfo import ZoneInfo
    d = dt.date(2026, 10, 29) + dt.timedelta(days=day)
    return dt.datetime(d.year, d.month, d.day, hour, tzinfo=ZoneInfo("America/New_York")).timestamp()


def _conn(uid=4, tz=None, paid=False):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE user_data (user_id INTEGER, section TEXT, ts INTEGER, payload TEXT)")
    if tz:
        c.execute("INSERT INTO user_data VALUES (?, 'settings', 1, ?)", (uid, json.dumps({"tz": tz})))
    if paid:
        c.execute("CREATE TABLE subscriptions (user_id INTEGER PRIMARY KEY, status TEXT)")
        c.execute("INSERT INTO subscriptions VALUES (?, 'active')", (uid,))
    PM.ensure_tables(c)
    PA.subscribe(c, "ab" * 32, kind="apns", user_id=uid, topics=["settled", "clutch", "bets"])
    return c


def _settled(i):
    return {"id": f"settled:{i}", "kind": "settled", "league": "", "title": "t", "body": "b", "url": "/"}


def _send(c, i, t):
    got = []
    st = PA.send(c, [_settled(i)], apns=lambda e, m, cfg: got.append(m) or 200, apns_cfg={"x": 1}, vapid={"x": 1},
                 now_s=t)
    return got, st


def test_a_paused_phone_hears_nothing_until_it_runs_out():
    c = _conn()
    assert PA.pause(c, "nope", 24, NOW)[0] == 404
    assert PA.pause(c, "ab" * 32, 5, NOW)[0] == 400, "a day or a week, nothing else"
    code, out = PA.pause(c, "ab" * 32, 24, NOW)
    assert code == 200 and out["paused_until"] == NOW + 86400
    got, st = _send(c, 1, NOW + 60)
    assert not got and st["paused"] == 1
    PM.tell(c, 4, "clutch:x", "clutch", "A big moment", "b", "/", now=NOW + 60)
    sent = []
    PM.flush(c, apns=lambda e, m, cfg: sent.append(m) or 200, apns_cfg={"x": 1}, vapid={"x": 1}, now=NOW + 120,
             quiet=False)
    assert not sent, "the member's own alerts wait too"
    got, _ = _send(c, 2, NOW + 86400 + 1)
    assert len(got) == 1, "a day later it is over"
    PA.pause(c, "ab" * 32, 168, NOW)
    PA.pause(c, "ab" * 32, 0, NOW)
    assert len(_send(c, 3, NOW + 200)[0]) == 1, "on again at once"


def test_five_a_day_eight_on_a_plan_and_tomorrow_again():
    c = _conn()
    n = sum(len(_send(c, i, _et(0, 10) + i * 60)[0]) for i in range(8))
    assert n == PA.DAY_CAP["free"] == 5
    _, st = _send(c, 99, _et(0, 11))
    assert st["day_capped"] == 1
    assert len(_send(c, 100, _et(1, 10))[0]) == 1, "an Eastern day: the next one starts again"
    p = _conn(paid=True)
    assert sum(len(_send(p, i, _et(0, 10) + i * 60)[0]) for i in range(12)) == PA.DAY_CAP["paid"] == 8
    # The member's own alerts count against the same day.
    q = _conn()
    for i in range(4):
        _send(q, i, _et(0, 10) + i)
    for i in range(3):
        PM.tell(q, 4, f"bets:{i}", "bets", f"Your bet {i}", "b", "/", now=_et(0, 12))
    sent = []
    PM.flush(q, apns=lambda e, m, cfg: sent.append(m) or 200, apns_cfg={"x": 1}, vapid={"x": 1}, now=_et(0, 12),
             quiet=False)
    assert len(sent) == 1, "four shared, then one of theirs: five"


def test_quiet_hours_are_where_the_member_is():
    west = _conn(tz="America/Los_Angeles")
    east = _conn(uid=4)
    one_am_et = _et(0, 1) + 86400                                    # 01:00 Eastern = 22:00 Pacific
    assert PA.quiet_for(east, 4, one_am_et) and not PA.quiet_for(west, 4, one_am_et)
    nine_thirty_et = _et(1, 9) + 1800                                # 09:30 Eastern = 06:30 Pacific
    assert not PA.quiet_for(east, 4, nine_thirty_et) and PA.quiet_for(west, 4, nine_thirty_et)
    for c, t, want in ((west, one_am_et, 1), (east, one_am_et, 0)):
        PM.tell(c, 4, f"clutch:{want}", "clutch", "A big moment", "b", "/", now=t)
        sent = []
        PM.flush(c, apns=lambda e, m, cfg: sent.append(m) or 200, apns_cfg={"x": 1}, vapid={"x": 1}, now=t)
        assert len(sent) == want, (want, sent)
    # Their own bet is never held.
    PM.tell(east, 4, "bets:x", "bets", "Your bet is on", "b", "/", now=one_am_et)
    sent = []
    PM.flush(east, apns=lambda e, m, cfg: sent.append(m) or 200, apns_cfg={"x": 1}, vapid={"x": 1}, now=one_am_et)
    assert [m["kind"] for m in sent] == ["bets"]


def test_the_page_offers_the_break_and_says_the_limits():
    more = READ("web", "js", "more.js")              # the Alerts page loads on first use
    zone = more[more.index("function renderPushZone("):more.index("function renderAlerts(")]
    assert 'data-push-pause="24"' in zone and 'data-push-pause="168"' in zone and 'data-push-pause="0"' in zone
    assert "Five alerts a day at most (eight on a plan), none overnight where you are." in zone
    assert "1-800-GAMBLER" in zone
    srv = READ("server.py")
    at = srv.index("def _push_post(self, path: str):")
    assert '"pause"' in srv[at:at + 900] and "PA.pause(conn, endpoint, body.get(\"hours\"))" in srv[at:]


def test_a_break_survives_a_change_of_switches():
    """The review of 2026-10-29: turning a switch on while paused rewrote the
    phone's memory without its pause, so the page said "active" while the
    box was still holding everything. Run under Node with a stand-in
    localStorage."""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        print("      (skipped: no node)")
        return
    app = READ("web", "js", "app.js")
    fn = lambda name: app[app.index(f"function {name}("):app.index("\n}\n", app.index(f"function {name}(")) + 2]  # noqa: E731
    js = "\n".join([
        "const store = {}; const localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); } };",
        'const PUSH_KEY = "qb_push";', fn("pushSaved"), fn("pushRemember"),
        'localStorage.setItem(PUSH_KEY, JSON.stringify({ topics: ["posted"], paused_until: 1900000000 }));',
        'pushRemember({ endpoint: "e", topics: ["posted", "news"] });',
        "const a = JSON.parse(localStorage.getItem(PUSH_KEY));",
        'pushRemember({ endpoint: "e", topics: ["posted"], paused_until: 0 });',
        "const b = JSON.parse(localStorage.getItem(PUSH_KEY));",
        "console.log(JSON.stringify([a.paused_until, a.mine, b.paused_until]));"])
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    assert json.loads(out.stdout) == [1900000000, ["news"], 0], (out.stdout, out.stderr)


def test_the_research_s_events_are_counted_where_they_happen():
    from _app import app_js
    every = app_js() + READ("web", "js", "slip.js")
    for e in ("signup", "bet_logged", "game_view", "push_prompt", "push_on", "installed", "kelly", "billing_portal",
              "discord", "sweat"):
        assert e in AN.CLIENT_EVENTS, e
    for hook in ('track("bet_logged", "hand");', 'track("bet_logged", "ask");', 'window.track("bet_logged", "slip");',
                 'track("signup", "email");', 'track("push_on", "ask");', 'track("push_on", "alerts");',
                 'track("installed", "web");', 'track("installed", "home-screen");', 'track("kelly", state.view);',
                 'track("billing_portal", _anFrom);', 'data-an="discord"', 'track("game_view", league);'):
        assert hook in every, hook
    old_env, old_db = os.environ.get(AN.ENV), AN.DB_PATH
    import tempfile
    AN.DB_PATH = Path(tempfile.mkdtemp()) / "a.db"
    os.environ[AN.ENV] = "1"
    try:
        AN.record("bet_logged", "slip")
        AN.record("bet_logged", "hand")
        AN.record("push_on", "ask")
        rep = AN.report(7, accounts_path=Path(tempfile.mkdtemp()) / "none.db")
    finally:
        AN.DB_PATH = old_db
        if old_env is None:
            os.environ.pop(AN.ENV, None)
        else:
            os.environ[AN.ENV] = old_env
    assert "what readers did (the research's events):" in rep and "bet_logged" in rep and "slip 1" in rep, rep


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
