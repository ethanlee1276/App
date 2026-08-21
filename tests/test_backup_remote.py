"""The offsite leg of the backup, and the two ways it was silently off.

`QB_BACKUP_REMOTE` stayed unset for weeks and `--todo` said so every
time. Part of that is nobody getting round to it. Part of it is that the
only destination the script accepted was an rsync target, which means
"own a second machine" — the wrong shape for a few megabytes of
irreplaceable data, where the natural answer is object storage and rsync
cannot speak to it at all.

TWO BUGS FOUND WHILE WIRING IT UP, both of the same kind: a failure that
leaves a successful-looking run.

  * the pruning loop is a pipeline under `set -euo pipefail`, and when a
    database has no backups yet the glob matches nothing, `ls` exits
    non-zero, and the script ENDS THERE. Everything below it — including
    the offsite push — was skipped. The local snapshot was already
    written, so the run printed "backed up" and exited 0;

  * `--check` verified the local copies and said nothing about the
    remote, so a destination that had quietly stopped accepting writes
    looked identical to one that was working, from here, until the day
    the box died.

    python3 tests/test_backup_remote.py
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SCRIPT = os.path.join(ROOT, "deploy", "backup.sh")


def _src():
    with open(SCRIPT, encoding="utf-8") as fh:
        return fh.read()


class Stub:
    """A PATH with a fake `rsync` in it, so the script's own logic is
    what gets exercised rather than the network."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="qb-bk-")
        self.bin = os.path.join(self.dir, "bin")
        os.makedirs(self.bin)
        path = os.path.join(self.bin, "rsync")
        with open(path, "w", encoding="utf-8") as fh:
            # A TRAILING SLASH ON THE SOURCE MEANS "THE CONTENTS", which
            # is rsync's rule and the one the script relies on. The first
            # stub copied the directory itself, so files landed in
            # remote/backups/ and the test failed on the stub rather than
            # on the code it was pointed at.
            fh.write('#!/bin/sh\n'
                     'for a in "$@"; do d="$a"; done\n'
                     'mkdir -p "$d" 2>/dev/null\n'
                     'for a in "$@"; do\n'
                     '  case "$a" in -*) continue;; esac\n'
                     '  [ "$a" = "$d" ] && continue\n'
                     '  case "$a" in\n'
                     '    */) cp -r "$a". "$d" 2>/dev/null ;;\n'
                     '    *)  cp -r "$a" "$d" 2>/dev/null ;;\n'
                     '  esac\n'
                     'done\nexit 0\n')
        os.chmod(path, 0o755)
        self.backups = os.path.join(self.dir, "backups")
        self.remote = os.path.join(self.dir, "remote")
        os.makedirs(self.remote)
        return self

    def __exit__(self, *a):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run(self, *args, remote=None, with_rsync=True):
        env = dict(os.environ, QB_BACKUP_DIR=self.backups)
        if remote is not None:
            env["QB_BACKUP_REMOTE"] = remote
        else:
            env.pop("QB_BACKUP_REMOTE", None)
        if with_rsync:
            env["PATH"] = self.bin + os.pathsep + env["PATH"]
        return subprocess.run(["bash", SCRIPT, *args], capture_output=True,
                              text=True, cwd=ROOT, env=env, timeout=180)


def test_the_offsite_push_is_reached_even_when_a_database_is_missing():
    """THE PIPEFAIL BUG. The run looked successful and skipped the only
    part that survives losing the box."""
    with Stub() as s:
        got = s.run(remote=s.remote)
        assert "syncing to" in got.stdout, (
            "the script never reached the offsite push:\n" + got.stdout)
        assert "offsite copy updated" in got.stdout
        landed = [f for f in os.listdir(s.remote) if f.endswith(".db.gz")]
        assert landed, "nothing actually arrived at the destination"


def test_the_prune_cannot_end_the_script():
    src = _src()
    prune = src[src.index("Keep the last N"):]
    prune = prune[:prune.index("push_remote")]
    assert "|| true" in prune, (
        "the pruning pipeline can exit non-zero under `set -e` again, "
        "which skips everything below it including the offsite push")


def test_check_fails_when_there_is_no_offsite_copy_at_all():
    """The state the site was in for weeks. `--check` said the backups
    were fine, and they were — on the same disk as the databases."""
    with Stub() as s:
        s.run(remote=s.remote)          # make a backup to check
        got = s.run("--check")          # …then check with no remote set
        assert got.returncode != 0, \
            "--check passed with every backup on the same disk as the data"
        assert "OFFSITE" in got.stdout


def test_check_passes_once_a_destination_is_configured():
    with Stub() as s:
        s.run(remote=s.remote)
        got = s.run("--check", remote=s.remote)
        assert "offsite" in got.stdout.lower()
        assert "OFFSITE: none" not in got.stdout


def test_object_storage_is_told_apart_from_a_machine():
    """`user@host:/path` and `b2:bucket/path` are both `something:path`.
    The `@` is the only thing that separates them, and picking the wrong
    tool means rsync trying to ssh to a host called `b2`."""
    src = _src()
    fn = src[src.index("remote_kind()"):]
    fn = fn[:fn.index("\n}")]
    assert '*"@"*' in fn, "the ssh form is no longer detected by its @"
    assert "rclone" in fn

    # Exercised, not just read.
    probe = ("bash", "-c",
             f'source <(sed -n "/^remote_kind()/,/^}}/p" {SCRIPT}); '
             'for r in "$@"; do echo "$r $(remote_kind "$r")"; done', "_",
             "user@host:/srv/backups", "b2:qellys/backups",
             "spaces:bucket/x", "/mnt/volume", "root@1.2.3.4:/b")
    got = subprocess.run(probe, capture_output=True, text=True, timeout=60)
    seen = dict(line.split() for line in got.stdout.split("\n") if line.strip())
    assert seen["user@host:/srv/backups"] == "rsync"
    assert seen["root@1.2.3.4:/b"] == "rsync"
    assert seen["b2:qellys/backups"] == "rclone"
    assert seen["spaces:bucket/x"] == "rclone"
    assert seen["/mnt/volume"] == "rsync"


def test_a_failed_upload_does_not_destroy_the_local_backup():
    """The snapshot on this disk is written and valid before the push
    happens. Exiting non-zero from the middle of a nightly cron is how
    you find out months later that the whole job stopped."""
    with Stub() as s:
        got = s.run(remote="nosuchuser@no.such.host.invalid:/x",
                    with_rsync=False)
        made = [f for f in os.listdir(s.backups) if f.endswith(".db.gz")]
        assert made, "the local backup was lost when the remote failed"


def test_a_missing_rclone_says_how_to_get_it():
    with Stub() as s:
        got = s.run("--test-remote", remote="b2:nowhere/x", with_rsync=False)
        if "rclone" in got.stdout and "not installed" in got.stdout:
            assert "apt install rclone" in got.stdout
        # If rclone IS installed here it will simply fail to reach b2,
        # which is also a correct outcome — the point is that neither
        # case is a stack trace.
        assert "Traceback" not in got.stdout + got.stderr


def test_test_remote_does_a_round_trip_rather_than_just_writing():
    """A write that appears to succeed and a file you can read back are
    different facts. The same reason `--check` restores a backup instead
    of checking the file exists."""
    src = _src()
    block = src[src.index('"--test-remote"'):src.index('if [[ "${1:-}" == "--check" ]]')]
    assert "read it back" in block or "read back" in block
    with Stub() as s:
        got = s.run("--test-remote", remote=s.remote)
        assert got.returncode == 0, got.stdout
        assert "ok —" in got.stdout
        # …and it cleaned up after itself.
        assert not [f for f in os.listdir(s.remote) if "probe" in f], \
            "the probe file was left at the destination"


def test_the_todo_still_names_the_setting():
    from engine import todo
    items = todo.config_items({"QB_BACKUP_REMOTE": ""})
    hit = [i for i in items if "BACKUP_REMOTE" in i.name]
    assert hit and hit[0].state == todo.TODO
    items = todo.config_items({"QB_BACKUP_REMOTE": "b2:x/y"})
    hit = [i for i in items if "BACKUP_REMOTE" in i.name]
    assert hit and hit[0].state == todo.DONE


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
