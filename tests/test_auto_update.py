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
    assert "/etc/systemd/system/${SERVICE}.service" in sh
    assert "cmp -s" in sh, "it must compare before writing a system file"
    assert "daemon-reload" in sh, "systemd will not reread it otherwise"


def test_the_unit_is_installed_before_the_restart():
    """Installing after would need a second restart to take effect, and
    the deploy's own health check would pass on the old unit."""
    sh = _src("deploy", "deploy.sh")
    assert sh.index("cp \"$UNIT_SRC\"") < sh.index('systemctl restart "$SERVICE"')


def test_it_shows_what_changed_rather_than_writing_silently():
    """This edits a system file. A unit that changed under you is worth
    reading about."""
    sh = _src("deploy", "deploy.sh")
    assert "diff" in sh and "the systemd unit changed" in sh


def test_an_unchanged_unit_is_left_alone():
    """`cmp` gates it, so an ordinary deploy neither writes nor reloads."""
    sh = _src("deploy", "deploy.sh")
    at = sh.index("UNIT_SRC=")
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
    at = sh.index("UNIT_SRC=")
    block = sh[at:at + 1400]
    assert "matches the repo" in block, block
    # And the one fact being deployed for rides on the line, read from
    # the file rather than asserted.
    assert "auto-update: ON" in block


# --- the unit asks for it -------------------------------------------------
def test_the_service_passes_the_flag():
    unit = _src("deploy", "qellys.service")
    line = [ln for ln in unit.splitlines() if ln.startswith("ExecStart=")]
    assert line, "no ExecStart"
    assert "--auto-update" in line[0], line[0]


def test_only_one_execstart_carries_it():
    """A second ExecStart would silently win or lose depending on order."""
    unit = _src("deploy", "qellys.service")
    assert len([ln for ln in unit.splitlines()
                if ln.startswith("ExecStart=")]) == 1


def test_the_launcher_still_treats_it_as_opt_in():
    """The flag must stay a flag. If it ever becomes the default, a
    laptop starts pulling and running code nobody asked it to."""
    src = _src("launch.py")
    assert 'if "--auto-update" in argv:' in src


def test_the_unit_records_why_a_deliberate_opt_in_was_opted_into():
    unit = _src("deploy", "qellys.service")
    assert "not a laptop" in unit.lower()


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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
