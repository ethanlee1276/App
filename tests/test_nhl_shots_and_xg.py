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



# --- X2: shot quality inside the models ---------------------------------------
from engine.nhl import edgehunter as EH                        # noqa: E402
from engine.nhl import model as M                              # noqa: E402
from engine.nhl import scan as SC                              # noqa: E402


def _teams():
    base = {"gf": 3.0, "ga": 3.0, "sog_for": 30.0, "sog_against": 30.0, "n": 40}
    return {t: dict(base) for t in ("AAA", "BBB", "CCC", "DDD")}


def test_team_strength_mixes_expected_goals_in_and_reads_as_before_without_it():
    teams = _teams()
    before = M.team_lambdas(teams, "AAA", "BBB")
    xs = {t: {"xgf": 60.0, "xga": 60.0, "xgf_ev": 45.0, "xga_ev": 45.0, "games": 20} for t in teams}
    xs["AAA"].update(xgf=80.0, xgf_ev=60.0)            # same goals, better chances
    M.attach_xg(teams, xs)
    after = M.team_lambdas(teams, "AAA", "BBB")
    assert teams["AAA"]["xgf"] == 4.0 and teams["AAA"]["xg_games"] == 20
    assert after[0] > before[0], "more chances for, more expected goals"
    plain = _teams()
    assert M.team_lambdas(plain, "AAA", "BBB") == before, "no xG, nothing moves"


def test_a_shooter_regresses_toward_what_his_shots_were_worth():
    games = [{"date": f"2025-11-{i + 1:02d}", "toi": 18.0, "sog": 3.0, "goals": float(i % 10 == 0)}
             for i in range(30)]
    p = {"position": "C", "games": games}
    league = {"F": {"sog": 8.0, "goals": 0.8, "points": 2.0, "assists": 1.2, "blocks": 1.0, "sh": 0.10},
              "sv": 0.900}
    slot = M.skater_projection(p, "goals", league, {}, "", xp={"ixg": 18.0, "sog": 90, "iff": 120,
                                                              "goals": 3, "games": 30})
    point = M.skater_projection(p, "goals", league, {}, "", xp={"ixg": 4.5, "sog": 90, "iff": 120,
                                                               "goals": 3, "games": 30})
    flat = M.skater_projection(p, "goals", league, {}, "")
    assert slot["mean"] > flat["mean"] > point["mean"], (slot, flat, point)
    assert slot["xsh"] > 0.10 > point["xsh"] and flat["xsh"] is None
    assert M.expected_sh(None, 0.1) is None


def test_the_opposing_goalie_is_measured_against_the_chances_he_faced():
    assert M.goalie_skill(None) is None and M.goalie_skill({"xga": 0, "ga": 0}) is None
    assert round(M.goalie_skill({"xga": 15.0, "ga": 10}), 3) == round(40 / 45, 3)
    teams = _teams()
    M.attach_xg(teams, {t: {"xgf": 60.0, "xga": 60.0, "xgf_ev": 45.0, "xga_ev": 45.0, "games": 20}
                        for t in teams})
    games = [{"date": f"2025-11-{i + 1:02d}", "toi": 18.0, "sog": 3.0, "goals": 0.3, "points": 0.8}
             for i in range(20)]
    p = {"position": "C", "games": games}
    league = {"F": {"sog": 8.0, "goals": 1.0, "points": 2.5, "assists": 1.5, "blocks": 1.0, "sh": 0.10},
              "sv": 0.900}
    leaky = M.skater_projection(p, "points", league, teams, "BBB", opp_sv=0.900, opp_skill=1.15)
    wall = M.skater_projection(p, "points", league, teams, "BBB", opp_sv=0.900, opp_skill=0.85)
    assert leaky["mean"] > wall["mean"] and leaky["shot_model"] == "xg"
    capped = M.skater_projection(p, "points", league, teams, "BBB", opp_skill=3.0)
    assert capped["opp"] == round(1 + M.GOALIE_CAP, 3), "a goalie never moves it past the cap"
    eh = EH.assess_prop("points", "OVER", 0.5, 0.6, 0.5, 0.06, -110, "fd", True, leaky, p, "AAA", "BBB",
                        ctx={"BBB": {"starter": "Wall", "starter_sure": True, "sv": 0.9, "gskill": 1.15,
                                     "gsax": -4.2}},
                        teams=teams, league=league)
    notes = {c["key"]: c["note"] for c in eh["components"]}
    assert "goals saved above expected" in notes["goalie"], notes
    assert "expected goals a game at 5-on-5" in notes["process"], notes


def test_the_scan_names_chances_allowed_and_finishing_luck():
    teams = _teams()
    xs = {t: {"xgf": 60.0, "xga": 60.0, "xgf_ev": 45.0, "xga_ev": 45.0, "games": 20} for t in teams}
    xs["BBB"].update(xga_ev=70.0)
    M.attach_xg(teams, xs)
    games = [{"date": f"2025-11-{i + 1:02d}", "toi": 18.0, "sog": 3.0} for i in range(12)]
    ctx = {"BBB": {"starter": "Leaky", "starter_sure": True, "sv": 0.9, "gsax": -5.0}}
    r = SC.read_skater("Shooter", {"position": "C", "games": games}, "AAA", "BBB", teams, ctx,
                       {"sv": 0.9}, xp={"ixg": 9.0, "goals": 3, "iff": 80, "sog": 60, "games": 20})
    text = " ".join(r["pro"] + r["notes"])
    assert "5-on-5 chances" in text and "goals saved above expected" in text
    assert "finishing cold, due to warm" in text
    t = SC.tape("AAA", "BBB", teams, ctx)
    assert t["sides"]["BBB"]["xga_ev"] == 3.5 and t["sides"]["BBB"]["ranks"]["xga_ev"] == 4


def test_no_model_no_change_and_the_build_reads_it_when_there_is_one():
    conn = db.connect(":memory:")
    old = os.environ.get("QB_MODELS_DIR")
    os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()
    try:
        assert X.board_summaries(conn) is None, "no fitted model: the board reads as before"
        db.upsert_nhl_shots(conn, P.parse_shots(PBP, "2025-10-30", 2025))
        X.save(X.fit_from_db(conn))
        xs = X.board_summaries(conn)
        assert xs and "Connor McDavid" in xs["players"] and xs["players"]["Connor McDavid"]["sog"] == 3
        kept = Path(os.environ["QB_MODELS_DIR"]) / X.BOARD_FILE
        assert kept.exists() and X.board_summaries(conn) == xs, "the next build reuses them"
        conn.execute("DELETE FROM nhl_shots WHERE event_id = 6")
        assert X.board_summaries(conn)["players"]["Connor McDavid"]["sog"] == 2, "new shots, new summaries"
    finally:
        if old is None:
            os.environ.pop("QB_MODELS_DIR", None)
        else:
            os.environ["QB_MODELS_DIR"] = old
    src = open(os.path.join(ROOT, "nhl_build.py"), encoding="utf-8").read()
    for wired in ("X.board_summaries(", "M.attach_xg(teams", "xs=xs", "xg_players="):
        assert wired in src, wired


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
