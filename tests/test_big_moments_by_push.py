"""Big moments by push: a walk-off, a go-ahead score late, any play rated
8.5 or more, in a game of a team you follow or by a player you follow —
the score and who did it, a tap into the game (engine/pushmine.clutch_pass).

Ethan, 2026-10-25: "create things I've never even thought of." What these
hold:

  - the first look at a game is its baseline: what was already on it is
    never sent (a restart in the fourth quarter does not replay the game);
  - a new moment goes to the accounts following a side in it or a player
    on it, and to nobody else, once;
  - a game sends one account at most CLUTCH_PER_GAME moments;
  - a stale file (no game in progress) is not read;
  - quiet hours hold a moment, and its twenty minutes run out first;
  - the phone's switch, the topic and the privacy page.

Every test runs on a throwaway accounts database; nothing is sent.

    python3 tests/test_big_moments_by_push.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_DIR = tempfile.mkdtemp()
os.environ["QB_ACCOUNTS_DB"] = os.path.join(_DIR, "accounts.db")

from engine import accounts as A                                  # noqa: E402
from engine import alerts as AL                                   # noqa: E402
from engine import pushalerts as PA                               # noqa: E402
from engine import pushmine as PM                                 # noqa: E402

NOW = 1_760_000_000.0
_n = [0]


def _member(*watches, topics=("clutch",)):
    _n[0] += 1
    conn = A.connect()
    PM.ensure_tables(conn)
    code, out = A.create_user(conn, f"c{_n[0]}@example.com", "correct horse battery", confirmed=True)
    assert code == 200, out
    PA.subscribe(conn, f"https://fcm.googleapis.com/fcm/send/clutch{_n[0]}:APA91bHxyz",
                 topics=list(topics), user_id=out["id"])
    for kind, value in watches:
        AL.add_watch(conn, out["id"], kind, value)
    conn.close()
    return out["id"]


def _queued(uid):
    conn = A.connect()
    try:
        return [r[0] for r in conn.execute("SELECT id FROM push_mine WHERE user_id = ? AND kind = 'clutch' "
                                           "ORDER BY at", (uid,))]
    finally:
        conn.close()


def _write(d, name, doc, mtime=NOW):
    p = Path(d) / name
    p.write_text(json.dumps(doc))
    os.utime(p, (mtime, mtime))
    return p


def _mlb(events):
    return {"league": "mlb", "event_id": "777", "home": "NYM", "away": "ATL", "events": events}


AB = lambda n, **kw: dict({"kind": "atbat", "at_bat": n, "inning": 9, "half": "B", "batter": "Pete Alonso",  # noqa: E731
                           "pitcher": "Raisel Iglesias", "event": "Home Run", "away_score": 4, "home_score": 5}, **kw)


def test_the_moment_reads_like_the_scoreboard():
    title, body = PM.clutch_line(_mlb([]), AB(70, swing="walkoff", rating=9.8))
    assert title == "Walk-off: ATL 4–5 NYM", title
    assert body == "Pete Alonso — Home Run, bottom of the 9th. Rated 9.8.", body
    doc = {"league": "nfl", "home": "CIN", "away": "PIT"}
    t2, b2 = PM.clutch_line(doc, {"period": 4, "clock": "0:41", "event": "Passing Touchdown",
                                  "players": ["Joe Burrow", "Ja'Marr Chase"], "swing": "go_ahead",
                                  "rating": 8.9, "away_score": 20, "home_score": 24})
    assert t2 == "Go-ahead: PIT 20–24 CIN" and b2 == "Joe Burrow — Passing Touchdown, Q4, 0:41. Rated 8.9."
    assert PM._ordinal(1) == "1st" and PM._ordinal(11) == "11th" and PM._ordinal(22) == "22nd"


def test_only_big_plays_count_and_a_walk_off_always_does():
    got = PM.clutch_plays(_mlb([AB(1, rating=3.0), AB(2, rating=8.6), AB(3, swing="walkoff", rating=None),
                                {"kind": "pitch", "rating": 9.9}]))
    assert [k for k, _ in got] == ["ab2", "ab3"]


def test_the_first_look_is_the_baseline_then_followers_hear_once():
    fan = _member(("team", "NYM"))
    player_fan = _member(("player", "pete alonso"))
    other = _member(("team", "LAD"))
    no_topic = _member(("team", "NYM"), topics=("watches",))
    with tempfile.TemporaryDirectory() as d:
        conn = A.connect()
        try:
            _write(d, "mlb_777.json", _mlb([AB(40, inning=6, rating=8.7)]))
            assert PM.clutch_pass(conn, d, now=NOW + 5) == 0, "the moments already on it are the baseline"
            _write(d, "mlb_777.json", _mlb([AB(40, inning=6, rating=8.7), AB(70, swing="walkoff", rating=9.8)]),
                   mtime=NOW + 30)
            assert PM.clutch_pass(conn, d, now=NOW + 40) == 2
            assert _queued(fan) == ["clutch:mlb_777:ab70"] and _queued(player_fan) == ["clutch:mlb_777:ab70"]
            assert _queued(other) == [] and _queued(no_topic) == []
            _write(d, "mlb_777.json", _mlb([AB(40, inning=6, rating=8.7), AB(70, swing="walkoff", rating=9.8)]),
                   mtime=NOW + 60)
            assert PM.clutch_pass(conn, d, now=NOW + 70) == 0, "once"
        finally:
            conn.close()


def test_a_wild_game_is_capped_and_a_stale_file_is_not_read():
    fan = _member(("team", "KC"))
    with tempfile.TemporaryDirectory() as d:
        conn = A.connect()
        try:
            plays = lambda n: [{"id": str(i), "period": 4, "clock": "1:00", "event": "Touchdown", "rating": 9.0,  # noqa: E731
                                "away_score": i, "home_score": 0} for i in range(n)]
            doc = lambda n: {"league": "nfl", "event_id": "55", "home": "KC", "away": "BUF", "plays": plays(n)}  # noqa: E731
            _write(d, "nfl_55.json", doc(0))
            PM.clutch_pass(conn, d, now=NOW + 1)
            _write(d, "nfl_55.json", doc(9), mtime=NOW + 20)
            PM.clutch_pass(conn, d, now=NOW + 25)
            assert len(_queued(fan)) == PM.CLUTCH_PER_GAME
            _write(d, "nfl_66.json", dict(doc(3), event_id="66"), mtime=NOW - PM.CLUTCH_FRESH_S - 60)
            PM.clutch_pass(conn, d, now=NOW + 30)
            conn2 = A.connect()
            assert conn2.execute("SELECT COUNT(*) FROM push_clutch_seen WHERE game = 'nfl_66'").fetchone()[0] == 0
            conn2.close()
        finally:
            conn.close()


def test_quiet_hours_hold_a_moment_until_it_runs_out():
    uid = _member(("team", "SEA"))
    conn = A.connect()
    try:
        PM.flush(conn, knock=lambda *a, **k: 201, apns=lambda *a: 200, vapid={"d": 1}, apns_cfg={}, now=NOW,
                 quiet=False)                                       # the earlier tests' queue, sent
        assert PM.tell(conn, uid, "clutch:x:1", "clutch", "Walk-off", "b", "/#pbp/mlb/1", now=NOW)
        knocks = []
        knock = lambda ep, k, topic="": knocks.append(topic) or 201        # noqa: E731
        assert PM.flush(conn, knock=knock, vapid={"d": 1}, apns_cfg={}, now=NOW + 1, quiet=True)["messages"] == 0
        PM.flush(conn, knock=knock, vapid={"d": 1}, apns_cfg={}, now=NOW + PM.TTL_S["clutch"] + 5, quiet=False)
        assert knocks == [], "a moment from the night is dropped, not sent in the morning"
    finally:
        conn.close()


def test_the_switch_the_topic_and_the_privacy_page():
    assert "clutch" in PA.PERSONAL and PM.TOPICS == PA.PERSONAL
    from _app import app_js                    # the Alerts page loads on first use (js/more.js)
    app = app_js()
    assert 'box("clutch", "Big moments in games I follow", !signedIn)' in app
    assert '|| t === "clutch"' in app
    src = (ROOT / "engine" / "pushmine.py").read_text()
    run = src[src.index("def run_once("):src.index("def main(")]
    assert run.index("clutch_pass(conn") < run.index("flush(conn"), "told before the minute's send"
    priv = (ROOT / "web" / "privacy.html").read_text()
    assert "push_clutch_seen" in priv and "big\n      moment in a game of a team or player you follow" in priv


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
