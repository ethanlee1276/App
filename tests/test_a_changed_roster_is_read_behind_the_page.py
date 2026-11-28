"""A changed roster is read behind the page (step AHF, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load" ... "Ok keep going and work more on these issues as
they are not fixed". Step AGM kept a roster file's parse through a rewrite of the same rosters; a rewrite whose
rosters did change was still parsed by the first page to ask after it. On the live site Jeremiah Smith's college page
spent 3.1 s of 3.2 on the 9.2 MB college file (772 ms of its own work, the rest waiting on the other threads). A
page's ask (`behind=True`: the player page, its link, a team's roster tab) now answers with the rosters in hand and
the file is read behind it, one read per file at a time; the next page has the new rosters. The first ask of a file
with nothing parsed reads it before it answers, as every other reader's ask still does.

Offline. Run directly: `python3 tests/test_a_changed_roster_is_read_behind_the_page.py`
"""
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from contextlib import redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import playerpage as PP, rosterfile as RF  # noqa: E402

SMITH = {"player": "Jeremiah Smith", "position": "WR", "number": "4"}
DAY = {"player": "Ryan Day", "position": "QB", "number": "1"}


def _write(path, players, stamp="2026-11-25T10:00:00"):
    doc = {"teams": {"OSU": {"players": players}}, "sport": "cfb", "generated_at": stamp}
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":")))
    os.replace(tmp, path)
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000 * int(time.time() % 1000 + 1)))


def _until(check, secs=5.0):
    end = time.time() + secs
    while time.time() < end:
        if check():
            return True
        time.sleep(0.02)
    return check()


def test_a_changed_rewrite_answers_with_the_rosters_in_hand_and_is_read_behind():
    d = Path(tempfile.mkdtemp())
    path = d / "rosters_cfb.json"
    real, n, gate = RF.json.loads, [0], threading.Event()

    def slow(*a, **k):
        n[0] += 1
        if n[0] > 1:
            gate.wait(5)                                  # the read behind the page is slow; the page must not wait
        return real(*a, **k)
    RF.forget()
    RF.json.loads = slow
    ran = []
    try:
        _write(path, [SMITH, DAY])
        first = RF.doc(path, behind=True)
        assert n[0] == 1 and len(first["teams"]["OSU"]["players"]) == 2, "nothing in hand: read before it answers"
        _write(path, [SMITH], stamp="2026-11-25T10:30:00")
        t0 = time.time()
        got = [RF.doc(path, behind=True, then=lambda: ran.append(1)) for _ in range(5)]
        assert time.time() - t0 < 1.0 and all(g is first for g in got), "the rosters in hand, at once"
        assert _until(lambda: n[0] == 2), "read behind the page"
        assert n[0] == 2, "one read, however many ask meanwhile"
        gate.set()
        assert _until(lambda: RF.doc(path, behind=True) is not first), "the next page has the new rosters"
        assert len(RF.doc(path, behind=True)["teams"]["OSU"]["players"]) == 1 and n[0] == 2
        assert _until(lambda: ran == [1]), "and what a reader builds from it is built behind the read"
        _write(path, [SMITH, DAY], stamp="2026-11-25T11:00:00")
        assert len(RF.doc(path)["teams"]["OSU"]["players"]) == 2 and n[0] == 3, "any other ask reads before it answers"
    finally:
        gate.set()
        RF.json.loads = real
        RF.forget()
        shutil.rmtree(d, ignore_errors=True)


def test_the_player_pages_index_is_built_again_behind_the_read():
    d = Path(tempfile.mkdtemp())
    path = d / "rosters_cfb.json"
    RF.forget()
    try:
        _write(path, [SMITH, DAY])
        index = PP._roster_names("cfb", data_dir=d)
        assert PP.roster_row("cfb", "Ryan Day", "OSU", data_dir=d)["position"] == "QB"
        _write(path, [SMITH], stamp="2026-11-25T10:30:00")
        assert PP.roster_row("cfb", "Ryan Day", "OSU", data_dir=d)["position"] == "QB", "the rosters in hand"
        key = os.path.join(str(d), "rosters_cfb.json")
        assert _until(lambda: PP._ROSTER_BY_NAME[key][1] is not index), "the index built again behind the read"
        assert PP.roster_row("cfb", "Ryan Day", "OSU", data_dir=d) == {}, "and the next page reads the new rosters"
        assert PP.roster_row("cfb", "Jeremiah Smith", "OSU", data_dir=d)["position"] == "WR"
    finally:
        RF.forget()
        shutil.rmtree(d, ignore_errors=True)


def test_a_read_behind_that_fails_says_so_once_and_the_rosters_in_hand_answer():
    d = Path(tempfile.mkdtemp())
    path = d / "rosters_cfb.json"
    RF.forget()
    said = RF._BEHIND_SAID[0]
    RF._BEHIND_SAID[0] = False
    err = io.StringIO()

    def boom():
        raise RuntimeError("index would not build")
    try:
        _write(path, [SMITH])
        first = RF.doc(path, behind=True)
        with redirect_stderr(err):
            for stamp in ("2026-11-25T10:30:00", "2026-11-25T11:00:00"):
                _write(path, [SMITH, DAY], stamp=stamp)
                RF.doc(path, behind=True, then=boom)
                assert _until(lambda: not RF._BEHIND), "the read behind ends"
        assert err.getvalue().count("a roster file not read again behind the page") == 1, err.getvalue()
        assert first is not None and RF.doc(path) is not None
        RF.forget()
        assert RF.doc(d / "rosters_nfl.json", behind=True) is None, "no file, none"
    finally:
        RF._BEHIND_SAID[0] = said
        RF.forget()
        shutil.rmtree(d, ignore_errors=True)


def test_the_pages_readers_read_behind_and_the_others_do_not():
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    fn = srv[srv.index("def _live_roster(sport, team):"):srv.index("def _depth_chart(sport, team")]
    assert 'rosterfile.doc(ROOT / "web" / "data" / f"rosters_{sport}.json", behind=True)' in fn, "a team's roster tab"
    page = (ROOT / "engine" / "playerpage.py").read_text(encoding="utf-8")
    assert "behind=True,\n                          then=lambda: _roster_names(sport, data_dir)) or {}" in page
    routes = (ROOT / "engine" / "routes.py").read_text(encoding="utf-8")
    assert 'rosterfile.doc(Path(web) / "data" / f"rosters_{sport}.json", behind=True) or {}' in routes, "a link"
    for f in ("engine/statlogs.py", "engine/askbot.py", "engine/rosters.py"):
        assert "behind=True" not in (ROOT / f).read_text(encoding="utf-8"), f
    judged = (ROOT / "tests" / "test_silent_failures.py").read_text(encoding="utf-8")
    assert '"_read_behind",' in judged, "the read behind is judged by the sweep"


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
