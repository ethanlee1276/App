"""The riding note names which number moved.

Ethan, 2026-09-05, on Ja'Kyrian Turner's riding row: "The price has
changed since we took this pick — placed at −110, now −110 (line now
15.5)". The line had moved and the price had not, and the sentence
named the wrong one. `ridingMoveCopy` now says only what the two quotes
show — the board leaning the other way, the price, the line, both,
neither, or no quote at all — and a moneyline never prints a line. Run
for real in node (skipped without it).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    i = APP.index("const american = (o) =>")
    american = APP[i:APP.index("\n", i)]
    prog = f"""
      const trueMinus = (s) => String(s).replace("-", "−");
      {american}
      {_fn("ridingMoveCopy")}
      const flat = (s) => s.replace(/\\s+/g, " ").trim();
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


TURNER = {"player": "Ja'Kyrian Turner", "market": "rec_yds", "side": "UNDER", "line": 14.5, "odds": -110}


def test_turners_row_says_the_line_moved_and_not_the_price():
    got = _node("""
      return flat(ridingMoveCopy(%s, {side: "UNDER", line: 15.5, odds: -110}));""" % json.dumps(TURNER))
    if got is None:
        print("  SKIP node not installed"); return
    assert got.startswith("The line has moved since we took this pick — placed at 14.5, now 15.5, −110 either way."), got
    assert "price has changed" not in got
    assert got.endswith("the bet rides as placed, but don’t add more.")


def test_each_of_the_other_cases_says_only_what_the_quotes_show():
    got = _node("""
      const b = %s;
      return {
        price: flat(ridingMoveCopy(b, {side: "UNDER", line: 14.5, odds: -125})),
        both: flat(ridingMoveCopy(b, {side: "UNDER", line: 15.5, odds: -125})),
        neither: flat(ridingMoveCopy(b, {side: "UNDER", line: 14.5, odds: -110})),
        flipped: flat(ridingMoveCopy(b, {side: "OVER", line: 15.5, odds: -105})),
        noQuote: flat(ridingMoveCopy(b, null)),
        noOdds: flat(ridingMoveCopy(b, {side: "UNDER", line: 15.5, odds: null})),
      };""" % json.dumps(TURNER))
    if got is None:
        print("  SKIP node not installed"); return
    assert got["price"].startswith("The price has changed since we took this pick — placed at −110, now −125."), got["price"]
    assert "line" not in got["price"].split(".")[0], "a price-only move must not mention the line"
    assert got["both"].startswith("The price and the line have both moved since we took this pick — placed at −110 on 14.5, now −125 on 15.5."), got["both"]
    assert got["neither"].startswith("Nothing has moved at the book — still −110 on 14.5 — but the pick no longer clears the bar on today’s build."), got["neither"]
    assert got["flipped"].startswith("The board now leans the other way — we hold UNDER on 14.5 at −110; today’s number is OVER on 15.5 at −105."), got["flipped"]
    assert got["noQuote"].startswith("There is no live quote for this market right now — placed at −110 on 14.5, and nothing to compare it with."), got["noQuote"]
    assert "has changed" not in got["noQuote"], "no quote is not evidence of a move"
    assert got["noOdds"] == got["noQuote"], "a quote without a price is no quote"
    for k in ("price", "both", "neither", "flipped", "noQuote"):
        assert "don’t add more" in got[k], k


def test_a_moneyline_never_prints_a_line():
    got = _node("""
      const ml = {player: "TOR", market: "moneyline", side: "TOR", line: 0, odds: -140};
      return {
        neither: flat(ridingMoveCopy(ml, {side: "TOR", line: 0, odds: -140})),
        price: flat(ridingMoveCopy(ml, {side: "TOR", line: 0, odds: -160})),
        none: flat(ridingMoveCopy(ml, null)),
      };""")
    if got is None:
        print("  SKIP node not installed"); return
    for k, v in got.items():
        assert " on 0" not in v and " on null" not in v, (k, v)
    assert got["neither"].startswith("Nothing has moved at the book — still −140 —"), got["neither"]
    assert got["price"].startswith("The price has changed since we took this pick — placed at −140, now −160."), got["price"]


def test_the_row_calls_it_and_the_old_sentence_is_gone_from_the_row():
    i = APP.index("const ridingRow =")
    row = APP[i:APP.index("(ridingAttrs(b));", i)]
    assert '${icon("warn", 12)} ${ridingMoveCopy(b, cur)}' in row
    assert "The price has changed" not in row, "the row still hard-codes the price sentence"


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
