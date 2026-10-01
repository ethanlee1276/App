"""The phone Home's first lines say how the book stands and what tonight
holds, and the banner art no longer costs a phone its first screen.

Audit 2026-09-30, O25 (roadmap #40). Measured at 390x844 before: header,
chips, a 105 px banner image, the four doors, Live now — and the first
record at y=554. After: a record line and tonight's verdict sit directly
under the chips (y≈180), the banner art is neither shown nor fetched on a
phone, and the four doors keep the top of the deck (Ethan, 2026-09-26)
with the stadiums above the picks (2026-09-24) — the audit's own order
yields to those two decisions.
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 3]


def _brief(rec, data, edge=0, likely=0):
    js = ("const escapeHtml = (s) => String(s);\n"
          "const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;\n"
          "const fmtRoi = (x) => `${x >= 0 ? '+' : '\\u2212'}${Math.abs(x * 100).toFixed(1)}%`;\n"
          f"const state = {{ data: {json.dumps(data)} }};\n"
          f"const tonightSignals = () => ({{ props: Array({edge}).fill(1), sharpBets: [], modelBets: [] }});\n"
          f"const oneBoardAllRows = () => Array({likely}).fill(1);\n"
          "let _recMinGraded = 30;\n"
          + _fn("recFloor") + _fn("deckBriefHTML")
          + f"\nconsole.log(JSON.stringify(deckBriefHTML({json.dumps(rec)})));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_record_line_reads_the_same_book_and_floor_as_the_first_ribbon():
    thin = _brief({"min_graded": 30, "overall": {"settled": 0},
                   "pooled_overall": {"settled": 1, "wins": 1, "losses": 0}}, {"x": 1})
    assert "1-0 · 1 of 30 graded — too early to judge" in thin, thin
    full = _brief({"min_graded": 30, "overall": {"settled": 40, "wins": 23, "losses": 17, "roi": 0.051},
                   "pooled_overall": {"settled": 90}}, {"x": 1})
    assert "23-17 · +5.1% ROI over 40 graded bets" in full, full


def test_tonight_says_the_verdict_including_no_edge():
    assert "3 edge picks tonight · 12 on Most Likely" in _brief(None, {"x": 1}, edge=3, likely=12)
    assert "No edge tonight · 12 on Most Likely" in _brief(None, {"x": 1}, likely=12)
    assert "No edge tonight — no bet is a result too" in _brief(None, {"x": 1})
    assert _brief(None, {}) == ""


def test_the_brief_rides_above_the_doors_and_only_on_phones():
    deck = _fn("renderHomeDeck")
    assert 'host.querySelector(\'.hd-sec[data-sec="tools"]\')' in deck and "toolsSec.prepend(br)" in deck
    assert ".hd-brief { display: none; }" in CSS
    i = CSS.index(".hd-brief { display: none; }")
    assert "@media (max-width: 720px) {\n  .hd-brief { display: grid;" in CSS[i:i + 200]


def test_the_banner_art_is_neither_shown_nor_fetched_on_a_phone():
    hero = _fn("brandHeroHTML")
    assert '<source media="(max-width: 720px)" srcset="data:image/gif;base64,' in hero
    assert "<picture>" in hero and "</picture>" in hero
    i = CSS.index("/* The banner art is off on phones")
    assert ".qt-brand-art { display: none; }" in CSS[i:i + 300]


def test_the_deck_order_ethan_set_is_kept():
    i = APP.index("const HOME_DECK_ORDER = ")
    order = json.loads(APP[i + len("const HOME_DECK_ORDER = "):APP.index(";", i)])
    assert order[0] == "tools" and order.index("games") < order.index("likely")


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
