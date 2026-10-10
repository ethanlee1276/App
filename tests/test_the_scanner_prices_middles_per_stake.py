"""Middles on the scanner: dollars for the stake typed, grouped by player,
shared legs flagged, sorted, and the other books named.

Audit 2026-09-30, V-19 (roadmap #47). The "Total stake" box sat over the
middles and only the arbitrage rows read it; "+184% both win / -9%" were
per 1u on EACH leg, read as returns on the whole stake; one cheap Over
against three Unders was three unrelated rows, so a reader could take the
shared leg twice; and the stale-line rows said "the other 2 books" without
saying which. These run the shipped functions under node.
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

from engine import marketscan  # noqa: E402


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _node(body):
    node = shutil.which("node")
    if not node:
        return None
    prog = (_fn("scanMiddleSplit") + _fn("scanMiddleGroups") + body)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _m(player, ob, ol, oo, ub, ul, uo, ev=None, gap=1.0):
    return {"player": player, "bet": f"{player} pts", "gap": gap, "ev_per_unit": ev,
            "over": {"book": ob, "line": ol, "odds": oo}, "under": {"book": ub, "line": ul, "odds": uo}}


def test_the_split_is_in_dollars_of_the_stake_typed():
    got = _node("console.log(JSON.stringify(["
                "scanMiddleSplit({over:{odds:-110},under:{odds:-110}}, 100),"
                "scanMiddleSplit({over:{odds:150},under:{odds:-200}}, 300)]));")
    if got is None:
        print("  SKIP node not installed"); return
    even, lop = got
    assert abs(even["so"] - 50) < 1e-9 and abs(even["su"] - 50) < 1e-9
    # -110 both sides: one leg returns 50 * 1.909 = 95.45, so one wins -4.55,
    # both win +90.91, on the WHOLE $100.
    assert abs(even["worst"] - (-4.545)) < 0.01 and abs(even["both"] - 90.91) < 0.01
    # Lopsided: stakes in proportion to 1/decimal, either leg alone pays alike.
    so, su = lop["so"], lop["su"]
    assert abs(so + su - 300) < 1e-9
    assert abs(so * 2.5 - su * 1.5) < 1e-6


def test_grouped_by_player_best_first_shared_legs_flagged():
    rows = [
        _m("Judge", "DK", 1.5, 120, "FD", 2.5, 110, ev=0.01),
        _m("Soto", "MGM", 0.5, 105, "CZR", 1.5, 105, ev=0.04),
        _m("Judge", "DK", 1.5, 120, "BR", 2.5, 105, ev=0.02),     # shares DK Over
        _m("Ohtani", "DK", 0.5, 100, "FD", 1.5, 100, ev=None, gap=2),
        _m("Judge", "PB", 1.5, 100, "FD", 3.5, 100, ev=None, gap=3),
    ]
    got = _node(f"console.log(JSON.stringify(scanMiddleGroups({json.dumps(rows)})));")
    if got is None:
        print("  SKIP node not installed"); return
    assert [g["who"] for g in got] == ["Soto", "Judge", "Ohtani"], [g["who"] for g in got]
    judge = got[1]["list"]
    assert [m["ev_per_unit"] for m in judge] == [0.02, 0.01, None], "measured EV first, then width"
    assert judge[0]["shared"] == [] and judge[1]["shared"] == ["Over at DK"], judge[1]["shared"]


def test_the_row_says_dollars_and_which_ranking():
    body = _fn("scanMiddleRow")
    assert "scanMiddleSplit(m, stake)" in body and "both win ${money(sp.both)}" in body
    assert "not EV-ranked" in body and "fill one of them, not both" in body
    render = _fn("renderScanner")
    assert "scanMiddleGroups(middles)" in render and "scanMiddleRow(list[0], stake)" in render
    # The stake box shows only where a row reads it: arbs and middles.
    assert '(arbs.length || middles.length ? stakeInput : "")' in render


def test_stale_lines_name_the_other_books():
    rec = {"player": "Judge", "market": "hits", "market_label": "Hits",
           "all_lines": [{"book": b, "line": 0.5, "over_odds": o, "under_odds": None}
                         for b, o in (("DK", -150), ("FD", -150), ("MGM", -150), ("CZR", -110))]}
    out = marketscan.stale_quotes([rec])
    assert out and out[0]["book"] == "CZR"
    assert out[0]["other_books"] == ["DK", "FD", "MGM"]
    render = _fn("renderScanner")
    assert "t.other_books.join" in render and "pts cheaper" in render and "pts cheap<" not in render


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
