"""A roster rewritten the same is read once (step AGM, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load" ... "Ok keep going and work more on these issues as
they are not fixed". The roster build rewrites every league's file every half hour with a new `generated_at` and,
nearly always, the same rosters, and every reader keyed its parse on the file's time: every half hour the first
college player's page read the 9.2 MB college file again (Jeremiah Smith's page, the roster 1.3 s of its 1.4 on the
live site), the search rebuilt its 41,888 names behind itself, and a team's roster tab, a player's link and Ask read
the file on every ask. engine/rosterfile parses each file once per content: a rewrite that changes only
`generated_at` keeps the parse (the same object, so what a reader built from it stands), with the new stamp on it.

Offline. Run directly: `python3 tests/test_a_roster_rewritten_the_same_is_read_once.py`
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import playerpage as PP, rosterfile as RF, statlogs as SL  # noqa: E402


def _write(path, players, stamp="2026-11-25T10:00:00"):
    doc = {"teams": {"OSU": {"players": players}}, "team_count": 1, "player_count": len(players), "sport": "cfb",
           "season": 2026, "generated_at": stamp, "feed": "live", "source": "roster", "note": ""}
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":")))
    os.replace(tmp, path)                                  # as rosters_build writes it
    st = os.stat(path)                                     # a rewrite moves the file's time, as the box's does
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000 * int(time.time() % 1000 + 1)))


SMITH = {"player": "Jeremiah Smith", "position": "WR", "number": "4", "headshot": "h.png"}
DAY = {"player": "Ryan Day", "position": "QB", "number": "1"}


def _counting():
    real, n = json.loads, [0]

    def loads(*a, **k):
        n[0] += 1
        return real(*a, **k)
    return real, n, loads


def test_a_rewrite_of_the_same_rosters_keeps_the_parse_with_its_new_stamp():
    d = Path(tempfile.mkdtemp())
    path = d / "rosters_cfb.json"
    real, n, loads = _counting()
    RF.forget()
    RF.json.loads = loads
    try:
        _write(path, [SMITH])
        first = RF.doc(path)
        assert first["teams"]["OSU"]["players"][0]["player"] == "Jeremiah Smith" and n[0] == 1
        assert RF.doc(path) is first and n[0] == 1, "the same file: no read at all"
        _write(path, [SMITH], stamp="2026-11-25T10:30:00")
        again = RF.doc(path)
        assert again is first and n[0] == 1, "the same rosters rewritten: the parse stands"
        assert again["generated_at"] == "2026-11-25T10:30:00", "with the new stamp"
        _write(path, [SMITH, DAY], stamp="2026-11-25T11:00:00")
        third = RF.doc(path)
        assert third is not first and n[0] == 2 and len(third["teams"]["OSU"]["players"]) == 2, "new rosters: read"
        assert RF.doc(d / "rosters_nfl.json") is None, "no file, none"
        path.write_text("{not json")
        assert RF.doc(path) is third, "a file that will not read keeps the one in hand"
        RF.forget()
        assert RF.doc(path) is None, "and with none in hand, none"
    finally:
        RF.json.loads = real
        RF.forget()
        shutil.rmtree(d, ignore_errors=True)


def test_one_parse_however_many_ask_at_once():
    d = Path(tempfile.mkdtemp())
    path = d / "rosters_cfb.json"
    real, n, loads = _counting()

    def slow(*a, **k):
        time.sleep(0.2)
        return loads(*a, **k)
    RF.forget()
    RF.json.loads = slow
    try:
        _write(path, [SMITH])
        got = []
        ts = [threading.Thread(target=lambda: got.append(RF.doc(path))) for _ in range(5)]
        [t.start() for t in ts]
        [t.join(5) for t in ts]
        assert len(got) == 5 and all(g is got[0] for g in got) and n[0] == 1, n
    finally:
        RF.json.loads = real
        RF.forget()
        shutil.rmtree(d, ignore_errors=True)


def test_the_page_and_the_search_keep_what_they_built_through_a_rewrite():
    d = Path(tempfile.mkdtemp())
    path = d / "rosters_cfb.json"
    RF.forget()
    try:
        _write(path, [SMITH, DAY])
        index = PP._roster_names("cfb", data_dir=d)
        assert PP.roster_row("cfb", "Jeremiah Smith", "OSU", data_dir=d)["position"] == "WR"
        listed = SL._read_roster(str(path))
        _write(path, [SMITH, DAY], stamp="2026-11-25T10:30:00")
        assert PP._roster_names("cfb", data_dir=d) is index, "the page's index by name stands"
        assert SL._read_roster(str(path)) is listed, "the search's list stands, and its names with it"
        _write(path, [SMITH], stamp="2026-11-25T11:00:00")
        assert PP._roster_names("cfb", data_dir=d) is not index and SL._read_roster(str(path)) is not listed
        assert PP.roster_row("cfb", "Ryan Day", "OSU", data_dir=d) == {}, "a man off the roster is gone from it"
        try:
            SL._read_roster(str(d / "rosters_nba.json"))
            raise AssertionError("no file must raise: the search keeps the roster in hand")
        except OSError:
            pass
        src = (ROOT / "engine" / "statlogs.py").read_text(encoding="utf-8")
        assert "if hit is None or hit[0] is not out:" in src, "its names rebuilt only for a new list"
    finally:
        RF.forget()
        shutil.rmtree(d, ignore_errors=True)


def test_every_reader_of_the_roster_files_reads_them_this_way():
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    fn = srv[srv.index("def _live_roster(sport, team):"):srv.index("def _depth_chart(sport, team")]
    assert 'rosterfile.doc(ROOT / "web" / "data" / f"rosters_{sport}.json")' in fn and "json.load(" not in fn
    for f, needle in (("engine/playerpage.py", 'rosterfile.doc(os.path.join(str(data_dir or ROSTER_DIR), '
                                               'f"rosters_{sport}.json"))'),
                      ("engine/rosters.py", 'rosterfile.doc(Path(data_dir) / f"rosters_{league}.json")'),
                      ("engine/routes.py", 'rosterfile.doc(Path(web) / "data" / f"rosters_{sport}.json")'),
                      ("engine/askbot.py", 'rosterfile.doc(_web(data_dir) / f"rosters_{s}.json")'),
                      ("engine/statlogs.py", "doc = rosterfile.doc(path)")):
        assert needle in (ROOT / f).read_text(encoding="utf-8"), f
    import inspect
    assert "_roster_names(sport)" in inspect.getsource(PP.warm), "parsed behind a restart, before the first page"


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
