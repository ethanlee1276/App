"""Tonight's pick count is written beside its board (step AGS, 25 November 2026).

Ethan: "Ok keep going and work more on these issues as they are not fixed". The sign-up screen's first look counts
each league's picks for tonight, and read every league's whole private board to do it (up to 18 MB each): its
"boards" part was 1.84 s of a rebuild on the live site (step AGQ said so), in the one process every page waits on,
whenever a board had changed since the last. The build already holds the board when it publishes it, so it writes
the count beside it (engine/gate._write_picks_sidecar); the count is read from there when it is at least as new as
the board, and from the board itself otherwise. The record's head (885 KB) is read once a change too.

Offline. Run directly: `python3 tests/test_tonights_count_is_written_beside_its_board.py`
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gate, widgetfeed  # noqa: E402


def _board(n_picks=2):
    return {"date": "2026-11-25", "sport": "nba",
            "recommendations": [{"player": f"P{i}", "recommended": i < n_picks} for i in range(5)]}


def test_publish_writes_the_count_beside_the_private_copy():
    with tempfile.TemporaryDirectory() as tmp:
        pub = Path(tmp) / "web" / "data" / "nba.json"
        was = gate.FULL_DIR
        gate.FULL_DIR = Path(tmp) / "data" / "built"
        try:
            _public, full = gate.publish(_board(2), pub, "nba.json")
            side = gate.picks_sidecar(full)
            assert json.loads(side.read_text()) == {"picks": 2, "date": "2026-11-25"}
            assert side.stat().st_mtime_ns >= Path(full).stat().st_mtime_ns, "written after the board"
            assert not side.name.endswith(".json"), "never a name a URL can be served for"
        finally:
            gate.FULL_DIR = was


def test_the_count_is_read_off_the_sidecar_and_off_the_board_when_it_is_older():
    from engine import pushalerts as PA
    d = Path(tempfile.mkdtemp())
    board = d / "nba.json"
    board.write_text(json.dumps(_board(3)))
    real, reads = PA._load, []
    PA._load = lambda p: (reads.append(str(p)), real(p))[1]
    widgetfeed._COUNTS.clear()
    try:
        time.sleep(0.01)
        gate.picks_sidecar(board).write_text(json.dumps({"picks": 3, "date": "2026-11-25"}))
        assert widgetfeed._board_count(board) == (3, "2026-11-25") and reads == [], "the sidecar, not the board"
        widgetfeed._COUNTS.clear()
        time.sleep(0.01)
        board.write_text(json.dumps(_board(4)))          # a board newer than its count: the count is old
        assert widgetfeed._board_count(board) == (4, "2026-11-25") and len(reads) == 1, "read off the board"
        widgetfeed._COUNTS.clear()
        gate.picks_sidecar(board).write_text("not a count")
        os.utime(gate.picks_sidecar(board), None)
        assert widgetfeed._board_count(board) == (4, "2026-11-25") and len(reads) == 2, "a count that won't read"
    finally:
        PA._load = real
        widgetfeed._COUNTS.clear()


def test_the_record_head_is_read_once_a_change():
    d = Path(tempfile.mkdtemp())
    head = d / "record_head.json"
    head.write_text(json.dumps({"overall": {"settled": 10, "wins": 6, "losses": 4}}))
    real, reads = widgetfeed._load, []
    widgetfeed._load = lambda p: (reads.append(1), real(p))[1]
    widgetfeed._KEPT_FILES.clear()
    try:
        a = widgetfeed._load_kept(head)
        b = widgetfeed._load_kept(head)
        assert a is b and len(reads) == 1 and a["overall"]["wins"] == 6
        time.sleep(0.01)
        head.write_text(json.dumps({"overall": {"settled": 11, "wins": 7, "losses": 4}}))
        assert widgetfeed._load_kept(head)["overall"]["wins"] == 7 and len(reads) == 2
        assert widgetfeed._load_kept(d / "none.json") == {}
    finally:
        widgetfeed._load = real
        widgetfeed._KEPT_FILES.clear()


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
