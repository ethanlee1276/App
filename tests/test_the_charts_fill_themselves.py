"""The carry and route charts fill the day a table is empty — not the next night.

Ethan, 2026-10-13, about an hour after both charts shipped: "Also the
charts aren't working for any players." The charts were fine and their
tables were empty: every row comes from reads inside the daily chores,
which run once a calendar day, and the box had already run that day's
when the charts' code landed. Every player's chart read "No carries on
file" and would have until the next day's chores.

What is pinned, offline, on databases built here:

  * WHAT IS OWED (engine/chartfill.owed): a chart table with no rows for
    a season — this one or last — the box has a finished game of; never
    a season with no games (a clone or a test owes nothing), never a
    table that has rows (behind is the nightly's job);
  * EVERY CYCLE ONCE THE DAY'S CHORES ARE DONE: run_if_due asks it on
    the pass that returns "already done today" — never beside the
    chores' own read of the same plays;
  * ONCE, THEN A WHILE: the fill starts as a detached child, at most
    once every CHART_FILL_EVERY_S, and a sandbox never starts a real one;
  * ONE READ: an owed NFL season's play-by-play is read once and feeds
    both charts; a failed read is a line, not the end of the others;
  * THE PAGE SAYS SO: a league with no chart rows at all answers
    {"filling": true}, and the page says the charts are being filled
    instead of "no carries on file" for a player who has hundreds.

Run directly: `python3 tests/test_the_charts_fill_themselves.py`
"""
import datetime as dt
import inspect
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import carries as CR, chartfill as CF, db as D, maintenance as M, passes as PS, targets as TG  # noqa: E402

TODAY = dt.date(2026, 10, 13)
CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
ALLEN, LAPORTA = "00-0034857", "00-0039065"
NAMES = {ALLEN: {"name": "Josh Allen", "position": "QB", "jersey": "17"},
         LAPORTA: {"name": "Sam LaPorta", "position": "TE", "jersey": "87"}}


def _game(conn, sport, season, gid, score=21.0, date="2026-10-11"):
    D.upsert_games(conn, [{"sport": sport, "season": season, "period": "005", "game_id": gid,
                           "home": "LA", "away": "BUF", "home_score": score,
                           "away_score": None if score is None else 24.0, "date": date}])


def _run(**kw):
    row = {"play_type": "run", "season": "2026", "season_type": "REG", "week": "5",
           "game_id": "2026_05_BUF_LA", "home_team": "LA", "away_team": "BUF", "posteam": "BUF",
           "defteam": "LA", "game_date": "2026-10-12", "rusher_player_id": ALLEN,
           "rusher_player_name": "J.Allen", "rushing_yards": "8", "yards_gained": "8",
           "run_location": "left", "run_gap": "end", "qb_scramble": "0", "two_point_attempt": "0",
           "fumble_lost": "0", "fumbled_1_player_id": "NA", "rush_touchdown": "0",
           "first_down_rush": "0", "down": "1", "ydstogo": "10", "yardline_100": "47", "qtr": "1",
           "quarter_seconds_remaining": "264", "play_id": "100"}
    row.update(kw)
    return row


def _pass(**kw):
    row = {"play_type": "pass", "season": "2026", "season_type": "REG", "week": "5",
           "game_id": "2026_05_DET_ARI", "home_team": "ARI", "away_team": "DET", "posteam": "DET",
           "defteam": "ARI", "game_date": "2026-10-11", "receiver_player_id": LAPORTA,
           "receiver_player_name": "S.LaPorta", "air_yards": "11", "pass_location": "middle",
           "complete_pass": "1", "yards_after_catch": "1", "receiving_yards": "12",
           "pass_touchdown": "0", "td_player_id": "NA", "interception": "0", "first_down_pass": "1",
           "two_point_attempt": "0", "sack": "0", "down": "4", "ydstogo": "3", "yardline_100": "47",
           "qtr": "2", "quarter_seconds_remaining": "817", "play_id": "1157"}
    row.update(kw)
    return row


def _one_throw(conn, season=2026):
    fold = PS.NflPasses(season)
    fold.add(_pass(season=str(season), passer_player_id=ALLEN, passer_player_name="J.Allen",
                   passing_yards="12"))
    D.upsert_passes(conn, fold.rows(NAMES, {}))


def _one_kick(conn, season=2026):
    """One field goal, so the kicker chart's table has a row (2026-10-14)."""
    from engine import kicks as KK
    fold = KK.NflKicks(season)
    fold.add({"play_type": "field_goal", "season": str(season), "season_type": "REG", "week": "5",
              "home_team": "LA", "away_team": "BUF", "posteam": "BUF", "defteam": "LA",
              "game_date": f"{season}-10-12", "field_goal_attempt": "1", "field_goal_result": "made",
              "kick_distance": "40", "kicker_player_id": "00-0036000", "kicker_player_name": "T.Bass",
              "play_id": "77"})
    D.upsert_kicks(conn, fold.rows({}))


def _one_carry(conn, season=2026):
    fold = CR.NflCarries(season)
    fold.add(_run(season=str(season)))
    D.upsert_carries(conn, fold.rows(NAMES))


def _one_target(conn, season=2026):
    fold = TG.NflTargets(season)
    fold.add(_pass(season=str(season)))
    D.upsert_targets(conn, fold.rows(NAMES, {}, {}))


# --- what is owed -------------------------------------------------------------
def test_a_season_played_with_no_chart_rows_is_owed_and_nothing_else_is():
    conn = D.connect(":memory:")
    assert CF.owed(conn, TODAY) == [], "a database with no games owes nothing (a clone, a test)"
    _game(conn, "nfl", 2026, "2026_05_BUF_LA")
    _game(conn, "nfl", 2025, "2025_10_DET_WAS", date="2025-11-09")
    _game(conn, "cfb", 2026, "401752000")
    _game(conn, "cfb", 2025, "401700000", score=None, date="2025-09-01")   # never finished
    # The passing chart's table and the college target chart's rows
    # (2026-10-13), and the kicker chart's (2026-10-14), are owed like the
    # others.
    assert CF.owed(conn, TODAY) == [("nfl", 2026, "carries"), ("nfl", 2026, "targets"),
                                    ("nfl", 2026, "passes"), ("nfl", 2026, "kicks"),
                                    ("cfb", 2026, "carries"), ("cfb", 2026, "targets"),
                                    ("nfl", 2025, "carries"), ("nfl", 2025, "targets"),
                                    ("nfl", 2025, "passes"), ("nfl", 2025, "kicks")]
    _one_carry(conn)
    _one_target(conn, 2025)
    _one_throw(conn, 2025)
    assert CF.owed(conn, TODAY) == [("nfl", 2026, "targets"), ("nfl", 2026, "passes"),
                                    ("nfl", 2026, "kicks"), ("cfb", 2026, "carries"),
                                    ("cfb", 2026, "targets"), ("nfl", 2025, "carries"),
                                    ("nfl", 2025, "kicks")], \
        "a table with rows is never owed"
    # January is still last autumn's season: 2026 and 2025, not 2027.
    assert CF.season_of(dt.date(2027, 1, 20)) == 2026 and CF.season_of(dt.date(2026, 7, 31)) == 2025

    class Broken:
        def execute(self, *a):
            raise RuntimeError("database is locked")
    assert CF.owed(Broken(), TODAY) == [], "a database that cannot answer owes nothing"


def test_a_baseball_season_with_no_pitches_is_owed_and_one_nights_finals_are_read():
    """The hit tracker and the pitch chart (2026-10-13) fill the same way:
    owed when this season has a final and no pitch is stored, read one
    night's budget of finals (newest first, engine/mlb/charts.backfill),
    and never owed again once a pitch is stored. Football's answer never
    depends on baseball's tables."""
    from engine.mlb.sources import mlbstats, pbp
    conn = D.connect(":memory:")
    assert CF.owed(conn, TODAY) == []
    D.upsert_games(conn, [{"sport": "mlb", "season": 2026, "period": "2026-10-11", "game_id": "776001",
                           "home": "NYY", "away": "DET", "home_score": 4.0, "away_score": 2.0,
                           "date": "2026-10-11"}])
    assert CF.owed(conn, TODAY) == [("mlb", 2026, "mlb_pitches")]
    # Baseball's season is the calendar year; February is still last year's.
    assert CF.mlb_season_of(dt.date(2027, 2, 20)) == 2026 and CF.mlb_season_of(dt.date(2026, 3, 1)) == 2026
    side = lambda tid, ab: {"team": {"id": tid, "abbreviation": ab}}  # noqa: E731
    schedule = {"dates": [{"games": [{"gamePk": 776001, "officialDate": "2026-10-11", "gameType": "D",
                                      "status": {"abstractGameState": "Final", "codedGameState": "F"},
                                      "teams": {"home": side(147, "NYY"), "away": side(116, "DET")}}]}]}
    play = {"result": {"event": "Single", "eventType": "single", "rbi": 0},
            "about": {"atBatIndex": 0, "halfInning": "bottom", "inning": 1},
            "matchup": {"batter": {"id": 592450, "fullName": "Aaron Judge"}, "batSide": {"code": "R"},
                        "pitcher": {"id": 669373, "fullName": "Tarik Skubal"}, "pitchHand": {"code": "L"}},
            "playEvents": [{"isPitch": True, "pitchNumber": 1, "details": {"call": {"code": "D"},
                                                                         "type": {"code": "FF"}},
                            "count": {"balls": 0, "strikes": 0},
                            "pitchData": {"startSpeed": 97.0, "zone": 5, "coordinates": {"pX": 0.1, "pZ": 2.4}},
                            "hitData": {"launchSpeed": 101.0, "launchAngle": 12, "totalDistance": 240,
                                        "trajectory": "line_drive", "coordinates": {"coordX": 150.0, "coordY": 110.0}}}]}
    asked = []
    old = (mlbstats.fetch_schedule, pbp.fetch_playbyplay)
    mlbstats.fetch_schedule = lambda start, end: asked.append((start, end)) or schedule
    pbp.fetch_playbyplay = lambda pk: {"allPlays": [play]}
    try:
        lines = CF.fill(conn, CF.owed(conn, TODAY), log=lambda *_: None)
    finally:
        mlbstats.fetch_schedule, pbp.fetch_playbyplay = old
    assert lines == ["MLB 2026: 1 game, 1 plate appearance, 1 pitch"], lines
    assert asked and asked[0][0] == "2026-03-01", "the whole season's finals are asked for"
    assert CF.owed(conn, TODAY) == [], "a season with a stored pitch is the nightly's from here"


def test_stored_says_whether_anyone_in_the_league_has_a_row():
    conn = D.connect(":memory:")
    assert not CR.stored(conn, "nfl") and not CR.stored(conn, "nfl", table="targets")
    _one_carry(conn)
    assert CR.stored(conn, "nfl") and not CR.stored(conn, "cfb")
    assert not CR.stored(conn, "nfl", table="targets")
    try:
        CR.stored(conn, "nfl", table="games")
        raise AssertionError("only the chart tables")
    except ValueError:
        pass


# --- every cycle, once, then a while -----------------------------------------
def _owing_conn():
    conn = D.connect(":memory:")
    _game(conn, "nfl", 2026, "2026_05_BUF_LA")
    return conn


def test_the_cycle_starts_the_fill_once_and_tries_again_only_after_a_while():
    started, logs = [], []

    def spawn(module, log):
        started.append(module)
        return [f"{module}: started in the background (pid 4242)"]

    td = tempfile.mkdtemp()
    try:
        state = Path(td) / "chartfill.json"
        conn = _owing_conn()
        got = M.fill_charts_if_owed(logs.append, today=TODAY, now=1000.0, conn=conn,
                                    state_path=state, spawn=spawn)
        assert started == ["engine.chartfill"]
        assert got[0] == ("charts: NFL 2026 carries, NFL 2026 targets, NFL 2026 passes, NFL 2026 kicks empty — "
                          "filling now, not with tomorrow's chores")
        assert json.loads(state.read_text())["started"] == 1000.0
        assert json.loads(state.read_text())["owed"] == [["nfl", 2026, "carries"], ["nfl", 2026, "targets"],
                                                         ["nfl", 2026, "passes"], ["nfl", 2026, "kicks"]]
        assert any("pid 4242" in ln for ln in logs)
        # The next cycle, a minute on, while the child reads: not again.
        assert M.fill_charts_if_owed(logs.append, today=TODAY, now=1060.0, conn=conn,
                                     state_path=state, spawn=spawn) == []
        assert started == ["engine.chartfill"]
        # A read that failed is tried again, once the wait is up.
        M.fill_charts_if_owed(logs.append, today=TODAY, now=1000.0 + M.CHART_FILL_EVERY_S + 1,
                              conn=conn, state_path=state, spawn=spawn)
        assert started == ["engine.chartfill"] * 2
        # Filled: nothing starts, nothing is written.
        _one_carry(conn)
        _one_target(conn)
        _one_throw(conn)
        _one_kick(conn)
        state.unlink()
        assert M.fill_charts_if_owed(logs.append, today=TODAY, now=10 ** 9, conn=conn,
                                     state_path=state, spawn=spawn) == []
        assert started == ["engine.chartfill"] * 2 and not state.exists()
    finally:
        shutil.rmtree(td, ignore_errors=True)
    assert 3600 <= M.CHART_FILL_EVERY_S <= 6 * 3600


def test_a_sandbox_never_starts_a_real_fill():
    from engine import modelstate
    keep_env = os.environ.get(modelstate.ENV_VAR)
    keep_spawn = M._spawn_module

    def must_not(*a, **kw):
        raise AssertionError("a test started a real child")
    os.environ[modelstate.ENV_VAR] = tempfile.gettempdir()
    M._spawn_module = must_not
    try:
        assert M.fill_charts_if_owed(lambda *_: None, today=TODAY, now=1.0, conn=_owing_conn(),
                                     state_path=Path(tempfile.gettempdir()) / "never.json") == []
    finally:
        M._spawn_module = keep_spawn
        if keep_env is None:
            os.environ.pop(modelstate.ENV_VAR, None)
        else:
            os.environ[modelstate.ENV_VAR] = keep_env


def test_the_check_never_raises():
    logs = []

    class Broken:
        def execute(self, *a):
            raise RuntimeError("disk I/O error")
    assert M.fill_charts_if_owed(logs.append, today=TODAY, now=1.0, conn=Broken(),
                                 state_path=Path(tempfile.gettempdir()) / "never.json",
                                 spawn=lambda *a: ["started"]) == []


def test_run_if_due_asks_every_cycle_once_the_days_chores_are_done():
    """The pass that returns "already done today" asks — the day the charts
    shipped, those passes were the only ones left. A pass whose chores are
    still to run (or running in another runner) does not: the chores read
    the same plays, and two reads side by side is twice the memory in a
    service capped at 1600 MB."""
    import fcntl
    asked = []
    keep = M.fill_charts_if_owed
    M.fill_charts_if_owed = lambda log=print, **kw: asked.append(kw.get("today")) or []
    td = tempfile.mkdtemp()
    try:
        state = Path(td) / "m.json"
        state.write_text(json.dumps({"last_done": TODAY.isoformat()}))
        assert M.run_if_due(harvest=False, log=lambda *_: None, state_path=state, today=TODAY) is False
        assert asked == [TODAY]
        # Not done today, and another runner holds the chores: no ask.
        state.write_text(json.dumps({"last_done": "2026-10-12"}))
        with open(str(state) + ".lock", "a+") as held:
            fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            assert M.run_if_due(harvest=False, log=lambda *_: None, state_path=state,
                                today=TODAY) is False
        assert asked == [TODAY], "never beside the chores' own read"
    finally:
        M.fill_charts_if_owed = keep
        shutil.rmtree(td, ignore_errors=True)
    src = inspect.getsource(M.run_if_due)
    done = src.index('state.get("last_done") == today.isoformat()')
    assert done < src.index("fill_charts_if_owed(") < src.index("return False", done)


# --- one read ------------------------------------------------------------------
def test_an_owed_nfl_season_is_read_once_for_both_charts():
    from engine.sources import nflpbp
    from engine.sources.fetch import DataUnavailable
    reads = []

    def load(season, columns=None):
        reads.append((season, tuple(columns or ())))
        yield _run(season=str(season))
        yield _pass(season=str(season))

    saved = [(nflpbp, "load_pbp_rows"), (CR, "nfl_names"), (TG, "routes_for"), (TG, "charting_for"),
             (CR, "fetch_ngs_rushing"), (TG, "fetch_ngs_receiving"), (CR, "backfill_cfb"),
             (PS, "charting_for"), (PS, "fetch_ngs_passing")]
    saved = [(o, n, getattr(o, n)) for o, n in saved]
    nflpbp.load_pbp_rows = load
    CR.nfl_names = lambda season: NAMES
    TG.routes_for = lambda season: {}
    TG.charting_for = lambda season: {}
    CR.fetch_ngs_rushing = lambda ttl=0: []
    TG.fetch_ngs_receiving = lambda ttl=0: []
    CR.backfill_cfb = lambda conn, season: 7
    PS.charting_for = lambda season: {}
    PS.fetch_ngs_passing = lambda ttl=0: []
    try:
        conn = D.connect(":memory:")
        lines = []
        CF.fill(conn, [("nfl", 2026, "carries"), ("nfl", 2026, "targets"), ("cfb", 2026, "carries")],
                log=lines.append)
        assert [s for s, _ in reads] == [2026], "one read of the season feeds every chart"
        cols = reads[0][1]
        assert set(CR.PBP_COLS) <= set(cols) and set(TG.PBP_COLS) <= set(cols) and set(PS.PBP_COLS) <= set(cols)
        from engine import kicks as KK
        assert set(KK.PBP_COLS) <= set(cols), "the kicks ride the same read (2026-10-14)"
        # The fixture's pass names no passer, so it is a target and no throw;
        # nobody kicked.
        assert lines == ["NFL 2026: 1 carries, 1 targets, 0 throws, 0 kicks, no route charting published for it yet",
                         "NGS rushing: 0 rows", "NGS receiving: 0 rows", "NGS passing: 0 rows",
                         "CFB 2026: 7 carries, 0 targets"]
        assert CR.chart(conn, "nfl", "Josh Allen")["games"][0]["carries"][0]["y"] == 8.0
        assert TG.chart(conn, "Sam LaPorta")["games"][0]["line"]["yds"] == 12.0

        # A read that fails is a line; the others still run.
        def down(season, columns=None):
            raise DataUnavailable("github.com unreachable")
        nflpbp.load_pbp_rows = down
        lines = []
        CF.fill(D.connect(":memory:"), [("nfl", 2025, "carries"), ("cfb", 2025, "carries")],
                log=lines.append)
        assert lines[0] == "NFL 2025: not read — github.com unreachable"
        assert lines[-1] == "CFB 2025: 7 carries, 0 targets"
    finally:
        for o, n, v in saved:
            setattr(o, n, v)


# --- the page says so ----------------------------------------------------------
def test_the_endpoints_say_filling_when_no_one_has_a_chart_yet():
    import server
    tmp = tempfile.mkdtemp()
    keep = D.DEFAULT_DB
    sent = []
    try:
        path = Path(tmp) / "history.db"
        D.connect(path).close()
        D.DEFAULT_DB = path
        h = object.__new__(server.Handler)
        h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
        h._players_carries({"sport": ["nfl"], "player": ["Josh Allen"]})
        h._players_routes({"sport": ["nfl"], "player": ["Sam LaPorta"]})
        conn = D.connect(path)
        _one_carry(conn)
        _one_target(conn)
        conn.close()
        h._players_carries({"sport": ["nfl"], "player": ["Nobody Here"]})
        h._players_routes({"sport": ["nfl"], "player": ["Nobody Here"]})
        h._players_carries({"sport": ["cfb"], "player": ["Nobody Here"]})
    finally:
        D.DEFAULT_DB = keep
        shutil.rmtree(tmp, ignore_errors=True)
    assert sent[0] == (200, {"filling": True}) and sent[1] == (200, {"filling": True})
    assert sent[2] == (200, {}) and sent[3] == (200, {}), "rows on file: a missing player is just missing"
    assert sent[4] == (200, {"filling": True}), "college has its own table rows to wait for"


def test_the_page_says_the_charts_are_being_filled():
    i = CC_JS.index("function render()")
    body = CC_JS[i:CC_JS.index("const sport = d.sport", i)]
    assert "d.filling" in body and "still being filled" in body
    assert body.index("d.filling") < body.index("No targets on file"), \
        "being filled is said first: it is not the same as none for him"


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
