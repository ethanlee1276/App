"""The deploy pulls the remote and the branch by name.

Ethan's deploy, 2026-09-24, stopped at its pull with "fatal: Cannot
fast-forward to multiple branches": a bare `git pull --ff-only` reads the
branch's upstream from the git config, and the droplet's names more than
one. The five-minute auto-update names them and pulled fine the whole
time, so the two now pull the same way. A failed pull puts the trimmed
scripts back and stops, leaving the site as it was.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOY = open(os.path.join(ROOT, "deploy", "deploy.sh"), encoding="utf-8").read()
AUTO = open(os.path.join(ROOT, "deploy", "autoupdate.py"), encoding="utf-8").read()


def test_the_pull_names_the_remote_and_the_branch():
    assert 'git pull --ff-only origin "$(git rev-parse --abbrev-ref HEAD)"' in DEPLOY
    assert "\n  git pull --ff-only\n" not in DEPLOY, "the bare pull is back"
    assert '"pull", "--ff-only", "origin", branch' in AUTO, "the auto-update pulls the same way"


def test_a_failed_pull_leaves_the_site_as_it_was():
    i = DEPLOY.index('if ! git pull --ff-only origin')
    block = DEPLOY[i:DEPLOY.index("\n  fi\n", i)]
    assert "python3 -m engine.shrink" in block and "exit 1" in block
    assert DEPLOY.index("engine.shrink --clear") < i, "cleared before the pull, rebuilt if it fails"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
