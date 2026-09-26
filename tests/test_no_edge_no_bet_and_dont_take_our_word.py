"""Audit items 4, 6 and 19: lead with verifiability; "No edge. No bet."

Ethan's product audit, 2026-09-23. Item 4: the strongest proposition is
that the model makes a quantified claim, records the price and grades
itself in public — "DON'T TAKE OUR WORD FOR IT. Every pick is
timestamped. Every price is recorded. Every result is graded. Every loss
stays on the board." Item 19: "NO EDGE. NO BET … make that a visible
product philosophy." Item 6: the lede sold three audiences at once.
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
    return APP[i:APP.index("\n}\n", i) + 2]


def test_a_priced_board_that_clears_nothing_says_no_edge_no_bet():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed"); return
    prog = "const state = { data: null };\n" + _fn("noMarketHeading") + """
      const out = {};
      state.data = { generated_from: "live-oddsapi", recommendations: [{ has_market: true }], game_bets: [] }; out.props = noMarketHeading();
      state.data = { generated_from: "live-oddsapi", recommendations: [], game_bets: [{}] }; out.games = noMarketHeading();
      state.data = { generated_from: "live-oddsapi", recommendations: [{ has_market: false }], game_bets: [] }; out.unpriced = noMarketHeading();
      state.data = { generated_from: "schedule-only", game_bets: [{}] }; out.sched = noMarketHeading();
      state.data = null; out.none = noMarketHeading();
      console.log(JSON.stringify(out));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert got["props"] == got["games"] == "No edge. No bet.", got
    assert got["unpriced"] == got["none"] == "Nothing clears the bar right now", "no verdict the model never reached"
    assert got["sched"] == "Not priced yet"


def test_the_plans_page_says_dont_take_our_word_for_it():
    body = _fn("paywallHTML")
    hero = body[body.index('<section class="pw-hero">'):body.index("</section>", body.index('<section class="pw-hero">'))]
    assert hero.index("${pwResultsHTML(rec)}") < hero.index('<div class="pw-verify">'), "under the receipts"
    for line in ("Every pick is timestamped.", "Every price is recorded.", "Every result is graded.",
                 "Every loss stays on the board."):
        assert f'<li>${{iconMark("check", 13)}}<span>{line}</span></li>' in hero, line
    assert "Don’t take our word for it." in hero and 'href="#record"' in hero
    assert ".pw-verify-list .ico-mark { color: var(--good); }" in CSS


def test_the_lede_sells_one_thing():
    body = _fn("paywallHTML")
    lede = " ".join(body[body.index('<p class="pw-lede">'):body.index("</p>", body.index('<p class="pw-lede">'))].split())
    assert "a sports intelligence platform for serious bettors" in lede
    assert "market traders" not in lede and "Fantasy and market tools come with it." in lede


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
