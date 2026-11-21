"""The site tells its owner when it needs them: on the desk, and on the phone.

Ethan, 2026-11-02: "deep dive and add more features and tools the Qellys book
owners account should have". engine/owneralerts reads the desk's health
section and lists what needs the owner — a board stale on a day its league
plays, grading stopped, the disk filling, a failed update, odds credits
running out, a flood of script errors — and queues each, once an Eastern
day, as an `account` notice to the phones signed in to the verified
Qellys_Book account. These hold:

  * each problem is read off the health section and nothing else is: a
    resting league's old board, a quiet night, a disk with room say nothing;
  * a stale board needs a game today (begun or not) on its league's
    scoreboard;
  * the alerts go to the site account's phones only, once a day each, and
    not at all without a phone or without the account;
  * the desk heads with the same list and says whether a phone will hear it;
  * the minute's push pass runs it.

Run directly: `python3 tests/test_the_site_tells_its_owner.py`
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import accounts as A                                  # noqa: E402
from engine import owneralerts as OA                              # noqa: E402
from engine import pushalerts as PA                               # noqa: E402
from engine import socialfeed as SF                               # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
#: 3pm Eastern on a weekday in November (EST, UTC-5).
T = dt.datetime(2026, 11, 4, 20, 0, tzinfo=dt.timezone.utc).timestamp()
SICK = {"disk": {"free_gb": 3.1, "used_pct": 93.4}, "settled_ago_s": 3 * 3600 + 600,
        "stale": {"nba": 7.0, "mlb": 30.5}, "update": {"ok": False, "note": "git pull: could not resolve host"},
        "odds": {"remaining": 1500, "used": 98500, "days_left": 6, "per_day": 250},
        "crashes": 61, "crash_top": [{"m": "TypeError: x is undefined", "n": 40}]}
WELL = {"disk": {"free_gb": 31.2, "used_pct": 58.0}, "settled_ago_s": 140, "stale": {},
        "update": {"ok": True, "note": "pulled"}, "odds": {"remaining": 41000, "days_left": 28, "per_day": 1460},
        "crashes": 2, "crash_top": []}


def _iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _boards(games: dict) -> Path:
    """A data folder whose live_{league}.json carry these games."""
    d = Path(tempfile.mkdtemp())
    for league, gs in games.items():
        (d / f"live_{league}.json").write_text(json.dumps({"games": gs}))
    return d


def test_each_problem_is_read_off_the_desks_health():
    d = _boards({"nba": [{"event_id": "1", "live": {"state": "pre", "start_time": _iso(T + 4 * 3600)}}],
                 "mlb": []})
    try:
        got = OA.problems(SICK, data_dir=d, now=T)
        assert [p["key"] for p in got] == ["disk", "grading", "board-nba", "update", "odds", "crashes"], got
        said = {p["key"]: p for p in got}
        assert said["disk"]["title"] == "The disk is 93.4% full" and "3.1 GB left" in said["disk"]["body"]
        assert said["grading"]["title"] == "Bets have not been graded in 3.2 hours", said["grading"]
        assert said["board-nba"]["title"] == "The NBA board is 7 hours old"
        assert "could not resolve host" in said["update"]["body"]
        assert said["odds"]["title"] == "1,500 odds credits left" and "6 days" in said["odds"]["body"]
        assert "TypeError: x is undefined" in said["crashes"]["body"]
        assert OA.problems(WELL, data_dir=d, now=T) == [], "all well says nothing"
        assert OA.problems({"error": "x"}, data_dir=d, now=T) == []
        # The month's last day: low credits are the month ending, not a problem.
        assert "odds" not in [p["key"] for p in OA.problems({**WELL, "odds": {"remaining": 900, "days_left": 1}},
                                                            data_dir=d, now=T)]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_a_stale_board_needs_a_game_today():
    tomorrow = _boards({"nba": [{"event_id": "1", "live": {"state": "pre", "start_time": _iso(T + 30 * 3600)}}]})
    under_way = _boards({"nba": [{"event_id": "1", "live": {"state": "in", "start_time": _iso(T - 30 * 3600)}}]})
    try:
        h = {**WELL, "stale": {"nba": 9.0}}
        assert OA.problems(h, data_dir=tomorrow, now=T) == [], "no game today: resting, not late"
        assert [p["key"] for p in OA.problems(h, data_dir=under_way, now=T)] == ["board-nba"]
        assert OA.problems({**WELL, "stale": {"nba": 4.0}}, data_dir=under_way, now=T) == [], "under STALE_H"
        assert OA.problems(h, data_dir=Path(tempfile.gettempdir()) / "no-such-boards", now=T) == []
    finally:
        shutil.rmtree(tomorrow, ignore_errors=True)
        shutil.rmtree(under_way, ignore_errors=True)


def _phone(conn, uid, n):
    PA.ensure_tables(conn)
    conn.execute("INSERT INTO push_subs (endpoint, kind, user_id, topics, leagues, created) VALUES (?,?,?,?,?,?)",
                 (f"https://fcm.googleapis.com/fcm/send/owner-test-{uid}-{n}", "web", uid, "posted,settled", "",
                  "2026-11-01T00:00:00"))
    conn.commit()


def test_the_alerts_reach_the_site_accounts_phones_once_a_day():
    d = Path(tempfile.mkdtemp())
    boards = _boards({"nba": [{"event_id": "1", "live": {"state": "pre", "start_time": _iso(T + 3600)}}]})
    conn = A.connect(str(d / "a.db"))
    try:
        h = {**WELL, "disk": {"free_gb": 2.0, "used_pct": 95.0}, "stale": {"nba": 8.0}}
        assert OA.alerts_pass(conn, now=T, health=h, data_dir=boards) == 0, "no site account: nobody to tell"
        site = int(A.create_user(conn, "siteowner@example.com", "correct horse battery", confirmed=True)[1]["id"])
        assert SF.claim(conn, "siteowner@example.com", "Qellys_Book", name="Qellys Book")[0] == 200
        fan = int(A.create_user(conn, "fan@example.com", "correct horse battery", confirmed=True)[1]["id"])
        _phone(conn, fan, 1)
        assert OA.site_account(conn) == site
        assert OA.alerts_pass(conn, now=T, health=h, data_dir=boards) == 0, "the account has no phone yet"
        _phone(conn, site, 1)
        assert OA.alerts_pass(conn, now=T, health=h, data_dir=boards) == 2
        rows = conn.execute("SELECT user_id, id, kind, title, url FROM push_mine ORDER BY id").fetchall()
        assert {r[0] for r in rows} == {site}, "the site's own phones, nobody else's"
        assert [r[1] for r in rows] == ["owner:board-nba:2026-11-04", "owner:disk:2026-11-04"], [r[1] for r in rows]
        assert {r[2] for r in rows} == {PA.ACCOUNT} and {r[4] for r in rows} == {"/#owner"}
        assert OA.alerts_pass(conn, now=T + 900, health=h, data_dir=boards) == 0, "once a day each"
        assert OA.alerts_pass(conn, now=T + 86400, health=h, data_dir=boards) == 1, \
            "the next day the disk is still full (the board's game was yesterday)"
    finally:
        conn.close()
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(boards, ignore_errors=True)


def test_the_desk_heads_with_what_needs_you():
    node = shutil.which("node")
    if not node:
        return
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      const escapeAttr = escapeHtml;
      const toneOf = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
      const tzTime = () => "3:00 PM";
      const document = { addEventListener() {} };
    """
    sample = {"now": {"members": 1, "visitors": 2, "pages": 3}, "switches": [], "alerts": {"phones": 0},
              "needs": [{"key": "disk", "title": "The disk is 95% full", "body": "2 GB <left>."}]}
    fd, path = tempfile.mkstemp(suffix=".js")
    with os.fdopen(fd, "w") as fh:
        fh.write(stubs + READ("web", "js", "owner.js")
                 + f"\nconst d = {json.dumps(sample)};\nprocess.stdout.write(odHTML(d) + '\\n@@\\n' + "
                   f"odHTML({{...d, needs: [], alerts: {{phones: 2}}}}));")
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    sick, well = out.stdout.split("\n@@\n")
    assert sick.index("Needs you") < sick.index("Members on"), "what needs you heads the page"
    assert "The disk is 95% full" in sick and "2 GB &lt;left&gt;." in sick
    assert "No phone yet" in sick and "turn alerts on" in sick
    assert "Needs you" not in well and "On · 2 phones" in well


def test_the_minutes_push_pass_runs_it():
    pm = READ("engine", "pushmine.py")
    assert '"owner": 0.0' in pm and "_oa.alerts_pass(conn, now=t, data_dir=Path(web) / \"data\")" in pm
    od = READ("engine", "ownerdesk.py")
    assert '"needs": _section(_needs, h, t)' in od and '"alerts": _section(_alerts, conn)' in od


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
