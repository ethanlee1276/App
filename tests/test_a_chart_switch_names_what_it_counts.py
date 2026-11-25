"""A chart switch's count is what its label says (step AFY, 25 November 2026).

A player's chart switch reads each chart's name and its count: "Targets 97", "Shots 356", "Carries 141". The hit
tracker's count is the season's plate appearances and a goalie's save map counts the shots faced, so Aaron Judge's
switch read "Hits 285" over a season of 57 hits. Those two say what they count now: "At the plate 285" and "Shots
faced". The word above a chart's season box (its eyebrow, "RF Hits") is unchanged.

Offline. Run directly: `python3 tests/test_a_chart_switch_names_what_it_counts.py`
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CC = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")


def _kind(name):
    m = re.search(r"\n    " + name + r": \{([^}]*)\}", CC)
    assert m, name
    return m.group(1)


def test_the_two_charts_whose_count_is_not_their_name_say_it():
    spray, saves = _kind("spray"), _kind("saves")
    assert 'chip: "Hits", tab: "At the plate"' in spray and 'noun: "plate appearances"' in spray
    assert 'chip: "Saves", tab: "Shots faced"' in saves and 'noun: "shots faced"' in saves
    for name in ("carries", "routes", "passes", "pitches", "shots", "kicks"):
        assert "tab:" not in _kind(name), f"{name}: its chip already names its count"


def test_the_switch_and_its_waiting_chips_read_the_tab():
    assert "const tabOf = (k) => kindOf(k, S.sport).tab || kindOf(k, S.sport).chip;" in CC
    i = CC.index("  function kindBar() {")
    bar = CC[i:CC.index("\n  }\n", i)]
    assert bar.count("${esc(tabOf(k))}") == 2 and "kindOf(k, S.sport).chip" not in bar


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
