"""Lineup alerts: a starter in your lineup who will not play, by push.

Ethan, 2026-10-27: "make sure … the fantasy room is actually a useful tool".
The one mistake every fantasy app guards against is a starter left in who
is out or on a bye (docs/FANTASY.md, item 7). engine/lineupalerts reads the
lineup a member has actually set on Sleeper, against this week's byes and
injury designations, and knocks their phone.

What these hold: who counts as not playing (a bye, Out, IR, suspended,
doubtful; not questionable, not a bench player); the words are the name and
the designation and never a number; one alert a week per news, a new name
is new news; only an account whose phone has "My fantasy lineup" on, and
only the league its own desk opened; turning the switch off forgets the
league; deleting the account deletes it; quiet hours hold it; the switch,
the policy and the runner.

    python3 tests/test_lineup_alerts_by_push.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A          # noqa: E402
from engine import lineupalerts as LA     # noqa: E402
from engine import pushalerts as PA       # noqa: E402
from engine import pushmine as PM         # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
ACCOUNT = open(os.path.join(ROOT, "web", "js", "account.js"), encoding="utf-8").read()
SERVER = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
PRIVACY = open(os.path.join(ROOT, "web", "privacy.html"), encoding="utf-8").read()

PLAYERS = {"10": {"first_name": "Ja'Marr", "last_name": "Chase", "team": "CIN", "injury_status": None},
           "11": {"first_name": "Mark", "last_name": "Andrews", "team": "BAL"},
           "12": {"first_name": "Saquon", "last_name": "Barkley", "team": "PHI", "injury_status": "Questionable"},
           "13": {"first_name": "Breece", "last_name": "Hall", "team": "NYJ"},
           "14": {"first_name": "Tee", "last_name": "Higgins", "team": "CIN", "injury_status": "Out"}}


def _sleeper(starters=("10", "11", "12"), leg=9):
    rosters = [{"roster_id": 1, "owner_id": "555", "starters": list(starters), "players": list(PLAYERS)},
               {"roster_id": 2, "owner_id": "777", "starters": ["14"], "players": ["14"]}]
    data = {"league/321": {"name": "Sunday Funday", "settings": {"leg": leg}},
            "league/321/rosters": rosters, "players/nfl": PLAYERS}
    return lambda path, ttl: data[path]


WEEK = {"week": 9, "byes": ["BAL"], "listed": {"Ja'Marr Chase": {"team": "CIN", "status": "Out"},
                                               "Breece Hall": {"team": "NYJ", "status": "Doubtful"}}}


def _db(d):
    conn = A.connect(Path(d) / "a.db")
    PM.ensure_tables(conn)
    return conn


def _member(conn, email, topics):
    cur = conn.execute("INSERT INTO users (email, verifier, created_at, age_confirmed, terms_accepted_at) "
                       "VALUES (?, 'x', ?, 1, ?)", (email, time.time(), time.time()))
    uid = int(cur.lastrowid)
    conn.execute("INSERT INTO push_subs (endpoint, kind, user_id, topics, created) VALUES (?, 'web', ?, ?, '2026-10-27')",
                 (f"https://push.example/{uid}", uid, topics))
    conn.commit()
    return uid


def _queued(conn):
    return conn.execute("SELECT user_id, kind, title, body FROM push_mine ORDER BY user_id, at").fetchall()


# --- who will not play ---------------------------------------------------------------------

def test_a_bye_out_ir_and_doubtful_count_and_questionable_does_not():
    starters = [{"player": "Ja'Marr Chase", "team": "CIN"}, {"player": "Mark Andrews", "team": "BAL"},
                {"player": "Saquon Barkley", "team": "PHI", "status": "Questionable"},
                {"player": "Breece Hall", "team": "NYJ"}, {"player": "Rico Dowdle", "team": "CAR", "status": "IR"},
                {"player": "Nobody", "team": "DAL", "status": "Suspended"}]
    got = LA.starters_out(starters, byes={"BAL"}, listed=WEEK["listed"])
    assert got == [("Ja'Marr Chase", "out"), ("Mark Andrews", "on a bye"), ("Breece Hall", "doubtful"),
                   ("Rico Dowdle", "on IR"), ("Nobody", "suspended")]


def test_the_week_s_designation_wins_over_sleeper_s():
    assert LA.why_not("chase", "CIN", listed={"chase": {"status": "Questionable"}}, sleeper_status="Out") is None
    assert LA.why_not("chase", "CIN", listed={}, sleeper_status="Out") == "out"


def test_the_words_are_names_and_designations_never_a_number():
    title, body = LA.message("Sunday Funday", [("Ja'Marr Chase", "out")])
    assert title == "Ja'Marr Chase is out"
    assert body == "Still in your Sunday Funday lineup. Tap to see who to start instead."
    title, body = LA.message("", [("Philadelphia Eagles", "on a bye")])
    assert (title, body) == ("Philadelphia Eagles is on a bye", "Still in your lineup. Tap to see who to start instead.")
    title, body = LA.message("", [("Ja'Marr Chase", "out"), ("Mark Andrews", "on a bye"), ("Breece Hall", "doubtful")])
    assert title == "3 of your starters won’t play"
    assert body.startswith("Ja'Marr Chase (out), Mark Andrews (on a bye) and Breece Hall (doubtful) are in your lineup.")
    assert not any(ch.isdigit() for ch in body), "no points, no projection"


# --- the pass ------------------------------------------------------------------------------

def test_only_the_switch_and_only_the_league_its_desk_opened():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        on = _member(conn, "on@example.com", "posted,lineup")
        off = _member(conn, "off@example.com", "posted,finals")
        assert PM.lineup_remember(conn, on, "321", "555")
        assert not PM.lineup_remember(conn, off, "321", "555"), "no switch, no league kept"
        assert not PM.lineup_remember(conn, on, "321; DROP", "555"), "a league id is digits"
        assert LA.lineup_pass(conn, now=1000.0, grab=_sleeper(), week_doc=WEEK) == 1
        rows = _queued(conn)
        assert [(r[0], r[1]) for r in rows] == [(on, "lineup")]
        assert rows[0][2] == "2 of your starters won’t play"
        assert rows[0][3].startswith("Ja'Marr Chase (out) and Mark Andrews (on a bye) are in your Sunday Funday lineup.")
        assert LA.lineup_pass(conn, now=2000.0, grab=_sleeper(), week_doc=WEEK) == 0, "the same news once"
        assert LA.lineup_pass(conn, now=3000.0, grab=_sleeper(starters=("10", "11", "13")), week_doc=WEEK) == 1, \
            "a new name in the lineup is new news"
        assert LA.lineup_pass(conn, now=4000.0, grab=_sleeper(starters=("12", "13")),
                              week_doc=dict(WEEK, listed={})) == 0, "a fixed lineup is quiet"
        conn.close()


def test_a_stale_week_file_lends_neither_its_byes_nor_its_list():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _member(conn, "on@example.com", "lineup")
        PM.lineup_remember(conn, uid, "321", "555")
        stale = dict(WEEK, week=8)
        assert LA.lineup_pass(conn, now=1000.0, grab=_sleeper(starters=("10", "11")), week_doc=stale) == 0, \
            "Chase's Out and Baltimore's bye were last week's"
        assert LA.lineup_pass(conn, now=1000.0, grab=_sleeper(starters=("10", "11", "12")), week_doc={}) == 0
        assert LA.lineup_pass(conn, now=1000.0, grab=_sleeper(starters=("10", "14")), week_doc=stale) == 1, \
            "Sleeper's own Out is this week's whatever the file says"
        assert _queued(conn)[0][2] == "Tee Higgins is out"
        conn.close()


def test_turning_it_off_forgets_the_league_and_deleting_the_account_too():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _member(conn, "on@example.com", "lineup")
        PM.lineup_remember(conn, uid, "321", "555")
        conn.execute("UPDATE push_subs SET topics = 'posted' WHERE user_id = ?", (uid,))
        conn.commit()
        LA.lineup_pass(conn, now=1000.0, grab=_sleeper(), week_doc=WEEK)
        assert conn.execute("SELECT COUNT(*) FROM push_lineup_leagues").fetchone()[0] == 0
        conn.execute("UPDATE push_subs SET topics = 'lineup' WHERE user_id = ?", (uid,))
        conn.commit()
        PM.lineup_remember(conn, uid, "321", "555")
        A.delete_user(conn, uid)
        assert conn.execute("SELECT COUNT(*) FROM push_lineup_leagues").fetchone()[0] == 0
        conn.close()


def test_the_minute_forgets_even_when_no_phone_is_left():
    """The last phone of the last signed-in account goes: the minute's pass
    stops early (nothing to send), and the league is still forgotten."""
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _member(conn, "on@example.com", "lineup")
        PM.lineup_remember(conn, uid, "321", "555")
        conn.execute("DELETE FROM push_subs")
        conn.commit()
        PM.run_once(connect=lambda: A.connect(Path(d) / "a.db"), log=lambda *a: None)
        assert conn.execute("SELECT COUNT(*) FROM push_lineup_leagues").fetchone()[0] == 0
        conn.close()


def test_one_read_of_the_players_file_a_pass():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        for i in range(3):
            uid = _member(conn, f"on{i}@example.com", "lineup")
            PM.lineup_remember(conn, uid, "321", "555")
        seen = []
        inner = _sleeper()

        def counting(path, ttl):
            seen.append(path)
            return inner(path, ttl)
        assert LA.lineup_pass(conn, now=1000.0, grab=counting, week_doc=WEEK) == 3
        assert seen.count("players/nfl") == 1 and seen.count("league/321/rosters") == 1, seen
        conn.close()


def test_sleeper_down_is_the_next_pass_s_problem():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _member(conn, "on@example.com", "lineup")
        PM.lineup_remember(conn, uid, "321", "555")

        def down(path, ttl):
            raise OSError("no route")
        assert LA.lineup_pass(conn, now=1000.0, grab=down, week_doc=WEEK) == 0
        conn.close()


def test_quiet_hours_hold_it():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        uid = _member(conn, "on@example.com", "lineup")
        PM.lineup_remember(conn, uid, "321", "555")
        LA.lineup_pass(conn, now=time.time(), grab=_sleeper(), week_doc=WEEK)
        sent = []
        stats = PM.flush(conn, knock=lambda *a, **k: sent.append(a) or 201, vapid={"x": 1}, quiet=True)
        assert stats["messages"] == 0 and not sent, "held until the morning"
        assert PM.TTL_S["lineup"] >= 12 * 3600, "and still worth sending then"
        conn.close()


# --- the switch, the desk, the policy, the runner ------------------------------------------

def test_the_switch_the_desk_the_policy_and_the_runner():
    assert "lineup" in PA.PERSONAL
    assert 'box("lineup", "My fantasy lineup: a starter out or on a bye", !signedIn),' in APP
    assert 't === "finals" || t === "lineup"' in APP and 't === "finals" || t === "lineup"' in ACCOUNT
    desk = SERVER[SERVER.index("    def _league_desk(self, query: dict):"):SERVER.index("    def _league_desk_espn(")]
    assert "self._remember_lineup_league(league_id, user_id)" in desk
    assert "pushmine.lineup_remember(aconn, who[\"id\"], league_id, sleeper_user)" in SERVER
    assert "push_lineup_leagues" in PRIVACY and "a starter in your fantasy lineup is out, on a bye" in PRIVACY
    assert "delete them within fifteen minutes of your turning it off" in PRIVACY
    pm = open(os.path.join(ROOT, "engine", "pushmine.py"), encoding="utf-8").read()
    assert "told += _la.lineup_pass(conn, now=t)" in pm and "'watches', 'clutch', 'lineup'" in pm


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {fn.__name__}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(fns) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
