"""The roster files are rebuilt half-hourly, not on every sweep
(launch.refresh_sport_rosters, _rosters_age, ROSTER_REBUILD_S).

The heartbeat at 07:54 on 9 November had the rosters step at 34 seconds of
a 365-second sweep, on every sweep, rebuilding five leagues' rosters whose
feeds are each kept half an hour or longer. What these hold:

  * a sweep inside the half hour keeps the files and runs nothing;
  * the oldest file decides: one missing, or one past the half hour (a
    league whose build failed last time keeps its old file), and the
    step runs again on that sweep;
  * the leagues it watches are exactly the files rosters_build.py writes.

Run directly: `python3 tests/test_the_rosters_are_rebuilt_half_hourly.py`
"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import launch                                                       # noqa: E402


class _Box:
    """launch.ROOT pointed at a folder of roster files with chosen ages, and
    the build stubbed so the test sees whether it would have run."""

    def __init__(self, ages_min: dict):
        self.dir = Path(tempfile.mkdtemp(prefix="rosters-age-"))
        data = self.dir / "web" / "data"
        data.mkdir(parents=True)
        now = time.time()
        for lg, age in ages_min.items():
            p = data / f"rosters_{lg}.json"
            p.write_text("{}")
            os.utime(p, (now - age * 60, now - age * 60))
        self.ran = []

    def __enter__(self):
        self.keep = (launch.ROOT, launch._run_build)
        launch.ROOT = self.dir
        launch._run_build = lambda args, *a, **k: (self.ran.append(args) or (True, ""))
        return self

    def __exit__(self, *exc):
        launch.ROOT, launch._run_build = self.keep


def _all(age):
    return {lg: age for lg in launch.ROSTER_LEAGUES}


def test_a_sweep_inside_the_half_hour_keeps_the_files():
    with _Box(_all(10)) as box:
        assert launch.refresh_sport_rosters(quiet=True) is True
    assert box.ran == [], "nothing rebuilt ten minutes after the last"


def test_the_oldest_file_decides():
    ages = _all(5)
    ages["mlb"] = 31
    with _Box(ages) as box:
        launch.refresh_sport_rosters(quiet=True)
    assert box.ran == [["rosters_build.py"]], "one file past the half hour rebuilds them"


def test_a_missing_file_rebuilds_them():
    ages = _all(1)
    del ages["ufc"]
    with _Box(ages) as box:
        launch.refresh_sport_rosters(quiet=True)
    assert box.ran == [["rosters_build.py"]]


def test_no_files_at_all_rebuilds_them():
    with _Box({}) as box:
        launch.refresh_sport_rosters(quiet=True)
    assert box.ran == [["rosters_build.py"]]


def test_the_age_is_the_oldest_files_and_never_raises():
    ages = _all(3)
    ages["cfb"] = 20
    with _Box(ages):
        age = launch._rosters_age()
        assert 19 * 60 < age < 21 * 60, age
        assert launch._rosters_age(now="not a time") is None


def test_the_leagues_watched_are_the_files_the_build_writes():
    import rosters_build
    assert set(launch.ROSTER_LEAGUES) == set(rosters_build.FROM_LOGS) | set(rosters_build.NO_SOURCE)
    assert launch.ROSTER_REBUILD_S == 30 * 60


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
