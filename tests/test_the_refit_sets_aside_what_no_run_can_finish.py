"""The weekly refit learns each piece's own time and sets aside what no run
can finish (engine/deepfit.run_round, _refit_sport).

Ethan's catch-up, 6 November: the round of 4 November owed nine pieces after
two days; the NBA's teammate-out check had never finished (it was started on
a ten-minute guess with half an hour left, and ran out), and the NBA's own
fitters wait on every NBA check, so their alternate-line correction was
still dated 17 October. What these hold:

  * a check cut off by the clock is never started again with less time than
    it already ran, except as a run's first piece;
  * a check that ran the most a run can give and did not finish is set aside
    for the round, named in the round's line, and what waited on it goes
    ahead the next run;
  * a sport's fitter that starts over each time (the player memory, the
    temperatures) and ran its whole time is set aside the same way, the
    sport finishes with the others, and the NBA's switch is not thrown on a
    refit missing one; the recency dial, which keeps what it fitted, is
    still tried again (tests/test_the_refit_resumes_inside_a_sport.py).

Run directly: `python3 tests/test_the_refit_sets_aside_what_no_run_can_finish.py`
"""
import datetime as dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import deepfit as D                                  # noqa: E402
# The round's mechanics, pinned on any date: whether a league at rest sits the
# round out is tests/test_a_league_at_rest_sits_out_the_heavy_nights.py.
D.resting_pieces = lambda pieces, today: []

WED = dt.date(2026, 11, 4)
THU, FRI = WED + dt.timedelta(days=1), WED + dt.timedelta(days=2)


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _state(path):
    return json.loads(path.read_text())


def _round(path, today, clock, run_piece, rows=None):
    keep = D._row_counts
    D._row_counts = lambda db="data/history.db": dict(rows or {"nba": 250_000})
    try:
        return D.run_round(db="unused", state_path=path, today=today, budget_s=D.DEEP_BUDGET_S,
                           clock=clock, run_piece=run_piece)
    finally:
        D._row_counts = keep


def _start(path, left, pieces=None):
    # The NBA checks not named in ``left`` are done this round, so the
    # round's own late-joining rule (deepfit._late_checks) adds none.
    done = {c: {"done": WED.isoformat(), "seconds": 60} for c in D.NBA_CHECKS if c not in left}
    path.write_text(json.dumps({"round": WED.isoformat(), "left": list(left),
                                "pieces": {**done, **(pieces or {})}}))


def test_a_check_cut_off_by_the_clock_waits_for_the_time_it_ran():
    path = Path(tempfile.mkdtemp()) / "deepfit_state.json"
    clock = _Clock()
    # The rules take 20 minutes; the rates (a ten-minute guess) are started
    # after them with 30 left and run out of the run's time.
    _start(path, ["nba_rules", "nba_rates", "nba"])
    ran = []

    def run_piece(p, db, deadline, say):
        ran.append(p)
        if p == "nba_rules":
            clock.t += 20 * 60
            return ["rules ran"], True
        if p == "nba_rates":
            clock.t = deadline                     # the run's time is gone
            return ["rates cut off"], False
        clock.t += 60
        return ["ran"], True
    _round(path, THU, clock, run_piece)
    st = _state(path)
    assert ran == ["nba_rules", "nba_rates"], ran
    assert st["pieces"]["nba_rates"]["min_s"] == 30 * 60, st["pieces"]["nba_rates"]
    assert "too_long" not in st["pieces"]["nba_rates"], "half a run is not the most a run can give"
    assert "nba_rates" in st["left"] and "nba" in st["left"], "the fitters still wait on it"
    # Next run: MLB first (never tried), 25 minutes, then 25 left — not
    # enough for the 36 the rates now need (1.2 x 30), so they are not
    # started half-way again.
    st["left"] = ["mlb"] + st["left"]
    path.write_text(json.dumps(st))
    ran.clear()
    clock2 = _Clock()

    def run_piece2(p, db, deadline, say):
        ran.append(p)
        clock2.t += 25 * 60 if p == "mlb" else 60
        return ["ran"], True
    _round(path, FRI, clock2, run_piece2, rows={"nba": 250_000, "mlb": 900_000})
    assert ran == ["mlb"], ("the rates wait for a run with their time", ran)
    # As a run's first piece they still get their turn, and the fitters follow.
    ran.clear()
    _round(path, FRI + dt.timedelta(days=1), _Clock(), run_piece2)
    assert ran == ["nba_rates", "nba"], ran
    assert "min_s" not in _state(path)["pieces"]["nba_rates"], "a finished check keeps its real time instead"


def test_a_check_that_outgrew_a_whole_run_is_set_aside_and_the_fitters_go_ahead():
    path = Path(tempfile.mkdtemp()) / "deepfit_state.json"
    clock = _Clock()
    _start(path, ["nba_spread", "nba"])
    ran = []

    def run_piece(p, db, deadline, say):
        ran.append(p)
        if p == "nba_spread":
            clock.t += D.DEEP_BUDGET_S                # all of it, and still running
            return ["nba_spread: still running"], False
        clock.t += 60
        return ["nba fitted"], True
    lines = _round(path, THU, clock, run_piece)
    st = _state(path)
    assert ran == ["nba_spread"], "nothing else is started with the run's time gone"
    assert "nba_spread" not in st["left"] and st["left"] == ["nba"], st["left"]
    assert st["pieces"]["nba_spread"]["too_long"]["round"] == WED.isoformat()
    assert any("too long for a run; set aside for this round" in ln for ln in lines), lines
    assert "set aside as too long for a run: nba_spread" in lines[-1], lines[-1]
    clock2 = _Clock()
    ran.clear()
    lines = _round(path, FRI, clock2, run_piece)
    assert ran == ["nba"], ("the NBA's fitters no longer wait on it", ran)
    assert _state(path)["left"] == []
    # A finished check forgets its old measure and its set-aside mark.
    assert "too_long" in _state(path)["pieces"]["nba_spread"], "kept until it finishes a later round"


def test_a_fitter_that_starts_over_and_ran_its_whole_time_is_set_aside_and_the_sport_finishes():
    import time as _t
    now = [10_000.0]
    ran = []

    def fake_run(cmd, **kw):
        script = Path(cmd[1]).name
        ran.append(script)
        if script == "playerfit.py":
            now[0] += kw["timeout"]
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        now[0] += 60
        return subprocess.CompletedProcess(cmd, 0, "  receptions: adopted 0.9\n", "")
    keep_run, keep_mono = subprocess.run, _t.monotonic
    subprocess.run, _t.monotonic = fake_run, (lambda: now[0])
    try:
        told = []
        lines, finished = D._refit_sport("nfl", deadline=now[0] + 2 * D.TIMEOUT_S,
                                         on_done=lambda label, secs, status: told.append((label, status)))
    finally:
        subprocess.run, _t.monotonic = keep_run, keep_mono
    assert ran == ["formfit.py", "playerfit.py", "calibrate.py"], ran
    assert finished, "the sport finishes with its other fitters"
    assert ("player memory", "too_long") in told, told
    assert any("too long for a run; set aside for this round" in ln for ln in lines), lines


def test_the_round_counts_a_set_aside_fitter_as_done_for_the_round():
    path = Path(tempfile.mkdtemp()) / "deepfit_state.json"
    _start(path, ["nfl", "nfl_props"])
    keep_rows, keep_run = D._row_counts, D._refit_sport
    D._row_counts = lambda db="data/history.db": {"nfl": 330_000}

    def fake_sport(sport, db, say=None, deadline=None, skip=(), on_done=None, **kw):
        on_done("recency dial", 60, "ok")
        on_done("player memory", 2700, "too_long")
        on_done("temperatures", 60, "ok")
        return ["nfl fitted, the memory set aside"], True
    D._refit_sport = fake_sport
    try:
        D.run_round(db="unused", state_path=path, today=THU, budget_s=D.DEEP_BUDGET_S,
                    run_piece=None)
    finally:
        D._row_counts, D._refit_sport = keep_rows, keep_run
    st = _state(path)
    assert st["pieces"]["nfl"]["done"] == THU.isoformat(), st["pieces"]["nfl"]
    assert "nfl" not in st["left"], "and what waited on the NFL (its props' book-line fit) can go"


def test_the_nba_switch_is_not_thrown_on_a_refit_missing_a_fitter():
    src = (ROOT / "engine" / "deepfit.py").read_text(encoding="utf-8")
    i = src.index('if (label not in RESUMES and bound >= TOO_LONG_SHARE * TIMEOUT_S')
    block = src[i:i + 1200]
    assert "clean = False" in block, "a refit missing a fitter never throws the NBA's switch"
    assert D.RESUMES == ("recency dial",)
    assert D.NBA_CHECK_GUESS_S["nba_vacancy"] >= 30 * 60, "the box's own time for that much replay"


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
