"""Final scores by push: a followed team's game ends, the phone says how.

The ideas list (2026-10-25, item 6, "recap by push"; engine/finals). What
these hold:

  - the alert is the game page's "game in 30 seconds" on a lock screen:
    the final, the play of the game, the best line — and the best line is
    the page's own (js/detail.js recapTop), word for word;
  - it goes once a game, only while the final is fresh, only to accounts
    following a side or a player in the box, only on the new "finals"
    switch;
  - the switch is on the Alerts page and named in the Privacy policy.

    python3 tests/test_final_scores_by_push.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A          # noqa: E402
from engine import alerts as AL           # noqa: E402
from engine import finals as FN           # noqa: E402
from engine import pushalerts as PA       # noqa: E402

DETAIL = open(os.path.join(ROOT, "web", "js", "detail.js"), encoding="utf-8").read()
from _app import app_js  # noqa: E402  (app.js and the rooms: the Alerts page is js/more.js)
APP = app_js()
ACCOUNT = open(os.path.join(ROOT, "web", "js", "account.js"), encoding="utf-8").read()


def _nfl(state="final"):
    plays = [{"id": "1", "period": 2, "clock": "4:10", "event": "Rush", "players": ["Chase Brown"], "rating": 2.2},
             {"id": "2", "period": 4, "clock": "2:01", "event": "Passing Touchdown", "players": ["Joe Burrow"],
              "rating": 8.7, "swing": "go_ahead"}]
    return {"league": "nfl", "event_id": "990555", "home": "CIN", "away": "PIT", "plays": plays,
            "live": {"state": state, "home_score": 24, "away_score": 21},
            "players": [{"player": "Joe Burrow", "team": "CIN", "stats": {"pass_yds": 312.0, "pass_td": 2.0}},
                        {"player": "Ja'Marr Chase", "team": "CIN", "stats": {"rec_yds": 131.0, "rec_td": 1.0}},
                        {"player": "Najee Harris", "team": "PIT", "stats": {"rush_yds": 88.0}}]}


def _mlb():
    return {"league": "mlb", "event_id": "776655", "home": "NYY", "away": "BOS", "events": [],
            "live": {"state": "final", "home_score": 5, "away_score": 3},
            "players": [{"player": "Aaron Judge", "team": "NYY", "line": {"batting": {"h": 2, "ab": 4, "hr": 1, "rbi": 3}}},
                        {"player": "Gerrit Cole", "team": "NYY", "line": {"pitching": {"ip": "6.2", "k": 9}}}]}


def _js_top(doc):
    i = DETAIL.index("function recapTop(")
    fn = DETAIL[i:DETAIL.index("\n}\n", i) + 3]
    js = f"{fn}\nconsole.log(JSON.stringify(recapTop({json.dumps(doc)}, {json.dumps(doc['league'])})));"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_alert_is_the_pages_recap():
    title, body = FN.message(_nfl())
    assert title == "Final: PIT 21–24 CIN"
    assert body == ("Play of the game: Joe Burrow — Passing Touchdown, Q4, 2:01 (8.7). "
                    "Best line: Joe Burrow (CIN): 312 pass yds, 2 TD.")
    assert FN.message(dict(_nfl(), live={"state": "final"})) is None, "no score, no alert"


def test_the_best_line_is_the_pages_own_word_for_word():
    nhl = {"league": "nhl", "players": [{"player": "Igor Shesterkin", "team": "NYR", "stats": {"saves": 38.0}},
                                         {"player": "Artemi Panarin", "team": "NYR", "stats": {"goals": 1.0, "assists": 1.0}}]}
    nba = {"league": "nba", "players": [{"player": "Jalen Brunson", "team": "NYK", "stats": {"pts": 38.0, "reb": 4.0, "ast": 9.0}}]}
    for doc in (_nfl(), _mlb(), nhl, nba):
        assert FN.best_line(doc) == _js_top(doc), doc["league"]
    assert FN.best_line({"league": "nfl", "players": []}) == ""


def _db(d):
    conn = A.connect(Path(d) / "a.db")
    FN.ensure_tables(conn)
    FN._mtimes.clear()
    return conn


def _member(conn, email, topics, watch=None):
    cur = conn.execute("INSERT INTO users (email, verifier, created_at, age_confirmed, terms_accepted_at) "
                       "VALUES (?, 'x', ?, 1, ?)", (email, time.time(), time.time()))
    uid = int(cur.lastrowid)
    conn.execute("INSERT INTO push_subs (endpoint, kind, user_id, topics, created) VALUES (?, 'web', ?, ?, '2026-10-26')",
                 (f"https://push.example/{uid}", uid, topics))
    conn.commit()
    if watch:
        code, out = AL.add_watch(conn, uid, *watch)
        assert code == 200, out
    return uid


def _write(d, doc, age=0.0):
    path = Path(d) / f"{doc['league']}_{doc['event_id']}.json"
    path.write_text(json.dumps(doc))
    t = time.time() - age
    os.utime(path, (t, t))
    return path


def _queued(conn):
    return conn.execute("SELECT user_id, id, kind, title FROM push_mine ORDER BY user_id").fetchall()


def test_once_a_game_to_followers_on_the_switch():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        fan = _member(conn, "fan@example.com", "finals", ("team", "CIN"))
        player = _member(conn, "chase@example.com", "finals,clutch", ("player", "Ja'Marr Chase"))
        _member(conn, "other@example.com", "finals", ("team", "DAL"))
        _member(conn, "clutchonly@example.com", "clutch", ("team", "PIT"))
        _write(d, _nfl("live"))
        assert FN.finals_pass(conn, Path(d)) == 0, "not final yet"
        _write(d, _nfl())
        assert FN.finals_pass(conn, Path(d)) == 2
        rows = _queued(conn)
        assert [(r[0], r[1], r[2]) for r in rows] == [(fan, "final:nfl_990555", "finals"),
                                                       (player, "final:nfl_990555", "finals")]
        assert rows[0][3] == "Final: PIT 21–24 CIN"
        _write(d, _nfl(), age=-5)        # the file written again
        assert FN.finals_pass(conn, Path(d)) == 0 and len(_queued(conn)) == 2, "once a game"
        conn.close()


def test_a_stale_final_is_not_news():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        _member(conn, "fan@example.com", "finals", ("team", "CIN"))
        _write(d, _nfl(), age=FN.FRESH_S + 60)
        assert FN.finals_pass(conn, Path(d)) == 0 and not _queued(conn)
        conn.close()


def test_the_switch_the_runner_and_the_policy():
    assert "finals" in PA.PERSONAL
    assert 'box("finals", "Final scores of games I follow", !signedIn),' in APP
    assert 't === "clutch" || t === "finals"' in APP and 't === "clutch" || t === "finals"' in ACCOUNT
    pm = open(os.path.join(ROOT, "engine", "pushmine.py"), encoding="utf-8").read()
    assert "moments += _fin.finals_pass(conn, Path(web) / \"data\" / \"pbp\", now=t)" in pm
    priv = open(os.path.join(ROOT, "web", "privacy.html"), encoding="utf-8").read()
    assert "that game's final score with its play of the game and" in priv and "push_final_seen" in priv


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
