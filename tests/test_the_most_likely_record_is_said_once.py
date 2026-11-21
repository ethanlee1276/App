"""The Record page says the Most Likely record once (2026-11-19).

Ethan, asked whether the Most Likely record, which appeared four times on the
Record page under three different counts, should be cut to one: "Yes."

A league's Record page read it as the top tile ("Most Likely · tracked for its
hit rate", 1543-1114: the board's picks and the list's own, each once), the
by-tier section's "All tiers" line (1320-1010: the board's alone), the paper
record card's "Settled" tile and the verdict's Most Likely line (1256-780 both:
the list's own), and the records by book once more in two halves (448-255 and
808-525). The top tile stays the one record; the rest keep what only they say:
each tier's line, the card's claimed-against-actual, return and sample (its open
picks beside the sample), the verdict's picture and reading, and each half's
size and return.

    python3 tests/test_the_most_likely_record_is_said_once.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REC = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def test_the_top_tile_is_the_one_record():
    assert 'tile("Most Likely · tracked for its hit rate", wl(lo)' in APP, "the one Most Likely record"
    board = _fn(REC, "recBoardSection")
    assert 'line("All tiers"' not in board and "bd.total" not in board, "no total of the tiers"
    card = _fn(REC, "recLikelySection")
    assert 'recTile("Settled"' not in card and "${lk.wins}-${lk.losses}" not in card, "no W-L tile on the card"
    assert '(lk.open ? ` · ${lk.open} open` : "")' in card, "its open picks ride the sample's tile"
    verdict = _fn(REC, "verdictBooksHTML")
    assert "line(lk)" not in verdict, "the verdict draws the book's picture and reading, not its record again"


def test_a_most_likely_half_says_its_size_and_return_not_a_record():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    prog = _fn(REC, "recBookSections") + """
      const _recMinGraded = 30;
      const marketWord = (m) => m;
      const escapeHtml = (s) => String(s);
      const recBucketTable = (head) => `<h4>${head}</h4>`;
      const br = {nfl: {edge: {w: 311, l: 290, push: 0, net_u: 12.4, staked: 388, markets: {}},
        likely: {w: 448, l: 255, push: 0, net_u: -2.4, staked: 70.3, markets: {}},
        likely_live: {w: 808, l: 525, push: 2, net_u: -14.3, staked: 333, markets: {}},
        longshots: {w: 3, l: 9, push: 0, net_u: 1.2, staked: 12, markets: {}}}};
      const heads = [...recBookSections(br, "nfl").matchAll(/<h4>([^<]*)<\\/h4>/g)].map((m) => m[1]);
      console.log(JSON.stringify(heads));"""
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    edge, paper, money, long_ = json.loads(out.stdout)
    assert edge == "Edge bets · 311-290 · +3.2% ROI", edge
    assert paper == "Most Likely — paper, before the money · 703 graded · -3.4% ROI", paper
    assert money == "Most Likely — real money · 1,333 graded · -4.3% ROI", money
    assert not re.search(r"\d+-\d+", paper + money), "no W-L on a Most Likely half"
    assert long_ == "Long Shots · 3-9 · +10.0% ROI · 12 graded — thin sample", long_


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
