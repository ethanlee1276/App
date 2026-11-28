"""Every build's full output is kept on the box, and the journal hears
about a change in its warnings — once.

2026-09-26: a night's diagnosis went in circles through probes because a
successful build's output reached neither the journal nor a file ("does
the build's own output reach the journal?" — 0 lines). launch
._keep_build_log writes data/logs/<script>.log (the run before to
.prev.log) and prints one journal line when the build's set of warning
lines changes, never the same warnings every cycle.
"""
import io
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import launch                                                    # noqa: E402


def _run(out, code=0):
    buf = io.StringIO()
    with redirect_stdout(buf):
        launch._keep_build_log(["nfl_build.py", "2026", "4"], out, code)
    return buf.getvalue()


def test_the_log_is_kept_rotated_and_the_journal_hears_a_change_once():
    real_dir, real_warned = launch.BUILD_LOG_DIR, dict(launch._BUILD_WARNED)
    launch.BUILD_LOG_DIR = Path(tempfile.mkdtemp()) / "logs"
    launch._BUILD_WARNED.clear()
    try:
        first = ["Injuries: 157 designations", "  ⚠️  touchdown scenarios skipped: boom", "Wrote board"]
        said = _run(first)
        log = (launch.BUILD_LOG_DIR / "nfl_build.log").read_text()
        assert log.startswith("# ") and "exit 0 · nfl_build.py 2026 4" in log.splitlines()[0]
        assert "Injuries: 157 designations" in log and "Wrote board" in log
        assert "nfl_build: 1 warning line(s) — first: ⚠️  touchdown scenarios skipped: boom" in said
        assert "data/logs/nfl_build.log" in said
        assert _run(first) == "", "the same warnings again: nothing in the journal"
        assert (launch.BUILD_LOG_DIR / "nfl_build.prev.log").exists(), "the run before is kept"
        assert _run(["Injuries: 150", "Wrote board"]) == "", "no warnings: nothing to announce"
        assert "Traceback" in _run(["Traceback (most recent call last):", "ValueError: x"], code=1)
    finally:
        launch.BUILD_LOG_DIR = real_dir
        launch._BUILD_WARNED.clear()
        launch._BUILD_WARNED.update(real_warned)


def test_every_build_goes_through_it():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    body = src[src.index("def _run_build("):]
    body = body[:body.index("\ndef ", 10)]
    assert "_keep_build_log(args, out, proc.returncode)" in body
    gi = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read().splitlines()
    assert "logs/" in gi, "the logs never reach the repository"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
