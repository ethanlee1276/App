"""A broken odds pacer spends nothing (audit 2026-09-30, F-7, roadmap #13).

`_odds_affordable` answered True when `engine.oddsbudget` failed to import,
so a broken pacer meant every refresh re-pulled paid odds unmetered.
"""

import builtins
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import launch  # noqa: E402


def test_an_import_error_refuses_the_pull():
    real_import = builtins.__import__
    saved = launch._with_odds

    def fake(name, *a, **k):
        if name == "engine.oddsbudget":
            raise ImportError("simulated")
        return real_import(name, *a, **k)
    builtins.__import__ = fake
    launch._with_odds = lambda: True
    sys.modules.pop("engine.oddsbudget", None)
    try:
        assert launch._odds_affordable("/nonexistent.json", quiet=True) is False
    finally:
        builtins.__import__ = real_import
        launch._with_odds = saved


if __name__ == "__main__":
    test_an_import_error_refuses_the_pull()
    print("  ok  test_an_import_error_refuses_the_pull\n\n1 tests passed.")
