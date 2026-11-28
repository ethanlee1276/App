"""One destination, one name: in the menu, the tab bar, the page title and
the doors that lead there.

Audit 2026-09-30, V-16 (roadmap #46). The Most Likely board was "Top
Picks" in the menu, "Most Likely to Hit" on its page and "All Most Likely
picks" on the door to it. The Record was "Results" on the tab bar,
"Track Record" on its page and "Results" again on the deck's link. Line
Shopping's page said "Market Scanner", and Injuries & News said "Injury
Report". A reader following a door could not tell they had arrived.

The tab bar's "Picks" stays: Ethan named that tab for its group on
2026-09-28, and it opens Most Likely. The Rankings page keeps its
"rankings & standings" title (test_rankings_lead pins that choice).
Predict / Prediction Market is left as it is, because the sidebar's app
tile clips anything longer than one short word.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
HTML = (ROOT / "web" / "index.html").read_text()
sys.path.insert(0, str(ROOT))

from engine import askbot  # noqa: E402


def _visible(s):
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    return re.sub(r"^\s*//.*$", " ", s, flags=re.M)


def _label(container, attr):
    i = container.index(attr)
    j = container.index("</button>", i)
    return re.sub(r"<[^>]+>", " ", container[container.index(">", i) + 1:j]).split()[-2:]


SIDEBAR = HTML[HTML.index('id="sidebar"'):HTML.index("</aside>")]
TABBAR = HTML[HTML.index('<nav class="tabbar"'):HTML.index("</nav>", HTML.index('<nav class="tabbar"'))]


def test_the_menu_and_the_page_agree():
    assert _label(SIDEBAR, 'data-view="likely"') == ["Most", "Likely"]
    assert 'id="likely-title">Most Likely\n' in HTML or 'id="likely-title">Most Likely<' in HTML
    assert _label(SIDEBAR, 'data-sport="record"')[-1] == "Record"
    assert _label(TABBAR, 'data-sport="record"')[-1] == "Record"
    assert _label(SIDEBAR, 'data-view="scanner"') == ["Line", "Shopping"]
    assert '<div class="section-title">Line Shopping' in HTML
    assert _label(SIDEBAR, 'data-view="injuries"') == ["&amp;", "News"]
    assert '<div class="section-title">Injuries &amp; News' in HTML
    assert '<div class="section-title">Record' in HTML


def test_the_old_names_are_gone_from_what_a_reader_sees():
    seen = _visible(HTML) + _visible(APP)
    for old in ("Top Picks", "Most Likely to Hit", "All Most Likely picks",
                "Track Record", "Market Scanner", "Injury Report", "Results page",
                '"record", "Results")'):
        assert old not in seen, old
    assert "Results</button>" not in TABBAR


def test_the_doors_say_where_they_go():
    assert '<b>Most Likely</b>' in APP
    assert 'deckHead("The record", "#record", "record", "Record")' in APP


def test_ask_uses_the_same_names():
    assert "Top Picks" not in askbot.SITE_GUIDE
    for name in ("Most Likely", "Record", "Line Shopping", "Edge Picks"):
        assert name in askbot.SITE_GUIDE, name


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
