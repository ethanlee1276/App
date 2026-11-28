"""A form tile says its number to one decimal in every league (step AFA, 25 November 2026).

The tiles over a market card's chart (L1, L3, L5, L10, Season) print the averages the builds hand over, and each
build rounded them its own way: the NFL's to one place (engine/pipeline._avg), basketball's and baseball's to two
(engine/nba/pipeline._avg, engine/mlb/pipeline._avg), hockey's not at all (nhl_build: ``sum(vals[:3]) / 3``), so a
hockey card read "L3 0.6666666666666666" beside the NFL's "L3 1.3". Ethan, 24 November: "NFL is kind of like the one we
want to go off of". The page says every tile as the NFL's does, and as the pick page says the same averages
(js/detail.js propFormRows, one place).

Offline. Run directly: `python3 tests/test_a_form_tile_reads_to_one_place.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_the_card_says_each_tile_through_one_rounding():
    card = _fn("pricedProfileHTML")
    # One row helper for every market card (step AFD): the priced card's and the history card's.
    row = next(ln for ln in APP.splitlines() if ln.startswith("  `<div class=\"form-tile\"><div class=\"k\">"))
    assert '<div class="v">${tileNum(v)}</div>' in row
    assert "const tiles = formTiles([" in card and "formTiles([" in _fn("historyProfileHTML")
    assert "${v == null ? \"—\" : v}" not in card, "a tile printed as the build handed it over"
    detail = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    assert "${Number(v).toFixed(1)}</span>" in detail, "the pick page says the same averages to one place"


def test_hockeys_thirds_basketballs_hundredths_and_the_nfls_tenths_read_alike():
    line = next(ln for ln in APP.splitlines() if ln.startswith("const tileNum = "))
    if not shutil.which("node"):
        print("      (skipped: no node)")
        return
    prog = line + "\nconsole.log(JSON.stringify([0.6666666666666666, 27.333333333333332, 23.33, 1.3, 2, 0, 1.25, null, " \
                  "undefined, 'x', '4.56'].map((v) => String(tileNum(v)))));"
    path = os.path.join(tempfile.mkdtemp(), "t.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    got = json.loads(out.stdout)
    assert got == ["0.7", "27.3", "23.3", "1.3", "2", "0", "1.3", "—", "—", "—", "4.6"], got


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
