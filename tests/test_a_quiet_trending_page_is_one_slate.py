"""v5: a quiet Trending page is one slate, and the slate is a rule, not a box.

Rendered on an empty board, Trending drew three cards — Trending Up,
Cooling Off, Biggest Edges — each holding "No movers." centred in 24px
of nothing. Without rows the page is one empty slate, with the same
doors as every other empty board; with rows, a column that has none
says so in the empty-panel voice, on the baseline, no box.

And the slate itself: it is ruled off by a top hairline only, and a
radius on a one-sided border curves the rule down at both ends. On the
Streak, Alerts, Prediction Market and Rocket Radar pages that read as
the top edge of a card whose sides had vanished. No radius.
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
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const escapeHtml = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
      const escapeAttr = (s) => escapeHtml(s).replace(/"/g, "&quot;");
      const icon = (n) => `<i class="ic-${{n}}"></i>`;
      const iconMark = (n) => `<i class="im-${{n}}"></i>`;
      const signedPct = (v) => (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%";
      const passesFilters = () => true;
      const gamelogBars = () => "<svg></svg>";
      const revealChildren = () => {{}};
      const host = {{ innerHTML: "" }};
      const document = {{ getElementById: () => host }};
      const state = {{ data: {{ recommendations: [] }} }};
      {_fn("panelEmpty")}
      {_fn("trendRow")}
      {_fn("renderTrending")}
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


def test_without_a_mover_anywhere_the_page_is_one_slate():
    got = _node("""
      renderTrending(); const quiet = host.innerHTML;
      state.data.recommendations = [{ player: "Josh Allen", team: "BUF", market_label: "Pass yds", trend_delta: 1.2, edge: 0.05, logs: [] }];
      renderTrending(); const some = host.innerHTML;
      return { quiet, some };""")
    if got is None:
        print("  SKIP node not installed"); return
    q = got["quiet"]
    assert q.count('class="empty-slate"') == 1 and "trend-col" not in q, "three boxes around nothing"
    assert "Nothing moving yet" in q and "No movers." not in q
    s = got["some"]
    assert s.count('class="trend-col"') == 3 and s.count('class="trow"') == 2, "one riser is a riser and an edge"
    assert s.count('class="panel-empty"') == 1, "the column with nothing says so on the baseline"
    assert 'class="empty"' not in s and "padding:24px" not in s, "the centred box is back"
    assert "No movers on tonight’s board." in s


def test_the_slate_is_a_rule_not_a_box():
    i = CSS.index(".empty-slate { text-align: left;")
    rule = CSS[i:CSS.index("}", i)]
    assert "border-top: var(--hairline) solid var(--border)" in rule
    assert "border-radius: 0" in rule, "a radius on a one-sided border curves the rule"
    # …and nothing later in the cascade hands it a radius back.
    for m in re.finditer(r"([^{}]*)\{([^{}]*border-radius:\s*var\(--radius[^)]*\)[^{}]*)\}", CSS):
        sel = m.group(1)
        assert not re.search(r"(^|,)\s*\.empty-slate\s*($|,)", sel), f"the slate is back in a radius rule: {sel.strip()[:60]}"


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
