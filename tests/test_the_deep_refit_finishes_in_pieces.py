"""The deep refit finishes in pieces: a weekly round of pieces, begun on
Wednesday and continued day by day, each run stopping itself inside the
chores' hour (engine/deepfit.run_round, engine/maintenance._deep_due).

The 3 November audit of the learning loop: the Record page's own dates had
the NFL's recency dial last fitted 25 August and its player memory 29
August, MLB's dial 1 September, college's memory 28 October. `refit_all`
walked college, MLB, NBA, NFL and the WNBA and then the extras in one
Wednesday child, and the chores' reaper kills a weekly child past the hour
(maintenance.WEEKLY_JOB_TIMEOUT_S, since 2 September), so every Wednesday
it died in MLB and never reached the NFL, the touchdown fits, the NFL
props' refit against book lines or the conviction ladder. What these hold:

  * a run cut off part way keeps every piece it finished, and the pieces
    it did not reach stay owed for the next run;
  * the piece a run was cut off in goes to the back of the line, and the
    next run finishes the round;
  * a new round owes every extra, and every sport whose history has grown
    since its last full fit — never one with nothing new (out of season);
  * a piece waits while a piece it builds on is still owed;
  * no piece starts without the time it needs, except a run's first, and a
    sport's fitters are bounded by what is left of the run;
  * the chores start the job on another day only while the round owes a
    run, once a day, marked before it starts, and never the Wednesday-only
    scouts; with no round on record they wait for Wednesday.

Run directly: `python3 tests/test_the_deep_refit_finishes_in_pieces.py`
"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import deepfit as D                                  # noqa: E402
from engine import maintenance                                   # noqa: E402

WED = dt.date(2026, 11, 4)
THU = WED + dt.timedelta(days=1)
ROWS = {"cfb": 400_000, "mlb": 900_000, "nba": 250_000, "nfl": 330_000, "wnba": 60_000}


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class _Killed(BaseException):
    """What the reaper does at the hour: not an error the run can catch."""


def _with_rows(rows):
    keep = D._row_counts
    D._row_counts = lambda db="data/history.db": dict(rows)
    return keep


def _pieces(clock, cost=None, kill_at=None, unfinished=()):
    """A stand-in for one piece: costs `cost[p]` seconds of the clock."""
    ran = []
    cost = cost or {}

    def run_piece(p, db, deadline, say):
        ran.append(p)
        if kill_at is not None and len(ran) == kill_at:
            raise _Killed()
        clock.t += cost.get(p, 60)
        return [f"{p} ran"], p not in unfinished
    return run_piece, ran


def _state(tmp):
    return json.loads((tmp / "deepfit_state.json").read_text())


def _round(tmp, today, clock, run_piece, budget=D.DEEP_BUDGET_S):
    return D.run_round(db="unused", state_path=tmp / "deepfit_state.json", today=today,
                       budget_s=budget, clock=clock, run_piece=run_piece)


def test_a_run_cut_off_part_way_keeps_every_piece_it_finished():
    tmp, clock = Path(tempfile.mkdtemp()), _Clock()
    keep = _with_rows(ROWS)
    try:
        run_piece, ran = _pieces(clock, kill_at=3)
        try:
            _round(tmp, WED, clock, run_piece)
            raise AssertionError("the stand-in was meant to be cut off")
        except _Killed:
            pass
        assert ran == ["nfl", "cfb", "nba"], "football first, then the rest, stalest first"
        st = _state(tmp)
        assert st["round"] == "2026-11-04"
        assert st["pieces"]["nfl"]["done"] == "2026-11-04" and st["pieces"]["cfb"]["done"] == "2026-11-04"
        assert st["pieces"]["nfl"]["rows"] == ROWS["nfl"], "what the fit read, to judge the next round by"
        assert "done" not in st["pieces"]["nba"] and st["pieces"]["nba"]["attempted"] == "2026-11-04"
        assert "nfl" not in st["left"] and "cfb" not in st["left"] and "nba" in st["left"]
        assert D.due(tmp / "deepfit_state.json", THU), "a round with pieces left owes the next day a run"
    finally:
        D._row_counts = keep


def test_the_cut_off_piece_goes_to_the_back_and_the_next_run_finishes_the_round():
    tmp, clock = Path(tempfile.mkdtemp()), _Clock()
    keep = _with_rows(ROWS)
    try:
        run_piece, _ = _pieces(clock, kill_at=3)
        try:
            _round(tmp, WED, clock, run_piece)
        except _Killed:
            pass
        run_piece, ran = _pieces(clock)
        lines = _round(tmp, THU, clock, run_piece)
        assert ran[-1] == "nba", ("the piece the hour ran out in waits behind the rest", ran)
        assert ran[:3] == ["mlb", "wnba", "yardage_mixture"], ran
        assert _state(tmp)["left"] == [] and not D.due(tmp / "deepfit_state.json", THU)
        assert lines[-1].startswith("deep refit: round of 2026-11-04 complete"), lines[-1]
    finally:
        D._row_counts = keep


def test_what_a_new_round_owes():
    st = {"pieces": {"mlb": {"done": "2026-10-28", "rows": ROWS["mlb"]},
                     "nfl": {"done": "2026-10-28", "rows": ROWS["nfl"] - 4_000}}}
    owed = D.round_pieces(st, ROWS)
    assert "mlb" not in owed, "nothing new since its last full fit: out of season, nothing to refit"
    assert "nfl" in owed, "last week's games landed: refit"
    assert all(x in owed for x in D.EXTRAS), "every extra, every week"
    assert owed.index("td_scale") < owed.index("touchdowns") and owed[-1] == "ladder"
    assert D.round_pieces({}, {}) == [], "no history, nothing owed"
    # A sport the fitters' own table gains joins the round with no second
    # list to remember: after the named sports, before the extras.
    grown = D.round_pieces({}, dict(ROWS, nhl=120_000))
    assert "nhl" in grown and grown.index("nhl") > grown.index("wnba") and grown.index("nhl") < grown.index("yardage_mixture")


def test_a_piece_waits_while_what_it_builds_on_is_owed():
    tmp, clock = Path(tempfile.mkdtemp()), _Clock()
    keep = _with_rows({"nfl": ROWS["nfl"]})
    try:
        (tmp / "deepfit_state.json").write_text(json.dumps({
            "round": "2026-11-04", "left": ["nfl_props", "nfl"],
            "pieces": {"nfl": {"attempted": "2026-11-04"}}}))
        run_piece, ran = _pieces(clock)
        _round(tmp, THU, clock, run_piece)
        assert ran == ["nfl", "nfl_props"], ("the props' book-line fit is the last word over the NFL's own", ran)
    finally:
        D._row_counts = keep


def test_no_piece_starts_without_the_time_it_needs_except_a_runs_first():
    tmp, clock = Path(tempfile.mkdtemp()), _Clock()
    keep = _with_rows(ROWS)
    try:
        # NFL takes 47 of the 50 minutes; nothing else fits behind it.
        run_piece, ran = _pieces(clock, cost={"nfl": 47 * 60})
        _round(tmp, WED, clock, run_piece)
        assert ran == ["nfl"], ran
        # Next run, a piece whose own last run took longer than the whole
        # budget still gets its turn as the run's first piece.
        st = _state(tmp)
        st["pieces"]["cfb"] = {"seconds": 99 * 60}
        (tmp / "deepfit_state.json").write_text(json.dumps(st))
        run_piece, ran = _pieces(clock)
        _round(tmp, THU, clock, run_piece)
        assert ran and ran[0] == "cfb", ran
    finally:
        D._row_counts = keep


def test_a_sports_fitters_are_bounded_by_what_is_left_of_the_run():
    import subprocess
    seen = []
    keep = subprocess.run

    def fake_run(cmd, **kw):
        seen.append(kw.get("timeout"))
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
    subprocess.run = fake_run
    try:
        import time
        lines, finished = D._refit_sport("nfl", deadline=time.monotonic() + 120)
    finally:
        subprocess.run = keep
    assert seen and seen[0] <= 120, seen
    assert not finished and any("left for the next" in ln or "skipped" in ln for ln in lines), lines


def test_due_reads_the_round():
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "deepfit_state.json"
    assert not D.due(path, THU), "no round on record: wait for Wednesday"
    path.write_text(json.dumps({"round": "2026-11-04", "left": []}))
    assert not D.due(path, THU), "this week's round is done"
    path.write_text(json.dumps({"round": "2026-10-28", "left": []}))
    assert D.due(path, THU), "this week's never began (a Wednesday the box was down)"
    assert D.round_start(dt.date(2026, 11, 3)) == dt.date(2026, 10, 28)
    assert D.round_start(WED) == WED
    assert Path(D.STATE_PATH).parent == Path(maintenance.STATE_PATH).parent, "beside the chores' own state"


def _quiet(monkeypatch_set):
    from engine import db, ingest, ledger
    monkeypatch_set(ingest, "ingest_mlb_results",
                    lambda conn, start, end, with_logs=True, progress=None:
                    {"games": 0, "player_logs": 0, "skipped": []})
    monkeypatch_set(ledger, "settle_from_history", lambda c, h, sport=None: 0)
    monkeypatch_set(ledger, "connect", lambda path=None: None)
    monkeypatch_set(db, "connect", lambda path=None: None)


def test_the_chores_continue_the_round_on_other_days_once():
    import test_maintenance as TM
    keep = []

    def setattr_(obj, name, value):
        keep.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    class _MP:
        setattr = staticmethod(setattr_)
    calls = []
    try:
        _quiet(setattr_)
        TM._no_feeds(_MP)
        # Every other job the chores can start, stubbed: a test about one
        # job's schedule must never start a real one (Thursday is the
        # inventions', and the bug scan is daily outside the suite's sandbox).
        for seam in ("_run_inventions", "_run_bugscan", "_run_nflrefs", "_run_lab"):
            setattr_(maintenance, seam, lambda log: [])
        setattr_(maintenance, "_run_board_learning", lambda lconn, hconn, log: [])
        setattr_(maintenance, "_run_deep_refit", lambda log: calls.append(("wednesday", None)) or [])

        def cont(log):
            calls.append(("continue", json.loads(state.read_text()).get("deep_attempted")))
            return []
        setattr_(maintenance, "_continue_deep_refit", cont)
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "m.json"
            deep = Path(td) / "deepfit_state.json"
            # A Thursday with no round on record: nothing.
            maintenance.run_if_due(harvest=False, log=lambda *_: None, state_path=state, today=THU)
            assert calls == []
            # A Thursday whose round has pieces left: the next run, marked first.
            deep.write_text(json.dumps({"round": "2026-11-04", "left": ["ladder"]}))
            maintenance.run_if_due(force=True, harvest=False, log=lambda *_: None, state_path=state,
                                   today=THU)
            assert calls == [("continue", "2026-11-05")], calls
            # Once a day, even when the chores run again.
            maintenance.run_if_due(force=True, harvest=False, log=lambda *_: None, state_path=state,
                                   today=THU)
            assert calls == [("continue", "2026-11-05")], calls
            # Wednesday is the whole spawn, scouts and all — not the continuation.
            maintenance.run_if_due(force=True, harvest=False, log=lambda *_: None, state_path=state,
                                   today=WED + dt.timedelta(days=7))
            assert calls[-1] == ("wednesday", None), calls
    finally:
        for obj, name, value in reversed(keep):
            setattr(obj, name, value)


def test_the_continuation_spawns_the_fitters_alone_and_the_job_says_where_it_is():
    import inspect
    body = inspect.getsource(maintenance._continue_deep_refit)
    assert '_spawn_module("engine.deepfit", log)' in body and "scouthist" not in body
    src = (ROOT / "engine" / "deepfit.py").read_text(encoding="utf-8")
    main = src[src.index('if __name__ == "__main__":'):]
    assert "run_round(say=lambda l: print(l, flush=True))" in main, "flushed, so the reaper's last line is current"
    assert '"--all"' in main and "refit_all()" in main, "the whole refit, by hand"
    assert D.DEEP_BUDGET_S < maintenance.WEEKLY_JOB_TIMEOUT_S, "the run stops itself before the reaper does"


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tests"))
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
