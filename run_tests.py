#!/usr/bin/env python3
"""Run every tests/test_*.py (stdlib only — no pytest needed) and summarize.

    python3 run_tests.py

Each test file runs itself as a script (exit non-zero on failure). Used by CI
and handy locally.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    # Every fixture's tempfile.mkdtemp() outlives its test — a full run
    # leaves thousands of orphan directories, and repeated runs filled a
    # machine's /tmp to ENOSPC. Sandbox the children's TMPDIR for the run
    # and sweep it once at the end, whatever the verdict.
    sandbox = tempfile.mkdtemp(prefix="qellys-tests-")
    env = dict(os.environ, TMPDIR=sandbox, TEMP=sandbox, TMP=sandbox)
    try:
        return _run(env)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def _run(env) -> int:
    files = sorted(glob.glob(os.path.join(ROOT, "tests", "test_*.py")))
    failed, skipped, total = [], [], 0
    for f in files:
        name = os.path.basename(f)
        r = subprocess.run([sys.executable, f], capture_output=True, text=True,
                           cwd=ROOT, env=env)
        m = re.search(r"(\d+) tests passed", r.stdout)
        n = int(m.group(1)) if m else 0
        # A file may bow out when the machine can't give it what it needs
        # (Pillow, for the hand-run venue intake tool). It says so on a
        # SKIP line and exits 0. Report that as a skip, never as a green
        # zero: a file that stops running and still shows ✅ is how
        # coverage disappears without anyone noticing.
        why = re.search(r"^SKIP (.+)$", r.stdout, re.M)
        if r.returncode == 0:
            total += n
            if why:
                skipped.append(name)
                print(f"  ⏭️  {name:27} skipped — {why.group(1).strip()}")
            else:
                print(f"  ✅ {name:28} {n} tests")
        else:
            failed.append(name)
            print(f"  ❌ {name:28} FAILED")
            print((r.stdout + r.stderr)[-800:])
    print(f"\n{'—' * 40}")
    if failed:
        print(f"FAILED: {', '.join(failed)}  ({total} passed before failure)")
        return 1
    # The skip note rides on the summary line because that line is what
    # doctor.py reports and what the nightly shows.
    note = f"  {len(skipped)} skipped: {', '.join(skipped)}." if skipped else ""
    print(f"All green: {total} tests across "
          f"{len(files) - len(skipped)} files.{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
