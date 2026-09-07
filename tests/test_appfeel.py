"""The app feel, and the small stuff that quietly signals "real".

Ethan, 2026-08-25: *"Make the PWA feel like an app, not a bookmark"* and
*"The small stuff that quietly signals real"*.

What shipped in this pass: the install prompt moved to the moment a
first bet is journaled, a skeleton for the strip (the picks host already
had one), an offline line that names which board you are looking at, a
live countdown on a board that is days out, a favicon badged with what
is still running, and an apology when a render throws.

Already live before it and checked here so the claim is auditable: the
bottom tab bar, the number ticks, the freshness pulses, a real 404, and
timestamps in the reader's own zone (tests/test_settings.py).

Run directly: `python3 tests/test_appfeel.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


APP = _read("web", "js", "app.js")
CSS = _read("web", "css", "styles.css")
HTML = _read("web", "index.html")


# --- the install prompt ------------------------------------------------------

def test_the_install_ask_waits_for_a_reason_to_come_back():
    """Ethan: "after a user journals their first bet, not on first
    visit". Somebody who has logged a bet has a reason to open this
    tomorrow; a stranger has none, and the sheet they dismiss is
    dismissed forever — A2HS_KEY goes to "off" and never re-arms."""
    i = APP.index("window.mbAdd")
    body = APP[i:APP.index("window.mbResult", i)]
    assert "bets.length === 1" in body, "it fires on every bet, which is nagging"
    assert "a2hsArm" in body and "a2hsTick" in body


def test_a_dismissal_is_still_final():
    i = APP.index("window.a2hsArm = function ()")
    body = APP[i:APP.index("\n};", i)]
    assert 'localStorage.getItem(A2HS_KEY) === "off"' in body


# --- skeletons ---------------------------------------------------------------

def test_the_strip_has_a_placeholder_shaped_like_what_replaces_it():
    """A placeholder of the wrong size is a layout shift with extra
    steps: the real cards land and everything jumps."""
    i = APP.index("function showSkeleton()")
    body = APP[i:APP.index("\n}", i)]
    assert 'getElementById("games")' in body
    assert "skeleton-game" in body
    assert "!strip.children.length" in body, \
        "it would flash placeholders over cards that are already up"
    i = CSS.index(".skeleton-game {")
    rule = CSS[i:CSS.index("}", i)]
    assert "272px" in rule, "the strip's card is 272 wide; this is not"


def test_no_animation_survives_a_reduced_motion_request():
    i = CSS.index("@media (prefers-reduced-motion: reduce) {\n  .skeleton-card")
    assert ".skeleton-game" in CSS[i:i + 160]


# --- offline -----------------------------------------------------------------

def test_offline_outranks_stale_and_unreachable():
    """It is the only one of the three that names a cause the reader can
    act on, and it changes what the other two mean."""
    i = APP.index("function renderStaleBar(ageMs, ago)")
    body = APP[i:APP.index("\nfunction updateAgo", i)]
    off = body.index("navigator.onLine === false")
    down = body.index("const down = wireDown();")
    assert off < down, "the offline check runs after the unreachable one"


def test_the_offline_line_names_which_board_you_are_looking_at():
    """Ethan: "showing the 7:42 board — you're offline". The board time,
    not a generic apology: /data/*.json is never cached, on purpose, so
    an offline app is showing numbers from whenever it last had a
    connection and has to say which moment that was."""
    i = APP.index("function renderStaleBar(ageMs, ago)")
    body = APP[i:APP.index("\nfunction updateAgo", i)]
    assert "tzTime(state.builtAt)" in body
    assert "You’re offline" in body


def test_losing_the_connection_repaints_the_bar():
    """Nothing else renders when a connection drops, so on a parked tab
    the line would never appear."""
    assert 'addEventListener("offline", refreshStaleBar);' in APP
    assert 'addEventListener("online", refreshStaleBar);' in APP


# --- the countdown -----------------------------------------------------------

def test_the_countdown_needs_a_real_instant_not_a_clock_reading():
    """"20:20" is a wall clock in Eastern with no date and no offset, and
    ET is two different offsets depending on the month. Reconstructed
    from the calendar; a failure returns null, because a missing
    countdown is a smaller lie than a wrong one."""
    i = APP.index("function zonedInstant(dateStr, hhmm, tz)")
    body = APP[i:APP.index("\n}", i)]
    assert "America/New_York" not in body, "the zone is the caller's to name"
    assert "return null" in body
    i = APP.index("function gameStartMs(g)")
    body = APP[i:APP.index("\n}", i)]
    assert 'kick.includes("T")' in body, "an ISO first pitch is already an instant"
    assert "America/New_York" in body


def test_the_countdown_stops_at_two_units():
    """"3 days, 4 hours, 12 minutes" invites somebody to watch the
    minutes at a distance where they are noise."""
    i = APP.index("function countdownText(ms)")
    body = APP[i:APP.index("\n}", i)]
    assert 'if (d) return `${unit(d, "day")}, ${unit(h, "hour")}`;' in body
    assert "ms <= 0" in body, "a passed kickoff would count up"


def test_the_countdown_lives_where_the_date_is_actually_known():
    """A board with no games cannot count down to one — we would be
    inventing the date. It rides the horizon strip, which exists
    precisely because the board is carrying a future slate."""
    i = APP.index("function renderSlateHorizon()")
    body = APP[i:APP.index("\nfunction renderGames", i)]
    assert "gameStartMs" in body and "countdownText" in body
    assert "setTimeout(renderSlateHorizon, 60000)" in body, \
        "a tab left open would sit claiming a distance it passed an hour ago"
    j = APP.index("function renderEmptySlate()")
    empty = APP[j:APP.index("\n/* ====", j)]
    assert "countdownText" not in empty, \
        "the no-games state has no date to count down to"


# --- the favicon badge -------------------------------------------------------

def test_the_badge_counts_what_is_still_running():
    i = APP.index("function faviconBadge()")
    body = APP[i:APP.index("\n  img.src", i)]
    assert 'String(b.result || "pending") === "pending"' in body
    assert "icon-192.png" in APP[i:i + 3000], "an SVG source draws differently per browser"


def test_an_empty_book_puts_the_plain_icon_back():
    """A badge saying nothing is worse than no badge, and this has to be
    reversible or a settled book keeps its old count forever."""
    i = APP.index("function faviconBadge()")
    body = APP[i:APP.index("\n  img.src", i)]
    assert "if (!open)" in body and "_faviconOrig.href" in body


def test_the_badge_follows_every_way_the_book_changes():
    """Logging, grading, deleting — and the account sync adopting a
    grading done on another device, which never goes through mbSave."""
    i = APP.index("function mbSave(bets)")
    assert "faviconBadge();" in APP[i:APP.index("\n}", i)]
    j = APP.index('if (name === "mybets") {')
    assert "faviconBadge();" in APP[j:j + 700]


# --- the apology -------------------------------------------------------------

def test_the_apology_reports_and_never_swallows():
    """This site's characteristic failure is a SILENT throw: the render
    stops, the previous content stays, and the page merely looks quiet.
    The reader cannot tell "nothing qualifies tonight" from "the code
    that draws this threw"."""
    i = APP.index("function crashNote(what)")
    body = APP[i:APP.index("\n}", i)]
    assert "_crashSaid" in body, "a throwing render loop would paper the screen"
    assert "slot.textContent" in body, \
        "an exception message is untrusted text and must not be innerHTML"
    assert 'addEventListener("unhandledrejection"' in APP, \
        "a rejected promise is how a throw inside a view transition arrives"


def test_a_missing_image_is_not_a_broken_page():
    """`error` fires for a 404'd image too, and apologising for a venue
    photo would train people to ignore the line."""
    i = APP.index('addEventListener("error", (e) => {')
    body = APP[i:APP.index("});", i)]
    assert "e.target && e.target.tagName" in body


# --- the ones that were already live -----------------------------------------

def test_the_thumb_navigation_and_the_real_404_are_still_there():
    assert 'class="tabbar"' in HTML
    assert os.path.exists(os.path.join(ROOT, "web", "404.html"))
    assert ".tb-item" in CSS


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
