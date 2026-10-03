"""NHL shots from the play-by-play, and the expected-goals model fitted on them.

Ethan, 2026-10-03: "the opposing goalie, the shot quality, the power play
role ... continue doing all that." Checks, one rule each: a shot is placed
against the net its team attacks (the home side flips by period through
``homeTeamDefendingSide``), with its type, the shooter's strength, an empty
net, a rebound and a rush; shootouts and plays with no shooter are not
shots; a close shot is worth more than a far one and a rare cell borrows
from its parent instead of reading 1-for-1; blocks carry no xG; the
summaries add up per player, team and goalie (goals saved above
expected); the backfill skips games already stored; the daily ingest
stores shots without a second walk; and nothing here touches the network.

Run directly: `python3 tests/test_nhl_shots_and_xg.py`
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db                                          # noqa: E402
from engine.nhl import xg as X                                 # noqa: E402
from engine.sources import nhlpbp as P                         # noqa: E402


def _play(eid, kind, t, x, y, owner, shooter, code="1551", side="right", period=1, ptype="REG", **d):
    det = {"xCoord": x, "yCoord": y, "eventOwnerTeamId": owner, "shotType": d.pop("shot", "wrist"),
           "goalieInNetId": d.pop("goalie", 800 if owner == 22 else 900)}
    det["scoringPlayerId" if kind == "goal" else "shootingPlayerId"] = shooter
    det.update(d)
    return {"eventId": eid, "typeDescKey": kind, "timeInPeriod": t, "situationCode": code,
            "homeTeamDefendingSide": side, "periodDescriptor": {"number": period, "periodType": ptype},
            "details": det}


PBP = {
    "id": 2025020101, "homeTeam": {"id": 22, "abbrev": "EDM"}, "awayTeam": {"id": 20, "abbrev": "CGY"},
    "rosterSpots": [
        {"teamId": 22, "playerId": 97, "firstName": {"default": "Connor"}, "lastName": {"default": "McDavid"}},
        {"teamId": 20, "playerId": 13, "firstName": {"default": "Jonathan"}, "lastName": {"default": "Huberdeau"}},
        {"teamId": 20, "playerId": 800, "firstName": {"default": "Dan"}, "lastName": {"default": "Vladar"}},
        {"teamId": 22, "playerId": 900, "firstName": {"default": "Stuart"}, "lastName": {"default": "Skinner"}}],
    "plays": [
        # EDM (home) defends the right end in period 1, so attacks x = -89.
        {"eventId": 1, "typeDescKey": "faceoff", "timeInPeriod": "00:00",
         "details": {"xCoord": 0, "yCoord": 0}, "periodDescriptor": {"number": 1, "periodType": "REG"}},
        _play(2, "shot-on-goal", "00:03", -80, 3, 22, 97),                 # rush: 3s after the centre faceoff
        _play(3, "goal", "00:05", -85, -2, 22, 97, shot="tip-in"),         # rebound, 2s after the last
        _play(4, "missed-shot", "05:00", 60, 20, 20, 13, code="1541"),     # CGY on the PP (5 v 4)
        _play(5, "blocked-shot", "06:00", 50, 0, 20, 13),
        _play(6, "shot-on-goal", "19:30", -30, 0, 22, 97, code="0651", goalie=None),   # CGY net empty
        {"eventId": 7, "typeDescKey": "shot-on-goal", "timeInPeriod": "10:00",
         "details": {"xCoord": 10, "yCoord": 0, "eventOwnerTeamId": 22},
         "periodDescriptor": {"number": 2, "periodType": "REG"}},          # no shooter: not a row
        _play(8, "goal", "00:00", -70, 0, 22, 97, ptype="SO", period=5),  # shootout: never a shot
    ],
}


def test_a_shot_is_placed_against_the_net_its_team_attacks():
    rows = P.parse_shots(PBP, "2025-10-30", 2025)
    assert [r["event_id"] for r in rows] == [2, 3, 4, 5, 6], "no shooter and the shootout are not shots"
    sog, goal, miss, block, en = rows
    assert sog["dist"] == 9.5 and sog["team"] == "EDM" and sog["opponent"] == "CGY"
    assert sog["shooter"] == "Connor McDavid" and sog["goalie"] == "Dan Vladar"
    assert goal["is_goal"] == 1 and goal["rebound"] == 1 and goal["shot_type"] == "tip-in"
    assert miss["strength"] == "PP" and miss["team"] == "CGY" and miss["dist"] == round((29 ** 2 + 20 ** 2) ** .5, 1)
    assert block["kind"] == "block" and en["empty_net"] == 1
    assert sog["rush"] == 1, "three seconds after a faceoff at centre ice"


def test_close_beats_far_and_a_rare_cell_borrows_from_its_parent():
    rows = []
    for i in range(400):
        rows.append({"kind": "sog", "is_goal": int(i % 5 == 0), "dist": 8, "angle": 10, "shot_type": "wrist",
                     "strength": "EV", "rebound": 0, "rush": 0, "empty_net": 0})
        rows.append({"kind": "sog", "is_goal": int(i % 40 == 0), "dist": 50, "angle": 10, "shot_type": "slap",
                     "strength": "EV", "rebound": 0, "rush": 0, "empty_net": 0})
    rows.append({"kind": "goal", "is_goal": 1, "dist": 50, "angle": 10, "shot_type": "slap",
                 "strength": "SH", "rebound": 1, "rush": 0, "empty_net": 0})
    m = X.fit(rows)
    near = X.xg(m, {"kind": "sog", "dist": 8, "angle": 10, "shot_type": "wrist", "strength": "EV"})
    far = X.xg(m, {"kind": "sog", "dist": 50, "angle": 10, "shot_type": "slap", "strength": "EV"})
    rare = X.xg(m, {"kind": "goal", "dist": 50, "angle": 10, "shot_type": "slap", "strength": "SH", "rebound": 1})
    assert near > 0.15 > far and far < 0.05
    assert rare < 0.2, "one shorthanded rebound goal is not a sure thing"
    assert X.xg(m, {"kind": "block", "dist": 5}) == 0.0
    assert X.xg(m, {"kind": "sog", "empty_net": 1, "dist": 80}) == 0.6
    path = Path(tempfile.mkdtemp()) / "m.json"
    X.save(m, path)
    assert X.load(path)["n"] == m["n"] == 801


def test_the_summaries_add_up_for_players_teams_and_goalies():
    conn = db.connect(":memory:")
    db.upsert_nhl_shots(conn, P.parse_shots(PBP, "2025-10-30", 2025))
    m = X.fit([{"kind": "sog", "is_goal": 0, "dist": 30, "angle": 10, "shot_type": "wrist", "strength": "EV",
                "rebound": 0, "rush": 0, "empty_net": 0}] * 50)
    rows = X.game_rows(conn, m)
    s = X.summaries(rows)
    mc = s["players"]["Connor McDavid"]
    assert mc["iff"] == 3 and mc["goals"] == 1 and mc["games"] == 1, mc
    edm, cgy = s["teams"]["EDM"], s["teams"]["CGY"]
    assert edm["gf"] == 1 and cgy["ga"] == 1 and round(edm["xgf"], 3) == round(cgy["xga"], 3)
    assert edm["xgf_ev"] < edm["xgf"], "the empty-net shot is not even strength"
    vlad = s["goalies"]["Dan Vladar"]
    assert vlad["shots"] == 2 and vlad["ga"] == 1 and vlad["gsax"] == round(vlad["xga"] - 1, 2)


def test_the_backfill_skips_what_is_stored_and_the_daily_ingest_stores_shots():
    conn = db.connect(Path(tempfile.mkdtemp()) / "h.db")
    db.upsert_games(conn, [{"sport": "nhl", "season": 2025, "period": "2025-10-30", "game_id": "CGY@EDM",
                            "home": "EDM", "away": "CGY", "home_score": 2, "away_score": 1, "date": "2025-10-30",
                            "extra": json.dumps({"nhl_id": 2025020101})}])
    calls = []
    fetch = lambda gid: calls.append(gid) or PBP                                   # noqa: E731
    r = P.backfill(conn, fetch=fetch)
    assert r == {"games": 1, "shots": 5, "failed": 0, "todo": 1} and calls == [2025020101]
    assert P.backfill(conn, fetch=fetch)["todo"] == 0, "a stored game is not fetched again"
    src = open(os.path.join(ROOT, "engine", "sources", "nhldata.py"), encoding="utf-8").read()
    assert "nhlpbp.ingest_game(" in src, "the nightly results ingest stores each final's shots"


def test_the_flag_the_refit_and_the_cache_are_wired():
    ing = open(os.path.join(ROOT, "ingest.py"), encoding="utf-8").read()
    assert '"--shots"' in ing and "nhlpbp.backfill(" in ing
    mnt = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()
    assert "_xg.fit_from_db(hconn2)" in mnt and '"nhl_pbp_"' in mnt


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
