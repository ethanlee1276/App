"""College basketball's shot chart: the NBA's chart on the college court.

Ethan, 2026-11-13: "don't stop working until you've added every single tool
and feature that we have for NBA onto college basketball. Make sure we use
the renders that we use for NBA." The NBA's shot chart reads each final's
ESPN summary (engine/nba/shots.fold_espn); college's summaries are the same
feed, and ESPN's college play-by-play keeps the NBA's frame (the basket at
x 25, y 0, whole feet; on 2025-26's 990,000 college shots with a spot the
threes sat 22.0 feet and out). What these hold:

  * a college final folds into college's OWN table (`cbb_shots`), its
    schools keyed as the board keys them (`espnhoops.team_key`), its zones on
    the college court (a 12-foot lane: a shot 7 feet off the middle is in the
    NBA's paint and outside college's), never into the NBA's table, whose
    zone percentages are every NBA shot of the season;
  * the results ingest folds them off the summary it already read, so they
    cost no fetch;
  * the chart reads college's table, by half, beside college's own zone
    percentages, and the door serves it;
  * the page draws the college court (lane 190-310, the arc at 22 feet 1.75
    inches) and says H1, H2 and "By half"; the NBA's court is untouched.

Run directly: `python3 tests/test_a_shot_chart_for_every_college_player.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())

from engine import charts as CH, db as D  # noqa: E402
from engine.nba import shots as NS  # noqa: E402
from engine.sources import espnhoops as EH  # noqa: E402

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
HOOPS_JS = (ROOT / "web" / "js" / "chart-hoops.js").read_text(encoding="utf-8")

FLAGG, KNUEPPEL, CADEAU = 4433134, 4433135, 4433136
DUKE_ID, UNC_ID = "150", "153"


def _play(seq, team, who, pts, made, x=None, y=None, kind="JumpShot", per=1, clock="11:30"):
    p = {"id": f"8{seq}", "sequenceNumber": str(seq), "period": {"number": per}, "clock": {"displayValue": clock},
         "team": {"id": team}, "participants": [{"athlete": {"id": str(w)}} for w in who],
         "type": {"id": "1", "text": kind}, "shootingPlay": True, "scoringPlay": made,
         "scoreValue": pts if made else 0, "pointsAttempted": pts,
         "text": "ESPN PROSE NEVER STORED"}
    p["coordinate"] = {"x": x, "y": y} if x is not None else {"x": -214748340, "y": -214748365}
    return p


def _summary(gid="401820001"):
    """A college final's summary: the header's teams carry no conference
    (the scoreboard does), so the board's codes come from the ids a
    scoreboard tied to them."""
    def ath(i, name):
        return {"athlete": {"id": str(i), "displayName": name}, "stats": []}
    return {"header": {"id": gid, "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"id": DUKE_ID, "abbreviation": "DUKE"}},
                {"homeAway": "away", "team": {"id": UNC_ID, "abbreviation": "UNC"}}]}]},
            "boxscore": {"players": [
                {"team": {"id": DUKE_ID}, "statistics": [{"athletes": [
                    ath(FLAGG, "Cooper Flagg"), ath(KNUEPPEL, "Kon Knueppel")]}]},
                {"team": {"id": UNC_ID}, "statistics": [{"athletes": [ath(CADEAU, "Elliot Cadeau")]}]}]},
            "plays": [
                _play(4, DUKE_ID, (FLAGG, KNUEPPEL), 2, True, x=25, y=1, kind="DunkShot"),   # at the rim
                _play(6, DUKE_ID, (FLAGG,), 2, False, x=32, y=5),          # 7 ft off the middle: college's mid
                _play(8, DUKE_ID, (FLAGG,), 3, True, x=3, y=3),            # the corner
                _play(9, DUKE_ID, (FLAGG,), 3, False, x=25, y=23, per=2, clock="4:10"),   # up top, second half
                _play(10, DUKE_ID, (FLAGG,), 1, True, kind="MadeFreeThrow", per=2),
                _play(12, UNC_ID, (CADEAU,), 2, True, x=22, y=4, kind="LayUpShot", per=3, clock="2:00"),  # overtime
            ]}


def _seed():
    EH.DI_SEEN.update({DUKE_ID: "DUKE", UNC_ID: "UNC"})


# --- the fold ------------------------------------------------------------------------
def test_a_college_final_folds_onto_the_college_court():
    _seed()
    rows = NS.fold_espn(_summary(), "2026-11-12", league="cbb")
    by = {r["action"]: r for r in rows}
    assert sorted(by) == [4, 6, 8, 9, 10, 12]
    assert by[4]["team"] == "DUKE" and by[4]["opponent"] == "UNC" and by[4]["home"] == 1
    assert by[4]["zone"] == "ra" and by[4]["assist"] == "Kon Knueppel"
    assert (by[6]["x"], by[6]["y"]) == (70.0, 50.0)
    assert by[6]["zone"] == "mid", "7 feet off the middle is outside a 12-foot lane"
    assert NS.zone("2pt", 70.0, 50.0, 8.6) == "paint", "and inside the NBA's 16-foot one"
    assert by[8]["zone"] == "corner3" and by[9]["zone"] == "above3" and by[9]["period"] == 2
    assert by[10]["kind"] == "ft" and by[10]["x"] is None
    assert by[12]["team"] == "UNC" and by[12]["home"] == 0
    assert all(r["season"] == 2026 for r in rows), "a college season is named by the year it starts"
    assert not any("PROSE" in str(v) for r in rows for v in r.values())
    # A school no scoreboard has placed in Division I keeps the board's spelling for a small school.
    EH.DI_SEEN.pop(UNC_ID, None)
    try:
        small = NS.fold_espn(_summary(), "2026-11-12", league="cbb")
        assert {r["team"] for r in small if r["action"] == 12} == {f"espn:{UNC_ID}"}
    finally:
        _seed()


def test_college_shots_live_in_their_own_table():
    _seed()
    conn = D.connect(":memory:")
    D.upsert_cbb_shots(conn, NS.fold_espn(_summary(), "2026-11-12", league="cbb"))
    assert conn.execute("SELECT COUNT(*) FROM cbb_shots").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM nba_shots").fetchone()[0] == 0, "the NBA's zones stay the NBA's"
    assert NS.stored(conn, league="cbb") == {"401820001"} and NS.stored(conn) == set()
    assert NS.table_of("cbb") == "cbb_shots" and NS.table_of("nba") == "nba_shots"


def test_the_results_ingest_keeps_them_off_the_summary_it_read():
    _seed()
    conn = D.connect(":memory:")
    game = {"game_id": "401820001", "home": "DUKE", "away": "UNC", "home_id": DUKE_ID, "away_id": UNC_ID,
            "home_score": 80, "away_score": 71, "completed": True}
    asked = []
    keep = (EH.load_day, EH.fetch_summary)
    EH.load_day = lambda date, ttl=None, league="wnba": [dict(game)]

    def summary(gid, ttl=30 * 24 * 3600, league="wnba"):
        asked.append((gid, league))
        return _summary(gid)
    EH.fetch_summary = summary
    try:
        res = EH.ingest_day(conn, "2026-11-12", league="cbb")
    finally:
        EH.load_day, EH.fetch_summary = keep
    assert asked == [("401820001", "cbb")], "one summary read, the one the box score already needed"
    assert res["shots"] == 6 and conn.execute("SELECT COUNT(*) FROM cbb_shots").fetchone()[0] == 6
    assert not any("shots" in s for s in res["skipped"]), res["skipped"]


def test_the_nightly_fills_the_finals_stored_before_and_files_an_empty_one_once():
    """Finals stored before the ingest folded shots are read back a budget a
    night; a final read whole with no shot in it (a small school's, often no
    play-by-play) is filed as known-empty so it is never read again."""
    import datetime as dt
    _seed()
    conn = D.connect(":memory:")
    D.upsert_games(conn, [{"sport": "cbb", "season": 2026, "period": d, "game_id": g, "home": "DUKE",
                           "away": "UNC", "home_score": 80.0, "away_score": 71.0, "date": d}
                          for g, d in (("401820001", "2026-11-12"), ("401820002", "2026-11-11"))])
    reads = []

    def read(gid):
        reads.append(gid)
        return _summary(gid) if gid == "401820001" else {"header": {"id": gid}, "plays": []}
    got = NS.backfill(conn, dt.date(2026, 11, 13), read=read, league="cbb")
    assert got["games"] == 1 and got["shots"] == 6 and got.get("empty") == 1 and got["left"] == 0, got
    assert NS.stored(conn, league="cbb") == {"401820001", "401820002"}
    again = NS.backfill(conn, dt.date(2026, 11, 13), read=read, league="cbb")
    assert again["games"] == 0 and reads == ["401820001", "401820002"], "an empty final is not read twice"
    d = NS.chart(conn, "Cooper Flagg", league="cbb")
    assert {z["key"]: z["league"] for z in d["zones"]}["ra"] == 1.0, "the empty mark is in no zone"
    import inspect
    from engine import maintenance as M
    src = inspect.getsource(M._run_chores)
    assert '_cshots.backfill(_cs, today, league="cbb")' in src


# --- the chart -------------------------------------------------------------------------
def _conn():
    _seed()
    conn = D.connect(":memory:")
    D.upsert_cbb_shots(conn, NS.fold_espn(_summary(), "2026-11-12", league="cbb"))
    D.upsert_player_logs(conn, [{"sport": "cbb", "season": 2026, "period": "2026-11-12", "game_id": "401820001",
                                 "player": "Cooper Flagg", "team": "DUKE", "opponent": "UNC", "position": "F",
                                 "home": 1, "market": m, "value": v}
                                for m, v in (("min", 34.0), ("reb", 9.0), ("ast", 4.0))])
    return conn


def test_the_chart_reads_his_halves_and_colleges_own_zones():
    d = NS.chart(_conn(), "Cooper Flagg", league="cbb")
    assert d["sport"] == "cbb" and d["season"] == 2026 and d["team"] == "DUKE"
    assert [p["key"] for p in d["by_period"]] == ["H1", "H2"], "two halves, not four quarters"
    g = d["games"][0]
    assert (g["line"]["fga"], g["line"]["fgm"], g["line"]["fta"]) == (4, 2, 1) and g["line"]["pts"] == 6
    assert g["box"] == {"min": 34.0, "reb": 9.0, "ast": 4.0}, "his box score from college's own logs"
    zones = {z["key"]: z for z in d["zones"]}
    assert zones["corner3"]["fgm"] == 1 and zones["mid"]["fga"] == 1
    assert zones["ra"]["league"] == 1.0, "the league's own: every college shot of the season on file"
    assert NS.chart(_conn(), "Cooper Flagg") == {}, "the NBA's chart never reads college's table"


def test_the_door_serves_college_shots():
    assert CH.known("shots", "cbb") and CH.known("shots", "nba") and not CH.known("shots", "wnba")
    got = CH.answer(_conn(), "shots", "cbb", "Cooper Flagg")
    assert got["kind"] == "shots" and got["sport"] == "cbb" and got["season_line"]["pts"] == 6
    empty = D.connect(":memory:")
    assert CH.answer(empty, "shots", "cbb", "Cooper Flagg") == {"filling": True}, "an empty table is filling"


def test_the_matchup_reads_colleges_own_defenses():
    """The NBA's matchup view (his zones beside what tonight's opponent
    allows in each, engine/matchview) off college's own table."""
    from engine import matchview as MV
    conn = _conn()
    got = MV.chart(conn, "cbb", "Cooper Flagg", "UNC")
    assert got["sport"] == "cbb" and got["family"] == "shots" and got["opp"] == "UNC", got
    assert {z["key"] for z in got["zones"]} <= {"ra", "paint", "mid", "corner3", "above3"}
    assert sum(z["n"] for z in got["zones"]) == 4, "his four shots from the floor"
    assert CH.known("matchup", "cbb") and MV.chart(conn, "nba", "Cooper Flagg", "UNC") == {}


# --- the page --------------------------------------------------------------------------
def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {};
      const window = {};
    """
    prog = (f"{stubs}\n{CC_JS}\n{HOOPS_JS}\n"
            f"console.log(JSON.stringify((() => {{ const T = window.QBCarry._t; {js} }})()));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_page_draws_the_college_court():
    d = NS.chart(_conn(), "Cooper Flagg", league="cbb")
    got = _node(f"""
      const d = {json.dumps(d)}, P = T.DRAW.shots, g = d.games[0];
      const nba = Object.assign({{}}, d, {{ sport: "nba" }});
      return {{
        game: P.game(g, d), season: P.season(d), list: P.list(g, d), tables: P.splits(d),
        note: P.note(d), tip: P.tip(g.shots[3], g, d), nbaGame: P.game(g, nba), nbaList: P.list(g, nba),
        kinds: [T.kindsFor("cbb", "pts", "F"), T.kindsFor("wnba", "pts", "")],
      }};
    """)
    if got is None:
        return
    assert 'x="190" y="0" width="120"' in got["game"], "a 12-foot lane"
    assert "M33.5 0 V94.3 A221.5 221.5 0 0 0 466.5 94.3 V0" in got["game"], "the college arc"
    assert 'x="170" y="0" width="160"' in got["nbaGame"] and "A237.5 237.5" in got["nbaGame"], "the NBA's untouched"
    assert "A221.5 221.5" in got["season"]
    assert "H2 4:10" in got["list"] and "Q2 4:10" in got["nbaList"]
    assert "By half" in got["tables"] and "By quarter" not in got["tables"]
    assert "college court" in got["note"] and "H2" in got["tip"]
    assert got["kinds"] == [["shots", "role"], ["role"]], "a college bet opens his shots; the WNBA's her role"


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
