"""Two chores lanes keep one state file, and neither undoes the other.

data/cache/maintenance.json is kept by the daily pass (the day's chores, the
deep refit's start, the bug scan) and by the settle pass (the settle clock,
the board learning's clock, the Lab's start), two processes that each hold
the copy they loaded for minutes. Each wrote its whole copy back, so the
settle pass put back the daily pass's marks as they were before it began,
and the daily pass the settle pass's. On 7 November the refit began four
runs in one day (its pieces each the first of a run), and with every child
now level with the board builds (engine/childproc), a run started again in
the afternoon takes half of the box's one CPU from the boards.

What these hold (engine.maintenance `_load_state` / `_save_state`):

  * a copy writes only the keys it changed or removed, into the file as it
    is at that moment, under a short lock, in either order;
  * after a save the copy holds what the other lane wrote meanwhile;
  * a plain dict still replaces the file (the disk-full test's way);
  * two real processes saving side by side lose nothing.

Run directly: `python3 tests/test_two_chore_lanes_never_undo_each_other.py`
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import maintenance as M  # noqa: E402


def _fresh() -> Path:
    p = Path(tempfile.mkdtemp()) / "maintenance.json"
    M._save_state(p, {"last_done": "2026-11-06", "last_settle_ts": 100.0})
    return p


def test_the_settle_pass_no_longer_undoes_the_days_marks():
    p = _fresh()
    daily, settle = M._load_state(p), M._load_state(p)       # both lanes load at the top
    daily["last_done"] = "2026-11-07"
    daily["deep_attempted"] = "2026-11-07"
    M._save_state(p, daily)
    settle["last_settle_ts"] = 200.0                        # minutes later, its whole copy
    settle["lab_attempted"] = "2026-11-07"
    M._save_state(p, settle)
    got = M._load_state(p)
    assert got == {"last_done": "2026-11-07", "deep_attempted": "2026-11-07",
                   "last_settle_ts": 200.0, "lab_attempted": "2026-11-07"}, got


def test_the_daily_pass_no_longer_undoes_the_settle_passs_marks():
    p = _fresh()
    daily, settle = M._load_state(p), M._load_state(p)
    settle["lab_attempted"] = "2026-11-07"
    settle["last_boardlearn_ts"] = 300.0
    M._save_state(p, settle)
    daily["bugscan_attempted"] = "2026-11-07"
    M._save_state(p, daily)
    got = M._load_state(p)
    assert got["lab_attempted"] == "2026-11-07" and got["last_boardlearn_ts"] == 300.0, got
    assert got["bugscan_attempted"] == "2026-11-07" and got["last_settle_ts"] == 100.0, got
    assert daily["lab_attempted"] == "2026-11-07", "the copy holds what the other lane wrote"
    daily["inventions_attempted"] = "2026-11-07"           # and its next save keeps it
    M._save_state(p, daily)
    assert M._load_state(p)["lab_attempted"] == "2026-11-07"


def test_a_key_one_lane_removes_stays_removed():
    p = _fresh()
    a = M._load_state(p)
    a["held"] = {"deep": "2026-11-07"}
    M._save_state(p, a)
    b, c = M._load_state(p), M._load_state(p)
    b.pop("held")
    M._save_state(p, b)
    c["last_settle_ts"] = 400.0                             # never touched "held"
    M._save_state(p, c)
    got = M._load_state(p)
    assert "held" not in got and got["last_settle_ts"] == 400.0, got
    assert "held" not in c, "the copy lets go of it too"


def test_a_change_inside_a_nested_value_is_a_change():
    p = _fresh()
    a = M._load_state(p)
    a["held"] = {"deep": "2026-11-07"}
    M._save_state(p, a)
    b = M._load_state(p)
    b["held"]["lab"] = "2026-11-07"                         # changed in place
    M._save_state(p, b)
    assert M._load_state(p)["held"] == {"deep": "2026-11-07", "lab": "2026-11-07"}


def test_a_plain_dict_still_replaces_the_file():
    p = _fresh()
    M._save_state(p, {"last_backup": "2026-10-01"})
    assert M._load_state(p) == {"last_backup": "2026-10-01"}


def test_two_real_processes_lose_nothing():
    p = _fresh()
    worker = (
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from engine import maintenance as M\n"
        "p, lane = sys.argv[1], sys.argv[2]\n"
        "for i in range(40):\n"
        "    st = M._load_state(p)\n"
        "    st[lane] = i\n"
        "    st[f'{lane}_{i}'] = True\n"
        "    M._save_state(p, st)\n")
    procs = [subprocess.Popen([sys.executable, "-c", worker, str(p), lane]) for lane in ("daily", "settle")]
    assert all(pr.wait(timeout=120) == 0 for pr in procs)
    got = json.loads(p.read_text())
    assert got["daily"] == 39 and got["settle"] == 39, got
    lost = [f"{lane}_{i}" for lane in ("daily", "settle") for i in range(40) if f"{lane}_{i}" not in got]
    assert not lost, lost


def test_every_writer_loads_through_the_one_door():
    import inspect
    for fn in (M.settle_open, M.run_if_due, M.launch_held):
        src = inspect.getsource(fn)
        assert "_load_state(" in src, fn.__name__
    assert "_load_state(STATE_PATH)" in (ROOT / "launch.py").read_text(encoding="utf-8")


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
