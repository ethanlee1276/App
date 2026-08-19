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


def test_the_plan_cards_invent_no_tier_and_no_price():
    """Render 21 shows three priced tiers. There is ONE real plan — a
    single Paddle price the server does not know the amount of — so the
    page ships two cards, quotes no number it cannot source, and splits
    the features the way engine/gate.py actually splits the files."""
    i = APP.index("function billPlansHTML(")
    body = APP[i:APP.index("\nasync function renderBilling(", i)]
    assert body.count('class="card plan') == 2, "a third tier was invented"
    # The one number on the page is the free one, which is true.
    assert "$0" in body
    prices = re.findall(r"\$\d[\d.,]*", body)
    assert prices == ["$0"], f"invented a price: {prices}"
    for word in ("Premium", "Elite", "/mo", "per month"):
        assert word not in body, f"invented a tier or a term: {word}"
    assert "Paddle" in body and "billSubscribe(this)" in body, \
        "the paid card must go to the real checkout"
    # And the free half is the gate's own free half.
    for free in ("Record page", "injury report", "fantasy room"):
        assert free.lower() in body.lower(), f"free list lost {free}"
    for sel in (".plan-grid {", ".plan-price {", ".plan-band {"):
        assert sel in CSS, f"{sel} is unstyled"


def test_the_bet_log_table_is_a_view_of_the_same_rows():
    """Render 12's dense table. It must be a VIEW switch over the bets
    already stored, not a second store — and it may not print a market
    label the log does not carry."""
    i = APP.index("const tableRow = (b) =>")
    body = APP[i:APP.index("const betTable", i)]
    for col in ("b.date", "b.desc", "b.odds", "b.stake", "mbProfit(b)"):
        assert col in body, f"table lost {col}"
    assert "mbToWin(b)" in body, "a pending row shows what it stands to return"
    assert "legs ? `${legs.length}-leg parlay`" in body, \
        "type comes from the ticket's own shape, never an invented market"
    j = APP.index("const vw = window._mbView")
    assert "_mbView='table'" in APP and "_mbView='cards'" in APP
    assert 'vw === "table" ? betTable(shown)' in APP, \
        "both views must render the same filtered rows"
    assert ".mb-table-wrap {" in CSS and ".mbc-view {" in CSS


def test_every_market_row_opens_with_a_mark_not_a_word():
    """Ethan, 2026-08-19: "you never added the thumbnails for the Kalshi
    and Polly market bets." Every other board opens a row with art; these
    opened with a word in a box. What each kind may honestly wear is the
    point — a sports row borrows the fixture's own team marks, a weather
    row wears a sun because the market IS a daily-high bracket, and the
    venue wears OUR monogram rather than a traced logo."""
    i = APP.index("function deskThumb(")
    body = APP[i:APP.index("\nfunction deskSectionHTML(", i)]
    assert "teamMark(" in body and "teamsForSport(" in body, \
        "a matched fixture must draw the same marks the rest of the site does"
    assert 'icon("sun"' in body, "a temperature market has a temperature mark"
    # The icon labels the CATEGORY; one that moved with the number would be
    # the picture making a claim the model did not.
    assert "forecast_f" not in body.split('icon("sun"')[1][:200], \
        "the weather mark must not vary with the forecast"
    # The venue monogram is ours, and it is used on both surfaces.
    j = APP.index("function venueMark(")
    vm = APP[j:APP.index("\nfunction deskThumb(", j)]
    assert "vmark" in vm and "kalshi" in vm and "poly" in vm
    assert APP.count("venueMark(") >= 3, "board and detail panel both wear it"
    for sel in (".kx-thumb {", ".kx-thumb-ic {", ".vmark {", ".vmark.kalshi {"):
        assert sel in CSS, f"{sel} is unstyled"
    # The phone grid places cells by NAME; the thumbnail took the chip's
    # slot in the markup and must take it in the layout too.
    assert ".kx-sport, .kx-thumb { grid-area: sport; }" in CSS


def test_the_record_scopes_wear_the_same_purple_as_every_other_filter():
    """Ethan, 2026-08-19, ringing the row: "fix these buttons on the
    record page to match all the other buttons which are all purple."
    They were underlined tabs while every other filter row on the site
    is a pill that fills with brand violet when active."""
    i = CSS.index(".rec-scope {")
    seg = CSS[i:i + 900]
    assert "var(--grad-brand)" in seg, "the active scope is not brand-filled"
    assert "border-bottom-color" not in seg, "the underline treatment survived"
    # And it is the SAME fill the sidebar's sport chips use, not a new one.
    j = CSS.index(".sb-chips .sport-btn.active")
    assert "var(--grad-brand)" in CSS[j:j + 200]


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
