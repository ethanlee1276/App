"""v5: the edge rows read like the book, everywhere.

Ethan, 2026-09-22: "the section for the edge bets on each page." The
Best bets box on the home (a pick, a riding position, an on-deck
hitter) and the Edge Board's row were inline-styled rows. They now
share the deck's row: rank, mark, grade; the bet with its game and
reason beneath; the price in the grey pill and the number in the green
one. Same fields, same doors, same chart. Nothing ranked that was not.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
FLAT = re.sub(r"^\s*//.*$", "", re.sub(r"/\*.*?\*/", "", APP, flags=re.S), flags=re.M)


def _best():
    i = APP.index("async function renderBestBets(")
    return APP[i:APP.index("\nfunction ", i)]


def _row(name, end):
    b = _best()
    i = b.index(f"const {name} = ")
    return b[i:b.index(end, i)]


def test_the_pick_row_is_the_decks_row():
    row = _row("pickRow", "const ")
    row = _best()[_best().index("const pickRow = "):]
    row = row[:row.index("</div>`;") + 8]
    assert '<div class="hd-row hd-pick ${p.open ? "openable" : ""}"${p.open || ""}>' in row
    assert '<span class="hd-rank">${i + 1}</span>' in row, "the rank leads — this list means act on these"
    assert '<span class="hd-what"><b>${escapeHtml(p.label)}</b>' in row
    assert '<span class="hd-p">${escapeHtml(p.metric)}</span>' in row, "the number in the green pill"
    assert '<b class="hd-stake">${stakeText(p.stake)}</b>' in row
    assert 'style="' not in row, "no inline styles left on the row"


def test_the_riding_row_keeps_its_dot_grade_and_note_and_no_rank():
    row = _best()[_best().index("const ridingRow = "):]
    row = row[:row.index("const pickRow =")]
    assert '<span class="hd-rank">·</span>' in row, "a riding position is not ranked"
    assert '<span class="grade riding">RIDING</span>' in row
    assert "ridingMoveCopy(b, cur)" in row and 'class="pick-moved"' in row
    assert '<span class="hd-chip">riding</span>' in row
    assert 'style="' not in row


def test_the_on_deck_row_says_lineup_pending_as_a_chip():
    row = _best()[_best().index("const earlyRow = "):]
    row = row[:row.index("</div>`;") + 8]
    assert '<div class="hd-row hd-pick openable"${propAttrs(r) || ""}>' in row
    assert '<span class="hd-p">${signedPct(r.edge)}</span>' in row
    assert '<span class="hd-chip warn">LINEUP PENDING</span>' in row, "the honest words, in the capitals test_early_board pins"
    assert "every gate cleared" in row, "the reason is kept"
    assert 'style="' not in row


def test_the_edge_board_row_is_the_decks_row_with_its_chart():
    i = APP.index("function edgeRowHTML(")
    fn = APP[i:APP.index("\n}\n", i)]
    assert '<div class="ls-row drow hd-row hd-edge ${r.open ? "openable" : ""}"${r.open || ""}>' in fn
    assert '<span class="hd-rank">${i + 1}</span>' in fn and '<span class="pick-id">${r.mark || ""}</span>' in fn
    assert "${spark}" in fn and "gamelogBars(r.vals" in fn and "line: r.line" in fn, "the chart, against its line"
    assert '<span class="hd-o">${oddsTxt(r.odds)}</span><span class="hd-p">+${evPct}% EV</span>' in fn
    assert "% vs ${(r.implied * 100).toFixed(0)}%" in fn and "r.rec ?" in fn, "ours against the price, and the tick the headline counts"
    assert "style=" not in fn.split("return `")[1], "no inline styles left on the row"


def test_the_rows_are_styled_and_rise_with_the_rest():
    for rule in (".hd-pick, .hd-edge { padding: 12px 14px; gap: 10px; align-items: flex-start; }",
                 ".hd-rank { flex: 0 0 18px; font-family: var(--font-mono);",
                 ".hd-vs { font-family: var(--font-mono);", ".hd-chip.warn { color: var(--warn); }",
                 ".hd-stake { color: var(--good);"):
        assert rule in CSS, rule
    assert ".card > .hd-pick, .card > .hd-edge { animation: rise" in CSS
    assert ".hd-pick .hd-what span { font-family: var(--font-sans); }" in CSS, "a reason is a sentence, not a figure"
    i = CSS.index("@media (max-width: 700px) {\n  .ls-row.drow { flex-wrap: wrap; }")
    phone = CSS[i:CSS.index("\n}", i)]
    assert ".hd-edge .hd-what { flex: 1 1 150px; min-width: 150px; }" in phone, "on a phone the bet's column shrank to a sliver"


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
