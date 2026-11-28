"""The deploy's backup takes the small databases only; a big copy says so.

Ethan, 2026-10-03: "this keeps freezing like this" — the deploy printed
the three small backups and then sat silent for minutes, copying and
gzipping the multi-gigabyte history.db on a one-core box. Checks: the
deploy runs the backup with history off unless asked; the nightly backup
still takes it; a big copy announces itself, checks the disk first, and
compresses at the fastest level.

Run directly: `python3 tests/test_the_deploy_backup_is_quick.py`
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def test_the_deploy_backs_up_the_small_databases_only():
    sh = _read("deploy", "deploy.sh")
    assert 'QB_BACKUP_HISTORY="${QB_BACKUP_HISTORY:-0}" ./deploy/backup.sh' in sh
    assert sh.index("backup.sh") < sh.index("git pull"), "still before anything changes"


def test_the_nightly_backup_still_takes_history():
    b = _read("deploy", "backup.sh")
    assert 'if [[ "${QB_BACKUP_HISTORY:-1}" != "0" ]]; then DBS+=("data/history.db"); fi' in b


def test_a_big_copy_says_it_is_starting_and_checks_the_disk():
    b = _read("deploy", "backup.sh")
    assert "this takes a few minutes, nothing prints until it is done" in b
    assert "SKIPPED: $db is ${size_mb} MB and only ${free_mb} MB is free" in b
    assert 'gzip -1 -f "$out"' in b


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
