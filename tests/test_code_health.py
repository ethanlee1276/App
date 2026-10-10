"""Code health (audit D-8 … D-12, roadmap #53).

* No undefined names and no exception re-raised without its cause
  (ruff F821 / B904). Both were found by the audit — two undefined names
  in guarded test fallbacks, seven re-raises that dropped the original
  traceback — and both are the kind that come back one edit at a time.
* engine/paddle.py stays retired: a second payment processor in the tree
  is a second answer to "what grants access".
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_undefined_names_and_no_causeless_reraise():
    ruff = shutil.which("ruff")
    if not ruff:
        print("  SKIP ruff is not installed"); return
    r = subprocess.run([ruff, "check", "--select", "F821,B904", "--output-format", "concise",
                        "--exclude", "audit", "."], cwd=ROOT, capture_output=True, text=True,
                       timeout=300)
    assert r.returncode == 0, r.stdout[-2000:] or r.stderr[-2000:]


def test_the_retired_processor_stays_retired():
    assert not (ROOT / "engine" / "paddle.py").exists()
    assert "from engine import paddle" not in (ROOT / "server.py").read_text()
    # Its one piece of behaviour the live page needed now lives in billing.
    sys.path.insert(0, str(ROOT))
    from engine import billing
    assert billing.describe("paused").startswith("Paused")


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
