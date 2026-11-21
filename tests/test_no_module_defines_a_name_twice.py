"""No module of the app defines the same function or class twice.

Python keeps the last `def` of a name and drops the first without a word.
On 6 November a new `ledger._bet_team` (the team on an NFL player's stat
line, so the close-line repair reads the day he played) was written above
an older `ledger._bet_team` (a daily sport's team, for the void rules) that
returns None for every NFL week. The older one, later in the file, won:
the repair would have gone on reading the whole week, and only a test that
asked for "DET" noticed. This holds every module the site and the box run
(not the tests) to one definition of each top-level name.

Run directly: `python3 tests/test_no_module_defines_a_name_twice.py`
"""
import ast
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {"tests", "node_modules", ".git", "__pycache__", "data", "web"}


def _modules():
    for p in sorted(ROOT.rglob("*.py")):
        if SKIP & set(p.relative_to(ROOT).parts):
            continue
        yield p


def test_every_top_level_name_is_defined_once():
    twice = []
    for p in _modules():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        names = Counter(n.name for n in tree.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
        twice += [f"{p.relative_to(ROOT)}: {name} ×{c}" for name, c in names.items() if c > 1]
    assert not twice, "a later definition silently replaces the earlier one:\n  " + "\n  ".join(twice)


def test_the_scan_reads_the_modules_that_matter():
    seen = {str(p.relative_to(ROOT)) for p in _modules()}
    for must in ("launch.py", "server.py", "engine/ledger.py", "engine/linemoves.py",
                 "engine/sources/oddsapi.py"):
        assert must in seen, must
    assert not any(s.startswith("tests/") for s in seen)


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            fails += 1
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} of {len(tests)} failed.")
    sys.exit(1 if fails else 0)
