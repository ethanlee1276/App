"""One odds converter and one door to the record (audit #53).

  * engine.odds.implied_or_none is the one guarded American → probability
    converter; the nine local copies call it (or american_to_prob behind
    their own gate) instead of repeating the arithmetic. One early copy
    had the plus-money case inverted, which is why copies are the risk.
  * the builders settle and publish record.json through
    ledger.settle_and_export, so the order and the "only when something
    moved" rule live in one place;
  * every process writes its own temp file before the swap, so two
    builders exporting at once cannot swap in each other's half-file.

Run directly: `python3 tests/test_one_converter_and_one_record_door.py`
"""

import inspect
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import odds  # noqa: E402

COPIES = ["engine/streak.py", "engine/livelines.py", "engine/lab.py", "engine/linemoves.py",
          "engine/booksharp.py", "engine/numcheck.py", "engine/sources/cfblines.py",
          "engine/prereg.py", "engine/potd.py"]


def test_the_converter_and_its_guards():
    f = odds.implied_or_none
    assert f(None) is None and f("x") is None and f(0) is None and f("0") is None
    assert abs(f(-110) - 110 / 210) < 1e-12 and abs(f("+190") - 100 / 290) < 1e-12
    assert f(150.7, parse=int) == odds.american_to_prob(150), "int parse truncates, as the int callers always did"


def test_no_copy_repeats_the_arithmetic():
    pat = re.compile(r"100\.0 / \(\w+ \+ 100\.0\)")
    for path in COPIES:
        src = (ROOT / path).read_text(encoding="utf-8")
        assert not pat.search(src), f"{path} carries its own copy of the formula again"
        assert "implied_or_none" in src or "american_to_prob" in src, path


def test_the_builders_use_the_one_door():
    for b in ("nfl_build.py", "mlb_build.py", "nba_build.py", "cfb_build.py"):
        src = (ROOT / b).read_text(encoding="utf-8")
        assert "ledger.settle_and_export(" in src, b
        assert "ledger.settle_from_history(" not in src, f"{b} settles around the door"


def test_the_door_exports_on_its_rule():
    from engine import ledger
    calls = []
    real_s, real_e = ledger.settle_from_history, ledger.export_json
    try:
        for settled, logged, want in ((0, None, True), (0, 0, False), (2, 0, True), (0, 3, True)):
            calls.clear()
            ledger.settle_from_history = lambda c, h, sport=None, _n=settled: _n
            ledger.export_json = lambda c, p: calls.append(p)
            assert ledger.settle_and_export(None, None, "nfl", logged=logged) == settled
            assert bool(calls) is want, (settled, logged)
    finally:
        ledger.settle_from_history, ledger.export_json = real_s, real_e


def test_each_process_writes_its_own_temp_file():
    from engine import ledger
    src = inspect.getsource(ledger.export_json)
    assert 'f".{_os.getpid()}.tmp"' in src and "_os.replace(tmp, p)" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
