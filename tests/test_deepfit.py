"""The learning a human had to remember to run.

Three rungs walk the history DB through a sport's own engine — the
recency dial, the per-player memory and the probability temperatures.
They are the strongest fits on the site, and all three take ``--sport``
and DEFAULT TO MLB. So unless somebody typed the flag, only baseball had
ever been deep-fitted. launch.py wrote that down on 2026-08-16, quoting
Ethan — *"i wanna make sure the self learning and all of that shit is
wrapped into nfl too"* — and it stayed true until this module.

It is not a formality. Run against the NFL's 329,434 ingested log rows
for the first time on 2026-08-27, the recency dial moved three of its
four markets, each on more than twenty thousand settled predictions.

Run directly: `python3 tests/test_deepfit.py`
"""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import deepfit as D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _db(counts):
    path = os.path.join(tempfile.mkdtemp(), "h.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, player TEXT)")
    for sport, n in counts.items():
        conn.executemany("INSERT INTO player_game_logs VALUES (?,?)",
                         [(sport, f"p{i}") for i in range(n)])
    conn.commit()
    conn.close()
    return path


def test_the_order_is_dial_then_memory_then_temperature():
    """Load-bearing. The first two MOVE the model the third calibrates,
    so a temperature fitted before them describes a model that no longer
    exists — the exact bug launch.py's refit command was written to fix
    after NFL shipped three adopted dials under stale temperatures."""
    assert [s for _l, s in D.REFIT_ORDER] == ["formfit.py", "playerfit.py",
                                              "calibrate.py"]


def test_only_sports_with_real_history_are_attempted():
    path = _db({"nfl": D.MIN_LOG_ROWS + 10, "mlb": 5, "nba": 0})
    assert D.sports_with_history(path) == ["nfl"]


def test_a_sport_the_fitters_do_not_support_is_never_attempted():
    """UFC prices through its own machinery and has no deep harness:
    it has no game logs at all, so handing it to these CLIs would be an
    argparse error every week, forever.

    CFB LEFT THIS TEST ON 2026-09-04, and the reason it was here is the
    reason it is gone. `--sport` validates against each fitter's own
    SPORT_MARKETS, college was in none of them, so cfb was not a legal
    value to type — and `correction_for("cfb", …)` therefore returned
    the neutral (1.0, 0.0) on every college prop the board priced. Now
    that `engine/cfb/props.py` builds props off the ingested logs, the
    walk runs and the fit is one the CLIs can do."""
    path = _db({"ufc": 500_000})
    assert D.sports_with_history(path) == []


def test_college_is_attempted_once_it_has_the_logs():
    path = _db({"cfb": 500_000})
    assert D.sports_with_history(path) == ["cfb"]


def test_college_still_needs_the_logs_before_it_is_attempted():
    """MIN_LOG_ROWS is what stops a 1-vCPU box walking an empty table."""
    path = _db({"cfb": 5})
    assert D.sports_with_history(path) == []


def test_a_missing_database_is_not_a_crash():
    assert D.sports_with_history("/nonexistent/qb/history.db") == []
    assert D.refit_all("/nonexistent/qb/history.db") == [
        "deep refit: no sport has enough ingested logs yet"]


def test_the_scripts_it_shells_out_to_all_exist():
    """It runs the real CLIs so there is one definition of each fit. That
    only holds if they are where it thinks they are."""
    for _label, script in D.REFIT_ORDER:
        assert os.path.isfile(os.path.join(ROOT, script)), script


def test_every_script_accepts_the_flags_it_is_given():
    for _label, script in D.REFIT_ORDER:
        src = open(os.path.join(ROOT, script), encoding="utf-8").read()
        assert '"--sport"' in src, script
        assert '"--from-db"' in src, script


def test_a_failing_fitter_is_reported_not_swallowed():
    """A weekly job that silently does nothing is the failure this whole
    module exists to end."""
    keep = D.REFIT_ORDER
    D.REFIT_ORDER = (("nonsense", "no_such_script.py"),)
    try:
        lines = D.refit_sport("nfl")
    finally:
        D.REFIT_ORDER = keep
    assert lines and "⚠️" in lines[0] and "failed" in lines[0]


def test_the_run_is_time_bounded():
    """A fitter that has not finished in fifteen minutes has found
    something pathological; a weekly job must not become a permanent
    one."""
    assert 60 <= D.TIMEOUT_S <= 3600
    src = open(os.path.join(ROOT, "engine", "deepfit.py"),
               encoding="utf-8").read()
    assert "timeout=TIMEOUT_S" in src
    assert "TimeoutExpired" in src


def test_the_row_floor_sits_below_every_fitters_own_gate():
    """This floor only avoids spending minutes walking an empty table.
    The decision about what gets ADOPTED belongs to the fitters, which is
    why the schedule can be generous."""
    from engine import formfit, playerfit
    assert D.MIN_LOG_ROWS > 0
    assert formfit.MIN_SAMPLES > 0 and playerfit.MIN_SAMPLES > 0


def test_the_nightly_runs_it_weekly_and_in_a_guard():
    src = open(os.path.join(ROOT, "engine", "maintenance.py"),
               encoding="utf-8").read()
    # Out of process since 2026-09-02: the pass calls `_run_deep_refit`,
    # which spawns `python3 -m engine.deepfit` (its __main__ is
    # refit_all) — the Wednesday it ran in-process it was OOM-killed 223
    # times. The import lives in the child now, not the server.
    assert "from .deepfit import refit_all" not in src
    assert "_run_deep_refit(log)" in src
    import inspect
    from engine import maintenance as _m
    assert "engine.deepfit" in inspect.getsource(_m._run_deep_refit)
    assert "_spawn_module(" in inspect.getsource(_m._run_deep_refit)
    # Weekly, not nightly: this is the slow fit.
    block = src[src.index("The DEEP fitters, weekly"):]
    block = block[:block.index("_run_deep_refit(log)") + 200]
    assert "weekday() == 2" in block
    assert "except Exception" in block
    # Attempted once a day, marked BEFORE it starts.
    assert 'state["deep_attempted"] = today.isoformat()' in block
    assert block.index('state["deep_attempted"]') < block.index("_run_deep_refit(log)")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
