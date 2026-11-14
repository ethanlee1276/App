"""The confirmed-five probe (tools/nbafive_probe.py): read-only, and it reads
both sources' shapes without guessing more than they hold.

Knowing tonight's five outright is the NBA lab's largest gain left (5.5-6.0%
off minutes, 0.9-1.2% off points; docs/NBA_LAB.md). Neither source answers
from the lab, so the box asks (runbook KH).

Run directly: `python3 tests/test_nba_five_probe.py`
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools import nbafive_probe as P                            # noqa: E402

SRC = open(os.path.join(ROOT, "tools", "nbafive_probe.py"), encoding="utf-8").read()


def test_the_scoreboard_gives_each_game_its_id_clubs_and_tip():
    board = {"events": [{"id": "401810001", "date": "2026-11-06T00:30Z",
                         "status": {"type": {"state": "pre"}},
                         "competitions": [{"competitors": [
                             {"homeAway": "home", "team": {"abbreviation": "NY"}},
                             {"homeAway": "away", "team": {"abbreviation": "BOS"}}]}]}]}
    assert P.espn_games(board) == [{"id": "401810001", "away": "BOS", "home": "NY",
                                    "tip": "2026-11-06T00:30Z", "state": "pre"}]
    assert P.espn_games({}) == [] and P.espn_games(None) == []


def test_espn_starters_are_the_flagged_athletes_by_club():
    summary = {"boxscore": {"players": [
        {"team": {"abbreviation": "BOS"}, "statistics": [{"athletes": [
            {"starter": True, "athlete": {"displayName": "Jayson Tatum"}},
            {"starter": False, "athlete": {"displayName": "Sam Hauser"}},
            {"starter": True, "athlete": {"displayName": "Jaylen Brown"}}]}]},
        {"team": {"abbreviation": "NY"}, "statistics": [{"athletes": [
            {"athlete": {"displayName": "Jalen Brunson"}}]}]}]}}
    assert P.espn_starters(summary) == {"BOS": ["Jayson Tatum", "Jaylen Brown"], "NY": []}
    assert P.espn_starters({}) == {} and P.espn_starters({"boxscore": {}}) == {}


def test_the_league_file_is_counted_by_status_without_assuming_more():
    payload = {"games": [{"homeTeam": {"teamAbbreviation": "NYK", "players": [
        {"lineupStatus": "Confirmed", "rosterStatus": "Active", "timestamp": "2026-11-05T23:01:00"},
        {"lineupStatus": "Confirmed", "rosterStatus": "Active", "timestamp": "2026-11-05T23:02:00"},
        {"rosterStatus": "Inactive"}]},
        "awayTeam": {"teamAbbreviation": "BOS", "players": []}}]}
    rows = P.daily_lineups(payload)
    assert rows[0] == {"club": "BOS", "players": 0, "status": {}, "roster": {}, "latest": ""}
    assert rows[1]["club"] == "NYK" and rows[1]["status"] == {"Confirmed": 2, "-": 1}
    assert rows[1]["roster"] == {"Active": 2, "Inactive": 1} and rows[1]["latest"] == "2026-11-05T23:02:00"
    assert P.daily_lineups({}) == [] and P.daily_lineups(None) == []


def test_the_probe_stores_nothing_and_sends_nothing_about_anyone():
    import re
    for word in ("fetch_json", "fetch_text", "db.connect", "sqlite3", ".write(", "write_text"):
        assert word not in SRC, f"the probe must not store anything: {word}"
    assert not re.search(r"(?<![\w.])open\(", SRC), "no file opened: the probe stores nothing"
    assert "User-Agent" not in SRC, "urllib names itself, as the box's ESPN reads do"
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", SRC), "no address of anybody's in a request"


def test_a_dead_source_is_a_line_not_a_crash():
    st, payload, note = P._get("http://127.0.0.1:9/nothing-listens-here")
    assert st is None and payload is None and note


def test_the_runbook_and_the_catch_up_carry_it():
    book = open(os.path.join(ROOT, "docs", "WHEN_YOU_ARE_HOME.md"), encoding="utf-8").read()
    catch = open(os.path.join(ROOT, "tools", "catchup.sh"), encoding="utf-8").read()
    line = "cd /srv/qellys && sudo -u qellys python3 tools/nbafive_probe.py"
    assert "**KH. " in book and line in book
    assert 'run KH "' in catch and line in catch
    nxt = open(os.path.join(ROOT, "docs", "RUN_NEXT.md"), encoding="utf-8").read()
    assert "(step KH)" in nxt


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    if fails:
        print(f"{ran} passed, {fails} failed")
        sys.exit(1)
    print(f"\n{ran} tests passed.")
