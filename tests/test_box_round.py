"""research/box_round.py: the lab's box runs in one command, and never a holdout.

Ethan: "tell me what to run i dont wanna have to search the runbook". The
round runs runbook block CP's read-only lines in order, each in its own
process, under its own heading. What these hold: every step runs in order
and a long one keeps its last lines; a step that fails or hangs is
reported and the round goes on; a step that asks for a holdout stops the
round before anything runs; and the real list reads no holdout and names
only scripts that exist.

Run directly: `python3 tests/test_box_round.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research import box_round as BR                               # noqa: E402


def _scripts():
    d = tempfile.mkdtemp()
    for name, body in (("many.py", "for i in range(30):\n    print('line', i)\n"),
                       ("fails.py", "import sys\nprint('half done')\nsys.exit(3)\n"),
                       ("hangs.py", "import time\nprint('started', flush=True)\ntime.sleep(30)\n"),
                       ("last.py", "print('the last one ran')\n")):
        with open(os.path.join(d, name), "w") as fh:
            fh.write(body)
    return d


def test_every_step_runs_in_order_and_a_failure_does_not_stop_the_round():
    d = _scripts()
    steps = (("many", ("many.py",), 5), ("fails", ("fails.py",), None), ("hangs", ("hangs.py",), None),
             ("last", ("last.py",), None))
    lines = []
    assert BR.main(steps, timeout=2, cwd=d, out=lines.append) == 0
    text = "\n".join(lines)
    heads = [ln for ln in lines if ln.startswith("\n===== ")]
    assert [h.split(" ", 3)[-1] for h in heads[:4]] == ["many", "fails", "hangs", "last"]
    assert "line 29" in text and "line 24" not in text, "a tail keeps only its last lines"
    assert "half done" in text and "----- exit 3" in text
    assert "started" in text and "----- timed out" in text
    assert "the last one ran" in text and "1 ok, 2 exit 3, 3 timed out, 4 ok" in text


def test_a_step_that_asks_for_a_holdout_stops_the_round_before_anything_runs():
    d = _scripts()
    lines = []
    try:
        BR.main((("last", ("last.py",), None), ("peek", ("many.py", "--holdout"), None)), cwd=d,
                out=lines.append)
    except SystemExit as exc:
        assert "holdout" in str(exc)
    else:
        raise AssertionError("a holdout step must stop the round")
    assert not lines, "nothing ran"


def test_the_real_round_reads_no_holdout_and_names_scripts_that_exist():
    BR.refuse_holdouts(BR.STEPS)
    for _heading, args, _tail in BR.STEPS:
        assert (ROOT / args[0]).exists(), args[0]
    assert [a[0] for _h, a, _t in BR.STEPS] == [
        "research/thinmarket_box.py", "research/exp1_lines_box.py", "research/exp7_mlb_strikeouts_box.py",
        "research/exp7b_mlb_strikeout_lines_box.py", "research/exp4c_college_lines_box.py",
        "research/exp8_nba_shape_box.py", "research/exp9_nhl_shape_box.py"], "runbook block CP's order"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
