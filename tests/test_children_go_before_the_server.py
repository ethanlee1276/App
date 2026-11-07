"""Every child the app starts is niced, and goes before the server when memory runs out.

Ethan, 2026-10-14: "There's no most likely bets. There's no edge bets.
There's no players showing up in the search page." The web server is the
one process whose death empties every paid board and every search; a
board build or a chores child dying costs one board one cycle. The unit's
1,600 MB cap is shared by all of them, and the kernel's choice of what to
kill at the cap is mostly size — so each child raises its own
`oom_score_adj` (engine/childproc) on the way in.

Pinned: the helper nices and writes the score, never raises; the three
places the app starts children (board builds, chores lanes, detached
jobs) all go through it; and a real child started this way reads its own
score and niceness back.

Run directly: `python3 tests/test_children_go_before_the_server.py`
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import childproc as CP  # noqa: E402


def _body(path, start, end):
    src = (ROOT / path).read_text(encoding="utf-8")
    at = src.index(start)
    return src[at:src.index(end, at + len(start))]


def test_the_dial_and_the_niceness():
    assert CP.CHILD_NICE == 10, "the niceness every child had before"
    assert 0 < CP.CHILD_OOM_ADJ <= 1000, "raised, never lowered: lowering needs privilege"


def test_the_helper_writes_the_score_and_never_raises():
    d = tempfile.mkdtemp()
    f = os.path.join(d, "oom_score_adj")
    open(f, "w").close()
    CP.lower_self(nice=0, oom_adj=432, path=f)
    assert open(f).read() == "432"
    CP.lower_self(nice=0, path=os.path.join(d, "missing", "oom_score_adj"))   # no /proc: nothing raised
    assert CP.below_server() is (CP.lower_self if hasattr(os, "nice") else None)


def test_every_place_the_app_starts_a_child_goes_through_it():
    for path, start, end in (("launch.py", "def _run_build(", "\ndef "),
                             ("launch.py", "def _lane_child(", "\ndef "),
                             ("engine/maintenance.py", "def _spawn_module(", "\ndef ")):
        body = _body(path, start, end)
        assert "below_server()" in body and "preexec_fn=nicer" in body, (path, start)
        assert "lambda: os.nice" not in body, (path, start)


def test_a_real_child_reads_its_own_score_and_niceness_back():
    if not os.path.exists(CP.OOM_ADJ_PATH) or not hasattr(os, "nice"):
        print("      (skipped: no /proc oom_score_adj here)")
        return
    probe = ("import os\n"
             "print(open('/proc/self/oom_score_adj').read().strip(), os.nice(0))\n")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                         preexec_fn=CP.below_server(), timeout=60)
    adj, nice = out.stdout.split()
    assert int(adj) == CP.CHILD_OOM_ADJ, out.stdout
    assert int(nice) == min(19, os.nice(0) + CP.CHILD_NICE), out.stdout


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
