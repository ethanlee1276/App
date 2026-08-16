"""The sign-in screen has an address of its own.

Ethan, 2026-08-16: *"the login page is hidden and should be on the main
screen with maybe an account icon in the top right … it needs to look
professional."*

It was hidden in a way worth naming, because nothing was broken. The form
existed, worked, and was tested — it was mounted three cards down inside
My Bets, reachable only by pressing an unlabelled person glyph. A thing
with no address cannot be linked to, cannot be bookmarked, and cannot be
where you send somebody who has just hit a paywall. That last one is why
this had to land before the gate: every locked board needs a destination.

These tests are about wiring and hierarchy rather than pixels. A
screenshot proves it looked right once; these prove the button that says
Sign in is the one a signed-out visitor is pushed towards, and that the
screen is still reachable after the next refactor.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


APP = _read("web", "js", "app.js")
HTML = _read("web", "index.html")
CSS = _read("web", "css", "styles.css")


def test_the_account_screen_is_a_view_with_its_own_url():
    """`#account` in the address bar is what makes it linkable — from a
    locked board, from an email, from a bookmark."""
    assert 'id="view-account"' in HTML
    assert 'id="account-body"' in HTML
    order = re.search(r"const VIEW_ORDER = \[(.*?)\];", APP, re.S).group(1)
    assert '"account"' in order, "the view exists but nothing can route to it"


def test_switching_to_it_waits_for_the_server_before_drawing():
    """The whole screen depends on "who is this". Drawn before the answer
    lands, it shows the sign-in form to somebody already signed in — which
    is the single most alarming thing a page like this can do."""
    assert "acctWho().then(renderAccount)" in APP


def test_the_topbar_chip_says_sign_in_rather_than_showing_a_glyph():
    """A bare person mark reads as "settings". What sits behind it is the
    only route to paying for anything."""
    assert "nav-acct-out" in APP and "nav-acct-out" in CSS
    i = APP.index("const acctBtn")
    block = APP[i:i + 1800]
    assert ">Sign in</span>" in block or "Sign in</span>" in block, \
        "the signed-out chip has no words on it"
    assert 'switchView("account", true)' in block, \
        "the chip still lands somewhere other than the account screen"


def test_sign_in_is_the_primary_action_on_the_sign_in_screen():
    """It shipped the other way round: "Create account" was the filled
    button and came first, with Sign in as a ghost below it. Most people
    arriving at a login screen already have an account."""
    i = APP.index("acctAuth(this, 'login')")
    j = APP.index("acctAuth(this, 'signup')", i - 400 if i > 400 else 0)
    # The login button must come first in the markup…
    assert i < j, "Create account still precedes Sign in"
    # …and be the filled one, not the ghost.
    line = APP[APP.rindex("<button", 0, i):i]
    assert 'class="btn"' in line, "Sign in is still the secondary button"


def test_the_screen_does_not_carry_two_competing_headings():
    """"Sign in to Qellys Book" above a card headed "Make an account" tells
    a visitor they are on the wrong page."""
    assert "Sign in to Qellys Book" in APP
    assert "<div class=\"player\">Make an account</div>" not in APP


def test_my_bets_and_fantasy_show_a_strip_not_a_second_sign_in_form():
    """Two forms for one thing is how a password gets typed into the one
    that is not wired up."""
    assert APP.count("acctStripHTML()") >= 2
    assert "${acctCardHTML()}\n    ${form}" not in APP, \
        "My Bets still mounts the full sign-in card"


def test_the_form_stacks_at_a_sign_in_measure():
    """`.acct-row` is a wrapping flex row built for a board-width card. At
    30rem it wrapped into a ragged three-row arrangement — email, then
    password sharing a line with a button, then a button alone."""
    assert ".acct-screen .acct-row" in CSS
    block = CSS[CSS.index(".acct-screen .acct-row"):][:400]
    assert "column" in block


def test_the_render_sweep_covers_it():
    """A view absent from the sweep is a view nobody renders until a user
    does. Weather and Alerts were both missing once and both crashed on
    load; this is now the page every locked board points at, where a
    silent crash costs a subscription rather than a glance."""
    launch = _read("launch.py")
    sweep = launch[launch.index("SWEEP_VIEWS = ["):]
    sweep = sweep[:sweep.index("]\n")]
    assert "#account" in sweep, "the account screen is not in SWEEP_VIEWS"
    assert "#account-body" in sweep, "the sweep does not wait for its content"


def test_the_screen_still_promises_only_things_that_are_true():
    """The assurances sit beside the button precisely because that is
    where an objection is felt, which is also what makes an inaccurate one
    expensive. Each of these is a fact about how the site is built."""
    i = APP.index("acct-assure")
    block = APP[i:i + 700]
    assert "Paddle" in block, "the card promise no longer names the processor"
    assert "takes no bets" in block
    # …and not the claim that was already made twice on the same screen.
    assert block.count("sportsbook or ESPN password") == 0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
