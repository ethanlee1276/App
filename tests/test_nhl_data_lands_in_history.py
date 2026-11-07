"""engine/sources/nhldata: the NHL's finals and box scores into history.

Ethan, 2026-10-03: "We want to get at least three years worth of NHL data
on the website." Fixture payloads in the API's shape (this sandbox cannot
reach api-web.nhle.com; `python3 ingest.py nhl --probe` checks the real
shape on the box). Checks: a final lands with its score, a live game lands
with none, preseason never lands, every skater and goalie line lands under
his FULL name (the box score's "C. McDavid" is looked up once), the older
"27/29" goalie format reads, and a backup who never played is skipped.

Run directly: `python3 tests/test_nhl_data_lands_in_history.py`
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db                                           # noqa: E402
from engine.sources import nhldata as N                         # noqa: E402

DAY = {"games": [
    {"id": 2025020001, "gameType": 2, "gameState": "OFF", "startTimeUTC": "2025-10-08T23:00:00Z",
     "homeTeam": {"abbrev": "EDM", "score": 4, "sog": 33, "name": {"default": "Oilers"}},
     "awayTeam": {"abbrev": "CGY", "score": 2, "sog": 25, "name": {"default": "Flames"}},
     "periodDescriptor": {"periodType": "REG"}},
    {"id": 2025020002, "gameType": 2, "gameState": "LIVE", "startTimeUTC": "2025-10-09T02:00:00Z",
     "homeTeam": {"abbrev": "VAN", "score": 1}, "awayTeam": {"abbrev": "SEA", "score": 0}},
    {"id": 2025010099, "gameType": 1, "gameState": "OFF",
     "homeTeam": {"abbrev": "TOR", "score": 3}, "awayTeam": {"abbrev": "MTL", "score": 1}},
]}

BOX = {"homeTeam": {"abbrev": "EDM"}, "awayTeam": {"abbrev": "CGY"},
       "playerByGameStats": {
           "homeTeam": {
               "forwards": [{"playerId": 8478402, "name": {"default": "C. McDavid"}, "position": "C",
                             "goals": 1, "assists": 2, "points": 3, "sog": 5, "hits": 1, "blockedShots": 0,
                             "powerPlayGoals": 1, "toi": "21:30"}],
               "defense": [{"playerId": 8480803, "name": {"default": "E. Bouchard"}, "position": "D",
                            "goals": 0, "assists": 1, "points": 1, "shots": 3, "hits": 0, "blockedShots": 2,
                            "toi": "24:06"}],
               "goalies": [{"playerId": 8479973, "name": {"default": "S. Skinner"}, "saveShotsAgainst": "23/25",
                            "goalsAgainst": 2, "toi": "60:00", "starter": True},
                           {"playerId": 8476999, "name": {"default": "C. Pickard"}, "toi": "00:00"}]},
           "awayTeam": {
               "forwards": [{"playerId": 8477496, "name": {"default": "N. Kadri"}, "position": "C",
                             "goals": 1, "assists": 0, "points": 1, "sog": 4, "toi": "18:12"}],
               "defense": [],
               "goalies": [{"playerId": 8480045, "name": {"default": "D. Vladar"}, "saves": 29,
                            "shotsAgainst": 33, "goalsAgainst": 4, "toi": "58:40", "starter": True}]}}}

PEOPLE = {"8478402": ("Connor", "McDavid"), "8480803": ("Evan", "Bouchard"), "8479973": ("Stuart", "Skinner"),
          "8477496": ("Nazem", "Kadri"), "8480045": ("Dan", "Vladar")}



def _no_pbp(game_id):
    """No play-by-play in these tests — the network is never touched."""
    raise N.DataUnavailable("no play-by-play in tests")

def _person(pid):
    f, l = PEOPLE[str(pid)]
    return {"firstName": {"default": f}, "lastName": {"default": l}, "headshot": f"https://img/{pid}.png"}


def _ingest():
    conn = db.connect(Path(tempfile.mkdtemp()) / "history.db")
    res = N.ingest_day(conn, "2025-10-08", fetch_day=lambda d: DAY, fetch_box=lambda g: BOX,
                       fetch_person=_person, fetch_pbp=_no_pbp)
    return conn, res


def test_a_final_lands_with_its_score_and_a_live_game_without_one():
    conn, res = _ingest()
    rows = {r[0]: (r[1], r[2]) for r in conn.execute(
        "SELECT game_id, home_score, away_score FROM games WHERE sport='nhl'")}
    assert rows["CGY@EDM"] == (4.0, 2.0)
    assert rows["SEA@VAN"] == (None, None), "a live score is never a result"
    assert "MTL@TOR" not in rows, "preseason never lands"


def test_every_line_lands_under_the_full_name():
    conn, _ = _ingest()
    got = {(r[0], r[1]): r[2] for r in conn.execute(
        "SELECT player, market, value FROM player_game_logs WHERE sport='nhl'")}
    assert got[("Connor McDavid", "sog")] == 5 and got[("Connor McDavid", "points")] == 3
    assert got[("Connor McDavid", "anytime_goal")] == 1 and got[("Connor McDavid", "toi")] == 21.5
    assert got[("Evan Bouchard", "sog")] == 3, "the older 'shots' field reads"
    assert got[("Evan Bouchard", "blocks")] == 2 and got[("Evan Bouchard", "anytime_goal")] == 0
    assert got[("Stuart Skinner", "saves")] == 23 and got[("Stuart Skinner", "shots_against")] == 25
    assert got[("Dan Vladar", "saves")] == 29 and got[("Dan Vladar", "started")] == 1
    assert not any(p == "C. McDavid" for p, _m in got), "no short names"
    assert not any(p.startswith("C") and "Pickard" in p for p, _m in got), "a backup who never played"


def test_the_season_is_the_year_it_started():
    conn, _ = _ingest()
    assert {r[0] for r in conn.execute("SELECT DISTINCT season FROM player_game_logs WHERE sport='nhl'")} == {2025}
    from engine.seasons import season_of
    assert season_of("nhl", "2026-03-01") == 2025


def test_a_player_is_looked_up_once():
    conn, _ = _ingest()
    calls = []
    N.ingest_day(conn, "2025-10-08", fetch_day=lambda d: DAY, fetch_box=lambda g: BOX,
                 fetch_person=lambda pid: calls.append(pid) or _person(pid),
                 fetch_pbp=_no_pbp)
    assert calls == [], "names come from player_assets the second time"
    assert conn.execute("SELECT headshot FROM player_assets WHERE sport='nhl' AND player='Connor McDavid'"
                        ).fetchone()[0] == "https://img/8478402.png"


def test_the_roster_pull_keeps_every_face_current():
    """Ethan, 2026-10-03: "make sure we are pulling all the up to date
    headshots for nhl." The first photo stored for a player was never asked
    for again, and the league's photo address carries the season and team."""
    conn, _ = _ingest()
    old = conn.execute("SELECT headshot FROM player_assets WHERE player='Connor McDavid'").fetchone()[0]
    roster = {"forwards": [{"id": 8478402, "firstName": {"default": "Connor"}, "lastName": {"default": "McDavid"},
                            "positionCode": "C", "headshot": "https://assets.nhle.com/mugs/nhl/20262027/EDM/8478402.png"}],
              "defensemen": [], "goalies": [{"id": 8479973, "firstName": {"default": "Stuart"},
                                             "lastName": {"default": "Skinner"}, "headshot": ""}]}
    out = Path(tempfile.mkdtemp())
    res = N.refresh_rosters(conn, "2026-10-03", teams=("EDM", "CGY"),
                            fetch=lambda t: roster if t == "EDM" else (_ for _ in ()).throw(N.DataUnavailable("down")),
                            out_dir=out)
    assert res["teams"] == 1 and res["failed"] == ["CGY"] and res["faces_changed"] == 1, res
    new = conn.execute("SELECT headshot FROM player_assets WHERE player='Connor McDavid'").fetchone()[0]
    assert new != old and "20262027" in new
    kept = conn.execute("SELECT headshot FROM player_assets WHERE player='Stuart Skinner'").fetchone()[0]
    assert kept == "https://img/8479973.png", "a blank photo never erases one we have"
    import json
    import datetime
    data = json.loads((out / N.ROSTER_FILE).read_text())
    data["date"] = datetime.date.today().isoformat()
    (out / N.ROSTER_FILE).write_text(json.dumps(data))
    assert N.load_rosters(path=out / N.ROSTER_FILE) == {"Connor McDavid": "EDM", "Stuart Skinner": "EDM"}


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
