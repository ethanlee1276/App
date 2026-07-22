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
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    files = sorted(glob.glob(os.path.join(ROOT, "tests", "test_*.py")))
    failed, total = [], 0
    for f in files:
        name = os.path.basename(f)
        r = subprocess.run([sys.executable, f], capture_output=True, text=True, cwd=ROOT)
        m = re.search(r"(\d+) tests passed", r.stdout)
        n = int(m.group(1)) if m else 0
        if r.returncode == 0:
            total += n
            print(f"  ✅ {name:28} {n} tests")
        else:
            failed.append(name)
            print(f"  ❌ {name:28} FAILED")
            print((r.stdout + r.stderr)[-800:])
    print(f"\n{'—' * 40}")
    if failed:
        print(f"FAILED: {', '.join(failed)}  ({total} passed before failure)")
        return 1
    print(f"All green: {total} tests across {len(files)} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
