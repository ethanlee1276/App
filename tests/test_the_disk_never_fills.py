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

Incident 2026-11-01: the same "No space left on device" at 04:32 UTC, and
the API down until 11:19. The weekly `backup.sh --check` (Sundays, 04:30
UTC) restored history.db, 6.5 GB, into /tmp with 4.5 GB free, filled the
disk, died in gunzip and left the half-written copy behind; a second one
from an earlier Sunday sat beside it. And data/backups held 16 GB, most of
it pre-repair copies of history.db that nothing ever deleted. Pinned too:
  * the weekly check measures before it restores, keeps its scratch copy
    beside the backups and leaves nothing behind however it ends;
  * a pre-repair copy measures first and is refused without room;
  * old pre-repair copies are pruned every cycle, the newest two kept;
  * the low-disk warning comes while a copy of history.db still fits.
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
    assert launch.DISK_LOW_GB == 8.0, "a warning has to come while history.db still fits"
    lines = []
    launch._disk_check(free_bytes=lambda p: int(1.5 * 1024 ** 3), say=lines.append)
    assert lines and "⚠️" in lines[0] and "1.5 GB" in lines[0], lines
    lines.clear()
    launch._disk_check(free_bytes=lambda p: 20 * 1024 ** 3, say=lines.append)
    assert lines == []


def _check_tree(d: Path):
    """deploy/backup.sh run from a copy in a tree of our own (the way
    tests/test_backup_remote.py runs it), with one database and its own
    backup folder and lock."""
    import shutil
    import sqlite3
    tree, dest = d / "tree", d / "backups"
    (tree / "deploy").mkdir(parents=True)
    (tree / "data").mkdir()
    dest.mkdir()
    shutil.copy2(ROOT / "deploy" / "backup.sh", tree / "deploy" / "backup.sh")
    c = sqlite3.connect(str(tree / "data" / "ledger.db"))
    c.execute("CREATE TABLE t (x)"); c.execute("INSERT INTO t VALUES (1)"); c.commit(); c.close()
    return tree, dest


def _run_check(tree: Path, dest: Path, **env):
    full = dict(os.environ, QB_BACKUP_DIR=str(dest), QB_BACKUP_LOCK=str(dest.parent / "lock"),
                QB_ENV_FILE=str(dest.parent / "no-env"), **env)
    full.pop("QB_BACKUP_REMOTE", None)
    return subprocess.run(["bash", str(tree / "deploy" / "backup.sh"), "--check"],
                          capture_output=True, text=True, cwd=str(tree), env=full, timeout=120)


def test_the_weekly_check_measures_before_it_restores():
    import gzip
    with tempfile.TemporaryDirectory() as d:
        tree, dest = _check_tree(Path(d))
        with open(tree / "data" / "ledger.db", "rb") as fh, \
                gzip.open(dest / "ledger-20261101T040001Z.db.gz", "wb") as gz:
            gz.write(fh.read())
        (dest / ".check-ledger-AbC123").write_text("left by a killed run")
        # A floor no disk can keep: the restore must be skipped, loudly.
        r = _run_check(tree, dest, QB_BACKUP_MEASURE_MB="0", QB_BACKUP_FLOOR_PCT="100")
        assert "NOT CHECKED: ledger" in r.stdout, r.stdout + r.stderr
        assert "ok: ledger" not in r.stdout
        assert not list(dest.glob(".check-*")), "a killed run's scratch copy is swept"
        # Room enough: restored, checked, and the scratch copy gone.
        r = _run_check(tree, dest)
        assert "ok: ledger" in r.stdout, r.stdout + r.stderr
        assert not list(dest.glob(".check-*"))


def test_a_restore_that_dies_leaves_nothing_behind():
    with tempfile.TemporaryDirectory() as d:
        tree, dest = _check_tree(Path(d))
        (dest / "ledger-20261101T040001Z.db.gz").write_bytes(b"\x1f\x8b\x08\x00 not a whole archive")
        r = _run_check(tree, dest)
        assert r.returncode != 0 and "ok: ledger" not in r.stdout, r.stdout + r.stderr
        assert not list(dest.glob(".check-*")), list(dest.iterdir())
    src = (ROOT / "deploy" / "backup.sh").read_text()
    assert 'tmp="$(mktemp)"' not in src, "the restore never goes to /tmp"
    assert 'rm -f "$CHECK_TMP"' in src and "CHECK_TMP" in src.split("trap ", 1)[1].split("\n", 1)[0]


def _repair_fixture(d: Path):
    import importlib
    import sqlite3
    from engine import db as _db, ledger
    launch = importlib.import_module("launch")
    live = d / "ledger.db"
    c = sqlite3.connect(live)
    c.execute("CREATE TABLE t (x)"); c.execute("INSERT INTO t VALUES (1)"); c.commit(); c.close()
    saved = (ledger.DEFAULT_DB, _db.DEFAULT_DB, launch.ROOT, launch.REPAIR_COPY_MEASURE_BYTES)
    ledger.DEFAULT_DB, _db.DEFAULT_DB, launch.ROOT = live, d / "nohist.db", d
    launch.REPAIR_COPY_MEASURE_BYTES = 0

    def restore():
        (ledger.DEFAULT_DB, _db.DEFAULT_DB, launch.ROOT, launch.REPAIR_COPY_MEASURE_BYTES) = saved
    return launch, restore


def test_a_repair_copy_is_refused_without_room():
    gb = 1024 ** 3
    with tempfile.TemporaryDirectory() as d:
        launch, restore = _repair_fixture(Path(d))
        try:
            out = launch._backup_before_repair("test", disk=lambda p: (48 * gb, 43 * gb, 5 * gb))
            assert out is None, "a copy that leaves under 15% free must be refused"
            bdir = Path(d) / "data" / "backups"
            assert not (bdir.exists() and list(bdir.glob("pre-*"))), "and nothing was written"
            out = launch._backup_before_repair("test", disk=lambda p: (48 * gb, 20 * gb, 28 * gb))
            assert out and out.name.startswith("pre-test-"), "with room it is taken"
        finally:
            restore()


def test_old_pre_repair_copies_are_pruned_and_the_newest_two_kept():
    import time as _t
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        now = _t.mktime(_t.strptime("20261101-120000", "%Y%m%d-%H%M%S"))
        for name in ("pre-repair-20260801-000000", "pre-resize-unstaked-20261001-000000",
                     "pre-void-unplayed-20261030-000000", "pre-repair-closes-20261031-000000"):
            (base / name).mkdir()
            (base / name / "history.db").write_bytes(b"h" * 1000)
            (base / name / "ledger.db").write_bytes(b"l" * 10)
        (base / "backup_2026-10-25.zip").write_bytes(b"z")
        r = maintenance.prune_repair_copies(base, now=now)
        left = sorted(str(p.relative_to(base)) for p in base.rglob("*") if p.is_file())
        assert left == ["backup_2026-10-25.zip",
                        "pre-repair-closes-20261031-000000/history.db",
                        "pre-repair-closes-20261031-000000/ledger.db",
                        "pre-resize-unstaked-20261001-000000/ledger.db",
                        "pre-void-unplayed-20261030-000000/history.db",
                        "pre-void-unplayed-20261030-000000/ledger.db"], left
        assert r["removed"] == 2 and r["freed"] == 1000 + 1010, r
    src = inspect.getsource(maintenance.run_if_due)
    assert "prune_repair_copies()" in src, "pruned every cycle, not only when a repair runs"


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
