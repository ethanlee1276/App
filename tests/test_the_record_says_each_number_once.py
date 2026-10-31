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
    # Since 2026-10-31 (engine/stakeplan) the record as placed is its own
    # labelled tile on the Record page; a record from before the rule still
    # draws the Combined tile, only when it adds something.
    assert "if (po && po.settled && staked && parts && !sameTally(po, ov))" in ribbons
    assert "} else if (po && po.settled && !staked && !sameTally(po, ov)) {" in ribbons
    combined = _fn(APP, "combinedLineHTML")
    assert "sameTally(po, o)" in combined
    assert '${opts.combinedShown ? "" : combinedLineHTML(src.pooled_overall, need, o)}' in _fn(APP, "recordVerdictHTML")
    books = _fn(APP, "verdictBooksHTML")
    assert 'sameTally(edge, o) ? ""' in books, "the Edge bets box keeps its reading, not the tiles' numbers"


def test_the_verdict_leaves_out_what_the_same_room_already_says():
    """The live NFL record, 2026-10-25, after the first pass: the verdict
    still printed "Combined with the Most Likely board: 45-33-2 · +2.9u" a
    screen below the Combined ribbon showing 45-33-2, and the Most Likely
    box printed that book's verdict sentence word for word above the Most
    Likely section that leads with it. Each goes only where the other
    copy is actually drawn: the ribbon carries the combined total unless
    it is cut to a window with rows in it, and the section is drawn
    whenever the book has a settled or open row."""
    body = REC[REC.index("async function renderRecord("):]
    assert "lkHere, { combinedShown: !(winFrom && recRangeTotals(src.curve, winFrom))," in body
    assert "likelySaid: !!(lkHere && (lkHere.settled || lkHere.open)) });" in body
    # The same window test the ribbon makes, and the same draw test the
    # section makes — so neither copy can go missing on its own.
    assert "const winO = from ? recRangeTotals(src.curve, from) : null;" in body
    assert "pooled_overall: winO ? null : src.pooled_overall," in body
    assert "if (!lk || (!lk.settled && !lk.open)) return \"\";" in _fn(REC, "recLikelySection")
    books = _fn(APP, "verdictBooksHTML")
    assert "lk && lk.verdict && !opts.likelySaid ?" in books
    assert "verdictBooksHTML(edge, lk, chart, lines, o, opts)" in _fn(APP, "recordVerdictHTML")


def test_the_verdict_drops_each_copy_only_when_told():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    js = "\n".join(_fn(APP, n) for n in ("sameTally", "combinedLineHTML")) + """
      const fmtRoi = (r) => `${(r * 100).toFixed(1)}%`;
      const po = {wins: 45, losses: 33, pushes: 2, net_units: 2.9, roi: 0.035, settled: 80};
      const o = {wins: 18, losses: 19, pushes: 1, net_units: -1.13, roi: -0.031, settled: 38};
      const draw = (opts) => (opts.combinedShown ? "" : combinedLineHTML(po, 30, o));
      console.log(JSON.stringify([draw({}).includes("45"), draw({combinedShown: true})]));"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [True, ""]


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
