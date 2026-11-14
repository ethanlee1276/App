"""The site binds its socket BEFORE it builds its boards.

Ethan, 2026-08-19, watching a deploy on the droplet: "IT RESTARTED BUT IS
NOT ANSWERING." Nothing was broken. `refresh_all()` ran before the bind,
so every restart took the site off the air for the length of a full
rebuild — 5 to 15 minutes on a 1 vCPU box — and the deploy script's own
three-minute health check could not tell "still building" from "dead". A
healthy deploy reported failure and invited a rollback.

What is defended here:

  * THE SOCKET OPENS FIRST. A restart costs a second of downtime, not a
    rebuild. The boards already on disk are served meanwhile.
  * ONE BUILD AT A TIME. The startup build is now concurrent with the
    periodic refresher, and two `refresh_all()` runs writing the same
    files would interleave into a slate that never existed.
  * THE PERIODIC BUILD SKIPS RATHER THAN QUEUES. It runs on a timer; the
    next tick beats piling up behind the build already in flight.
  * THE ONE-SHOT CLI STILL BLOCKS. `nightly_run()` exists to build and
    exit — backgrounding that would return before the work was done.

Run directly: `python3 tests/test_boot_order.py`
"""

import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
TREE = ast.parse(SRC)
DEPLOY = open(os.path.join(ROOT, "deploy", "deploy.sh"), encoding="utf-8").read()


def _fn(name):
    for n in ast.walk(TREE):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    raise AssertionError(f"{name}() is gone")


def _calls(node, name):
    """Line numbers where `name()` is called inside this node."""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                and n.func.id == name:
            out.append(n.lineno)
    return out


def test_main_binds_before_it_builds():
    main = _fn("main")
    # ANY server class, not one name. This pinned the literal
    # `ThreadingHTTPServer` and started failing the day the server was
    # given a ceiling and became `BoundedHTTPServer` — a rename, with the
    # ordering this test is about completely unchanged. What matters is
    # that a socket is bound, not what the class is called this month.
    binds = [n.lineno for n in ast.walk(main)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id.endswith("HTTPServer")]
    assert binds, "main() no longer binds a socket"
    # Any build inside main() must live in the nested startup thread,
    # which is defined after the bind. A bare call before it is the bug.
    inner = {f.name for f in ast.walk(main)
             if isinstance(f, ast.FunctionDef)}
    assert "_startup_chores" in inner
    chores = _fn("_startup_chores")
    for line in _calls(main, "refresh_all"):
        inside_thread = chores.lineno <= line <= (chores.end_lineno or line)
        assert inside_thread, (
            f"refresh_all() at line {line} runs on main()'s own path — "
            f"that is the restart-downtime bug returning")
        assert line > min(binds), "the build must come after the bind"


def test_the_startup_build_holds_the_lock():
    chores = _fn("_startup_chores")
    src = ast.get_source_segment(SRC, chores) or ""
    assert "_BUILD_LOCK" in src, "the startup build takes no lock"
    assert "refresh_all()" in src
    # A failed build must not cost the settle or the running site.
    assert "except Exception" in src
    assert "_WARMING = False" in src, "the warming flag never clears"


def test_the_periodic_build_skips_rather_than_queues():
    ref = _fn("_background_refresher")
    src = ast.get_source_segment(SRC, ref) or ""
    assert "_BUILD_LOCK.acquire(blocking=False)" in src, \
        "the refresher would queue behind the startup build, not skip"
    assert "_BUILD_LOCK.release()" in src
    i = src.index("_BUILD_LOCK.acquire(blocking=False)")
    assert "finally:" in src[i:i + 400], "a raising build would hold the lock forever"


def test_the_one_shot_cli_still_blocks():
    """nightly_run() builds and exits; backgrounding it would return
    before the work was done and report success for nothing."""
    night = _fn("nightly_run")
    assert _calls(night, "refresh_all"), "the nightly build lost its build"
    src = ast.get_source_segment(SRC, night) or ""
    assert "Thread(" not in src, "the one-shot run must not background itself"


def test_the_deploy_check_no_longer_calls_a_slow_start_healthy():
    """The check used to wait three minutes and then print a sentence that
    sent a healthy deploy toward a rollback."""
    assert "up to 3 min" not in DEPLOY, "the stale cold-start promise survived"
    assert "binds first" in DEPLOY
    # It still fails loudly when the site really is silent — and points at
    # the journal before the rollback.
    assert "IT RESTARTED BUT IS NOT ANSWERING." in DEPLOY
    i = DEPLOY.index("IT RESTARTED BUT IS NOT ANSWERING.")
    assert "journalctl" in DEPLOY[i:i + 700]
    assert DEPLOY.index("journalctl", i) < DEPLOY.index("roll back", i), \
        "read the journal before rolling back, not after"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
