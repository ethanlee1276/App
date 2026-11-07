"""A league at rest sits out the box's heavy nights.

The deep refit's round reaches about one piece a night on the box's one
CPU. On 7 November, MLB and the WNBA, their seasons over, held two of its
seven places, while the NFL, first on every board, still carried its
25 August fit. The Lab replayed MLB first every week, half an hour of the
same CPU, on a season with no new games. Ethan's rule for the odds credits
(28 October: "whatever other sport is not being played needs to be taken
out of the credit pool") holds for the CPU too. What these hold:

  * a league rests when it is out of season and stays out for the next
    three weeks (`oddsplan.resting`); it comes back three weeks before its
    season, so its models are fitted on everything its last season played
    before the first game is priced; the UFC and any league the table does
    not name never rest;
  * the refit leaves resting pieces out of a new round and takes them out of
    the one under way, saying so; a piece rests when every league it serves
    rests (the NBA's checks with the NBA, the football extras with football;
    the ladder never rests); a round left holding only resting pieces is not
    started for;
  * the Lab replays a resting sport once more only when its last replay came
    before its season ended, then not again until the season comes near.

Run directly: `python3 tests/test_a_league_at_rest_sits_out_the_heavy_nights.py`
"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import deepfit as D                                     # noqa: E402
from engine import lab, oddsplan                                    # noqa: E402

NOV7 = dt.date(2026, 11, 7)
ROWS = {"nfl": 30_000, "cfb": 20_000, "nba": 25_000, "mlb": 40_000, "wnba": 9_000}


# --- the calendar ---------------------------------------------------------------
def test_a_league_rests_out_of_season_and_comes_back_three_weeks_before_it():
    assert oddsplan.resting("mlb", NOV7) and oddsplan.resting("wnba", NOV7)
    assert not oddsplan.resting("nfl", NOV7) and not oddsplan.resting("nba", NOV7)
    opening = dt.date(2027, 3, 25)
    assert oddsplan.resting("mlb", opening - dt.timedelta(days=22))
    assert not oddsplan.resting("mlb", opening - dt.timedelta(days=21)), "back three weeks before opening day"
    assert not oddsplan.resting("mlb", dt.date(2026, 7, 4))
    assert oddsplan.resting("nba", dt.date(2026, 7, 4)), "the NBA in July"
    assert oddsplan.resting("nba", dt.date(2026, 9, 28)) and not oddsplan.resting("nba", dt.date(2026, 9, 29))
    assert oddsplan.resting("nfl", dt.date(2027, 3, 1)) and not oddsplan.resting("nfl", dt.date(2026, 8, 13))
    assert not any(oddsplan.resting("ufc", dt.date(2026, m, 15)) for m in range(1, 13)), "the UFC never rests"
    assert not oddsplan.resting("xfl", NOV7), "a league the table does not name is never skipped"


def test_the_day_a_season_ended():
    assert oddsplan.season_ended("mlb", NOV7) == dt.date(2026, 11, 4)
    assert oddsplan.season_ended("wnba", NOV7) == dt.date(2026, 10, 20)
    assert oddsplan.season_ended("nfl", NOV7) == NOV7, "in season: today"
    assert oddsplan.season_ended("xfl", NOV7) is None


# --- the deep refit -----------------------------------------------------------------
def test_a_piece_rests_with_every_league_it_serves():
    every = ["nfl", "cfb", *D.NBA_CHECKS, "nba", "mlb", "wnba", *D.EXTRAS]
    assert D.resting_pieces(every, NOV7) == ["mlb", "wnba"]
    march = D.resting_pieces(every, dt.date(2027, 3, 1))
    assert set(march) == {"nfl", "cfb", "mlb", "wnba", "yardage_mixture", "td_scale", "touchdowns",
                          "cfb_touchdowns", "nfl_props"}, march
    july = D.resting_pieces(every, dt.date(2026, 7, 4))
    assert set(july) == {*D.NBA_CHECKS, "nba", "nfl", "cfb", "yardage_mixture", "td_scale", "touchdowns",
                         "cfb_touchdowns", "nfl_props"}, july
    assert "ladder" not in march + july, "the ladder serves every sport and never rests"
    assert "yardage_mixture" not in D.resting_pieces(["yardage_mixture"], dt.date(2026, 12, 20)), \
        "college's bowls keep football's extras awake"


def test_a_new_round_leaves_the_resting_leagues_out():
    owed = D.round_pieces({}, ROWS, NOV7)
    assert "mlb" not in owed and "wnba" not in owed, owed
    assert owed[:2] == ["nfl", "cfb"] and "nba" in owed and "ladder" in owed, owed
    assert "mlb" in D.round_pieces({}, ROWS), "no date given: every sport, as before"


def _clock():
    t = {"now": 0.0}
    return (lambda: t["now"]), t


def test_a_round_under_way_gives_up_its_resting_pieces_and_says_so():
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "deepfit_state.json"
    path.write_text(json.dumps({"round": "2026-11-04", "left": ["nfl", "mlb", "wnba", "ladder"],
                                "pieces": {}}))
    keep = D._row_counts
    D._row_counts = lambda db="data/history.db": dict(ROWS)
    clock, t = _clock()
    ran = []

    def run_piece(p, db, deadline, say):
        ran.append(p)
        t["now"] += 60
        return [f"{p} ran"], True
    try:
        lines = D.run_round(db="unused", state_path=path, today=NOV7, clock=clock, run_piece=run_piece)
    finally:
        D._row_counts = keep
    assert ran == ["nfl", "ladder"], ran
    said = [ln for ln in lines if "at rest" in ln]
    assert said and "mlb, wnba" in said[0] and "21 days before the season" in said[0], lines
    st = json.loads(path.read_text())
    assert st["left"] == [] and any("complete" in ln for ln in lines), (st, lines)


def test_a_round_holding_only_resting_pieces_is_not_started_for():
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "deepfit_state.json"
    path.write_text(json.dumps({"round": "2026-11-04", "left": ["mlb", "wnba"], "pieces": {}}))
    assert not D.due(path, NOV7), "nothing owed that is not at rest"
    path.write_text(json.dumps({"round": "2026-11-04", "left": ["mlb", "nfl"], "pieces": {}}))
    assert D.due(path, NOV7)
    path.write_text(json.dumps({"round": "2026-10-28", "left": ["mlb"], "pieces": {}}))
    assert D.due(path, NOV7), "this week's round never began: still due, as before"


def test_a_broken_calendar_rests_nothing():
    keep = oddsplan.resting

    def torn(*_a, **_k):
        raise RuntimeError("a torn season table")
    oddsplan.resting = torn
    try:
        assert D.resting_pieces(["mlb", "nfl"], NOV7) == []
        assert not lab._replay_still_holds("mlb", dt.date(2026, 11, 5), NOV7)
    finally:
        oddsplan.resting = keep


# --- the Lab -----------------------------------------------------------------
def _page(stamps: dict) -> dict:
    return {"generated_at": "2026-11-06T01:00:00",
            "sports": {sp: {"replayed_at": f"{d}T01:00:00", "props": {"markets": {"m": {}}}}
                       for sp, d in stamps.items()}}


def test_the_lab_replays_a_resting_sport_once_after_its_season():
    stamps = {"mlb": "2026-11-05", "nfl": "2026-10-30", "cfb": "2026-11-06", "nba": "2026-11-06",
              "wnba": "2026-10-10", "ufc": "2026-10-30"}
    owed = lab.due_sports(_page(stamps), NOV7)
    assert "mlb" not in owed, "replayed after its last game: nothing new to replay"
    assert "wnba" in owed, "its last replay came before its season ended: the final games are owed"
    assert {"nfl", "ufc"} <= set(owed) and not {"cfb", "nba"} & set(owed), owed
    stamps["mlb"] = "2026-10-20"
    assert "mlb" in lab.due_sports(_page(stamps), NOV7), "a replay from before the World Series ended"
    stamps["mlb"] = "2026-11-05"
    assert "mlb" in lab.due_sports(_page(stamps), dt.date(2027, 3, 10)), "three weeks out: weekly again"


# --- the owner's desk: a date kept on purpose is not late --------------------------
def test_the_desk_marks_a_sport_at_rest_and_its_alert_stays_quiet():
    import os
    import time
    os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())
    from engine import owneralerts as OA
    from engine import ownerdesk as OD
    d = Path(tempfile.mkdtemp())
    (d / "data" / "built").mkdir(parents=True)
    (d / "web" / "data").mkdir(parents=True)
    page = _page({"mlb": "2026-11-05", "nfl": "2026-11-01", "wnba": "2026-10-10"})
    (d / "data" / "built" / "backtest.json").write_text(json.dumps(page), encoding="utf-8")
    now = time.mktime((2026, 11, 7, 12, 0, 0, 0, 0, -1))
    w = OD.weekly(now=now, jobs={}, deep_path=d / "none.json", lab_path=d / "web" / "data" / "backtest.json",
                  attempts_path=d / "tried.json")
    rest = {x["sport"]: x["resting"] for x in w["lab"]["sports"]}
    assert rest["mlb"] is True, "replayed after its last game"
    assert rest["wnba"] is False and rest["nfl"] is False, rest
    late_mlb = {"lab": {"sports": [{"sport": "mlb", "replayed": "2026-09-01", "resting": True}]}}
    assert not [p for p in OA.problems({"weekly": late_mlb}, now=now) if p["key"] == "lab"], \
        "a sport at rest keeps its date on purpose: no alert all winter"
    both = {"lab": {"sports": [{"sport": "mlb", "replayed": "2026-09-01", "resting": True},
                               {"sport": "nfl", "replayed": "2026-10-20"}]}}
    got = [p for p in OA.problems({"weekly": both}, now=now) if p["key"] == "lab"]
    assert got and "NFL" in got[0]["title"] and "MLB" not in got[0]["body"], got
    js = (ROOT / "web" / "js" / "owner.js").read_text(encoding="utf-8")
    assert 'const late = !x.resting && (age == null' in js and '${x.resting ? " · at rest" : ""}' in js


def test_the_desks_refit_card_names_the_leagues_at_rest_and_owes_them_nothing():
    """Until the night's run takes them out, the box's round still lists MLB
    and the WNBA: the card neither counts them as owed nor alerts on their
    August fits."""
    import os
    import time
    os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())
    from engine import owneralerts as OA
    from engine import ownerdesk as OD
    d = Path(tempfile.mkdtemp())
    deep = d / "deepfit_state.json"
    deep.write_text(json.dumps({"round": "2026-11-04", "left": ["nfl", "mlb", "wnba"],
                                "pieces": {"nfl": {"done": "2026-08-25"}, "mlb": {"done": "2026-08-20"},
                                           "wnba": {"done": "2026-08-20"}}}), encoding="utf-8")
    now = time.mktime((2026, 11, 7, 12, 0, 0, 0, 0, -1))
    w = OD.weekly(now=now, jobs={}, deep_path=deep, lab_path=d / "none.json", attempts_path=d / "tried.json",
                  fit_paths=[])
    dp = w["deep"]
    assert dp["left"] == ["nfl"] and dp["resting"] == ["mlb", "wnba"], dp
    assert set(dp["last_done"]) == {"nfl"}, dp
    got = [p for p in OA.problems({"weekly": {"deep": dp}}, now=now) if p["key"] == "deepfit"]
    assert got and "NFL" in got[0]["title"] and "MLB" not in got[0]["body"], got
    js = (ROOT / "web" / "js" / "owner.js").read_text(encoding="utf-8")
    assert 'odRow("At rest (out of season)", dp.resting.map(odPiece)' in js


# --- the sweep: a board at rest rebuilds every six hours ---------------------------
def _launch_with_board(age_h: float):
    import os
    import time
    os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())
    import launch as L
    p = Path(tempfile.mkdtemp()) / "mlb_recommendations.json"
    p.write_text(json.dumps({"games": [], "most_likely": []}), encoding="utf-8")
    t = time.time() - age_h * 3600
    os.utime(p, (t, t))
    return L, p


def test_the_sweep_leaves_a_resting_leagues_board_until_it_is_six_hours_old():
    """7 November: the MLB board took about three minutes of every sweep for a
    slate with no games."""
    L, p = _launch_with_board(1.0)
    keep = dict(L.BOARD_FILES), L._slate_date
    try:
        L.BOARD_FILES["mlb"] = str(p)
        L._slate_date = lambda: "2026-11-07"
        assert L._resting_board("mlb"), "an hour old, at rest: left as it is"
        import os
        import time
        old = time.time() - (L.REST_REBUILD_S + 60)
        os.utime(p, (old, old))
        assert not L._resting_board("mlb"), "six hours old: rebuilt"
        L.BOARD_FILES["nfl"] = str(p)
        assert not L._resting_board("nfl"), "in season: every sweep"
        L.BOARD_FILES["mlb"] = str(p) + ".missing"
        assert not L._resting_board("mlb"), "no board: built"
        L.BOARD_FILES["mlb"] = str(p)
        L._slate_date = lambda: "2027-03-10"
        os.utime(p, (time.time(), time.time()))
        assert not L._resting_board("mlb"), "three weeks before opening day: every sweep"
    finally:
        L.BOARD_FILES.clear()
        L.BOARD_FILES.update(keep[0])
        L._slate_date = keep[1]


def test_a_kept_board_reads_off_season_never_stale():
    L, p = _launch_with_board(5.0)
    keep = dict(L.BOARD_FILES), L._BOARD_RUNS.pop("mlb", None)
    try:
        L.BOARD_FILES["mlb"] = str(p)
        L._note_rest("mlb")
        rec = L._BOARD_RUNS["mlb"]
        assert rec["offseason"] and rec["resting"] and rec["stale"] is False, rec
        assert 4.9 < rec["age_h"] < 5.1 and rec["ok"] is True and rec["most_likely"] == 0, rec
        rec["at"] = "2026-11-07T08:00:00"                 # the last build's record is kept
        L._note_rest("mlb")
        assert L._BOARD_RUNS["mlb"]["at"] == "2026-11-07T08:00:00"
    finally:
        L.BOARD_FILES.clear()
        L.BOARD_FILES.update(keep[0])
        L._BOARD_RUNS.pop("mlb", None)
        if keep[1] is not None:
            L._BOARD_RUNS["mlb"] = keep[1]


def test_every_league_board_in_the_sweep_asks_first():
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    body = src[src.index("def refresh_all("):src.index('lap("ufc")')]
    for lg in ("nfl", "cfb", "mlb", "nba", "wnba", "nhl"):
        ask, build = f'if _resting_board("{lg}"):', f'_note_board("{lg}", refresh_{lg}(quiet=quiet))'
        assert ask in body and build in body and body.index(ask) < body.index(build), lg
        assert f'_note_rest("{lg}")' in body, lg


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
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
