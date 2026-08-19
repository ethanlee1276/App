"""The small screens from Ethan's render pack: 404, maintenance, alerts.

Renders 23 and 24 are a numeral and a wrench over "We'll Be Right
Back!"; render 14 is an alerts list with a toggle on every row. Two
rules decide what crosses:

  * A PAGE MAY NOT PROMISE WHAT THE SOFTWARE CANNOT DO. The maintenance
    page never guesses a time ("back in 5 minutes" is the first thing
    that lies to a reader), and the alerts page ships no per-row toggle
    and no "Create New Alert" — it is a digest of feeds we already
    hold, and a switch that turns nothing on is a lie you can click.
  * A 404 IS FOR A PAGE, NOT FOR AN ASSET. Handing a browser HTML where
    it asked for a script turns a clear console error into a blank
    screen, so the pretty page is served only for page-shaped paths.

Run directly: `python3 tests/test_stub_pages.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


NOT_FOUND = _read("web", "404.html")
MAINT = _read("web", "maintenance.html")
CSS = _read("web", "css", "styles.css")
APP = _read("web", "js", "app.js")
SERVER = _read("server.py")


def test_both_stubs_are_real_pages_in_the_house_style():
    for doc in (NOT_FOUND, MAINT):
        assert 'href="css/styles.css"' in doc, "a stub off the theme is a stub"
        assert "Qellys" in doc
        assert 'href="index.html"' in doc, "every stub carries a door home"
    assert "404" in NOT_FOUND
    for sel in (".stub {", ".stub-num {", ".stub-mark {", ".stub-cta {"):
        assert sel in CSS, f"{sel} is unstyled"


def test_the_maintenance_page_promises_no_clock():
    """The render says "We'll Be Right Back!" over a countdown. We do not
    know when a rebuild finishes, so the page says what IS true — nothing
    settled is touched — and what to do if it is still up in an hour."""
    # The page's own comment explains the rule, so scan the MARKUP only.
    low = re.sub(r"<!--.*?-->", "", MAINT, flags=re.S).lower()
    for lie in ("back in 5", "back in five", "minutes", "estimated time"):
        assert lie not in low, f"the maintenance page guessed a time: {lie}"
    assert not re.search(r"\beta\b", low), "the page quoted an ETA"
    assert "settled stays settled" in MAINT


def test_the_404_page_is_served_for_pages_and_not_for_assets():
    i = SERVER.index("def _static(")
    body = SERVER[i:i + 1400]
    assert '"404.html"' in body
    assert 'target.suffix in ("", ".html", ".htm")' in body, \
        "an asset miss must keep the bare body, not a page of HTML"
    assert 'b"Not found"' in body, "the asset path still answers plainly"


def test_the_alerts_page_reports_feeds_and_sells_no_subscription():
    i = APP.index("function renderAlerts(")
    body = APP[i:APP.index("\nfunction ", i + 10)]
    # Comments explain what was deliberately NOT copied, so scan the CODE
    # or the test matches its own reasoning.
    code = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
    # The render's chrome that has no engine behind it.
    for banned in ("Create New Alert", "createAlert", 'type="checkbox"',
                   "al-toggle", "Notify me"):
        assert banned not in code, f"alerts grew a promise it cannot keep: {banned}"
    # What it does ship: the filter chips and a condition under each row.
    assert "al-cats" in body and "_alSet(" in body
    assert "al-c" in body, "every row prints the condition that fired it"
    for cat in ("Line moves", "Injuries", "The desk"):
        assert cat in body, f"filter lost {cat}"
    for sel in (".al-cats {", ".al-row {", ".al-ic {"):
        assert sel in CSS, f"{sel} is unstyled"


def test_the_alert_rows_still_come_from_the_three_real_feeds():
    """The restyle must not have quietly invented a fourth source."""
    i = APP.index("function renderAlerts(")
    body = APP[i:APP.index("\nfunction ", i + 10)]
    assert "d.recommendations" in body and "move_delta" in body
    assert "d.injury_watch" in body
    assert "_railDeskCache" in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
