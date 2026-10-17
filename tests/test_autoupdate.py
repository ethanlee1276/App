"""`--auto-update` pulls code and then RUNS it. The guards are the feature.

The point is a laptop sitting at home while its owner is at work: a fix
gets pushed, and the machine picks it up without anyone typing `git pull`.
That convenience is only acceptable because of what it refuses to do —
so these tests are almost entirely about the refusals.

Every case runs against real git repositories in a temp directory, not
mocks, because the thing being trusted here is git's behaviour, not ours.
"""

import os
import subprocess
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import launch


def _run(cwd, *args):
    subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True)


def _repo():
    """An origin with one commit, and a clone tracking it."""
    tmp = tempfile.mkdtemp()
    origin, clone = os.path.join(tmp, "origin"), os.path.join(tmp, "clone")
    os.makedirs(origin)
    _run(origin, "git", "init", "-q", "-b", "main")
    _run(origin, "git", "config", "user.email", "t@t")
    _run(origin, "git", "config", "user.name", "t")
    with open(os.path.join(origin, "f.txt"), "w") as fh:
        fh.write("one\n")
    _run(origin, "git", "add", "-A")
    _run(origin, "git", "commit", "-qm", "one")
    _run(tmp, "git", "clone", "-q", origin, clone)
    _run(clone, "git", "config", "user.email", "t@t")
    _run(clone, "git", "config", "user.name", "t")
    return tmp, origin, clone


def _push_new_commit(origin, text="two"):
    with open(os.path.join(origin, "f.txt"), "a") as fh:
        fh.write(text + "\n")
    _run(origin, "git", "add", "-A")
    _run(origin, "git", "commit", "-qm", text)


def _as_repo(path):
    """Point launch.ROOT at a repo for the duration of a call."""
    real = launch.ROOT
    launch.ROOT = path
    return real


def test_it_pulls_a_pushed_commit():
    tmp, origin, clone = _repo()
    real = _as_repo(clone)
    try:
        assert launch._auto_update() is False, "nothing pushed yet"
        _push_new_commit(origin)
        assert launch._auto_update() is True, "should have fast-forwarded"
        with open(os.path.join(clone, "f.txt")) as fh:
            assert "two" in fh.read()
        # And once it's applied, it reports nothing new.
        assert launch._auto_update() is False
    finally:
        launch.ROOT = real
        shutil.rmtree(tmp, ignore_errors=True)


def test_uncommitted_work_is_never_touched():
    """Someone's half-finished edit is work, not an obstacle."""
    tmp, origin, clone = _repo()
    real = _as_repo(clone)
    try:
        scratch = os.path.join(clone, "f.txt")
        with open(scratch, "w") as fh:
            fh.write("MY UNCOMMITTED WORK\n")
        _push_new_commit(origin)
        assert launch._auto_update() is False, "must refuse on a dirty tree"
        with open(scratch) as fh:
            assert fh.read() == "MY UNCOMMITTED WORK\n", "local edit was clobbered"
    finally:
        launch.ROOT = real
        shutil.rmtree(tmp, ignore_errors=True)


def test_a_diverged_branch_stops_rather_than_merges():
    """--ff-only. It must never invent a merge on an unattended machine."""
    tmp, origin, clone = _repo()
    real = _as_repo(clone)
    try:
        # Local commit…
        with open(os.path.join(clone, "local.txt"), "w") as fh:
            fh.write("local\n")
        _run(clone, "git", "add", "-A")
        _run(clone, "git", "commit", "-qm", "local work")
        # …and a different one upstream. Now they've diverged.
        _push_new_commit(origin, "remote")
        assert launch._auto_update() is False
        ok, log = launch._git("log", "--oneline")
        assert "Merge" not in log, "auto-update created a merge commit"
        with open(os.path.join(clone, "local.txt")) as fh:
            assert fh.read() == "local\n", "local commit was lost"
    finally:
        launch.ROOT = real
        shutil.rmtree(tmp, ignore_errors=True)


def test_it_stays_on_the_checked_out_branch():
    tmp, origin, clone = _repo()
    real = _as_repo(clone)
    try:
        _run(clone, "git", "checkout", "-q", "-b", "side")
        launch._auto_update()
        ok, branch = launch._git("rev-parse", "--abbrev-ref", "HEAD")
        assert branch == "side", "auto-update switched branches"
    finally:
        launch.ROOT = real
        shutil.rmtree(tmp, ignore_errors=True)


def test_a_detached_head_is_left_alone():
    tmp, origin, clone = _repo()
    real = _as_repo(clone)
    try:
        ok, sha = launch._git("rev-parse", "HEAD")
        _run(clone, "git", "checkout", "-q", sha)
        _push_new_commit(origin)
        assert launch._auto_update() is False
    finally:
        launch.ROOT = real
        shutil.rmtree(tmp, ignore_errors=True)


def test_no_git_repo_is_not_a_crash():
    tmp = tempfile.mkdtemp()
    real = _as_repo(tmp)
    try:
        assert launch._auto_update() is False
    finally:
        launch.ROOT = real
        shutil.rmtree(tmp, ignore_errors=True)


def test_it_is_opt_in_per_run():
    """Code that pulls and executes must be asked for, not remembered."""
    with open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "launch.py"), encoding="utf-8") as fh:
        src = fh.read()
    assert '"--auto-update" in argv' in src
    # No env var, no config file, no default-on path.
    assert "AUTO_UPDATE" not in src.replace("AUTO_UPDATE_EVERY_S", "")


def test_the_pull_can_only_fast_forward():
    with open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "launch.py"), encoding="utf-8") as fh:
        src = fh.read()
    fn = src[src.index("def _auto_update()"):src.index("def _restart_into_new_code")]
    assert '"--ff-only"' in fn
    for forbidden in ("reset", "--hard", "clean", "checkout", "rebase", "merge"):
        assert f'"{forbidden}"' not in fn, f"auto-update must never run git {forbidden}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
