"""The sign-up screen's first look reads each board once a change (step AGH, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load" ... "work more on these issues as they are not
fixed". Traced on Amon-Ra St. Brown's live page, his routes and carries charts took 1.3 s each with 25 to 34 ms of
their own work: they waited behind the first look's rebuild (/api/firstlook, 2.9 s, 1.8 s of the server's own time)
in the one process that answers every page. The first look counted tonight's picks off every league's whole board
and read every league's report archive, on each rebuild, about once a minute. Now:

  * a board's count is read again only once its file has changed (engine/widgetfeed._board_count);
  * a league's record on its reports is kept until its archive moves: a report saved renames into its day's folder,
    which moves that folder's time (engine/reportrecord.record);
  * the first look is rebuilt at most every five minutes (server.FIRSTLOOK_TTL_S), and its answer says the last
    build's parts and their milliseconds, so the next slow one says where.

Offline. Run directly: `python3 tests/test_the_first_look_reads_each_board_once_a_change.py`
"""
import gzip
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import firstlook, reportarchive, reportrecord, widgetfeed  # noqa: E402


def test_a_boards_count_is_read_again_only_once_it_changed():
    d = Path(tempfile.mkdtemp())
    board = d / "nfl.json"
    board.write_text(json.dumps({"date": "2026-11-26", "recommendations": [{"recommended": True}] * 3}))
    from engine import pushalerts as PA
    real, reads = PA._load, []
    PA._load = lambda p: (reads.append(str(p)), real(p))[1]
    try:
        assert widgetfeed._board_count(board) == (3, "2026-11-26")
        assert widgetfeed._board_count(board) == (3, "2026-11-26") and len(reads) == 1, "read once"
        time.sleep(0.01)
        board.write_text(json.dumps({"date": "2026-11-26", "recommendations": [{"recommended": True}] * 5}))
        assert widgetfeed._board_count(board) == (5, "2026-11-26") and len(reads) == 2, "and again once it changed"
        assert widgetfeed._board_count(d / "none.json") == (0, ""), "no file, nothing"
    finally:
        PA._load = real
    src = (ROOT / "engine" / "widgetfeed.py").read_text(encoding="utf-8")
    assert 'n, date = _board_count(gate.board_source(web / "data" / file))' in src


def _report(where, day, away, home):
    path = Path(where) / reportarchive.DIR / "nfl" / day / f"{away}@{home}.json.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(gzip.compress(json.dumps({"date": day, "away": away, "home": home, "final": {"away": 20,
                                                                                               "home": 24}}).encode()))
    tmp.replace(path)                                     # as reportarchive writes one: renamed in


def test_a_leagues_record_is_kept_until_its_archive_moves():
    where = tempfile.mkdtemp()
    _report(where, "2026-11-23", "GB", "DET")
    real, built = reportrecord._record, []
    reportrecord._record = lambda w, s, d: (built.append(s), real(w, s, d))[1]
    try:
        first = reportrecord.record(where, "nfl", today="2026-11-25")
        again = reportrecord.record(where, "nfl", today="2026-11-25")
        assert again is first and built == ["nfl"], "kept"
        time.sleep(0.01)
        _report(where, "2026-11-23", "NYG", "PHI")         # a report saved into a day's folder moves it
        third = reportrecord.record(where, "nfl", today="2026-11-25")
        assert len(built) == 2 and third is not first, "built again"
        reportrecord.record(where, "nfl", today="2026-11-26")
        assert len(built) == 3, "another day's recent window is its own"
        assert reportrecord.record(tempfile.mkdtemp(), "nfl")["games"] == [], "no archive, nothing kept"
    finally:
        reportrecord._record = real


def test_the_first_look_says_its_parts_and_is_rebuilt_every_five_minutes():
    took = []
    out = firstlook.build(Path(tempfile.mkdtemp()), took=took)
    assert [p for p, _ in took] == ["counts", "free", "last", "proof", "reports"], took
    assert all(ms >= 0 for _, ms in took) and "record" in out
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    assert "FIRSTLOOK_TTL_S = 300" in srv and "_FIRSTLOOK.update(at=time.time(), body=body, took=took)" in srv
    fn = srv[srv.index("    def _firstlook(self"):srv.index("    def _record_lab(self")]
    assert 'headers=[("Server-Timing", parts)] if parts else None' in fn


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
