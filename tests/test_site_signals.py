"""The new signals, on the page.

Ethan, 2026-08-09: "all this new data we should be showing on the website
as well for users to see if its usefull information."

Everything built that day reached a terminal command and nothing else.
These are the chips that carry it onto a pick card, and the rules that
keep a chip from reading as a recommendation.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:i + 1400]


def test_both_new_chips_are_rendered_on_a_pick_card():
    """A chip nobody calls is the website version of the problem
    `--data-use` exists to catch.

    Scans EVERY chips row, not the first: several cards have one — the
    pick card, the parlay leg, the long shot — and taking `index()` found
    a different card's row and reported a correctly-wired chip missing.
    """
    rows = []
    for m in re.finditer(r'<div class="chips">', APP):
        rows.append(APP[m.start():APP.index("</div>", m.start())])
    assert rows, "no chips row found at all"
    assert any("veloChip(r)" in r for r in rows), "velocity chip unrendered"
    assert any("firstMoverChip(r)" in r for r in rows), "first-mover unrendered"


def test_the_velocity_chip_is_absent_when_unmeasured():
    """It is computed for pitcher markets only, so most cards have no
    number. An absent chip must mean UNMEASURED — printing a 0.0 would
    claim a reading nobody took, the same error `velo_band` avoids by
    banding None to None."""
    src = _fn("veloChip")
    assert "if (d == null) return \"\";" in src.replace("'", '"')


def test_the_velocity_chip_says_it_does_not_change_the_price():
    """A number on a card reads as a recommendation unless it says
    otherwise, and the claimed edge on this book is still
    indistinguishable from a coin flip."""
    src = _fn("veloChip")
    assert "does not change the price" in src or "nothing prices from it" in src
    assert "injury and mechanics" in src, "the §5 instruction is missing"


def test_the_first_mover_chip_only_fires_for_a_SHARP_book():
    """§4 is about the informed side moving. A recreational book moving
    first is usually a stale number being corrected — noise on a card,
    and worse than nothing because it wears the same badge."""
    src = _fn("firstMoverChip")
    assert "first_mover_sharp" in src
    assert "!m.first_mover_sharp) return" in src.replace(" ", "").replace(
        "!m.first_mover_sharp)return", "!m.first_mover_sharp) return")


def test_the_first_mover_chip_says_it_does_not_price():
    src = _fn("firstMoverChip")
    assert "does not change the price" in src


def test_the_chips_escape_what_they_print():
    """Book names come from a feed. Everything user-visible in this repo
    goes through escapeHtml and these are not exceptions."""
    assert "escapeHtml(m.first_mover)" in _fn("firstMoverChip")


def test_every_icon_the_new_chips_use_exists():
    """A missing icon renders an empty box, silently."""
    for name in ("warn", "signal"):
        assert re.search(rf"^\s+{name}:", APP, re.M), name


def test_velo_delta_reaches_the_board_payload():
    """The chip reads `r.velo_delta`, so the pipeline has to put it on the
    recommendation dict that gets serialised — otherwise the card is
    wired to a field that never arrives."""
    pipe = open(os.path.join(ROOT, "engine", "mlb", "pipeline.py"),
                encoding="utf-8").read()
    assert 'd["velo_delta"]' in pipe


def test_first_mover_reaches_the_board_payload():
    lm = open(os.path.join(ROOT, "engine", "linemoves.py"),
              encoding="utf-8").read()
    assert '"first_mover": rep.first_mover' in lm
    assert '"first_mover_sharp": rep.first_mover_sharp' in lm


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
