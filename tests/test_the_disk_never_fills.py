"""The droplet's disk never fills up behind the site's back.

Incident 2026-10-01: every board stopped rebuilding at about 06:30 UTC with
"No space left on device", and the restart failed for the same reason.
The 48 GB disk held 26 GB of data/cache, and 18 GB of that was the meme
radar's throwaway lookups: 384,283 `dex_pairs_*` files and 702,511 `rug_*`
files. `fetch_pairs_for` named its cache file after Python's `hash()`, which
is randomised per process, and memes_build runs as a new process every 15
seconds, so every lookup wrote a file no later run could ever read. Nothing
pruned either prefix. The weekly backup (a 3.5 GB database copied, then
zipped) pushed the nearly full disk over the edge, and a write to the chore
state file on the full disk left it EMPTY, so the box forgot the backup and
the paid harvest had already run.

What is pinned here:
  * the dex cache name is the same in every process for the same coins;
  * throwaway lookups are pruned on the cycle, and nothing else in the
    cache is touched;
  * the chore state is never left empty or half-written;
  * the backup refuses to start without room, keeps its scratch copy beside
    the backups (not in /tmp) and deletes it whatever happens;
  * the test runner sweeps the sandboxes interrupted runs left behind;
  * the heartbeat carries the free space and the journal says when it is low.
"""

import inspect
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import maintenance                                 # noqa: E402
from engine.sources import dexes, fetch                       # noqa: E402


def _age(path: Path, seconds: float) -> None:
    t = time.time() - seconds
    os.utime(path, (t, t))


def test_the_dex_cache_name_is_the_same_in_every_process():
    mints = ["MintA111", "MintB222", "MintC333"]
    here = dexes.pairs_cache_name(mints)
    code = ("import sys; sys.path.insert(0, %r); from engine.sources import dexes; "
            "print(dexes.pairs_cache_name(%r))" % (str(ROOT), mints))
    names = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            env=dict(os.environ, PYTHONHASHSEED=str(seed))).stdout.strip()
             for seed in (1, 2, 3)}
    assert names == {here}, names
    assert here.startswith("dex_pairs_") and here.endswith(".json")
    assert "hash(" not in inspect.getsource(dexes.fetch_pairs_for)


def test_throwaway_lookups_are_pruned_and_nothing_else():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        keep = {"dex_pairs_new.json": 60, "rug_new.json": 3600,
                "pbp_2024.csv": 90 * 86400, "line_history.jsonl": 90 * 86400,
                "cfb_player_stats_2025.csv": 90 * 86400, "dex_boosts_top.json": 90 * 86400}
        gone = {"dex_pairs_old.json": 2 * 3600, "rug_old.json": 2 * 86400}
        for name, age in {**keep, **gone}.items():
            (d / name).write_text("{}")
            _age(d / name, age)
        out = fetch.prune_ephemeral(d, force=True)
        assert out["removed"] == 2, out
        assert sorted(p.name for p in d.iterdir()) == sorted(keep)


def test_the_prune_is_throttled_and_runs_before_the_daily_gate():
    with tempfile.TemporaryDirectory() as d:
        fetch._PRUNED_AT[0] = 0.0
        assert fetch.prune_ephemeral(Path(d))["ran"] is True
        assert fetch.prune_ephemeral(Path(d))["ran"] is False      # throttled
    src = inspect.getsource(maintenance.run_if_due)
    assert src.index("prune_ephemeral") < src.index('state.get("last_done")')


def test_the_chore_state_is_never_left_empty():
    src = inspect.getsource(maintenance._save_state)
    assert "os.replace" in src and ".tmp" in src
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "maintenance.json"
        maintenance._save_state(p, {"last_backup": "2026-10-01"})
        real_write = Path.write_text

        def full_disk(self, *a, **k):
            raise OSError(28, "No space left on device")
        Path.write_text = full_disk
        try:
            try:
                maintenance._save_state(p, {"last_backup": "2026-10-08"})
            except OSError:
                pass
        finally:
            Path.write_text = real_write
        assert maintenance._load_state(p) == {"last_backup": "2026-10-01"}


def test_the_backup_refuses_without_room():
    with tempfile.TemporaryDirectory() as d:
        root, bdir = Path(d) / "root", Path(d) / "backups"
        (root / "data").mkdir(parents=True)
        (root / "data" / "ledger.db").write_bytes(b"x" * 1000)
        state = {}
        try:
            maintenance._maybe_backup(state, maintenance._dt.date(2026, 10, 1), print,
                                      root=root, backup_dir=bdir, free_bytes=lambda p: 10)
        except RuntimeError as exc:
            assert "free" in str(exc), exc
        else:
            raise AssertionError("a backup started with 10 bytes free")
        assert not list(bdir.glob("backup_*"))


def test_a_failed_backup_leaves_nothing_behind():
    import sqlite3
    with tempfile.TemporaryDirectory() as d:
        root, bdir = Path(d) / "root", Path(d) / "backups"
        (root / "data").mkdir(parents=True)
        c = sqlite3.connect(str(root / "data" / "ledger.db"))
        c.execute("CREATE TABLE t (x)"); c.commit(); c.close()
        bdir.mkdir()
        (bdir / "backup_2026-09-24.zip.tmp").write_text("left by a crash")
        real = maintenance.zipfile_testzip
        maintenance.zipfile_testzip = lambda zf: "data/ledger.db"     # a bad read-back
        try:
            try:
                maintenance._maybe_backup({}, maintenance._dt.date(2026, 10, 1), print,
                                          root=root, backup_dir=bdir)
            except RuntimeError:
                pass
        finally:
            maintenance.zipfile_testzip = real
        assert sorted(p.name for p in bdir.iterdir()) == [], list(bdir.iterdir())
    src = inspect.getsource(maintenance._maybe_backup)
    assert "NamedTemporaryFile" not in src, "the scratch copy stays beside the backups"
    assert "finally" in src


def test_the_runner_sweeps_old_sandboxes():
    src = (ROOT / "run_tests.py").read_text()
    assert "def sweep_stale_sandboxes" in src
    import importlib.util
    spec = importlib.util.spec_from_file_location("rt", ROOT / "run_tests.py")
    rt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rt)
    with tempfile.TemporaryDirectory() as d:
        old, new = Path(d) / "qellys-tests-old", Path(d) / "qellys-tests-new"
        other = Path(d) / "someone-else"
        for p in (old, new, other):
            p.mkdir()
            (p / "f").write_text("x")
        _age(old, 2 * 86400)
        _age(other, 2 * 86400)
        rt.sweep_stale_sandboxes(d)
        assert sorted(p.name for p in Path(d).iterdir()) == ["qellys-tests-new", "someone-else"]


def test_the_heartbeat_carries_the_free_space():
    import launch
    src = inspect.getsource(launch._write_heartbeat)
    assert '"disk_free_gb"' in src
    assert launch.DISK_LOW_GB == 2.0
    lines = []
    launch._disk_check(free_bytes=lambda p: int(1.5 * 1024 ** 3), say=lines.append)
    assert lines and "⚠️" in lines[0] and "1.5 GB" in lines[0], lines
    lines.clear()
    launch._disk_check(free_bytes=lambda p: 20 * 1024 ** 3, say=lines.append)
    assert lines == []


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:  # noqa: BLE001
                fails += 1; print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
