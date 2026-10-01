"""Every word the boards lean on is defined, and the tour has a phone door.

Audit 2026-09-30, V-15 / O23 (roadmap #39). Most Likely, Edge, Worth a
look, Top/Strong, journaled, CLV, calibration, Zeno, Pikkit and "u" were
used without definition; the tour never showed on a phone (by Ethan's
choice, 2026-09-22) and had no other door there; and its first card
described a single board of "pick cards". Now: a two-line legend on the
Edge and Most Likely boards, a glossary on the Features page with its own
menu entry, the tour offered from the More menu, and card 1 rewritten.
"""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
HTML = (ROOT / "web" / "index.html").read_text()


def _glossary():
    i = APP.index("const GLOSSARY = [")
    j = APP.index("];\n", i) + 2
    out = subprocess.run(["node", "-e", APP[i:j] + "\nconsole.log(JSON.stringify(GLOSSARY));"],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return dict(json.loads(out.stdout))


def test_the_glossary_defines_every_word_the_audit_named():
    g = _glossary()
    for term in ("Most Likely", "Edge pick", "Edge", "EV", "Worth a look", "Pick of the Day",
                 "Riding", "Journaled", "u (unit)", "Paper", "Probation", "CLV", "Calibration",
                 "Brier", "Zeno", "Pikkit", "Prediction market"):
        assert term in g and len(g[term]) > 30, term
    assert "Top, Strong, Solid, Slight" in g["Most Likely"]


def test_both_boards_carry_a_two_line_legend_with_a_glossary_door():
    for view in ("view-edge", "view-likely"):
        i = HTML.index(f'id="{view}"')
        sec = HTML[i:HTML.index("</section>", i)]
        legend = re.search(r'<p class="board-legend">(.*?)</p>', sec, re.S)
        assert legend, view
        assert "data-glossary" in legend.group(1), view
    assert "beats the book’s price" in HTML and "ranks bets by our chance they hit" in HTML


def test_the_glossary_lives_on_the_features_page_and_opens_from_anywhere():
    i = APP.index("function renderFeatures(")
    body = APP[i:APP.index("\n}\n", i)]
    assert "${glossaryHTML()}" in body and 'href="#glossary" data-glossary' in body
    assert 'id="glossary"' in APP
    assert 'e.target.closest("[data-glossary]")' in APP and "openGlossary();" in APP


def test_the_tour_has_a_door_on_phones_and_card_one_names_both_boards():
    assert 'id="more-tour">Take the tour</button>' in HTML
    assert 'id="more-glossary" data-glossary>Glossary</button>' in HTML
    assert 'tour.addEventListener("click", () => { moreSheetOpen(false); tourOpen(0); });' in APP
    i = APP.index("function tourSteps(")
    first = APP[i:APP.index("},", i)]
    assert '"Two boards, two questions"' in first


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
