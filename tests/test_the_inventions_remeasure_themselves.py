"""The inventions are measured again every week, so one that holds joins Most Likely and Edge on its own.

Ethan, 2026-10-22: "Are all of our new data and changes being pushed to the
most likely bets too bc it should be. And the edge bets." Each invention
moves Most Likely and Edge the moment its saved verdict holds
(engine/ideagate) — and the verdicts were saved by hand once, a third of a
season in, and never again. engine/inventionfit runs each measurement with
--save, one at a time in its own process, every Thursday from
engine/maintenance.

What these hold: every gate has its measurement and nothing extra rides
along; no run reaches the network (no backfill) or overwrites one sport's
verdict with another's; one that fails or runs long is a line and the rest
still run; the hour's budget stops new starts; and nothing starts in the
test sandbox.

Run directly: `python3 tests/test_the_inventions_remeasure_themselves.py`
"""
import io
import os
import sys
import tempfile
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ideagate as G                                   # noqa: E402
from engine import inventionfit as I                               # noqa: E402
from engine import maintenance as M                                # noqa: E402


def test_every_gate_is_measured_and_nothing_else():
    names = [n for n, _cmd in I.JOBS]
    assert len(names) == len(set(names))
    gates = {n for n, *_x in G.GATES}
    assert gates <= set(names), gates - set(names)
    assert set(names) - gates == {"vacancy"}, "the NBA vacancy is the one measured outside the gates"
    assert not {n for n, *_x in G.NEVER} & set(names), "never a number, by design: nothing to measure"
    for name, mod, *_x in G.GATES:
        cmd = dict(I.JOBS)[name]
        assert f"engine.{mod}" in cmd, (name, cmd)
        assert "--save" in cmd, name


def test_no_run_reaches_the_network_or_crosses_sports():
    for name, cmd in I.JOBS:
        assert "--backfill" not in cmd, f"{name}: a backfill fetches (attention's is Wikipedia)"
        if "--sport" in cmd:
            assert cmd[cmd.index("--sport") + 1] == "nfl", f"{name}: only the sport run by hand"
    # playsim keeps one verdict for every sport: a college run would replace the NFL's.
    sims = [cmd for _n, cmd in I.JOBS if "engine.playsim" in cmd]
    assert sims == [("-m", "engine.playsim", "--sport", "nfl", "--save")]


def test_one_that_fails_is_a_line_and_the_rest_still_run():
    ran = []

    def runner(cmd):
        ran.append(cmd)
        if "engine.bookmenu" in cmd:
            return "failed (code 1)", ["Traceback", "ValueError: nothing stored"]
        return "ok", [f"line {i}" for i in range(20)] + ["THE BAR — does not hold"]

    out = io.StringIO()
    with redirect_stdout(out):
        got = I.run(runner=runner)
    assert len(ran) == len(I.JOBS)
    assert got["menu"] == "failed (code 1)" and got["practice"] == "ok"
    text = out.getvalue()
    assert "menu: failed (code 1)" in text and "ValueError: nothing stored" in text
    assert "THE BAR — does not hold" in text and "line 13" not in text, "each keeps only its last lines"


def test_the_hours_budget_stops_new_starts():
    clock = {"t": 0.0}

    def runner(cmd):
        clock["t"] += 20 * 60
        return "ok", []

    said = []
    got = I.run(runner=runner, now=lambda: clock["t"], say=said.append)
    started = [n for n, v in got.items() if v == "ok"]
    assert len(started) == 3, got
    assert all(v == "not started" for n, v in got.items() if n not in started)
    assert any("it runs next week" in s for s in said)


def test_the_real_runner_reports_a_failure_and_a_long_run():
    status, lines = I._run_one(("-c", "import sys; print('hello'); sys.exit(3)"))
    assert status == "failed (code 3)" and lines[:1] == ["hello"]
    keep = I.JOB_TIMEOUT_S
    try:
        I.JOB_TIMEOUT_S = 1
        status, _l = I._run_one(("-c", "import time; time.sleep(5)"))
    finally:
        I.JOB_TIMEOUT_S = keep
    assert status.startswith("cut off")


def test_nothing_starts_in_the_sandbox():
    assert os.environ.get("QB_MODELS_DIR")
    keep = M._spawn_module

    def must_not(*a, **k):
        raise AssertionError("a real measurement was started in the test sandbox")
    try:
        M._spawn_module = must_not
        assert M._run_inventions(print) == ["engine.inventionfit: not started in the sandbox"]
    finally:
        M._spawn_module = keep


def test_the_list_names_every_job():
    out = io.StringIO()
    with redirect_stdout(out):
        assert I.main(["--list"]) == 0
    text = out.getvalue()
    for name, cmd in I.JOBS:
        assert f"python3 {' '.join(cmd)}" in text


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
