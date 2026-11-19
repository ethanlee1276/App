"""College basketball players show their real positions (2026-11-19).

Ethan, asked whether college players should show their real positions: "I would
assume so. Yeah."

The college basketball roster page and the player search were built from
appearances: a school's roster was whoever had played, and every position was
the box score's starter or bench mark, so the search called both Boozers "S"
(the live file: 7,889 players, not one with a position). rosters_build now reads
each Division I school's published roster from ESPN (guard, forward, center,
number, height), by the ids the scoreboards taught us, one request a school on a
day's cache and at most CBB_ROSTER_NEW new ones a build; a school not read yet
keeps its appearance rows, and the page says how many.

    python3 tests/test_college_players_show_their_real_positions.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import rosters_build as RB                                        # noqa: E402
from engine import statlogs                                       # noqa: E402
from engine.db import connect                                     # noqa: E402
from engine.sources import fetch as F                             # noqa: E402

DUKE = [{"fullName": "Cayden Boozer", "position": {"abbreviation": "G"}, "jersey": "2",
         "displayHeight": "6' 4\"", "headshot": {"href": "https://a.espncdn.com/x/5041937.png"}},
        {"fullName": "Patrick Ngongba II", "position": {"abbreviation": "C"}, "jersey": "21"},
        {"fullName": "Dame Sarr", "position": {"abbreviation": "F"}, "jersey": "7"}]


def _logs(conn):
    rows = [("cbb", 2026, "2026-11-17", "g1", "Cayden Boozer", "DUKE", "S", "min", 31),
            ("cbb", 2026, "2026-11-17", "g1", "Dame Sarr", "DUKE", "S", "min", 28),
            ("cbb", 2026, "2026-11-17", "g2", "Tyler Small", "espn:2948", "B", "min", 12)]
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, position, market,"
                     " value) VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()


def test_a_schools_published_roster_gives_its_players_their_positions():
    conn = connect(":memory:")
    _logs(conn)
    real = RB._cbb_feed
    RB._cbb_feed = lambda: ({"DUKE": [{"player": a["fullName"], "position": a["position"]["abbreviation"],
                                       "number": a["jersey"], "height": a.get("displayHeight")} for a in DUKE]},
                            ["UNC"])
    try:
        out = RB.payload_for(conn, "cbb", today="2026-11-19")
    finally:
        RB._cbb_feed = real
    assert out["source"] == "roster" and out["rosters_read"] == 1, out.get("source")
    duke = {p["player"]: p for p in out["teams"]["DUKE"]["players"]}
    assert duke["Cayden Boozer"]["position"] == "G" and duke["Cayden Boozer"]["games"] == 1, duke["Cayden Boozer"]
    assert duke["Patrick Ngongba II"]["position"] == "C" and duke["Patrick Ngongba II"]["games"] == 0, \
        "the roster lists who has not played"
    # A school not read yet keeps who has played, and the page says how many wait.
    assert [p["player"] for p in out["teams"]["espn:2948"]["players"]] == ["Tyler Small"]
    assert out["note"] == ("1 school roster not read yet show who has played, without positions, "
                           "until the next build reads them."), out["note"]
    assert "cbb" in RB.SLIM_SPORTS, "college basketball's file drops its empty fields, as college football's does"


def test_a_build_reads_its_budget_of_schools_and_the_rest_wait():
    cache = Path(tempfile.mkdtemp())
    real_dir = F.CACHE_DIR
    asked = []

    def fake(url, name):
        asked.append(name)
        return {"athletes": DUKE}
    try:
        F.CACHE_DIR = cache
        ids = {"AAA": "1", "BBB": "2", "CCC": "3", "DDD": "4"}
        # A stale file for DDD: past its day, it is read as it is once the budget is spent.
        stale = cache / "espn_cbb_roster_4.json"
        stale.write_text(json.dumps({"athletes": DUKE[:1]}))
        old = time.time() - RB.CBB_ROSTER_TTL - 60
        os.utime(stale, (old, old))
        # A fresh file for CCC costs nothing.
        (cache / "espn_cbb_roster_3.json").write_text(json.dumps({"athletes": DUKE}))
        feed, missed = RB._cbb_feed(ids=ids, budget=1, fetch=lambda url, name: (
            fake(url, name) if not (cache / name).exists() or name.endswith("_3.json")
            else json.loads((cache / name).read_text())))
    finally:
        F.CACHE_DIR = real_dir
    assert asked == ["espn_cbb_roster_1.json", "espn_cbb_roster_3.json"], asked
    assert sorted(feed) == ["AAA", "CCC", "DDD"] and missed == ["BBB"], (sorted(feed), missed)
    assert [p["player"] for p in feed["DDD"]] == ["Cayden Boozer"], "the stale file read as it is"


def test_the_search_shows_the_rosters_position_over_the_box_scores_mark():
    hits = [{"player": "Cayden Boozer", "team": "DUKE", "position": "S", "headshot": ""}]
    real = statlogs._roster_by_player
    statlogs._roster_by_player = lambda sport, data_dir=None: {("DUKE", "cayden boozer"): {
        "player": "Cayden Boozer", "team": "DUKE", "position": "G", "headshot": "h"}}
    try:
        statlogs._lend_roster("cbb", hits)
    finally:
        statlogs._roster_by_player = real
    assert hits[0]["position"] == "G", hits


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
