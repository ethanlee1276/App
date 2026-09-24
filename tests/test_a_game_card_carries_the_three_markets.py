"""A game card carries the three markets in columns.

Ethan, 2026-09-22: use what the sportsbook apps do about organisation
"without losing information". Every book's game card shows spread,
moneyline and total for both teams in aligned columns; ours carried
the line in a sentence and no moneyline at all. The row reads only
fields the board already put on the game, prints "—" for a market the
board did not price, and prints nothing for a finished game. Where it
draws, the sub-line under the name stops repeating the spread and
total — the same information, once. The Record page gains the
Open / Settled convention: one line saying what is riding, pointing at
the Live tab, from the same journal's count.
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
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _strip(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return _strip(APP[i:min(ends)])


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";\n", i) + 1]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      {_const("MINUS")}
      {_const("RE_SIGN")}
      {_const("trueMinus")}
      {_const("american")}
      {_fn("escapeHtml")}
      {_fn("gameMarketsHTML")}
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


def test_both_teams_three_markets_and_dashes_for_what_the_board_did_not_price():
    got = _node("""
      const full = gameMarketsHTML({ away: "KC", home: "LAC", spread: -3.5, favorite: "KC", total: 47.5, away_ml: -178, home_ml: 150 }, {});
      const noml = gameMarketsHTML({ away: "GB", home: "CHI", spread: -3, total: 44.5 }, {});
      const mlb = gameMarketsHTML({ away: "NYY", home: "BOS", spread: 1.5, favorite: "BOS", total: 8.5, away_ml: 110, home_ml: -128 }, { mlb: true });
      const fin = gameMarketsHTML({ away: "KC", home: "LAC", spread: -3.5, total: 47.5, away_ml: -178, home_ml: 150 }, { isFinal: true });
      const bare = gameMarketsHTML({ away: "KC", home: "LAC" }, {});
      const awayFav = gameMarketsHTML({ away: "DAL", home: "NYG", spread: 6.5, total: 41.5 }, {});
      const cells = (h) => [...h.matchAll(/<b>([^<]*)<\\/b>/g)].map((m) => m[1]);
      const labels = (h) => [...h.matchAll(/<i>([^<]*)<\\/i>/g)].map((m) => m[1]);
      return { full: cells(full), fullLabels: labels(full), noml: cells(noml), mlb: cells(mlb), mlbLabels: labels(mlb),
               fin, bare, awayFav: cells(awayFav), hasRow: full.includes('class="gc-mkts"') };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["hasRow"]
    assert got["fullLabels"] == ["", "Spread", "ML", "Total"]
    assert got["full"] == ["KC", "LAC", "−3.5", "+3.5", "−178", "+150", "O 47.5", "U 47.5"], got["full"]
    assert got["noml"] == ["GB", "CHI", "+3.0", "−3.0", "—", "—", "O 44.5", "U 44.5"], \
        "no favorite named: the negative spread is the home side's"
    assert got["awayFav"][2:4] == ["−6.5", "+6.5"], \
        "no favorite named: a positive spread is the away side's, not the home side's by default"
    assert got["mlb"][2:4] == ["+1.5", "−1.5"] and got["mlbLabels"][1] == "Run line", got["mlb"]
    assert got["fin"] == "", "a finished game's lines are history"
    assert got["bare"] == "", "nothing priced, nothing drawn"


def test_the_card_draws_the_row_and_the_sub_line_stops_repeating_it():
    card = _fn("gameCard")
    assert 'const mkts = gameMarketsHTML(g, { mlb, isFinal: (g.live || {}).state === "final" });' in card
    assert "${mkts}" in card
    assert '${sub ? `<div class="game-sub">${sub}</div>` : ""}' in card, "an empty sub-line is not a blank row"
    assert card.count("if (!mkts && g.total != null)") == 2, "CFB and NBA sub-lines yield the total to the row"
    # MLB also refuses the board's 8.5 filler total and any total on a
    # game already under way (2026-09-24: the live Marlins @ Cubs card).
    assert "const bits = !mkts && g.total != null && g.total_posted !== false && !inPlay" in card, "MLB too"
    assert "const favTxt = (!mkts && g.favorite && g.spread != null)" in card, "and the NFL default"
    assert 'const ouTxt = mkts || inPlay ? "" : g.total != null' in card
    assert card.count('(mkts || inPlay ? "" : "line not posted yet")') == 2, \
        "with the row drawn, an otherwise-empty sub-line says nothing rather than 'not posted'"
    assert ".gc-mkts { display: grid; grid-template-columns: auto repeat(3, minmax(0, 1fr));" in CSS
    assert ".gc-mk b { font-family: var(--font-mono);" in CSS


def test_the_record_page_says_what_is_riding_from_the_same_journal():
    rec = APP[APP.index("async function renderRecord("):]
    rec = _strip(rec[:rec.index("\nfunction ", 10)])
    assert "const ridingNote = o.open" in rec
    assert '<a href="#live" data-view="live">Live tab</a>' in rec
    assert "+ verdict + ridingNote + unstaked + small" in rec, "right under the verdict"
    assert ".rec-riding a { color: var(--brand-2); }" in CSS


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
