"""A game page offers one "Most likely" chip, not two.

Ethan, 2026-10-01, circling "Most likely · 15" beside "Most likely · 0" on
the PIT @ CLE page: "What's going on here". With the one board on, the
game's picks are the `gp-sec-matchup` section ("Most likely · this
game"). The old shelf section (`gp-sec-likely`) survived for its two
folds, picks pulled from this game and posted picks whose chance has
dropped, and its chip kept counting the old shelf, which is empty by
construction then. So a second "Most likely" chip read 0 beside the real
count.

Now, with the one board on, the old section's chip appears only when the
game has no board picks at all (then it is the only "Most likely" chip),
and its folds sit under the board's section without a second heading.
With the one board off, nothing changes.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _page():
    i = APP.index("function renderGamePage(")
    return APP[i:APP.index("\n}\n", i)]


def _chip_line(page, sec):
    i = page.index(f'["{sec}",')
    start = page.rindex("\n", 0, i) + 1
    end = page.index("\n", i)
    line = page[start:end].strip()
    # A chip expression may open on the line before ("(cond)\n ? [...]").
    if line.startswith("?"):
        prev_start = page.rindex("\n", 0, start - 1) + 1
        line = page[prev_start:start].strip() + " " + line
    return line.rstrip(",")


def _chips(ob, match_n, likely_n, dropped, pulled):
    node = shutil.which("node")
    if not node:
        return None
    page = _page()
    js = (f"const oneBoardOn = () => {json.dumps(ob)};\n"
          f"const matchupPickCount = () => {match_n};\n"
          f"const likelies = {{ length: {likely_n} }};\n"
          f"const droppedHere = {{ length: {dropped} }};\n"
          f"const pulled = {{ length: {pulled} }};\n"
          "const g = {};\n"
          "const offHere = droppedHere.length + pulled.length;\n"
          f"const chips = [{_chip_line(page, 'gp-sec-matchup')}, {_chip_line(page, 'gp-sec-likely')}];\n"
          "console.log(JSON.stringify(chips.filter(Boolean).map((c) => c[1])));")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_one_board_with_picks_offers_one_most_likely_chip():
    got = _chips(True, 15, 0, 1, 2)
    if got is None:
        print("  SKIP node not installed"); return
    assert got == ["Most likely · 15"], got


def test_one_board_without_picks_still_leads_to_the_pulled_ones():
    got = _chips(True, 0, 0, 0, 2)
    if got is None:
        print("  SKIP node not installed"); return
    assert got == ["Most likely · 0"], got
    assert _chips(True, 0, 0, 0, 0) == []


def test_the_old_shelf_is_unchanged_when_the_one_board_is_off():
    got = _chips(False, 3, 4, 0, 0)
    if got is None:
        print("  SKIP node not installed"); return
    assert got == ["Matchup picks · 3", "Most likely · 4"], got


def test_the_folds_sit_under_the_board_without_a_second_heading():
    page = _page()
    assert "const offHere = droppedHere.length + pulled.length;" in page
    i = page.index('<div id="gp-sec-likely">')
    block = page[i:i + 900]
    # The old heading is drawn only when the one board is off, or has no
    # picks in this game.
    assert re.search(r"oneBoardOn\(\) && matchupPickCount\(g\)\s*\?\s*\"\"", block), block[:400]


if __name__ == "__main__":
    import sys
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
