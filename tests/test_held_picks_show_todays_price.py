"""A held Most Likely pick keeps its seat and its number, and shows
today's price. Ethan, 2026-09-27: "the most likely bets all just stay in
the same spot and didn't seem like they are updating" — asked what he
wanted: "keep them in place but refresh the prices"."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    depth, j = 0, APP.index("{", i)
    for k in range(j, len(APP)):
        depth += APP[k] == "{"
        depth -= APP[k] == "}"
        if depth == 0:
            return APP[i:k + 1]
    raise AssertionError(name)


def test_the_board_refreshes_held_prices_as_it_loads():
    assert "refreshLikelyPrices(d);" in _fn("normalizeSlate")
    if not shutil.which("node"):
        return
    prog = ("var escapeHtml=(s)=>String(s==null?'':s);var american=(o)=>(o>0?'+':'')+o;\n"
            + _fn("refreshLikelyPrices") + "\n" + _fn("likelyNowHTML") + """
      const held = { locked: true, now_listed: true, odds: -150, book: "DraftKings", now_odds: -190, now_book: "FanDuel" };
      const gone = { locked: true, now_listed: false, odds: -140, book: "BetMGM" };
      const fresh = { odds: -120, book: "Caesars" };
      const d = { most_likely: [held, gone, fresh], likely_board: { rows: [held] } };
      refreshLikelyPrices(d);
      refreshLikelyPrices(d);
      console.log(JSON.stringify({ held, gone, fresh, line: likelyNowHTML(held, true) }));""")
    path = os.path.join(tempfile.mkdtemp(), "s.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-500:]
    got = json.loads(out.stdout)
    h = got["held"]
    assert (h["odds"], h["book"], h["posted_odds"], h["posted_book"]) == (-190, "FanDuel", -150, "DraftKings"), \
        "today's price up front, the posted one kept — and only once, however often it loads"
    assert got["gone"]["odds"] == -140 and "posted_odds" not in got["gone"], "no book lists it: the posted price stands"
    assert got["fresh"] == {"odds": -120, "book": "Caesars"}, "a pick that is not held is untouched"
    assert got["held"]["price_refreshed"] is True
    assert got["line"] == " · posted -150"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
