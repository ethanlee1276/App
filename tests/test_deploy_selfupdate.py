"""The deploy script rewrites itself mid-run.

`deploy/deploy.sh` does `git pull` on the repository that contains
`deploy/deploy.sh`. Bash does not read a script into memory — it reads
lazily, keeping a byte offset into the open file — so the pull replaces
the text underneath the running shell and execution continues at that
same offset in the NEW file.

MEASURED, NOT THEORISED. On 2026-08-22 the pull that added the promo-code
step inserted 27 lines above the restart. Bash resumed past them:

    ==> pulling
    ==> restarting qellys

The step never ran and nothing said so. A shorter edit could as easily
have resumed in the middle of a word and run a fragment as a command,
which is the same failure with a worse ending.

The fix is to notice and start over from the new copy. These tests pin
the parts of that which are easy to lose in a later edit: that it happens
at all, that the second run does not repeat the backup, and that the
arguments survive.

Run directly: `python3 tests/test_deploy_selfupdate.py`
"""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = os.path.join(ROOT, "deploy", "deploy.sh")


def _read():
    with open(SH, encoding="utf-8") as fh:
        return fh.read()


def _code():
    """The script with comments stripped.

    The block explaining this hazard names every mechanism involved, so a
    substring search over the raw file passes on the explanation rather
    than on the code. That shape has bitten this suite repeatedly.
    """
    return "\n".join(l for l in _read().splitlines()
                     if not l.lstrip().startswith("#"))


def test_the_script_re_execs_when_the_pull_changes_it():
    code = _code()
    assert "exec bash" in code, "deploy.sh no longer restarts itself"
    assert "deploy/deploy.sh" in code
    assert "git diff --quiet" in code, \
        "the re-exec no longer checks whether THIS file changed"


def test_the_re_exec_passes_its_arguments_on():
    """Losing them would turn `--no-tests` into a full suite run on a
    two-vCPU box — about an hour, in the middle of a deploy somebody is
    watching."""
    code = _code()
    line = [l for l in code.splitlines() if "exec bash" in l][0]
    assert '"$@"' in line, line


def test_the_second_run_does_not_repeat_the_backup_or_the_pull():
    code = _code()
    assert "QB_DEPLOY_RESUMED" in code
    # The backup call has to sit inside the guard, or every self-updating
    # deploy writes two identical copies of both databases.
    guard = code.index("RESUMED")
    backup = code.index("./deploy/backup.sh")
    assert guard < backup, "the backup runs before the resumed-check"


def test_a_pull_that_adds_a_step_runs_that_step_now():
    """The whole claim, end to end: build a repo whose HEAD adds a step
    above the tail, run the OLD copy, and require the new step to appear.

    This is the test that would have caught it. Everything above is a
    description of the fix; this one reproduces the bug.
    """
    if not _have_git():
        print("      (skipped: no usable git)")
        return
    with tempfile.TemporaryDirectory() as tmp:
        origin = os.path.join(tmp, "origin")
        clone = os.path.join(tmp, "clone")
        os.makedirs(os.path.join(origin, "deploy"))
        _git(origin, "init", "-q", ".")
        _git(origin, "config", "user.email", "t@t.t")
        _git(origin, "config", "user.name", "t")

        header = _header()
        _write(os.path.join(origin, "deploy", "backup.sh"),
               "#!/usr/bin/env bash\necho backed-up >> $ROOTMARK\n")
        _write(os.path.join(origin, "deploy", "deploy.sh"),
               header + '\nsay "TAIL v1"\n')
        _git(origin, "add", "-A")
        _git(origin, "commit", "-qm", "v1")
        _git(tmp, "clone", "-q", origin, clone)

        pad = "\n".join(f"# padding {i}" for i in range(30))
        _write(os.path.join(origin, "deploy", "deploy.sh"),
               header + "\n" + pad + '\nsay "NEW STEP"\nsay "TAIL v2"\n')
        _git(origin, "add", "-A")
        _git(origin, "commit", "-qm", "v2")

        mark = os.path.join(tmp, "backups")
        env = dict(os.environ, ROOTMARK=mark)
        out = subprocess.run(["bash", os.path.join(clone, "deploy", "deploy.sh"),
                              "--no-tests"], capture_output=True, text=True,
                             env=env, timeout=120).stdout
        assert "NEW STEP" in out, (
            "a step added by the pull was skipped — the byte-offset bug is "
            f"back:\n{out}")
        assert "TAIL v2" in out and "TAIL v1" not in out, out
        with open(mark, encoding="utf-8") as fh:
            assert len(fh.read().split()) == 1, "the backup ran twice"


# --- the backup script reads where the value is actually written ------------
def test_backup_reads_the_env_file_it_is_configured_in():
    """setenv.sh writes /etc/qellys/env, systemd reads it, and every
    Python tool reads it through engine/secrets.py. backup.sh did not —
    so a correctly configured box printed "QB_BACKUP_REMOTE is not set"
    on every deploy and answered "OFFSITE: none" to --check, which is the
    one question that command exists to answer."""
    sh = _backup_code()
    assert "QB_ENV_FILE" in sh, "backup.sh no longer reads the env file"
    assert "source" not in sh.split("QB_ENV_FILE")[1][:600], \
        "the env file holds the Stripe key — parse it, never execute it"


def test_the_ambient_environment_still_wins():
    """The nightly cron puts QB_BACKUP_REMOTE inline on its own line, and
    a one-off `QB_BACKUP_REMOTE=... ./deploy/backup.sh` has to override
    the file too. Same rule as engine/secrets.py: additive, never
    overriding."""
    sh = _backup_code()
    i = sh.index("QB_ENV_FILE")
    guard = sh[i:i + 400]
    assert '-z "${QB_BACKUP_REMOTE:-}"' in guard, guard


def test_reading_the_env_file_survives_it_being_absent_or_unreadable():
    """Mode 600 and owned by root: a developer running this as themselves
    gets a PermissionError, and that must be a quiet miss rather than a
    crash in the one script that protects the data."""
    sh = _backup_code()
    i = sh.index("QB_ENV_FILE")
    assert '-r "$QB_ENV_FILE"' in sh[i:i + 400]


def _backup_code():
    """deploy/backup.sh with comments stripped — the block explaining
    this bug names every variable in it, so a raw search would pass on
    the explanation rather than on the code."""
    with open(os.path.join(ROOT, "deploy", "backup.sh"), encoding="utf-8") as fh:
        raw = fh.read()
    return "\n".join(l for l in raw.splitlines()
                     if not l.lstrip().startswith("#"))


def _header():
    """deploy.sh from `set -e` down to the end of the re-exec block.

    Sliced from the real file rather than restated, so a change to the
    mechanism is exercised here instead of being shadowed by a copy.
    """
    raw = _read()
    start = raw.index("set -euo pipefail")
    end = raw.index("# --- 4. the gate")
    body = raw[start:end]
    return ("#!/usr/bin/env bash\n" + body
            .replace("./deploy/backup.sh", "bash ./deploy/backup.sh")
            .replace('SERVICE="${QB_SERVICE:-qellys}"', 'SERVICE=test'))


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(path, 0o755)


def _git(cwd, *args):
    subprocess.run(("git",) + args, cwd=cwd, check=True,
                   capture_output=True, timeout=60)


def _have_git():
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=30)
        return True
    except Exception:                                        # noqa: BLE001
        return False


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
