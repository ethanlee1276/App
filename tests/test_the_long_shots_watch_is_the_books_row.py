"""v5: the Long Shots watch — most likely to score — is the Edge Board's row.

Rendered on the sample board at 390, the watch list crushed five
columns into one line: rank, name and reason squeezed to a sliver, a
tiny chart, then "62% vs 56%", the price and the EV overprinting each
other at the right edge. The shared row's `nowrap` (slice N) beat the
phone's wrap rule, and even wrapped it was a table, not the book's row.

It is the Edge Board's row now: rank, the face, the name over its
reason, the chart against the 0.5 line, the price in the grey pill and
the EV in the green one — grey when the price is not worth taking —
with ours against the book's beneath. It wraps on a phone the way that
row does, and each row rises with the rest.
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


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\ndocument.")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const escapeHtml = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
      const icon = (n) => `<i class="ic-${{n}}"></i>`;
      const teamName = (t) => ({{ GB: "Packers", CHI: "Bears", KC: "Chiefs", BUF: "Bills" }})[t] || t;
      const oddsTxt = (o) => o == null ? "—" : (o > 0 ? "+" + o : String(o));
      const likelySpark = (r, o) => `<svg data-w="${{o.w}}" data-h="${{o.h}}" data-line="${{o.line}}"></svg>`;
      const playerAvatar = (p, t, o) => `<i class="avatar" data-size="${{o.size}}">${{p}}</i>`;
      const reasonLI = (x) => `<li>${{escapeHtml(x)}}</li>`;
      {_fn("watchlistHTML")}
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


WATCH = """[
  { player: "Josh Jacobs", team: "GB", opponent: "CHI", odds: -139, model_prob: 0.6195, implied_prob: 0.5556, ev_per_unit: 0.0652,
    primary_reason: "Soft run defence — +10% vs average", reasons: ["Team implied total 24.8 → 2.63 expected offensive TDs", "Red-zone touch share ~60%"],
    recent_values: [1, 0, 1, 1, 0, 1, 1], caveats: ["Red-zone usage inferred"], headshot: "" },
  { player: "Travis Kelce", team: "KC", opponent: "BUF", odds: 292, model_prob: 0.22, implied_prob: 0.24, ev_per_unit: -0.13,
    primary_reason: "Team implied total 24.8 → 2.63 expected offensive TDs", reasons: [], recent_values: [0, 1], caveats: [] }]"""


def test_the_watch_row_is_the_edge_boards_row():
    got = _node(f"const html = watchlistHTML({WATCH}, false); return {{ html }};")
    if got is None:
        print("  SKIP node not installed"); return
    html = got["html"]
    rows = [m for m in re.split(r'(?=<div class="watch-item">)', html) if m.startswith('<div class="watch-item">')]
    assert len(rows) == 2, "one item per watch row"
    first, second = rows
    assert 'class="ls-row drow hd-row hd-edge watch-door" data-watch-toggle role="button"' in first, "a row with reasons is a door"
    assert 'class="ls-row drow hd-row hd-edge"' in second and "data-watch-toggle" not in second, "no reasons, no door"
    for row in rows:
        assert '<span class="hd-rank">' in row and '<span class="pick-id"><i class="avatar" data-size="30">' in row
        assert '<span class="hd-what"><b>' in row and '<span class="hd-state"><span class="hd-num"><span class="hd-o">' in row
        assert "nowrap" not in row and "rec-row" not in row, "the one-line table row is back"
        head = row[:row.index("</div>")]
        assert "style=" not in head, "an inline style on the row"
    assert '<span class="hd-o">-139</span><span class="hd-p">+7% EV</span>' in first
    fn = _fn("watchlistHTML")
    assert 'class="hd-o">${oddsTxt(r.odds)}</span>' in fn and "american(" not in fn, "the price goes through the one formatter, so the decimal setting reaches it"
    assert '<span class="hd-vs">62% vs 56%</span>' in first
    assert 'data-w="92" data-h="34" data-line="0.5"' in first, "the chart fills the edge slot, against the 0.5 line"
    assert 'title="Touchdowns, last 7 games"' in first
    assert '<span class="hd-o">+292</span><span class="hd-p flat">-13% EV</span>' in second, "a price not worth taking wears the pill in grey"
    assert '<span class="edge-spark"></span>' in second, "two games is not a chart"
    assert "Packers vs Bears" in first and "Soft run defence" in first and "▾" in first
    assert '<div class="watch-why" hidden>' in first and "style=" not in first[first.index("watch-why"):first.index("watch-why") + 40]


def test_the_rows_are_ruled_and_rise_through_their_items():
    assert ".watch-item + .watch-item > .hd-row { border-top: var(--hairline) solid var(--border-soft); }" in CSS
    assert ".watch-item > .hd-edge { animation: rise var(--dur-slow) var(--ease-out) both; }" in CSS
    assert ".watch-item:nth-child(2) > .hd-edge { animation-delay: calc(var(--dur-fast) * .3); }" in CSS
    assert ".hd-p.flat { color: var(--text-mute); border-color: var(--border-soft); background: transparent; }" in CSS
    assert ".watch-why { padding: 2px 14px 12px 44px; }" in CSS
    # …and on a phone the row wraps, because it is the Edge Board's row.
    i = CSS.index("@media (max-width: 700px) {\n  .ls-row.drow { flex-wrap: wrap; }")
    assert ".hd-edge .hd-what { flex: 1 1 150px; min-width: 150px; }" in CSS[i:CSS.index("\n}", i)]


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
