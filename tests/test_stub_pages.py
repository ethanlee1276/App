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
    # THE WHOLE FUNCTION, not a character count. This read `i + 1400`
    # and broke the day `_static` grew a branch above the 404 fallback
    # (the service worker's version stamp, 2026-08-19) — the claims were
    # all still true, the window had simply stopped reaching them. A test
    # that fails when unrelated code moves is a test people learn to
    # ignore.
    i = SERVER.index("def _static(")
    j = SERVER.index("\n    def ", i + 10)
    body = SERVER[i:j]
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


def test_the_plan_cards_invent_no_tier_and_quote_no_unsourced_price():
    """Render 21 shows three priced tiers. This card is not the price
    list — it is the FREE-vs-PAID split, drawn from engine/gate.py's own
    FREE_FILES/PAID_FILES rather than from a marketing page. Two cards,
    no invented tiers.

    IT USED TO QUOTE NO PRICE AT ALL, because there was none to quote:
    one plan, at a Paddle price this side did not know. Since 2026-08-21
    there are three real prices in `billing.PLANS`, and this card names
    the cheapest as an entry point and sends people to the plans page for
    the rest.

    ONE PRICING SURFACE IS THE RULE. Printing all three here as well
    would be a second place for them to be wrong, and the failure is not
    cosmetic — a page advertising one number while Checkout charges
    another is a chargeback. So exactly two figures are allowed: $0 for
    free, and the monthly price, which must equal the one in
    `billing.PLANS` rather than being typed.
    """
    from engine import billing
    # THE SLICE IS THE FUNCTION, not everything up to the next async one.
    # The wider boundary swept in whatever constants happened to live
    # between the two, and the moment PLAN_EXTRAS landed there — with the
    # words "Save $25" in it — this test failed on a file it does not
    # describe. A boundary that drifts makes a passing test meaningless
    # too, which is the half nobody notices.
    i = APP.index("function billPlansHTML(")
    body = APP[i:APP.index("\n}\n", i) + 3]
    assert body.count('class="card plan') == 2, "a third tier was invented"
    prices = re.findall(r"\$\d[\d.,]*", body)
    monthly = f"${billing.PLANS['monthly']['cents'] // 100}"
    assert prices == ["$0", monthly], (
        f"the plan card quotes {prices}; it may quote only $0 and the "
        f"monthly price ({monthly}), and the other two plans belong on "
        "the plans page where the buy buttons are")
    for word in ("Premium", "Elite", "/mo"):
        assert word not in body, f"invented a tier or a term: {word}"
    assert "Stripe" in body and "billSeePlans()" in body, \
        "the paid card must name the processor and reach the plans page"
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

VIS = _read("web", "js", "visuals.js")


def test_a_number_that_moved_says_so_and_a_first_sight_does_not():
    """Ethan, 2026-08-19: "add more animations." This is the half with
    information in it — the board reloads on a timer, so a price could
    move four cents while you watched and the render said nothing.

    The rule that keeps it from becoming decoration: a key seen for the
    FIRST time is recorded silently. Without that every cell flares on
    first paint, which is an entrance animation wearing a data costume —
    and §3.4 threw those out once already."""
    i = VIS.index("function mountLiveTicks(")
    body = VIS[i:VIS.index("\nif (typeof window", i)]
    assert "_tickSeen" in body
    assert "if (was === undefined || was === now) continue;" in body, \
        "a first sighting, or an unchanged number, must not animate"
    # The count is cosmetic; the flash is the message. Reduced motion
    # keeps the message and drops the count.
    assert "if (quiet) continue;" in body
    assert "prefers-reduced-motion" in VIS
    for sel in (".tick-up {", ".tick-down {", "@keyframes tickUp"):
        assert sel in CSS, f"{sel} is unstyled"
    # Tinting the digits would fight the green/red the cell already uses
    # to mean YES and NO, so the flash is a background.
    ku = CSS[CSS.index("@keyframes tickUp"):CSS.index("@keyframes tickDown")]
    assert "background:" in ku and "color:" not in ku


def test_view_transitions_are_native_scoped_and_optional():
    """The browser's own page cross-fade: no library, no bytes. Scoped to
    <main> so the masthead and sidebar are not captured, and declined
    outright when the reader asked for less motion."""
    i = APP.index("function switchView(")
    body = APP[i:APP.index("function _switchViewNow(", i)]
    assert "document.startViewTransition" in body
    assert "prefers-reduced-motion" in body, "motion preference is ignored"
    assert "state.quiet" in body
    # Falls through to the plain swap where the API is absent.
    assert 'typeof document.startViewTransition === "function"' in body
    assert "main { view-transition-name: page; }" in CSS
    # Compositor properties only, and inside the 300ms UI ceiling.
    seg = CSS[CSS.index("::view-transition-old(page)"):
              CSS.index("@keyframes vtEnter") + 200]
    assert "var(--dur-base)" in seg
    for prop in ("width", "height", "left", "top"):
        assert f"{prop}:" not in seg, f"view transition animates {prop}"


def test_press_feedback_is_transform_only_and_short():
    """What separates a web page from an app on a phone is that something
    moves under your thumb. It has to be transform (compositor) and it has
    to be quick, or it reads as lag rather than as the surface giving."""
    i = CSS.index("/* ---- Press feedback")
    seg = CSS[i:i + 1200]
    assert "transform: scale(" in seg
    assert "transition: transform var(--dur-fast)" in seg, \
        "press feedback must ride the duration ladder, not a raw ms"
    for prop in ("width:", "height:", "margin:", "padding:"):
        assert prop not in seg, f"press feedback animates {prop}"
    # And it is dropped for a reader who asked for less motion.
    rm = CSS[CSS.index("@media (prefers-reduced-motion: reduce) {",
                       CSS.index("main { view-transition-name: page; }")):]
    assert ".plan-btn:active { transform: none; }" in rm[:900]


def test_a_score_never_claims_the_run_was_good_for_you():
    """Direction is not always meaning. A price rising is good or bad for
    the reader and green/red says which; a SCORE only ever rises, so
    tinting the opponent's run green would be the colour making a claim
    nobody made. Those cells ask for `neutral` and get "this changed"."""
    i = VIS.index("function mountLiveTicks(")
    body = VIS[i:VIS.index("\nif (typeof window", i)]
    assert 'data-tick-mode' in body and 'mode === "neutral"' in body
    # No count either: 3 to 4 has no in-between worth animating.
    neutral = body[body.index('if (mode === "neutral")'):]
    assert "continue;" in neutral[:400]
    assert ".tick-move {" in CSS and "@keyframes tickMove" in CSS
    tm = CSS[CSS.index("@keyframes tickMove"):]
    assert "var(--brand)" in tm[:220], "the neutral flash must not be good/bad"
    # Live scores are the surface that needs it.
    assert 'data-tick-mode="neutral"' in APP
    assert 'data-tick="ls:' in APP, "live scores never opted in"


def test_the_ticks_reach_every_surface_whose_numbers_move():
    """A helper wired to one board is half a feature. The three surfaces
    that actually change under a reader are the prediction-market prices,
    the desk's recommended rows, and live scores."""
    # Counts BOTH shapes the mount is called in. renderIntel stopped
    # calling it by name on 2026-08-19 and started running it through a
    # loop with its two siblings, each in its own try — because chained
    # bare, the first to throw silently cancelled the rest and the price
    # chart never upgraded. The invariant is "every surface that can
    # change numbers mounts the ticks", and counting one literal spelling
    # measured the spelling instead.
    direct = APP.count("mountLiveTicks(host)")
    looped = APP.count("mountLiveTicks]") + APP.count("mountLiveTicks,")
    assert direct + looped >= 3, \
        "a render path that can change numbers is not calling the mount"
    for key in ('data-tick="y:', 'data-tick="n:', 'data-tick="d:', 'data-tick="ls:'):
        assert key in APP, f"no cell opts in with {key}"



if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
