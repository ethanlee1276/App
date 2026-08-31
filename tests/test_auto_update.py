"""Pushed code reaches the site without anyone typing anything.

Turned on 2026-08-31 at Ethan's request, from his phone, at work. The
CFB board had sat crashed most of a day for want of somebody reaching a
terminal to run a deploy.

`launch.py` calls the flag "opt-in, every run: this pulls code and
executes it, so it should be a thing you asked for this morning, not a
setting you forgot." On a laptop that is exactly right. This is not a
laptop — it is a droplet nobody sits at, and the alternative was a fix
waiting hours on a human.

THE ONE WAY THIS SILENTLY STOPS WORKING, and it is the reason most of
this file exists: `_auto_update` refuses to pull when the working tree
is dirty, and it is right to — uncommitted work is somebody's work in
progress, not an obstacle. But the app WRITES while it runs: every board
into web/data/, caches and fitted models into data/. If any of that were
tracked, the tree would be permanently dirty, auto-update would skip
forever, and it would say so once every five minutes into a log nobody
reads. Turned on and never running again is worse than off, because
nobody would go back and check.

That is not hypothetical. Commit 0a3e9b9, pushed to this branch the same
day by another session, was "Three tests were writing into the working
copy" — the same failure from the test side.

Run directly: `python3 tests/test_auto_update.py`
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def t_block(sh):
    """The unit-install region of deploy.sh, wherever it moves."""
    at = sh.index("UNIT_SRC")
    return sh[at:at + 2400]


#: Everything the running service writes, by the constants that name it.
#: A path here that git tracks is a path that jams auto-update shut.
WRITTEN_WHILE_RUNNING = (
    "web/data/cfb.json",            # every sport board
    "web/data/recommendations.json",
    "web/data/wnba.json",
    "web/data/heartbeat.json",      # the loop's pulse, every cycle
    "web/data/live_mlb.json",
    "data/cache/espn_cfb_20260831.json",
    "data/models/calibration.json",
    "data/feedstate/hold.json",
    "data/ledger.db",
    "data/autoupdate.json",       # the update timer's own state
)


# --- the tracked unit is the unit that runs -------------------------------
def test_the_deploy_installs_the_unit_when_it_changes():
    """THE GAP THAT MADE THIS COMMIT NECESSARY TWICE.
    `deploy/qellys.service` is tracked by git; systemd reads
    /etc/systemd/system/. Nothing copied one onto the other, so the
    deploy pulled --auto-update, restarted, reported success, and ran a
    unit that had never heard of the flag. A deploy that pulls a change
    and restarts into something else is a deploy that lies."""
    sh = _src("deploy", "deploy.sh")
    assert '/etc/systemd/system/$(basename "$UNIT_SRC")' in sh
    assert "cmp -s" in sh, "it must compare before writing a system file"
    assert "daemon-reload" in sh, "systemd will not reread it otherwise"
    # All three units ride the same install loop — the app, the update
    # oneshot, and its clock.
    for unit in ("qellys.service", "qellys-update.service",
                 "qellys-update.timer"):
        assert f"deploy/{unit}" in sh, unit


def test_the_unit_is_installed_before_the_restart():
    """Installing after would need a second restart to take effect, and
    the deploy's own health check would pass on the old unit."""
    sh = _src("deploy", "deploy.sh")
    assert sh.index("cp \"$UNIT_SRC\"") < sh.index('systemctl restart "$SERVICE"')


def test_it_shows_what_changed_rather_than_writing_silently():
    """This edits a system file. A unit that changed under you is worth
    reading about."""
    sh = _src("deploy", "deploy.sh")
    assert "diff" in sh and "changed — installing it" in sh


def test_an_unchanged_unit_is_left_alone():
    """`cmp` gates it, so an ordinary deploy neither writes nor reloads."""
    sh = _src("deploy", "deploy.sh")
    at = sh.index("UNIT_SRC")
    block = sh[at:at + 1400]
    assert "! sudo cmp -s" in block, block[:200]


def test_a_matching_unit_is_reported_rather_than_silent():
    """The first cut printed nothing on a match. From a phone that is
    indistinguishable from the step not existing, and it cost a round
    trip the day it shipped: the unit was already installed by hand, the
    step skipped silently, and the output could not say which. Silence
    on success is fine for a loop that runs every minute; a deploy runs
    once, watched, and every step should account for itself."""
    sh = _src("deploy", "deploy.sh")
    at = sh.index("UNIT_SRC")
    block = sh[at:at + 1400]
    assert "matches the repo" in block, block
    # And the fact being deployed for rides on its own line, read from
    # systemd rather than asserted.
    assert "auto-update timer:" in t_block(sh)


# --- the app unit must NOT ask for it -------------------------------------
def test_the_service_does_not_pass_the_flag():
    """The reversal is the lesson. --auto-update was put ON this line on
    2026-08-31 and failed silently every five minutes: the app runs as
    `qellys` under ProtectSystem=strict, so its own checkout is
    read-only to it — as it should be. Updates come from the root timer
    (qellys-update.timer) instead; the flag reappearing here would be
    the broken design coming back."""
    unit = _src("deploy", "qellys.service")
    line = [ln for ln in unit.splitlines() if ln.startswith("ExecStart=")]
    assert line and "--auto-update" not in line[0], line


def test_the_unit_records_why_the_flag_was_removed():
    unit = _src("deploy", "qellys.service")
    assert "qellys-update.timer" in unit
    assert "read-only" in unit.lower()


def test_the_timer_units_exist_and_agree():
    svc = _src("deploy", "qellys-update.service")
    tim = _src("deploy", "qellys-update.timer")
    assert "autoupdate.py" in svc
    assert "oneshot" in svc
    assert "OnUnitActiveSec=5min" in tim


def test_the_deploy_installs_and_enables_the_timer():
    sh = _src("deploy", "deploy.sh")
    assert "qellys-update.timer" in sh
    assert "enable --now qellys-update.timer" in sh


def test_the_launcher_still_treats_it_as_opt_in():
    """The flag must stay a flag. If it ever becomes the default, a
    laptop starts pulling and running code nobody asked it to."""
    src = _src("launch.py")
    assert 'if "--auto-update" in argv:' in src


# --- and nothing the app writes can jam it shut ---------------------------
def _tracked(path):
    out = subprocess.run(["git", "ls-files", "--error-unmatch", path],
                         cwd=ROOT, capture_output=True, text=True)
    return out.returncode == 0


def test_nothing_the_service_writes_is_tracked_by_git():
    """THE LOAD-BEARING TEST. A tracked runtime file means a permanently
    dirty tree, auto-update skipping forever, and a five-minute apology
    into a log nobody reads."""
    tracked = [p for p in WRITTEN_WHILE_RUNNING if _tracked(p)]
    assert not tracked, tracked


def test_the_board_and_state_directories_are_ignored_wholesale():
    """Per-file ignores rot the first time a sport ships. The
    directories are what has to be ignored."""
    ignore = _src(".gitignore")
    for rule in ("web/data/", "data/cache/", "data/models/"):
        assert rule in ignore, rule


def test_a_new_board_would_be_ignored_without_anyone_remembering():
    out = subprocess.run(
        ["git", "check-ignore", "web/data/some_new_sport.json"],
        cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, "a new board would dirty the tree"


def test_the_updater_still_refuses_a_dirty_tree():
    """Not a thing to fix — a thing to keep. Uncommitted work on this
    box means somebody is mid-something."""
    src = _src("launch.py")
    at = src.index("def _auto_update()")
    body = src[at:src.index("\ndef ", at + 10)]
    assert "--porcelain" in body
    assert "auto-update skipped" in body


def test_it_never_merges_or_switches_branch():
    """It ends in RUNNING code. Timid is the whole design."""
    src = _src("launch.py")
    at = src.index("def _auto_update()")
    body = src[at:src.index("\ndef ", at + 10)]
    assert "--ff-only" in body
    assert "checkout" not in body


# --- the grep that came back empty on a WORKING updater --------------------
def test_the_success_line_contains_the_words_people_grep_for():
    """2026-08-31, from a phone: `journalctl | grep -i auto-update` came
    back empty and read as "it isn't running". Every failure path said
    "auto-update"; the success path said "new code pulled" — so a healthy
    updater and a dead one produced the same empty grep. The one line
    that proves it worked must contain the term anyone would search."""
    import io
    from contextlib import redirect_stdout
    import launch

    real = os.execv
    os.execv = lambda *a: (_ for _ in ()).throw(RuntimeError("held"))
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            launch._restart_into_new_code()
    finally:
        os.execv = real
    first = buf.getvalue().splitlines()[0]
    assert "auto-update" in first.lower(), first


def test_the_heartbeat_stamps_the_serving_commit_and_updater_state():
    """"Did my push land" was answerable only over SSH. The heartbeat now
    carries the commit this PROCESS started from and whether it would
    ever pull on its own — which `--boards` reads back."""
    import json
    import tempfile
    from pathlib import Path
    import launch

    tmp = Path(tempfile.mkdtemp())
    (tmp / "web" / "data").mkdir(parents=True)
    saved = launch.ROOT
    launch.ROOT = tmp
    try:
        launch._write_heartbeat(60)
    finally:
        launch.ROOT = saved
    beat = json.loads((tmp / "web" / "data" / "heartbeat.json").read_text())
    assert "auto_update" in beat
    head = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    assert beat["commit"] == head, (beat["commit"], head)


def test_the_commit_is_captured_once_not_reread_from_disk():
    """After a pull whose restart failed, `git rev-parse` names code that
    is on disk but NOT in memory. First-read-and-keep is what makes the
    heartbeat truthful about what is actually serving."""
    import inspect
    import launch
    src = inspect.getsource(launch._running_commit)
    assert "_RUNNING_COMMIT" in src
    assert "if not _RUNNING_COMMIT" in src


# --- a persistent pull failure must not look like offline ------------------
def _fail_git(*a, **k):
    if a[0] == "status":
        return True, ""
    if a[0] == "rev-parse" and "--abbrev-ref" in a:
        return True, "main"
    if a[0] == "rev-parse":
        return True, "abc123"
    if a[0] == "pull":
        return False, "fatal: could not read from remote repository"
    return True, ""


def _run_checks(n, git):
    import io
    from contextlib import redirect_stdout
    import launch
    saved_git, saved = launch._git, launch._PULL_FAILS[0]
    launch._git, launch._PULL_FAILS[0] = git, 0
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            for _ in range(n):
                launch._auto_update()
        return buf.getvalue(), launch._PULL_FAILS[0]
    finally:
        launch._git, launch._PULL_FAILS[0] = saved_git, saved


def test_one_failed_check_is_still_just_offline():
    out, _ = _run_checks(1, _fail_git)
    assert out == "", out


def test_the_third_straight_failure_says_why():
    """The in-process updater ran for an HOUR on a box where the pull
    could never succeed, without a word — by design, because offline is
    common. Offline is one check. Three in a row is a pattern, and the
    reason was in git's own output the whole time."""
    out, fails = _run_checks(3, _fail_git)
    assert fails == 3
    assert "auto-update" in out
    assert "could not read from remote" in out


def test_a_success_resets_the_streak():
    import launch
    calls = {"n": 0}

    def flaky(*a, **k):
        if a[0] == "pull":
            calls["n"] += 1
            return (False, "boom") if calls["n"] < 3 else (True, "ok")
        return _fail_git(*a, **k)
    _, fails = _run_checks(3, flaky)
    assert fails == 0


# --- the timer's state file, produced by actually running the script -------
def _make_repo():
    import tempfile
    origin = tempfile.mkdtemp()
    clone = tempfile.mkdtemp()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

    def g(cwd, *a):
        return subprocess.run(("git", "-C", cwd) + a, env=env, check=True,
                              capture_output=True, text=True)
    g(origin, "init", "-b", "main")
    with open(os.path.join(origin, "f.txt"), "w") as f:
        f.write("one\n")
    # The real repo ignores the updater's state file; the test repo must
    # too, or the double-run test below fails for the fixed reason.
    with open(os.path.join(origin, ".gitignore"), "w") as f:
        f.write("data/autoupdate.json\n")
    g(origin, "add", "."); g(origin, "commit", "-m", "one")
    subprocess.run(("git", "clone", origin, clone), env=env, check=True,
                   capture_output=True)
    # clone into itself leaves clone/<basename>; clone dir must BE the repo
    inner = os.path.join(clone, os.path.basename(origin))
    repo = inner if os.path.isdir(os.path.join(inner, ".git")) else clone
    return origin, repo, g


def _run_updater(repo, bindir):
    subprocess.run((sys.executable, os.path.join(ROOT, "deploy",
                                                 "autoupdate.py"),
                    "--repo", repo, "--service", "qellys"),
                   env={**os.environ, "PATH": bindir + os.pathsep
                        + os.environ["PATH"]},
                   check=True, capture_output=True, text=True)
    import json
    with open(os.path.join(repo, "data", "autoupdate.json")) as f:
        return json.load(f)


def _fake_systemctl():
    """A systemctl on PATH that records its argv instead of acting."""
    import tempfile
    bindir = tempfile.mkdtemp()
    log = os.path.join(bindir, "calls")
    path = os.path.join(bindir, "systemctl")
    with open(path, "w") as f:
        f.write(f'#!/bin/sh\necho "$@" >> {log}\n')
    os.chmod(path, 0o755)
    return bindir, log


def test_an_up_to_date_repo_records_ok_and_restarts_nothing():
    _, repo, _ = _make_repo()
    bindir, log = _fake_systemctl()
    state = _run_updater(repo, bindir)
    assert state["ok"] and state["note"] == "up to date", state
    assert not os.path.exists(log), "restarted with nothing pulled"


def test_new_code_is_pulled_and_the_service_restarted():
    origin, repo, g = _make_repo()
    with open(os.path.join(origin, "f.txt"), "w") as f:
        f.write("two\n")
    g(origin, "add", "."); g(origin, "commit", "-m", "two")
    bindir, log = _fake_systemctl()
    state = _run_updater(repo, bindir)
    assert state["ok"] and "restarted" in state["note"], state
    with open(os.path.join(repo, "f.txt")) as f:
        assert f.read() == "two\n", "the pull did not land"
    with open(log) as f:
        assert "restart qellys" in f.read()


def test_a_dirty_tree_is_skipped_and_the_note_names_the_file():
    """"Dirty" without a path cost a round trip over SSH on 2026-08-31:
    the state file said the tree was dirty every five minutes for a day
    and never once said WHICH file, which was the entire question."""
    _, repo, _ = _make_repo()
    with open(os.path.join(repo, "f.txt"), "a") as f:
        f.write("wip\n")
    bindir, log = _fake_systemctl()
    state = _run_updater(repo, bindir)
    assert not state["ok"] and "dirty" in state["note"], state
    assert "f.txt" in state["note"], state
    assert not os.path.exists(log)


def test_an_untracked_stray_file_does_not_jam_the_pull():
    """THE DROPLET INCIDENT, 2026-08-31. `git status --porcelain` lists
    untracked files, and the first cut treated any output as dirt — so
    one stray unignored file skipped every clean pull for a day. A
    fast-forward cannot harm an untracked file (git refuses the pull if
    it would collide), so it must not block one. It IS a .gitignore
    hole, so the note names it without stopping for it."""
    origin, repo, g = _make_repo()
    with open(os.path.join(repo, "stray.log"), "w") as f:
        f.write("dropped by some tool\n")
    with open(os.path.join(origin, "f.txt"), "w") as f:
        f.write("two\n")
    g(origin, "add", "."); g(origin, "commit", "-m", "two")
    bindir, _ = _fake_systemctl()
    state = _run_updater(repo, bindir)
    assert state["ok"], state
    with open(os.path.join(repo, "f.txt")) as f:
        assert f.read() == "two\n", "the stray file blocked a clean pull"
    assert "stray.log" in state["note"], state
    assert "not ignored" in state["note"], state


def test_a_colliding_untracked_file_is_protected_by_git_itself():
    """The loosened guard leans on git's own refusal — so run that
    refusal, don't cite it. Upstream commits stray.log; the clone holds
    an untracked stray.log with different content. The pull must fail,
    recorded, and the local file must survive byte-for-byte."""
    origin, repo, g = _make_repo()
    with open(os.path.join(repo, "stray.log"), "w") as f:
        f.write("MY LOCAL CONTENT\n")
    with open(os.path.join(origin, "stray.log"), "w") as f:
        f.write("upstream content\n")
    g(origin, "add", "."); g(origin, "commit", "-m", "collide")
    bindir, log = _fake_systemctl()
    state = _run_updater(repo, bindir)
    assert not state["ok"] and "pull failed" in state["note"], state
    with open(os.path.join(repo, "stray.log")) as f:
        assert f.read() == "MY LOCAL CONTENT\n", "git clobbered untracked work"
    assert not os.path.exists(log)


def test_a_dead_remote_is_recorded_not_swallowed():
    """THE WHOLE POINT OF THE STATE FILE. The last updater's pull failed
    every five minutes for an hour and said nothing anywhere."""
    import shutil
    origin, repo, _ = _make_repo()
    shutil.rmtree(origin)
    bindir, log = _fake_systemctl()
    state = _run_updater(repo, bindir)
    assert not state["ok"] and "pull failed" in state["note"], state
    assert not os.path.exists(log)


def test_the_updaters_own_state_file_does_not_jam_the_updater():
    """`git status --porcelain` lists UNTRACKED files. Unignored, the
    state file written by run one reads as a dirty tree on run two, and
    the updater deadlocks itself forever — reporting "dirty" about its
    own droppings. The .gitignore entry is the fix; this runs it."""
    _, repo, _ = _make_repo()
    bindir, _ = _fake_systemctl()
    first = _run_updater(repo, bindir)
    second = _run_updater(repo, bindir)
    assert first["ok"] and second["ok"], (first, second)
    assert "dirty" not in second["note"]


def test_the_real_repo_ignores_the_state_file():
    r = subprocess.run(["git", "-C", ROOT, "check-ignore",
                        "data/autoupdate.json"], capture_output=True)
    assert r.returncode == 0, "data/autoupdate.json is not gitignored"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
