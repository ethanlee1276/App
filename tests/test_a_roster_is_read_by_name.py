"""A player page finds its player on the roster by name, not by reading every row (step AFP, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load". The page's timing line showed every college player's
page spending about half a second on the roster (Jeremiah Smith's 506 ms of 557, Julian Sayin's 490 of 536): to find
one player, `roster_row` put every row of the 9.2 MB college roster through `core_name`. Each roster file, as read,
is now indexed once by its names' cores, in its own order, and a lookup is a dictionary read; a new file is
indexed again. The rows found are the ones the scan found.

Offline. Run directly: `python3 tests/test_a_roster_is_read_by_name.py`
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import playerpage as PP  # noqa: E402


def _write(d, teams):
    path = os.path.join(d, "rosters_cfb.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"teams": teams}, fh)
    return path


def _big():
    teams = {f"T{t:03d}": {"players": [{"player": f"Player {t}-{i}", "position": "WR"} for i in range(120)]}
             for t in range(250)}
    teams["OSU"] = {"players": [{"player": "Jeremiah Smith", "position": "WR", "number": 4},
                                {"player": "Julian Sayin", "position": "QB"}]}
    teams["LT"] = {"players": [{"player": "Jeremiah Smith", "position": "LB"}]}
    teams["MIA"] = {"players": [{"player": "Nolan Smith Jr.", "position": "LB"}]}
    return teams


def test_the_rows_found_are_the_scans_rows():
    d = tempfile.mkdtemp()
    _write(d, _big())
    PP._ROSTERS.clear()
    PP._ROSTER_BY_NAME.clear()
    assert PP.roster_row("cfb", "Jeremiah Smith", "OSU", data_dir=d)["number"] == 4
    assert PP.roster_row("cfb", "Jeremiah Smith", data_dir=d) == {}, "two men of one name are neither"
    assert PP.roster_row("cfb", "Jeremiah Smith", "LT", data_dir=d, position="LB")["position"] == "LB"
    assert PP.roster_row("cfb", "Nolan Smith", data_dir=d)["team"] == "MIA", "by the name's core: Jr. or not"
    assert PP.roster_row("cfb", "Nobody Here", data_dir=d) == {}


def test_a_lookup_is_a_read_and_a_new_file_is_indexed_again():
    d = tempfile.mkdtemp()
    path = _write(d, _big())
    PP._ROSTERS.clear()
    PP._ROSTER_BY_NAME.clear()
    PP.roster_row("cfb", "Julian Sayin", "OSU", data_dir=d)          # the file read and indexed once
    t0 = time.perf_counter()
    for _ in range(200):
        assert PP.roster_row("cfb", "Julian Sayin", "OSU", data_dir=d)["position"] == "QB"
    took = time.perf_counter() - t0
    assert took < 1.0, f"200 lookups on a 30,000-row roster took {took:.2f} s"
    teams = _big()
    teams["OSU"]["players"].append({"player": "Bryson Rodgers", "position": "WR"})
    _write(d, teams)
    st = os.stat(path)
    os.utime(path, (st.st_atime, st.st_mtime + 5))                    # a new version of the file
    assert PP.roster_row("cfb", "Bryson Rodgers", "OSU", data_dir=d)["position"] == "WR", "indexed again"
    src = (ROOT / "engine" / "playerpage.py").read_text(encoding="utf-8")
    body = src[src.index("def roster_row("):src.index("\ndef ", src.index("def roster_row(") + 10)]
    assert "_roster_names(sport, data_dir).get(want, ())" in body and "for r in rows" not in body


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
