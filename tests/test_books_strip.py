"""Odds shopping, on the card and the prop page.

Ethan, 2026-09-05: "odds shopping on the card". Every priced row has
carried every book's quote since the odds pull (`all_lines`); the card
only ever named the best. The pick's side is now priced at each book,
best first — so "don't add more at −110" comes with "FanDuel still has
−118" — with quotes at another line listed apart, never mixed into the
ranking. Only real quotes: no proxy, no unquoted side. Run for real in
node (skipped without it).
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
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    i = APP.index("const payoutOf = ")
    prog = f"""
      const trueMinus = (s) => String(s).replace("-", "−");
      {APP[APP.index("const american = (o) =>"):APP.index(chr(10), APP.index("const american = (o) =>"))]}
      const icon = (n) => `<i data-icon="${{n}}"></i>`;
      const state = {{ data: {{ odds_status: {{ at: "10:40 AM" }} }} }};
      {_fn("escapeHtml")}
      const escapeAttr = escapeHtml;
      {APP[i:APP.index(chr(10), i)]}
      {_fn("quotesForSide")}
      {_fn("booksStripHTML")}
      {_fn("booksTableHTML")}
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


ROW = """{ player: "Ja'Marr Chase", side: "UNDER", line: 58.5, book: "FanDuel", odds: -118, all_lines: [
    { book: "DraftKings", line: 58.5, over_odds: -110, under_odds: -120 },
    { book: "FanDuel", line: 58.5, over_odds: -114, under_odds: -118 },
    { book: "BetMGM", line: 58.5, over_odds: -105, under_odds: -125 },
    { book: "Caesars", line: 57.5, over_odds: -110, under_odds: -110 },
    { book: "proxy", line: 58.5, over_odds: -110, under_odds: -110 },
    { book: "Bovada", line: 58.5, over_odds: -115, under_odds: 0 },
    { book: "PointsBet", line: 58.5, over_odds: -112, under_odds: null },
  ] }"""


def test_the_picks_side_is_priced_at_each_book_best_first_and_only_real_quotes():
    got = _node(f"""
      const q = quotesForSide({ROW});
      const over = quotesForSide({{ ...{ROW}, side: "OVER" }});
      return {{ same: q.same.map((x) => [x.book, x.odds]), other: q.other.map((x) => [x.book, x.line, x.odds]),
               best: q.best.book, over: over.same.map((x) => [x.book, x.odds]) }};""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["same"] == [["FanDuel", -118], ["DraftKings", -120], ["BetMGM", -125]], got["same"]
    assert got["best"] == "FanDuel"
    assert got["other"] == [["Caesars", 57.5, -110]], "a quote at another line is a different bet"
    assert not any(b in ("proxy", "Bovada", "PointsBet") for b, _ in got["same"]), "a proxy is not a book; an unquoted side is not a price"
    assert got["over"] == [["BetMGM", -105], ["DraftKings", -110], ["PointsBet", -112], ["FanDuel", -114], ["Bovada", -115]], got["over"]


def test_the_strip_and_the_table_say_the_shop_and_hide_under_two_quotes():
    got = _node(f"""
      const strip = (h) => h.replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim();
      const one = {{ side: "OVER", line: 1.5, all_lines: [{{ book: "FanDuel", line: 1.5, over_odds: -110, under_odds: -110 }}] }};
      return {{ strip: strip(booksStripHTML({ROW})), raw: booksStripHTML({ROW}), table: booksTableHTML({ROW}),
               one: booksStripHTML(one), oneT: booksTableHTML(one), none: booksStripHTML({{}}), nul: booksStripHTML(null) }};""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["strip"] == "UNDER 58.5 by book FanDuel −118 DraftKings −120 BetMGM −125 +1 at other line", got["strip"]
    assert 'class="bs-q best"' in got["raw"] and got["raw"].count('class="bs-q') == 3
    assert "Shop the price" in got["table"] and "from the 10:40 AM odds pull" in got["table"]
    assert got["table"].count("<tr class=\"best\">") == 1 and "At another line — a different bet" in got["table"]
    assert got["table"].index("FanDuel") < got["table"].index("DraftKings") < got["table"].index("Caesars")
    assert got["one"] == "" and got["oneT"] == "" and got["none"] == "" and got["nul"] == ""


def test_the_card_and_the_prop_page_draw_it():
    card = _fn("cardHTML")
    assert "${booksStripHTML(r)}" in card
    assert card.index("${booksStripHTML(r)}") < card.index("${tfRow(r)}"), "under the chips, above the reasons"
    i = APP.index("function renderPropPage()")
    page = APP[i:APP.index("\n/* ====", i)]
    assert "${booksTableHTML(r)}" in page
    assert page.index("${propAnalysis(r)}") < page.index("${booksTableHTML(r)}") < page.index("Last ${shown} game")
    for sel in (".bs-strip", ".bs-q.best", ".pp-books tr.best td", ".pp-books tr.bs-sep td"):
        assert sel in CSS, sel


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
