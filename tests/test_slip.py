"""The parlay slip and the Messages inbox.

Ethan, 2026-08-25: *"there also should be a way for players to select
props and put them in a parlay so they can parlay props together so they
can send it to there friends. we will calculate odds for the parlays as
well … they should show up how it works on sports books … and they show
up on the bottom"* — and — *"there should be a message button at the top
with an inbox with the messages from friends."*

The structural rules pinned here:

  * THE SLIP IS LOCAL, THE SHARE IS A POINTER. The reader's own slip
    holds sides, lines and prices — read off a board their entitlement
    served. What leaves for a friend is player+market per leg, nothing
    else, and the send site proves it by construction.
  * THE ODDS ARE A BOOK'S ARITHMETIC, SAID PLAINLY. Decimal products,
    independence assumed, with the assumption stated on the panel —
    never borrowed authority from the engine's correlation-priced SGPs.

Run directly: `python3 tests/test_slip.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


APP = _read("web", "js", "app.js")
HTML = _read("web", "index.html")
CSS = _read("web", "css", "styles.css")


def _fn(marker):
    i = APP.index(marker)
    return APP[i:APP.index("\n}", i)]


# --- the slip ----------------------------------------------------------------

def test_the_slip_survives_a_reload_and_holds_one_board():
    assert 'SLIP_KEY = "qb_slip_v1"' in APP
    body = _fn("function slipToggle(r)")
    assert "s.sport !== state.sport" in body, \
        "legs from two different boards would build an unsendable ticket"
    assert "SLIP_MAX" in body


def test_the_ceiling_is_eight_legs():
    assert "const SLIP_MAX = 8;" in APP
    src = _read("engine", "social.py")
    assert "MAX_PARLAY_LEGS = 8" in src, \
        "the slip and the share disagree about how long a ticket can be"


def test_the_combined_price_is_a_decimal_product():
    """What every book does to an uncorrelated ticket — and the panel
    says so instead of borrowing the SGP engine's authority."""
    body = _fn("function slipAmerican()")
    assert "mbDecimal(l.odds)" in body and "dec *=" in body
    assert "Math.round((dec - 1) * 100)" in body
    i = APP.index("function slipRender()")
    panel = APP[i:i + 4000]
    assert "same-game\n        correlation is not priced here" in panel or \
           "correlation is not priced here" in panel, \
        "the independence assumption is no longer stated"


def test_what_leaves_the_device_is_identity_only():
    """The send handler maps each leg to exactly {player, market} before
    the POST — the sides, lines and prices the local slip holds never
    enter the request body."""
    i = APP.index('fetch("/api/social/send-parlay"')
    body = APP[i - 600:i + 600]
    assert "s.legs.map((l) => ({ player: l.player, market: l.market }))" in body
    for word in ("l.side", "l.line", "l.odds"):
        assert word not in body, f"{word} rides in the parlay share"


def test_the_dock_exists_and_sits_above_the_phone_tab_bar():
    assert '<div id="qb-slip" hidden></div>' in HTML
    assert HTML.index('id="qb-slip"') < HTML.index('class="tabbar"'), \
        "the dock markup should precede the tab bar it docks above"
    assert "#qb-slip { position: fixed" in CSS
    assert "#qb-slip { bottom: calc(58px + env(safe-area-inset-bottom)); }" in CSS, \
        "on a phone the slip would hide underneath the tab bar"


def test_an_empty_slip_shows_no_bar():
    body = _fn("function slipRender()")
    assert "host.hidden = true" in body


def test_the_add_control_reaches_the_places_picks_live():
    # The prop page's nav, the big board card's chip row, and Top Picks.
    assert APP.count("data-slip=") >= 3, \
        "the add-to-slip control lost one of its surfaces"
    i = APP.index("function slipChip(r)")
    body = APP[i:APP.index("\n}", i)]
    assert "r.odds == null" in body, \
        "a prop with no price cannot be a parlay leg"


# --- messages ----------------------------------------------------------------

def test_the_messages_view_is_registered_everywhere_a_view_must_be():
    assert 'id="view-messages"' in HTML and 'id="messages-body"' in HTML
    assert '"alerts", "messages", "streak"' in APP.replace("\n", " ") or \
           '"messages"' in APP[APP.index("const VIEW_ORDER"):
                               APP.index("]", APP.index("const VIEW_ORDER"))]
    assert 'if (name === "messages") renderMessages();' in APP


def test_the_topbar_carries_the_envelope_and_an_honest_badge():
    assert 'id="nav-msg"' in HTML
    i = HTML.index('id="nav-msg-badge"')
    assert "hidden" in HTML[i - 200:i + 60], \
        "the badge ships visible — a red dot with nothing behind it"
    body = _fn("function msgBadge()")
    assert "b.hidden = !n" in body
    assert '"9+"' in body, "a 47-message badge would stretch the topbar"


def test_seen_is_marked_after_display_on_the_messages_page_too():
    # Sliced to the finder function that follows — the render-pack
    # rebuild (tabs, filters, requests) grew the body past a fixed
    # window, which is exactly the slice bug the suite keeps relearning.
    i = APP.index("async function renderMessages()")
    body = APP[i:APP.index("async function msgFinderHTML", i)]
    assert "setTimeout" in body and "/api/social/seen" in body
    assert body.index("host.innerHTML") < body.index("/api/social/seen"), \
        "seen fires before the rows are on screen"


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
