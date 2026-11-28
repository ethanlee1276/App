"""A game's page says what it has, once (2026-11-18, step XY).

Walking tonight's NBA, NHL and college game pages as a reader:

  - with no prop prices posted yet, the props section read "No player
    props clear the filters in this game" over "Books haven't posted prop
    prices for this game yet": the same nothing twice, the first wrongly
    (nothing had been filtered). Now it says there are no prices yet and
    when they usually come;
  - "Under pressure" drew four columns for leagues whose games carry no
    closing line (basketball and baseball as stored): clutch, then three
    columns of dashes beside a note saying why they were empty. A table
    shows the rates either side has a number for; the note stays;
  - a hockey page with no total posted showed a lone "O/U —" chip, and its
    back-to-back chip was the one chip starting in lower case.

    python3 tests/test_a_game_page_says_what_it_has.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "detail.css").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(src: str, name: str) -> str:
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i)]


def test_no_prices_is_said_once_and_rightly():
    i = DETAIL.index('<div id="gp-sec-props">')
    block = DETAIL[i:DETAIL.index("</div>`}</div>", i)]
    assert ('<div class="es-title">${props.length ? "No player props clear the filters in this game"\n'
            '            : "No prop prices for this game yet"}</div>') in block
    assert "Books usually post them on game day; the ones that clear the edge bar land here." in block
    assert "Books haven’t posted prop prices for this game yet." not in block, "said once"


def test_no_total_is_no_chip_and_a_chip_starts_with_a_capital():
    # A finished game reads its close (`gl`, app.js closedLine, step ADT); the rule is the same.
    assert '${gpLines || gl.total == null ? "" : `<span class="chip">O/U ${gl.total.toFixed(1)}</span>`}' in DETAIL
    assert 'O/U ${g.total != null ? g.total.toFixed(1) : "—"}' not in DETAIL, "a lone \"O/U —\" said nothing"
    assert '<span class="chip down">Second night of a back-to-back</span>' in DETAIL


def test_both_pressure_tables_show_the_rates_that_have_numbers():
    pair = _fn(DETAIL, "pressurePairHTML")
    assert "const rates = pressureRatesOf(rows);" in pair
    assert "PRESSURE_RATES.map" not in pair, "the game page's table draws only its rates"
    assert '<div class="pr-table" style="--pr-n:${rates.length}">' in pair
    rail = DETAIL[DETAIL.index('return `<div class="card pbp-pressure">') - 900:]
    rail = rail[:rail.index("\n}\n")]
    assert "const rates = pressureRatesOf(rows);" in rail and "PRESSURE_RATES.map" not in rail, "the live page's too"
    assert ".pr-table { display: grid; grid-template-columns: 1fr repeat(var(--pr-n, 4), auto);" in CSS
    assert "function pressureRatesOf(rows) {" not in APP, "the first visit's file pays nothing for it"


def test_the_rates_kept_are_the_ones_with_a_number():
    node = shutil.which("node")
    if not node:
        return
    prog = """
      const fs = require('fs');
      const app = fs.readFileSync(process.argv[1], 'utf8'), det = fs.readFileSync(process.argv[2], 'utf8');
      const i = app.indexOf('const PRESSURE_RATES = ['), j = app.indexOf('];', i) + 2;
      eval(app.slice(i, j).replace('const PRESSURE_RATES', 'globalThis.PRESSURE_RATES'));
      const k = det.indexOf('function pressureRatesOf(rows) {');
      eval('globalThis.pressureRatesOf = ' + det.slice(k, det.indexOf('\\n}\\n', k) + 2));
      const keys = (rows) => pressureRatesOf(rows).map(([key]) => key);
      const hoops = { clutch: 48.0, reliability: null, comeback: null, choke: null };
      const foot = { clutch: 55.1, reliability: 70.2, comeback: 31.0, choke: 12.5 };
      console.log(JSON.stringify([
        keys([["MEM", hoops], ["CLE", { ...hoops, clutch: 58 }]]),
        keys([["DET", foot], ["MIN", foot]]),
        keys([["DET", hoops], ["MIN", { ...foot, choke: null }]]),
        keys([["A", {}], ["B", {}]]),
      ]));
    """
    out = subprocess.run([node, "-e", prog, str(ROOT / "web" / "js" / "app.js"), str(ROOT / "web" / "js" / "detail.js")],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [
        ["clutch"],
        ["clutch", "reliability", "comeback", "choke"],
        ["clutch", "reliability", "comeback"],
        ["clutch", "reliability", "comeback", "choke"],
    ], ("only the rates with a number; a table with none keeps all four", out.stdout)


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
