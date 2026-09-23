"""Over / Under: every prop we price, both sides side by side, as cards or a list.

Ethan, 2026-09-23, on Rithmm: "I like how they have the over and under
props shown side by side with a card view and a list view you can
switch between."

What this file holds:

  * OUR SIDE is the row's own side, price and chance.
  * THE OTHER SIDE is the same book at the same line, else the best
    price at that line, and its chance is the rest of ours ONLY on a
    half-point line — on a whole number a push takes some of it, and a
    number we did not compute is not drawn.
  * One row per player, market and line; unpriced rows are left out.
  * The view is a real destination: sidebar, More sheet, features page,
    and the Cards | List choice is remembered.
  * Not called "Player Props": Most Likely is props too.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
HTML = (ROOT / "web" / "index.html").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _strip(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return _strip(APP[i:min(ends)])


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
      const escapeAttr = escapeHtml;
      const oddsTxt = (v) => (v > 0 ? "+" : "") + v;
      {_fn("mbDecimal")}
      {_fn("ouHalfLine")}
      {_fn("ouSides")}
      {_fn("propsRows")}
      {_fn("ouSideHTML")}
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


ROW = """{ player: "Josh Allen", market: "pass_yds", side: "UNDER", line: 259.5, odds: -108,
  book: "FanDuel", hit_prob: 0.5451,
  all_lines: [{ book: "DraftKings", line: 258.5, over_odds: -110, under_odds: -110 },
              { book: "FanDuel", line: 259.5, over_odds: -112, under_odds: -108 },
              { book: "BetMGM", line: 259.5, over_odds: 105, under_odds: -130 }] }"""


def test_our_side_is_ours_and_the_other_side_is_the_same_book_at_the_same_line():
    got = _node(f"return ouSides({ROW});")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["ours"] == "under"
    assert got["under"] == {"odds": -108, "book": "FanDuel", "prob": 0.5451, "ours": True}
    assert got["over"]["odds"] == -112 and got["over"]["book"] == "FanDuel", \
        "the same book, even though BetMGM pays more on the over"
    assert abs(got["over"]["prob"] - 0.4549) < 1e-9 and got["over"]["ours"] is False


def test_without_our_book_the_other_side_is_the_best_price_at_that_line():
    got = _node(f"""const r = {ROW}; r.book = "Caesars";
      const s = ouSides(r);
      const none = ouSides({{ ...r, all_lines: [{{ book: "DraftKings", line: 258.5, over_odds: -110, under_odds: -110 }}] }});
      return {{ s, none }};""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["s"]["over"]["odds"] == 105 and got["s"]["over"]["book"] == "BetMGM", "best payout at 259.5"
    assert got["none"]["over"]["odds"] is None and got["none"]["over"]["book"] == "", \
        "another line's price is not this line's"


def test_the_rest_of_our_chance_is_drawn_only_where_a_push_cannot_happen():
    got = _node("""
      const whole = ouSides({ side: "OVER", line: 6, odds: -120, book: "DK", hit_prob: 0.6,
        all_lines: [{ book: "DK", line: 6, over_odds: -120, under_odds: 100 }] });
      const noProb = ouSides({ side: "OVER", line: 6.5, odds: -120, book: "DK",
        all_lines: [{ book: "DK", line: 6.5, over_odds: -120, under_odds: 100 }] });
      return { whole, noProb, half: [ouHalfLine(6.5), ouHalfLine(-3.5), ouHalfLine(6), ouHalfLine("x")],
               cell: ouSideHTML("Over", whole.under), ours: ouSideHTML("Over", whole.over) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["whole"]["under"]["prob"] is None and got["whole"]["under"]["odds"] == 100
    assert got["whole"]["over"]["prob"] == 0.6
    assert got["noProb"]["over"]["prob"] is None and got["noProb"]["under"]["prob"] is None
    assert got["half"] == [True, True, False, False]
    assert '<span class="ou-pct">—</span>' in got["cell"] and "no push-free line" in got["cell"]
    assert 'class="ou-side ours"' in got["ours"] and '<span class="ou-pct">60%</span>' in got["ours"]


def test_one_row_per_prop_priced_rows_only_likeliest_first():
    got = _node("""
      return propsRows({ recommendations: [
        { player: "A", market: "rec", line: 4.5, side: "OVER", hit_prob: 0.52 },
        { player: "A", market: "rec", line: 4.5, side: "UNDER", hit_prob: 0.48 },
        { player: "B", market: "rec", line: 3.5, side: "OVER", hit_prob: 0.61 },
        { player: "C", market: "rec", line: 2.5, side: "OVER", hit_prob: 0.7, has_market: false },
        { player: "D", market: "rec", line: null, side: "OVER", hit_prob: 0.7 }] })
        .map((r) => r.player + r.side);""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got == ["BOVER", "AOVER"], got
    assert _node("return propsRows(null).length;") == 0


def test_cards_or_a_list_remembered_and_the_page_is_a_real_destination():
    render = _fn("renderProps")
    assert 'localStorage.setItem("qb.propsView", _propsView)' in render
    assert 'mode === "list"' in render and "shown.map(ouRowHTML)" in render and "shown.map(ouCardHTML)" in render
    assert 'localStorage.getItem("qb.propsView")' in _fn("propsViewMode")
    assert "renderEdgeBoard();\n  renderProps();" in APP, "drawn with the other boards"
    assert '"live", "props", "edge"' in APP[APP.index("const VIEW_ORDER"):][:300]
    assert '["Odds", ["view:props", "view:edge",' in APP
    assert 'data-view="props"' in HTML and 'id="view-props"' in HTML and 'id="props-body"' in HTML
    sb = HTML[HTML.index('data-view="props"'):]
    assert sb[:sb.index("</button>")].rstrip().endswith("Over / Under"), 'not "Player Props"'
    assert '"Over / Under", "Every prop we price tonight' in APP, "on the features page"
    for card in (_fn("ouCardHTML"), _fn("ouRowHTML")):
        assert "${propAttrs(r)}" in card, "every prop is a door to its page"
    assert ".ou-side.ours { border-color: var(--brand-2);" in CSS
    assert ".ou-grid { display: grid;" in CSS


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
