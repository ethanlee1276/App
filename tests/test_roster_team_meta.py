"""The college roster page can draw a logo from its own payload.

Ethan, 2026-09-14: "We should be showing your team logos on the team
roster." ESPN keys its schools numerically, so `logoUrl` needs the team's
`id` — which the front end only had once the BOARD had loaded. Now
`rosters_build.write` carries the same cached teams map the board uses,
and `renderRosters` reads it.
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import rosters_build                                          # noqa: E402
from engine.sources import cfbdata                            # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fake_payload(conn, sport, today):
    return {"sport": sport, "teams": {"UGA": {"count": 1, "players": []}},
            "team_count": 1, "player_count": 1, "generated_at": "", "feed": "t",
            "source": "", "note": ""}


def test_college_rosters_carry_the_team_id_map():
    tmp = Path(tempfile.mkdtemp())
    keep = (rosters_build.payload_for, rosters_build.connect,
            cfbdata.fetch_teams, cfbdata.parse_teams)
    rosters_build.payload_for = _fake_payload
    rosters_build.connect = lambda: type("C", (), {"close": lambda s: None})()
    cfbdata.fetch_teams = lambda ttl=0: {"raw": 1}
    cfbdata.parse_teams = lambda payload: {"UGA": {"id": "61", "name": "Georgia"}}
    try:
        blob = rosters_build.write("cfb", tmp)
    finally:
        (rosters_build.payload_for, rosters_build.connect,
         cfbdata.fetch_teams, cfbdata.parse_teams) = keep
    assert blob["team_meta"] == {"UGA": {"id": "61", "name": "Georgia"}}
    assert '"team_meta"' in (tmp / "rosters_cfb.json").read_text()


def test_a_dead_teams_feed_costs_only_the_logo():
    tmp = Path(tempfile.mkdtemp())
    keep = (rosters_build.payload_for, rosters_build.connect, cfbdata.fetch_teams)
    rosters_build.payload_for = _fake_payload
    rosters_build.connect = lambda: type("C", (), {"close": lambda s: None})()
    cfbdata.fetch_teams = lambda ttl=0: (_ for _ in ()).throw(RuntimeError("down"))
    try:
        blob = rosters_build.write("cfb", tmp)
    finally:
        rosters_build.payload_for, rosters_build.connect, cfbdata.fetch_teams = keep
    assert blob["team_meta"] == {} and blob["teams"], blob


def test_other_leagues_are_untouched():
    tmp = Path(tempfile.mkdtemp())
    keep = (rosters_build.payload_for, rosters_build.connect)
    rosters_build.payload_for = _fake_payload
    rosters_build.connect = lambda: type("C", (), {"close": lambda s: None})()
    try:
        blob = rosters_build.write("nfl", tmp)
    finally:
        rosters_build.payload_for, rosters_build.connect = keep
    assert "team_meta" not in blob


def test_the_roster_page_reads_it():
    body = APP[APP.index("async function renderRosters()"):]
    body = body[:body.index("\n}\n")]
    assert "_cfbTeams = d.team_meta" in body, "the roster view never adopts the ids"
    assert "window.ACTIVE_TEAMS = teamsForSport(sport)" in body, \
        "teamMark reads ACTIVE_TEAMS, which must be refreshed once the ids land"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
