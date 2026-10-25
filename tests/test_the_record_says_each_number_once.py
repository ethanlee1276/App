"""The Record page says each number once (2026-10-25).

Ethan: "I feel like the record page could look better. I feel like we have
a lot of data lined up that says the same thing, so we can probably
condense some pages and do stuff like that without losing any information."

On a board whose Most Likely half had nothing settled, one record —
18-19-1, -1.1u, -3.1% — printed six times: the edge ribbon, a "Combined"
ribbon, the verdict's tiles, a "Combined with the Most Likely board" line
under them, the Edge bets box, and Records by book. The combined ribbon,
the combined line and the box's line are now drawn only when they add
something (`sameTally`). Two contradictions went with them: "Most likely:
no rows yet" above a 27-14-1 paper book, and "Nothing settled yet" under a
verdict of 38 settled when the server's journal answered with nothing.

Run directly: `python3 tests/test_the_record_says_each_number_once.py`
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
REC = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def test_same_tally_compares_the_record_and_the_money():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    js = _fn(APP, "sameTally") + """
      const a = {wins: 18, losses: 19, pushes: 1, net_units: -1.13, roi: -0.031, settled: 38};
      console.log(JSON.stringify([sameTally(a, {...a}), sameTally(a, {...a, wins: 19}),
        sameTally(a, {...a, net_units: -0.9}), sameTally(a, null), sameTally(null, a)]));"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [True, False, False, False, False]


def test_the_combined_lines_draw_only_when_they_add_something():
    ribbons = _fn(APP, "recordRibbonsHTML")
    assert "if (po && po.settled && !sameTally(po, ov))" in ribbons
    combined = _fn(APP, "combinedLineHTML")
    assert "sameTally(po, o)" in combined
    assert "combinedLineHTML(src.pooled_overall, need, o)" in _fn(APP, "recordVerdictHTML")
    books = _fn(APP, "verdictBooksHTML")
    assert 'sameTally(edge, o) ? ""' in books, "the Edge bets box keeps its reading, not the tiles' numbers"


def test_the_most_likely_box_does_not_contradict_the_paper_book():
    books = _fn(APP, "verdictBooksHTML")
    assert '"no rows yet"' not in books
    assert "nothing staked yet — its paper picks are under Records by book" in books


def test_an_empty_answer_from_the_journal_does_not_erase_settled_rows():
    fetch = REC[REC.index("async function recBetsFetch("):REC.index("function recBetsMount(")]
    assert "!Number(page.total) && (ctx.settled || 0) > 0" in fetch
    assert "&& !blank)" in fetch


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
