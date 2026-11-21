"""Every league's season simulation starts from the table that is really
there: the wins already banked, and in hockey the points.

Found 2026-11-17. The live NHL projection showed all 32 clubs at 0-0 with
0 points after 321 games played. `futuresdata.records` and `points_banked`
read each standings group's "rows"; `engine.standings` has always written
them under "teams". Since 2026-08-03, then, every league's projection
(NFL, NBA, MLB, college football, NHL) has played out only the games left,
from 0-0. A 9-1 club got no credit for the nine. Nothing failed, because an
empty table is a valid table. So these checks build the table with the
real `standings.compute` on the real schema, never a mock of its shape.

Checks, one rule each:
- every league's banked record reaches the simulation;
- a hockey loss past regulation is the third column, worth a point;
- a hockey playoff game is not in the regular-season table;
- the projection starts from the banked points and writes W-L-OT;
- the NHL's projection is behind the paywall like every other league's,
  and the daily rebuild publishes through the paywall;
- Ask answers a hockey question in W-L-OT and points.

Run directly: `python3 tests/test_the_season_simulation_starts_from_the_real_table.py`
"""
import json
import os
import random
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db                                            # noqa: E402
from engine import futuresdata as FD                             # noqa: E402
from engine import gate, standings                               # noqa: E402
from engine.divisions import MAPS                                # noqa: E402

NHL = sorted(MAPS["nhl"])


def _db(rows):
    conn = db.connect(":memory:")
    conn.executemany(
        "INSERT INTO games (sport, season, period, game_id, home, away, "
        "home_score, away_score, extra) VALUES (?,?,?,?,?,?,?,?,?)", rows)
    return conn


def _nhl(day, home, away, hs, as_, ended="REG", kind=2):
    return ("nhl", 2026, day, f"{away}@{home}", home, away, hs, as_,
            json.dumps({"type": kind, "ended_in": ended}))


def test_every_league_banks_its_record_into_the_simulation():
    conn = _db([
        ("nfl", 2026, "3", "KC@BUF", "BUF", "KC", 20.0, 27.0, None),
        ("nfl", 2026, "4", "DEN@KC", "KC", "DEN", 30.0, 10.0, None),
        ("nba", 2026, "2026-10-25", "NYK@BOS", "BOS", "NYK", 110.0, 100.0, None),
        ("mlb", 2026, "2026-04-02", "NYY@BOS", "BOS", "NYY", 3.0, 5.0, None),
        _nhl("2026-10-08", "BOS", "TOR", 3.0, 2.0),
    ])
    assert FD.records(conn, "nfl", 2026) == {"KC": (2, 0), "BUF": (0, 1), "DEN": (0, 1)}
    assert FD.records(conn, "nba", 2026) == {"BOS": (1, 0), "NYK": (0, 1)}
    assert FD.records(conn, "mlb", 2026) == {"NYY": (1, 0), "BOS": (0, 1)}
    assert FD.records(conn, "nhl", 2026) == {"BOS": (1, 0), "TOR": (0, 1)}


def test_one_reader_walks_the_shape_the_table_writes():
    conn = _db([("nba", 2026, "2026-10-25", "NYK@BOS", "BOS", "NYK", 110.0, 100.0, None)])
    table = standings.compute(conn, "nba", season=2026)
    by_hand = [t for g in table["groups"] for t in g["teams"]]
    assert by_hand, "the computed table is empty, so this check would prove nothing"
    assert list(standings.team_rows(table)) == by_hand
    assert list(standings.team_rows({})) == [] and list(standings.team_rows(None)) == []


def test_a_hockey_loss_past_regulation_is_the_third_column_and_a_point():
    conn = _db([
        _nhl("2026-10-08", "BOS", "TOR", 3.0, 2.0, "REG"),   # BOS win, TOR loss
        _nhl("2026-10-09", "TOR", "BOS", 4.0, 3.0, "OT"),    # TOR win, BOS OT loss
        _nhl("2026-10-10", "BOS", "TOR", 2.0, 1.0, "SO"),    # BOS win, TOR OT loss
    ])
    rows = {r["team"]: r for r in standings.team_rows(standings.compute(conn, "nhl", season=2026))}
    assert (rows["BOS"]["wins"], rows["BOS"]["losses"], rows["BOS"]["otl"]) == (2, 0, 1)
    assert (rows["TOR"]["wins"], rows["TOR"]["losses"], rows["TOR"]["otl"]) == (1, 1, 1)
    assert rows["BOS"]["record"] == "2-0-1" and rows["BOS"]["points"] == 5
    assert rows["TOR"]["points"] == 3 and rows["TOR"]["games"] == 3
    # A home record is the league's: regulation losses only.
    assert rows["BOS"]["home"] == "2-0" and rows["TOR"]["away"] == "0-1"
    assert FD.points_banked(conn, "nhl", 2026) == ({"BOS": 5, "TOR": 3}, {"BOS": 1, "TOR": 1})
    # The simulation's outcome has no third kind: a game not won is a loss.
    assert FD.records(conn, "nhl", 2026) == {"BOS": (2, 1), "TOR": (1, 2)}


def test_a_hockey_row_with_no_ending_counts_as_regulation():
    conn = _db([("nhl", 2026, "2026-10-08", "TOR@BOS", "BOS", "TOR", 3.0, 2.0, None),
                ("nhl", 2026, "2026-10-09", "BOS@TOR", "TOR", "BOS", 3.0, 2.0, "not json")])
    rows = {r["team"]: r for r in standings.team_rows(standings.compute(conn, "nhl", season=2026))}
    assert rows["BOS"]["record"] == "1-1-0" and rows["TOR"]["record"] == "1-1-0"


def test_a_hockey_playoff_game_is_not_in_the_regular_season_table():
    conn = _db([
        _nhl("2026-10-08", "BOS", "TOR", 3.0, 2.0),
        _nhl("2027-04-25", "BOS", "TOR", 5.0, 1.0, kind=3),
    ])
    table = standings.compute(conn, "nhl", season=2026)
    rows = {r["team"]: r for r in standings.team_rows(table)}
    assert rows["BOS"]["wins"] == 1 and table["games_counted"] == 1


def test_the_projection_starts_from_the_banked_points_and_writes_w_l_ot():
    rng = random.Random(4)
    played = []
    for i in range(160):
        h, a = rng.sample(NHL, 2)
        played.append(_nhl(f"2026-10-{8 + i % 20:02d}", h, a, 3.0, 2.0, "OT" if i % 5 == 0 else "REG"))
    # One club has won every game it played, all in regulation.
    for i in range(12):
        played.append(_nhl(f"2026-11-{1 + i:02d}", "COL", NHL[i] if NHL[i] != "COL" else "EDM", 5.0, 1.0))
    conn = _db(played)
    left = [FD.Fixture(*rng.sample(NHL, 2)) for _ in range(200)]
    real = FD.FIXTURES.get("nhl")
    FD.FIXTURES["nhl"] = lambda _s: left
    try:
        out = FD.project(conn, "nhl", season=2026, trials=300, prices=False)
    finally:
        FD.FIXTURES["nhl"] = real
    table = {r["team"]: r for r in standings.team_rows(standings.compute(conn, "nhl", season=2026))}
    by = {t["team"]: t for t in out["teams"]}
    assert by, "the projection produced no clubs"
    for team, row in table.items():
        got = by[team]
        assert (got["wins"], got["losses"], got["otl"]) == (row["wins"], row["losses"], row["otl"]), team
        assert got["points"] == row["points"], f"{team} did not start from its banked points"
        assert got["played"] == row["games"], f"{team}'s games played lost its overtime losses"
        assert got["proj_points"] >= row["points"], f"{team} projects fewer points than it has"
    assert by["COL"]["wins"] >= 12 and by["COL"]["points"] >= 24
    assert sum(t["played"] for t in out["teams"]) == 2 * len(played)


def test_the_nhl_projection_is_behind_the_paywall_like_every_league():
    for sport in ("nfl", "mlb", "cfb", "nba", "nhl", "cbb"):
        name = f"futures_{sport}.json"
        assert name in gate.PAID_FILES and name in gate.KNOWN_BOARDS, name
    kept = gate.redact({"sport": "nhl", "teams": [{"team": "COL", "p_title": 0.2}]}, "futures_nhl.json")
    assert "teams" not in kept and kept.get("locked_reason") == "subscription"


def test_the_daily_rebuild_publishes_through_the_paywall():
    """The refresh loop's daily rebuild wrote the full projection straight
    onto the public path: unsealed until the next restart, and the
    members' copy never refreshed. It goes through `gate.publish`, the
    door `futures_build.main` and every other board use."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def _run_futures(")
    block = src[i:src.index("\ndef ", i + 1)]
    assert "futures_build.publish(sport, data, conn)" in block
    assert "json.dumps(data" not in block and "os.replace(" not in block
    src = open(os.path.join(ROOT, "futures_build.py"), encoding="utf-8").read()
    body = src[src.index("def publish("):src.index("def main(")]
    assert 'gate.publish(data, OUT / f"futures_{sport}.json")' in body


def test_a_fix_to_the_projection_rebuilds_on_the_first_pass_after_its_deploy():
    """A day-old stamp from the old code is not fresh: the corrected
    numbers go up on the loop's next pass, not up to a day later."""
    import time
    import launch
    d = tempfile.mkdtemp()
    stamp = os.path.join(d, "web", "data", ".futures_built")
    os.makedirs(os.path.dirname(stamp))
    built = []
    real_root, real_build = launch.ROOT, None
    import futures_build
    real_build, real_sports = futures_build.build, futures_build.SPORTS
    real_publish = futures_build.publish
    futures_build.build = lambda sport, conn, **k: built.append(sport) or {"sport": sport, "teams": []}
    futures_build.SPORTS = ("nhl",)
    futures_build.publish = lambda sport, data, conn: ""
    launch.ROOT = __import__("pathlib").Path(d)
    try:
        with open(stamp, "w", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%dT%H:%M:%S"))       # the old code's stamp
        launch._run_futures(quiet=True)
        assert built == ["nhl"], "an old stamp kept the corrected numbers off for a day"
        assert open(stamp, encoding="utf-8").read().endswith(launch.FUTURES_VERSION)
        launch._run_futures(quiet=True)
        assert built == ["nhl"], "a fresh stamp from this code must still throttle to a day"
    finally:
        launch.ROOT = real_root
        futures_build.build, futures_build.SPORTS = real_build, real_sports
        futures_build.publish = real_publish


def test_ask_answers_hockey_in_w_l_ot_and_points():
    from engine import askbot
    d = tempfile.mkdtemp()
    blob = {"sport": "nhl", "season": 2026, "points_league": True, "teams": [
        {"team": "COL", "wins": 12, "losses": 3, "otl": 2, "points": 26, "played": 17,
         "proj_points": 108.4, "proj_points_lo": 99, "proj_points_hi": 117,
         "proj_wins": 50.1, "proj_wins_lo": 46, "proj_wins_hi": 54, "p_playoffs": 0.97, "p_title": 0.18}]}
    with open(os.path.join(d, "futures_nhl.json"), "w", encoding="utf-8") as fh:
        json.dump(blob, fh)
    old, askbot.PAID_DIR = askbot.PAID_DIR, d
    try:
        got = askbot.futures("nhl")
    finally:
        askbot.PAID_DIR = old
    row = got["rows"][0]
    assert row["record"] == "12-3-2", row
    assert row["points"] == 26 and row["projected_points"] == 108.4
    assert row["projected_points_range"] == "99-117"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
