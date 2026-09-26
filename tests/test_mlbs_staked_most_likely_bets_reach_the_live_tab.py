"""MLB's staked Most Likely bets reach the Live tab.

Ethan, 2026-09-22: "the most likely bets for mlb are not showing in the
live tab."

The Most Likely board journals to `likely` on paper and to `likely_live`
where it stakes real money — MLB since 2026-09-19. engine/livepicks was
taught both halves on 2026-09-21, but baseball does not use it for its
tracker: mlb_build assembles its own, and that copy still asked the
ledger for ('main','longshot','likely'). So no staked MLB Most Likely bet
ever reached the Live tab. The sweat had the same retyped tuple, and the
page split its panels on `category === "likely"`, which would have drawn
any staked row that did arrive under "Open edge bets".

Every one of those now reads the ledger's LIKELY_BOOKS. These tests run
the actual queries against a ledger holding one bet of each book, and
the page's split against one row of each.
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger                                        # noqa: E402
from engine.livepicks import TRACKER_CATEGORIES                  # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()
BUILD = (ROOT / "mlb_build.py").read_text()
SWEAT = (ROOT / "engine" / "sweat.py").read_text()


def _expr(src, start):
    """The Python expression assigned at `start`, up to its balanced close."""
    i = src.index(start) + len(start)
    depth, k = 1, i
    while depth:
        depth += {"(": 1, ")": -1}.get(src[k], 0)
        k += 1
    return src[i - 1:k]


def _ledger():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE bets (sport TEXT, status TEXT, category TEXT, player TEXT)")
    for cat in ("main", "longshot", "likely", "likely_live", "paper", "potd"):
        db.execute("INSERT INTO bets VALUES ('mlb', 'open', ?, ?)", (cat, cat))
    return db


def test_the_mlb_builds_tracker_asks_for_both_halves_of_the_book():
    where = eval(_expr(BUILD, "_where = ("), {"_TRK": TRACKER_CATEGORIES})
    got = {r[0] for r in _ledger().execute(f"SELECT category FROM bets WHERE {where}")}
    assert "likely_live" in got, "the staked Most Likely bets never reach MLB's Live tab"
    assert got == set(TRACKER_CATEGORIES) == {"main", "longshot", "likely", "likely_live"}, got


def test_the_sweat_asks_for_both_halves_too():
    ns = {"ledger": ledger}
    exec(re.search(r"^    cats = .*$", SWEAT, re.M).group(0).strip(), ns)
    where = eval(_expr(SWEAT, "where = ("), ns)
    got = {r[0] for r in _ledger().execute(f"SELECT category FROM bets WHERE {where}")}
    assert got == {"main", "longshot", "likely", "likely_live"}, got


def test_the_edge_count_leaves_both_halves_out():
    assert 'if r.get("category") not in _lp_ledger.LIKELY_BOOKS)' in BUILD
    hc = (ROOT / "homecheck.py").read_text()
    assert 'n_likely = sum(1 for r in rows if r.get("category") in _LB)' in hc
    lp = (ROOT / "engine" / "livepicks.py").read_text()
    assert 'n_likely = sum(1 for r in rows if r.get("category") in LIKELY_BOOKS)' in lp


def test_nothing_retypes_the_likely_book_any_more():
    for path in [ROOT / "mlb_build.py", ROOT / "homecheck.py", *(ROOT / "engine").glob("*.py")]:
        src = path.read_text()
        assert "IN ('main','longshot','likely')" not in src, f"{path.name} retypes the book list"
        assert not re.search(r'get\("category"\) [!=]= "likely"', src), f"{path.name} splits on the paper book alone"
    assert not re.search(r'category [!=]== "likely"\)', APP), "a page split on the paper book alone"


def test_the_page_draws_a_staked_most_likely_bet_under_most_likely():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed"); return
    i = APP.index("function isLikelyBook(")
    fn = APP[i:APP.index("\n}\n", i) + 2]
    split = re.search(r"  const edge = rows\.filter\(.*?\n  const likely = rows\.filter\(.*?\n", APP).group(0)
    prog = fn + """
      const rows = ["main", "longshot", "likely", "likely_live"].map((category) => ({ category }));
    """ + split + """
      console.log(JSON.stringify({ edge: edge.map((r) => r.category), likely: likely.map((r) => r.category) }));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got == {"edge": ["main", "longshot"], "likely": ["likely", "likely_live"]}, got
    assert set(ledger.LIKELY_BOOKS) == {"likely", "likely_live"}, \
        "the ledger grew a Most Likely book the page does not know — add it to isLikelyBook"


def test_the_panel_says_when_the_book_is_staked():
    i = APP.index("function renderLivePicks(")
    body = APP[i:APP.index("\n}\n", i)]
    assert 'const likelyStaked = likely.some((r) => r.category === "likely_live");' in body
    assert "staked with real money on this league" in body
    assert "flat stake with no dollar exposure" in body, "the paper wording stays for a paper book"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
