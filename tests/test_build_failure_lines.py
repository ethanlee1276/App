"""A failing build reported WHAT went wrong and never WHERE.

`--boards` on 2026-08-31 recorded CFB's last refresh as FAILED while its
file sat 13.5 hours old — the loop was reaching the build every cycle and
the build was exiting non-zero every cycle. That is a better position
than the silent freeze it replaced (#82), and it still left one line to
go on:

    print(f"  build failed: {args} — exit {code}: {tail[:140]}")

`tail` is the LAST line of output. For a Python traceback that is the
exception message, with the frame that raised it discarded — so half a
day of failures produced "ValueError: ..." and no file, no line, no call
path.

A few lines, not the whole log. A build failing every cycle must not
bury the journal, and a traceback's last frames are where the answer
lives.

Run directly: `python3 tests/test_build_failure_lines.py`
"""

import io
import os
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())

import launch


def _script(body):
    path = os.path.join(tempfile.mkdtemp(), "b.py")
    with open(path, "w") as f:
        f.write(body)
    return path


def _run(body):
    buf = io.StringIO()
    with redirect_stdout(buf):
        ok, tail = launch._run_build([_script(body)])
    return ok, tail, buf.getvalue()


TRACEBACK = ("def inner():\n"
             "    raise ValueError('the actual cause')\n"
             "def outer():\n"
             "    inner()\n"
             "outer()\n")


# --- the frames survive ---------------------------------------------------
def test_a_failing_build_is_reported_at_all():
    ok, _tail, out = _run(TRACEBACK)
    assert ok is False
    assert "build failed" in out


def test_the_exception_still_appears():
    """Unchanged: the last line was always right, just not enough."""
    assert "the actual cause" in _run(TRACEBACK)[2]


def test_the_frame_that_raised_it_now_appears_too():
    """THE POINT. "ValueError" with no file and no line is a fact you
    cannot act on."""
    out = _run(TRACEBACK)[2]
    assert "in inner" in out, out
    assert "line 2" in out, out


def test_the_call_path_above_it_survives():
    out = _run(TRACEBACK)[2]
    assert "in outer" in out, out


def test_the_forwarded_lines_are_marked_as_the_builds_own():
    """So a traceback in the journal is not mistaken for the launcher's."""
    assert "    | " in _run(TRACEBACK)[2]


# --- but it does not become the whole log ---------------------------------
def test_only_the_last_few_lines_are_forwarded():
    """A build failing every cycle would otherwise bury the journal."""
    body = "\n".join(f"print('noise {i}')" for i in range(200)) + "\nraise SystemExit(3)\n"
    out = _run(body)[2]
    assert out.count("    | ") <= launch.FAIL_LINES, out.count("    | ")


def test_the_cap_is_big_enough_for_a_traceback():
    """Frame, call, exception — six is the smallest that carries them."""
    assert launch.FAIL_LINES >= 5


def test_a_long_line_is_truncated_rather_than_dropped():
    out = _run("raise ValueError('x' * 4000)\n")[2]
    assert "build failed" in out
    assert max(len(ln) for ln in out.splitlines()) < 400


# --- a build that works says nothing --------------------------------------
def test_a_successful_build_forwards_nothing():
    """The loop is quiet on purpose; only failure earns output."""
    ok, _tail, out = _run("print('all good')\n")
    assert ok is True
    assert out == "", out


def test_a_build_with_no_output_at_all_does_not_crash():
    ok, tail, out = _run("raise SystemExit(4)\n")
    assert ok is False and "exit 4" in out


# --- and the caller still gets what it needs ------------------------------
def test_the_tail_is_still_returned_for_the_callers_own_checks():
    """`refresh_cfb` matches phrases in `tail` to name its degraded
    states; forwarding must not change what it receives."""
    _ok, tail, _out = _run("print('Keeping the last board')\n")
    assert tail == "Keeping the last board"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
