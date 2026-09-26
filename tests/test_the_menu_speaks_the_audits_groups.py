"""Audit items 1 and 10: the menu speaks the audit's groups, and the two
switches fold under Filters.

Ethan's product audit, 2026-09-23: "I'd reduce the primary navigation to
roughly: HOME, PICKS, ODDS, RESEARCH, MY BOOK", and of the two sidebar
switches, "Those feel like internal application controls … settings
leaking into the landing experience."

The sidebar's folds read Odds, Research, My Book and Proof (the fold ids
are unchanged, so a reader's remembered folds survive), and the phone's
More sheet is grouped Picks · Odds · Research · My Book · Proof. The
High Confidence and Parlay Mode cards fold under a shut Filters heading
that says how many are on. Predict, Fantasy and Radar stay where Ethan
put them on 2026-09-10 (the audit's item 6 is his call).
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
    heads = re.findall(r'data-fold="([a-z]+)"\s+type="button" aria-expanded="false">([A-Za-z ]+)\n', SIDEBAR)
    assert heads == [("research", "Odds"), ("library", "Research"), ("tools", "My Book"),
                     ("proof", "Proof"), ("filters", "Filters")], heads
    assert ">Betting\n" not in SIDEBAR and ">Library\n" not in SIDEBAR


def test_the_switches_fold_under_filters_shut_by_default():
    i = SIDEBAR.index('data-fold="filters"')
    head = SIDEBAR[SIDEBAR.rindex("<button", 0, i):SIDEBAR.index("</button>", i)]
    assert 'aria-expanded="false"' in head and 'id="sb-filters-n" hidden' in head
    grp = SIDEBAR[SIDEBAR.index('<div class="sb-group sb-filters" data-group="filters" hidden>'):SIDEBAR.index("<!-- /.sb-filters -->")]
    assert 'id="sb-hcm"' in grp and 'id="sb-pz"' in grp and 'id="hcm-toggle"' in grp and 'id="pz-toggle"' in grp
    assert SIDEBAR.index('data-fold="filters"') < SIDEBAR.index('id="sb-hcm"'), "the heading sits above its switches"
    assert ".sb-filters-head { margin-top: auto; }" in CSS and ".sb-filters .sb-hcm { margin-top: 0; }" in CSS
    # The side apps stay where Ethan put them (2026-09-10).
    assert SIDEBAR.index('<div class="sb-apps"') < SIDEBAR.index('id="sport-switch"')


def test_the_heading_counts_what_is_on():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed"); return
    prog = """
      const store = {}; const localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } };
      const el = { hidden: true, textContent: "" };
      const document = { getElementById: (id) => (id === "sb-filters-n" ? el : null) };
    """ + _fn("paintFilterCount") + """
      const out = [];
      paintFilterCount(); out.push([el.hidden, el.textContent]);
      store.qb_hcm = "1"; paintFilterCount(); out.push([el.hidden, el.textContent]);
      store.qb_pz = "1"; paintFilterCount(); out.push([el.hidden, el.textContent]);
      store.qb_hcm = "0"; store.qb_pz = "0"; paintFilterCount(); out.push([el.hidden, el.textContent]);
      console.log(JSON.stringify(out));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [[True, ""], [False, "1 on"], [False, "2 on"], [True, ""]]
    assert "paintFilterCount();" in _fn("hcmPaint")
    assert "paintFilterCount();" in _fn("initPz")
    assert '"qb_hcm"' in _fn("paintFilterCount") and 'const HCM_KEY = "qb_hcm";' in APP
    assert '"qb_pz"' in _fn("paintFilterCount") and 'const PZ_KEY = "qb_pz";' in APP


def test_the_phone_sheet_uses_the_same_groups():
    i = APP.index("const MORE_GROUPS = [")
    block = APP[i:APP.index("];", i)]
    titles = re.findall(r'^\s*\["([A-Za-z ]+)",', block, re.M)
    assert titles == ["Picks", "Odds", "Research", "My Book", "Proof"], titles
    for ref in ("view:likely", "view:longshots", "view:zeno", "view:edge", "subtab:gamebets", "view:scanner",
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
