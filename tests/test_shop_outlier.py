"""A price off the field is not shopped, and the book is named.

Ethan, 2026-09-04: "Cam Edward's on the Michigan state Spartans has a
-300 line to score a touchdown but on our site we are showing -155."
Read from the droplet's own cached payload on 09-05: Hard Rock -155,
FanDuel -260, DraftKings -270, Caesars -280, all read in the same pull.
One soft book 100+ cents off the field, and the shop crowned it —
because the shop is a `max`, and an outlier is by construction the best
number. The third refusal with that shape (after the dead zone and the
sharp reference): a quote sitting more than OUTLIER_GAP under the median
of the OTHER books at the same line is left out, in both touchdown
shops, and on the card's strip. The college row names the refused book.
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

from engine import odds as O                                            # noqa: E402
from engine.models import SportsbookLine                                # noqa: E402
from engine.sources.oddsapi import best_scorer_price                    # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
TDS = (ROOT / "engine" / "cfb" / "tds.py").read_text()

#: The Cam Edwards field, as the box read it.
CAM = [("Hard Rock", -155), ("FanDuel", -260), ("DraftKings", -270), ("Caesars", -280)]


def test_the_measured_case_is_flagged_and_only_it():
    flags = O.field_outliers([o for _, o in CAM])
    assert flags == [True, False, False, False], flags
    # the gap the constant was set from: 73.0 - 60.8 = 12.2 points
    med = sorted(O.american_to_prob(o) for _, o in CAM[1:])[1]
    assert round(100 * (med - O.american_to_prob(-155)), 1) == 12.2
    assert O.OUTLIER_GAP == 0.10 and O.OUTLIER_MIN_BOOKS == 3


def test_an_ordinary_shopping_spread_is_never_flagged():
    assert O.field_outliers([-200, -230, -250, -260]) == [False] * 4, "a 5-point spread is a shop, not a stray"
    assert O.field_outliers([+120, +105, +110]) == [False] * 3
    assert O.field_outliers([-110, -115, -105, -108, -112]) == [False] * 5


def test_two_books_are_a_disagreement_not_a_field():
    assert O.field_outliers([-155, -280]) == [False, False]
    assert O.field_outliers([-155]) == [False]
    assert O.field_outliers([]) == []


def test_leave_one_out_so_the_stray_cannot_drag_the_field():
    # A three-book field: the others' median is 71.0% and -155 sits 10.2
    # under it. With the stray IN its own median the middle price drops
    # to 70.6% and the gap to 9.8 — the stray talks itself under the bar.
    assert O.field_outliers([-155, -240, -250]) == [True, False, False]
    assert O.field_outliers([-155, -260, -280, -300]) == [True, False, False, False]
    # A price ABOVE the field (worse for the bettor) is never an outlier:
    # nobody is harmed by a book we would not shop anyway.
    assert O.field_outliers([-400, -260, -270, -280]) == [False] * 4


def test_unquotable_prices_are_neither_flagged_nor_part_of_the_field():
    assert O.field_outliers([0, -155, -260]) == [False] * 3, "0 is the unquoted-side sentinel; two real prices are not a field"
    assert O.field_outliers([0, -155, -260, -270]) == [False, True, False, False], "three real prices are, and the sentinel is never one"
    assert O.field_outliers([-97, -155, -260, -270, -280]) == [False, True, False, False, False]
    assert O.field_outliers(["x", -155, -260, -270, -280]) == [False, True, False, False, False]


def test_the_college_scorer_shop_refuses_the_stray_and_names_it():
    quotes = [{"book": b, "yes_odds": o, "no_odds": None} for b, o in CAM]
    best = best_scorer_price(quotes)
    assert best["book"] == "FanDuel" and best["yes_odds"] == -260, best
    assert best["refused"] == [{"book": "Hard Rock", "yes_odds": -155, "gap_pts": 12.2}], best["refused"]
    # two books: no field, Hard Rock wins as before and nothing is refused
    two = best_scorer_price(quotes[:2])
    assert two["book"] == "Hard Rock" and "refused" not in two
    # the sharp reference is still never the answer, and never in the field
    sharp = best_scorer_price(quotes + [{"book": "Pinnacle", "yes_odds": -150, "no_odds": None}])
    assert sharp["book"] == "FanDuel" and [r["book"] for r in sharp["refused"]] == ["Hard Rock"]
    # the input is untouched
    assert all("refused" not in q for q in quotes)


def _ln(book, over, line=0.5, under=0):
    return SportsbookLine(book=book, line=line, over_odds=over, under_odds=under)


def test_the_nfl_touchdown_shop_refuses_the_same_stray():
    lines = [_ln(b, o) for b, o in CAM]
    best = O.best_over_line(lines)
    assert best.book == "FanDuel" and best.odds == -260, best
    assert O.best_over_line(lines[:2]).book == "Hard Rock", "two books: no field to be off"


def test_a_different_line_is_a_different_bet_and_never_the_field():
    # -155 at 1.5 is a worse bet at a higher line, not a stray at 0.5
    lines = [_ln("Hard Rock", -155, line=1.5), _ln("FanDuel", -260), _ln("DraftKings", -270), _ln("Caesars", -280)]
    best = O.best_over_line(lines)
    assert best.line == 0.5 and best.book == "FanDuel"
    # a 2-book group at another line is never flagged; the lowest line still wins
    lines = [_ln("A", +100, line=0.5), _ln("B", -300, line=0.5), _ln("C", -155, line=1.5), _ln("D", -280, line=1.5)]
    assert O.best_over_line(lines).book == "A"


def test_the_under_shop_mirrors_it():
    lines = [SportsbookLine(book=b, line=0.5, over_odds=-110, under_odds=o) for b, o in CAM]
    assert O.best_under_line(lines).book == "FanDuel"


def test_the_college_row_carries_the_refusal_and_says_it():
    assert 'shop_refused = list(best.get("refused") or [])' in TDS
    assert '"shop_refused": shop_refused,' in TDS
    assert "not shopped — " in TDS and "points off the other books" in TDS
    i = TDS.index("for rq in shop_refused:")
    assert i < TDS.index('"shop_refused": shop_refused,'), "the sentence is on the reasons the row carries"


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
      const OUTLIER_GAP = 0.10;
      {_fn("impliedOf")}
      {_fn("fieldOutliers")}
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


def test_the_page_applies_the_same_rule_and_never_crowns_the_stray():
    assert "const OUTLIER_GAP = 0.10;" in APP
    got = _node("""
      const r = { side: "OVER", line: 0.5, all_lines: [
        { book: "Hard Rock", line: 0.5, over_odds: -155, under_odds: 0 },
        { book: "FanDuel", line: 0.5, over_odds: -260, under_odds: 0 },
        { book: "DraftKings", line: 0.5, over_odds: -270, under_odds: 0 },
        { book: "Caesars", line: 0.5, over_odds: -280, under_odds: 0 } ] };
      const q = quotesForSide(r);
      return { flags: fieldOutliers([-155, -260, -270, -280]), two: fieldOutliers([-155, -280]),
               best: q.best.book, order: q.same.map((x) => x.book + (x.outlier ? "*" : "")),
               strip: booksStripHTML(r), table: booksTableHTML(r) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["flags"] == [True, False, False, False] and got["two"] == [False, False]
    assert got["best"] == "FanDuel", got
    assert got["order"] == ["FanDuel", "DraftKings", "Caesars", "Hard Rock*"], got["order"]
    assert 'class="bs-q best"' in got["strip"] and "FanDuel" in got["strip"].split('class="bs-q best"')[1][:40]
    assert 'class="bs-q off"' in got["strip"] and "<i>off the field</i>" in got["strip"]
    assert "off the field — not shopped" in got["table"] and got["table"].count("best price") == 1
    assert ".bs-q.off {" in CSS and ".pp-books tr.off td" in CSS


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
