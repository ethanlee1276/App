"""Monday's "Your week" at the hour each member usually looks
(engine/pushmine.week_pass, engine/engagement.usual_hours).

The Privacy Policy's §2.10 says what a member's activity record is for:
"to send the ones not tied to a game at the hour you usually look". Monday's
recap of their week is one of those, and it went to everybody at nine. What
these hold:

  * a member who said yes to keeping their activity, with an hour to read,
    hears it in that hour (the last of Monday's hours when theirs is later);
  * everybody else at nine, as before: no yes, a no, or the site's locks shut;
  * still once a week.

Run directly: `python3 tests/test_your_week_at_your_hour.py`
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("QB_ACTIVITY", None)

from engine import accounts as A                                  # noqa: E402
from engine import activity as ACT                                # noqa: E402
from engine import engagement as EN                               # noqa: E402
from engine import pushalerts as PA                               # noqa: E402
from engine import pushmine as PM                                 # noqa: E402

ET = dt.timezone(dt.timedelta(hours=-5))                          # New York in November
MONDAY = dt.datetime(2026, 11, 2, tzinfo=ET).timestamp()          # Monday 2 November, midnight


def _at(hour, minute=0):
    return MONDAY + hour * 3600 + minute * 60


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


BETS = [{"id": "1", "desc": "Josh Allen Under 259.5", "odds": -110, "stake": 22, "date": "2026-10-27", "result": "win"},
        {"id": "2", "desc": "Henry Over 84.5", "odds": -115, "stake": 20, "date": "2026-10-30", "result": "loss"}]


def _member(conn, n, hour=None, said=None):
    """An account whose phone gets its bets, with last week's bets; with a
    usual hour when ``hour`` is given; ``said`` True/False for a yes or a no
    to keeping their activity."""
    uid = int(A.create_user(conn, f"w{n}@example.com", "correct horse battery", confirmed=True)[1]["id"])
    conn.execute("UPDATE users SET created_at = ? WHERE id = ?", (MONDAY - 60 * 86400, uid))
    A.save_sections(conn, uid, {"mybets": {"ts": 1, "data": {"rows": BETS, "deleted": []}}})
    PA.subscribe(conn, f"https://fcm.googleapis.com/fcm/send/w{n}:APA91bHxyz", topics=["bets"], user_id=uid)
    ACT.ensure_tables(conn)
    if said is not None:
        conn.execute("INSERT INTO activity_prefs (user_id, off, at) VALUES (?, ?, ?)", (uid, 0 if said else 1, MONDAY - 86400 * 50))
    if hour is not None:
        hrs = [0] * 24
        hrs[hour] = 900
        hrs[9] = 60                                                # a little in the morning too
        for d in range(2, 16):
            day = (dt.datetime.fromtimestamp(MONDAY, ET).date() - dt.timedelta(days=d)).isoformat()
            conn.execute("INSERT INTO activity_days (user_id, day, seconds, visits, taps, views, sports, hours) "
                         "VALUES (?, ?, 960, 1, 0, '{}', '{}', ?)", (uid, day, ",".join(map(str, hrs))))
    conn.commit()
    return uid


def _told(conn, uid):
    return conn.execute("SELECT COUNT(*) FROM push_mine WHERE user_id = ? AND id LIKE 'bets:week:%'", (uid,)).fetchone()[0]


def test_each_at_their_hour_and_everybody_else_at_nine():
    conn = A.connect(str(Path(tempfile.mkdtemp()) / "acc.db"))
    try:
        PM.ensure_tables(conn)
        evening = _member(conn, 1, hour=19, said=True)
        late = _member(conn, 2, hour=21, said=True)                # later than Monday's hours
        nobody = _member(conn, 3)                                  # never said
        no = _member(conn, 4, hour=13, said=False)                 # said no: never read
        with _Locks():
            assert EN.usual_hours(conn, [evening, late, nobody, no], _at(9)) == {evening: 19, late: 21}
            assert PM.week_pass(conn, now=_at(8, 59)) == 0, "Monday from nine"
            assert PM.week_pass(conn, now=_at(9)) == 2 and _told(conn, nobody) == 1 and _told(conn, no) == 1
            assert PM.week_pass(conn, now=_at(18, 30)) == 0, "the evening member's hour is not yet"
            assert PM.week_pass(conn, now=_at(19)) == 1 and _told(conn, evening) == 1
            assert PM.week_pass(conn, now=_at(19, 30)) == 0, "once"
            assert PM.week_pass(conn, now=_at(20)) == 1 and _told(conn, late) == 1, "the last of Monday's hours"
            assert PM.week_pass(conn, now=_at(20, 30)) == 0
    finally:
        conn.close()


def test_with_the_locks_shut_it_is_nine_for_everybody():
    conn = A.connect(str(Path(tempfile.mkdtemp()) / "acc.db"))
    try:
        PM.ensure_tables(conn)
        evening = _member(conn, 1, hour=19, said=True)
        assert EN.usual_hours(conn, [evening], _at(9)) == {}, "nothing read while the switch is off"
        assert PM.week_pass(conn, now=_at(9)) == 1 and _told(conn, evening) == 1
    finally:
        conn.close()


def test_the_policy_says_so_already():
    policy = " ".join(ROOT.joinpath("web", "privacy.html").read_text(encoding="utf-8").split())
    assert "to send the ones not tied to a game at the hour you usually look" in policy
    src = ROOT.joinpath("engine", "pushmine.py").read_text(encoding="utf-8")
    assert "usual = EN.usual_hours(conn, users, t)" in src
    assert "if hour is not None and et.hour < min(hour, WEEK_HOURS[1] - 1):" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
