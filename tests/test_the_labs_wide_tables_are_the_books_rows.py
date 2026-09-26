"""v5: the Lab's three wide tables read as the book's rows.

Measured on every view at 390 with a full backtest, three Lab tables ran
past the phone: the usage ripple by 114px, a mixed-basis card's
"priced against" table by 56px, and the game-lines table by 14px. The
ripple and the game lines also named their markets by their keys —
"rush_yds" — on a public page. Each is the book's row now: the name
in words, the counts under it, the figure a reader looks for on the
right. The calibration table fits a phone and stays a table.
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
    m = re.search(r"^(async )?function " + name + r"\(", APP, re.M)
    assert m, name
    i = m.start()
    return APP[i:APP.index("\n}\n", i) + 2]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const escapeHtml = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
      const toneOf = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
      const _marketWords = {{}};
      {_fn("marketWord")}
      {_fn("labRippleHTML")}
      {_fn("labGameTable")}
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


def test_the_ripple_and_the_game_lines_are_rows_with_names():
    got = _node("""return {
      ripple: labRippleHTML({ markets: {
        rush_yds: { n: 212, n_measured: 148, resid_mean: 6.4, resid_se: 2.1, bets: 61, roi: 0.084, verdict: "clears", reason: "residual over two standard errors" },
        rec_yds: { n: 0, n_measured: 0, verdict: "not enough" } }, measured_at: "2026-09-21T14:21:02" }),
      games: labGameTable({ markets: [
        { market: "spread", games_priced: 2345, mae: 10.42, n_bets: 312, win_rate: 0.522, roi: -0.004 },
        { market: "moneyline", games_priced: 2345, mae: null, n_bets: 401, win_rate: 0.566, roi: 0.018 } ] }),
      none: labGameTable({ unavailable: "no harvested closing lines" }) };""")
    if got is None:
        print("  SKIP node not installed"); return
    r, g = " ".join(got["ripple"].split()), " ".join(got["games"].split())
    for html in (r, g):
        assert "<table" not in html, "a wide table is back"
        assert "rush_yds" not in html and "rec_yds" not in html, "a market printed by its key"
        assert 'style="' not in html.replace('style="opacity:.7"', ""), "an inline style on a row"
    assert r.count('<div class="hd-row lab-row">') == 2 and '<div class="hd-card lab-rows">' in r
    assert "<b>Rush Yds</b>" in r and "212 absence rows · 148 measured · 61 bets judged at +8.4%" in r
    assert '<span class="lab-reason">residual over two standard errors</span>' in r
    assert '<span class="hd-chip good">clears</span> <b>+6.4 ± 2.1</b><span class="hd-vs">actual − close</span>' in r
    assert '<span class="hd-chip">not enough</span> <b>—</b>' in r and "0 absence rows · 0 measured</span>" in r
    assert "prices nothing until a market clears here" in r, "the ripple's standing caveat"
    assert "Measured 2026-09-21" in r
    assert g.count('<div class="hd-row lab-row">') == 2
    assert "<b>Spread</b>" in g and "2,345 games priced · MAE 10.42 vs close" in g
    assert '<b class="neg">-0.4% ROI</b> <span class="hd-vs">312 bets · 52.2%</span>' in g
    assert "<b>Moneyline</b>" in g and "2,345 games priced</span>" in g and '<b class="pos">+1.8% ROI</b>' in g
    assert "no harvested closing lines" in got["none"] and "hd-row" not in got["none"]


def test_the_priced_against_segments_are_rows_too():
    card = _fn("labPropCard")
    assert "<th>Priced against</th>" not in card and "<table class=\"agate\"><thead><tr><th>Priced" not in card
    assert '`<div class="hd-row lab-row">' in card
    assert '<div class="lab-rows"><div class="lab-rows-head">Priced against</div>${seg}</div>' in card
    assert "% ROI</b>" in card and "g.net.toFixed(2)}u" in card, "ROI and net both survive"
    assert "labBins(m)" in card and '<table class="agate lab-bins">' in _fn("labBins"), \
        "the calibration table fits a phone and stays a table"


def test_the_rows_are_styled():
    for rule in (".lab-row .hd-state b.pos { color: var(--good); }",
                 ".lab-row .hd-state b.neg { color: var(--bad); }",
                 ".lab-row .hd-what .lab-reason { font-family: var(--font-sans); color: var(--text-dim); }",
                 ".lab-rows-head { color: var(--text-mute); font-size: var(--fs-2xs); font-weight: 700;"):
        assert rule in CSS, rule


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
