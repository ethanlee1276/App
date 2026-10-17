"""The auto-updater never runs pulled code as root, and can refuse a push.

Audit 2026-09-30, P1-7 (roadmap #10). deploy/autoupdate.py runs as root
(it needs the deploy key and systemctl) and ran `python3 -m engine.shrink`
from the freshly pulled checkout — so any commit on the branch executed as
root within five minutes. Now:

  * the trim runs as the app user (`runuser -u qellys --`), with its output
    directory handed to that user first;
  * `QB_UPDATE_REQUIRE=tag` pulls only a head a `deploy-*` tag points at,
    `signed` only a head `git verify-commit` accepts; `off` (the default,
    Ethan's ship-on-green pipeline) behaves exactly as before.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _mod():
    spec = importlib.util.spec_from_file_location("autoupdate", ROOT / "deploy" / "autoupdate.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_the_trim_runs_as_the_app_user_when_root():
    au = _mod()
    cmd = au._as_app_user(["python3", "-m", "engine.shrink"], euid=0,
                          user_exists=lambda u: u == "qellys", have=lambda b: True)
    assert cmd[:4] == ["runuser", "-u", "qellys", "--"] and cmd[4:] == ["python3", "-m", "engine.shrink"]
    # Not root (a laptop, the tests): unchanged.
    assert au._as_app_user(["x"], euid=1000, user_exists=lambda u: True,
                           have=lambda b: True) == ["x"]
    # Root, but no such user (a scratch box): unchanged, never a crash.
    assert au._as_app_user(["x"], euid=0, user_exists=lambda u: False,
                           have=lambda b: True) == ["x"]
    import inspect
    assert "_as_app_user(args)" in inspect.getsource(au._trim)


def _make_repo():
    origin, clone = tempfile.mkdtemp(), tempfile.mkdtemp()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

    def g(cwd, *a):
        return subprocess.run(("git", "-C", cwd) + a, env=env, check=True,
                              capture_output=True, text=True)
    g(origin, "init", "-b", "main")
    Path(origin, "f.txt").write_text("one\n")
    Path(origin, ".gitignore").write_text("data/autoupdate.json\n")
    g(origin, "add", "."); g(origin, "commit", "-m", "one")
    subprocess.run(("git", "clone", origin, clone), env=env, check=True, capture_output=True)
    return origin, clone, g


def _run(repo, require):
    bindir = tempfile.mkdtemp()
    Path(bindir, "systemctl").write_text(f'#!/bin/sh\necho "$@" >> {bindir}/calls\n')
    os.chmod(Path(bindir, "systemctl"), 0o755)
    env = {**os.environ, "PATH": bindir + os.pathsep + os.environ["PATH"],
           "QB_UPDATE_REQUIRE": require, "QB_ENV_FILE": "/nonexistent"}
    subprocess.run((sys.executable, str(ROOT / "deploy" / "autoupdate.py"), "--repo", repo),
                   env=env, check=True, capture_output=True, text=True)
    return json.loads(Path(repo, "data", "autoupdate.json").read_text())


def test_tag_mode_refuses_an_untagged_head_and_takes_a_tagged_one():
    origin, repo, g = _make_repo()
    Path(origin, "f.txt").write_text("two\n")
    g(origin, "add", "."); g(origin, "commit", "-m", "two")
    state = _run(repo, "tag")
    assert not state["ok"] and "refused" in state["note"], state
    assert Path(repo, "f.txt").read_text() == "one\n", "nothing was pulled"
    g(origin, "tag", "deploy-2026-09-30")
    state = _run(repo, "tag")
    assert state["ok"] and "pulled" in state["note"], state
    assert Path(repo, "f.txt").read_text() == "two\n"


def test_the_setting_is_read_from_the_env_file_without_sourcing_it():
    au = _mod()
    f = Path(tempfile.mkdtemp()) / "env"
    f.write_text("STRIPE_SECRET_KEY=never-read\nQB_UPDATE_REQUIRE=tag\n")
    old = dict(os.environ)
    try:
        os.environ.pop("QB_UPDATE_REQUIRE", None)
        os.environ["QB_ENV_FILE"] = str(f)
        assert au._setting("QB_UPDATE_REQUIRE", "off") == "tag"
        assert "STRIPE_SECRET_KEY" not in os.environ
    finally:
        os.environ.clear(); os.environ.update(old)


def test_off_behaves_as_before():
    origin, repo, g = _make_repo()
    Path(origin, "f.txt").write_text("two\n")
    g(origin, "add", "."); g(origin, "commit", "-m", "two")
    state = _run(repo, "off")
    assert state["ok"] and "pulled" in state["note"], state


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
