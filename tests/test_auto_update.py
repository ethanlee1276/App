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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
