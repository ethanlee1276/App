"""Audit items 1 and 10: the menu speaks the audit's groups, and the
switches that folded under Filters are gone.

Ethan's product audit, 2026-09-23: "I'd reduce the primary navigation to
roughly: HOME, PICKS, ODDS, RESEARCH, MY BOOK", and of the two sidebar
switches, "Those feel like internal application controls … settings
leaking into the landing experience."

The sidebar's folds read Odds, Research, My Book and Proof (the fold ids
are unchanged, so a reader's remembered folds survive), and the phone's
More sheet is grouped Picks · Odds · Research · My Book · Proof. The
High Confidence and Parlay Mode cards folded under a shut Filters heading
until both left on 2026-10-31: Parlays became a page of its own, and High
Confidence gave way to the ranked Most Likely list (Ethan: "we have most
likely picks that are ranked ... so we don't need that anymore"). Predict,
Fantasy and Radar stay where Ethan put them on 2026-09-10 (the audit's item
6 is his call).
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
HTML = (ROOT / "web" / "index.html").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
SIDEBAR = HTML[HTML.index('id="sidebar"'):HTML.index("</aside>")]


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_the_folds_read_the_audits_words_and_keep_their_ids():
    heads = re.findall(r'data-fold="([a-z]+)"\s+type="button" aria-expanded="(?:true|false)">([A-Za-z ]+)\n', SIDEBAR)
    assert heads == [("research", "Odds"), ("library", "Research"), ("tools", "My Book"),
                     ("proof", "Proof")], heads
    assert ">Betting\n" not in SIDEBAR and ">Library\n" not in SIDEBAR


def test_the_filters_fold_left_with_its_last_switch():
    """A heading over nothing is a control that does nothing."""
    assert 'data-fold="filters"' not in SIDEBAR and 'id="sb-filters-n"' not in SIDEBAR
    assert 'id="sb-hcm"' not in SIDEBAR and 'id="pz-toggle"' not in SIDEBAR
    assert "function paintFilterCount" not in APP and ".sb-filters-head" not in CSS
    # The footer keeps the foot of the column the fold used to hold.
    assert ".sb-foot { margin-top: auto;" in CSS
    # The side apps stay where Ethan put them (2026-09-10).
    assert SIDEBAR.index('<div class="sb-apps"') < SIDEBAR.index('id="sport-switch"')


def test_the_phone_sheet_uses_the_same_groups():
    i = APP.index("const MORE_GROUPS = [")
    block = APP[i:APP.index("];", i)]
    titles = re.findall(r'^\s*\["([A-Za-z ]+)",', block, re.M)
    assert titles == ["Picks", "Odds", "Research", "My Book", "Proof"], titles
    for ref in ("view:likely", "view:longshots", "view:parlays", "view:zeno", "view:edge", "subtab:gamebets", "view:scanner",
                "view:futures", "sport:mybets", "view:alerts", "view:streak", "view:bankroll", "sport:fantasy",
                "sport:intel", "sport:memes", "sport:lab"):
        assert f'"{ref}"' in block, f"{ref} fell out of the sheet"


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
